"""统一私有 API 错误、请求追踪和大小限制；不记录身份输入。"""
import json
import uuid
from functools import wraps

from django.http import JsonResponse
from django.core.exceptions import RequestDataTooBig
from rest_framework.exceptions import ValidationError
from .services import AccountError


def error_response(request, code, message, status):
    """request 为 HTTP 请求；其余参数为服务端固定公开错误内容。"""
    return JsonResponse({"error": {"code": code, "message": message, "request_id": getattr(request, "account_request_id", str(uuid.uuid4()))}}, status=status, headers={"Cache-Control": "no-store"})


def csrf_failure(request, reason=""):
    """request 为被拒请求；reason 可能含内部来源信息，永不回显。"""
    return error_response(request, "CSRF_FAILED", "请求校验失败", 403)


class PrivateAPIMiddleware:
    """所有 API 响应禁缓存，统一中间件级错误外壳。"""

    def __init__(self, get_response):
        """get_response 为 Django 下游处理函数。"""
        self.get_response = get_response

    def __call__(self, request):
        """request 为入站 HTTP 请求；追踪 ID 完全由服务端产生。"""
        request.account_request_id = str(uuid.uuid4())
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            if response.status_code >= 400 and not response.get("Content-Type", "").startswith("application/json"):
                code, message = {404: ("NOT_FOUND", "资源不存在"), 405: ("METHOD_NOT_ALLOWED", "请求方法不允许")}.get(response.status_code, ("REQUEST_FAILED", "请求未完成"))
                converted = error_response(request, code, message, response.status_code)
                if response.has_header("Allow"):
                    converted["Allow"] = response["Allow"]
                response = converted
            response["Cache-Control"] = "no-store"
            response["X-Request-ID"] = request.account_request_id
        return response


def endpoint(methods, input_serializer=None):
    """methods 为允许方法，input_serializer 为实际请求事实源；保留全局 CSRF。"""
    def decorate(view):
        """view 为待包装的 HTTP 适配函数。"""
        @wraps(view)
        def wrapped(request):
            """request 为当前请求；仅将已知安全错误转为 JSON。"""
            if request.method not in methods:
                response = error_response(request, "METHOD_NOT_ALLOWED", "请求方法不允许", 405)
                response["Allow"] = ", ".join(sorted(methods))
                return response
            try:
                request.account_input_serializer = input_serializer
                return view(request)
            except (ValidationError, ValueError, RequestDataTooBig):
                return error_response(request, "INVALID_INPUT", "请求内容无效", 400)
            except AccountError as error:
                response = error_response(request, error.code, error.message, error.status)
                if error.retry_after is not None:
                    response["Retry-After"] = str(error.retry_after)
                return response
        wrapped.allowed_methods = frozenset(methods)
        wrapped.input_serializer = input_serializer
        return wrapped
    return decorate


def read_input(request, serializer_class=None):
    """request 为 JSON 请求；未传 serializer_class 时使用实际端点绑定的白名单。"""
    from .serializers import EmptySerializer
    serializer_class = serializer_class or request.account_input_serializer
    if serializer_class is EmptySerializer and not request.body:
        return {}
    if request.content_type != "application/json" or len(request.body) > 8192:
        raise ValueError("请求内容无效")
    serializer = serializer_class(data=json.loads(request.body))
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data
