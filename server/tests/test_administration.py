"""真实 PostgreSQL + runtime HTTP；管理员准备独立迁移身份，仅使用自编临时数据。"""
import base64
import json
import tempfile
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
import psycopg
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, connections, DatabaseError
from django.test import SimpleTestCase, Client, override_settings
from django.utils import timezone
from django_otp.oath import TOTP
from jsonschema import Draft202012Validator
from access.context import owner_transaction
from accounts.models import User, AuthThrottle
from accounts.services import AccountError
from administration.bootstrap import prepare_administrator, confirm_administrator, require_management_connection
from administration.credentials import recovery_digest
from administration.models import AdministratorDevice, RecoveryCode
from administration.permissions import ROLES, granted_permissions
from administration.services import BACKEND, SESSION_KEY, require_admin
from config.contracts import build_contract

PASSWORD = 'Administrator-SelfAuthored-721!'


class AdministrationTests(SimpleTestCase):
    databases = {'default'}

    def setUp(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_sb_product')
        self.manager = psycopg.connect(settings.DEV_ENV['SB_MIGRATION_DATABASE_URL'],
            dbname='test_sb_product', autocommit=True)
        self.addCleanup(self.manager.close)
        self.assertEqual(self.manager.execute('SELECT current_database(), current_user').fetchone(),
            ('test_sb_product', 'sb_migrator'))
        self.directory = tempfile.TemporaryDirectory(prefix='sb-admin-fixture-')
        self.addCleanup(self.directory.cleanup)
        self.private = override_settings(SB_PRIVATE_DATA_ROOT=Path(self.directory.name))
        self.private.enable()
        self.addCleanup(self.private.disable)
        self.users = []
        self.addCleanup(self.cleanup_records)
        self.user, self.enrollment = self.prepare()
        self.confirm(self.user, self.enrollment)
        self.browser = self.client_with_csrf()

    @contextmanager
    def migration_connection(self):
        """仅固定测试库临时切为真实表拥有者；所有 HTTP/权限断言恢复 runtime。"""
        original = {key: connection.settings_dict[key] for key in ('USER', 'PASSWORD')}
        connection.close()
        connection.settings_dict.update(USER='sb_migrator', PASSWORD=settings.DEV_CONFIG['migration_password'])
        try:
            require_management_connection()
            yield
        finally:
            connection.close()
            connection.settings_dict.update(original)

    def prepare(self, role='knowledge-admin'):
        output = Path(self.directory.name) / (uuid4().hex + '.json')
        with self.migration_connection():
            user = prepare_administrator(f'admin-{uuid4().hex}@example.test', '自编管理员', PASSWORD, role, output)
        self.users.append(user.pk)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        return user, json.loads(output.read_text())

    def confirm(self, user, data):
        now = timezone.now() - timedelta(seconds=90)
        with self.migration_connection(), patch('administration.credentials.timezone.now', return_value=now):
            self.assertTrue(confirm_administrator(user.email, self.token(data, now)))

    def token(self, data=None, now=None):
        otp = TOTP(base64.b32decode((data or self.enrollment)['manual_secret']), step=30, digits=6)
        otp.time = (now or timezone.now()).timestamp()
        return f'{otp.token():06d}'

    def cleanup_records(self):
        for record in Session.objects.all():
            if record.get_decoded().get('_auth_user_id') in {str(uid) for uid in self.users}:
                record.delete()
        for table, column in (('administration_adminaudit', 'actor_id'),
                              ('administration_recoverycode', 'owner_id'),
                              ('administration_administratordevice', 'owner_id'),
                              ('accounts_user_groups', 'user_id'),
                              ('accounts_user_user_permissions', 'user_id'), ('accounts_user', 'id')):
            self.manager.execute(f'DELETE FROM {table} WHERE {column}=ANY(%s)', [self.users])
        AuthThrottle.objects.all().delete()

    def client_with_csrf(self):
        browser = Client(enforce_csrf_checks=True)
        browser.defaults['HTTP_X_CSRFTOKEN'] = browser.get('/api/v1/auth/csrf').json()['csrf_token']
        return browser

    def login(self, browser=None, user=None, token=None, method='totp'):
        browser = browser or self.browser
        user = user or self.user
        response = browser.post('/api/v1/admin/auth/login', {'email': user.email, 'password': PASSWORD,
            'token': token or self.token(), 'method': method}, content_type='application/json')
        browser.defaults['HTTP_X_CSRFTOKEN'] = browser.get('/api/v1/auth/csrf').json()['csrf_token']
        return response

    def test_complete_http_identity_reauth_logout_and_audit(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post('/api/v1/admin/auth/login', {},
            content_type='application/json').status_code, 403)
        self.browser.force_login(self.user, backend=BACKEND)
        previous = self.browser.session.session_key
        self.assertEqual(self.browser.get('/api/v1/admin/me').status_code, 401)
        self.browser.defaults['HTTP_X_CSRFTOKEN'] = self.browser.get('/api/v1/auth/csrf').json()['csrf_token']
        response = self.login()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotEqual(previous, self.browser.session.session_key)
        data = response.json()
        Draft202012Validator({'$ref': '#/components/schemas/AdminIdentity',
            'components': build_contract()['components']}).validate(data)
        self.assertEqual(set(data['user']), {'id', 'email', 'display_name'})
        self.assertEqual(data['granted_permissions'], sorted(ROLES['knowledge-admin']))
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(self.browser.get('/api/v1/admin/me').status_code, 200)
        reauth = self.browser.post('/api/v1/admin/auth/reauth', {'password': PASSWORD,
            'token': self.enrollment['recovery_codes'][0], 'method': 'recovery'}, content_type='application/json')
        self.assertEqual(reauth.status_code, 200, reauth.content)
        self.assertEqual(data['session_expires_at'], reauth.json()['session_expires_at'])
        self.assertEqual(self.browser.post('/api/v1/admin/auth/logout', {}, content_type='application/json').status_code, 204)
        self.assertEqual(self.browser.get('/api/v1/admin/me').status_code, 401)
        rows = self.manager.execute('SELECT action, request_id FROM administration_adminaudit WHERE actor_id=%s ORDER BY occurred_at', [self.user.pk]).fetchall()
        # fixture 用较早时间确认 OTP 避免真实等待；生产审计使用实际当前时间。
        self.assertCountEqual([row[0] for row in rows[:2]], ['admin.provision', 'admin.initialize'])
        self.assertEqual([row[0] for row in rows[2:]], ['admin.login', 'admin.reauth', 'admin.logout'])
        self.assertTrue(all(row[1] for row in rows[2:]))

    def test_totp_replay_and_expired_token_persist_failure_state(self):
        code = self.token()
        self.assertEqual(self.login(token=code).status_code, 200)
        replay = self.login(browser=self.client_with_csrf(), token=code)
        self.assertEqual(replay.status_code, 401)
        self.assertEqual(replay.json()['error']['code'], 'INVALID_CREDENTIALS')
        with owner_transaction(self.user.pk):
            device = AdministratorDevice.objects.get(owner=self.user)
            self.assertEqual(device.failure_count, 1)
            self.assertIsNotNone(device.next_attempt_at)
        future = timezone.now() + timedelta(seconds=2)
        with patch('administration.credentials.timezone.now', return_value=future):
            response = self.login(browser=self.client_with_csrf(), token=self.token(now=future - timedelta(seconds=150)))
        self.assertEqual(response.status_code, 401)
        with owner_transaction(self.user.pk):
            self.assertEqual(AdministratorDevice.objects.get(owner=self.user).failure_count, 2)

    def test_recovery_code_concurrent_consumption_exactly_once(self):
        barrier = Barrier(2)
        code = self.enrollment['recovery_codes'][0]
        def attempt():
            try:
                browser = self.client_with_csrf()
                barrier.wait(timeout=10)
                return self.login(browser=browser, token=code, method='recovery').status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt) for _ in range(2)]
            self.assertEqual(sorted(f.result() for f in futures), [200, 401])
        with owner_transaction(self.user.pk):
            self.assertIsNotNone(RecoveryCode.objects.get(token_hash=recovery_digest(code)).consumed_at)

    def test_ordinary_cookie_staff_cookie_and_password_only_have_no_admin_access(self):
        ordinary = User.objects.create_user(f'user-{uuid4().hex}@example.test', PASSWORD, display_name='自编用户')
        self.users.append(ordinary.pk)
        self.browser.force_login(ordinary, backend='accounts.backends.AccountBackend')
        self.assertEqual(self.browser.get('/api/v1/admin/me').status_code, 401)
        self.browser.force_login(self.user, backend=BACKEND)
        self.assertEqual(self.browser.get('/api/v1/admin/me').status_code, 401)
        self.browser.defaults['HTTP_X_CSRFTOKEN'] = self.browser.get('/api/v1/auth/csrf').json()['csrf_token']
        self.assertEqual(self.browser.post('/api/v1/auth/login', {'email': self.user.email, 'password': PASSWORD},
            content_type='application/json').json()['error']['code'], 'MFA_REQUIRED')
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.browser.get('/api/v1/me').status_code, 401)
        self.assertEqual(self.browser.patch('/api/v1/me', {'display_name': '不应写入'}, content_type='application/json').status_code, 401)
        self.assertEqual(self.browser.post('/api/v1/me/password', {'current_password': PASSWORD,
            'new_password': PASSWORD + '-new'}, content_type='application/json').status_code, 401)
        self.assertEqual(self.browser.get('/api/v1/problems').status_code, 401)

    def test_permissions_are_explicit_fresh_and_immediately_revocable(self):
        self.assertEqual(self.login().status_code, 200)
        request = self.browser.get('/api/v1/admin/me').wsgi_request
        self.assertEqual(require_admin(request, 'knowledge.review').pk, self.user.pk)
        with self.assertRaises(AccountError) as denied:
            require_admin(request, 'accounts.view')
        self.assertEqual(denied.exception.code, 'ADMIN_PERMISSION_DENIED')
        self.manager.execute('DELETE FROM accounts_user_groups WHERE user_id=%s', [self.user.pk])
        self.assertEqual(self.browser.get('/api/v1/admin/me').json()['granted_permissions'], [])
        with self.assertRaises(AccountError):
            require_admin(request, 'knowledge.review')
        self.manager.execute('UPDATE accounts_user SET is_superuser=true WHERE id=%s', [self.user.pk])
        self.assertEqual(granted_permissions(User.objects.get(pk=self.user.pk)), [])

    def test_expired_fresh_window_requires_reauth_without_extending_absolute_session(self):
        self.assertEqual(self.login().status_code, 200)
        response = self.browser.get('/api/v1/admin/me')
        request = response.wsgi_request
        expiry = response.json()['session_expires_at']
        future = timezone.now() + timedelta(minutes=6)
        with patch('administration.services.timezone.now', return_value=future):
            with self.assertRaises(AccountError) as denied:
                require_admin(request, 'knowledge.review', fresh=True)
            self.assertEqual(denied.exception.code, 'ADMIN_REAUTH_REQUIRED')
            reauth = self.browser.post('/api/v1/admin/auth/reauth', {'password': PASSWORD,
                'token': self.enrollment['recovery_codes'][0], 'method': 'recovery'}, content_type='application/json')
            self.assertEqual(reauth.status_code, 200, reauth.content)
            self.assertEqual(reauth.json()['session_expires_at'], expiry)
            require_admin(self.browser.get('/api/v1/admin/me').wsgi_request, 'knowledge.review', fresh=True)
        with patch('administration.services.timezone.now', return_value=timezone.now() + timedelta(hours=9)):
            self.assertEqual(self.browser.get('/api/v1/admin/me').status_code, 401)

    def test_device_revocation_epoch_and_unconfirmed_device_fail_closed(self):
        pending, data = self.prepare('system-admin')
        self.assertEqual(granted_permissions(pending), [])
        self.assertEqual(self.login(user=pending, token=self.token(data)).status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        self.manager.execute('UPDATE administration_administratordevice SET revoked_at=now() WHERE owner_id=%s', [self.user.pk])
        self.assertEqual(self.browser.get('/api/v1/admin/me').status_code, 401)
        self.manager.execute('UPDATE administration_administratordevice SET revoked_at=NULL WHERE owner_id=%s', [self.user.pk])
        self.assertEqual(self.login(token=self.enrollment['recovery_codes'][0], method='recovery').status_code, 200)
        self.manager.execute('UPDATE accounts_user SET auth_epoch=auth_epoch+1 WHERE id=%s', [self.user.pk])
        self.assertEqual(self.browser.get('/api/v1/admin/me').status_code, 401)

    def test_database_ciphertext_owner_rls_column_limits_and_append_only_audit(self):
        self.assertEqual(AdministratorDevice.objects.count(), 0)
        self.assertEqual(RecoveryCode.objects.count(), 0)
        other, _ = self.prepare()
        with owner_transaction(self.user.pk):
            self.assertEqual(list(AdministratorDevice.objects.values_list('owner_id', flat=True)), [self.user.pk])
            self.assertFalse(AdministratorDevice.objects.filter(owner=other).exists())
            stored = AdministratorDevice.objects.get(owner=self.user).secret_ciphertext
            self.assertNotIn(self.enrollment['manual_secret'], stored)
            self.assertEqual(RecoveryCode.objects.filter(owner=self.user).count(), 8)
        statements = [
            "UPDATE administration_administratordevice SET secret_ciphertext='bad'",
            'UPDATE administration_administratordevice SET confirmed_at=now()',
            'UPDATE administration_administratordevice SET revoked_at=NULL',
            'DELETE FROM administration_recoverycode',
            "UPDATE administration_recoverycode SET token_hash='bad'",
            'SELECT * FROM administration_adminaudit',
            "UPDATE administration_adminaudit SET action='admin.login'",
            'DELETE FROM administration_adminaudit',
            "INSERT INTO auth_group(name) VALUES ('forbidden')",
            "UPDATE auth_permission SET name='forbidden'",
            'UPDATE accounts_user_groups SET group_id=group_id',
        ]
        for statement in statements:
            with self.assertRaises(DatabaseError), connection.cursor() as cursor:
                cursor.execute(statement)
        raw = self.manager.execute('SELECT row_to_json(t)::text FROM administration_adminaudit t WHERE actor_id=%s', [self.user.pk]).fetchall()
        for secret in [PASSWORD, self.user.email, self.enrollment['manual_secret'], *self.enrollment['recovery_codes']]:
            self.assertNotIn(secret, str(raw))

    def test_bootstrap_refuses_runtime_existing_identity_outfile_and_non_tty(self):
        with self.assertRaises(ValueError):
            prepare_administrator('cannot@example.test', '不应建立', PASSWORD, 'system-admin', Path(self.directory.name) / 'no.json')
        with self.migration_connection(), self.assertRaises(ValueError):
            prepare_administrator(self.user.email, '不能覆盖', PASSWORD, 'system-admin', Path(self.directory.name) / 'other.json')
        with self.migration_connection(), self.assertRaises(FileExistsError):
            prepare_administrator('exclusive@example.test', '不能覆盖', PASSWORD, 'system-admin',
                next(Path(self.directory.name).glob('*.json')))
        self.assertFalse(User.objects.filter(email='exclusive@example.test').exists())
        stdout = StringIO()
        with patch('sys.stdin.isatty', return_value=False), self.assertRaises(CommandError):
            call_command('bootstrap_admin', output=str(Path(self.directory.name) / 'new.json'),
                settings='config.settings.migrate', stdout=stdout)
        self.assertEqual(stdout.getvalue(), '')

    def test_confirmation_requires_valid_totp_and_persists_failed_attempts(self):
        """未确认设备无组权限；错误确认不会回滚退避，真实 OTP 才启用指定角色。"""
        pending, data = self.prepare('system-admin')
        with self.migration_connection():
            self.assertFalse(confirm_administrator(pending.email, 'invalid'))
            self.assertFalse(confirm_administrator(pending.email, self.token(data)))
        self.assertEqual(granted_permissions(pending), [])
        with owner_transaction(pending.pk):
            device = AdministratorDevice.objects.get(owner=pending)
            self.assertIsNone(device.confirmed_at)
            self.assertEqual(device.failure_count, 1)
        future = timezone.now() + timedelta(seconds=2)
        with self.migration_connection(), patch('administration.credentials.timezone.now', return_value=future):
            self.assertTrue(confirm_administrator(pending.email, self.token(data, future)))
        self.assertEqual(granted_permissions(pending), sorted(ROLES['system-admin']))
        self.assertFalse(User.objects.get(pk=pending.pk).is_superuser)

    @override_settings(ACCOUNT_LOGIN_EMAIL_LIMIT=1, ACCOUNT_LOGIN_SOURCE_LIMIT=100)
    def test_admin_auth_attempts_are_persistently_rate_limited(self):
        bad = {'email': self.user.email, 'password': 'bad', 'token': '000000', 'method': 'totp'}
        first = self.browser.post('/api/v1/admin/auth/login', bad, content_type='application/json')
        second = self.browser.post('/api/v1/admin/auth/login', bad, content_type='application/json')
        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()['error']['code'], 'RATE_LIMITED')
        self.assertGreater(int(second['Retry-After']), 0)
