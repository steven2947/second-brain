"""问题草稿公开服务；短事务内检查身份、owner隔离和当前版本授权。"""
import hashlib
import json
from datetime import timedelta
from uuid import UUID

from django.core import signing
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import User
from accounts.services import AccountError
from access.context import owner_transaction
from access.services import KnowledgeError, access_snapshot
from src.orchestration.intake import create_problem, problem_snapshot
from .models import IdempotencyRecord, Problem

GOALS = ('explain', 'analyze', 'compare', 'act', 'review')
PUBLIC_FIELDS = ('id', 'title', 'original_question', 'goal', 'release_id', 'revision',
                 'status', 'clarification', 'current_answer_id', 'library_available',
                 'created_at', 'updated_at')
CURSOR_SALT = 'problems.list.v1'


class ProblemError(AccountError):
    """固定公开错误；冲突可携带本人当前revision，不泄漏底层异常。"""

    def __init__(self, code, message, status, current_revision=None):
        """code/message/status为公开错误；current_revision仅用于已归属本人的编辑冲突。"""
        super().__init__(code, message, status)
        self.current_revision = current_revision


def invalid():
    """无参数；返回固定输入错误，不回显请求原文。"""
    return ProblemError('INVALID_INPUT', '请求参数无效', 400)


def not_found():
    """无参数；资源不存在与无权访问统一为404。"""
    return ProblemError('NOT_FOUND', '资源不存在', 404)


def unavailable():
    """无参数；核心状态失效时只提供固定503。"""
    return ProblemError('PROBLEM_UNAVAILABLE', '问题暂不可用', 503)


def _uuid(value, error):
    """value为请求UUID文本或已验证UUID；error为该入口固定错误工厂。"""
    if not isinstance(value, (str, UUID)):
        raise error()
    try:
        return UUID(str(value))
    except (ValueError, AttributeError):
        raise error() from None


def _current_user(user, *, lock=False):
    """user为可信会话用户；lock在创建时串行同owner的短幂等事务。"""
    query = User.objects.select_for_update() if lock else User.objects
    current = query.filter(pk=user.pk, status='active', is_staff=False,
                           is_superuser=False, auth_epoch=user.auth_epoch).first()
    if current is None:
        raise not_found()
    return current


def _snapshot(problem):
    """problem为已核对owner的行；验证完整核心状态及原问题、goal、核心ID绑定。"""
    try:
        snapshot = problem_snapshot(problem.core_state)
        if (snapshot['question'] != problem.original_question or snapshot['goal'] != problem.goal
                or snapshot['problem_id'] != problem.core_problem_id):
            raise ValueError('core binding')
        return snapshot
    except (ValueError, TypeError, KeyError, AttributeError):
        raise unavailable() from None


def _available(user, release_id):
    """user/release_id为已归属问题的用户与固定版本；即时授权失败只标记不可用。"""
    try:
        access_snapshot(user, release_id)
        return True
    except KnowledgeError:
        return False


def _public(problem, user):
    """problem为本人问题、user为可信当前用户；仅投影公开草稿和核心派生澄清摘要。"""
    snapshot = _snapshot(problem)
    available = _available(user, problem.release_id)
    return {'id': str(problem.pk), 'title': problem.title,
            'original_question': problem.original_question, 'goal': problem.goal,
            'release_id': str(problem.release_id), 'revision': problem.revision,
            'status': problem.status,
            'clarification': {'rounds': snapshot['clarification_rounds'],
                              'limit': snapshot['clarification_limit'],
                              'pending_question': snapshot['pending_question'] if available else None,
                              'closed': snapshot['intake_closed']},
            # 答案表将在后批实现；这里没有无外键约束的UUID占位列。
            'current_answer_id': None,
            'library_available': available,
            'created_at': problem.created_at.isoformat(), 'updated_at': problem.updated_at.isoformat()}


def _get(user, problem_id, *, lock=False):
    """user为当前用户、problem_id为已验证UUID；lock在编辑时锁定本人非删除行。"""
    query = Problem.objects.select_for_update() if lock else Problem.objects
    problem = query.filter(pk=problem_id, owner_id=user.pk, status__in=['active', 'archived']).first()
    if problem is None:
        raise not_found()
    return problem


def create_draft(user, data, key):
    """user为可信会话用户；data仅question/goal/release_id；key为创建幂等键。"""
    if (not isinstance(data, dict) or set(data) != {'question', 'goal', 'release_id'}
            or not isinstance(data['question'], str) or not 1 <= len(data['question']) <= 4000
            or not data['question'].strip() or not isinstance(data['goal'], str)
            or data['goal'] not in GOALS or not isinstance(key, str)
            or not 1 <= len(key) <= 128 or not key.strip()):
        raise invalid()
    release_id = _uuid(data['release_id'], invalid)
    canonical = dict(data, release_id=str(release_id))
    request_hash = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                                            separators=(',', ':')).encode()).hexdigest()
    with owner_transaction(user.pk):
        current = _current_user(user, lock=True)
        record = IdempotencyRecord.objects.filter(owner=current, method='POST',
                    route_scope='/api/v1/problems', key=key).first()
        if record is not None:
            if record.request_hash != request_hash:
                raise ProblemError('IDEMPOTENCY_CONFLICT', '幂等键已用于其他请求', 409)
            problem = _get(current, record.resource_id)
            _snapshot(problem)
            if not _available(current, problem.release_id):
                raise not_found()
            # 即使过期也不覆盖旧记录；调用者可使用新key重新创建。
            if record.status != 'completed' or record.response_status != 201:
                raise ProblemError('IDEMPOTENCY_CONFLICT', '请求尚未完成', 409)
            payload = record.response_payload
            try:
                result = {field: payload[field] for field in PUBLIC_FIELDS}
                result['clarification'] = {field: payload['clarification'][field]
                    for field in ('rounds', 'limit', 'pending_question', 'closed')}
                result['current_answer_id'], result['library_available'] = None, True
                return result
            except (KeyError, TypeError):
                raise unavailable() from None
        if not _available(current, release_id):
            raise not_found()
        state = create_problem(data['question'], data['goal'])
        problem = Problem.objects.create(owner=current, title=' '.join(data['question'].split())[:160],
            original_question=data['question'], goal=data['goal'], release_id=release_id,
            core_problem_id=state['problem_id'], core_state=state)
        result = _public(problem, current)
        IdempotencyRecord.objects.create(owner=current, method='POST', route_scope='/api/v1/problems',
            key=key, request_hash=request_hash, status='completed', response_status=201,
            response_payload=result, resource_type='problem', resource_id=problem.pk,
            expires_at=timezone.now() + timedelta(hours=48))
        return result


def get_draft(user, problem_id):
    """user为可信会话用户；problem_id为UUID，返回本人原问题而不要求重新获得知识授权。"""
    problem_id = _uuid(problem_id, not_found)
    with owner_transaction(user.pk):
        current = _current_user(user)
        return _public(_get(current, problem_id), current)


def update_draft(user, problem_id, data):
    """user为可信用户；problem_id为UUID；data只含title/status变更及expected_revision。"""
    if (not isinstance(data, dict) or not set(data) <= {'title', 'status', 'expected_revision'}
            or 'expected_revision' not in data or not set(data) & {'title', 'status'}
            or type(data['expected_revision']) is not int or data['expected_revision'] < 0
            or data['expected_revision'] > 9223372036854775807):
        raise invalid()
    if 'title' in data and (not isinstance(data['title'], str)
                           or not 1 <= len(data['title']) <= 160 or not data['title'].strip()):
        raise invalid()
    if 'status' in data and (not isinstance(data['status'], str) or data['status'] not in ('active', 'archived')):
        raise invalid()
    problem_id = _uuid(problem_id, not_found)
    with owner_transaction(user.pk):
        current = _current_user(user)
        problem = _get(current, problem_id, lock=True)
        _snapshot(problem)
        if problem.revision != data['expected_revision']:
            raise ProblemError('REVISION_CONFLICT', '问题已更新，请刷新后重试', 409,
                               current_revision=problem.revision)
        fields = [field for field in ('title', 'status') if field in data]
        for field in fields:
            setattr(problem, field, data[field])
        if problem.revision == 9223372036854775807:
            raise unavailable()
        problem.revision += 1
        problem.save(update_fields=[*fields, 'revision', 'updated_at'])
        return _public(problem, current)


def list_drafts(user, query):
    """user为可信用户；query为q/status/cursor/limit，游标绑定身份epoch和相同查询15分钟。"""
    if not isinstance(query, dict) or not set(query) <= {'q', 'status', 'cursor', 'limit'}:
        raise invalid()
    q, status, limit, cursor = (query.get('q', ''), query.get('status', 'active'),
                              query.get('limit', 20), query.get('cursor'))
    if (not isinstance(q, str) or len(q) > 500 or not isinstance(status, str)
            or status not in ('active', 'archived') or type(limit) is not int
            or not 1 <= limit <= 100 or (cursor is not None and (not isinstance(cursor, str)
                                                       or len(cursor) > 4096))):
        raise invalid()
    with owner_transaction(user.pk):
        current = _current_user(user)
        binding = {'owner': str(current.pk), 'epoch': current.auth_epoch, 'q': q,
                   'status': status, 'limit': limit}
        rows = Problem.objects.filter(owner=current, status=status)
        if q:
            rows = rows.filter(Q(title__icontains=q) | Q(original_question__icontains=q))
        if cursor:
            try:
                payload = signing.loads(cursor, salt=CURSOR_SALT, max_age=900)
                if not isinstance(payload, dict) or payload.get('binding') != binding:
                    raise ValueError('binding')
                after_id = _uuid(payload['id'], invalid)
                after_time = parse_datetime(payload['updated_at'])
                if after_time is None or timezone.is_naive(after_time):
                    raise ValueError('timestamp')
            except (signing.BadSignature, ValueError, KeyError, TypeError):
                raise invalid() from None
            rows = rows.filter(Q(updated_at__lt=after_time) | Q(updated_at=after_time, id__gt=after_id))
        selected = list(rows.order_by('-updated_at', 'id')[:limit + 1])
        next_cursor = None
        if len(selected) > limit:
            last = selected[limit - 1]
            next_cursor = signing.dumps({'binding': binding, 'id': str(last.pk),
                'updated_at': last.updated_at.isoformat()}, salt=CURSOR_SALT)
        return {'items': [_public(problem, current) for problem in selected[:limit]],
                'next_cursor': next_cursor}
