"""后台认证路由复用全站 CSRF 与固定安全错误外壳。"""
from django.http import JsonResponse, HttpResponse
from accounts.http import endpoint, read_input
from accounts.serializers import EmptySerializer
from .serializers import AdminLoginSerializer, AdminReauthSerializer, AdminIdentitySerializer
from . import services


@endpoint({'POST'}, input_serializer=AdminLoginSerializer)
def login(request):
    """校验管理员登录白名单，返回已完成双因素的身份。"""
    return JsonResponse(AdminIdentitySerializer(services.login(request, read_input(request))).data)


@endpoint({'GET'})
def me(request):
    """读取每请求重新核验的后台身份和明确权限。"""
    return JsonResponse(AdminIdentitySerializer(services.identity(request)).data)


@endpoint({'POST'}, input_serializer=AdminReauthSerializer)
def reauth(request):
    """校验本人密码及第二因素后返回新的再次认证窗口。"""
    return JsonResponse(AdminIdentitySerializer(services.reauthenticate(request, read_input(request))).data)


@endpoint({'POST'}, input_serializer=EmptySerializer)
def logout(request):
    """保持全局 CSRF 保护，审计并退出当前后台会话。"""
    read_input(request)
    services.logout(request)
    return HttpResponse(status=204)
