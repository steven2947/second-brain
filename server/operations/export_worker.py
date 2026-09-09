"""无模型、无额度消费的私有导出租约worker；生成和下载均即时核对许可。"""
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.utils import timezone
from accounts.models import User
from access.context import owner_transaction
from access.services import access_snapshot, analysis_snapshot, KnowledgeError
from answers.models import Answer
from answers.services import get_answer
from learning.models import LearningSession, LearningTurn
from learning.services import session_public, turn_public
from learning.serializers import LearningTurnSerializer
from personal.models import Bookmark, ActionRecord, Feedback
from problems.models import Problem, Message
from problems.services import _current_user, _public, _uuid, not_found, ProblemError
from .models import PersonalExport
from .privacy import digest

MAX_RECORDS = 10000
MAX_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class ExportLease:
    """可信worker持有的尝试标识，过期或重领令牌无法发布文件。"""
    owner_id: UUID
    export_id: UUID
    token: UUID
    attempt: int


def _rows(user, scope):
    """user/scope为本人和固定范围；有界物化，超限明确失败而非静默截断。"""
    queries = {}
    if scope in ('problems', 'all_personal'):
        queries.update(problems=Problem.objects.filter(owner=user, status__in=['active', 'archived']),
            messages=Message.objects.filter(owner=user, problem__status__in=['active', 'archived'], visibility='visible'),
            answers=Answer.objects.filter(owner=user, problem__status__in=['active', 'archived'],
                run__job__status='succeeded', run__outcome='answer'),
            actions=ActionRecord.objects.filter(owner=user, problem__status__in=['active', 'archived']),
            feedback=Feedback.objects.filter(owner=user, answer__problem__status__in=['active', 'archived']))
    if scope in ('learning', 'all_personal'):
        visible = Q(problem=None) | Q(problem__status__in=['active', 'archived'])
        sessions = LearningSession.objects.filter(visible, owner=user)
        queries.update(learning=sessions, learning_turns=LearningTurn.objects.filter(owner=user,
            learning_session__in=sessions))
    if scope == 'all_personal':
        queries['bookmarks'] = Bookmark.objects.filter(owner=user)
    rows, count = {}, 0
    for name, query in queries.items():
        items = list(query.order_by('id')[:MAX_RECORDS + 1 - count])
        count += len(items)
        if count > MAX_RECORDS:
            raise ProblemError('EXPORT_TOO_LARGE', '记录超过导出上限，请选择较小范围或联系支持', 413)
        rows[name] = items
    return rows


def _permissions(user, rows):
    """user/rows为同一次本人数据；每个版本分别核对browse/analyze与短引策略。"""
    releases = {row.release_id for name in ('problems', 'learning', 'bookmarks') for row in rows.get(name, [])}
    permissions = {}
    for release_id in sorted(releases):
        state = {}
        for name, loader in (('browse', access_snapshot), ('analyze', analysis_snapshot)):
            try:
                state[name] = digest(loader(user, release_id))
            except KnowledgeError:
                state[name] = None
        permissions[str(release_id)] = state
    return permissions


def snapshot(user, scope, rows=None):
    """user/scope为当前身份与范围；摘要绑定真实许可及所有记录变化、删除与修订。"""
    rows = rows if rows is not None else _rows(user, scope)
    return {'epoch': user.auth_epoch, 'access_revision': user.access_revision,
        'permissions': _permissions(user, rows), 'records': digest({name: [
            [row.pk, row.updated_at, getattr(row, 'revision', None), getattr(row, 'status', None)]
            for row in items] for name, items in rows.items()})}


def _fields(row, names):
    """row为本人记录；names是本功能明确公开白名单。"""
    return {name: getattr(row, name) for name in names}


def build_payload(user, row, pulse=lambda: None):
    """user/row为持租约本人任务；返回可读个人记录与当前许可绑定，不含内部包。"""
    with owner_transaction(user.pk):
        user = _current_user(user)
        rows = _rows(user, row.scope)
        binding = snapshot(user, row.scope, rows)
    payload = {'schema_version': 1, 'export_id': str(row.pk), 'scope': row.scope,
        'generated_at': timezone.now(), 'problems': [], 'messages': [], 'answers': [],
        'learning': [], 'learning_turns': [], 'bookmarks': [], 'actions': [], 'feedback': [], 'omissions': []}
    if row.scope == 'all_personal':
        from accounts.serializers import public_user
        payload['profile'] = public_user(user)
    def permitted(release_id, purpose='analyze'):
        """release_id/purpose为记录所依附版本与所需用途。"""
        return binding['permissions'][str(release_id)][purpose] is not None
    def omit(kind, identifier):
        """kind/identifier标记知识正文缺失，用户自己的原始记录继续保留。"""
        payload['omissions'].append({'kind': kind, 'id': str(identifier), 'reason': 'KNOWLEDGE_UNAVAILABLE'})
    for problem in rows.get('problems', []):
        pulse()
        payload['problems'].append(_public(problem, user))
    problem_releases = {item.pk: item.release_id for item in rows.get('problems', [])}
    for message in rows.get('messages', []):
        pulse()
        if message.kind == 'answer':
            # 正式答案仅通过get_answer当前短引投影导出，绝不复用旧消息markdown。
            continue
        if message.role != 'user' and not permitted(problem_releases[message.problem_id]):
            omit('message', message.pk)
            continue
        payload['messages'].append(_fields(message, ('id', 'problem_id', 'sequence', 'role', 'kind', 'content', 'created_at')))
    answers = {}
    for answer in rows.get('answers', []):
        pulse()
        try:
            answers[answer.pk] = get_answer(user, answer.pk)
            payload['answers'].append(answers[answer.pk])
        except ProblemError as error:
            if error.status != 404:
                raise
            omit('answer', answer.pk)
    sessions = {session.pk: session for session in rows.get('learning', [])}
    for session in sessions.values():
        pulse()
        payload['learning'].append({**session_public(session), 'library_available': permitted(session.release_id)})
    for turn in rows.get('learning_turns', []):
        pulse()
        if turn.kind not in ('user_request', 'user_response') and not permitted(sessions[turn.learning_session_id].release_id):
            omit('learning_turn', turn.pk)
            continue
        payload['learning_turns'].append(LearningTurnSerializer(turn_public(turn)).data)
    for bookmark in rows.get('bookmarks', []):
        pulse()
        payload['bookmarks'].append({**_fields(bookmark, ('id', 'release_id', 'core_card_id', 'note', 'created_at', 'updated_at')),
            'library_available': permitted(bookmark.release_id, 'browse')})
    for action in rows.get('actions', []):
        pulse()
        item = _fields(action, ('id', 'problem_id', 'answer_id', 'action_index', 'status', 'observation', 'revision', 'created_at', 'updated_at'))
        answer = answers.get(action.answer_id)
        item['advice'] = answer['content']['actions'][action.action_index] if answer and action.action_index < len(answer['content']['actions']) else None
        if item['advice'] is None:
            omit('action_advice', action.pk)
        payload['actions'].append(item)
    payload['feedback'] = [_fields(item, ('id', 'answer_id', 'category', 'comment', 'created_at')) for item in rows.get('feedback', [])]
    return payload, binding


def file_path(owner_id, key, *, create=False):
    """owner_id/key必须是服务端UUID存储键；只访问private root内确切文件，拒绝符号链接。"""
    owner = str(UUID(str(owner_id)))
    if not re.fullmatch(r'[0-9a-f-]{36}-[0-9a-f-]{36}\.json', key):
        raise ValueError('无效导出存储键')
    UUID(key[:36]), UUID(key[37:73])
    root = Path(settings.SB_PRIVATE_DATA_ROOT).resolve()
    if create:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = root
    for name in ('exports', owner):
        directory = directory / name
        if directory.is_symlink():
            raise ValueError('导出目录不可为符号链接')
        if create:
            directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / key
    if path.is_symlink():
        raise ValueError('导出文件不可为符号链接')
    return path


def _locked(lease):
    """lease来自可信worker；只有当前未过期令牌及原身份可继续发布。"""
    user = User.objects.select_for_update().filter(pk=lease.owner_id).first()
    row = PersonalExport.objects.select_for_update().filter(owner_id=lease.owner_id, pk=lease.export_id).first()
    if (user is None or row is None or row.status != 'running' or row.lease_token != lease.token
            or row.attempts != lease.attempt or row.lease_until is None or row.lease_until <= timezone.now()):
        return None
    if (user.status != 'active' or user.is_staff or user.is_superuser or user.auth_epoch != row.auth_epoch
            or user.access_revision != row.access_revision or row.deadline <= timezone.now()):
        row.status, row.error_code, row.lease_token, row.lease_until = 'failed', 'ACCESS_REVOKED', None, None
        row.save(update_fields=['status', 'error_code', 'lease_token', 'lease_until', 'updated_at'])
        return None
    return user, row


def heartbeat(lease):
    """lease为当前尝试；只在独立短事务续租，不延长总截止时间。"""
    with owner_transaction(lease.owner_id):
        locked = _locked(lease)
        if locked is None:
            return False
        _, row = locked
        row.lease_until = min(timezone.now() + timedelta(seconds=60), row.deadline)
        row.save(update_fields=['lease_until', 'updated_at'])
        return True


def claim(owner_id):
    """owner_id为调度器当前账号；最多20个候选，重启重领最多三次且总截止15分钟。"""
    with owner_transaction(owner_id):
        user = User.objects.select_for_update().filter(pk=owner_id).first()
        if user is None:
            return None
        now = timezone.now()
        rows = PersonalExport.objects.select_for_update(skip_locked=True).filter(owner=user).filter(
            Q(status='queued') | Q(status='running', lease_until__lte=now)).order_by('created_at')[:20]
        for row in rows:
            if (user.status != 'active' or user.is_staff or user.is_superuser or user.auth_epoch != row.auth_epoch
                    or user.access_revision != row.access_revision or row.attempts >= 3 or row.deadline <= now):
                row.status, row.error_code = 'failed', 'EXPORT_FAILED'
                row.lease_token = row.lease_until = None
                row.save(update_fields=['status', 'error_code', 'lease_token', 'lease_until', 'updated_at'])
                continue
            row.status, row.lease_token, row.lease_until = 'running', uuid4(), min(now + timedelta(seconds=60), row.deadline)
            row.attempts += 1
            row.save(update_fields=['status', 'lease_token', 'lease_until', 'attempts', 'updated_at'])
            return ExportLease(user.pk, row.pk, row.lease_token, row.attempts)
    return None


def execute(lease):
    """lease为当前尝试；先生成私有文件，发布前再次比较权限/记录，失败删除该尝试文件。"""
    path, published = None, False
    last_pulse = time.monotonic()
    def pulse():
        """无参数；长导出每10秒在独立短事务检查并续租，失败停止生成。"""
        nonlocal last_pulse
        if time.monotonic() - last_pulse >= 10:
            if not heartbeat(lease):
                raise ProblemError('EXPORT_STALE', '导出任务已失效，请重新生成', 409)
            last_pulse = time.monotonic()
    try:
        with owner_transaction(lease.owner_id):
            locked = _locked(lease)
            if locked is None:
                return False
            user, row = locked
        payload, binding = build_payload(user, row, pulse)
        encoded = json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, separators=(',', ':')).encode()
        if len(encoded) > MAX_BYTES:
            raise ProblemError('EXPORT_TOO_LARGE', '导出超过大小上限，请选择较小范围或联系支持', 413)
        key = f'{lease.export_id}-{lease.token}.json'
        path = file_path(lease.owner_id, key, create=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        with owner_transaction(lease.owner_id):
            locked = _locked(lease)
            if locked is None:
                return False
            user, row = locked
            if snapshot(user, row.scope) != binding:
                raise ProblemError('EXPORT_STALE', '记录或许可已变化，请重新导出', 409)
            row.status, row.file_key, row.binding = 'ready', key, binding
            row.content_hash = hashlib.sha256(encoded).hexdigest()
            row.expires_at = timezone.now() + timedelta(hours=24)
            row.lease_token = row.lease_until = None
            row.save(update_fields=['status', 'file_key', 'binding', 'content_hash', 'expires_at', 'lease_token', 'lease_until', 'updated_at'])
            published = True
        return True
    except (ProblemError, OSError, ValueError, KeyError, TypeError) as error:
        with owner_transaction(lease.owner_id):
            locked = _locked(lease)
            if locked:
                _, row = locked
                row.status, row.error_code = 'failed', error.code if isinstance(error, ProblemError) else 'EXPORT_FAILED'
                row.lease_token = row.lease_until = None
                row.save(update_fields=['status', 'error_code', 'lease_token', 'lease_until', 'updated_at'])
        return False
    finally:
        if path is not None and not published:
            path.unlink(missing_ok=True)


def process_one(owner_id):
    """owner_id为可信调度器遍历账号；无任务返回False，不调用模型或记账。"""
    lease = claim(owner_id)
    if lease is None:
        return False
    execute(lease)
    return True


def download(user, identifier):
    """user/identifier为本人当前请求；受控读取有界文件，发送前再核对真实授权和删除状态。"""
    with owner_transaction(user.pk):
        current = _current_user(user)
        row = PersonalExport.objects.filter(owner=current, pk=_uuid(identifier, not_found)).first()
        if row is None:
            raise not_found()
        if row.status == 'expired' or (row.expires_at is not None and row.expires_at <= timezone.now()):
            raise ProblemError('EXPORT_EXPIRED', '导出已过期，请重新生成', 410)
        if row.status != 'ready':
            raise ProblemError('EXPORT_NOT_READY', '导出尚未完成', 409)
        if snapshot(current, row.scope) != row.binding:
            raise ProblemError('EXPORT_STALE', '记录或许可已变化，请重新导出', 409)
    try:
        descriptor = os.open(file_path(user.pk, row.file_key), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as stream:
            content = stream.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES or hashlib.sha256(content).hexdigest() != row.content_hash:
            raise ValueError('导出文件不完整')
    except (OSError, ValueError):
        raise ProblemError('EXPORT_UNAVAILABLE', '导出暂不可用，请重新生成', 503) from None
    with owner_transaction(user.pk):
        current = _current_user(user)
        if (not PersonalExport.objects.filter(owner=current, pk=row.pk, status='ready',
                expires_at__gt=timezone.now(), content_hash=row.content_hash).exists()
                or snapshot(current, row.scope) != row.binding):
            raise ProblemError('EXPORT_STALE', '记录或许可已变化，请重新导出', 409)
    return content
