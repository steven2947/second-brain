"""后台知识请求与响应的唯一白名单。"""
from rest_framework import serializers as s
from accounts.serializers import StrictSerializer


class AdminPageQuerySerializer(StrictSerializer):
    limit = s.IntegerField(min_value=1, max_value=100, default=30)
    cursor = s.UUIDField(required=False)


class ImportInputSerializer(StrictSerializer):
    staging_key = s.RegexField(r'^[A-Za-z0-9_-]+$', max_length=80)


class SourceSerializer(StrictSerializer):
    staging_key = s.CharField()
    title = s.CharField()
    content_version = s.CharField()
    book_count = s.IntegerField()
    card_count = s.IntegerField()


class AdminSourcesSerializer(StrictSerializer):
    items = SourceSerializer(many=True)


class ImportAcceptedSerializer(StrictSerializer):
    job_id = s.UUIDField()


class AdminImportSerializer(StrictSerializer):
    id = s.UUIDField()
    status = s.ChoiceField(choices=['queued', 'running', 'succeeded', 'failed'])
    stage = s.CharField()
    release_id = s.UUIDField(allow_null=True)
    error_code = s.CharField(allow_null=True)


class AdminImportsSerializer(StrictSerializer):
    items = AdminImportSerializer(many=True)
    next_cursor = s.CharField(allow_null=True)


class AdminReleaseSerializer(StrictSerializer):
    id = s.UUIDField()
    title = s.CharField()
    description = s.CharField(allow_blank=True)
    content_version = s.CharField()
    status = s.ChoiceField(choices=['staged', 'validated', 'published', 'revoked'])
    rights_status = s.ChoiceField(choices=['unreviewed', 'approved', 'rejected', 'expired'])
    book_count = s.IntegerField()
    card_count = s.IntegerField()


class AdminReleasesSerializer(StrictSerializer):
    items = AdminReleaseSerializer(many=True)
    next_cursor = s.CharField(allow_null=True)


class AdminBookSerializer(StrictSerializer):
    id = s.CharField()
    title = s.CharField()
    author_display = s.CharField(allow_null=True)


class QuotePolicySerializer(StrictSerializer):
    max_chars = s.IntegerField(min_value=1, max_value=2000, required=False)


class RightsInputRecordSerializer(StrictSerializer):
    scope_book_ids = s.ListField(child=s.CharField(max_length=240), max_length=1000)
    source_description = s.CharField(max_length=2000)
    basis_type = s.ChoiceField(choices=['self_authored', 'public_domain', 'license', 'permission', 'other'])
    license_name = s.CharField(max_length=500, allow_null=True, allow_blank=True)
    proof_storage_key = s.CharField(max_length=240, allow_null=True, allow_blank=True)
    allowed_audience = s.ChoiceField(choices=['granted_users'])
    allowed_uses = s.ListField(child=s.ChoiceField(choices=['browse', 'analyze', 'quote']), allow_empty=False, max_length=3)
    quote_policy = QuotePolicySerializer()
    valid_until = s.DateTimeField(allow_null=True)
    status = s.ChoiceField(choices=['approved', 'rejected'])


class RightsInputSerializer(StrictSerializer):
    records = RightsInputRecordSerializer(many=True, allow_empty=False, max_length=100)


class PublicRightsSerializer(StrictSerializer):
    id = s.UUIDField()
    scope_book_ids = s.ListField(child=s.CharField())
    basis_type = s.CharField()
    license_name = s.CharField(allow_null=True, allow_blank=True)
    allowed_audience = s.CharField()
    allowed_uses = s.ListField(child=s.CharField())
    quote_policy = QuotePolicySerializer()
    valid_until = s.DateTimeField(allow_null=True)
    status = s.CharField()
    reviewed_at = s.DateTimeField(allow_null=True)
    proof_available = s.BooleanField()


class AdminReleaseDetailSerializer(AdminReleaseSerializer):
    books = AdminBookSerializer(many=True)
    rights_records = PublicRightsSerializer(many=True)


class PublishInputSerializer(StrictSerializer):
    expected_status = s.ChoiceField(choices=['staged', 'validated', 'published', 'revoked'])


class RevokeInputSerializer(PublishInputSerializer):
    reason = s.CharField(max_length=500)


class GrantInputSerializer(StrictSerializer):
    expires_at = s.DateTimeField(allow_null=True)


class GrantRevokeInputSerializer(StrictSerializer):
    reason = s.CharField(max_length=500)


class AdminGrantSerializer(StrictSerializer):
    id = s.UUIDField()
    owner_id = s.UUIDField()
    release_id = s.UUIDField()
    status = s.ChoiceField(choices=['active', 'revoked'])
    expires_at = s.DateTimeField(allow_null=True)
    revoked_at = s.DateTimeField(allow_null=True)


class AdminUserSerializer(StrictSerializer):
    id = s.UUIDField()
    email = s.EmailField()
    display_name = s.CharField()
    status = s.ChoiceField(choices=['active', 'disabled', 'deletion_pending'])


class AdminUsersSerializer(StrictSerializer):
    items = AdminUserSerializer(many=True)
    next_cursor = s.CharField(allow_null=True)
