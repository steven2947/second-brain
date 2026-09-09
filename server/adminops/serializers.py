"""后台运营公开输入和输出；禁止携带业务正文或邀请令牌。"""
from rest_framework import serializers as s
from accounts.serializers import StrictSerializer


class AdminStatusInputSerializer(StrictSerializer):
    status = s.ChoiceField(choices=['active', 'disabled'])
    expected_status = s.ChoiceField(choices=['active', 'disabled'])
    reason = s.CharField(max_length=500)


class AdminQuotaInputSerializer(StrictSerializer):
    expected_period = s.RegexField(r'^[0-9]{4}-(0[1-9]|1[0-2])-01$', max_length=10)
    limit_runs = s.IntegerField(min_value=0, max_value=9223372036854775807)
    expected_revision = s.IntegerField(min_value=0, max_value=9223372036854775806)


class AdminQuotaSerializer(StrictSerializer):
    owner_id = s.UUIDField()
    period = s.CharField()
    limit_runs = s.IntegerField()
    reserved_runs = s.IntegerField()
    settled_runs = s.IntegerField()
    revision = s.IntegerField()


class AdminInvitationInputSerializer(StrictSerializer):
    email = s.EmailField(max_length=254)


class AdminInvitationSerializer(StrictSerializer):
    delivery = s.ChoiceField(choices=['local_capture'])
    delivery_id = s.UUIDField()
    expires_at = s.DateTimeField()


class AdminRunCountSerializer(StrictSerializer):
    status = s.ChoiceField(choices=['queued', 'running', 'cancel_requested', 'succeeded', 'failed', 'cancelled'])
    count = s.IntegerField()


class AdminOperationsSerializer(StrictSerializer):
    period = s.CharField()
    run_counts = AdminRunCountSerializer(many=True)
    total_runs = s.IntegerField()


class AdminFeedbackCountSerializer(StrictSerializer):
    category = s.ChoiceField(choices=['helpful', 'shallow', 'unclear_principle', 'wrong_source', 'other'])
    count = s.IntegerField()


class AdminFeedbackSummarySerializer(StrictSerializer):
    category_counts = AdminFeedbackCountSerializer(many=True)
    total_feedback = s.IntegerField()
