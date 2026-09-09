"""真实 PostgreSQL 验证当前账号成功响应和政策版本切换，不访问主库数据。"""
from django.conf import settings
from django.test import Client, TestCase, override_settings

from accounts.contracts import build_contract
from accounts.models import Invitation, PolicyAcceptance
from accounts.services import issue_invitation
from .test_auth_contract import assert_contract_value


class AuthContractIntegrationTests(TestCase):
    """真实邀请、会话、CSRF 及公开响应的接缝验收。"""

    def setUp(self):
        """无参数；使用本测试专属账号和强密码，仅存受限测试数据库。"""
        self.browser = Client(enforce_csrf_checks=True)
        self.contract = build_contract()
        self.secret = "Local-Orchid-Lantern-672!"
        self.payload = {"email": "contract@example.test", "password": self.secret,
                        "display_name": "契约测试", "invite_token": issue_invitation("contract@example.test"),
                        "policy_versions": dict(settings.ACCOUNT_POLICY_VERSIONS)}

    def write(self, method, path, payload):
        """method/path/payload 为当前写操作；每次使用实际同源 CSRF 引导。"""
        token = self.browser.get("/api/v1/auth/csrf").json()["csrf_token"]
        return getattr(self.browser, method)(path, payload, content_type="application/json", HTTP_X_CSRFTOKEN=token)

    def assert_response(self, response, path, method, status):
        """response 为真实 HTTP 响应；按路径、方法、状态检查实际 JSON 或无正文。"""
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Cache-Control"], "no-store")
        schema = self.contract["paths"][path][method]["responses"][str(status)]
        if status == 204:
            self.assertNotIn("content", schema)
            self.assertEqual(response.content, b"")
        else:
            assert_contract_value(self, response.json(), schema["content"]["application/json"]["schema"],
                                  self.contract["components"]["schemas"])

    def test_every_successful_account_operation_matches_exported_response(self):
        """无参数；覆盖全部实际账号方法的真实响应及会话建立/撤销。"""
        for path in ("/api/v1/auth/options", "/api/v1/auth/csrf"):
            self.assert_response(self.browser.get(path), path, "get", 200)
        self.assert_response(self.write("post", "/api/v1/auth/register", self.payload), "/api/v1/auth/register", "post", 201)
        self.assert_response(self.write("post", "/api/v1/auth/login", {"email": self.payload["email"], "password": self.secret}), "/api/v1/auth/login", "post", 200)
        self.assert_response(self.browser.get("/api/v1/me"), "/api/v1/me", "get", 200)
        self.assert_response(self.write("patch", "/api/v1/me", {"display_name": "已修改", "timezone": "UTC", "theme": "dark"}), "/api/v1/me", "patch", 200)
        new_secret = "Local-Pebble-Terrace-936!"
        self.assert_response(self.write("post", "/api/v1/me/password", {"current_password": self.secret, "new_password": new_secret}), "/api/v1/me/password", "post", 204)
        self.assert_response(self.write("post", "/api/v1/auth/logout-all", {"password": new_secret}), "/api/v1/auth/logout-all", "post", 204)
        self.assertEqual(self.browser.get("/api/v1/me").status_code, 401)
        self.assert_response(self.write("post", "/api/v1/auth/logout", {}), "/api/v1/auth/logout", "post", 204)

    def test_changed_policy_requires_explicit_new_acceptance(self):
        """无参数；旧版本提交失败且不消费邀请，只有明确新版本输入才记接受。"""
        updated = {"terms": "local-test-next", "privacy": "local-test-next"}
        with override_settings(ACCOUNT_POLICY_VERSIONS=updated):
            self.assertEqual(self.browser.get("/api/v1/auth/options").json()["registration"]["policy_versions"], updated)
            stale = self.write("post", "/api/v1/auth/register", self.payload)
            self.assertEqual(stale.status_code, 400)
            self.assertFalse(PolicyAcceptance.objects.exists())
            self.assertIsNone(Invitation.objects.get().consumed_at)
            current = self.write("post", "/api/v1/auth/register", {**self.payload, "policy_versions": updated})
            self.assertEqual(current.status_code, 201)
            self.assertEqual(PolicyAcceptance.objects.get().versions, updated)
