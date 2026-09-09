"""无数据库验证匿名能力、公开字段以及可复算的账号接缝。"""
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from django.conf import settings
from django.core.management import call_command, CommandError
from django.http import JsonResponse
from django.test import SimpleTestCase, override_settings
from django.urls import get_resolver, resolve
from django.utils import timezone


def assert_contract_value(test, value, schema, schemas):
    """test 为断言对象；递归核对真实 JSON 值与本段 schema 的字段、类型及格式。"""
    if "$ref" in schema:
        schema = schemas[schema["$ref"].rsplit("/", 1)[-1]]
    types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    if value is None:
        test.assertIn("null", types)
        return
    if "object" in types:
        test.assertIsInstance(value, dict)
        test.assertIs(schema["additionalProperties"], False)
        test.assertLessEqual(set(value), set(schema["properties"]))
        test.assertLessEqual(set(schema.get("required", [])), set(value))
        for key, item in value.items():
            assert_contract_value(test, item, schema["properties"][key], schemas)
    elif "array" in types:
        test.assertIsInstance(value, list)
        for item in value:
            assert_contract_value(test, item, schema["items"], schemas)
    elif "string" in types:
        test.assertIsInstance(value, str)
        test.assertGreaterEqual(len(value), schema.get("minLength", 0))
        test.assertLessEqual(len(value), schema.get("maxLength", len(value)))
        if schema.get("format") == "uuid":
            test.assertEqual(str(UUID(value)), value)
        elif schema.get("format") == "date-time":
            from django.utils.dateparse import parse_datetime
            test.assertIsNotNone(parse_datetime(value))
        elif schema.get("format") == "email":
            from django.core.validators import validate_email
            validate_email(value)
        if "enum" in schema:
            test.assertIn(value, schema["enum"])
    elif "boolean" in types:
        test.assertIs(type(value), bool)
    elif "integer" in types:
        test.assertIs(type(value), int)
    else:
        test.fail("测试未覆盖的 schema 类型")


class AuthOptionsTests(SimpleTestCase):
    """匿名能力仅公开白名单和真实测试政策。"""

    def test_anonymous_options_and_policy_text_are_consistent(self):
        """无参数；匿名读取不访问数据库，版本与正文同源且禁缓存。"""
        response = self.client.get("/api/v1/auth/options")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        data = response.json()
        self.assertEqual(set(data), {"registration", "password", "password_reset", "admin_mfa"})
        self.assertEqual(data["password"], {"min_length": 12, "max_length": 256})
        self.assertEqual(data["password_reset"], {"available": False, "delivery": "disabled", "token_ttl_seconds": 1800})
        self.assertEqual(data["admin_mfa"], {"available": True})
        registration = data["registration"]
        self.assertEqual(set(registration), {"enabled", "invitation_required", "policy_versions", "policies"})
        self.assertIs(registration["enabled"], True)
        self.assertIs(registration["invitation_required"], True)
        self.assertEqual(registration["policy_versions"], settings.ACCOUNT_POLICY_VERSIONS)
        self.assertEqual({item["kind"] for item in registration["policies"]}, {"terms", "privacy"})
        for policy in registration["policies"]:
            self.assertEqual(set(policy), {"kind", "version", "title", "body", "test_only"})
            self.assertEqual(policy["version"], registration["policy_versions"][policy["kind"]])
            self.assertIs(policy["test_only"], True)
        text = "\n".join(item["body"] for item in registration["policies"])
        for phrase in ("本机功能测试", "邮箱", "昵称", "密码哈希", "数据库", "邮件验证", "密码找回", "模型尚未接通", "敏感资料", "负责人审核", "法律审核"):
            self.assertIn(phrase, text)

    @override_settings(ACCOUNT_POLICY_VERSIONS={"terms": "test-next", "privacy": "test-new"})
    def test_versions_are_not_cached_or_hardcoded_in_response(self):
        """无参数；版本修改反映到说明和提交版本，客户端不能沿用旧同意。"""
        response = self.client.get("/api/v1/auth/options")
        self.assertEqual(response.status_code, 200)
        registration = response.json()["registration"]
        self.assertEqual(registration["policy_versions"], settings.ACCOUNT_POLICY_VERSIONS)
        self.assertEqual({p["kind"]: p["version"] for p in registration["policies"]}, settings.ACCOUNT_POLICY_VERSIONS)

    @override_settings(SB_ENV="production", SECRET_KEY="not-for-public-output", SB_MODEL_API_KEY="not-for-public-output")
    def test_production_registration_is_disabled_without_sensitive_settings(self):
        """无参数；生产能力明确关闭，不回显环境、路径或秘密配置。"""
        response = self.client.get("/api/v1/auth/options")
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["registration"]["enabled"], False)
        self.assertNotIn("not-for-public-output", response.content.decode())
        self.assertNotIn("/Users/", response.content.decode())
        self.assertEqual(response["Cache-Control"], "no-store")

    @override_settings(AUTH_PASSWORD_VALIDATORS=[{"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 16}}])
    def test_password_options_and_schema_read_actual_validator_settings(self):
        """无参数；实际校验配置改变时，公开长度和两种新密码输入一起变化。"""
        from accounts.contracts import build_contract
        self.assertEqual(self.client.get("/api/v1/auth/options").json()["password"]["min_length"], 16)
        schemas = build_contract()["components"]["schemas"]
        self.assertEqual(schemas["RegistrationInput"]["properties"]["password"]["minLength"], 16)
        self.assertEqual(schemas["PasswordInput"]["properties"]["new_password"]["minLength"], 16)


class AuthContractTests(SimpleTestCase):
    """从真实 serializer 和当前路由检查静态导出。"""

    def test_contract_is_deterministic_and_only_covers_actual_account_methods(self):
        """无参数；每个已实现账号方法都有稳定 ID，不暴露规划端点。"""
        from accounts.contracts import build_contract, contract_text
        contract = build_contract()
        self.assertEqual(contract["openapi"], "3.1.0")
        self.assertEqual(contract_text(), contract_text())
        expected = set()
        for pattern in get_resolver().url_patterns:
            if pattern.callback.__module__ == "accounts.views":
                for method in pattern.callback.allowed_methods:
                    expected.add(("/" + str(pattern.pattern), method.lower()))
        actual = {(path, method) for path, methods in contract["paths"].items() for method in methods}
        self.assertEqual(actual, expected)
        operations = [operation for methods in contract["paths"].values() for operation in methods.values()]
        self.assertEqual(len({operation["operationId"] for operation in operations}), len(operations))
        self.assertNotIn("servers", contract)
        self.assertNotIn("/Users/", contract_text())
        self.assertNotIn("SB_MODEL", contract_text())

    def test_export_check_rejects_drift_and_does_not_rewrite(self):
        """无参数；显式输出可复算，--check 检测漂移而不悄悄修复。"""
        from config.contracts import contract_text
        with TemporaryDirectory() as directory:
            target = Path(directory) / "auth.json"
            call_command("export_auth_contract", output=str(target), stdout=io.StringIO())
            self.assertEqual(target.read_text(), contract_text())
            call_command("export_auth_contract", output=str(target), check=True, stdout=io.StringIO())
            target.write_text("{}\n")
            with self.assertRaises(CommandError):
                call_command("export_auth_contract", output=str(target), check=True, stdout=io.StringIO())
            self.assertEqual(target.read_text(), "{}\n")

    def test_request_schemas_are_bound_to_actual_view_serializers(self):
        """无参数；方法绑定实际 strict serializer，未知键关闭、敏感字段只写。"""
        from accounts.contracts import build_contract, serializer_schema, INPUT_SCHEMAS
        contract = build_contract()
        schemas = contract["components"]["schemas"]
        for path, methods in contract["paths"].items():
            view = resolve(path).func
            for method, operation in methods.items():
                if method in {"post", "patch"}:
                    name = INPUT_SCHEMAS[view.input_serializer]
                    body = operation["requestBody"]["content"]["application/json"]["schema"]
                    self.assertEqual(body, {"$ref": f"#/components/schemas/{name}"})
                    self.assertEqual(schemas[name], serializer_schema(view.input_serializer()))
                    self.assertIs(schemas[name]["additionalProperties"], False)
                    self.assertIn({"$ref": "#/components/parameters/CsrfHeader"}, operation["parameters"])
        for name, field in (("LoginInput", "password"), ("RegistrationInput", "password"), ("PasswordInput", "current_password"), ("PasswordInput", "new_password"), ("LogoutAllInput", "password")):
            self.assertIs(schemas[name]["properties"][field]["writeOnly"], True)
            self.assertEqual(schemas[name]["properties"][field]["maxLength"], 256)
        self.assertEqual(schemas["RegistrationInput"]["properties"]["password"]["minLength"], 12)
        self.assertEqual(schemas["PasswordInput"]["properties"]["new_password"]["minLength"], 12)
        self.assertEqual(schemas["ProfileInput"].get("required", []), [])
        self.assertEqual(schemas["PublicUser"]["properties"]["id"]["format"], "uuid")
        self.assertEqual(schemas["PublicUser"]["properties"]["email"]["format"], "email")
        self.assertEqual(schemas["PublicUser"]["properties"]["email_verified_at"]["type"], ["string", "null"])

    def test_public_user_retains_existing_json_semantics(self):
        """无参数；响应 serializer 精确公开白名单并保持时间的既有 JSON 编码。"""
        from accounts.models import User
        from accounts.serializers import public_user
        from accounts.contracts import build_contract
        now = timezone.now().replace(microsecond=123456)
        user = User(id=uuid4(), email="sample@example.test", display_name="测试", created_at=now)
        expected = {"id": str(user.id), "email": user.email, "display_name": user.display_name,
                    "timezone": user.timezone, "theme": user.theme,
                    "email_verified_at": None, "created_at": now}
        self.assertEqual(JsonResponse(public_user(user)).content, JsonResponse(expected).content)
        schema = build_contract()["components"]["schemas"]["PublicUser"]
        self.assertEqual(set(public_user(user)), set(schema["properties"]))
        self.assertEqual(set(schema["required"]), set(schema["properties"]))

    def test_public_responses_and_security_match_contract(self):
        """无参数；真实匿名成功及错误字段对应 schema，私有接口使用会话 Cookie。"""
        from accounts.contracts import build_contract
        contract = build_contract()
        schemas = contract["components"]["schemas"]
        for path, name in (("/api/v1/auth/options", "AuthOptions"), ("/api/v1/auth/csrf", "CsrfResponse")):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.json()), set(schemas[name]["properties"]))
            assert_contract_value(self, response.json(), schemas[name], schemas)
            self.assertEqual(contract["paths"][path]["get"]["security"], [])
        error = self.client.get("/api/v1/me").json()
        self.assertEqual(set(error), set(schemas["ErrorResponse"]["properties"]))
        self.assertEqual(set(error["error"]), set(schemas["ErrorResponse"]["properties"]["error"]["properties"]))
        assert_contract_value(self, error, schemas["ErrorResponse"], schemas)
        cookie = contract["components"]["securitySchemes"]["SessionCookie"]
        self.assertEqual(cookie, {"type": "apiKey", "in": "cookie", "name": settings.SESSION_COOKIE_NAME})
        for method in ("get", "patch"):
            self.assertEqual(contract["paths"]["/api/v1/me"][method]["security"], [{"SessionCookie": []}])

    def test_committed_export_matches_current_contract(self):
        """无参数；仓库导出必须与当前实际代码一致。"""
        from config.contracts import contract_text
        self.assertEqual((settings.BASE_DIR / "openapi.json").read_text(), contract_text())

    def test_actual_disallowed_methods_return_contract_error(self):
        """无参数；逐路由真实请求的方法错误与公开错误 schema 一致。"""
        from accounts.contracts import build_contract
        contract = build_contract()
        schemas = contract["components"]["schemas"]
        for path in contract["paths"]:
            response = self.client.delete(path)
            self.assertEqual(response.status_code, 405)
            assert_contract_value(self, response.json(), schemas["ErrorResponse"], schemas)
