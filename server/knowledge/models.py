"""产品知识发布元数据、权利记录和授权；内容事实仍在固定版本只读文件中。"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Substr


class Timestamped(models.Model):
    """通用UUID与审计时间；不包含隐式用户归属。"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class LibraryCollection(Timestamped):
    """逻辑知识集；scope仅分类，绝不构成任何读授权。"""
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=12, default='active')
    scope = models.CharField(max_length=12, default='private')
    curator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=['active', 'suspended']), name='knowledge_collection_state_valid'),
            models.CheckConstraint(condition=models.Q(scope__in=['demo', 'licensed', 'private']), name='knowledge_collection_scope_valid'),
        ]


class LibraryRelease(Timestamped):
    """固定单版本发布；技术验证与权利批准分别记录。"""
    library = models.ForeignKey(LibraryCollection, on_delete=models.PROTECT)
    content_version = models.CharField(max_length=24)
    source_fingerprint = models.CharField(max_length=64)
    storage_key = models.CharField(max_length=240)
    status = models.CharField(max_length=12, default='staged')
    rights_status = models.CharField(max_length=12, default='unreviewed')
    rights_record_key = models.CharField(max_length=240, null=True, blank=True)
    card_count = models.PositiveIntegerField(default=0)
    book_count = models.PositiveIntegerField(default=0)
    validated_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict)
    metadata_schema_version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['library', 'content_version'], name='knowledge_release_version_unique'),
            models.CheckConstraint(condition=models.Q(content_version__regex=r'^[0-9a-f]{24}$', source_fingerprint__regex=r'^[0-9a-f]{64}$'), name='knowledge_release_fingerprint_valid'),
            models.CheckConstraint(condition=models.Q(content_version=Substr('source_fingerprint', 1, 24)), name='knowledge_release_version_matches'),
            models.CheckConstraint(condition=models.Q(status__in=['staged', 'validated', 'published', 'revoked']), name='knowledge_release_state_valid'),
            models.CheckConstraint(condition=models.Q(rights_status__in=['unreviewed', 'approved', 'rejected', 'expired']), name='knowledge_release_rights_state'),
            models.CheckConstraint(condition=~models.Q(status='published') | models.Q(validated_at__isnull=False, published_at__isnull=False, rights_status='approved', book_count__gt=0, card_count__gt=0), name='knowledge_release_publish_ready'),
        ]


class LibraryGrant(Timestamped):
    """整release读授权；runtime只有按owner读取权，不提供自行授权写入口。"""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='library_grants')
    release = models.ForeignKey(LibraryRelease, on_delete=models.PROTECT)
    role = models.CharField(max_length=12, default='reader')
    status = models.CharField(max_length=12, default='active')
    expires_at = models.DateTimeField(null=True, blank=True)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='issued_library_grants')
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'release'], name='knowledge_grant_owner_release_unique'),
            models.CheckConstraint(condition=models.Q(role='reader'), name='knowledge_grant_role_reader'),
            models.CheckConstraint(condition=models.Q(status__in=['active', 'revoked']), name='knowledge_grant_state_valid'),
            models.CheckConstraint(condition=models.Q(status='active', revoked_at__isnull=True) | models.Q(status='revoked', revoked_at__isnull=False), name='knowledge_grant_revocation_matches'),
        ]


class RightsRecord(Timestamped):
    """逐版本权利事实；私有证明位置、审批和短引规则不得原样进入API。"""
    release = models.ForeignKey(LibraryRelease, on_delete=models.PROTECT, related_name='rights_records')
    scope_book_ids = models.JSONField(default=list)
    source_description = models.TextField()
    basis_type = models.CharField(max_length=20)
    license_name = models.TextField(null=True, blank=True)
    proof_storage_key = models.TextField(null=True, blank=True)
    allowed_audience = models.TextField()
    allowed_uses = models.JSONField(default=list)
    quote_policy = models.JSONField(default=dict)
    valid_until = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, default='unreviewed')

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=['unreviewed', 'approved', 'rejected', 'expired']), name='knowledge_rights_state_valid'),
            models.CheckConstraint(condition=models.Q(basis_type__in=['self_authored', 'public_domain', 'license', 'permission', 'other']), name='knowledge_rights_basis_valid'),
            models.CheckConstraint(condition=~models.Q(status='approved') | models.Q(reviewer__isnull=False, reviewed_at__isnull=False), name='knowledge_rights_review_required'),
        ]


class ReleaseBook(Timestamped):
    """可重建书目投影；作者未知时保持NULL和partial，不用模型补作者。"""
    release = models.ForeignKey(LibraryRelease, on_delete=models.PROTECT)
    core_book_id = models.CharField(max_length=240)
    title = models.TextField()
    author_display = models.TextField(null=True, blank=True)
    contributor_metadata = models.JSONField(default=dict)
    metadata_status = models.CharField(max_length=12, default='partial')
    cover_asset_key = models.CharField(max_length=240, null=True, blank=True)
    description = models.TextField(blank=True)
    chapter_summary = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['release', 'core_book_id'], name='knowledge_book_release_id_unique'),
            models.CheckConstraint(condition=models.Q(metadata_status__in=['verified', 'partial']), name='knowledge_book_metadata_valid'),
        ]


class ReleaseCard(Timestamped):
    """卡片公开投影；同release书籍外键另由数据库复合约束保证。"""
    release = models.ForeignKey(LibraryRelease, on_delete=models.PROTECT)
    core_card_id = models.CharField(max_length=240)
    core_book_id = models.CharField(max_length=240)
    card_type = models.CharField(max_length=40)
    title = models.TextField()
    browse_payload = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['release', 'core_card_id'], name='knowledge_card_release_id_unique')]


class ReleaseEvidence(Timestamped):
    """证据预览投影；不是原书或完整私有证据结构的第二份真源。"""
    release = models.ForeignKey(LibraryRelease, on_delete=models.PROTECT)
    core_evidence_id = models.CharField(max_length=240)
    core_book_id = models.CharField(max_length=240)
    chapter = models.TextField()
    preview_payload = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['release', 'core_evidence_id'], name='knowledge_evidence_release_id_unique')]
