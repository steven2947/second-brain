"""问题档案保存完整核心状态；公开投影不成为另一份事实源。"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Length
from django.db.models.lookups import GreaterThanOrEqual, LessThanOrEqual


class Timestamped(models.Model):
    """UUID身份和审计时间，不隐式绑定请求身份。"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Problem(Timestamped):
    """本人草稿；core_state为唯一澄清事实源，revision独立保护产品编辑。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=160)
    original_question = models.TextField()
    goal = models.CharField(max_length=10)
    release = models.ForeignKey('knowledge.LibraryRelease', on_delete=models.PROTECT)
    core_problem_id = models.CharField(max_length=40, unique=True)
    core_state = models.JSONField()
    revision = models.BigIntegerField(default=0)
    processed_message_sequence = models.BigIntegerField(default=0)
    status = models.CharField(max_length=10, default='active')
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'id'], name='problem_owner_id_unique'),
            models.CheckConstraint(condition=models.Q(title__regex=r'\S'), name='problem_title_nonblank'),
            models.CheckConstraint(condition=models.Q(GreaterThanOrEqual(Length('original_question'), 1), LessThanOrEqual(Length('original_question'), 4000)), name='problem_question_length'),
            models.CheckConstraint(condition=models.Q(goal__in=['explain', 'analyze', 'compare', 'act', 'review']), name='problem_goal_valid'),
            models.CheckConstraint(condition=models.Q(revision__gte=0), name='problem_revision_nonnegative'),
            models.CheckConstraint(condition=models.Q(processed_message_sequence__gte=0), name='problem_processed_message_nonnegative'),
            models.CheckConstraint(condition=models.Q(status__in=['active', 'archived', 'deleted']), name='problem_status_valid'),
            models.CheckConstraint(condition=models.Q(status='deleted', deleted_at__isnull=False) | models.Q(status__in=['active', 'archived'], deleted_at__isnull=True), name='problem_deleted_matches'),
        ]
        indexes = [models.Index(fields=['owner', 'status', '-updated_at', 'id'], name='problem_owner_status_updated')]


class IdempotencyRecord(Timestamped):
    """产品写入幂等记录；响应仅保存公开白名单字段，不保存核心状态或提示词。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    method = models.CharField(max_length=10)
    route_scope = models.CharField(max_length=240)
    key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=10, default='processing')
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_payload = models.JSONField(null=True, blank=True)
    resource_type = models.CharField(max_length=40, null=True, blank=True)
    resource_id = models.UUIDField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'method', 'route_scope', 'key'], name='problem_idempotency_unique'),
            models.CheckConstraint(condition=models.Q(status__in=['processing', 'completed']), name='problem_idempotency_status'),
            models.CheckConstraint(condition=models.Q(request_hash__regex=r'^[0-9a-f]{64}$'), name='problem_idempotency_hash'),
        ]


class Message(Timestamped):
    """原始用户意图和已发布消息；不以UI重建历史或暴露内部模型状态。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    sequence = models.BigIntegerField()
    role = models.CharField(max_length=10)
    kind = models.CharField(max_length=20)
    content = models.TextField()
    client_message_id = models.UUIDField(null=True, blank=True)
    intent = models.CharField(max_length=20, default='unknown')
    run = models.ForeignKey('runs.AnalysisRun', null=True, blank=True, on_delete=models.SET_NULL)
    published_at = models.DateTimeField(null=True, blank=True)
    visibility = models.CharField(max_length=12, default='visible')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['problem', 'sequence'], name='message_problem_sequence_unique'),
            models.UniqueConstraint(fields=['owner', 'problem', 'client_message_id'],
                condition=models.Q(client_message_id__isnull=False), name='message_client_unique'),
            models.UniqueConstraint(fields=['owner', 'problem', 'id'], name='message_owner_problem_id_unique'),
            models.CheckConstraint(condition=models.Q(sequence__gte=1), name='message_sequence_positive'),
            models.CheckConstraint(condition=models.Q(role__in=['user', 'assistant']), name='message_role_valid'),
            models.CheckConstraint(condition=models.Q(kind__in=['user_text', 'clarification', 'answer', 'notice']), name='message_kind_valid'),
            models.CheckConstraint(condition=models.Q(intent__in=['answer', 'supplement', 'analyze_now', 'unknown']), name='message_intent_valid'),
            models.CheckConstraint(condition=models.Q(visibility__in=['visible', 'withdrawn']), name='message_visibility_valid'),
            models.CheckConstraint(condition=models.Q(content__regex=r'\S'), name='message_content_nonblank'),
            models.CheckConstraint(condition=models.Q(role='assistant') | models.Q(
                GreaterThanOrEqual(Length('content'), 1), LessThanOrEqual(Length('content'), 20000)), name='message_user_length'),
            models.CheckConstraint(condition=models.Q(role='assistant') | models.Q(kind='user_text'), name='message_user_kind'),
        ]
