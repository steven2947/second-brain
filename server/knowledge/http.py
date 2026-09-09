"""知识GET接口的认证、查询校验和不可跨上下文复用的游标。"""
import hashlib
import json
from functools import wraps

from django.core import signing
from django.http import JsonResponse
from rest_framework.exceptions import ValidationError
from accounts.http import error_response
from accounts.services import AccountError, require_user


def read_query(query, serializer_class):
    """query为QueryDict，serializer_class为端点输入事实源；拒绝重复与未知字段。"""
    if any(len(values) != 1 for _, values in query.lists()):
        raise ValueError('请求内容无效')
    serializer = serializer_class(data=query.dict())
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError:
        raise ValueError('请求内容无效') from None
    return serializer.validated_data


def paginate(items, *, limit, cursor, scope):
    """items为已授权物化列表；scope绑定身份/查询/版本，列表指纹防集合变化后复用。"""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('分页无效')
    signature = hashlib.sha256(json.dumps([scope, items], ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    offset = 0
    if cursor:
        try:
            value = signing.loads(cursor, salt='knowledge.page.v1', max_age=900)
            if (not isinstance(value, dict) or set(value) != {'offset', 'scope'}
                    or type(value['offset']) is not int or not 0 < value['offset'] < len(items)
                    or value['scope'] != signature):
                raise ValueError
            offset = value['offset']
        except (signing.BadSignature, ValueError, TypeError):
            raise ValueError('分页无效') from None
    following = offset + limit
    next_cursor = signing.dumps({'offset': following, 'scope': signature}, salt='knowledge.page.v1') if following < len(items) else None
    return {'items': items[offset:following], 'next_cursor': next_cursor}


def page_result(result, user, query, route):
    """result为仓库公开物化结果；游标绑定服务器user及真实查询，保留版本元数据。"""
    filters = {key: value for key, value in query.items() if key not in {'cursor', 'limit'}}
    scope = json.dumps([str(user.pk), route, result.get('release_id'), result.get('content_version'), filters], sort_keys=True)
    return {**result, **paginate(result['items'], limit=query['limit'], cursor=query['cursor'], scope=scope)}


def read_endpoint(query_serializer, response_serializer):
    """两serializer分别为真实输入和输出事实源；仅支持同源会话GET，底层异常不出网。"""
    def decorate(view):
        """view接收request、可信user、已验证query及路由参数。"""
        @wraps(view)
        def wrapped(request, **kwargs):
            """request为当前HTTP请求；认证先于仓库导入和任何内容访问。"""
            if request.method != 'GET':
                response = error_response(request, 'METHOD_NOT_ALLOWED', '请求方法不允许', 405)
                response['Allow'] = 'GET'
                return response
            try:
                user = require_user(request)
                if request.body:
                    raise ValueError('GET不接受请求正文')
                query = read_query(request.GET, query_serializer)
                from .repository import KnowledgeError
                try:
                    result = view(request, user, query, **kwargs)
                except KnowledgeError as error:
                    return error_response(request, error.code, error.message, error.status)
                return JsonResponse(response_serializer(result).data)
            except AccountError as error:
                return error_response(request, error.code, error.message, error.status)
            except (ValueError, ValidationError):
                return error_response(request, 'INVALID_INPUT', '请求内容无效', 400)
        wrapped.allowed_methods = frozenset({'GET'})
        wrapped.query_serializer = query_serializer
        wrapped.response_serializer = response_serializer
        return wrapped
    return decorate
