"""HTTP 适配层；公开响应使用明确白名单。"""
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import logout as django_logout
from django.middleware.csrf import get_token
from .http import endpoint, read_input
from .serializers import RegistrationSerializer, LoginSerializer, ProfileSerializer, PasswordSerializer, EmptySerializer, LogoutAllSerializer, public_user
from . import services
from .policies import auth_options
from .serializers import PasswordResetRequestSerializer, PasswordResetConfirmSerializer
from . import password_reset


@endpoint({"GET"})
def csrf(request):
    """request 为匿名或已登录请求；为同源写操作引导 CSRF token。"""
    return JsonResponse({"csrf_token": get_token(request)}, headers={"Cache-Control": "no-store"})


@endpoint({"GET"})
def options(request):
    """request 为匿名请求；返回现有能力与本机测试说明，禁止缓存。"""
    return JsonResponse(auth_options(), headers={"Cache-Control": "no-store"})


@endpoint({"POST"}, input_serializer=RegistrationSerializer)
def register(request):
    """request 为注册请求；校验输入并返回新账号公开字段，不自动登录。"""
    data = read_input(request)
    services.throttle(data["email"], request.META.get("REMOTE_ADDR", "unknown"), "register")
    user = services.register(data)
    return JsonResponse({"user": public_user(user)}, status=201)


@endpoint({"POST"}, input_serializer=LoginSerializer)
def login(request):
    """request 为登录请求；业务层验证并轮换服务端 cookie 会话。"""
    user = services.login(request, read_input(request))
    return JsonResponse({"user": public_user(user)})


@endpoint({"POST"}, input_serializer=EmptySerializer)
def logout(request):
    """request 为任意客户端；保持 CSRF 检查且匿名退出幂等。"""
    read_input(request)
    services.invalidate_logout_resets(request)
    django_logout(request)
    return HttpResponse(status=204)


@endpoint({"POST"}, input_serializer=LogoutAllSerializer)
def logout_all(request):
    """request 为已授权请求；撤销全部已有会话。"""
    services.logout_all(request, read_input(request))
    return HttpResponse(status=204)


@endpoint({"GET", "PATCH"}, input_serializer=ProfileSerializer)
def me(request):
    """request 为当前账号读写；修改只能进入资料白名单。"""
    user = services.require_user(request)
    if request.method == "PATCH":
        user = services.update_profile(user, read_input(request))
    return JsonResponse({"user": public_user(user)})


@endpoint({"POST"}, input_serializer=PasswordSerializer)
def password(request):
    """request 为改密请求；撤销其他会话，保留当前会话。"""
    services.change_password(request, read_input(request))
    return HttpResponse(status=204)


@endpoint({'POST'}, input_serializer=PasswordResetRequestSerializer)
def reset_request(request):
    """request为匿名同源申请；先验证通道，再进行与账号存在性无关的持久限流。"""
    data = read_input(request)
    password_reset.require_channel()
    services.throttle(data['email'], request.META.get('REMOTE_ADDR', 'unknown'), 'password-reset-request')
    return JsonResponse(password_reset.request_reset(data['email']), status=202)


@endpoint({'POST'}, input_serializer=PasswordResetConfirmSerializer)
def reset_confirm(request):
    """request为匿名同源确认；限流绑定不透明令牌HMAC及直接来源。"""
    data = read_input(request)
    services.throttle(data['token'], request.META.get('REMOTE_ADDR', 'unknown'), 'password-reset-confirm')
    password_reset.confirm_reset(data['token'], data['new_password'])
    return HttpResponse(status=204)
