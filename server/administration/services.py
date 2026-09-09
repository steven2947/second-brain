"""后台会话必须同时满足密码、当前设备、epoch、绝对期限及显式权限。"""
from datetime import datetime, timedelta, timezone as datetime_timezone
from django.contrib.auth import BACKEND_SESSION_KEY, login as django_login, logout as django_logout
from django.utils import timezone
from access.context import owner_transaction
from accounts.models import User
from accounts.services import AccountError, throttle
from .backends import AdminBackend
from .credentials import verify_device
from .models import AdministratorDevice, AdminAudit
from .permissions import granted_permissions

BACKEND = 'administration.backends.AdminBackend'
SESSION_KEY = 'administrator_mfa'
SESSION_SECONDS = 8 * 60 * 60
FRESH_SECONDS = 5 * 60


def denied(code='ADMIN_AUTH_REQUIRED', status=401):
    """只创建固定错误，不将输入凭据拼入响应或异常。"""
    return AccountError(code, {
        'ADMIN_AUTH_REQUIRED': '请完成管理员多因素登录',
        'ADMIN_PERMISSION_DENIED': '没有此项管理权限',
        'ADMIN_REAUTH_REQUIRED': '请再次验证密码和第二因素',
        'INVALID_CREDENTIALS': '管理员凭据无效或账号不可用',
    }[code], status)


def audit(user, action, request=None):
    """追加固定操作码、服务端身份 UUID 与请求编号，不采集业务内容。"""
    AdminAudit.objects.create(actor_id=user.pk, action=action,
        request_id=getattr(request, 'account_request_id', None))


def require_admin(request, permission=None, fresh=False):
    """每次重新核验身份/设备/epoch和真实授权；供后续真实管理操作直接使用。"""
    if not request.user.is_authenticated or request.session.get(BACKEND_SESSION_KEY) != BACKEND:
        raise denied()
    user = User.objects.filter(pk=request.user.pk).first()
    state = request.session.get(SESSION_KEY)
    now = timezone.now().timestamp()
    if not user or not user.is_active or not user.is_staff or not isinstance(state, dict):
        raise denied()
    try:
        if (state['epoch'] != user.auth_epoch or now >= state['expires_at']
                or state['verified_at'] > now or state['expires_at'] - state['started_at'] != SESSION_SECONDS
                or state['verified_at'] < state['started_at']):
            raise denied()
        with owner_transaction(user.pk):
            device = AdministratorDevice.objects.filter(pk=state['device_id'], owner=user,
                confirmed_at__isnull=False, revoked_at__isnull=True).first()
    except (KeyError, TypeError, ValueError):
        raise denied() from None
    if not device:
        raise denied()
    if permission is not None and permission not in granted_permissions(user):
        raise denied('ADMIN_PERMISSION_DENIED', 403)
    if fresh and now >= state['verified_at'] + FRESH_SECONDS:
        raise denied('ADMIN_REAUTH_REQUIRED', 403)
    return user


def identity(request, user=None):
    """输出最小管理员身份、明确授权和服务端会话期限。"""
    user = user or require_admin(request)
    state = request.session[SESSION_KEY]
    instant = lambda value: datetime.fromtimestamp(value, tz=datetime_timezone.utc)
    return {'user': {'id': user.pk, 'email': user.email, 'display_name': user.display_name},
        'granted_permissions': granted_permissions(user), 'verified_at': instant(state['verified_at']),
        'fresh_until': instant(min(state['verified_at'] + FRESH_SECONDS, state['expires_at'])),
        'session_expires_at': instant(state['expires_at'])}


def login(request, data):
    """密码和第二因素全部通过后才建立会话；失败计数独立提交。"""
    email = User.objects.normalize_email(data['email'])
    throttle(email, request.META.get('REMOTE_ADDR', 'unknown'), 'admin-login')
    user = AdminBackend().authenticate(request, username=email, password=data['password'], admin_login=True)
    if user is None:
        raise denied('INVALID_CREDENTIALS')
    valid = False
    # 已由密码识别的 UUID 才进入 owner 上下文；先提交失败计数，再在事务外返回统一错误。
    with owner_transaction(user.pk):
        current = User.objects.select_for_update().get(pk=user.pk)
        device = AdministratorDevice.objects.select_for_update().filter(owner=current).first()
        if current.is_active and current.is_staff and current.password == user.password and device:
            valid = verify_device(device, data['token'], data['method'])
        if valid:
            previous_key = request.session.session_key
            django_login(request, current, backend=BACKEND)
            if request.session.session_key == previous_key:
                request.session.cycle_key()
            now = timezone.now().timestamp()
            request.session[SESSION_KEY] = {'device_id': str(device.pk), 'epoch': current.auth_epoch,
                'started_at': now, 'verified_at': now, 'expires_at': now + SESSION_SECONDS}
            request.session.set_expiry(datetime.fromtimestamp(now + SESSION_SECONDS, tz=datetime_timezone.utc))
            audit(current, 'admin.login', request)
    if not valid:
        raise denied('INVALID_CREDENTIALS')
    return identity(request, current)


def reauthenticate(request, data):
    """重新核对同一账号密码及第二因素，更新五分钟窗口但不延长绝对期限。"""
    user = require_admin(request)
    throttle(user.email, request.META.get('REMOTE_ADDR', 'unknown'), 'admin-reauth')
    valid = False
    with owner_transaction(user.pk):
        current = User.objects.select_for_update().get(pk=user.pk)
        device = AdministratorDevice.objects.select_for_update().filter(
            pk=request.session[SESSION_KEY]['device_id'], owner=current).first()
        if (current.is_active and current.is_staff and current.auth_epoch == request.session[SESSION_KEY]['epoch']
                and current.check_password(data['password']) and device):
            valid = verify_device(device, data['token'], data['method'])
        if valid:
            state = {**request.session[SESSION_KEY], 'verified_at': timezone.now().timestamp()}
            request.session[SESSION_KEY] = state
            request.session.cycle_key()
            audit(current, 'admin.reauth', request)
    if not valid:
        raise denied('INVALID_CREDENTIALS')
    return identity(request, current)


def logout(request):
    """先追加管理员退出审计，再销毁服务端会话和浏览器 cookie。"""
    user = require_admin(request)
    audit(user, 'admin.logout', request)
    django_logout(request)
