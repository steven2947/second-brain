"""学习HTTP公开字段与严格输入；内部固定卡正文不进入响应。"""
from rest_framework import serializers
from accounts.serializers import StrictSerializer
from problems.serializers import ExactTextField, InputUUIDField, RevisionField
from knowledge.serializers import CardSummarySerializer, PageQuerySerializer
from runs.serializers import STATUSES, STAGES


class CreateLearningSerializer(StrictSerializer):
    """显式选择固定版本和真实卡；创建不调用模型。"""
    release_id = InputUUIDField()
    basis_card_ids = serializers.ListField(child=ExactTextField(max_length=240), min_length=1, max_length=1000)
    goal = ExactTextField(max_length=20000, trim_whitespace=False)
    problem_id = InputUUIDField(required=False, allow_null=True)


class SendLearningMessageSerializer(StrictSerializer):
    """每次显式请求或原回答都带去重ID与已读修订。"""
    content = ExactTextField(max_length=20000, trim_whitespace=False)
    client_message_id = InputUUIDField()
    expected_revision = RevisionField(min_value=0, max_value=9223372036854775806)
    mode = serializers.ChoiceField(choices=['explain', 'practice', 'respond'])
    responds_to_turn_id = InputUUIDField(required=False, allow_null=True)


class ArchiveLearningSerializer(StrictSerializer):
    """归档显式传入当前修订。"""
    expected_revision = RevisionField(min_value=0, max_value=9223372036854775806)


class LearningQuerySerializer(PageQuerySerializer):
    """本人学习分页，可筛选归档状态。"""
    status = serializers.ChoiceField(choices=['active', 'archived'], required=False)


class LearningSessionSerializer(StrictSerializer):
    """轻量学习会话，不含私有输入。"""
    id = serializers.UUIDField()
    release_id = serializers.UUIDField()
    problem_id = serializers.UUIDField(allow_null=True)
    title = serializers.CharField()
    goal = serializers.CharField()
    basis_card_ids = serializers.ListField(child=serializers.CharField())
    revision = serializers.IntegerField(min_value=0)
    status = serializers.ChoiceField(choices=['active', 'archived'])
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class LearningSectionSerializer(StrictSerializer):
    """自由展开原理、应用、边界；引用只能来自所选卡。"""
    title = serializers.CharField()
    body = serializers.CharField()
    basis_card_ids = serializers.ListField(child=serializers.CharField())


class LearningContentSerializer(StrictSerializer):
    """用户原文或完整讲解与扩展段落。"""
    text = serializers.CharField()
    sections = LearningSectionSerializer(many=True)


class LearningTurnSerializer(StrictSerializer):
    """五种持久学习记录，反馈保留真实回答引用。"""
    id = serializers.UUIDField()
    learning_session_id = serializers.UUIDField()
    sequence = serializers.IntegerField(min_value=1)
    kind = serializers.ChoiceField(choices=['user_request', 'explanation', 'exercise', 'user_response', 'feedback'])
    content = LearningContentSerializer()
    run_id = serializers.UUIDField(allow_null=True)
    responds_to_turn_id = serializers.UUIDField(allow_null=True)
    created_at = serializers.DateTimeField()


class LearningJobSerializer(StrictSerializer):
    """学习专用任务状态，不伪造问题引用。"""
    id = serializers.UUIDField()
    learning_session_id = serializers.UUIDField()
    run_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=STATUSES)
    stage = serializers.ChoiceField(choices=STAGES)
    error_code = serializers.CharField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)


class LearningDetailSerializer(StrictSerializer):
    """实际回合分页与可恢复的当前任务。"""
    session = LearningSessionSerializer()
    items = LearningTurnSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
    library_available = serializers.BooleanField()
    basis_cards = CardSummarySerializer(many=True)
    active_job = LearningJobSerializer(allow_null=True)


class LearningSessionPageSerializer(StrictSerializer):
    """本人已授权学习列表。"""
    items = LearningSessionSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
