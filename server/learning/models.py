"""学习记录独立于问题，固定知识输入仅供服务器使用。"""
from django.conf import settings
from django.db import models
from problems.models import Timestamped


class LearningSession(Timestamped):
    """同owner同release的学习会话；关联问题可空，不创建伪问题。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    release = models.ForeignKey('knowledge.LibraryRelease', on_delete=models.PROTECT)
    problem = models.ForeignKey('problems.Problem', null=True, blank=True, on_delete=models.PROTECT)
    title = models.CharField(max_length=160)
    goal = models.TextField()
    basis_card_ids = models.JSONField()
    fixed_input = models.JSONField()
    revision = models.BigIntegerField(default=0)
    status = models.CharField(max_length=10, default='active')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'id', 'release'], name='learning_owner_release_unique'),
            models.UniqueConstraint(fields=['owner', 'id'], name='learning_owner_id_unique'),
            models.CheckConstraint(condition=models.Q(revision__gte=0), name='learning_revision_valid'),
            models.CheckConstraint(condition=models.Q(status__in=['active', 'archived']), name='learning_status_valid'),
        ]


class LearningTurn(Timestamped):
    """请求、讲解、自编练习、用户原回答与反馈分别保存。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    learning_session = models.ForeignKey(LearningSession, on_delete=models.CASCADE)
    sequence = models.BigIntegerField()
    kind = models.CharField(max_length=20)
    content = models.JSONField()
    client_message_id = models.UUIDField(null=True, blank=True)
    run = models.ForeignKey('runs.AnalysisRun', null=True, blank=True, on_delete=models.PROTECT)
    responds_to_turn = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['learning_session', 'sequence'], name='learning_turn_sequence_unique'),
            models.UniqueConstraint(fields=['owner', 'learning_session', 'id'], name='learning_turn_owner_session_unique'),
            models.UniqueConstraint(fields=['owner', 'learning_session', 'client_message_id'], name='learning_turn_client_unique'),
            models.CheckConstraint(condition=models.Q(sequence__gte=1), name='learning_turn_sequence_valid'),
            models.CheckConstraint(condition=models.Q(kind__in=['user_request', 'explanation', 'exercise', 'user_response', 'feedback']), name='learning_turn_kind_valid'),
            models.CheckConstraint(condition=models.Q(kind__in=['user_response', 'feedback'], responds_to_turn__isnull=False) | models.Q(kind__in=['user_request', 'explanation', 'exercise'], responds_to_turn__isnull=True), name='learning_turn_response_required'),
        ]
