"""个人记录输入严格白名单；行动文字仅来自服务端当前授权投影。"""
from rest_framework import serializers
from accounts.serializers import StrictSerializer
from knowledge.serializers import PageQuerySerializer
from problems.serializers import ExactTextField, InputUUIDField, RevisionField
from .models import STATUSES, CATEGORIES


class SaveBookmarkSerializer(StrictSerializer):
    """备注允许清空，不能提供owner或卡片正文。"""
    note = ExactTextField(max_length=2000, allow_blank=True, trim_whitespace=False, required=False)


class BookmarkSerializer(StrictSerializer):
    """撤权后保留不可用占位，备注不再公开。"""
    id = serializers.UUIDField()
    release_id = serializers.UUIDField()
    core_card_id = serializers.CharField()
    note = serializers.CharField(allow_null=True, allow_blank=True)
    available = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class BookmarkPageSerializer(StrictSerializer):
    """本人收藏分页。"""
    items = BookmarkSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class CreateActionSerializer(StrictSerializer):
    """创建只能选择正式答案及零起始行动序号。"""
    answer_id = InputUUIDField()
    action_index = RevisionField(min_value=0, max_value=2147483647)


class UpdateActionSerializer(StrictSerializer):
    """修订号保护观察和状态不被旧窗口覆盖。"""
    expected_revision = RevisionField(min_value=0, max_value=9223372036854775807)
    status = serializers.ChoiceField(choices=STATUSES, required=False)
    observation = ExactTextField(max_length=10000, allow_blank=True, trim_whitespace=False, required=False)

    def validate(self, attrs):
        """attrs为已校验输入；至少包含一项实际修改。"""
        if not {'status', 'observation'} & set(attrs):
            raise serializers.ValidationError('没有指定修改')
        return attrs


class ActionQuerySerializer(PageQuerySerializer):
    """按本人问题和行动状态过滤。"""
    problem_id = serializers.UUIDField(required=False)
    status = serializers.ChoiceField(choices=STATUSES, required=False)


class ActionRecordSerializer(StrictSerializer):
    """行动四项正文每次从当前获准答案取得，不接受客户端副本。"""
    id = serializers.UUIDField()
    problem_id = serializers.UUIDField()
    answer_id = serializers.UUIDField()
    action_index = serializers.IntegerField(min_value=0)
    status = serializers.ChoiceField(choices=STATUSES)
    observation = serializers.CharField(allow_blank=True)
    revision = serializers.IntegerField(min_value=0)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    step = serializers.CharField()
    completion_criteria = serializers.CharField()
    validation_signal = serializers.CharField()
    stop_condition = serializers.CharField()


class ActionPageSerializer(StrictSerializer):
    """不含未授权行动的正文、数量或标识。"""
    items = ActionRecordSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class CreateFeedbackSerializer(StrictSerializer):
    """答案反馈不允许用户设置审核状态。"""
    answer_id = InputUUIDField()
    category = serializers.ChoiceField(choices=CATEGORIES)
    comment = ExactTextField(max_length=2000, allow_blank=True, trim_whitespace=False)


class FeedbackSerializer(StrictSerializer):
    """只返回当前提交的反馈内容。"""
    id = serializers.UUIDField()
    answer_id = serializers.UUIDField()
    category = serializers.ChoiceField(choices=CATEGORIES)
    comment = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
