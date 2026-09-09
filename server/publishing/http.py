"""后台HTTP边界：真实MFA、明确权限、全站CSRF、输入输出白名单。"""
from functools import wraps
import json
from django.core.exceptions import RequestDataTooBig
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from rest_framework.exceptions import ValidationError
from accounts.http import error_response
from accounts.services import AccountError
from administration.permissions import granted_permissions
from administration.services import require_admin
from knowledge.http import read_query
from .access import failure


def unique_object(pairs):
    """pairs为JSON对象键值序列；拒绝重复键，保证幂等请求含义唯一。"""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('重复字段')
        result[key] = value
    return result


def reject_constant(value):
    """value为NaN/Infinity等非标准JSON输入；不允许进入审核事实。"""
    raise ValueError('非标准JSON')


def read_input(request, serializer_class):
    """request为知识管理写请求，serializer_class为实际白名单；独立256KiB上限不改变账号8KiB。"""
    try:
        if request.content_type != 'application/json' or len(request.body) > 256 * 1024:
            raise ValueError('请求过大或格式无效')
        data = json.loads(request.body, object_pairs_hook=unique_object, parse_constant=reject_constant)
        serializer = serializer_class(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data
    except (UnicodeDecodeError, RecursionError, RequestDataTooBig):
        raise ValueError('请求内容无效') from None


def endpoint(spec, permission):
    """spec为方法到输入/输出/状态的真实契约；permission=None表示任意知识或grant查看权限。"""
    def decorate(view):
        """view接收请求、可信管理员、白名单数据与路由UUID。"""
        @wraps(view)
        def wrapped(request, **kwargs):
            """request与kwargs为HTTP数据；在调用业务层前完成认证，写操作仍需业务层再次校验。"""
            if request.method not in spec:
                return error_response(request, 'METHOD_NOT_ALLOWED', '请求方法不允许', 405)
            try:
                actor = require_admin(request, permission, fresh=request.method != 'GET')
                if permission is None and not any(name.startswith('knowledge.') or name == 'grants.manage' for name in granted_permissions(actor)):
                    raise failure('ADMIN_PERMISSION_DENIED', 403)
                input_type, output_type, status = spec[request.method]
                request.account_input_serializer = input_type
                if request.method == 'GET':
                    if request.body:
                        raise ValueError
                    data = read_query(request.GET, input_type)
                else:
                    data = read_input(request, input_type)
                result = view(request, actor, data, **kwargs)
                if request.method != 'GET':
                    result, status = result
                if status == 204:
                    return HttpResponse(status=204)
                return JsonResponse(output_type(result).data, status=status)
            except AccountError as error:
                return error_response(request, error.code, error.message, error.status)
            except (ValueError, ValidationError):
                return error_response(request, 'INVALID_INPUT', '请求内容无效', 400)
        wrapped.allowed_methods, wrapped.publishing_spec = frozenset(spec), spec
        return wrapped
    return decorate


def page(query, data, payload):
    """query为已授权QuerySet，data为分页白名单，payload为单项公开转换函数。"""
    if data.get('cursor'):
        query = query.filter(pk__gt=data['cursor'])
    rows = list(query.order_by('pk')[:data['limit'] + 1])
    return {'items': [payload(row) for row in rows[:data['limit']]],
        'next_cursor': str(rows[data['limit'] - 1].pk) if len(rows) > data['limit'] else None}


def recent_page(query, data, payload):
    """query为同owner任务集，data含UUID游标；按创建时间和UUID倒序分页，确保新任务首先可见。"""
    if data.get('cursor'):
        anchor = query.filter(pk=data['cursor']).first()
        if anchor is None:
            raise ValueError('任务游标无效')
        query = query.filter(Q(created_at__lt=anchor.created_at) | Q(created_at=anchor.created_at, pk__lt=anchor.pk))
    rows = list(query.order_by('-created_at', '-pk')[:data['limit'] + 1])
    return {'items': [payload(row) for row in rows[:data['limit']]],
        'next_cursor': str(rows[data['limit'] - 1].pk) if len(rows) > data['limit'] else None}
