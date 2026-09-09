"""知识读取的即时授权快照；不缓存授权，不将数据库对象交给公开接口。"""
from uuid import UUID

from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from accounts.services import AccountError
from access.context import owner_transaction
from knowledge.models import LibraryGrant, ReleaseBook, RightsRecord


class KnowledgeError(AccountError):
    """公开固定错误；继承账号错误以复用现有HTTP错误边界。"""


def not_found():
    """无参数；存在性与无权统一处理，避免泄漏版本和书目。"""
    return KnowledgeError('NOT_FOUND', '资源不存在', 404)


def _nonempty(value):
    """value为许可文本；空白与非文本都不是有效审批事实。"""
    return isinstance(value, str) and bool(value.strip())


def _current_user(user):
    """user为可信已登录对象；在当前短事务内复查持久身份和会话epoch。"""
    current = User.objects.filter(pk=user.pk, status='active', is_staff=False,
                                  is_superuser=False, auth_epoch=user.auth_epoch).first()
    if current is None:
        raise not_found()
    return current


def authorized_release_ids(user):
    """user为可信会话用户；仅物化其当前有效grant的版本ID，不读取目录或别人的标题。"""
    with owner_transaction(user.pk):
        _current_user(user)
        return list(LibraryGrant.objects.filter(owner_id=user.pk, role='reader',
            status='active', revoked_at=None).filter(
            Q(expires_at=None) | Q(expires_at__gt=timezone.now())).order_by('release_id')
            .values_list('release_id', flat=True))


def access_snapshot(user, release_id, *, purpose='browse'):
    """user/release_id为可信用户与UUID；purpose由服务端指定，分析必须同时满足浏览与分析覆盖。"""
    if purpose not in ('browse', 'analyze'):
        raise not_found()
    try:
        release_id = UUID(str(release_id))
    except (ValueError, AttributeError, TypeError):
        raise not_found() from None
    with owner_transaction(user.pk):
        current, now = _current_user(user), timezone.now()
        grant = LibraryGrant.objects.select_related('release__library').filter(
            owner_id=current.pk, release_id=release_id, role='reader', status='active',
            revoked_at=None).filter(Q(expires_at=None) | Q(expires_at__gt=now)).first()
        if grant is None:
            raise not_found()
        release, collection = grant.release, grant.release.library
        if (collection.status != 'active' or release.status != 'published'
                or not release.validated_at or not release.published_at
                or release.rights_status != 'approved' or not _nonempty(release.rights_record_key)):
            raise not_found()
        books = list(ReleaseBook.objects.filter(release_id=release_id).order_by('core_book_id')
                     .values_list('core_book_id', flat=True))
        book_ids = set(books)
        if not books or len(books) != release.book_count or not all(_nonempty(book) for book in books):
            raise not_found()
        rights = list(RightsRecord.objects.filter(release_id=release_id).order_by('id').values())
        browse, analyze, quotes = set(), set(), {}
        for right in rights:
            if (right['status'] != 'approved' or not right['reviewer_id'] or not right['reviewed_at']
                    or not _nonempty(right['source_description'])
                    or (right['valid_until'] is not None and right['valid_until'] <= now)
                    or right['allowed_audience'] != 'granted_users'
                    or right['basis_type'] not in ('self_authored', 'public_domain', 'license', 'permission', 'other')
                    or (right['basis_type'] in ('license', 'permission', 'other')
                        and not _nonempty(right['proof_storage_key']))):
                continue
            scope, uses = right['scope_book_ids'], right['allowed_uses']
            if (not isinstance(scope, list) or not all(_nonempty(value) for value in scope)
                    or len(scope) != len(set(scope)) or not set(scope) <= book_ids
                    or not isinstance(uses, list) or not all(
                        isinstance(value, str) and value in ('browse', 'quote', 'analyze') for value in uses)):
                continue
            applies = set(scope) if scope else book_ids
            if 'browse' in uses:
                browse.update(applies)
            if 'analyze' in uses:
                analyze.update(applies)
            policy = right['quote_policy']
            if ('quote' in uses and isinstance(policy, dict) and set(policy) == {'max_chars'}
                    and type(policy['max_chars']) is int and 1 <= policy['max_chars'] <= 2000):
                for book in applies:
                    quotes[book] = min(quotes.get(book, 2000), policy['max_chars'])
        if browse != book_ids or (purpose == 'analyze' and analyze != book_ids):
            raise not_found()
        # 保存实际字段值，不单看updated_at：管理SQL可能不更新时间戳。
        return {'user': {'id': current.pk, 'auth_epoch': current.auth_epoch,
                         'access_revision': current.access_revision, 'status': current.status,
                         'is_staff': current.is_staff, 'is_superuser': current.is_superuser},
                'grant': {field.attname: getattr(grant, field.attname) for field in grant._meta.fields},
                'release': {field.attname: getattr(release, field.attname) for field in release._meta.fields},
                'collection': {field.attname: getattr(collection, field.attname) for field in collection._meta.fields},
                'rights': rights, 'books': books, 'quotes': quotes}


def analysis_snapshot(user, release_id):
    """user/release_id为分析任务所属身份与版本；复用同一许可事实源，不由浏览权限推定分析权限。"""
    return access_snapshot(user, release_id, purpose='analyze')
