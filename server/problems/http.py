"""问题载荷使用独立大小限制，不放宽已有账号请求限制。"""
import json
from functools import wraps

from django.core.exceptions import RequestDataTooBig
from rest_framework.exceptions import ValidationError
from accounts.http import endpoint
from knowledge.http import read_query


def problem_endpoint(methods, input_serializer):
    """methods/serializer为操作契约；为既有无路径参数的错误边界绑定UUID路由参数。"""
    def decorate(view):
        """view为带可选路由参数的实际问题操作。"""
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            """request为HTTP请求；args/kwargs仅由Django已解析路由提供。"""
            def bound(current_request):
                """current_request经既有错误边界处理，不改原账号装饰器行为。"""
                return view(current_request, *args, **kwargs)
            return endpoint(methods, input_serializer=input_serializer)(bound)(request)
        wrapped.allowed_methods = frozenset(methods)
        wrapped.input_serializer = input_serializer
        return wrapped
    return decorate


def _unique_object(pairs):
    """pairs为JSON对象键值对；重复键使幂等语义不明确，直接拒绝。"""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('重复请求字段')
        result[key] = value
    return result


def _reject_constant(value):
    """value为非标准JSON常量；NaN/Infinity不是有效用户输入。"""
    raise ValueError('非标准JSON')


def read_problem_input(request, serializer_class):
    """request为问题写请求；serializer_class定义本操作字段白名单。"""
    try:
        if request.content_type != 'application/json' or len(request.body) > 256 * 1024:
            raise ValueError('请求内容无效')
        data = json.loads(request.body, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        serializer = serializer_class(data=data)
        serializer.is_valid(raise_exception=True)
    except (ValidationError, UnicodeDecodeError, RecursionError, RequestDataTooBig):
        raise ValueError('请求内容无效') from None
    return serializer.validated_data


def read_problem_query(query, serializer_class):
    """query为QueryDict；复用已有重复键检查，不读取知识或数据库。"""
    return read_query(query, serializer_class)
