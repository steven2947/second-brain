"""月度次数不以未知费用冒充零元；关联必须保持同一归属。"""
from django.conf import settings
from django.db import models

from problems.models import Timestamped


class PersonalExport(Timestamped):
    """私有导出任务；只保存受控存储键、授权摘要与租约，不持久保存密码。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    scope = models.CharField(max_length=16)
    status = models.CharField(max_length=10, default='queued')
    auth_epoch = models.PositiveBigIntegerField()
    access_revision = models.PositiveBigIntegerField()
    attempts = models.PositiveSmallIntegerField(default=0)
    lease_token = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    deadline = models.DateTimeField()
    expires_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=40, null=True)
    binding = models.JSONField(default=dict)
    file_key = models.CharField(max_length=100, blank=True, default='')
    content_hash = models.CharField(max_length=64, blank=True, default='')

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(scope__in=['problems', 'learning', 'all_personal']), name='export_scope_valid'),
            models.CheckConstraint(condition=models.Q(status__in=['queued', 'running', 'ready', 'failed', 'expired']), name='export_status_valid'),
            models.CheckConstraint(condition=models.Q(attempts__lte=3), name='export_attempts_valid'),
        ]


class RetainedUsage(Timestamped):
    """删除后最多90天保留无用户、问题、任务标识或正文的统计。"""
    period = models.DateField()
    call_count = models.PositiveIntegerField()
    input_tokens = models.BigIntegerField(null=True)
    output_tokens = models.BigIntegerField(null=True)
    expires_at = models.DateTimeField()


class QuotaBucket(Timestamped):
    """UTC自然月额度；预留与已消费之和不能超过服务端上限。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    period = models.DateField()
    limit_runs = models.BigIntegerField()
    reserved_runs = models.BigIntegerField(default=0)
    settled_runs = models.BigIntegerField(default=0)
    revision = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'period'], name='quota_owner_period_unique'),
            models.UniqueConstraint(fields=['owner', 'id'], name='quota_owner_id_unique'),
            models.CheckConstraint(condition=models.Q(period__day=1), name='quota_month_start'),
            models.CheckConstraint(condition=models.Q(limit_runs__gte=0, reserved_runs__gte=0,
                settled_runs__gte=0, revision__gte=0) & models.Q(
                limit_runs__gte=models.F('reserved_runs')+models.F('settled_runs')), name='quota_totals_valid'),
        ]


class RunReservation(Timestamped):
    """每轮只有一份预留记录，终态转移只允许结算或释放一次。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    run = models.OneToOneField('runs.AnalysisRun', on_delete=models.CASCADE)
    bucket = models.ForeignKey(QuotaBucket, on_delete=models.PROTECT)
    state = models.CharField(max_length=10, default='reserved')

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(
            state__in=['reserved', 'settled', 'released']), name='reservation_state_valid')]


class UsageEntry(Timestamped):
    """先登记调用，再以实际报告结算；异常、超时和缺失usage仍保留未知值。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    run = models.ForeignKey('runs.AnalysisRun', on_delete=models.CASCADE)
    attempt = models.PositiveSmallIntegerField()
    call_index = models.PositiveSmallIntegerField()
    purpose = models.CharField(max_length=24)
    provider = models.CharField(max_length=240, null=True, blank=True)
    model = models.CharField(max_length=240, null=True, blank=True)
    input_tokens = models.BigIntegerField(null=True, blank=True)
    output_tokens = models.BigIntegerField(null=True, blank=True)
    cached_tokens = models.BigIntegerField(null=True, blank=True)
    duration_ms = models.BigIntegerField(null=True, blank=True)
    prompt_version = models.CharField(max_length=64)
    usage_status = models.CharField(max_length=10, default='reserved')
    cost_kind = models.CharField(max_length=10, default='unknown')
    cost_amount = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    currency = models.CharField(max_length=3, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'run', 'attempt', 'call_index'], name='usage_call_unique'),
            models.CheckConstraint(condition=models.Q(attempt__gte=1, call_index__gte=1,
                call_index__lte=24), name='usage_call_bounds'),
            models.CheckConstraint(condition=models.Q(purpose__in=[
                'extract', 'plan', 'analysis', 'analysis_repair', 'learning']), name='usage_purpose_valid'),
            models.CheckConstraint(condition=models.Q(prompt_version__regex=r'^[0-9a-f]{64}$'), name='usage_prompt_hash'),
            models.CheckConstraint(condition=models.Q(usage_status__in=['reserved', 'settled']), name='usage_status_valid'),
            models.CheckConstraint(condition=models.Q(cost_kind='unknown', cost_amount__isnull=True,
                currency__isnull=True), name='usage_cost_unknown'),
            *[models.CheckConstraint(condition=models.Q(**{field+'__isnull': True}) |
                models.Q(**{field+'__gte': 0}), name='usage_'+field+'_nonnegative')
                for field in ('input_tokens', 'output_tokens', 'cached_tokens', 'duration_ms')],
        ]
