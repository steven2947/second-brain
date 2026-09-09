"""本人消息、异步分析入队及真实任务状态；不调用模型或隐式重试POST。"""
import copy
import hashlib
import json
from datetime import timedelta

from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Max
from django.utils import timezone

from access.context import owner_transaction
from access.services import KnowledgeError, analysis_snapshot
from problems.models import IdempotencyRecord, Message
from problems.services import (ProblemError, _current_user, _get, _snapshot, _uuid,
                               invalid, not_found, unavailable)
from .models import AnalysisRun, Job

INTENTS = ('answer', 'supplement', 'analyze_now', 'unknown')
CURSOR_SALT = 'messages.list.v1'
PUBLIC_ERRORS = frozenset(('MODEL_UNAVAILABLE', 'MODEL_OUTPUT_INVALID', 'RUN_TIMEOUT',
    'RUN_CANCELLED', 'RUN_STALE', 'ACCESS_REVOKED', 'RUN_FAILED', 'ANALYSIS_UNAVAILABLE'))
PUBLIC_OUTCOMES = frozenset(('question', 'answer', 'learning', 'coverage_gap', 'unavailable'))


def _authorization(user, release_id):
    """user/release_id为已核对owner的当前身份与版本；失败统一不存在。"""
    try:
        return analysis_snapshot(user, release_id)
    except KnowledgeError:
        raise not_found() from None


def _validate(data, key, kind):
    """data为未信任输入，key为幂等键，kind选择两种公开入口。"""
    fields = {'expected_revision'} if kind == 'analysis' else {
        'content', 'intent', 'client_message_id', 'expected_revision'}
    if (not isinstance(data, dict) or set(data) != fields or not isinstance(key, str)
            or not 1 <= len(key) <= 128 or not key.strip()
            or type(data['expected_revision']) is not int
            or not 0 <= data['expected_revision'] < 9223372036854775807):
        raise invalid()
    result = dict(data)
    if kind == 'turn':
        if (not isinstance(data['content'], str) or not 1 <= len(data['content']) <= 20000
                or not data['content'].strip() or not isinstance(data['intent'], str)
                or data['intent'] not in INTENTS):
            raise invalid()
        result['client_message_id'] = str(_uuid(data['client_message_id'], invalid))
    return result


def _conflict():
    """无参数；所有幂等内容冲突共享固定公开错误。"""
    return ProblemError('IDEMPOTENCY_CONFLICT', '幂等标识已用于其他请求', 409)


def _accepted(run):
    """run为已核对归属的持久任务；公开仅任务ID和被接受的输入修订。"""
    return {'run_id': str(run.pk), 'job_id': str(run.job_id), 'revision': run.input_revision}


def _record(user, route, key, digest, run):
    """user/route/key/digest/run为已验证本次请求；持久记录原始202响应。"""
    result = _accepted(run)
    IdempotencyRecord.objects.create(owner=user, method='POST', route_scope=route,
        key=key, request_hash=digest, status='completed', response_status=202,
        response_payload=result, resource_type='run', resource_id=run.pk,
        expires_at=timezone.now() + timedelta(hours=48))
    return result


def _enqueue(user, problem_id, data, key, kind):
    """user为可信会话；锁owner与problem后原子保存消息、快照、job和幂等记录。"""
    data = _validate(data, key, kind)
    problem_id = _uuid(problem_id, not_found)
    route = f'/api/v1/problems/{problem_id}/' + ('analyze' if kind == 'analysis' else 'messages')
    digest = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                           separators=(',', ':')).encode()).hexdigest()
    with owner_transaction(user.pk):
        current = _current_user(user, lock=True)
        problem = _get(current, problem_id, lock=True)
        authorization = _authorization(current, problem.release_id)
        record = IdempotencyRecord.objects.filter(owner=current, method='POST',
                                                  route_scope=route, key=key).first()
        if record is not None:
            if (record.request_hash != digest or record.status != 'completed'
                    or record.response_status != 202 or record.resource_type != 'run'):
                raise _conflict()
            run = AnalysisRun.objects.filter(pk=record.resource_id, owner=current,
                                              problem=problem, kind=kind).first()
            if run is None:
                raise unavailable()
            return _accepted(run)
        if kind == 'turn':
            previous = Message.objects.filter(owner=current, problem=problem,
                                  client_message_id=data['client_message_id']).first()
            if previous is not None:
                run = AnalysisRun.objects.filter(pk=previous.run_id, owner=current,
                                      problem=problem, input_message=previous, kind=kind).first()
                if (run is None or previous.role != 'user' or previous.content != data['content']
                        or previous.intent != data['intent']
                        or run.input_revision - 1 != data['expected_revision']):
                    raise _conflict()
                return _record(current, route, key, digest, run)
        if problem.status != 'active':
            raise ProblemError('PROBLEM_ARCHIVED', '请先恢复已归档的问题', 409)
        if problem.revision != data['expected_revision']:
            raise ProblemError('REVISION_CONFLICT', '问题已更新，请刷新后重试', 409,
                               current_revision=problem.revision)
        _snapshot(problem)
        sequence = (Message.objects.filter(owner=current, problem=problem)
                    .aggregate(last=Max('sequence'))['last'] or 0) + 1
        if sequence > 9223372036854775807:
            raise unavailable()
        message = Message.objects.create(owner=current, problem=problem, sequence=sequence,
            role='user', kind='user_text',
            content='请直接分析当前问题。' if kind == 'analysis' else data['content'],
            intent='analyze_now' if kind == 'analysis' else data['intent'],
            client_message_id=data.get('client_message_id'), published_at=timezone.now())
        job = Job.objects.create(owner=current, deadline=timezone.now() + timedelta(seconds=600))
        problem.revision += 1
        run = AnalysisRun.objects.create(owner=current, problem=problem, release_id=problem.release_id,
            job=job, input_revision=problem.revision, kind=kind,
            access_revision=current.access_revision, auth_epoch=current.auth_epoch,
            authorization_snapshot=json.loads(json.dumps(authorization, cls=DjangoJSONEncoder)),
            input_message=message, internal_state=copy.deepcopy(problem.core_state))
        from operations.usage import reserve_run, QuotaExceeded
        try:
            reserve_run(current, run)
        except QuotaExceeded:
            raise ProblemError('QUOTA_EXCEEDED', '本月运行额度已用完，请联系管理员调整额度', 429) from None
        message.run = run
        message.save(update_fields=['run', 'updated_at'])
        problem.save(update_fields=['revision', 'updated_at'])
        return _record(current, route, key, digest, run)


def send_message(user, problem_id, data, key):
    """user为可信会话；data严格包含content/intent/client_message_id/expected_revision。"""
    return _enqueue(user, problem_id, data, key, 'turn')


def start_analysis(user, problem_id, data, key):
    """user为可信会话；data仅含expected_revision，服务器保留直接分析按钮的原意图。"""
    return _enqueue(user, problem_id, data, key, 'analysis')


def _iso(value):
    """value为可空持久时间；公开使用ISO时间或null。"""
    return value.isoformat() if value is not None else None


def list_messages(user, problem_id, query):
    """user为可信会话；query仅cursor/limit，游标绑定本人epoch、问题与页大小15分钟。"""
    if not isinstance(query, dict) or not set(query) <= {'cursor', 'limit'}:
        raise invalid()
    limit, cursor = query.get('limit', 20), query.get('cursor')
    if (type(limit) is not int or not 1 <= limit <= 100 or
            (cursor is not None and (not isinstance(cursor, str) or len(cursor) > 4096))):
        raise invalid()
    problem_id = _uuid(problem_id, not_found)
    with owner_transaction(user.pk):
        current = _current_user(user)
        problem = _get(current, problem_id)
        try:
            _authorization(current, problem.release_id)
            available = True
        except ProblemError:
            available = False
        binding = {'owner': str(current.pk), 'epoch': current.auth_epoch,
                   'problem': str(problem.pk), 'limit': limit}
        rows = Message.objects.filter(owner=current, problem=problem, visibility='visible')
        if not available:
            rows = rows.filter(role='user')
        else:
            from django.db.models import Q
            rows = rows.filter(Q(role='user') | Q(role='assistant', published_at__isnull=False))
        after = 0
        ceiling = rows.aggregate(last=Max('sequence'))['last'] or 0
        if cursor:
            try:
                payload = signing.loads(cursor, salt=CURSOR_SALT, max_age=900)
                if (not isinstance(payload, dict) or payload.get('binding') != binding
                        or type(payload['after']) is not int or type(payload['ceiling']) is not int
                        or not 0 < payload['after'] <= payload['ceiling'] <= 9223372036854775807):
                    raise ValueError('binding')
                after, ceiling = payload['after'], payload['ceiling']
            except (signing.BadSignature, ValueError, TypeError, KeyError):
                raise invalid() from None
        selected = list(rows.filter(sequence__gt=after, sequence__lte=ceiling)
                        .order_by('sequence')[:limit + 1])
        next_cursor = None
        if len(selected) > limit:
            next_cursor = signing.dumps({'binding': binding, 'after': selected[limit - 1].sequence,
                                         'ceiling': ceiling}, salt=CURSOR_SALT)
        return {'items': [{'id': str(row.pk), 'problem_id': str(row.problem_id),
            'sequence': row.sequence, 'role': row.role, 'kind': row.kind, 'content': row.content,
            'client_message_id': str(row.client_message_id) if row.client_message_id else None,
            'run_id': str(row.run_id) if row.run_id else None,
            'published_at': _iso(row.published_at), 'created_at': _iso(row.created_at)}
            for row in selected[:limit]], 'next_cursor': next_cursor,
            'revision': problem.revision, 'library_available': available}


def _run(user, identifier, *, by_job=False):
    """user为当前身份；identifier选择run或job UUID，父问题与实时analyze许可逐次核验。"""
    lookup = {'job_id' if by_job else 'pk': identifier}
    run = AnalysisRun.objects.filter(owner=user, learning_session__isnull=True, **lookup).select_related('job').first()
    if run is None:
        raise not_found()
    problem = _get(user, run.problem_id)
    _authorization(user, problem.release_id)
    return run


def _error(job):
    """job为本人任务；仅白名单错误码可公开，未知内部错误不透传。"""
    return job.error_code if job.error_code in PUBLIC_ERRORS else None


def _job_public(run):
    """run含本人关联job；只返回已实际发布、同owner同problem的答案引用。"""
    job = run.job
    from answers.models import Answer
    answer_id = (Answer.objects.filter(owner_id=run.owner_id, problem_id=run.problem_id, run=run)
                 .values_list('id', flat=True).first()) if job.status == 'succeeded' and run.outcome == 'answer' else None
    return {'id': str(job.pk), 'status': job.status, 'stage': job.stage,
            'run_id': str(run.pk), 'problem_id': str(run.problem_id), 'result_ref': str(answer_id) if answer_id else None,
            'error_code': _error(job), 'started_at': _iso(job.started_at),
            'finished_at': _iso(job.finished_at)}


def get_job(user, job_id):
    """user为可信会话，job_id为UUID；只读本人非删除问题的已授权任务。"""
    job_id = _uuid(job_id, not_found)
    with owner_transaction(user.pk):
        current = _current_user(user)
        return _job_public(_run(current, job_id, by_job=True))


def get_run(user, run_id):
    """user为可信会话，run_id为UUID；不返回任何内部状态、提示词或授权快照。"""
    run_id = _uuid(run_id, not_found)
    with owner_transaction(user.pk):
        current = _current_user(user)
        run = _run(current, run_id)
        job = run.job
        return {'id': str(run.pk), 'problem_id': str(run.problem_id), 'job_id': str(job.pk),
            'status': job.status, 'stage': job.stage, 'input_revision': run.input_revision,
            'outcome': run.outcome if run.outcome in PUBLIC_OUTCOMES else None,
            'stale': run.stale_at is not None, 'error_code': _error(job),
            'started_at': _iso(job.started_at), 'finished_at': _iso(job.finished_at)}


def cancel_job(user, job_id):
    """user为可信会话，job_id为UUID；排队立即取消，执行中仅记录取消请求。"""
    job_id = _uuid(job_id, not_found)
    with owner_transaction(user.pk):
        current = _current_user(user, lock=True)
        run = _run(current, job_id, by_job=True)
        job = Job.objects.select_for_update().get(pk=run.job_id, owner=current)
        if job.status == 'queued':
            job.status, job.finished_at = 'cancelled', timezone.now()
            job.save(update_fields=['status', 'finished_at', 'updated_at'])
            from operations.usage import finalize_run
            finalize_run(run)
            from .queue import _event
            _event(job, run, 'cancelled')
        elif job.status == 'running':
            job.status = 'cancel_requested'
            job.save(update_fields=['status', 'updated_at'])
        run.job = job
        return _job_public(run), 202 if job.status == 'cancel_requested' else 200
