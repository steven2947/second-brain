"""独立导入worker：有界只读解析在事务外，短租约与当前身份控制最终落库。"""
from datetime import timedelta
from uuid import uuid4
from django.db.models import Q
from django.utils import timezone
from accounts.services import AccountError
from administration.models import AdminAudit
from access.context import owner_transaction
from knowledge.models import LibraryCollection, LibraryRelease, ReleaseBook, ReleaseCard, ReleaseEvidence
from knowledge.projections import book_payload, card_summary, books_by_id
from .access import current_actor, failure, source_library, source_fingerprint
from .models import ImportJob, RegisteredSource


def claim(owner):
    """owner为可信本机扫描身份；回收超时任务，最多三次尝试并签发新租约。"""
    with owner_transaction(owner):
        now = timezone.now()
        job = ImportJob.objects.select_for_update(skip_locked=True).filter(owner_id=owner).filter(
            Q(status='queued') | Q(status='running', lease_until__lte=now)).order_by('created_at').first()
        if job is None:
            return None
        try:
            current_actor(owner, job.device_id, job.auth_epoch, 'knowledge.import')
            if job.attempts >= 3:
                raise failure('IMPORT_RETRY_EXHAUSTED')
        except AccountError as error:
            job.status, job.stage, job.error_code = 'failed', 'failed', error.code
            job.save(update_fields=['status', 'stage', 'error_code', 'updated_at'])
            return job
        job.status, job.stage = 'running', 'validating'
        job.lease_token, job.lease_until = uuid4(), now + timedelta(minutes=5)
        job.attempts += 1
        job.save()
        return job


def finalize(job, library):
    """job为执行者租约快照，library为事务外真实校验对象；旧租约和已撤身份不能发布投影。"""
    with owner_transaction(job.owner_id):
        current = ImportJob.objects.select_for_update().get(pk=job.pk)
        if current.status != 'running' or current.lease_token != job.lease_token or current.lease_until <= timezone.now():
            raise failure('IMPORT_LEASE_LOST')
        actor = current_actor(job.owner_id, job.device_id, job.auth_epoch, 'knowledge.import')
        source = RegisteredSource.objects.get(pk=job.source_id)
        if source.source_fingerprint != job.source_fingerprint or library.version != source.content_version:
            raise failure('SOURCE_CHANGED')
        collection = LibraryCollection.objects.create(title=source.title, description=source.description, curator=actor)
        release = LibraryRelease.objects.create(library=collection, storage_key=source.storage_key,
            source_fingerprint=source.source_fingerprint, content_version=source.content_version,
            status='validated', rights_status='unreviewed', validated_at=timezone.now(),
            book_count=len(library.manifest['books']), card_count=len(library.cards))
        for book in library.manifest['books']:
            payload = book_payload(book)
            ReleaseBook.objects.create(release=release, core_book_id=payload['id'], title=payload['title'],
                author_display=payload['author_display'], metadata_status=payload['metadata_status'])
        books = books_by_id(library)
        ReleaseCard.objects.bulk_create([ReleaseCard(release=release, core_card_id=card['id'],
            core_book_id=card['book_id'], card_type=card['kind'], title=card['title'],
            browse_payload=card_summary(card, books[card['book_id']], release.pk)) for card in library.cards.values()])
        ReleaseEvidence.objects.bulk_create([ReleaseEvidence(release=release, core_evidence_id=record['id'],
            core_book_id=record['book_id'], chapter=record['chapter'], preview_payload={
                'evidence_id': record['id'], 'chapter': record['chapter']}) for record in library.evidence.values()])
        # 最后再次检查身份、登记事实、实际文件和租约；失败会回滚整个版本及投影。
        current_actor(job.owner_id, job.device_id, job.auth_epoch, 'knowledge.import')
        latest = RegisteredSource.objects.get(pk=source.pk)
        if (latest.source_fingerprint != job.source_fingerprint or latest.storage_key != source.storage_key
                or source_fingerprint(source.storage_key) != job.source_fingerprint):
            raise failure('SOURCE_CHANGED')
        if current.lease_until <= timezone.now():
            raise failure('IMPORT_LEASE_LOST')
        current.release, current.status, current.stage, current.error_code = release, 'succeeded', 'complete', None
        current.lease_token, current.lease_until = None, None
        current.save()
        AdminAudit.objects.create(actor_id=actor.pk, action='knowledge.import', target_id=release.pk)


def process_one(owner):
    """owner为运行进程枚举的用户UUID；处理一项真实任务并留下固定失败码。"""
    job = claim(owner)
    if job is None:
        return False
    if job.status == 'failed':
        return True
    try:
        source = RegisteredSource.objects.get(pk=job.source_id)
        if source.source_fingerprint != job.source_fingerprint:
            raise failure('SOURCE_CHANGED')
        library = source_library(source)
        finalize(job, library)
    except Exception as error:
        code = error.code if isinstance(error, AccountError) else 'IMPORT_FAILED'
        with owner_transaction(owner):
            ImportJob.objects.filter(pk=job.pk, owner_id=owner, status='running', lease_token=job.lease_token).update(
                status='failed', stage='failed', error_code=code, lease_token=None, lease_until=None)
    return True
