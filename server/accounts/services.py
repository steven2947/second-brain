"""账号业务与事务；HTTP 层不直接实现身份变更规则。"""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login as django_login, logout as django_logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from .models import AuthThrottle, Invitation, PolicyAcceptance, User


class AccountError(Exception):
    """仅携带可公开固定错误；禁止传入凭据或底层异常消息。"""

    def __init__(self, code, message, status, retry_after=None):
        """code/message/status 为公开错误，retry_after 为可选退避秒数。"""
        self.code, self.message, self.status, self.retry_after = code, message, status, retry_after
        super().__init__(code)


def issue_invitation(email):
    """email 为受控管理端已决定邀请的地址；仅返回一次原始令牌，调用者不得日志输出。"""
    normalized = User.objects.normalize_email(email)
    User._meta.get_field("email").clean(normalized, None)
    token = secrets.token_urlsafe(32)
    Invitation.objects.create(email=normalized, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=timezone.now() + timedelta(days=7))
    return token


def register(data):
    """data 为注册 serializer 校验数据；原子消费邀请并记录真实政策接受。"""
    if settings.SB_ENV != "development":
        raise AccountError("REGISTRATION_UNAVAILABLE", "注册暂不可用", 503)
    try:
        with transaction.atomic():
            invitation = Invitation.objects.select_for_update().filter(token_hash=hashlib.sha256(data["invite_token"].encode()).hexdigest()).first()
            now = timezone.now()
            if not invitation or invitation.consumed_at or invitation.expires_at <= now or invitation.email != data["email"] or User.objects.filter(email__iexact=data["email"]).exists():
                raise AccountError("INVITATION_INVALID", "邀请无效或不可用", 409)
            user = User.objects.create_user(data["email"], data["password"], display_name=data["display_name"])
            PolicyAcceptance.objects.create(user=user, versions=data["policy_versions"])
            invitation.consumed_at = now
            invitation.save(update_fields=["consumed_at"])
            return user
    except IntegrityError as error:
        constraint = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
        if constraint not in {"accounts_user_email_key", "account_email_case_unique"}:
            raise
        raise AccountError("INVITATION_INVALID", "邀请无效或不可用", 409) from None


def throttle(email, source, action="login"):
    """email/source 为规范化身份及直接连接地址；action 隔离操作，拒绝也持久计数。"""
    now = timezone.now()
    window = settings.ACCOUNT_AUTH_WINDOW_SECONDS
    limits = [("email", User.objects.normalize_email(email), settings.ACCOUNT_LOGIN_EMAIL_LIMIT),
              ("source", source, settings.ACCOUNT_LOGIN_SOURCE_LIMIT)]
    retry_after = 0
    with transaction.atomic():
        for kind, identity, limit in limits:
            key = salted_hmac("accounts.throttle", f"{action}:{kind}:{identity}", algorithm="sha256").hexdigest()
            record, _ = AuthThrottle.objects.select_for_update().get_or_create(key=key, defaults={"window_started_at": now})
            age = (now - record.window_started_at).total_seconds()
            if age >= window:
                record.window_started_at, record.attempts, age = now, 0, 0
            record.attempts = min(record.attempts + 1, limit + 1)
            record.save(update_fields=["window_started_at", "attempts"])
            if record.attempts > limit:
                retry_after = max(retry_after, max(1, int(window - age) + 1))
    if retry_after:
        raise AccountError("RATE_LIMITED", "请求过于频繁，请稍后重试", 429, retry_after)


def login(request, data):
    """request 携带真实来源和 session；data 为明确校验的邮箱/密码。"""
    from .password_reset import invalidate_resets
    email = User.objects.normalize_email(data["email"])
    throttle(email, request.META.get("REMOTE_ADDR", "unknown"))
    user = authenticate(request, username=email, password=data["password"])
    if user is None:
        raise AccountError("INVALID_CREDENTIALS", "账号或密码不匹配或账号不可用", 401)
    with transaction.atomic():
        current = User.objects.select_for_update().get(pk=user.pk)
        if not current.is_active or current.password != user.password:
            raise AccountError("INVALID_CREDENTIALS", "账号或密码不匹配或账号不可用", 401)
        if current.is_staff or current.is_superuser:
            raise AccountError("MFA_REQUIRED", "管理员需完成多因素认证；当前暂不可登录", 403)
        previous_key = request.session.session_key
        django_login(request, current, backend="accounts.backends.AccountBackend")
        invalidate_resets(current)
        if request.session.session_key == previous_key:
            request.session.cycle_key()
    return current


def require_user(request):
    """request 为当前请求；拒绝无效/被撤销/状态不可用的服务端会话。"""
    if (not request.user.is_authenticated or not request.user.is_active
            or request.user.is_staff or request.user.is_superuser
            or request.session.get('_auth_user_backend') == 'administration.backends.AdminBackend'):
        raise AccountError("AUTH_REQUIRED", "请先登录", 401)
    return request.user


def update_identity(user_id, *, status=None, is_staff=None, is_superuser=None):
    """user_id 为受控管理目标；可选状态/权限由未来管理层鉴权后传入，当前无HTTP入口。"""
    changes = {name: value for name, value in {"status": status, "is_staff": is_staff, "is_superuser": is_superuser}.items() if value is not None}
    if any(type(value) is not bool for name, value in changes.items() if name != "status"):
        raise ValidationError("管理权限必须为布尔值")
    with transaction.atomic():
        current = User.objects.select_for_update().get(pk=user_id)
        for name, value in changes.items():
            setattr(current, name, value)
        current.full_clean()
        current.save(update_fields=[*changes, "updated_at"])
        # 表级触发器是撤销事实源；save/update/SQL均覆盖，回读后返回持久epoch。
        current.refresh_from_db()
        return current


def update_profile(user, data):
    """user 为当前授权账号；data 仅含已校验公开资料字段。"""
    with transaction.atomic():
        current = User.objects.select_for_update().get(pk=user.pk)
        for name, value in data.items():
            setattr(current, name, value)
        current.full_clean()
        current.save(update_fields=[*data, "updated_at"])
    return current


def change_password(request, data):
    """request 为已登录用户请求；data 保留密码空白并通过成熟密码验证。"""
    from .password_reset import invalidate_resets
    user = require_user(request)
    throttle(user.email, request.META.get("REMOTE_ADDR", "unknown"), "password")
    with transaction.atomic():
        current = User.objects.select_for_update().get(pk=user.pk)
        if not current.check_password(data["current_password"]):
            raise AccountError("INVALID_CREDENTIALS", "账号或密码不匹配或账号不可用", 401)
        try:
            validate_password(data["new_password"], current)
        except ValidationError:
            raise AccountError("INVALID_INPUT", "请求内容无效", 400) from None
        current.set_password(data["new_password"])
        current.auth_epoch += 1
        current.save(update_fields=["password", "auth_epoch", "updated_at"])
        invalidate_resets(current)
        # Django 只在对象等于当前 request.user 时更新本会话授权哈希。
        update_session_auth_hash(request, current)


def logout_all(request, data):
    """request 为已授权请求；data 为本人密码，再认证后撤销全部旧会话。"""
    from .password_reset import invalidate_resets
    user = require_user(request)
    throttle(user.email, request.META.get("REMOTE_ADDR", "unknown"), "logout-all")
    with transaction.atomic():
        current = User.objects.select_for_update().get(pk=user.pk)
        if not current.check_password(data["password"]):
            raise AccountError("INVALID_CREDENTIALS", "账号或密码不匹配或账号不可用", 401)
        current.auth_epoch += 1
        current.save(update_fields=["auth_epoch", "updated_at"])
        invalidate_resets(current)
    django_logout(request)


def invalidate_logout_resets(request):
    """request为退出请求；只撤销当前普通账号的找回链接，不影响其他设备会话。"""
    from .password_reset import eligible, invalidate_resets
    if not request.user.is_authenticated:
        return
    with transaction.atomic():
        current = User.objects.select_for_update().filter(pk=request.user.pk).first()
        if eligible(current):
            invalidate_resets(current)
