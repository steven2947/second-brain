"""输入只允许明确字段，密码保持用户原始语义。"""
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from .models import User, validate_timezone


class StrictSerializer(serializers.Serializer):
    """未知键和非对象输入一律拒绝，防止未来自动赋值造成越权。"""

    def to_internal_value(self, data):
        """data 为已解析 JSON；先检查白名单，再使用框架字段校验。"""
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("请求字段无效")
        return super().to_internal_value(data)


def password_min_length():
    """无参数；公开密码下限读取实际 Django 校验配置，不复制常量。"""
    return max(validator.get("OPTIONS", {}).get("min_length", 8)
               for validator in settings.AUTH_PASSWORD_VALIDATORS
               if validator["NAME"] == "django.contrib.auth.password_validation.MinimumLengthValidator")


class NewPasswordField(serializers.CharField):
    """新密码字段与实际成熟密码校验共享长度，保留首尾空白。"""

    def __init__(self, **kwargs):
        """kwargs 为 DRF 字段选项；配置下限在每次实例化时读取。"""
        super().__init__(min_length=password_min_length(), max_length=256,
                         trim_whitespace=False, write_only=True, **kwargs)


class PolicyVersionsSerializer(StrictSerializer):
    """测试政策版本必须显式逐项提交，具体版本仍由注册校验核对。"""
    terms = serializers.CharField(trim_whitespace=False)
    privacy = serializers.CharField(trim_whitespace=False)


class RegistrationSerializer(StrictSerializer):
    """邀请注册显式输入契约。"""
    invite_token = serializers.CharField(max_length=128, trim_whitespace=False)
    email = serializers.EmailField(max_length=254)
    password = NewPasswordField()
    display_name = serializers.CharField(max_length=80)
    policy_versions = PolicyVersionsSerializer()

    def validate(self, attrs):
        """attrs 为字段校验后的输入；校验精确当前测试政策和成熟密码规则。"""
        if attrs["policy_versions"] != settings.ACCOUNT_POLICY_VERSIONS:
            raise serializers.ValidationError("政策版本无效")
        attrs["email"] = User.objects.normalize_email(attrs["email"])
        candidate = User(email=attrs["email"], display_name=attrs["display_name"])
        try:
            validate_password(attrs["password"], candidate)
        except DjangoValidationError:
            raise serializers.ValidationError("密码不符合要求") from None
        return attrs


class LoginSerializer(StrictSerializer):
    """登录只接受邮箱和未裁剪密码。"""
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=256, trim_whitespace=False, write_only=True)


class ProfileSerializer(StrictSerializer):
    """资料更新只允许昵称、时区和主题。"""
    display_name = serializers.CharField(max_length=80, required=False)
    timezone = serializers.CharField(max_length=64, required=False, validators=[validate_timezone])
    theme = serializers.ChoiceField(choices=["system", "light", "dark"], required=False)


class PasswordSerializer(StrictSerializer):
    """改密只接受原始旧密码和新密码；强度在服务层结合当前用户判断。"""
    current_password = serializers.CharField(max_length=256, trim_whitespace=False, write_only=True)
    new_password = NewPasswordField()


class PasswordResetRequestSerializer(StrictSerializer):
    """匿名找回申请只接受邮箱；不能指定接收人以外的邮件内容或来源。"""
    email = serializers.EmailField(max_length=254)


class PasswordResetConfirmSerializer(StrictSerializer):
    """匿名确认只接受不透明令牌与新密码，字段均不用于响应。"""
    token = serializers.CharField(max_length=512, trim_whitespace=False, write_only=True)
    new_password = NewPasswordField()


class PasswordResetAcceptedSerializer(StrictSerializer):
    """接收结果不表示发送完成，也不公开账号存在性。"""
    status = serializers.ChoiceField(choices=['accepted'])
    delivery = serializers.ChoiceField(choices=['local_capture', 'smtp'])


class EmptySerializer(StrictSerializer):
    """退出操作不接受客户端身份或额外参数。"""


class LogoutAllSerializer(StrictSerializer):
    """全退出必须再次提供本人密码，保留首尾空白语义。"""
    password = serializers.CharField(max_length=256, trim_whitespace=False, write_only=True)


class PublicUserSerializer(StrictSerializer):
    """公开用户唯一字段源；日期保留原对象，沿用 JsonResponse 的时间编码。"""
    id = serializers.UUIDField()
    email = serializers.EmailField(max_length=User._meta.get_field("email").max_length)
    display_name = serializers.CharField(max_length=User._meta.get_field("display_name").max_length)
    timezone = serializers.CharField(max_length=User._meta.get_field("timezone").max_length)
    theme = serializers.ChoiceField(choices=["system", "light", "dark"])
    email_verified_at = serializers.DateTimeField(format=None, allow_null=True)
    created_at = serializers.DateTimeField(format=None)


class UserResponseSerializer(StrictSerializer):
    """注册、登录和个人资料成功响应。"""
    user = PublicUserSerializer()


class CsrfResponseSerializer(StrictSerializer):
    """同源写请求的 CSRF 引导返回。"""
    csrf_token = serializers.CharField()


class ErrorDetailSerializer(StrictSerializer):
    """只公开固定错误与请求追踪，不包含输入或内部异常。"""
    code = serializers.CharField()
    message = serializers.CharField()
    request_id = serializers.UUIDField()


class ErrorResponseSerializer(StrictSerializer):
    """所有账号 API 错误使用嵌套外壳。"""
    error = ErrorDetailSerializer()


class TestPolicySerializer(StrictSerializer):
    """本机测试说明，不能充当已审核运营政策。"""
    kind = serializers.ChoiceField(choices=["terms", "privacy"])
    version = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField()
    test_only = serializers.BooleanField()


class RegistrationOptionsSerializer(StrictSerializer):
    """注册可用性及本次可接受的政策版本。"""
    enabled = serializers.BooleanField()
    invitation_required = serializers.BooleanField()
    policy_versions = PolicyVersionsSerializer()
    policies = TestPolicySerializer(many=True)


class PasswordOptionsSerializer(StrictSerializer):
    """实际新密码字段的长度边界。"""
    min_length = serializers.IntegerField()
    max_length = serializers.IntegerField()


class AvailabilitySerializer(StrictSerializer):
    """只表达现有能力是否可用，不承诺未来实现。"""
    available = serializers.BooleanField()


class PasswordResetOptionsSerializer(StrictSerializer):
    """找回能力明确区分关闭、本机捕获和SMTP。"""
    available = serializers.BooleanField()
    delivery = serializers.ChoiceField(choices=['disabled', 'local_capture', 'smtp'])
    token_ttl_seconds = serializers.IntegerField(min_value=1800, max_value=1800)


class AuthOptionsSerializer(StrictSerializer):
    """匿名能力响应的公开白名单。"""
    registration = RegistrationOptionsSerializer()
    password = PasswordOptionsSerializer()
    password_reset = PasswordResetOptionsSerializer()
    admin_mfa = AvailabilitySerializer()


def public_user(user):
    """user 为账号模型；仅序列化公开个人信息，不含密码/权限/内部修订。"""
    return PublicUserSerializer(user).data
