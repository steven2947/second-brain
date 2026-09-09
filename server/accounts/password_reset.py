"""普通账号找回业务；成熟Django令牌、身份锁、单次消费和私有捕获。"""
import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import PasswordResetDelivery, User
from .services import AccountError


class ResetTokenGenerator(PasswordResetTokenGenerator):
    """复用Django哈希/时间/轮换密钥校验，并纳入永久身份撤销和精确登录时间。"""

    def __init__(self, job_id):
        """job_id为持久任务UUID；Django密钥域绑定任务，防止跨任务替换ID。"""
        super().__init__()
        self.key_salt = f'accounts.password-reset.v1.{job_id}'

    def _make_hash_value(self, user, timestamp):
        """user为当前持锁账号；timestamp为Django令牌时间戳。"""
        return super()._make_hash_value(user, timestamp) + f':{user.auth_epoch}:{user.last_login}'


def eligible(user):
    """user为当前数据库账号；普通active且有可用密码才可找回。"""
    return user is not None and user.is_active and not user.is_staff and not user.is_superuser and user.has_usable_password()


def identity_binding(user):
    """user为申请时或发送时账号；仅持久保存HMAC而非密码哈希或邮箱副本。"""
    return salted_hmac('accounts.password-reset.binding.v1',
        f'{user.pk}:{user.email}:{user.password}:{user.auth_epoch}:{user.last_login}', algorithm='sha256').hexdigest()


def capture_directory(user_id=None, *, create=False):
    """user_id为服务端UUID；create仅供受控请求/worker，拒绝符号链接及公共目录。"""
    root = Path(settings.SB_PRIVATE_DATA_ROOT)
    if (not root.is_absolute() or root.is_symlink() or root.resolve() == Path('/')
            or any(part.lower() in {'web', 'public', 'static'} for part in root.resolve().parts)):
        raise ValueError('捕获目录无效')
    directory = root / 'password-reset'
    paths = [root, directory]
    if user_id is not None:
        directory = directory / str(UUID(str(user_id)))
        paths.append(directory)
    for path in paths:
        if path.is_symlink():
            raise ValueError('捕获目录无效')
        if create:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.exists() and (not path.is_dir() or path.stat().st_mode & 0o077):
            raise ValueError('捕获目录必须仅属主可访问')
    return directory


def configured_channel():
    """无参数；只读取显式运行配置，不探测SMTP、不读取其他工具凭据。"""
    mode = settings.SB_MAIL_MODE
    if mode == 'local_capture' and settings.SB_ENV == 'development':
        return mode
    if (mode == 'smtp' and all(getattr(settings, name, None) for name in
            ('EMAIL_HOST', 'EMAIL_PORT', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD', 'DEFAULT_FROM_EMAIL'))
            and settings.EMAIL_USE_TLS != settings.EMAIL_USE_SSL
            and isinstance(settings.EMAIL_TIMEOUT, (int, float)) and 1 <= settings.EMAIL_TIMEOUT <= 10):
        return mode
    return 'disabled'


def reset_options():
    """无参数；匿名能力只公开通道模式与固定有效期。"""
    mode = configured_channel()
    return {'available': mode != 'disabled', 'delivery': mode, 'token_ttl_seconds': 1800}


def require_channel():
    """无参数；在查询邮箱之前验证本机捕获可用性，配置失败使用统一503。"""
    mode = configured_channel()
    try:
        if mode == 'disabled':
            raise ValueError('disabled')
        if mode == 'local_capture':
            capture_directory(create=True)
    except (OSError, ValueError):
        raise AccountError('CHANNEL_UNAVAILABLE', '密码找回暂不可用', 503) from None
    return mode


def request_reset(email):
    """email为已校验邮箱；匿名请求只排队，所有合法地址均返回相同接收结果。"""
    mode = require_channel()
    with transaction.atomic():
        # 申请只读取MVCC快照；发送时复验绑定，避免申请等待SMTP发送所持的身份锁。
        user = User.objects.filter(email__iexact=User.objects.normalize_email(email)).first()
        if eligible(user):
            now = timezone.now()
            PasswordResetDelivery.objects.create(user=user, binding=identity_binding(user), delivery=mode,
                available_at=now, expires_at=now + timedelta(seconds=1800))
    return {'status': 'accepted', 'delivery': mode}


def invalid_reset():
    """无参数；所有不存在、过期、撤销和篡改令牌共享固定公开错误。"""
    return AccountError('RESET_INVALID', '重置链接无效或已过期，请重新申请', 400)


def remove_capture(user_id, job_id):
    """user_id/job_id为数据库精确目标；只清除此任务固定命名的私有捕获。"""
    path = capture_directory(user_id) / (str(UUID(str(job_id))) + '.json')
    if path.is_symlink():
        raise ValueError('捕获文件不可为符号链接')
    path.unlink(missing_ok=True)


def invalidate_resets(user):
    """user须由调用者持身份锁；退出或注销时撤销旧链接及旧发送租约。"""
    rows = list(PasswordResetDelivery.objects.filter(user=user))
    for row in rows:
        if row.delivery == 'local_capture':
            remove_capture(user.pk, row.pk)
    PasswordResetDelivery.objects.filter(user=user).update(status='cancelled', binding='', lease_token=None, lease_until=None)


def confirm_reset(token, new_password):
    """token为不持久化的邮件片段；new_password只进入Django校验与哈希，不自动登录。"""
    try:
        identifier, value = token.split('.', 1)
        identifier = UUID(hex=identifier)
    except (ValueError, AttributeError):
        raise invalid_reset() from None
    owner = PasswordResetDelivery.objects.filter(pk=identifier).values_list('user_id', flat=True).first()
    if owner is None:
        raise invalid_reset()
    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=owner).first()
        row = PasswordResetDelivery.objects.select_for_update().filter(pk=identifier, user_id=owner).first()
        if (not eligible(user) or row is None or row.status != 'sent' or row.expires_at <= timezone.now()
                or not constant_time_compare(row.binding, identity_binding(user)) or not ResetTokenGenerator(row.pk).check_token(user, value)):
            raise invalid_reset()
        try:
            validate_password(new_password, user)
        except ValidationError:
            raise AccountError('INVALID_INPUT', '请求内容无效', 400) from None
        user.set_password(new_password)
        user.auth_epoch += 1
        user.save(update_fields=['password', 'auth_epoch', 'updated_at'])
        invalidate_resets(user)
        row.status, row.binding = 'consumed', ''
        row.lease_token, row.lease_until = None, None
        row.save(update_fields=['status', 'binding', 'lease_token', 'lease_until'])


def write_capture(row, email, subject, body):
    """row为已锁发送任务；email/subject/body只写私有0600文件，不打印链接。"""
    directory = capture_directory(row.user_id, create=True)
    path = directory / (str(row.pk) + '.json')
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump({'to': email, 'subject': subject, 'body': body, 'expires_at': row.expires_at.isoformat()}, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
