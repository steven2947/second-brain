"""仅为现有账号路由导出 OpenAPI 3.1；请求字段直接取实际端点 serializer。"""
import json

from django.conf import settings
from django.urls import resolve, reverse
from rest_framework import serializers

from . import serializers as account


INPUT_SCHEMAS = {
    account.PasswordResetRequestSerializer: 'PasswordResetRequestInput',
    account.PasswordResetConfirmSerializer: 'PasswordResetConfirmInput',
    account.LoginSerializer: "LoginInput",
    account.RegistrationSerializer: "RegistrationInput",
    account.ProfileSerializer: "ProfileInput",
    account.PasswordSerializer: "PasswordInput",
    account.LogoutAllSerializer: "LogoutAllInput",
    account.EmptySerializer: "EmptyInput",
}
RESPONSE_SCHEMAS = {
    account.PasswordResetAcceptedSerializer: 'PasswordResetAccepted',
    account.PublicUserSerializer: "PublicUser",
    account.AuthOptionsSerializer: "AuthOptions",
    account.CsrfResponseSerializer: "CsrfResponse",
    account.UserResponseSerializer: "UserResponse",
    account.ErrorResponseSerializer: "ErrorResponse",
    account.PolicyVersionsSerializer: "PolicyVersions",
    account.TestPolicySerializer: "TestPolicy",
}
SCHEMAS = {**INPUT_SCHEMAS, **RESPONSE_SCHEMAS}

# 路由名称和稳定操作 ID 是公开接口命名；URL、允许方法及请求字段来自实际 view。
OPERATIONS = (
    ('auth-reset-request', 'POST', 'requestPasswordReset', None, 'PasswordResetAccepted', 202),
    ('auth-reset-confirm', 'POST', 'confirmPasswordReset', None, None, 204),
    ("auth-options", "GET", "getAuthOptions", None, "AuthOptions", 200),
    ("auth-csrf", "GET", "getCsrfToken", None, "CsrfResponse", 200),
    ("auth-register", "POST", "register", None, "UserResponse", 201),
    ("auth-login", "POST", "login", None, "UserResponse", 200),
    ("auth-logout", "POST", "logout", None, None, 204),
    ("auth-logout-all", "POST", "logoutAll", "SessionCookie", None, 204),
    ("account-me", "GET", "getMe", "SessionCookie", "UserResponse", 200),
    ("account-me", "PATCH", "updateMe", "SessionCookie", "UserResponse", 200),
    ("account-password", "POST", "changePassword", "SessionCookie", None, 204),
)


def reference(name):
    """name 为本文件登记的 schema 名；返回组件引用。"""
    return {"$ref": f"#/components/schemas/{name}"}


def field_schema(field):
    """field 为当前账号 DRF 字段；仅支持已使用字段，未知类型直接报错。"""
    if isinstance(field, serializers.ListSerializer):
        result = {"type": "array", "items": field_schema(field.child)}
    elif isinstance(field, serializers.Serializer):
        result = reference(SCHEMAS[type(field)]) if type(field) in SCHEMAS else serializer_schema(field)
    elif isinstance(field, serializers.ChoiceField):
        result = {"type": "string", "enum": list(field.choices)}
    elif isinstance(field, serializers.BooleanField):
        result = {"type": "boolean"}
    elif isinstance(field, serializers.IntegerField):
        result = {"type": "integer"}
        for attribute, keyword in (("min_value", "minimum"), ("max_value", "maximum")):
            value = getattr(field, attribute, None)
            if value is not None:
                result[keyword] = value
    elif isinstance(field, (serializers.CharField, serializers.UUIDField, serializers.DateTimeField)):
        result = {"type": "string"}
        if isinstance(field, serializers.EmailField):
            result["format"] = "email"
        elif isinstance(field, serializers.UUIDField):
            result["format"] = "uuid"
        elif isinstance(field, serializers.DateTimeField):
            result["format"] = "date-time"
        if isinstance(field, serializers.CharField):
            minimum = field.min_length
            if not field.allow_blank:
                minimum = max(minimum or 0, 1)
            if minimum is not None:
                result["minLength"] = minimum
            if field.max_length is not None:
                result["maxLength"] = field.max_length
    else:
        raise TypeError(f"账号契约未支持字段类型：{type(field).__name__}")
    if field.allow_null:
        if "enum" in result:
            result["enum"].append(None)
        if "type" in result:
            result["type"] = [result["type"], "null"]
        else:
            result = {"anyOf": [result, {"type": "null"}]}
    if field.write_only:
        result["writeOnly"] = True
    if field.read_only:
        result["readOnly"] = True
    return result


def serializer_schema(serializer):
    """serializer 为实际严格对象实例；保留必填、上限和禁止未知键语义。"""
    result = {"type": "object", "additionalProperties": False,
              "properties": {name: field_schema(field) for name, field in serializer.fields.items()}}
    required = [name for name, field in serializer.fields.items() if field.required]
    if required:
        result["required"] = required
    return result


def build_contract():
    """无参数；只输出账号已实现能力，不读取数据库或加入机器、模型配置。"""
    paths = {}
    for route, method, operation_id, security, response_name, status in OPERATIONS:
        path = reverse(route)
        view = resolve(path).func
        if method not in view.allowed_methods:
            raise ValueError("账号契约引用了未实现的方法")
        success = {"description": "成功；响应禁止缓存"}
        if response_name:
            success["content"] = {"application/json": {"schema": reference(response_name)}}
        operation = {
            "operationId": operation_id,
            "security": [{security: []}] if security else [],
            "responses": {
                str(status): success,
                "default": {"description": "请求失败；固定公开错误及请求追踪，响应禁止缓存",
                            "content": {"application/json": {"schema": reference("ErrorResponse")}}},
            },
        }
        if method in {"POST", "PATCH"}:
            operation["parameters"] = [{"$ref": "#/components/parameters/CsrfHeader"}]
            operation["requestBody"] = {
                "required": view.input_serializer is not account.EmptySerializer,
                "content": {"application/json": {"schema": reference(INPUT_SCHEMAS[view.input_serializer])}},
            }
        paths.setdefault(path, {})[method.lower()] = operation
    return {
        "openapi": "3.1.0",
        "info": {"title": "第二大脑账号接口", "version": "0.1.0",
                 "description": "本段仅包含已实现账号接口。测试政策不代表法律审核；邮件、MFA、模型和知识授权不在此接缝内。"},
        "paths": paths,
        "components": {
            "securitySchemes": {"SessionCookie": {"type": "apiKey", "in": "cookie", "name": settings.SESSION_COOKIE_NAME}},
            "parameters": {"CsrfHeader": {"name": "X-CSRFToken", "in": "header", "required": True,
                                          "description": "先同源 GET /api/v1/auth/csrf 取得 token，并在写操作随会话及 CSRF Cookie 发送。",
                                          "schema": {"type": "string", "minLength": 1}}},
            "schemas": {name: serializer_schema(serializer()) for serializer, name in SCHEMAS.items()},
        },
    }


def contract_text():
    """无参数；稳定排序和末尾换行确保可复算、可检查漂移。"""
    return json.dumps(build_contract(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
