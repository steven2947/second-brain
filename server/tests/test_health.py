"""经 Django HTTP 请求栈验证健康路由和安全边界。"""

from unittest.mock import patch

from django.db import OperationalError, connections
from django.http import JsonResponse
from django.test import Client, SimpleTestCase, override_settings
from django.urls import path


def mutation_probe(request):
    """request 为测试请求；仅在临时测试路由中验证 CSRF 中间件。"""
    return JsonResponse({"accepted": True})


urlpatterns = [path("probe", mutation_probe)]


class HealthTests(SimpleTestCase):
    """不创建数据库；连接成功与断开用驱动边界模拟，真实连接另做冒烟。"""

    def test_live_does_not_need_database(self):
        """进程存活检查在 SimpleTestCase 禁止数据库访问时仍成功。"""
        response = self.client.get("/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_ready_returns_minimal_success(self):
        """驱动成功执行查询时，就绪接口只返回状态。"""
        with patch.object(connections["default"], "cursor") as cursor:
            cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
            response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_ready_failure_never_exposes_database_details(self):
        """驱动错误只能变成 503，不得在 HTTP 正文中回显连接异常。"""
        with patch.object(connections["default"], "cursor", side_effect=OperationalError("password=do-not-expose db=private-name")):
            response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_health_only_accepts_safe_methods(self):
        """健康接口不得接受状态变更方法。"""
        for route in ("/health/live", "/health/ready"):
            with self.subTest(route=route):
                self.assertEqual(self.client.post(route).status_code, 405)

    def test_untrusted_host_is_rejected(self):
        """请求伪造未登记 Host 时返回 400。"""
        self.assertEqual(self.client.get("/health/live", HTTP_HOST="evil.example.org").status_code, 400)

    @override_settings(ROOT_URLCONF=__name__)
    def test_csrf_middleware_rejects_anonymous_cross_origin_writes(self):
        """未认证写入也必须经过全局 CSRF，不能依靠后续会话鉴权。"""
        client = Client(enforce_csrf_checks=True)
        response = client.post("/probe", HTTP_ORIGIN="https://evil.example.org")
        self.assertEqual(response.status_code, 403)

    def test_future_business_routes_are_not_fake_implemented(self):
        """尚未实现的产品业务路由返回真实 404。"""
        self.assertEqual(self.client.post("/api/v1/runs").status_code, 404)

    @override_settings(SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
    def test_production_redirects_http_to_https(self):
        """生产安全中间件将 HTTP 请求转到同一主机 HTTPS。"""
        response = self.client.get("/health/live")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://testserver/health/live")
