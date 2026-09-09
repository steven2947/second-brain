"""固定版本分析与原子发布；租约/账户/输入/授权任一失效均不覆盖问题。"""
import copy
import time
from django.db.models import Max
from access.context import owner_transaction
from ai.core_adapter import analyze_with_library, public_answer
from ai.ports import ModelFailure
from knowledge.release_loader import load_release, ReleaseUnavailable
from problems.models import Message
from runs.queue import _locked, _messages, _terminal, _event, heartbeat
from src.orchestration.intake import append_event, compile_request, problem_snapshot
from src.orchestration.validation import build_answer_packet
from .models import Answer
from .presentation import packet_hash, render_markdown


def _prepared_state(lease, intake):
    """lease固定所有原消息；intake必须完整重放每条原文，再以prepare结束，不能偷改原问题。"""
    if (not isinstance(intake, dict) or set(intake) != {'state', 'events', 'outcome', 'question', 'request'}
            or intake['outcome'] != 'ready' or intake['question'] is not None
            or not isinstance(intake['events'], list) or len(intake['events']) != len(lease.messages) + 1):
        raise ValueError('无效准备结果')
    state = copy.deepcopy(lease.state)
    for message, event in zip(lease.messages, intake['events'][:-1]):
        if (event.get('type') != 'user_update' or event.get('source_message') != message['content']
                or event.get('intent') != message['intent']):
            raise ValueError('原消息不一致')
        state = append_event(state, event, len(state['events']))
    if intake['events'][-1].get('type') != 'prepare':
        raise ValueError('缺少检索准备')
    state = append_event(state, intake['events'][-1], len(state['events']))
    if state != intake['state'] or compile_request(state) != intake['request']:
        raise ValueError('核心准备状态不一致')
    return state


def analyze_release(lease, intake, provider, *, timeout_seconds, cancelled):
    """lease来自当前worker；只从已检查授权快照加载固定release，所有模型执行在事务外。"""
    with owner_transaction(lease.owner_id):
        locked = _locked(lease)
        authorization = copy.deepcopy(locked[3].authorization_snapshot) if locked else None
    if authorization is None:
        raise ModelFailure('RUN_CANCELLED')
    started = time.monotonic()
    try:
        _prepared_state(lease, intake)
        release = authorization['release']
        library = load_release(release['storage_key'], release['source_fingerprint'], release['content_version'])
        if (set(authorization['books']) != {book['id'] for book in library.manifest['books']}
                or len(library.manifest['books']) != release['book_count']
                or len(library.cards) != release['card_count']):
            raise ReleaseUnavailable()
    except (ValueError, KeyError, TypeError, OSError, ReleaseUnavailable):
        raise ModelFailure('ANALYSIS_UNAVAILABLE') from None
    def stage(value):
        """value为实际执行阶段；每次转换都检查当前活租约与真实许可。"""
        if cancelled() or not heartbeat(lease, value):
            raise ModelFailure('RUN_CANCELLED')
    remaining = timeout_seconds - (time.monotonic() - started)
    if remaining <= 0:
        raise ModelFailure('RUN_TIMEOUT')
    analysis = analyze_with_library(library, intake['request'], provider,
        mode='deep' if intake['request']['goal'] in ('compare', 'review') else 'standard',
        timeout_seconds=remaining, cancelled=cancelled, stage=stage)
    return library, analysis


def publish_answer(lease, intake, analysis, library):
    """输入仅来自内部worker；先复核实际v3包，最后短事务再次校验并发布，禁止半写。"""
    try:
        state = _prepared_state(lease, intake)
        session = analysis['session']
        if session['request'] != intake['request'] or session['library_version'] != library.version:
            raise ValueError('分析输入不一致')
        gap = analysis['outcome'] == 'coverage_gap'
        if gap:
            # 空会话本身也须经固定会话hash及知识版本校验，不能只信任outcome标签。
            from src.orchestration.validation import _validate_session
            _validate_session(library, session)
            if session['candidates'] or analysis['packet'] is not None or analysis['draft'] is not None:
                raise ValueError('伪造知识缺口')
            packet = None
        else:
            packet = build_answer_packet(library, session, analysis['draft'], session['policy'])
            if analysis['outcome'] != 'answer' or packet != analysis['packet']:
                raise ValueError('正式包与验证结果不一致')
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        from runs.queue import finish_failure
        finish_failure(lease, 'MODEL_OUTPUT_INVALID')
        return False
    with owner_transaction(lease.owner_id):
        locked = _locked(lease)
        if locked is None:
            return False
        user, problem, job, run, now = locked
        snapshot = problem_snapshot(state)
        if (lease.messages != _messages(user, problem, run) or lease.state != run.internal_state
                or snapshot['question'] != problem.original_question or snapshot['goal'] != problem.goal
                or snapshot['problem_id'] != problem.core_problem_id
                or not lease.messages or lease.last_sequence != lease.messages[-1]['sequence']
                or session['library_version'] != run.authorization_snapshot['release']['content_version']):
            _terminal(job, run, 'RUN_STALE', now)
            return False
        sequence = (Message.objects.filter(owner=user, problem=problem).aggregate(last=Max('sequence'))['last'] or 0) + 1
        if sequence > 9223372036854775807 or problem.revision >= 9223372036854775807:
            _terminal(job, run, 'RUN_FAILED', now)
            return False
        if gap:
            content = '当前知识版本没有检索到与你的问题相关的材料，因此没有生成书库依据或正式答案。\n\n继续和 AI 聊：请帮我明确这个问题需要哪类知识，以及目前还缺哪些依据。'
        else:
            payload = public_answer(packet, quote_limits=run.authorization_snapshot['quotes'])
            content = render_markdown(payload)
            Answer.objects.create(owner=user, problem=problem, run=run, internal_packet=packet,
                public_payload=payload, rendered_markdown=content, content_hash=packet_hash(packet), published_at=now)
        Message.objects.create(owner=user, problem=problem, sequence=sequence, role='assistant',
            kind='notice' if gap else 'answer',
            content=content if gap else '分析已完成。请打开正式答案查看建议、书籍原理与依据。',
            run=run, published_at=now)
        problem.core_state, problem.processed_message_sequence = state, lease.last_sequence
        problem.revision += 1
        problem.save(update_fields=['core_state', 'processed_message_sequence', 'revision', 'updated_at'])
        run.internal_request, run.internal_session, run.internal_draft = intake['request'], session, analysis['draft']
        run.outcome = 'coverage_gap' if gap else 'answer'
        run.save(update_fields=['internal_request', 'internal_session', 'internal_draft', 'outcome', 'updated_at'])
        job.status, job.stage, job.finished_at = 'succeeded', 'composing', now
        job.lease_token = job.lease_until = None
        job.save(update_fields=['status', 'stage', 'finished_at', 'lease_token', 'lease_until', 'updated_at'])
        from operations.usage import finalize_run
        finalize_run(run)
        _event(job, run, 'coverage_gap' if gap else 'answer_ready')
        return True
