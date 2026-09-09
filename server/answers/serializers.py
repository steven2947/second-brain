"""正式答案公开元数据；content使用源于v3字段的严格公开schema验证。"""
from rest_framework import serializers
from accounts.serializers import StrictSerializer


class AnswerSerializer(StrictSerializer):
    """无内部会话/草稿/提示词；Markdown与content来自同一当前授权投影。"""
    id = serializers.UUIDField()
    problem_id = serializers.UUIDField()
    run_id = serializers.UUIDField()
    release_id = serializers.UUIDField()
    input_revision = serializers.IntegerField(min_value=1)
    published_at = serializers.DateTimeField()
    validation_status = serializers.ChoiceField(choices=['structure_passed', 'semantic_reviewed'])
    content_hash = serializers.RegexField(r'^[0-9a-f]{64}$')
    content = serializers.JSONField()
    rendered_markdown = serializers.CharField(trim_whitespace=False)
