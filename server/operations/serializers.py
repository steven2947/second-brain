"""隐私操作严格输入与公开元数据白名单。"""
from rest_framework import serializers
from accounts.serializers import StrictSerializer
from problems.serializers import ExactTextField, RevisionField


class ExportRequestSerializer(StrictSerializer):
    """只导出所选个人范围，密码只用于本次再认证。"""
    scope = serializers.ChoiceField(choices=['problems', 'learning', 'all_personal'])
    password = ExactTextField(max_length=256, trim_whitespace=False, write_only=True)


class PersonalExportSerializer(StrictSerializer):
    """不返回磁盘位置、租约、权限快照或永久下载URL。"""
    id = serializers.UUIDField()
    scope = serializers.ChoiceField(choices=['problems', 'learning', 'all_personal'])
    status = serializers.ChoiceField(choices=['queued', 'running', 'ready', 'failed', 'expired'])
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField(allow_null=True)
    error_code = serializers.CharField(allow_null=True)


class PersonalExportPageSerializer(StrictSerializer):
    items = PersonalExportSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class PrivacyRevisionSerializer(StrictSerializer):
    expected_revision = RevisionField(min_value=0, max_value=9223372036854775806)


class TrashItemSerializer(StrictSerializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    status = serializers.ChoiceField(choices=['deleted'])
    revision = serializers.IntegerField(min_value=0)
    deleted_at = serializers.DateTimeField()
    purge_after = serializers.DateTimeField()


class TrashPageSerializer(StrictSerializer):
    items = TrashItemSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class AccountDeletionRequestSerializer(StrictSerializer):
    password = ExactTextField(max_length=256, trim_whitespace=False, write_only=True)
    confirmation = serializers.ChoiceField(choices=['删除我的账号'])


class AccountDeletionSerializer(StrictSerializer):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=['pending'])
    requested_at = serializers.DateTimeField()
    purge_after = serializers.DateTimeField()
