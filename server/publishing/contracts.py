"""从实际后台路由和序列化白名单导出OpenAPI。"""
from uuid import UUID
from django.urls import reverse, resolve
from accounts.contracts import reference
from knowledge.contracts import public_serializer_schema, public_field_schema

OPERATIONS = (
    ('admin-sources', 'listAdminSources', {}), ('admin-import-release', 'importAdminRelease', {}),
    ('admin-imports', 'listAdminImports', {}), ('admin-import-detail', 'getAdminImport', {'job_id': UUID(int=1)}),
    ('admin-releases', 'listAdminReleases', {}), ('admin-release-detail', 'getAdminRelease', {'release_id': UUID(int=1)}),
    ('admin-rights', 'reviewAdminRelease', {'release_id': UUID(int=1)}),
    ('admin-publish', 'publishAdminRelease', {'release_id': UUID(int=1)}),
    ('admin-revoke', 'revokeAdminRelease', {'release_id': UUID(int=1)}),
    ('admin-users', 'listAdminUsers', {}),
    ('admin-grant', 'manageAdminGrant', {'user_id': UUID(int=2), 'release_id': UUID(int=1)}),
    ('admin-user-status', 'updateAdminUserStatus', {'user_id': UUID(int=2)}),
    ('admin-user-quota', 'getAdminQuota', {'user_id': UUID(int=2)}),
    ('admin-invitations', 'createAdminInvitation', {}),
    ('admin-operations', 'getAdminOperations', {}),
    ('admin-feedback-summary', 'getAdminFeedbackSummary', {}),
)


def build_fragment():
    """无参数；遍历已绑定管理方法和真实输入输出类，复用安全契约导出。"""
    paths, schemas = {}, {}
    for route, operation_id, arguments in OPERATIONS:
        url = reverse(route, kwargs=arguments)
        view = resolve(url).func
        parameters = []
        for name, value in arguments.items():
            url = url.replace(str(value), '{' + name + '}')
            parameters.append({'name': name, 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}})
        paths[url] = {}
        for method, (input_type, output_type, status) in view.publishing_spec.items():
            if method not in view.allowed_methods:
                raise ValueError('后台契约方法漂移')
            output_name = output_type.__name__.removesuffix('Serializer')
            schemas[output_name] = public_serializer_schema(output_type())
            operation = {'operationId': operation_id + ('Delete' if method == 'DELETE' else ''),
                'security': [{'SessionCookie': []}], 'parameters': list(parameters), 'responses': {
                    str(status): {'description': '已提交的后台结果；禁止缓存'},
                    'default': {'description': '固定安全错误', 'content': {'application/json': {'schema': reference('ErrorResponse')}}}}}
            if method == 'PUT' and 'GET' in view.publishing_spec:
                operation['operationId'] = operation_id.replace('get', 'update', 1)
            if status != 204:
                operation['responses'][str(status)]['content'] = {'application/json': {'schema': reference(output_name)}}
            if method == 'GET':
                operation['parameters'].extend({'name': name, 'in': 'query', 'required': field.required,
                    'schema': public_field_schema(field)} for name, field in input_type().fields.items())
            else:
                input_name = input_type.__name__.removesuffix('Serializer')
                schemas[input_name] = public_serializer_schema(input_type())
                operation['parameters'].extend([{'$ref': '#/components/parameters/CsrfHeader'},
                    {'name': 'Idempotency-Key', 'in': 'header', 'required': True,
                     'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128, 'pattern': '^[A-Za-z0-9_.:-]+$'}}])
                operation['requestBody'] = {'required': True, 'content': {'application/json': {'schema': reference(input_name)}}}
            paths[url][method.lower()] = operation
    return paths, schemas
