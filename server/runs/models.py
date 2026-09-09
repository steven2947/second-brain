"""私有任务、固定输入快照与仅含公开状态的持久事件。"""
from django.conf import settings
from django.db import models

from problems.models import Timestamped


class Job(Timestamped):
    """持久任务状态，供未来租约执行使用；排队不等于已执行。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=10, default='run')
    status = models.CharField(max_length=20, default='queued')
    stage = models.CharField(max_length=20, default='accepted')
    attempt = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=2)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    deadline = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'id'], name='job_owner_id_unique'),
            models.CheckConstraint(condition=models.Q(kind__in=['run', 'learning']), name='job_kind_run'),
            models.CheckConstraint(condition=models.Q(status__in=['queued', 'running', 'cancel_requested', 'succeeded', 'failed', 'cancelled']), name='job_status_valid'),
            models.CheckConstraint(condition=models.Q(stage__in=['accepted', 'understanding', 'retrieving', 'evaluating', 'validating', 'composing']), name='job_stage_valid'),
            models.CheckConstraint(condition=models.Q(max_attempts__gte=1, attempt__lte=models.F('max_attempts')), name='job_attempt_bounds'),
        ]


class AnalysisRun(Timestamped):
    """一轮输入及完整核心档案快照；后续worker只能对快照提出状态变化。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    problem = models.ForeignKey('problems.Problem', null=True, blank=True, on_delete=models.CASCADE)
    learning_session = models.ForeignKey('learning.LearningSession', null=True, blank=True, on_delete=models.CASCADE)
    release = models.ForeignKey('knowledge.LibraryRelease', on_delete=models.PROTECT)
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name='run')
    input_revision = models.BigIntegerField()
    kind = models.CharField(max_length=10)
    access_revision = models.BigIntegerField()
    auth_epoch = models.BigIntegerField()
    authorization_snapshot = models.JSONField()
    input_message = models.ForeignKey('problems.Message', null=True, blank=True, on_delete=models.PROTECT)
    internal_state = models.JSONField()
    internal_request = models.JSONField(null=True, blank=True)
    internal_session = models.JSONField(null=True, blank=True)
    internal_draft = models.JSONField(null=True, blank=True)
    outcome = models.CharField(max_length=40, null=True, blank=True)
    stale_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'problem', 'id'], name='run_owner_problem_id_unique'),
            models.CheckConstraint(condition=models.Q(input_revision__gte=1), name='run_input_revision_positive'),
            models.CheckConstraint(condition=models.Q(kind__in=['turn', 'analysis'], problem__isnull=False, learning_session__isnull=True) | models.Q(kind='learning', problem__isnull=True, learning_session__isnull=False, input_message__isnull=True), name='run_kind_valid'),
            models.UniqueConstraint(fields=['owner', 'learning_session', 'id'], name='run_owner_learning_unique'),
            models.CheckConstraint(condition=models.Q(access_revision__gte=0, auth_epoch__gte=0), name='run_access_revision_valid'),
        ]


class JobEvent(Timestamped):
    """任务持锁追加的公开投影；不保存用户原文、模型提案或提示词。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    seq = models.BigIntegerField()
    event_type = models.CharField(max_length=20)
    public_payload = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['job', 'seq'], name='job_event_sequence_unique'),
            models.CheckConstraint(condition=models.Q(seq__gte=1), name='job_event_sequence_positive'),
            models.CheckConstraint(condition=models.Q(event_type__in=['stage', 'question_ready', 'answer_ready', 'learning_ready', 'coverage_gap', 'failed', 'cancelled']), name='job_event_type_valid'),
        ]
