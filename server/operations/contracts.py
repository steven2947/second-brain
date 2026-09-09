"""从已实现隐私路由与serializer输出0.11契约片段。"""
from uuid import UUID
from django.urls import resolve, reverse
from accounts.contracts import reference
from knowledge.contracts import public_field_schema, public_serializer_schema

OPERATIONS = (
    ('privacy-exports', 'GET', 'listPersonalExports', {}, 200),
    ('privacy-exports', 'POST', 'requestPersonalExport', {}, 202),
    ('privacy-export', 'GET', 'getPersonalExport', {'export_id': UUID(int=1)}, 200),
    ('privacy-download', 'GET', 'downloadPersonalExport', {'export_id': UUID(int=1)}, 200),
    ('privacy-trash', 'GET', 'listTrash', {}, 200),
    ('privacy-restore', 'POST', 'restoreProblem', {'problem_id': UUID(int=1)}, 200),
    ('privacy-deletion', 'POST', 'requestAccountDeletion', {}, 202),
)


def build_fragment():
    """无参数；下载正文白名单由生成服务负责，根结构显式区别于任务元数据。"""
    paths, schemas = {}, {}
    for route, method, operation_id, arguments, status in OPERATIONS:
        url = reverse(route, kwargs=arguments)
        view = resolve(url).func
        if method not in view.allowed_methods:
            raise ValueError('隐私契约引用未实现操作')
        parameters = []
        for name, value in arguments.items():
            url = url.replace(str(value), '{' + name + '}')
            parameters.append({'name': name, 'in': 'path', 'required': True, 'schema': {'type': 'string', 'format': 'uuid'}})
        success = {'description': '本人隐私操作；禁止缓存'}
        serializer = view.response_serializers[method]
        if serializer:
            name = serializer.__name__.removesuffix('Serializer')
            if name != 'Problem':
                schemas[name] = public_serializer_schema(serializer())
            success['content'] = {'application/json': {'schema': reference(name)}}
        if route == 'privacy-download':
            success['description'] = '再次校验本人、知识许可、记录变化与24小时有效期的JSON附件；不提供永久URL'
            success['headers'] = {'Content-Disposition': {'schema': {'type': 'string'}}}
            success['content'] = {'application/json': {'schema': reference('PersonalExportDocument')}}
        operation = {'operationId': operation_id, 'security': [{'SessionCookie': []}],
            'parameters': parameters, 'responses': {str(status): success,
                'default': {'description': '固定公开错误；过期410、尚未完成或许可变更409',
                    'content': {'application/json': {'schema': reference('ErrorResponse')}}}}}
        if method == 'GET':
            parameters.extend({'name': name, 'in': 'query', 'required': field.required,
                'schema': public_field_schema(field)} for name, field in view.query_serializer().fields.items())
        else:
            parameters.append({'$ref': '#/components/parameters/CsrfHeader'})
            name = view.input_serializer.__name__.removesuffix('Serializer')
            if name != 'PrivacyRevision':
                schemas[name] = public_serializer_schema(view.input_serializer())
            operation['requestBody'] = {'required': True, 'content': {'application/json': {'schema': reference(name)}}}
            if route == 'privacy-exports':
                parameters.append({'name': 'Idempotency-Key', 'in': 'header', 'required': True,
                    'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
                    'description': '绑定scope；每次重新核验密码，密码不进入持久请求摘要'})
            if route == 'privacy-restore':
                operation['responses']['409'] = {'description': '修订冲突',
                    'content': {'application/json': {'schema': reference('ProblemConflictResponse')}}}
        paths.setdefault(url, {})[method.lower()] = operation
    arrays = ('problems', 'messages', 'answers', 'learning', 'learning_turns', 'bookmarks', 'actions', 'feedback', 'omissions')
    schemas['PersonalExportDocument'] = {'type': 'object', 'additionalProperties': False,
        'required': ['schema_version', 'export_id', 'scope', 'generated_at', *arrays],
        'properties': {'schema_version': {'type': 'integer', 'enum': [1]},
            'export_id': {'type': 'string', 'format': 'uuid'},
            'scope': {'type': 'string', 'enum': ['problems', 'learning', 'all_personal']},
            'generated_at': {'type': 'string', 'format': 'date-time'},
            'profile': {'type': 'object', 'additionalProperties': True},
            **{name: {'type': 'array', 'items': {'type': 'object', 'additionalProperties': True}} for name in arrays}}}
    return paths, schemas
