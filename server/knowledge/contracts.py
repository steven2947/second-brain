"""从实际知识路由和serializer生成OpenAPI片段，不连接数据库。"""
from uuid import UUID
from django.urls import resolve, reverse
from rest_framework import serializers
from accounts.contracts import field_schema, reference


OPERATIONS = (
    ('knowledge-libraries', 'listLibraries', {}),
    ('knowledge-books', 'listLibraryBooks', {'release_id': UUID(int=1)}),
    ('knowledge-book', 'getLibraryBook', {'release_id': UUID(int=1), 'book_id': 'book.contract'}),
    ('knowledge-cards', 'listLibraryCards', {'release_id': UUID(int=1)}),
    ('knowledge-card', 'getLibraryCard', {'release_id': UUID(int=1), 'card_id': 'card.contract'}),
    ('knowledge-evidence', 'getLibraryEvidence', {'release_id': UUID(int=1), 'evidence_id': 'evidence.contract'}),
)


def public_field_schema(field):
    """field为实际公开字段；递归展开嵌套对象和列表，其余复用账号字段转换。"""
    if isinstance(field, (serializers.ListSerializer, serializers.ListField)):
        return {'type': 'array', 'items': public_field_schema(field.child)}
    if isinstance(field, serializers.Serializer):
        return public_serializer_schema(field)
    return field_schema(field)


def public_serializer_schema(serializer):
    """serializer为实际响应/查询实例；未知输出字段一律禁止。"""
    result = {'type': 'object', 'additionalProperties': False,
              'properties': {name: public_field_schema(field) for name, field in serializer.fields.items()}}
    required = [name for name, field in serializer.fields.items() if field.required]
    if required:
        result['required'] = required
    return result


def build_fragment():
    """无参数；路径、允许方法和字段从已登记端点推导，不加入规划接口。"""
    paths, schemas = {}, {}
    for route, operation_id, arguments in OPERATIONS:
        url = reverse(route, kwargs=arguments)
        view = resolve(url).func
        if view.allowed_methods != frozenset({'GET'}):
            raise ValueError('知识契约引用了未实现的方法')
        parameters = []
        for name, value in arguments.items():
            url = url.replace(str(value), '{' + name + '}')
            schema = {'type': 'string', 'format': 'uuid'} if name == 'release_id' else {'type': 'string', 'minLength': 1}
            parameters.append({'name': name, 'in': 'path', 'required': True, 'schema': schema})
        for name, field in view.query_serializer().fields.items():
            schema = public_field_schema(field)
            if field.default is not serializers.empty:
                schema['default'] = field.default
            parameters.append({'name': name, 'in': 'query', 'required': field.required, 'schema': schema})
        response_name = view.response_serializer.__name__.removesuffix('Serializer')
        schemas[response_name] = public_serializer_schema(view.response_serializer())
        paths[url] = {'get': {'operationId': operation_id, 'security': [{'SessionCookie': []}],
            'parameters': parameters, 'responses': {
                '200': {'description': '获准内容；禁止缓存', 'content': {'application/json': {'schema': reference(response_name)}}},
                'default': {'description': '固定公开错误；无权与不存在统一404，损坏的获准版本503',
                            'content': {'application/json': {'schema': reference('ErrorResponse')}}}}}}
    return paths, schemas
