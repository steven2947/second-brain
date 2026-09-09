"""从实际学习路由与serializer生成公开契约。"""
from uuid import UUID
from django.urls import resolve, reverse
from rest_framework import serializers
from accounts.contracts import reference
from knowledge.contracts import public_field_schema, public_serializer_schema
from .serializers import LearningSessionSerializer, LearningTurnSerializer, LearningJobSerializer

OPERATIONS = (
    ('learning-collection', 'GET', 'listLearningSessions', (), 200),
    ('learning-collection', 'POST', 'createLearningSession', (), 201),
    ('learning-detail', 'GET', 'getLearningSession', ('session_id',), 200),
    ('learning-messages', 'POST', 'sendLearningMessage', ('session_id',), 202),
    ('learning-archive', 'POST', 'archiveLearningSession', ('session_id',), 200),
    ('learning-job', 'GET', 'getLearningJob', ('session_id', 'job_id'), 200),
    ('learning-cancel', 'POST', 'cancelLearningJob', ('session_id', 'job_id'), 202),
)


def build_fragment():
    """无参数；学习命名独立，复用已有AcceptedRun引用避免重复定义。"""
    paths, schemas = {}, {kind.__name__.removesuffix('Serializer'): public_serializer_schema(kind())
        for kind in (LearningSessionSerializer, LearningTurnSerializer, LearningJobSerializer)}
    for route, method, operation_id, names, status in OPERATIONS:
        arguments = {name: UUID(int=index + 1) for index, name in enumerate(names)}
        url = reverse(route, kwargs=arguments)
        view = resolve(url).func
        parameters = []
        for name, value in arguments.items():
            url = url.replace(str(value), '{' + name + '}')
            parameters.append({'name': name, 'in': 'path', 'required': True,
                               'schema': {'type': 'string', 'format': 'uuid'}})
        response = view.response_serializers[method]
        response_name = response.__name__.removesuffix('Serializer')
        if response_name != 'AcceptedRun':
            schemas[response_name] = public_serializer_schema(response())
        if response_name == 'LearningDetail':
            schemas[response_name]['properties']['active_job'] = {'anyOf': [reference('LearningJob'), {'type': 'null'}]}
        operation = {'operationId': operation_id, 'security': [{'SessionCookie': []}], 'parameters': parameters,
            'responses': {str(status): {'description': '本人学习记录或实际任务；禁止缓存',
                'content': {'application/json': {'schema': reference(response_name)}}},
                'default': {'description': '固定公开错误', 'content': {
                    'application/json': {'schema': reference('ErrorResponse')}}}}}
        if method == 'GET':
            for name, field in view.query_serializer().fields.items():
                schema = public_field_schema(field)
                if field.default is not serializers.empty:
                    schema['default'] = field.default
                parameters.append({'name': name, 'in': 'query', 'required': field.required, 'schema': schema})
        else:
            parameters.append({'$ref': '#/components/parameters/CsrfHeader'})
            input_name = 'CancelLearningInput' if route == 'learning-cancel' else view.input_serializer.__name__.removesuffix('Serializer')
            schemas[input_name] = public_serializer_schema(view.input_serializer())
            operation['requestBody'] = {'required': route != 'learning-cancel',
                'content': {'application/json': {'schema': reference(input_name)}}}
            if route in ('learning-collection', 'learning-messages'):
                parameters.append({'name': 'Idempotency-Key', 'in': 'header', 'required': True,
                                   'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128}})
            if route == 'learning-cancel':
                operation['responses']['200'] = operation['responses']['202']
        paths.setdefault(url, {})[method.lower()] = operation
    return paths, schemas
