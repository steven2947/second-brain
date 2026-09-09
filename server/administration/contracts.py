"""从四条真实后台身份路由导出契约。"""
from django.urls import reverse, resolve
from accounts.contracts import reference
from knowledge.contracts import public_serializer_schema
from .serializers import AdminLoginSerializer, AdminReauthSerializer, AdminIdentitySerializer, PublicAdministratorSerializer

OPERATIONS = (
    ('admin-login', 'POST', 'adminLogin', 200),
    ('admin-me', 'GET', 'getAdminMe', 200),
    ('admin-reauth', 'POST', 'adminReauth', 200),
    ('admin-logout', 'POST', 'adminLogout', 204),
)


def build_fragment():
    """输出已实现四条路由及实际 serializer 字段，拒绝虚构能力。"""
    schemas = {kind.__name__.removesuffix('Serializer'): public_serializer_schema(kind())
        for kind in (AdminLoginSerializer, AdminReauthSerializer, AdminIdentitySerializer, PublicAdministratorSerializer)}
    schemas['AdminIdentity']['properties']['user'] = reference('PublicAdministrator')
    paths = {}
    for route, method, operation_id, status in OPERATIONS:
        url = reverse(route)
        view = resolve(url).func
        if method not in view.allowed_methods:
            raise ValueError('后台契约引用了未实现的方法')
        success = {'description': '后台身份校验成功；禁止缓存'}
        if status == 200:
            success['content'] = {'application/json': {'schema': reference('AdminIdentity')}}
        operation = {'operationId': operation_id, 'security': [] if route == 'admin-login' else [{'SessionCookie': []}],
            'responses': {str(status): success, 'default': {'description': '固定公开错误',
                'content': {'application/json': {'schema': reference('ErrorResponse')}}}}}
        if method == 'POST':
            operation['parameters'] = [{'$ref': '#/components/parameters/CsrfHeader'}]
            name = 'EmptyInput' if route == 'admin-logout' else view.input_serializer.__name__.removesuffix('Serializer')
            operation['requestBody'] = {'required': route != 'admin-logout',
                'content': {'application/json': {'schema': reference(name)}}}
        paths[url] = {method.lower(): operation}
    return paths, schemas
