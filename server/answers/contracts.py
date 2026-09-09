"""从实际答案路由、元数据serializer与公开内容schema生成契约。"""
from uuid import UUID
from django.urls import resolve, reverse
from accounts.contracts import reference
from knowledge.contracts import public_field_schema
from .schemas import content_schema


def build_fragment():
    """无参数；只登记已经实现的GET答案，不预告未来答案列表或管理操作。"""
    identifier = UUID(int=1)
    url = reverse('answer-detail', kwargs={'answer_id': identifier})
    view = resolve(url).func
    if view.allowed_methods != frozenset({'GET'}):
        raise ValueError('答案路由未实现')
    properties = {name: public_field_schema(field) for name, field in view.response_serializer().fields.items()
                  if name != 'content'}
    properties['content'] = reference('AnswerContent')
    schemas = {'Answer': {'type': 'object', 'additionalProperties': False,
        'required': list(properties), 'properties': properties}, 'AnswerContent': content_schema()}
    return {url.replace(str(identifier), '{answer_id}'): {'get': {
        'operationId': 'getAnswer', 'security': [{'SessionCookie': []}],
        'parameters': [{'name': 'answer_id', 'in': 'path', 'required': True,
                        'schema': {'type': 'string', 'format': 'uuid'}}],
        'responses': {'200': {'description': '当前许可下已发布正式答案；禁止缓存',
            'content': {'application/json': {'schema': reference('Answer')}}},
            'default': {'description': '不存在与无权统一404；损坏答案503',
                'content': {'application/json': {'schema': reference('ErrorResponse')}}}}}}}, schemas
