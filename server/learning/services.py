"""独立学习事务：固定卡输入、真实授权、幂等原消息与共享任务额度。"""
import copy
import hashlib
import json
from datetime import timedelta
from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Max, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from access.context import owner_transaction
from access.services import KnowledgeError
from knowledge.repository import KnowledgeRepository
from knowledge.projections import card_summary, book_payload
from problems.models import IdempotencyRecord
from problems.services import ProblemError, _current_user, _get as get_problem, _uuid, invalid, not_found
from runs.models import AnalysisRun, Job
from runs.services import _authorization, _accepted, _conflict, _iso, _error
from .models import LearningSession, LearningTurn
from .serializers import CreateLearningSerializer, SendLearningMessageSerializer, ArchiveLearningSerializer


def _validate(data, serializer, key=None):
    """data为未信任字典，serializer为输入规则，key存在时验证幂等头。"""
    if key is not None and (not isinstance(key, str) or not key.strip() or len(key) > 128):
        raise invalid()
    value = serializer(data=json.loads(json.dumps(data, cls=DjangoJSONEncoder)))
    try:
        value.is_valid(raise_exception=True)
    except ValidationError:
        raise invalid() from None
    result = json.loads(json.dumps(value.validated_data, cls=DjangoJSONEncoder))
    if any(name in result and not result[name].strip() for name in ('goal', 'content')):
        raise invalid()
    return result


def _digest(data):
    """data为规范输入；稳定散列仅用于请求去重。"""
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def basis(user, release_id, identifiers):
    """user/release/identifiers为已授权选择；一次读取返回公开摘要和不含原文证据的固定卡。"""
    def project(library, snapshot):
        """library/snapshot为同次已校验版本；完整保留所选卡的解释字段。"""
        if any(identifier not in library.cards for identifier in identifiers):
            raise not_found()
        books = {book['id']: book for book in library.manifest['books']}
        cards = [library.cards[identifier] for identifier in identifiers]
        return {'summaries': [card_summary(card, books[card['book_id']], release_id) for card in cards],
                'cards': [{'book': book_payload(books[card['book_id']]), **{key: copy.deepcopy(card[key]) for key in ('id', 'book_id', 'title', 'statement',
                    'reasoning', 'conditions', 'boundaries', 'steps', 'application_notes', 'source_claim_type')
                    if key in card}} for card in cards]}
    try:
        return KnowledgeRepository(user)._read(release_id, project)
    except KnowledgeError:
        raise not_found() from None


def _get(user, identifier, lock=False):
    """user为当前身份，identifier为会话UUID，lock用于串行修改。"""
    query = LearningSession.objects.select_for_update(of=('self',)) if lock else LearningSession.objects
    session = query.filter(Q(problem=None) | Q(problem__status__in=['active', 'archived']),
        owner=user, pk=_uuid(identifier, not_found)).first()
    if session is None:
        raise not_found()
    _authorization(user, session.release_id)
    return session


def session_public(session):
    """session为已核对owner和当前授权的行，只投影公开字段。"""
    return {'id': str(session.pk), 'release_id': str(session.release_id),
        'problem_id': str(session.problem_id) if session.problem_id else None,
        'title': session.title, 'goal': session.goal, 'basis_card_ids': session.basis_card_ids,
        'revision': session.revision, 'status': session.status,
        'created_at': _iso(session.created_at), 'updated_at': _iso(session.updated_at)}


def turn_public(turn):
    """turn为本人会话记录，返回实际正文和回答引用。"""
    return {'id': str(turn.pk), 'learning_session_id': str(turn.learning_session_id),
        'sequence': turn.sequence, 'kind': turn.kind, 'content': copy.deepcopy(turn.content),
        'run_id': str(turn.run_id) if turn.run_id else None,
        'responds_to_turn_id': str(turn.responds_to_turn_id) if turn.responds_to_turn_id else None,
        'created_at': _iso(turn.created_at)}


def job_public(run):
    """run为已归属学习会话的任务，公开状态从job读取。"""
    job = run.job
    return {'id': str(job.pk), 'learning_session_id': str(run.learning_session_id),
        'run_id': str(run.pk), 'status': job.status, 'stage': job.stage, 'error_code': _error(job),
        'started_at': _iso(job.started_at), 'finished_at': _iso(job.finished_at)}


def _record(user, route, key, digest, resource, result, status):
    """参数均为已验证本次事务；保存原始公开响应以保证重复请求相同。"""
    IdempotencyRecord.objects.create(owner=user, method='POST', route_scope=route, key=key,
        request_hash=digest, status='completed', response_status=status, response_payload=result,
        resource_type='learning' if status == 201 else 'run', resource_id=resource.pk,
        expires_at=timezone.now() + timedelta(hours=48))
    return result


def create_session(user, data, key):
    """user为可信会话；data选择卡和学习目标，创建不会调用模型或新建问题。"""
    data = _validate(data, CreateLearningSerializer, key or '')
    identifiers = data['basis_card_ids']
    if len(set(identifiers)) != len(identifiers):
        raise invalid()
    loaded = basis(user, data['release_id'], identifiers)
    digest, route = _digest(data), '/api/v1/learning'
    with owner_transaction(user.pk):
        current = _current_user(user, lock=True)
        _authorization(current, data['release_id'])
        record = IdempotencyRecord.objects.filter(owner=current, route_scope=route, method='POST', key=key).first()
        if record:
            if record.request_hash != digest or record.response_status != 201 or record.resource_type != 'learning':
                raise _conflict()
            _get(current, record.resource_id)
            return record.response_payload
        problem = get_problem(current, _uuid(data['problem_id'], invalid)) if data.get('problem_id') else None
        if problem and str(problem.release_id) != data['release_id']:
            raise invalid()
        session = LearningSession.objects.create(owner=current, release_id=data['release_id'], problem=problem,
            title=' '.join(data['goal'].split())[:160], goal=data['goal'], basis_card_ids=identifiers,
            fixed_input={'goal': data['goal'], 'cards': loaded['cards']})
        return _record(current, route, key, digest, session, session_public(session), 201)


def _revision(session, expected):
    """session为持锁记录，expected为客户端已读修订。"""
    if session.revision != expected:
        raise ProblemError('REVISION_CONFLICT', '学习记录已更新，请刷新后重试', 409, session.revision)


def send_message(user, identifier, data, key):
    """显式消息才排队；respond必须引用同会话已发布练习并保存非空原回答。"""
    data = _validate(data, SendLearningMessageSerializer, key or '')
    identifier = _uuid(identifier, not_found)
    if (data['mode'] == 'respond') != bool(data.get('responds_to_turn_id')):
        raise invalid()
    route, digest = f'/api/v1/learning/{identifier}/messages', _digest(data)
    with owner_transaction(user.pk):
        current = _current_user(user, lock=True)
        session = _get(current, identifier, lock=True)
        authorization = _authorization(current, session.release_id)
        record = IdempotencyRecord.objects.filter(owner=current, method='POST', route_scope=route, key=key).first()
        if record:
            if record.request_hash != digest or record.response_status != 202 or record.resource_type != 'run':
                raise _conflict()
            run = AnalysisRun.objects.filter(owner=current, learning_session=session, pk=record.resource_id).first()
            if run is None:
                raise not_found()
            return _accepted(run)
        previous = LearningTurn.objects.filter(owner=current, learning_session=session,
                                               client_message_id=data['client_message_id']).first()
        if previous:
            if previous.run_id is None or previous.run.internal_request != data:
                raise _conflict()
            return _record(current, route, key, digest, previous.run, _accepted(previous.run), 202)
        if session.status != 'active':
            raise ProblemError('LEARNING_ARCHIVED', '学习会话已归档', 409)
        _revision(session, data['expected_revision'])
        if AnalysisRun.objects.filter(owner=current, learning_session=session,
                job__status__in=['queued', 'running', 'cancel_requested']).exists():
            raise ProblemError('LEARNING_BUSY', '请等待当前学习任务完成', 409)
        exercise = None
        if data['mode'] == 'respond':
            exercise = LearningTurn.objects.filter(owner=current, learning_session=session,
                pk=data['responds_to_turn_id'], kind='exercise', run__job__status='succeeded').first()
            if exercise is None:
                raise invalid()
        sequence = (LearningTurn.objects.filter(owner=current, learning_session=session)
                    .aggregate(last=Max('sequence'))['last'] or 0) + 1
        turn = LearningTurn.objects.create(owner=current, learning_session=session, sequence=sequence,
            kind='user_response' if exercise else 'user_request', content={'text': data['content'], 'sections': []},
            client_message_id=data['client_message_id'], responds_to_turn=exercise)
        job = Job.objects.create(owner=current, kind='learning', deadline=timezone.now() + timedelta(seconds=180))
        session.revision += 1
        state = {'fixed_input': copy.deepcopy(session.fixed_input), 'input_turn': turn_public(turn),
                 'exercise': turn_public(exercise) if exercise else None,
                 'history': [turn_public(row) for row in LearningTurn.objects.filter(owner=current,
                    learning_session=session, sequence__lte=sequence).order_by('sequence')]}
        run = AnalysisRun.objects.create(owner=current, learning_session=session, release=session.release,
            job=job, kind='learning', input_revision=session.revision, auth_epoch=current.auth_epoch,
            access_revision=current.access_revision, authorization_snapshot=json.loads(json.dumps(authorization,
            cls=DjangoJSONEncoder)), internal_state=state, internal_request=data)
        from operations.usage import reserve_run, QuotaExceeded
        try:
            reserve_run(current, run)
        except QuotaExceeded:
            raise ProblemError('QUOTA_EXCEEDED', '本月运行额度已用完，请联系管理员调整额度', 429) from None
        turn.run = run
        turn.save(update_fields=['run', 'updated_at'])
        session.save(update_fields=['revision', 'updated_at'])
        return _record(current, route, key, digest, run, _accepted(run), 202)


def _page(rows, query, binding, field):
    """rows为owner过滤查询，query为页参数，binding为身份范围，field为稳定唯一排序键。"""
    if not isinstance(query, dict) or not set(query) <= {'limit', 'cursor', 'status'}:
        raise invalid()
    limit = query.get('limit', 20)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise invalid()
    binding = {**binding, 'limit': limit}
    cursor = query.get('cursor')
    if cursor:
        try:
            payload = signing.loads(cursor, salt='learning.page.v1', max_age=900)
            if payload['binding'] != binding:
                raise ValueError('binding')
            rows = rows.filter(**{field + '__gt': payload['after']})
        except (signing.BadSignature, KeyError, TypeError, ValueError):
            raise invalid() from None
    selected = list(rows.order_by(field)[:limit + 1])
    next_cursor = signing.dumps({'binding': binding, 'after': str(getattr(selected[limit - 1], field))},
        salt='learning.page.v1') if len(selected) > limit else None
    return selected[:limit], next_cursor


def list_sessions(user, query):
    """user为可信身份；游标绑定owner/epoch/状态，失去授权的会话不投影。"""
    with owner_transaction(user.pk):
        current = _current_user(user)
        rows = LearningSession.objects.filter(Q(problem=None) | Q(problem__status__in=['active', 'archived']), owner=current)
        if 'status' in query:
            if query['status'] not in ('active', 'archived'):
                raise invalid()
            rows = rows.filter(status=query['status'])
        selected, cursor = _page(rows, query, {'owner': str(current.pk), 'epoch': current.auth_epoch,
            'status': query.get('status'), 'scope': 'sessions'}, 'id')
        items = []
        for session in selected:
            try:
                _authorization(current, session.release_id)
            except ProblemError:
                continue
            items.append(session_public(session))
        return {'items': items, 'next_cursor': cursor}


def get_detail(user, identifier, query):
    """先核对本人会话，再单次读取来源卡，返回前重核授权和当前任务。"""
    with owner_transaction(user.pk):
        session = _get(_current_user(user), identifier)
        release_id, identifiers = session.release_id, session.basis_card_ids
    loaded = basis(user, release_id, identifiers)
    with owner_transaction(user.pk):
        current = _current_user(user)
        session = _get(current, identifier)
        selected, cursor = _page(LearningTurn.objects.filter(owner=current, learning_session=session), query,
            {'owner': str(current.pk), 'epoch': current.auth_epoch, 'session': str(session.pk)}, 'sequence')
        active = AnalysisRun.objects.filter(owner=current, learning_session=session,
            job__status__in=['queued', 'running', 'cancel_requested']).select_related('job').order_by('-created_at').first()
        return {'session': session_public(session), 'items': [turn_public(turn) for turn in selected],
            'next_cursor': cursor, 'library_available': True, 'basis_cards': loaded['summaries'],
            'active_job': job_public(active) if active else None}


def archive_session(user, identifier, data):
    """user为可信身份；归档增加修订，使未完成任务在边界复查时失效。"""
    data = _validate(data, ArchiveLearningSerializer)
    with owner_transaction(user.pk):
        current = _current_user(user, lock=True)
        session = _get(current, identifier, lock=True)
        _revision(session, data['expected_revision'])
        session.status, session.revision = 'archived', session.revision + 1
        session.save(update_fields=['status', 'revision', 'updated_at'])
        return session_public(session)


def get_job(user, identifier, job_id, cancel=False):
    """学习专用路由始终绑定当前owner和父会话；cancel只作用于该会话任务。"""
    with owner_transaction(user.pk):
        current = _current_user(user, lock=cancel)
        session = _get(current, identifier, lock=cancel)
        run = AnalysisRun.objects.filter(owner=current, learning_session=session,
            job_id=_uuid(job_id, not_found)).select_related('job').first()
        if run is None:
            raise not_found()
        if cancel:
            job = Job.objects.select_for_update().get(owner=current, pk=run.job_id)
            if job.status == 'queued':
                from runs.queue import _terminal
                _terminal(job, run, 'RUN_CANCELLED', timezone.now())
            elif job.status == 'running':
                job.status = 'cancel_requested'
                job.save(update_fields=['status', 'updated_at'])
            run.job = job
        result = job_public(run)
        return (result, 202 if run.job.status == 'cancel_requested' else 200) if cancel else result
