"""正式答案完整包只在服务端保存；公开投影不是第二份分析真源。"""
from django.conf import settings
from django.db import models
from problems.models import Timestamped


class Answer(Timestamped):
    """同一运行最多发布一次；结构通过不冒充真实语义质量验收。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    problem = models.ForeignKey('problems.Problem', on_delete=models.CASCADE)
    run = models.OneToOneField('runs.AnalysisRun', on_delete=models.CASCADE)
    schema_version = models.PositiveSmallIntegerField(default=3)
    internal_packet = models.JSONField()
    public_payload = models.JSONField()
    rendered_markdown = models.TextField()
    content_hash = models.CharField(max_length=64)
    validation_status = models.CharField(max_length=24, default='structure_passed')
    published_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'id'], name='answer_owner_id_unique'),
            models.UniqueConstraint(fields=['owner', 'problem', 'id'], name='answer_owner_problem_id_unique'),
            models.CheckConstraint(condition=models.Q(schema_version=3), name='answer_schema_v3'),
            models.CheckConstraint(condition=models.Q(content_hash__regex=r'^[0-9a-f]{64}$'), name='answer_hash_valid'),
            models.CheckConstraint(condition=models.Q(validation_status__in=['structure_passed', 'semantic_reviewed']), name='answer_validation_status'),
        ]
        indexes = [models.Index(fields=['owner', 'problem', '-published_at', 'id'], name='answer_owner_problem_time')]
