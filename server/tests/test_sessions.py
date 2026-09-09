"""真实双客户端会话、CSRF、账号生命周期与持久防爆破。"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client, TestCase, override_settings
from .test_accounts import PASSWORD


class SessionTests(TestCase):
    """以数据库服务端会话验证 HTTP 真实边界。"""

    def setUp(self):
        """无参数；建立普通账号和两个分别持有 cookie 的浏览器。"""
        self.user = get_user_model().objects.create_user("member@example.test", PASSWORD, display_name="用户")
        self.first, self.second = Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)

    def write(self, client, path, data=None, method="post", **headers):
        """client/path/data/method 为请求参数；每次读取轮换后的 CSRF token。"""
        token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        return getattr(client, method)(path, data or {}, content_type="application/json", HTTP_X_CSRFTOKEN=token, **headers)

    def login(self, client, **fields):
        """client 为目标浏览器；fields 可覆盖测试邮箱和密码。"""
        return self.write(client, "/api/v1/auth/login", {"email": self.user.email, "password": PASSWORD, **fields})

    def test_two_clients_login_and_session_rotation(self):
        """无参数；登录轮换已有匿名 session，两个会话独立保存到 DB。"""
        anonymous = self.first.session
        anonymous["test_marker"] = "value"
        anonymous.save()
        self.first.cookies[settings.SESSION_COOKIE_NAME] = anonymous.session_key
        old_key = anonymous.session_key
        self.assertEqual(self.login(self.first).status_code, 200)
        self.assertNotEqual(self.first.session.session_key, old_key)
        self.assertFalse(Session.objects.filter(session_key=old_key).exists())
        self.assertEqual(self.login(self.second).status_code, 200)
        self.assertNotEqual(self.first.session.session_key, self.second.session.session_key)
        self.assertEqual(self.first.get("/api/v1/me").json()["user"]["id"], str(self.user.id))
        self.assertEqual(self.second.get("/api/v1/me")["Cache-Control"], "no-store")

    def test_login_errors_and_admin_never_receive_auth_session(self):
        """无参数；错误/不存在账号统一401，管理员正确密码也不能建立完整会话。"""
        wrong = self.login(self.first, password="wrong-password").json()["error"]
        missing = self.login(self.first, email="absent@example.test")
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong["code"], missing.json()["error"]["code"])
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        response = self.login(self.first)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "MFA_REQUIRED")
        self.assertNotIn(settings.SESSION_COOKIE_NAME, response.cookies)
        self.assertEqual(self.first.get("/api/v1/me").status_code, 401)

    def test_reauthentication_always_rotates_session(self):
        """无参数；同一已登录账号再次登录也不能继续使用旧 session key。"""
        self.assertEqual(self.login(self.first).status_code, 200)
        previous = self.first.session.session_key
        self.assertEqual(self.login(self.first).status_code, 200)
        self.assertNotEqual(self.first.session.session_key, previous)
        self.assertFalse(Session.objects.filter(session_key=previous).exists())

    def assert_restored_identity_rejects_old_sessions(self, writer):
        """writer 为实际身份写入函数；覆盖禁用期间未访问的第二客户端旧 cookie。"""
        for changed in ({"status": "disabled"}, {"status": "deletion_pending"}, {"is_staff": True}, {"is_superuser": True}):
            with self.subTest(changed=changed):
                self.assertEqual(self.login(self.first).status_code, 200)
                self.assertEqual(self.login(self.second).status_code, 200)
                self.user.refresh_from_db()
                previous_epoch = self.user.auth_epoch
                writer(changed)
                self.assertEqual(self.first.get("/api/v1/me").status_code, 401)
                writer({"status": "active", "is_staff": False, "is_superuser": False})
                self.assertEqual(self.second.get("/api/v1/me").status_code, 401)
                self.assertEqual(self.first.get("/api/v1/me").status_code, 401)
                self.user.refresh_from_db()
                self.assertGreaterEqual(self.user.auth_epoch, previous_epoch + 2)

    def test_model_save_cannot_resurrect_old_session_after_restore(self):
        """无参数；普通模型 save 的身份变更持久撤销所有旧会话。"""
        def writer(changes):
            """changes 为本次状态/权限字段；直接执行真实模型 save。"""
            current = get_user_model().objects.get(pk=self.user.pk)
            for key, value in changes.items():
                setattr(current, key, value)
            current.save()
        self.assert_restored_identity_rejects_old_sessions(writer)

    def test_queryset_update_cannot_resurrect_old_session_after_restore(self):
        """无参数；QuerySet.update 不得绕过身份变更撤销。"""
        def writer(changes):
            """changes 为本次受控测试字段；执行实际 QuerySet.update。"""
            get_user_model().objects.filter(pk=self.user.pk).update(**changes)
        self.assert_restored_identity_rejects_old_sessions(writer)

    def test_sql_update_cannot_resurrect_old_session_after_restore(self):
        """无参数；真实 runtime SQL 写入同样不能绕过 epoch 撤销。"""
        from django.db import connection
        def writer(changes):
            """changes 仅来自本测试固定字段；值均参数化，不接受客户端 SQL。"""
            assignments = ", ".join(f"{connection.ops.quote_name(key)} = %s" for key in changes)
            with connection.cursor() as cursor:
                cursor.execute(f"UPDATE accounts_user SET {assignments} WHERE id = %s", [*changes.values(), self.user.pk])
        self.assert_restored_identity_rejects_old_sessions(writer)

    def test_error_envelope_and_auth_code_follow_published_contract(self):
        """无参数；错误只有error外壳，公开字段与服务端request_id严格匹配。"""
        response = self.first.get("/api/v1/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(set(response.json()), {"error"})
        self.assertEqual(set(response.json()["error"]), {"code", "message", "request_id"})
        self.assertEqual(response.json()["error"]["code"], "AUTH_REQUIRED")
        self.assertEqual(response.json()["error"]["request_id"], response["X-Request-ID"])

    def test_controlled_identity_service_returns_persisted_epoch(self):
        """无参数；服务端明确状态入口返回触发器生效后的事实，不开放HTTP提权。"""
        from accounts import services
        self.assertTrue(callable(getattr(services, "update_identity", None)))
        changed = services.update_identity(self.user.pk, status="disabled")
        self.assertEqual(changed.status, "disabled")
        self.assertEqual(changed.auth_epoch, 1)
        restored = services.update_identity(self.user.pk, status="active")
        self.assertEqual(restored.auth_epoch, 2)

    def test_epoch_never_decreases_and_higher_explicit_revision_is_preserved(self):
        """无参数；旧实例/直接SQL不得降低epoch，显式更大值不被触发器覆盖。"""
        users = get_user_model().objects.filter(pk=self.user.pk)
        users.update(status="disabled", auth_epoch=10)
        self.user.refresh_from_db()
        self.assertEqual(self.user.auth_epoch, 10)
        users.update(status="active", auth_epoch=0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.auth_epoch, 11)
        users.update(auth_epoch=0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.auth_epoch, 11)

    def test_anonymous_logout_accepts_empty_body_with_valid_csrf(self):
        """无参数；无业务载荷的退出可重复204，但保留 CSRF 验证。"""
        token = self.first.get("/api/v1/auth/csrf").json()["csrf_token"]
        for _ in range(2):
            response = self.first.post("/api/v1/auth/logout", data=b"", content_type="application/json", HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 204)

    def test_disabled_pending_or_promoted_accounts_lose_existing_session(self):
        """无参数；服务端账号状态变化在下一请求立即生效。"""
        for status, staff in (("disabled", False), ("deletion_pending", False), ("active", True)):
            self.user.status, self.user.is_staff = "active", False
            self.user.save()
            self.assertEqual(self.login(self.first).status_code, 200)
            self.user.status, self.user.is_staff = status, staff
            self.user.save()
            self.assertEqual(self.first.get("/api/v1/me").status_code, 401)
            self.assertIn(self.login(self.second).status_code, (401, 403))

    def test_password_change_revokes_other_session_and_preserves_password_spaces(self):
        """无参数；改密保留当前会话、撤销第二会话且不裁剪密码。"""
        self.login(self.first)
        self.login(self.second)
        new_password = "  New-Strong-Password-846!  "
        response = self.write(self.first, "/api/v1/me/password", {"current_password": PASSWORD, "new_password": new_password})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.first.get("/api/v1/me").status_code, 200)
        self.assertEqual(self.second.get("/api/v1/me").status_code, 401)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertFalse(self.user.check_password(new_password.strip()))

    def test_logout_all_revokes_both_clients_and_logout_is_idempotent(self):
        """无参数；全退出撤销两个 cookie 对应的授权，普通退出匿名可重复。"""
        self.login(self.first)
        self.login(self.second)
        self.assertEqual(self.write(self.first, "/api/v1/auth/logout-all", {"password": PASSWORD}).status_code, 204)
        for client in (self.first, self.second):
            self.assertEqual(client.get("/api/v1/me").status_code, 401)
            self.assertEqual(self.write(client, "/api/v1/auth/logout").status_code, 204)

    def test_logout_all_requires_password_reauthentication(self):
        """无参数；缺失/错误密码不得撤销会话，正确密码才可全退出。"""
        self.login(self.first)
        self.login(self.second)
        self.assertEqual(self.write(self.first, "/api/v1/auth/logout-all").status_code, 400)
        self.assertEqual(self.write(self.first, "/api/v1/auth/logout-all", {"password": "wrong-password"}).status_code, 401)
        self.assertEqual(self.first.get("/api/v1/me").status_code, 200)
        self.assertEqual(self.second.get("/api/v1/me").status_code, 200)
        self.assertEqual(self.write(self.first, "/api/v1/auth/logout-all", {"password": PASSWORD}).status_code, 204)

    def test_all_writes_enforce_csrf_even_for_anonymous_login_and_logout(self):
        """无参数；缺 token 和跨域请求不因匿名或退出而旁路 CSRF。"""
        for path in ("/api/v1/auth/register", "/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/auth/logout-all", "/api/v1/me/password", "/api/v1/me"):
            method = "patch" if path == "/api/v1/me" else "post"
            response = getattr(self.first, method)(path, {}, content_type="application/json")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(set(response.json()), {"error"})
            self.assertEqual(set(response.json()["error"]), {"code", "message", "request_id"})
            response = self.write(self.first, path, method=method, HTTP_ORIGIN="https://evil.example.test")
            self.assertEqual(response.status_code, 403)

    def test_profile_whitelist_timezone_and_model_permissions(self):
        """无参数；资料字段和 IANA 时区严格限制，标准权限 API 不报错。"""
        self.assertTrue(callable(getattr(self.user, "has_perm", None)))
        self.assertFalse(self.user.has_perm("accounts.change_user"))
        self.assertIsNone(self.user.deletion_requested_at)
        self.login(self.first)
        for fields in ({"email": "new@example.test"}, {"owner_id": "other"}, {"timezone": "Mars/Base"}, {"theme": "neon"}, {"display_name": "a" * 81}):
            self.assertEqual(self.write(self.first, "/api/v1/me", fields, "patch").status_code, 400)
        response = self.write(self.first, "/api/v1/me", {"timezone": "Europe/Paris", "theme": "dark", "display_name": "新名字"}, "patch")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["timezone"], "Europe/Paris")

    @override_settings(ACCOUNT_LOGIN_EMAIL_LIMIT=2, ACCOUNT_LOGIN_SOURCE_LIMIT=3)
    def test_database_rate_limit_survives_clients_and_ignores_forwarded_header(self):
        """无参数；不存在的邮箱照样节流，同来源伪造代理头不能绕过。"""
        for client in (self.first, self.second):
            self.assertEqual(self.login(client, email="absent@example.test").status_code, 401)
        throttled = self.login(Client(enforce_csrf_checks=True), email="ABSENT@example.test")
        self.assertEqual(throttled.status_code, 429)
        self.assertGreater(int(throttled["Retry-After"]), 0)
        response = self.write(self.first, "/api/v1/auth/login", {"email": "another@example.test", "password": PASSWORD}, HTTP_X_FORWARDED_FOR="192.0.2.50")
        self.assertEqual(response.status_code, 429)
        from accounts.models import AuthThrottle
        self.assertFalse(any("@" in key for key in AuthThrottle.objects.values_list("key", flat=True)))
