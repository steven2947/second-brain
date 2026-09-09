"""仅自编账号、私有捕获与替身SMTP验证普通找回密码边界。"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from smtplib import SMTPException
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from accounts.models import PasswordResetDelivery, User
from accounts.password_reset import capture_directory
from accounts.reset_worker import claim, deliver, process_one
from .test_accounts import PASSWORD

SMTP_SETTINGS = {'SB_MAIL_MODE': 'smtp', 'EMAIL_HOST': 'smtp.example.test', 'EMAIL_PORT': 587,
    'EMAIL_HOST_USER': 'fixture-user', 'EMAIL_HOST_PASSWORD': 'fixture-secret',
    'EMAIL_USE_TLS': True, 'EMAIL_USE_SSL': False, 'EMAIL_TIMEOUT': 2,
    'DEFAULT_FROM_EMAIL': 'no-reply@example.test'}


class PasswordResetTests(TestCase):
    """真实PostgreSQL和HTTP校验匿名请求及重置闭环。"""

    def setUp(self):
        """无参数；只创建自编测试账号和隔离私有目录。"""
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.configuration = override_settings(SB_MAIL_MODE='local_capture', SB_PRIVATE_DATA_ROOT=Path(self.directory.name))
        self.configuration.enable()
        self.addCleanup(self.configuration.disable)
        self.user = User.objects.create_user('recovery@example.test', PASSWORD, display_name='找回测试')
        self.client = Client(enforce_csrf_checks=True)

    def post(self, path, data):
        """path/data为测试HTTP写请求；保留真实CSRF校验。"""
        csrf = self.client.get('/api/v1/auth/csrf').json()['csrf_token']
        return self.client.post(path, data, content_type='application/json', HTTP_X_CSRFTOKEN=csrf)

    def request_reset(self, email=None):
        """email可覆盖测试账号地址；请求只允许固定202接收状态。"""
        return self.post('/api/v1/auth/password-reset/request', {'email': email or self.user.email})

    def issue(self):
        """无参数；通过真实异步捕获取回测试链接，API不接触令牌。"""
        self.assertEqual(self.request_reset().status_code, 202)
        self.assertTrue(process_one(self.user.pk))
        row = PasswordResetDelivery.objects.filter(user=self.user).latest('created_at')
        path = capture_directory(self.user.pk) / (str(row.pk) + '.json')
        payload = json.loads(path.read_text())
        token = payload['body'].split('#token=', 1)[1].split()[0]
        return row, path, token

    def confirm(self, token, password='New-Recovery-Password-493!'):
        """token/password为本例确认输入；不裁剪密码或保存令牌。"""
        return self.post('/api/v1/auth/password-reset/confirm', {'token': token, 'new_password': password})

    def login(self, client=None):
        """client可提供另一浏览器；真实登录后返回原客户端供后续会话断言。"""
        client = client or self.client
        csrf = client.get('/api/v1/auth/csrf').json()['csrf_token']
        response = client.post('/api/v1/auth/login', {'email': self.user.email, 'password': PASSWORD},
            content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 200)
        return client

    def test_request_is_uniform_and_never_returns_private_link(self):
        """无参数；已知和未知邮箱公开响应完全一致。"""
        for email in (self.user.email, 'absent@example.test'):
            response = self.request_reset(email)
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json(), {'status': 'accepted', 'delivery': 'local_capture'})

    @override_settings(SB_MAIL_MODE='disabled')
    def test_disabled_channel_rejects_all_addresses(self):
        """无参数；无通道时账号存在性不影响统一503。"""
        for email in (self.user.email, 'absent@example.test'):
            response = self.request_reset(email)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['error']['code'], 'CHANNEL_UNAVAILABLE')

    def test_confirm_invalid_token_is_safe(self):
        """无参数；篡改令牌不泄露账号或内部异常。"""
        response = self.post('/api/v1/auth/password-reset/confirm', {'token': 'invalid', 'new_password': PASSWORD})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'RESET_INVALID')

    def test_only_active_ordinary_accounts_are_queued(self):
        """无参数；管理员、停用及注销中账号均202且不创建发送任务。"""
        for fields in ({'status': 'disabled'}, {'status': 'deletion_pending'}, {'is_staff': True}, {'is_superuser': True}):
            with self.subTest(fields=fields):
                User.objects.filter(pk=self.user.pk).update(status='active', is_staff=False, is_superuser=False)
                User.objects.filter(pk=self.user.pk).update(**fields)
                self.assertEqual(self.request_reset().json(), {'status': 'accepted', 'delivery': 'local_capture'})
                self.assertEqual(PasswordResetDelivery.objects.count(), 0)
                self.assertFalse(process_one(self.user.pk))

    def test_capture_is_private_fixed_origin_and_not_publicly_readable(self):
        """无参数；token只在私有正文，固定受控来源不使用Host，捕获不可由API/静态路由读取。"""
        row, path, token = self.issue()
        payload = json.loads(path.read_text())
        self.assertEqual(set(payload), {'to', 'subject', 'body', 'expires_at'})
        self.assertIn(settings.SB_PUBLIC_ORIGIN + '/reset-password#token=' + token, payload['body'])
        self.assertEqual(payload['to'], self.user.email)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        stored = json.dumps(list(PasswordResetDelivery.objects.values()), default=str)
        self.assertNotIn(self.user.email, stored)
        self.assertNotIn(token, stored)
        for route in ('/password-reset/' + str(self.user.pk) + '/' + path.name,
                '/static/password-reset/' + str(self.user.pk) + '/' + path.name,
                '/api/v1/auth/password-reset/' + str(row.pk)):
            self.assertEqual(self.client.get(route).status_code, 404)
        for route in ('/api/v1/auth/options', '/health/live'):
            response = self.client.get(route)
            self.assertNotIn(token, response.content.decode())
            self.assertNotIn(self.user.email, response.content.decode())

    def test_reset_revokes_all_sessions_and_other_tokens_without_login(self):
        """无参数；单次消费撤销全部旧会话及其他链接，响应204且不自动登录。"""
        self.login()
        second = self.login(Client(enforce_csrf_checks=True))
        row, path, token = self.issue()
        _, other_path, other_token = self.issue()
        before = User.objects.get(pk=self.user.pk).auth_epoch
        new_password = '  New-Recovery-Password-493!  '
        response = self.confirm(token, new_password)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b'')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertFalse(self.user.check_password(new_password.strip()))
        self.assertEqual(self.user.auth_epoch, before + 1)
        self.assertEqual(PasswordResetDelivery.objects.get(pk=row.pk).status, 'consumed')
        self.assertFalse(path.exists())
        self.assertFalse(other_path.exists())
        for value in (token, other_token):
            self.assertEqual(self.confirm(value).json()['error']['code'], 'RESET_INVALID')
        self.assertEqual(self.client.get('/api/v1/me').status_code, 401)
        self.assertEqual(second.get('/api/v1/me').status_code, 401)
        self.assertEqual(Client().get('/api/v1/me').status_code, 401)

    def test_weak_password_does_not_consume_valid_link(self):
        """无参数；长度、常见密码和用户相似密码由Django校验，同一链接可改交有效密码。"""
        _, _, token = self.issue()
        for password in ('short', '1234567890123456', 'recovery@example.test'):
            response = self.confirm(token, password)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()['error']['code'], 'INVALID_INPUT')
        self.assertEqual(self.confirm(token).status_code, 204)

    def test_expired_and_tampered_tokens_share_invalid_error(self):
        """无参数；数据库期限、Django期限以及换任务ID均不能绕过验证。"""
        row, _, token = self.issue()
        other, _, _ = self.issue()
        for value in (token + 'x', other.pk.hex + '.' + token.split('.', 1)[1]):
            self.assertEqual(self.confirm(value).json()['error']['code'], 'RESET_INVALID')
        PasswordResetDelivery.objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.confirm(token).json()['error']['code'], 'RESET_INVALID')
        with patch('accounts.password_reset.ResetTokenGenerator._now', return_value=datetime.now() - timedelta(minutes=31)):
            _, _, old = self.issue()
        self.assertEqual(self.confirm(old).json()['error']['code'], 'RESET_INVALID')

    def test_login_logout_and_password_change_invalidate_previous_links(self):
        """无参数；普通登录、普通退出、全退出和改密各自撤销旧链接。"""
        for operation in ('login', 'logout', 'logout-all', 'password'):
            with self.subTest(operation=operation):
                self.user.set_password(PASSWORD)
                self.user.save(update_fields=['password'])
                self.login()
                _, _, token = self.issue()
                if operation == 'login':
                    self.login()
                elif operation == 'password':
                    self.assertEqual(self.post('/api/v1/me/password', {'current_password': PASSWORD,
                        'new_password': 'Changed-Recovery-Password-129!'}).status_code, 204)
                else:
                    payload = {'password': PASSWORD} if operation == 'logout-all' else {}
                    self.assertEqual(self.post('/api/v1/auth/' + operation, payload).status_code, 204)
                self.assertEqual(self.confirm(token).json()['error']['code'], 'RESET_INVALID')

    def test_identity_change_and_restore_cannot_resurrect_old_link(self):
        """无参数；SQL身份触发器推进epoch，停用/管理员/注销后恢复也不能使用旧链接。"""
        for fields in ({'status': 'disabled'}, {'status': 'deletion_pending'}, {'is_staff': True}, {'is_superuser': True}):
            with self.subTest(fields=fields):
                _, _, token = self.issue()
                User.objects.filter(pk=self.user.pk).update(**fields)
                self.assertEqual(self.confirm(token).json()['error']['code'], 'RESET_INVALID')
                User.objects.filter(pk=self.user.pk).update(status='active', is_staff=False, is_superuser=False)
                self.assertEqual(self.confirm(token).json()['error']['code'], 'RESET_INVALID')

    def test_permissions_change_before_worker_prevents_delivery(self):
        """无参数；申请后至发送前权限或密码/登录变化阻止发送旧链接。"""
        self.assertEqual(self.request_reset().status_code, 202)
        User.objects.filter(pk=self.user.pk).update(status='disabled')
        self.assertTrue(process_one(self.user.pk))
        self.assertEqual(PasswordResetDelivery.objects.get().status, 'cancelled')
        self.assertFalse(list(Path(self.directory.name).rglob('*.json')))

    def test_restart_recovers_lease_and_old_worker_is_fenced(self):
        """无参数；过期租约重领后旧worker不能写捕获，新worker可完成同一任务。"""
        self.request_reset()
        first = claim(self.user.pk)
        PasswordResetDelivery.objects.filter(pk=first[0]).update(lease_until=timezone.now() - timedelta(seconds=1))
        second = claim(self.user.pk)
        self.assertNotEqual(first[1], second[1])
        deliver(self.user.pk, *first)
        self.assertFalse(list(Path(self.directory.name).rglob('*.json')))
        deliver(self.user.pk, *second)
        self.assertEqual(PasswordResetDelivery.objects.get().status, 'sent')
        self.assertEqual(len(list(Path(self.directory.name).rglob('*.json'))), 1)

    @override_settings(**SMTP_SETTINGS)
    def test_smtp_is_async_failed_delivery_is_bounded_and_private(self):
        """无参数；请求不建立SMTP连接，替身失败有限重试且不伪报成功、不泄露异常。"""
        with patch('accounts.reset_worker.get_connection', side_effect=SMTPException('private@example.test secret-link')) as transport:
            for address in (self.user.email, 'unknown@example.test'):
                self.assertEqual(self.request_reset(address).json(), {'status': 'accepted', 'delivery': 'smtp'})
            transport.assert_not_called()
            for attempt in range(1, 4):
                self.assertTrue(process_one(self.user.pk))
                row = PasswordResetDelivery.objects.get()
                self.assertEqual(row.attempts, attempt)
                self.assertEqual(row.status, 'queued' if attempt < 3 else 'failed')
                PasswordResetDelivery.objects.filter(pk=row.pk).update(available_at=timezone.now() - timedelta(seconds=1))
            self.assertFalse(process_one(self.user.pk))
            self.assertEqual(transport.call_count, 3)
            self.assertEqual(row.binding, '')

    @override_settings(**SMTP_SETTINGS)
    def test_smtp_uses_django_explicit_connection_and_one_recipient(self):
        """无参数；替身邮件连接验证单一收件人、固定来源、TLS和短超时，无真实网络。"""
        self.request_reset()
        connection = MagicMock()
        connection.send_messages.return_value = 1
        with patch('accounts.reset_worker.get_connection') as factory:
            factory.return_value.__enter__.return_value = connection
            process_one(self.user.pk)
        factory.assert_called_once_with(backend='django.core.mail.backends.smtp.EmailBackend',
            host='smtp.example.test', port=587, username='fixture-user', password='fixture-secret',
            use_tls=True, use_ssl=False, timeout=2, fail_silently=False)
        message = connection.send_messages.call_args.args[0][0]
        self.assertEqual(message.to, [self.user.email])
        self.assertEqual(message.from_email, 'no-reply@example.test')
        self.assertIn(settings.SB_PUBLIC_ORIGIN + '/reset-password#token=', message.body)
        self.assertEqual(PasswordResetDelivery.objects.get().status, 'sent')

    def test_captures_reject_public_or_symlink_directories_for_every_address(self):
        """无参数；失效目录对已知/未知邮箱相同503，不写公开目录或跟随符号链接。"""
        link = Path(self.directory.name) / 'linked'
        link.symlink_to(self.directory.name)
        for root in (Path(self.directory.name) / 'public', link):
            with override_settings(SB_PRIVATE_DATA_ROOT=root):
                for address in (self.user.email, 'absent@example.test'):
                    response = self.request_reset(address)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()['error']['code'], 'CHANNEL_UNAVAILABLE')
        self.assertEqual(PasswordResetDelivery.objects.count(), 0)

    def test_all_reset_writes_require_csrf_and_strict_fields(self):
        """无参数；匿名找回仍需CSRF，同源写只允许公开契约字段。"""
        for route, payload in (('/api/v1/auth/password-reset/request', {'email': self.user.email}),
                ('/api/v1/auth/password-reset/confirm', {'token': 'invalid', 'new_password': PASSWORD})):
            response = self.client.post(route, payload, content_type='application/json')
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()['error']['code'], 'CSRF_FAILED')
            self.assertEqual(self.post(route, {**payload, 'email_body': 'forbidden'}).status_code, 400)
        self.assertEqual(self.post('/api/v1/auth/password-reset/request', {'email': 'invalid'}).status_code, 400)

    @override_settings(ACCOUNT_LOGIN_EMAIL_LIMIT=2, ACCOUNT_LOGIN_SOURCE_LIMIT=3)
    def test_anonymous_rate_limits_persist_for_unknown_email_and_source(self):
        """无参数；不存在的邮箱也计数，不可利用换邮箱绕过直接来源限制。"""
        for _ in range(2):
            self.assertEqual(self.request_reset('absent@example.test').status_code, 202)
        response = self.request_reset('ABSENT@example.test')
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response['Retry-After']), 0)
        self.assertEqual(self.request_reset('different@example.test').status_code, 429)

    @override_settings(ACCOUNT_LOGIN_EMAIL_LIMIT=2, ACCOUNT_LOGIN_SOURCE_LIMIT=3)
    def test_confirm_rate_limit_counts_tampered_tokens(self):
        """无参数；无效令牌确认也受持久限流，换令牌不能绕过来源限制。"""
        for _ in range(2):
            self.assertEqual(self.confirm('invalid').status_code, 400)
        self.assertEqual(self.confirm('invalid').status_code, 429)
        self.assertEqual(self.confirm('different-invalid').status_code, 429)

    def test_delivery_expired_before_send_is_never_captured(self):
        """无参数；30分钟未处理的申请直接终结，重启worker不能发送过期链接。"""
        self.request_reset()
        PasswordResetDelivery.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertTrue(process_one(self.user.pk))
        self.assertEqual(PasswordResetDelivery.objects.get().status, 'failed')
        self.assertFalse(list(Path(self.directory.name).rglob('*.json')))

    @override_settings(**{**SMTP_SETTINGS, 'EMAIL_HOST_PASSWORD': ''})
    def test_missing_smtp_credentials_is_unavailable_for_all_addresses(self):
        """无参数；运行配置缺少SMTP秘密时，对存在/未知邮箱同503而不是伪造发送成功。"""
        for email in (self.user.email, 'absent@example.test'):
            response = self.request_reset(email)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['error']['code'], 'CHANNEL_UNAVAILABLE')
        self.assertEqual(PasswordResetDelivery.objects.count(), 0)

class MailConfigurationTests(SimpleTestCase):
    """无网络验证只接受显式配置和安全SMTP选项。"""

    def test_mode_defaults_disabled_and_production_rejects_capture(self):
        """无参数；默认关闭，无部署者配置不能声称邮件服务可用。"""
        from config.settings.environment import mail_settings
        self.assertEqual(mail_settings({}, False), {'SB_MAIL_MODE': 'disabled', 'PASSWORD_RESET_TIMEOUT': 1800})
        with self.assertRaises(ValueError):
            mail_settings({'SB_MAIL_MODE': 'local_capture'}, True)
        with override_settings(SB_MAIL_MODE='local_capture', SB_ENV='production'):
            self.assertFalse(self.client.get('/api/v1/auth/options').json()['password_reset']['available'])

    def test_smtp_missing_or_malformed_config_fails_closed(self):
        """无参数；SMTP必填、TLS互斥和短超时均由启动配置校验，错误不回显凭据。"""
        from config.settings.environment import mail_settings
        env = {'SB_MAIL_MODE': 'smtp', 'SB_SMTP_HOST': 'smtp.example.test', 'SB_SMTP_PORT': '587',
            'SB_SMTP_FROM_EMAIL': 'no-reply@example.test', 'SB_SMTP_USER': 'fixture-user',
            'SB_SMTP_PASSWORD': 'fixture-secret', 'SB_SMTP_USE_TLS': 'true', 'SB_SMTP_USE_SSL': 'false'}
        self.assertEqual(mail_settings(env, True)['EMAIL_TIMEOUT'], 5)
        for key in set(env) - {'SB_MAIL_MODE'}:
            with self.subTest(missing=key), self.assertRaises(ValueError):
                mail_settings({name: value for name, value in env.items() if name != key}, True)
        for changed in ({'SB_SMTP_USE_SSL': 'true'}, {'SB_SMTP_USE_TLS': 'false'},
                {'SB_SMTP_TIMEOUT_SECONDS': 'nan'}, {'SB_SMTP_TIMEOUT_SECONDS': '60'},
                {'SB_SMTP_PORT': '0'}, {'SB_SMTP_FROM_EMAIL': 'x@example.test\r\nBcc: x@example.test'}):
            with self.subTest(changed=changed), self.assertRaises(ValueError) as caught:
                mail_settings({**env, **changed}, True)
            self.assertNotIn('fixture-secret', str(caught.exception))
