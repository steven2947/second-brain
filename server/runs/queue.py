"""本人短事务租约与澄清发布；模型执行必须在事务外，旧令牌不可改写新尝试。"""
import copy
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Max, Q
from django.utils import timezone

from accounts.models import User
from access.context import owner_transaction
from access.services import KnowledgeError, analysis_snapshot
from problems.models import Message, Problem
from problems.services import invalid
from src.orchestration.intake import append_event, problem_snapshot
from .models import AnalysisRun, Job, JobEvent
from .services import PUBLIC_ERRORS, get_job

STAGES = frozenset(('understanding', 'retrieving', 'evaluating', 'validating', 'composing'))


@dataclass(frozen=True)
class Lease:
    """仅传给可信worker的固定输入；deadline是整体截止时间，不随续租延长。"""
    owner_id: UUID
    job_id: UUID
    run_id: UUID
    token: UUID
    attempt: int
    deadline: datetime
    input_revision: int
    state: dict
    messages: list
    last_sequence: int
    kind: str = 'run'


def _event(job, run, event_type):
    """job必须已持锁，run已核对归属；仅写固定字段，序号在同锁下递增。"""
    seq = (JobEvent.objects.filter(owner_id=job.owner_id, job=job)
           .aggregate(last=Max('seq'))['last'] or 0) + 1
    JobEvent.objects.create(owner_id=job.owner_id, job=job, seq=seq,
        event_type=event_type, public_payload={'job_id': str(job.pk),
        'run_id': str(run.pk), 'stage': job.stage})


def _terminal(job, run, code, now):
    """job/run为已持锁本次任务；code只允许固定错误，now为当前事务时间。"""
    job.status = 'cancelled' if code == 'RUN_CANCELLED' else 'failed'
    job.error_code, job.finished_at = code, now
    job.lease_token = job.lease_until = None
    job.save(update_fields=['status', 'error_code', 'finished_at', 'lease_token', 'lease_until', 'updated_at'])
    if code == 'RUN_STALE':
        run.stale_at = now
        run.save(update_fields=['stale_at', 'updated_at'])
    from operations.usage import finalize_run
    finalize_run(run)
    _event(job, run, job.status)


def _boundary(user, problem, job, run, now):
    """所有参数为当前持锁记录；复查原修订、账户和实际授权字段而非缓存许可。"""
    if job.status == 'cancel_requested':
        return 'RUN_CANCELLED'
    if job.deadline is None or job.deadline <= now:
        return 'RUN_TIMEOUT'
    if (user.status != 'active' or user.is_staff or user.is_superuser
            or user.auth_epoch != run.auth_epoch or user.access_revision != run.access_revision):
        return 'ACCESS_REVOKED'
    if (problem.status != 'active' or problem.revision != run.input_revision):
        return 'RUN_STALE'
    if run.kind == 'learning':
        from learning.generation import fixed_messages
        if problem.problem_id and not Problem.objects.filter(owner=user,
                pk=problem.problem_id, status__in=['active', 'archived']).exists():
            return 'RUN_STALE'
        if job.kind != 'learning' or not fixed_messages(problem, run):
            return 'RUN_STALE'
    elif job.kind != 'run' or problem.core_state != run.internal_state:
        return 'RUN_STALE'
    try:
        current = json.loads(json.dumps(analysis_snapshot(user, run.release_id), cls=DjangoJSONEncoder))
    except KnowledgeError:
        return 'ACCESS_REVOKED'
    if current != run.authorization_snapshot:
        return 'ACCESS_REVOKED'
    return None


def _messages(user, problem, run):
    """user/problem/run已归属；收集尚未成功入core的全部可见原消息直到固定输入。"""
    if run.kind == 'learning':
        from learning.generation import fixed_messages
        return fixed_messages(problem, run)
    target = Message.objects.filter(owner=user, problem=problem, pk=run.input_message_id,
                                    role='user', visibility='visible').first()
    if target is None:
        return []
    return list(Message.objects.filter(owner=user, problem=problem, role='user',
        visibility='visible', sequence__gt=problem.processed_message_sequence,
        sequence__lte=target.sequence).order_by('sequence').values('content', 'intent', 'sequence'))


def claim(owner_id):
    """owner_id为调度器提供的可信账号；最多检查20个候选，原截止点保持不变。"""
    with owner_transaction(owner_id):
        user = User.objects.select_for_update().filter(pk=owner_id).first()
        if user is None:
            return None
        now = timezone.now()
        eligible = Q(status='queued') | (Q(status__in=['running', 'cancel_requested'])
                    & (Q(lease_until__lte=now) | Q(lease_until=None)))
        candidates = list(Job.objects.filter(eligible, owner=user).order_by('created_at', 'id')
                          .values_list('pk', flat=True)[:20])
        for identifier in candidates:
            run = AnalysisRun.objects.filter(owner=user, job_id=identifier).first()
            if run is None:
                continue
            problem = _parent(user, run)
            job = Job.objects.select_for_update(skip_locked=True).filter(eligible, owner=user, pk=identifier).first()
            if job is None:
                continue
            code = _boundary(user, problem, job, run, now)
            if code is None and job.attempt >= job.max_attempts:
                code = 'RUN_FAILED'
            messages = _messages(user, problem, run) if code is None else []
            if code is None and not messages:
                code = 'RUN_FAILED'
            if code:
                _terminal(job, run, code, now)
                continue
            job.status, job.stage = 'running', 'understanding'
            job.attempt += 1
            job.lease_token = uuid4()
            job.lease_until = min(now + timedelta(seconds=30), job.deadline)
            job.heartbeat_at = now
            job.started_at = job.started_at or now
            job.error_code = None
            job.save(update_fields=['status', 'stage', 'attempt', 'lease_token', 'lease_until',
                                    'heartbeat_at', 'started_at', 'error_code', 'updated_at'])
            _event(job, run, 'stage')
            return Lease(user.pk, job.pk, run.pk, job.lease_token, job.attempt, job.deadline,
                         run.input_revision, copy.deepcopy(run.internal_state), messages, messages[-1]['sequence'], job.kind)
    return None


def _parent(user, run):
    """user/run为当前owner与任务；按父域选择持锁记录，不伪造Problem。"""
    if run.kind == 'learning':
        from learning.models import LearningSession
        return LearningSession.objects.select_for_update().get(owner=user, pk=run.learning_session_id)
    return Problem.objects.select_for_update().get(owner=user, pk=run.problem_id)


def _locked(lease):
    """lease为可信worker输入；调用者须已开启owner事务，锁序总为账号、问题、任务。"""
    user = User.objects.select_for_update().filter(pk=lease.owner_id).first()
    if user is None:
        return None
    run = AnalysisRun.objects.filter(owner=user, pk=lease.run_id, job_id=lease.job_id).first()
    if run is None:
        return None
    problem = _parent(user, run)
    job = Job.objects.select_for_update().get(owner=user, pk=lease.job_id)
    if (job.lease_token != lease.token or job.attempt != lease.attempt
            or job.status not in ('running', 'cancel_requested')):
        return None
    now = timezone.now()
    code = _boundary(user, problem, job, run, now)
    if code:
        _terminal(job, run, code, now)
        return None
    if job.lease_until is None or job.lease_until <= now:
        return None
    return user, problem, job, run, now


def heartbeat(lease, stage=None):
    """lease为当前尝试，stage仅在实际进入该阶段时提供；失效或被收回返回False。"""
    if stage is not None and stage not in STAGES:
        raise ValueError('无效运行阶段')
    with owner_transaction(lease.owner_id):
        locked = _locked(lease)
        if locked is None:
            return False
        _, _, job, run, now = locked
        changed = stage is not None and stage != job.stage
        if stage is not None:
            job.stage = stage
        job.heartbeat_at, job.lease_until = now, min(now + timedelta(seconds=30), job.deadline)
        job.save(update_fields=['stage', 'heartbeat_at', 'lease_until', 'updated_at'])
        if changed:
            _event(job, run, 'stage')
        return True


def finish_failure(lease, code):
    """lease必须仍为当前活租约；code仅固定公开错误，不接受异常原文。"""
    if not isinstance(code, str) or code not in PUBLIC_ERRORS:
        code = 'RUN_FAILED'
    with owner_transaction(lease.owner_id):
        locked = _locked(lease)
        if locked is None:
            return False
        _, _, job, run, now = locked
        _terminal(job, run, code, now)
        return True


def _question_state(lease, result, problem, run, messages):
    """result为未信任私有提案；从固定原state逐事件重放并核验每条原消息及唯一追问。"""
    if (not isinstance(result, dict) or set(result) != {'state', 'events', 'outcome', 'question', 'request'}
            or result['outcome'] != 'question' or result['request'] is not None
            or not isinstance(result['question'], str) or not result['question'].strip()
            or lease.state != run.internal_state or lease.input_revision != run.input_revision
            or lease.messages != messages or not messages
            or lease.last_sequence != messages[-1]['sequence']):
        raise ValueError('无效提案')
    events = result['events']
    if not isinstance(events, list) or len(events) != len(messages) + 1:
        raise ValueError('缺失原消息')
    state = copy.deepcopy(run.internal_state)
    for message, event in zip(messages, events[:-1]):
        if (not isinstance(event, dict) or event.get('type') != 'user_update'
                or event.get('source_message') != message['content'] or event.get('intent') != message['intent']):
            raise ValueError('原消息不一致')
        state = append_event(state, event, len(state['events']))
    if not isinstance(events[-1], dict) or events[-1].get('type') != 'ask':
        raise ValueError('缺失追问')
    state = append_event(state, events[-1], len(state['events']))
    snapshot = problem_snapshot(state)
    if (state != result['state'] or snapshot['pending_question'] != result['question']
            or snapshot['question'] != problem.original_question or snapshot['goal'] != problem.goal
            or snapshot['problem_id'] != problem.core_problem_id):
        raise ValueError('状态绑定失败')
    return state


def publish_question(lease, result):
    """lease/result为worker计算结果；同事务发布已重放状态、消费游标、助手消息与成功事件。"""
    with owner_transaction(lease.owner_id):
        locked = _locked(lease)
        if locked is None:
            return False
        user, problem, job, run, now = locked
        try:
            state = _question_state(lease, result, problem, run, _messages(user, problem, run))
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            _terminal(job, run, 'MODEL_OUTPUT_INVALID', now)
            return False
        sequence = (Message.objects.filter(owner=user, problem=problem).aggregate(last=Max('sequence'))['last'] or 0) + 1
        if sequence > 9223372036854775807 or problem.revision >= 9223372036854775807:
            _terminal(job, run, 'RUN_FAILED', now)
            return False
        problem.core_state, problem.processed_message_sequence = state, lease.last_sequence
        problem.revision += 1
        problem.save(update_fields=['core_state', 'processed_message_sequence', 'revision', 'updated_at'])
        Message.objects.create(owner=user, problem=problem, sequence=sequence, role='assistant',
            kind='clarification', content=result['question'], run=run, published_at=now)
        run.outcome = 'question'
        run.save(update_fields=['outcome', 'updated_at'])
        job.status, job.finished_at = 'succeeded', now
        job.lease_token = job.lease_until = None
        job.save(update_fields=['status', 'finished_at', 'lease_token', 'lease_until', 'updated_at'])
        from operations.usage import finalize_run
        finalize_run(run)
        _event(job, run, 'question_ready')
        return True


def list_events(user, job_id, after=0, limit=100):
    """user为真实会话；先使用实际job授权服务，再按序读取有界公开事件。"""
    if type(after) is not int or not 0 <= after <= 9223372036854775807 or type(limit) is not int or not 1 <= limit <= 100:
        raise invalid()
    with owner_transaction(user.pk):
        job = get_job(user, job_id)
        rows = JobEvent.objects.filter(owner=user, job_id=job['id'], seq__gt=after).order_by('seq')[:limit]
        return [{'seq': row.seq, 'event_type': row.event_type,
                 'public_payload': {key: row.public_payload[key] for key in ('job_id', 'run_id', 'stage')}}
                for row in rows]
