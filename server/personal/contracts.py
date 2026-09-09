"""从实际个人记录路由与serializer导出契约，不要求幂等请求头。"""
from uuid import UUID
from django.urls import resolve, reverse
from rest_framework import serializers
from accounts.contracts import reference
from knowledge.contracts import public_field_schema, public_serializer_schema

OPERATIONS = (
    ('personal-bookmarks', 'GET', 'listBookmarks', {}, 200),
    ('personal-bookmark', 'PUT', 'saveBookmark', {'release_id': UUID(int=1), 'card_id': 'card.contract'}, 200),
    ('personal-bookmark', 'DELETE', 'deleteBookmark', {'release_id': UUID(int=1), 'card_id': 'card.contract'}, 204),
    ('personal-actions', 'GET', 'listActions', {}, 200),
    ('personal-actions', 'POST', 'createAction', {}, 201),
    ('personal-action', 'PATCH', 'updateAction', {'action_id': UUID(int=1)}, 200),
    ('personal-feedback', 'POST', 'createFeedback', {}, 201),
)


def build_fragment():
    """无参数；只登记已实现的七个操作及其真实字段。"""
    paths, schemas = {}, {}
    for route, method, operation_id, arguments, status in OPERATIONS:
        url = reverse(route, kwargs=arguments)
        view = resolve(url).func
        if method not in view.allowed_methods:
            raise ValueError('个人记录契约引用未实现操作')
        parameters = []
        for name, value in arguments.items():
            url = url.replace(str(value), '{' + name + '}')
            schema = {'type': 'string', 'format': 'uuid'} if isinstance(value, UUID) else {'type': 'string', 'minLength': 1}
            parameters.append({'name': name, 'in': 'path', 'required': True, 'schema': schema})
        success = {'description': '本人记录；禁止缓存'}
        response = view.response_serializers[method]
        if response:
            name = response.__name__.removesuffix('Serializer')
            schemas[name] = public_serializer_schema(response())
            success['content'] = {'application/json': {'schema': reference(name)}}
        operation = {'operationId': operation_id, 'security': [{'SessionCookie': []}],
            'parameters': parameters, 'responses': {str(status): success,
                'default': {'description': '固定公开错误', 'content': {'application/json': {'schema': reference('ErrorResponse')}}}}}
        if method == 'GET':
            for name, field in view.query_serializer().fields.items():
                schema = public_field_schema(field)
                if field.default is not serializers.empty:
                    schema['default'] = field.default
                parameters.append({'name': name, 'in': 'query', 'required': field.required, 'schema': schema})
        else:
            parameters.append({'$ref': '#/components/parameters/CsrfHeader'})
            if method != 'DELETE':
                name = view.input_serializer.__name__.removesuffix('Serializer')
                schemas[name] = public_serializer_schema(view.input_serializer())
                operation['requestBody'] = {'required': True, 'content': {'application/json': {'schema': reference(name)}}}
            if method == 'PATCH':
                operation['responses']['409'] = {'description': '行动修订冲突',
                    'content': {'application/json': {'schema': reference('ProblemConflictResponse')}}}
        paths.setdefault(url, {})[method.lower()] = operation
    return paths, schemas
