"""公开权限与 Django 自定义权限的一一映射；不使用超级用户捷径。"""
from django.contrib.auth.models import Permission
from django.db.models import Q

PERMISSIONS = (
    'accounts.view', 'accounts.disable', 'quota.manage', 'accounts.invite',
    'knowledge.import', 'knowledge.review', 'knowledge.publish', 'knowledge.revoke',
    'grants.manage', 'operations.view', 'feedback.review',
)
ROLES = {
    'system-admin': PERMISSIONS,
    'knowledge-admin': tuple(name for name in PERMISSIONS if name.startswith('knowledge.')),
}


def granted_permissions(user):
    """每次查询显式用户/组授权；staff/superuser 均不隐式获得任何权限。"""
    codes = set(Permission.objects.filter(
        Q(user=user) | Q(group__user=user),
        content_type__app_label='administration', content_type__model='administratordevice',
    ).values_list('codename', flat=True))
    return sorted(name for name in PERMISSIONS if name.replace('.', '_') in codes)
