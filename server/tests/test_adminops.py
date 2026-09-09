"""后台运营真实PG验收：身份、CAS、私有交付与只读聚合边界。"""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone as utc_timezone
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
from django.db import connection, connections, DatabaseError, close_old_connections
from django.test import SimpleTestCase, Client, override_settings
from django.utils import timezone
from access.context import owner_transaction
from accounts.models import User, Invitation
from administration.services import SESSION_KEY
from operations.models import QuotaBucket
from runs.models import Job
from . import test_administration as admin_fixture

PASSWORD = admin_fixture.PASSWORD


class AdminOperationsTests(SimpleTestCase):
    databases = {'default'}
    migration_connection = admin_fixture.AdministrationTests.migration_connection
    confirm = admin_fixture.AdministrationTests.confirm
    token = admin_fixture.AdministrationTests.token
    cleanup_records = admin_fixture.AdministrationTests.cleanup_records
    client_with_csrf = admin_fixture.AdministrationTests.client_with_csrf
    login = admin_fixture.AdministrationTests.login

    def prepare(self, role='system-admin'):
        """role为显式测试角色；复用真实MFA登记。"""
        return admin_fixture.AdministrationTests.prepare(self, role)

    def setUp(self):
        """无参数；只在独占测试库建立临时管理员和普通账号。"""
        admin_fixture.AdministrationTests.setUp(self)
        self.target = User.objects.create_user(uuid4().hex + '@example.test', PASSWORD, display_name='测试读者')
        self.users.append(self.target.pk)
        self.addCleanup(self.cleanup_operations)
        self.assertEqual(self.login().status_code, 200)
        self.base = '/api/v1/admin/users/' + str(self.target.pk)

    def cleanup_operations(self):
        """无参数；只清理当前测试owner和捕获邮箱。"""
        for table in ('publishing_adminmutation', 'operations_quotabucket', 'runs_job'):
            self.manager.execute(f'DELETE FROM {table} WHERE owner_id=ANY(%s)', [self.users])
        Invitation.objects.filter(email=self.target.email).delete()

    def write(self, method, path, data, key=None, browser=None):
        """method/path/data为真实HTTP请求；key用于幂等重放。"""
        if method == 'put' and path.endswith('/quota'):
            data = {'expected_period': timezone.now().astimezone(utc_timezone.utc).date().replace(day=1).isoformat(), **data}
        return getattr(browser or self.browser, method)(path, data, content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=key or uuid4().hex)

    def status(self, status='disabled', expected='active', **kwargs):
        """status/expected为目标和比较状态；kwargs为HTTP测试选项。"""
        return self.write('post', self.base + '/status',
            {'status': status, 'expected_status': expected, 'reason': '本次自编测试'}, **kwargs)

    def test_status_cas_idempotency_and_old_session_never_revives(self):
        """无参数；停用恢复推进epoch，旧浏览器未经访问仍永久失效。"""
        reader = self.client_with_csrf()
        self.assertEqual(reader.post('/api/v1/auth/login', {'email': self.target.email, 'password': PASSWORD},
            content_type='application/json').status_code, 200)
        key = uuid4().hex
        response = self.status(key=key)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(set(response.json()), {'id', 'email', 'display_name', 'status'})
        self.assertEqual(response.json()['status'], 'disabled')
        self.assertEqual(self.status(key=key).json(), response.json())
        self.assertEqual(self.status().status_code, 409)
        self.assertEqual(self.status('active', 'disabled').status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.auth_epoch, 2)
        self.assertEqual(reader.get('/api/v1/me').status_code, 401)
        audits = self.manager.execute("SELECT action,reason FROM administration_adminaudit WHERE actor_id=%s AND target_id=%s ORDER BY occurred_at", [self.user.pk, self.target.pk]).fetchall()
        self.assertEqual(audits, [('accounts.disable', '本次自编测试'), ('accounts.enable', '本次自编测试')])

    def test_status_refuses_staff_superuser_deletion_pending_and_missing(self):
        """无参数；运营不得调整管理身份、删除待办和不存在目标。"""
        for changes in ({'is_staff': True}, {'is_superuser': True}, {'status': 'deletion_pending'}):
            User.objects.filter(pk=self.target.pk).update(**changes)
            self.assertEqual(self.status().status_code, 404)
            self.manager.execute("UPDATE accounts_user SET status='active', is_staff=false, is_superuser=false WHERE id=%s", [self.target.pk])
        self.base = '/api/v1/admin/users/' + str(uuid4())
        self.assertEqual(self.status().status_code, 404)

    def test_quota_get_has_no_side_effect_and_put_uses_revision_and_floor(self):
        """无参数；未用额度仅返回默认投影，PUT和消费共享revision。"""
        path = self.base + '/quota'
        result = self.browser.get(path)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['revision'], 0)
        with owner_transaction(self.target.pk):
            self.assertFalse(QuotaBucket.objects.filter(owner=self.target).exists())
        response = self.write('put', path, {'limit_runs': 10, 'expected_revision': 0})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()['limit_runs'], response.json()['revision']), (10, 1))
        self.assertEqual(self.write('put', path, {'limit_runs': 11, 'expected_revision': 0}).status_code, 409)
        with owner_transaction(self.target.pk):
            QuotaBucket.objects.filter(owner=self.target).update(reserved_runs=3, settled_runs=2, revision=2)
        self.assertEqual(self.write('put', path, {'limit_runs': 4, 'expected_revision': 2}).status_code, 409)
        response = self.write('put', path, {'limit_runs': 5, 'expected_revision': 2})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['revision'], 3)

    def test_invitation_capture_is_private_replay_safe_and_not_a_mail_claim(self):
        """无参数；只在0600文件中交付令牌，数据库/公开幂等响应无明文。"""
        # 删除未使用普通账号，使其邮箱可接收邀请；保留UUID用于精确清理。
        User.objects.filter(pk=self.target.pk).delete()
        key = uuid4().hex
        result = self.write('post', '/api/v1/admin/invitations', {'email': self.target.email}, key)
        self.assertEqual(result.status_code, 201, result.content)
        body = result.json()
        self.assertEqual(set(body), {'delivery', 'delivery_id', 'expires_at'})
        self.assertEqual(body['delivery'], 'local_capture')
        capture = Path(self.directory.name) / ('invitation-' + body['delivery_id'] + '.json')
        self.assertEqual(capture.stat().st_mode & 0o777, 0o600)
        captured = json.loads(capture.read_text())
        self.assertEqual(captured['email'], self.target.email)
        invitation = Invitation.objects.get(email=self.target.email)
        self.assertEqual(invitation.token_hash, hashlib.sha256(captured['invite_token'].encode()).hexdigest())
        again = self.write('post', '/api/v1/admin/invitations', {'email': self.target.email}, key)
        self.assertEqual(again.json(), body)
        self.assertEqual(Invitation.objects.filter(email=self.target.email).count(), 1)
        self.assertEqual(len(list(Path(self.directory.name).glob('invitation-*'))), 1)
        stored = self.manager.execute('SELECT response FROM publishing_adminmutation WHERE owner_id=%s', [self.user.pk]).fetchall()
        self.assertNotIn(captured['invite_token'], json.dumps(stored))

    def test_invitation_existing_email_or_production_is_refused(self):
        """无参数；已注册邮箱不可重复邀请，生产环境不开放本机捕获。"""
        path = '/api/v1/admin/invitations'
        self.assertEqual(self.write('post', path, {'email': self.target.email}).status_code, 409)
        with override_settings(SB_ENV='production'):
            self.assertEqual(self.write('post', path, {'email': uuid4().hex + '@example.test'}).status_code, 503)

    def test_aggregates_current_month_and_never_open_private_rows(self):
        """无参数；真实跨owner任务计数，管理员ORM依然看不到目标任务或正文。"""
        with owner_transaction(self.target.pk):
            Job.objects.create(owner=self.target, status='queued')
            old = Job.objects.create(owner=self.target, status='failed')
            Job.objects.filter(pk=old.pk).update(created_at=timezone.now().replace(day=1)-timedelta(days=1))
        other = User.objects.create_user(uuid4().hex + '@example.test', PASSWORD, display_name='另一读者')
        self.users.append(other.pk)
        with owner_transaction(other.pk):
            Job.objects.create(owner=other, status='running')
            self.assertEqual(Job.objects.count(), 1)
        result = self.browser.get('/api/v1/admin/operations')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['total_runs'], 2)
        self.assertEqual(result.json()['run_counts'], [{'status': 'queued', 'count': 1}, {'status': 'running', 'count': 1}])
        feedback = self.browser.get('/api/v1/admin/feedback/summary')
        self.assertEqual(feedback.status_code, 200, feedback.content)
        self.assertEqual(feedback.json(), {'category_counts': [], 'total_feedback': 0})
        with owner_transaction(self.user.pk):
            self.assertEqual(Job.objects.count(), 0)
            with connection.cursor() as cursor:
                cursor.execute('SELECT count(*) FROM personal_feedback')
                self.assertEqual(cursor.fetchone()[0], 0)

    def test_permissions_csrf_recent_mfa_input_and_transaction_recheck(self):
        """无参数；真实权限撤销、CSRF和陈旧MFA均拒绝，未知输入不进入事实。"""
        self.assertEqual(Client().get('/api/v1/admin/operations').status_code, 401)
        for permission in ('operations_view', 'feedback_review', 'quota_manage', 'accounts_disable', 'accounts_invite'):
            self.manager.execute('DELETE FROM accounts_user_groups WHERE user_id=%s', [self.user.pk])
            paths = {'operations_view': '/api/v1/admin/operations', 'feedback_review': '/api/v1/admin/feedback/summary',
                'quota_manage': self.base + '/quota'}
            if permission in paths:
                self.assertEqual(self.browser.get(paths[permission]).status_code, 403)
        self.assertEqual(self.status().status_code, 403)
        self.manager.execute("INSERT INTO accounts_user_groups(user_id,group_id) SELECT %s,id FROM auth_group WHERE name='system-admin'", [self.user.pk])
        self.assertEqual(self.browser.post(self.base + '/status', {'status': 'disabled', 'expected_status': 'active',
            'reason': 'x'}, content_type='application/json').status_code, 400)
        self.assertEqual(self.write('post', self.base + '/status', {'status': 'disabled', 'expected_status': 'active',
            'reason': 'x', 'is_staff': True}).status_code, 400)
        self.browser.defaults['HTTP_X_CSRFTOKEN'] = 'invalid'
        self.assertEqual(self.status().status_code, 403)
        self.browser.defaults['HTTP_X_CSRFTOKEN'] = self.browser.get('/api/v1/auth/csrf').json()['csrf_token']
        session = self.browser.session
        state = session[SESSION_KEY]
        state['verified_at'] = (timezone.now()-timedelta(hours=1)).timestamp()
        state['started_at'] -= 3600
        state['expires_at'] -= 3600
        session[SESSION_KEY] = state
        session.save()
        self.assertEqual(self.status().status_code, 403)

    def test_quota_admin_cannot_change_usage_owner_or_delete_and_reader_cannot_aggregate(self):
        """无参数；真实SQL测试管理策略不扩张到计数篡改或owner转移。"""
        result = self.write('put', self.base + '/quota', {'limit_runs': 10, 'expected_revision': 0})
        self.assertEqual(result.status_code, 200, result.content)
        for changes in ({'reserved_runs': 1, 'revision': 2}, {'owner_id': self.user.pk, 'revision': 2}):
            with self.assertRaises(DatabaseError), owner_transaction(self.user.pk):
                QuotaBucket.objects.filter(owner=self.target).update(**changes)
        with owner_transaction(self.user.pk):
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM operations_quotabucket WHERE owner_id=%s', [self.target.pk])
                self.assertEqual(cursor.rowcount, 0)
        for function in ('sb_admin_run_counts', 'sb_admin_feedback_counts'):
            with self.assertRaises(DatabaseError), owner_transaction(self.target.pk):
                with connection.cursor() as cursor:
                    cursor.execute('SELECT * FROM ' + function + '()')
        with owner_transaction(self.target.pk):
            self.assertEqual(QuotaBucket.objects.get(owner=self.target).reserved_runs, 0)
            old_month = (timezone.now().astimezone(utc_timezone.utc).date().replace(day=1)-timedelta(days=1)).replace(day=1)
            QuotaBucket.objects.create(owner=self.target, period=old_month, limit_runs=10)
        with owner_transaction(self.user.pk):
            self.assertFalse(QuotaBucket.objects.filter(owner=self.target, period=old_month).exists())

    def test_concurrent_quota_writers_have_one_winner(self):
        """无参数；独立runtime连接同时CAS创建同月桶，只能一个成功。"""
        barrier = Barrier(2)
        def write(limit):
            """limit为两个竞争请求各自次数；共享真实已MFA会话cookie但使用独立HTTP客户端。"""
            close_old_connections()
            browser = Client(enforce_csrf_checks=True)
            browser.cookies = self.browser.cookies.copy()
            browser.defaults['HTTP_X_CSRFTOKEN'] = self.browser.defaults['HTTP_X_CSRFTOKEN']
            try:
                barrier.wait(timeout=10)
                return self.write('put', self.base + '/quota', {'limit_runs': limit, 'expected_revision': 0}, browser=browser).status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(write, [10, 20])), [200, 409])
        self.assertEqual(self.browser.get(self.base + '/quota').json()['revision'], 1)

    def test_write_rechecks_permission_inside_transaction(self):
        """无参数；初次授权后撤权限，实际事务不能写账号。"""
        from publishing.access import current_actor
        def revoked(owner, device, epoch, permission):
            """owner/device/epoch/permission为真实事务快照；仅夹具模拟另一个管理员撤权。"""
            self.manager.execute('DELETE FROM accounts_user_groups WHERE user_id=%s', [owner])
            return current_actor(owner, device, epoch, permission)
        with patch('publishing.services.current_actor', side_effect=revoked):
            self.assertEqual(self.status().status_code, 403)
        self.target.refresh_from_db()
        self.assertEqual(self.target.status, 'active')

    def test_capture_failure_rolls_back_invitation_and_idempotency(self):
        """无参数；私有目录权限不符合要求时不能声称投递成功。"""
        User.objects.filter(pk=self.target.pk).delete()
        root = Path(self.directory.name) / 'publicish'
        root.mkdir(mode=0o755)
        root.chmod(0o755)
        with override_settings(SB_PRIVATE_DATA_ROOT=root):
            response = self.write('post', '/api/v1/admin/invitations', {'email': self.target.email})
        self.assertEqual(response.status_code, 503, response.content)
        self.assertFalse(Invitation.objects.filter(email=self.target.email).exists())
        self.assertEqual(self.manager.execute('SELECT count(*) FROM publishing_adminmutation WHERE owner_id=%s', [self.user.pk]).fetchone()[0], 0)

    def test_quota_old_month_is_a_conflict_even_when_revision_is_zero(self):
        """无参数；上月打开的页面不能以相同revision静默写入新月。"""
        old = (timezone.now().astimezone(utc_timezone.utc).date().replace(day=1)-timedelta(days=1)).replace(day=1)
        response = self.write('put', self.base + '/quota',
            {'limit_runs': 10, 'expected_revision': 0, 'expected_period': old.isoformat()})
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['error']['code'], 'REVISION_CONFLICT')
        with owner_transaction(self.target.pk):
            self.assertFalse(QuotaBucket.objects.exists())

    def test_feedback_counts_real_answers_without_selecting_comments(self):
        """无参数；复用真实自编答案准备，统计多类反馈且后台不读取评论。"""
        from . import test_personal as personal_fixture
        from personal.services import create_feedback
        from personal.models import Feedback
        from django.test.utils import CaptureQueriesContext
        fixture = personal_fixture.PersonalTests(methodName='test_http_complete_flow_and_other_owner')
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        for category in ['helpful', 'helpful', 'other']:
            create_feedback(fixture.user_a, {'answer_id': fixture.answer_id, 'category': category,
                'comment': '此处有不应进入后台的私有评论'})
        other = personal_fixture.PersonalTests(methodName='test_http_complete_flow_and_other_owner')
        self.addCleanup(other.doCleanups)
        other.setUp()
        create_feedback(other.user_a, {'answer_id': other.answer_id, 'category': 'helpful', 'comment': '另一用户私有评论'})
        with CaptureQueriesContext(connection) as queries:
            response = self.browser.get('/api/v1/admin/feedback/summary')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {'category_counts': [{'category': 'helpful', 'count': 3},
            {'category': 'other', 'count': 1}], 'total_feedback': 4})
        self.assertNotIn('comment', ' '.join(query['sql'] for query in queries))
        with owner_transaction(self.user.pk):
            self.assertFalse(Feedback.objects.exists())
        with owner_transaction(other.user_a.pk):
            self.assertEqual(Feedback.objects.count(), 1)
