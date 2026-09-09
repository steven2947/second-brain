"""登记事实、持久导入租约和后台幂等结果。"""
from django.conf import settings
from django.db import models
from knowledge.models import Timestamped


class RegisteredSource(Timestamped):
    """仅迁移角色可登记的固定目录和验证指纹。"""
    staging_key = models.SlugField(max_length=80, unique=True)
    storage_key = models.CharField(max_length=240)
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    source_fingerprint = models.CharField(max_length=64)
    content_version = models.CharField(max_length=24)
    book_count = models.PositiveIntegerField()
    card_count = models.PositiveIntegerField()


class ImportJob(Timestamped):
    """独立导入任务，身份快照与租约防止旧执行者落库。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    source = models.ForeignKey(RegisteredSource, on_delete=models.PROTECT)
    device_id = models.UUIDField()
    auth_epoch = models.PositiveBigIntegerField()
    source_fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=12, default='queued')
    stage = models.CharField(max_length=24, default='queued')
    lease_token = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    attempts = models.PositiveIntegerField(default=0)
    release = models.ForeignKey('knowledge.LibraryRelease', null=True, on_delete=models.PROTECT)
    error_code = models.CharField(max_length=48, null=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(status__in=['queued', 'running', 'succeeded', 'failed']), name='publishing_job_status_valid')]


class AdminMutation(Timestamped):
    """同一管理员、操作和幂等键对应一个安全公开结果。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    operation = models.CharField(max_length=240)
    key = models.CharField(max_length=128)
    body_hash = models.CharField(max_length=64)
    response = models.JSONField(default=dict)
    response_status = models.PositiveIntegerField(default=200)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'operation', 'key'], name='publishing_mutation_unique')]
