"""本人正式答案只读服务；每次重新按当前许可投影，不返回旧短引缓存。"""
import copy
from jsonschema import Draft202012Validator, ValidationError
from access.context import owner_transaction
from access.services import analysis_snapshot, KnowledgeError
from ai.core_adapter import public_answer
from problems.services import _current_user, _get, _uuid, not_found, unavailable
from .models import Answer
from .presentation import packet_hash, render_markdown
from .schemas import content_schema


def _authorization(user, release_id):
    """user为当前真实账号；release_id来自本人答案的固定run，不来自客户端选择。"""
    try:
        return analysis_snapshot(user, release_id)
    except KnowledgeError:
        raise not_found() from None


def get_answer(user, answer_id):
    """user为已认证会话；answer_id仅查询本人非删除档案，始终重查分析与短引权限。"""
    answer_id = _uuid(answer_id, not_found)
    with owner_transaction(user.pk):
        current = _current_user(user)
        answer = Answer.objects.select_related('run__job').filter(owner=current, pk=answer_id).first()
        if answer is None or answer.run.job.status != 'succeeded' or answer.run.outcome != 'answer':
            raise not_found()
        problem = _get(current, answer.problem_id)
        before = _authorization(current, answer.run.release_id)
        packet = copy.deepcopy(answer.internal_packet)
        digest = answer.content_hash
        metadata = {'id': str(answer.pk), 'problem_id': str(problem.pk), 'run_id': str(answer.run_id),
            'release_id': str(answer.run.release_id), 'input_revision': answer.run.input_revision,
            'published_at': answer.published_at.isoformat(), 'validation_status': answer.validation_status,
            'content_hash': digest}
    try:
        if packet_hash(packet) != digest:
            raise ValueError('答案完整性校验失败')
        payload = public_answer(packet, quote_limits=before['quotes'])
        Draft202012Validator(content_schema()).validate(payload)
        rendered = render_markdown(payload)
    except (ValueError, KeyError, TypeError, ValidationError):
        raise unavailable() from None
    with owner_transaction(user.pk):
        current = _current_user(user)
        _get(current, answer.problem_id)
        if (_authorization(current, answer.run.release_id) != before
                or not Answer.objects.filter(owner=current, pk=answer_id, content_hash=digest,
                    internal_packet=packet, run__job__status='succeeded').exists()):
            raise not_found()
    return {**metadata, 'content': payload, 'rendered_markdown': rendered}
