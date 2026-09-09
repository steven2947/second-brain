"""模型处理在事务外，租约线程使用独立DB连接；正式答案经原v3校验才原子发布。"""
import threading
from django.db import close_old_connections, connections
from django.utils import timezone
from ai.intake_service import advance_messages
from ai.ports import DisabledProvider, ModelFailure
from ai.provider import provider_from_settings
from .queue import claim, heartbeat, finish_failure, publish_question


def _renew(lease, stopped, cancelled):
    """lease为当前租约；stopped结束续租，cancelled通知模型停止，不共享主线程连接。"""
    try:
        while not stopped.wait(5):
            close_old_connections()
            if not heartbeat(lease):
                cancelled.set()
                return
    except Exception:
        # 续租异常不得继续产出或把底层报文写入公开事件。
        cancelled.set()
    finally:
        connections.close_all()


def process_one(owner_id, *, provider=None):
    """owner_id来自内部调度；provider是服务端端口，仅测试显式注入自编提案。返回是否领取任务。"""
    close_old_connections()
    lease = claim(owner_id)
    if lease is None:
        return False
    stopped, cancelled = threading.Event(), threading.Event()
    renewal = None
    try:
        provider = provider if provider is not None else provider_from_settings()
        if isinstance(provider, DisabledProvider):
            raise ModelFailure('MODEL_UNAVAILABLE')
        from operations.usage import MeteredProvider
        provider = MeteredProvider(provider, lease)
        if not heartbeat(lease):
            return True
        remaining = min(900,(lease.deadline-timezone.now()).total_seconds())
        if remaining<=0:
            raise ModelFailure('RUN_TIMEOUT')
        renewal = threading.Thread(target=_renew,args=(lease,stopped,cancelled),daemon=True)
        renewal.start()
        if lease.kind == 'learning':
            from learning.generation import generate, publish
            result = generate(lease, provider, timeout_seconds=remaining, cancelled=cancelled.is_set)
            if cancelled.is_set():
                raise ModelFailure('RUN_CANCELLED')
            publish(lease, result)
            return True
        result = advance_messages(lease.state,lease.messages,provider,
            timeout_seconds=remaining,cancelled=cancelled.is_set)
        if cancelled.is_set():
            raise ModelFailure('RUN_CANCELLED')
        if result['outcome']=='question':
            publish_question(lease,result)
        else:
            from answers.publisher import analyze_release, publish_answer
            remaining = min(900, (lease.deadline-timezone.now()).total_seconds())
            if remaining <= 0:
                raise ModelFailure('RUN_TIMEOUT')
            library, analysis = analyze_release(lease, result, provider,
                timeout_seconds=remaining, cancelled=cancelled.is_set)
            publish_answer(lease, result, analysis, library)
    except ModelFailure as error:
        finish_failure(lease,error.code)
    except Exception:
        import sys, traceback
        traceback.print_exc(file=sys.stderr)
        finish_failure(lease,'RUN_FAILED')
    finally:
        stopped.set()
        if renewal is not None:
            renewal.join(timeout=10)
        close_old_connections()
    return True
