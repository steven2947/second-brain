"""从实际问题路由与输入/输出字段生成公开契约片段。"""
from uuid import UUID

from django.urls import resolve, reverse
from rest_framework import serializers
from accounts.contracts import reference
from knowledge.contracts import public_field_schema, public_serializer_schema
from .serializers import ProblemConflictResponseSerializer


OPERATIONS = (
    ('problem-collection', 'GET', 'listProblems', {}, 200),
    ('problem-collection', 'POST', 'createProblem', {}, 201),
    ('problem-detail', 'GET', 'getProblem', {'problem_id': UUID(int=1)}, 200),
    ('problem-detail', 'PATCH', 'updateProblem', {'problem_id': UUID(int=1)}, 200),
    ('problem-detail', 'DELETE', 'deleteProblem', {'problem_id': UUID(int=1)}, 204),
)


def build_fragment():
    """无参数；仅导出当前四个操作，不登记尚未实现的消息或任务。"""
    paths, schemas = {}, {}
    for route, method, operation_id, arguments, status in OPERATIONS:
        url = reverse(route, kwargs=arguments)
        view = resolve(url).func
        if method not in view.allowed_methods:
            raise ValueError('问题契约引用了未实现的方法')
        parameters = []
        for name, value in arguments.items():
            url = url.replace(str(value), '{' + name + '}')
            parameters.append({'name': name, 'in': 'path', 'required': True,
                               'schema': {'type': 'string', 'format': 'uuid'}})
        response = view.response_serializers[method]
        success = {'description': '本人档案；禁止缓存'}
        if response:
            response_name = response.__name__.removesuffix('Serializer')
            schemas[response_name] = public_serializer_schema(response())
            success['content'] = {'application/json': {'schema': reference(response_name)}}
        operation = {'operationId': operation_id, 'security': [{'SessionCookie': []}],
            'parameters': parameters, 'responses': {
                str(status): success,
                'default': {'description': '固定公开错误；不回显内部档案',
                    'content': {'application/json': {'schema': reference('ErrorResponse')}}}}}
        if method == 'GET':
            for name, field in view.query_serializer().fields.items():
                schema = public_field_schema(field)
                if field.default is not serializers.empty:
                    schema['default'] = field.default
                parameters.append({'name': name, 'in': 'query', 'required': field.required, 'schema': schema})
        else:
            parameters.append({'$ref': '#/components/parameters/CsrfHeader'})
            input_serializer = getattr(view, 'input_serializers', {}).get(method, view.input_serializer)
            input_name = input_serializer.__name__.removesuffix('Serializer')
            schemas[input_name] = public_serializer_schema(input_serializer())
            operation['requestBody'] = {'required': True,
                'content': {'application/json': {'schema': reference(input_name)}}}
            if method == 'POST':
                parameters.append({'name': 'Idempotency-Key', 'in': 'header', 'required': True,
                    'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128},
                    'description': '同用户、同路径、同键同内容重放；不同内容冲突。不自动换键重试。'})
            else:
                schemas['ProblemConflictResponse'] = public_serializer_schema(ProblemConflictResponseSerializer())
                operation['responses']['409'] = {'description': '档案被另一窗口更新',
                    'content': {'application/json': {'schema': reference('ProblemConflictResponse')}}}
        paths.setdefault(url, {})[method.lower()] = operation
    return paths, schemas
