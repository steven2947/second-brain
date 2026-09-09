"""权利与发布状态机；HTTP写入在同一身份锁和幂等事务中执行。"""
import hashlib
import json
import re
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import F
from django.utils import timezone
from accounts.models import User
from access.context import owner_transaction
from administration.models import AdminAudit
from administration.services import SESSION_KEY, require_admin
from knowledge.models import LibraryRelease, LibraryGrant, ReleaseBook, RightsRecord
from .access import current_actor, failure, proof_exists, source_library, source_fingerprint
from .models import RegisteredSource, ImportJob, AdminMutation
from .serializers import AdminReleaseSerializer, AdminGrantSerializer


def release_payload(release, detail=False):
    """release为已授权ORM对象；detail决定是否附带无私有路径的书目与审核结果。"""
    result = {'id': release.pk, 'title': release.library.title, 'description': release.library.description,
        **{name: getattr(release, name) for name in ('content_version', 'status', 'rights_status', 'book_count', 'card_count')}}
    if detail:
        result['books'] = [{'id': book.core_book_id, 'title': book.title, 'author_display': book.author_display}
            for book in ReleaseBook.objects.filter(release=release).order_by('core_book_id')]
        result['rights_records'] = [{**{field: getattr(right, field) for field in (
            'id', 'scope_book_ids', 'basis_type', 'license_name', 'allowed_audience', 'allowed_uses',
            'quote_policy', 'valid_until', 'status', 'reviewed_at')}, 'proof_available': proof_exists(right.proof_storage_key)}
            for right in release.rights_records.order_by('created_at', 'id')]
    return result


def get_release(identifier, lock=False):
    """identifier为release UUID；lock为写流程短事务行锁开关。"""
    query = LibraryRelease.objects.select_related('library')
    if lock:
        query = query.select_for_update(of=('self',))
    result = query.filter(pk=identifier).first()
    if result is None:
        raise failure('NOT_FOUND', 404)
    return result


def coverage(release):
    """release为固定版本；从有效审核事实及真实存在的证明求全部书browse覆盖。"""
    books = set(ReleaseBook.objects.filter(release=release).values_list('core_book_id', flat=True))
    covered, now = set(), timezone.now()
    for right in release.rights_records.filter(status='approved'):
        scope, uses = right.scope_book_ids, right.allowed_uses
        if (not right.reviewer_id or not right.reviewed_at or not right.source_description.strip()
                or right.allowed_audience != 'granted_users' or (right.valid_until and right.valid_until <= now)
                or right.basis_type not in ('self_authored', 'public_domain', 'license', 'permission', 'other')
                or (right.basis_type in ('license', 'permission', 'other') and not proof_exists(right.proof_storage_key))
                or not isinstance(scope, list) or not all(isinstance(item, str) for item in scope)
                or len(scope) != len(set(scope)) or not set(scope) <= books
                or not isinstance(uses, list) or not all(item in ('browse', 'analyze', 'quote') for item in uses)):
            continue
        if 'browse' in uses:
            covered.update(set(scope) if scope else books)
    return bool(books) and len(books) == release.book_count and covered == books


def audited(actor, action, target, request):
    """actor为真实管理员，action/target为固定操作和目标UUID，request只提供请求编号。"""
    AdminAudit.objects.create(actor_id=actor.pk, action=action, target_id=target,
        request_id=request.account_request_id)


def mutate(request, permission, data, execute, status=200, prepare=None):
    """request/permission/data为已认证操作，execute在短事务执行；prepare可选且在事务外解析文件。"""
    actor = require_admin(request, permission, fresh=True)
    key = request.headers.get('Idempotency-Key', '')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', key):
        raise failure('IDEMPOTENCY_KEY_REQUIRED', 400)
    operation = request.method + ':' + request.path
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, cls=DjangoJSONEncoder, separators=(',', ':')).encode()).hexdigest()
    state = request.session[SESSION_KEY]
    if prepare is not None:
        # 先授权并识别重放；文件解析期间不占用账号或release行锁。
        with owner_transaction(actor.pk):
            current_actor(actor.pk, state['device_id'], state['epoch'], permission)
            previous = AdminMutation.objects.filter(owner=actor, operation=operation, key=key).first()
            if previous:
                if previous.body_hash != digest:
                    raise failure('IDEMPOTENCY_CONFLICT')
                return previous.response, previous.response_status
        prepare()
    with owner_transaction(actor.pk):
        actor = current_actor(actor.pk, state['device_id'], state['epoch'], permission)
        require_admin(request, permission, fresh=True)
        previous = AdminMutation.objects.filter(owner=actor, operation=operation, key=key).first()
        if previous:
            if previous.body_hash != digest:
                raise failure('IDEMPOTENCY_CONFLICT')
            return previous.response, previous.response_status
        result = execute(actor)
        current_actor(actor.pk, state['device_id'], state['epoch'], permission)
        result = json.loads(json.dumps(result, cls=DjangoJSONEncoder))
        AdminMutation.objects.create(owner=actor, operation=operation, key=key, body_hash=digest,
            response=result, response_status=status)
        return result, status


def enqueue(request, data):
    """request/data为导入写请求；登记源来自DB，不允许客户端指定身份或路径。"""
    def execute(actor):
        """actor为事务内再次确认的管理员；持久化独立任务与源指纹。"""
        source = RegisteredSource.objects.filter(staging_key=data['staging_key']).first()
        if source is None:
            raise failure('SOURCE_NOT_REGISTERED', 404)
        state = request.session[SESSION_KEY]
        job = ImportJob.objects.create(owner=actor, source=source, source_fingerprint=source.source_fingerprint,
            device_id=state['device_id'], auth_epoch=state['epoch'])
        audited(actor, 'knowledge.import', job.pk, request)
        return {'job_id': job.pk}
    return mutate(request, 'knowledge.import', data, execute, 202)


def review(request, identifier, data):
    """request/identifier/data为版本权利审核；保留旧记录但使其失效，服务端填写审批身份与时间。"""
    def execute(actor):
        """actor为事务内管理员；已发布版本必须先撤销才能重新审核。"""
        release = get_release(identifier, True)
        if release.status == 'published':
            raise failure('RELEASE_MUST_REVOKE')
        books = set(ReleaseBook.objects.filter(release=release).values_list('core_book_id', flat=True))
        for record in data['records']:
            scope = record['scope_book_ids']
            if len(scope) != len(set(scope)) or not set(scope) <= books:
                raise failure('INVALID_RIGHTS_SCOPE', 400)
            if 'quote' in record['allowed_uses'] and set(record['quote_policy']) != {'max_chars'}:
                raise failure('INVALID_QUOTE_POLICY', 400)
            if record['proof_storage_key'] and not proof_exists(record['proof_storage_key']):
                raise failure('PROOF_UNAVAILABLE', 400)
            if record['status'] == 'approved' and record['basis_type'] in ('license', 'permission', 'other') and not proof_exists(record['proof_storage_key']):
                raise failure('PROOF_REQUIRED', 400)
        release.rights_records.filter(status='approved').update(status='rejected')
        for record in data['records']:
            RightsRecord.objects.create(release=release, reviewer=actor, reviewed_at=timezone.now(), **record)
        release.rights_status = 'approved' if coverage(release) else (
            'rejected' if any(record['status'] == 'rejected' for record in data['records']) else 'unreviewed')
        release.rights_record_key = 'rights/' + str(release.pk)
        release.save(update_fields=['rights_status', 'rights_record_key', 'updated_at'])
        audited(actor, 'knowledge.review', release.pk, request)
        return AdminReleaseSerializer(release_payload(release)).data
    return mutate(request, 'knowledge.review', data, execute)


def transition(request, identifier, data, publish):
    """request/identifier/data为状态变更，publish由服务端路由固定；指纹与许可在提交前复核。"""
    permission = 'knowledge.publish' if publish else 'knowledge.revoke'
    prepared = None
    def prepare():
        """无参数；在MFA预检之后、事务之外真实解析固定库，保留最终事务内指纹复查。"""
        nonlocal prepared
        release = get_release(identifier)
        if release.status != data['expected_status']:
            raise failure('RELEASE_STATE_CONFLICT')
        if release.status not in ('validated', 'revoked') or not release.validated_at or release.rights_status != 'approved' or not coverage(release):
            raise failure('RELEASE_NOT_READY')
        library = source_library(release)
        prepared = (release.source_fingerprint, release.storage_key, len(library.cards), len(library.manifest['books']))
    def execute(actor):
        """actor为真实管理员；CAS状态冲突不可默默覆盖。"""
        release = get_release(identifier, True)
        if release.status != data['expected_status']:
            raise failure('RELEASE_STATE_CONFLICT')
        if publish:
            if release.status not in ('validated', 'revoked') or not release.validated_at or release.rights_status != 'approved' or not coverage(release):
                raise failure('RELEASE_NOT_READY')
            if prepared != (release.source_fingerprint, release.storage_key, release.card_count, release.book_count):
                raise failure('RELEASE_NOT_READY')
            if source_fingerprint(release.storage_key) != release.source_fingerprint:
                raise failure('SOURCE_UNAVAILABLE')
            release.status, release.published_at = 'published', timezone.now()
        else:
            release.status = 'revoked'
        release.save(update_fields=['status', 'published_at', 'updated_at'])
        audited(actor, permission, release.pk, request)
        return AdminReleaseSerializer(release_payload(release)).data
    return mutate(request, permission, data, execute, prepare=prepare if publish else None)


def manage_grant(request, user_id, release_id, data, revoke=False):
    """user_id/release_id为明确目标UUID；仅更新普通活跃用户授权与access_revision。"""
    def execute(actor):
        """actor为grants.manage管理员；目标状态与版本许可同事务核查。"""
        target = User.objects.select_for_update().filter(pk=user_id, status='active', is_staff=False, is_superuser=False).first()
        if target is None:
            raise failure('NOT_FOUND', 404)
        release = get_release(release_id, True)
        grant = LibraryGrant.objects.select_for_update().filter(owner=target, release=release).first()
        if revoke:
            if grant is None:
                raise failure('NOT_FOUND', 404)
            grant.status, grant.revoked_at = 'revoked', timezone.now()
        else:
            if release.status != 'published' or release.rights_status != 'approved' or not coverage(release):
                raise failure('RELEASE_NOT_READY')
            if data['expires_at'] and data['expires_at'] <= timezone.now():
                raise failure('INVALID_EXPIRY', 400)
            grant = grant or LibraryGrant(owner=target, release=release, granted_by=actor)
            grant.status, grant.revoked_at, grant.expires_at = 'active', None, data['expires_at']
            grant.granted_by = actor
        grant.save()
        User.objects.filter(pk=target.pk).update(access_revision=F('access_revision') + 1)
        audited(actor, 'grants.revoke' if revoke else 'grants.manage', grant.pk, request)
        return AdminGrantSerializer(grant).data
    return mutate(request, 'grants.manage', data, execute, 204 if revoke else 200)
