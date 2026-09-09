"""账号基础接入的无数据库回归。"""
from django.conf import settings
from django.test import SimpleTestCase


class AccountsBootstrapTests(SimpleTestCase):
    """确认首次建库前自定义用户与匿名 CSRF 接口已接入。"""

    def test_custom_user_is_configured_before_migration(self):
        """无参数；首次迁移不得落入默认整数用户模型。"""
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")

    def test_csrf_bootstrap(self):
        """无参数；匿名客户端取得实际 CSRF cookie 和对应 token。"""
        response = self.client.get("/api/v1/auth/csrf")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrf_token", response.json())
        self.assertIn("csrftoken", response.cookies)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_unknown_api_route_uses_not_found_error(self):
        """无参数；未实现API保持404，并使用契约NOT_FOUND错误外壳。"""
        response = self.client.get("/api/v1/not-implemented")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")
        self.assertEqual(set(response.json()["error"]), {"code", "message", "request_id"})
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_method_errors_keep_contract_and_allow_header(self):
        """无参数；Django装饰器和账号适配层的405都保留明确错误与Allow头。"""
        for route, method, allow in (("/api/v1/auth/csrf", "post", "GET"), ("/api/v1/auth/logout", "get", "POST")):
            with self.subTest(route=route):
                response = getattr(self.client, method)(route)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response.json()["error"]["code"], "METHOD_NOT_ALLOWED")
                self.assertEqual(response.get("Allow"), allow)
