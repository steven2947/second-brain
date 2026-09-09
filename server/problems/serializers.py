"""问题公开输入与输出契约，不暴露完整核心档案。"""
from rest_framework import serializers
from accounts.serializers import StrictSerializer
from knowledge.serializers import PageQuerySerializer


class ExactTextField(serializers.CharField):
    """文本必须是原始字符串，不能把数字转成用户陈述。"""

    def to_internal_value(self, data):
        """data为原始JSON字段；保持原文类型。"""
        if not isinstance(data, str):
            self.fail('invalid')
        return super().to_internal_value(data)


class RevisionField(serializers.IntegerField):
    """产品修订只接受非负JSON整数。"""

    def to_internal_value(self, data):
        """data为客户端修订；bool/字符串/浮点不作整数。"""
        if type(data) is not int:
            self.fail('invalid')
        return super().to_internal_value(data)


class InputUUIDField(serializers.UUIDField):
    """外部知识版本必须是UUID字符串，不接收整数或bool。"""

    def to_internal_value(self, data):
        """data为请求JSON的标识；解析后交给服务标准UUID。"""
        if not isinstance(data, str):
            self.fail('invalid')
        return super().to_internal_value(data)


class CreateProblemSerializer(StrictSerializer):
    """只接受原问题、任务类型与固定知识版本。"""
    question = ExactTextField(max_length=4000, trim_whitespace=False)
    goal = serializers.ChoiceField(choices=['explain', 'analyze', 'compare', 'act', 'review'])
    release_id = InputUUIDField()

    def validate_question(self, value):
        """value为未裁剪原问题；空白不算实际问题。"""
        if not value.strip():
            raise serializers.ValidationError('请填写问题')
        return value


class UpdateProblemSerializer(StrictSerializer):
    """改名和归档不改写原问题，也不能设置删除或模型状态。"""
    title = ExactTextField(max_length=160, required=False)
    status = serializers.ChoiceField(choices=['active', 'archived'], required=False)
    expected_revision = RevisionField(min_value=0, max_value=9223372036854775807)

    def validate(self, attrs):
        """attrs为已验证字段；必须明确提供改名或状态变更。"""
        if not ({'title', 'status'} & set(attrs)):
            raise serializers.ValidationError('没有指定修改')
        return attrs


class ProblemQuerySerializer(PageQuerySerializer):
    """列表默认只看活动档案，分页有界。"""
    q = ExactTextField(max_length=500, allow_blank=True, required=False, default='')
    status = serializers.ChoiceField(choices=['active', 'archived'], required=False, default='active')


class ProblemDetailQuerySerializer(StrictSerializer):
    """本批详情不接收尚未实现的消息游标或内部扩展。"""


class ClarificationSerializer(StrictSerializer):
    """仅展示从已验证核心快照派生的提问状态。"""
    rounds = serializers.IntegerField(min_value=0, max_value=5)
    limit = serializers.IntegerField(min_value=1, max_value=5)
    pending_question = serializers.CharField(allow_null=True)
    closed = serializers.BooleanField()


class ProblemSerializer(StrictSerializer):
    """明确公开白名单；不输出owner、core_state或内部推断。"""
    id = serializers.UUIDField()
    title = serializers.CharField(max_length=160)
    original_question = serializers.CharField(max_length=4000, trim_whitespace=False)
    goal = serializers.ChoiceField(choices=['explain', 'analyze', 'compare', 'act', 'review'])
    release_id = serializers.UUIDField()
    revision = serializers.IntegerField(min_value=0)
    status = serializers.ChoiceField(choices=['active', 'archived'])
    clarification = ClarificationSerializer()
    current_answer_id = serializers.UUIDField(allow_null=True)
    library_available = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class ProblemPageSerializer(StrictSerializer):
    """本人问题列表不包含他人总数或未授权书目。"""
    items = ProblemSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class ProblemConflictSerializer(StrictSerializer):
    """修订冲突只附本人当前修订，不泄露快照。"""
    code = serializers.ChoiceField(choices=['REVISION_CONFLICT'])
    message = serializers.CharField()
    request_id = serializers.UUIDField()
    current_revision = serializers.IntegerField(min_value=0)


class ProblemConflictResponseSerializer(StrictSerializer):
    """冲突的公开响应结构。"""
    error = ProblemConflictSerializer()
