"""账号事实模型；不承载知识数据或租户隔离承诺。"""
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.utils.crypto import salted_hmac


def validate_timezone(value):
    """value 为用户时区名称；仅接受系统可解析的 IANA 时区。"""
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationError("时区无效") from None


class UserManager(BaseUserManager):
    """统一规范化邮箱与成熟密码哈希。"""

    @classmethod
    def normalize_email(cls, email):
        """email 为邮箱输入；整个地址去首尾空白并转小写。"""
        return super().normalize_email(email).lower()

    def create_user(self, email, password=None, **extra_fields):
        """email/password 为凭据；extra_fields 为受控服务端字段。"""
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        # 字段校验保留；唯一性和跨字段约束由数据库原子判定，避免并发预检变成另一种异常。
        user.full_clean(validate_unique=False, validate_constraints=False)
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    """UUID 账号；状态和 epoch 每次会话读取时重新核对。"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=254, unique=True)
    display_name = models.CharField(max_length=80)
    status = models.CharField(max_length=20, default="active", choices=[(v, v) for v in ("active", "disabled", "deletion_pending")])
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    timezone = models.CharField(max_length=64, default="Asia/Shanghai", validators=[validate_timezone])
    theme = models.CharField(max_length=10, default="system", choices=[(v, v) for v in ("system", "light", "dark")])
    auth_epoch = models.PositiveBigIntegerField(default=0)
    access_revision = models.PositiveBigIntegerField(default=0)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    deletion_requested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="account_email_case_unique"),
            models.CheckConstraint(condition=models.Q(status__in=["active", "disabled", "deletion_pending"]), name="account_status_valid"),
            models.CheckConstraint(condition=models.Q(theme__in=["system", "light", "dark"]), name="account_theme_valid"),
        ]

    @property
    def is_active(self):
        """无参数；Django 认证只允许当前 active 状态。"""
        return self.status == "active"

    def _get_session_auth_hash(self, secret=None):
        """secret 为 Django 可选轮换密钥；密码或 epoch 改变均撤销旧会话。"""
        return salted_hmac("accounts.User.session", f"{self.password}:{self.auth_epoch}", secret=secret, algorithm="sha256").hexdigest()


class Invitation(models.Model):
    """服务端受控签发的七日单次邀请；仅保存随机令牌摘要。"""
    token_hash = models.CharField(max_length=64, unique=True)
    email = models.EmailField(max_length=254)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True)


class PolicyAcceptance(models.Model):
    """账号实际接受的本机测试版本；不表示法律审核完成。"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    versions = models.JSONField()
    accepted_at = models.DateTimeField(auto_now_add=True)


class AuthThrottle(models.Model):
    """持久认证尝试窗口；身份仅以服务端 HMAC 保存。"""
    key = models.CharField(max_length=64, primary_key=True)
    window_started_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)


class PasswordResetDelivery(models.Model):
    """仅普通找回的持久待发队列；不保存邮箱、正文或明文令牌。"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    binding = models.CharField(max_length=64)
    delivery = models.CharField(max_length=16, choices=[(v, v) for v in ('local_capture', 'smtp')])
    status = models.CharField(max_length=16, default='queued', choices=[(v, v) for v in ('queued', 'running', 'sent', 'failed', 'cancelled', 'consumed')])
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    lease_token = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'status', 'available_at'], name='reset_delivery_pending')]
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=['queued', 'running', 'sent', 'failed', 'cancelled', 'consumed']), name='reset_delivery_status_valid'),
            models.CheckConstraint(condition=models.Q(delivery__in=['local_capture', 'smtp']), name='reset_delivery_channel_valid'),
            models.CheckConstraint(condition=models.Q(attempts__lte=3), name='reset_delivery_attempts_bounded'),
        ]
