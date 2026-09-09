"""账号锁串行化配额；调用账本在网络开始前提交，网络结束后独立结算。"""
import hashlib
import json
import re
import time
from datetime import timezone as utc_timezone

from django.conf import settings
from django.db.models import Max
from django.utils import timezone

from access.context import owner_transaction
from accounts.models import User
from ai.ports import Generation, ModelFailure
from .models import QuotaBucket, RunReservation, UsageEntry


class QuotaExceeded(Exception):
    """次数额度不足，公开层可映射固定429错误。"""


def reserve_run(user, run):
    """在排队owner事务内调用；账号锁覆盖不同问题和不同worker的同月预留。"""
    if run.owner_id != user.pk:
        raise ValueError('运行归属不符')
    User.objects.select_for_update().get(pk=user.pk)
    existing = RunReservation.objects.filter(owner=user, run=run).first()
    if existing is not None:
        return existing
    ceiling = getattr(settings, 'SB_MONTHLY_RUN_LIMIT', 100)
    if type(ceiling) is not int or not 0 <= ceiling <= 9223372036854775807:
        raise ValueError('服务端月度额度无效')
    period = timezone.now().astimezone(utc_timezone.utc).date().replace(day=1)
    bucket, _ = QuotaBucket.objects.get_or_create(owner=user, period=period,
                                                defaults={'limit_runs': ceiling})
    bucket = QuotaBucket.objects.select_for_update().get(pk=bucket.pk, owner=user)
    if bucket.reserved_runs + bucket.settled_runs >= bucket.limit_runs:
        raise QuotaExceeded('QUOTA_EXCEEDED')
    reservation = RunReservation.objects.create(owner=user, run=run, bucket=bucket)
    bucket.reserved_runs += 1
    bucket.revision += 1
    bucket.save(update_fields=['reserved_runs', 'revision', 'updated_at'])
    return reservation


def finalize_run(run):
    """由持有账号/问题/任务锁的终态事务调用；有一次实际调用便消费整轮额度。"""
    reservation = RunReservation.objects.select_for_update().filter(owner_id=run.owner_id, run=run).first()
    if reservation is None or reservation.state != 'reserved':
        return
    bucket = QuotaBucket.objects.select_for_update().get(owner_id=run.owner_id, pk=reservation.bucket_id)
    consumed = UsageEntry.objects.filter(owner_id=run.owner_id, run=run).exists()
    bucket.reserved_runs -= 1
    bucket.settled_runs += int(consumed)
    bucket.revision += 1
    bucket.save(update_fields=['reserved_runs', 'settled_runs', 'revision', 'updated_at'])
    reservation.state = 'settled' if consumed else 'released'
    reservation.save(update_fields=['state', 'updated_at'])


def _label(value):
    """仅保存有界标识，不接受正文、换行或任意对象的字符串表示。"""
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,239}', value) else None


def _tokens(value):
    """缺失或无效供应商usage保持NULL，明确报告的零才保存为零。"""
    return value if type(value) is int and 0 <= value <= 9223372036854775807 else None


class MeteredProvider:
    """租约检查、实际调用登记和供应商结果记账；不拥有结果发布权限。"""

    def __init__(self, inner, lease):
        """inner由可信worker注入，lease为当前任务尝试的固定令牌。"""
        self.inner, self.lease = inner, lease

    def generate(self, request):
        """每个调用先提交reserved；即使期间租约过期，finally仍记录实际耗用。"""
        from runs.queue import _locked
        if request.purpose not in ('extract', 'plan', 'analysis', 'analysis_repair', 'learning'):
            raise ModelFailure('INVALID_INPUT')
        prompt_version = hashlib.sha256(json.dumps([request.purpose, request.system, request.schema],
            sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        entry = None
        with owner_transaction(self.lease.owner_id):
            locked = _locked(self.lease)
            if locked is not None:
                user, _, _, run, _ = locked
                reservation = RunReservation.objects.filter(owner=user, run=run, state='reserved').first()
                if reservation is not None:
                    last = UsageEntry.objects.filter(owner=user, run=run, attempt=self.lease.attempt).aggregate(
                        last=Max('call_index'))['last'] or 0
                    if last < 24:
                        entry = UsageEntry.objects.create(owner=user, run=run, attempt=self.lease.attempt,
                            call_index=last+1, purpose=request.purpose, prompt_version=prompt_version)
        if entry is None:
            raise ModelFailure('RUN_FAILED')
        started, generation = time.monotonic(), None
        try:
            generation = self.inner.generate(request)
            return generation
        except ModelFailure as error:
            generation = error.usage
            raise
        finally:
            values = dict(usage_status='settled', duration_ms=min(9223372036854775807,
                max(0, int((time.monotonic()-started)*1000))))
            if isinstance(generation, Generation):
                values.update(provider=_label(generation.provider), model=_label(generation.model),
                    input_tokens=_tokens(generation.input_tokens), output_tokens=_tokens(generation.output_tokens),
                    cached_tokens=_tokens(generation.cached_tokens))
            with owner_transaction(self.lease.owner_id):
                User.objects.select_for_update().get(pk=self.lease.owner_id)
                UsageEntry.objects.filter(owner_id=self.lease.owner_id, pk=entry.pk,
                    usage_status='reserved').update(**values, updated_at=timezone.now())
