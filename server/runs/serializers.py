"""消息和任务公开字段；运行时快照和供应商上下文不进入浏览器。"""
from rest_framework import serializers
from accounts.serializers import StrictSerializer
from problems.serializers import ExactTextField, InputUUIDField, RevisionField

STATUSES = ['queued','running','cancel_requested','succeeded','failed','cancelled']
STAGES = ['accepted','understanding','retrieving','evaluating','validating','composing']


class SendMessageSerializer(StrictSerializer):
    """真实用户消息只接受原文、显式意图、客户端去重ID和已读修订。"""
    content = ExactTextField(max_length=20000, trim_whitespace=False)
    intent = serializers.ChoiceField(choices=['answer','supplement','analyze_now','unknown'])
    client_message_id = InputUUIDField()
    expected_revision = RevisionField(min_value=0, max_value=9223372036854775807)

    def validate_content(self, value):
        """value为原消息；空白不构成用户陈述，不裁剪有效原文。"""
        if not value.strip():
            raise serializers.ValidationError('请填写消息')
        return value


class AnalyzeSerializer(StrictSerializer):
    """按钮提交直接分析意图；无权指定模型或内部状态。"""
    expected_revision = RevisionField(min_value=0, max_value=9223372036854775807)


class AcceptedRunSerializer(StrictSerializer):
    """202只证明真实任务已入库，不代表模型已开始或完成。"""
    run_id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    revision = serializers.IntegerField(min_value=0)


class MessageSerializer(StrictSerializer):
    """公开可见消息原文，不附带内部推理或提示词。"""
    id = serializers.UUIDField()
    problem_id = serializers.UUIDField()
    sequence = serializers.IntegerField(min_value=1)
    role = serializers.ChoiceField(choices=['user','assistant'])
    kind = serializers.ChoiceField(choices=['user_text','clarification','answer','notice'])
    content = serializers.CharField(trim_whitespace=False)
    client_message_id = serializers.UUIDField(allow_null=True)
    run_id = serializers.UUIDField(allow_null=True)
    published_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class MessagePageSerializer(StrictSerializer):
    """同一问题有界消息列表；失权时仍可显示本人原文。"""
    items = MessageSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
    revision = serializers.IntegerField(min_value=0)
    library_available = serializers.BooleanField()


class JobSerializer(StrictSerializer):
    """执行状态以持久job为唯一事实源；只公开固定阶段和错误码。"""
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=STATUSES)
    stage = serializers.ChoiceField(choices=STAGES)
    run_id = serializers.UUIDField()
    problem_id = serializers.UUIDField()
    result_ref = serializers.UUIDField(allow_null=True)
    error_code = serializers.CharField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)


class RunSerializer(StrictSerializer):
    """运行语义加关联job状态，不另存前端猜测进度。"""
    id = serializers.UUIDField()
    problem_id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=STATUSES)
    stage = serializers.ChoiceField(choices=STAGES)
    input_revision = serializers.IntegerField(min_value=0)
    outcome = serializers.ChoiceField(choices=['question','answer','coverage_gap','unavailable'], allow_null=True)
    stale = serializers.BooleanField()
    error_code = serializers.CharField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
