"""真实 PostgreSQL 的邀请注册与账号约束测试。"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, IntegrityError, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch
from django.db import connections

PASSWORD = "Tangerine-River-492!opaque"


class AccountModelTests(TestCase):
    """不借助管理员权限验证用户事实。"""

    def test_runtime_identity_and_case_insensitive_email(self):
        """无参数；ORM 受限且 DB 约束直接阻止邮箱大小写重复。"""
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            self.assertEqual(cursor.fetchone()[0], "sb_runtime")
        user = get_user_model().objects.create_user(" Name@Example.TEST ", PASSWORD, display_name="名字")
        self.assertEqual(user.email, "name@example.test")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertIsNone(user.email_verified_at)
        with self.assertRaises(IntegrityError), transaction.atomic():
            get_user_model().objects.create(email="NAME@example.test", display_name="重复")


class RegistrationTests(TestCase):
    """通过真实 HTTP 验证注册白名单、邀请与政策接受。"""

    def setUp(self):
        """无参数；每个测试使用独立事务和真实 CSRF 客户端。"""
        self.browser = Client(enforce_csrf_checks=True)
        self.token = self.browser.get("/api/v1/auth/csrf").json()["csrf_token"]

    def post(self, payload):
        """payload 为注册 JSON；使用已引导的真实 CSRF token。"""
        return self.browser.post("/api/v1/auth/register", payload, content_type="application/json", HTTP_X_CSRFTOKEN=self.token)

    def test_registration_route_rejects_missing_invite(self):
        """无参数；注册入口已实现且缺少必要字段返回公开 400。"""
        response = self.post({"email": "new@example.test", "password": PASSWORD})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {"error"})
        self.assertEqual(set(response.json()["error"]), {"code", "message", "request_id"})

    def test_unknown_integrity_error_is_not_misreported_as_invitation_conflict(self):
        """无参数；异常映射只覆盖邮箱唯一性，未知内部约束错误必须继续抛出。"""
        from accounts.services import issue_invitation, register
        from accounts.models import UserManager
        data = {"invite_token": issue_invitation("new@example.test"), "email": "new@example.test", "password": PASSWORD,
                "display_name": "名字", "policy_versions": settings.ACCOUNT_POLICY_VERSIONS}
        # 故障注入仅覆盖未知异常分支；真实邮箱约束竞态由独立并发测试验证。
        with patch.object(UserManager, "create_user", side_effect=IntegrityError("unknown internal constraint")):
            with self.assertRaises(Exception) as captured:
                register(data)
        self.assertIsInstance(captured.exception, IntegrityError)

    def test_invitation_registration_and_replay(self):
        """无参数；绑定邮箱、单次令牌、真实政策版本接受和 DTO 无秘密。"""
        from accounts.services import issue_invitation
        from accounts.models import Invitation, PolicyAcceptance
        token = issue_invitation("new@example.test")
        payload = {"invite_token": token, "email": "New@Example.test", "password": PASSWORD,
                   "display_name": "名字", "policy_versions": settings.ACCOUNT_POLICY_VERSIONS}
        invitation = Invitation.objects.get()
        self.assertNotEqual(invitation.token_hash, token)
        response = self.post(payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.json()), {"user"})
        self.assertEqual(set(response.json()["user"]), {"id", "email", "display_name", "timezone", "theme", "email_verified_at", "created_at"})
        self.assertEqual(PolicyAcceptance.objects.get().versions, settings.ACCOUNT_POLICY_VERSIONS)
        self.assertEqual(self.post(payload).status_code, 409)

    def test_unknown_privileged_fields_and_invalid_policies(self):
        """无参数；拒绝客户端越权字段和旧版/缺失政策，不消费邀请。"""
        from accounts.services import issue_invitation
        token = issue_invitation("new@example.test")
        payload = {"invite_token": token, "email": "new@example.test", "password": PASSWORD,
                   "display_name": "名字", "policy_versions": settings.ACCOUNT_POLICY_VERSIONS}
        for key in ("owner_id", "user_id", "is_staff", "is_superuser"):
            self.assertEqual(self.post({**payload, key: True}).status_code, 400)
        for versions in ({}, {"terms": "old"}, None):
            self.assertEqual(self.post({**payload, "policy_versions": versions}).status_code, 400)
        self.assertEqual(self.post(payload).status_code, 201)

    def test_expired_or_wrong_email_invitation_has_uniform_conflict(self):
        """无参数；错误绑定邮箱、过期及未知令牌仅公开同一409，不创建账号。"""
        from accounts.services import issue_invitation
        from accounts.models import Invitation
        token = issue_invitation("bound@example.test")
        payload = {"invite_token": token, "email": "other@example.test", "password": PASSWORD,
                   "display_name": "名字", "policy_versions": settings.ACCOUNT_POLICY_VERSIONS}
        wrong = self.post(payload)
        self.assertEqual(wrong.status_code, 409)
        Invitation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        expired = self.post({**payload, "email": "bound@example.test"})
        unknown = self.post({**payload, "invite_token": "unknown"})
        self.assertEqual(expired.status_code, 409)
        self.assertEqual(unknown.status_code, 409)
        self.assertEqual(wrong.json()["error"]["code"], expired.json()["error"]["code"])
        self.assertEqual(expired.json()["error"]["message"], unknown.json()["error"]["message"])
        self.assertFalse(get_user_model().objects.exists())

    def test_password_validation_length_limits_and_no_implicit_email_verification(self):
        """无参数；框架弱密码验证和字段上限在数据库写入前执行。"""
        from accounts.services import issue_invitation
        payload = {"invite_token": issue_invitation("new@example.test"), "email": "new@example.test",
                   "password": PASSWORD, "display_name": "名字", "policy_versions": settings.ACCOUNT_POLICY_VERSIONS}
        for password in ("123456789012", "password", "a" * 257):
            self.assertEqual(self.post({**payload, "password": password}).status_code, 400)
        self.assertEqual(self.post({**payload, "display_name": "a" * 81}).status_code, 400)
        response = self.post(payload)
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.json()["user"]["email_verified_at"])
        self.assertEqual(self.browser.get("/api/v1/me").status_code, 401)

    @override_settings(SB_ENV="production")
    def test_local_test_policies_cannot_enable_production_registration(self):
        """无参数；本机测试政策不能被当作生产法律文件接受。"""
        from accounts.services import issue_invitation
        payload = {"invite_token": issue_invitation("new@example.test"), "email": "new@example.test",
                   "password": PASSWORD, "display_name": "名字", "policy_versions": settings.ACCOUNT_POLICY_VERSIONS}
        self.assertEqual(self.post(payload).status_code, 503)
        self.assertFalse(get_user_model().objects.exists())


class InvitationConcurrencyTests(TransactionTestCase):
    """独立连接验证并发；清理只用 runtime DML，绝不用 owner/flush。"""

    def _fixture_teardown(self):
        """无参数；仅删除本测试应用记录，不调用需要 owner 权限的 TRUNCATE。"""
        from accounts.models import Invitation, AuthThrottle
        from django.contrib.sessions.models import Session
        get_user_model().objects.all().delete()
        Invitation.objects.all().delete()
        AuthThrottle.objects.all().delete()
        Session.objects.all().delete()

    def test_same_invitation_concurrently_consumed_once(self):
        """无参数；两个独立连接同时注册，严格一个201一个409。"""
        from accounts.services import issue_invitation
        from accounts.models import Invitation, PolicyAcceptance
        token = issue_invitation("race@example.test")
        barrier = Barrier(2)

        def attempt():
            """无参数；每个线程独立 runtime DB 连接及 CSRF/cookie 客户端。"""
            try:
                browser = Client(enforce_csrf_checks=True)
                csrf_token = browser.get("/api/v1/auth/csrf").json()["csrf_token"]
                with connections["default"].cursor() as cursor:
                    cursor.execute("SELECT current_user")
                    identity = cursor.fetchone()[0]
                barrier.wait(timeout=10)
                response = browser.post("/api/v1/auth/register", {"invite_token": token, "email": "race@example.test", "password": PASSWORD,
                    "display_name": "并发用户", "policy_versions": settings.ACCOUNT_POLICY_VERSIONS}, content_type="application/json", HTTP_X_CSRFTOKEN=csrf_token)
                return identity, response.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt) for _ in range(2)]
            results = [future.result() for future in futures]
        self.assertEqual(sorted(code for _, code in results), [201, 409])
        self.assertEqual({identity for identity, _ in results}, {"sb_runtime"})
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(PolicyAcceptance.objects.count(), 1)
        self.assertIsNotNone(Invitation.objects.get().consumed_at)

    def test_different_invitations_same_email_conflict_after_competing_commit(self):
        """无参数；不同邀请锁下竞态在真实full_clean出现时也只能返回公开409。"""
        from accounts.services import issue_invitation, register, AccountError
        from accounts.models import Invitation, PolicyAcceptance, UserManager
        tokens = [issue_invitation("same@example.test") for _ in range(2)]
        both_checked = Barrier(2)
        first_committed = Event()
        original_create_user = UserManager.create_user

        def ordered_create_user(manager, email, password=None, **fields):
            """manager/email/password/fields原样调用真实方法；同步仅令两个exists均先通过。"""
            both_checked.wait(timeout=10)
            if fields["display_name"] == "第二个注册":
                if not first_committed.wait(timeout=10):
                    raise RuntimeError("第一个注册未完成提交")
            return original_create_user(manager, email, password, **fields)

        def attempt(index):
            """index选择独立邀请；真实事务提交后才释放另一个线程继续full_clean。"""
            try:
                data = {"invite_token": tokens[index], "email": "same@example.test", "password": PASSWORD,
                        "display_name": "第一个注册" if index == 0 else "第二个注册", "policy_versions": settings.ACCOUNT_POLICY_VERSIONS}
                try:
                    register(data)
                    return 201, "created"
                except AccountError as error:
                    return error.status, error.code
                except Exception as error:
                    return 500, type(error).__name__
            finally:
                if index == 0:
                    first_committed.set()
                connections.close_all()

        with patch.object(UserManager, "create_user", ordered_create_user), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt, index) for index in range(2)]
            results = [future.result() for future in futures]
        self.assertEqual(results, [(201, "created"), (409, "INVITATION_INVALID")])
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(PolicyAcceptance.objects.count(), 1)
        self.assertEqual(Invitation.objects.filter(consumed_at__isnull=False).count(), 1)
