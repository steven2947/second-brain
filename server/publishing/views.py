"""后台知识路由适配；不在视图中执行文件操作或授权规则。"""
from accounts.models import User
from accounts.serializers import EmptySerializer
from access.context import owner_transaction
from . import serializers as s, services
from .access import failure
from .http import endpoint, page, recent_page
from .models import RegisteredSource, ImportJob
from knowledge.models import LibraryRelease


@endpoint({'GET': (EmptySerializer, s.AdminSourcesSerializer, 200)}, 'knowledge.import')
def sources(request, actor, data):
    """request/actor/data为已认证请求；返回登记源的安全摘要。"""
    return {'items': list(RegisteredSource.objects.order_by('staging_key').values(
        'staging_key', 'title', 'content_version', 'book_count', 'card_count'))}


@endpoint({'POST': (s.ImportInputSerializer, s.ImportAcceptedSerializer, 202)}, 'knowledge.import')
def import_release(request, actor, data):
    """request/actor/data为真实MFA导入请求；只有持久任务提交才返回202。"""
    return services.enqueue(request, data)


@endpoint({'GET': (s.AdminPageQuerySerializer, s.AdminImportsSerializer, 200)}, 'knowledge.import')
def imports(request, actor, data):
    """request/actor/data为同owner分页；不泄漏其他管理员任务。"""
    with owner_transaction(actor.pk):
        return recent_page(ImportJob.objects.filter(owner=actor), data, lambda job: s.AdminImportSerializer(job).data)


@endpoint({'GET': (EmptySerializer, s.AdminImportSerializer, 200)}, 'knowledge.import')
def import_detail(request, actor, data, job_id):
    """job_id为待查询任务UUID；actor是唯一可见owner。"""
    with owner_transaction(actor.pk):
        job = ImportJob.objects.filter(pk=job_id, owner=actor).first()
        if job is None:
            raise failure('NOT_FOUND', 404)
        return s.AdminImportSerializer(job).data


@endpoint({'GET': (s.AdminPageQuerySerializer, s.AdminReleasesSerializer, 200)}, None)
def releases(request, actor, data):
    """request/actor/data为有明确知识管理权限的分页请求。"""
    return page(LibraryRelease.objects.select_related('library'), data, services.release_payload)


@endpoint({'GET': (EmptySerializer, s.AdminReleaseDetailSerializer, 200)}, None)
def release_detail(request, actor, data, release_id):
    """release_id为明确版本UUID；只返回公开书目及审核摘要。"""
    return services.release_payload(services.get_release(release_id), True)


@endpoint({'PUT': (s.RightsInputSerializer, s.AdminReleaseSerializer, 200)}, 'knowledge.review')
def rights(request, actor, data, release_id):
    """release_id/data为审核目标与明确人工作出的记录。"""
    return services.review(request, release_id, data)


@endpoint({'POST': (s.PublishInputSerializer, s.AdminReleaseSerializer, 200)}, 'knowledge.publish')
def publish(request, actor, data, release_id):
    """release_id/data为状态比较后发布操作，不把技术校验当许可。"""
    return services.transition(request, release_id, data, True)


@endpoint({'POST': (s.RevokeInputSerializer, s.AdminReleaseSerializer, 200)}, 'knowledge.revoke')
def revoke(request, actor, data, release_id):
    """release_id/data为撤销目标；普通访问立即依据同一状态失效。"""
    return services.transition(request, release_id, data, False)


@endpoint({'PUT': (s.GrantInputSerializer, s.AdminGrantSerializer, 200),
           'DELETE': (s.GrantRevokeInputSerializer, s.AdminGrantSerializer, 204)}, 'grants.manage')
def grant(request, actor, data, user_id, release_id):
    """user_id/release_id为显式目标，data仅允许有效期或撤销原因。"""
    return services.manage_grant(request, user_id, release_id, data, request.method == 'DELETE')


@endpoint({'GET': (s.AdminPageQuerySerializer, s.AdminUsersSerializer, 200)}, 'accounts.view')
def users(request, actor, data):
    """request/actor/data为accounts.view分页；只读普通账号公开身份字段。"""
    return page(User.objects.filter(is_staff=False, is_superuser=False), data, lambda user: s.AdminUserSerializer(user).data)
