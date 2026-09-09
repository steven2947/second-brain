"""独占真实PG验证双连接消费、运行worker和仅目标隐私清理。"""
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event
from unittest.mock import patch, MagicMock

from django.core.management import call_command
from django.db import connections
from django.utils import timezone

from accounts.models import PasswordResetDelivery, User
from accounts.password_reset import capture_directory, confirm_reset, request_reset
from accounts.reset_worker import claim, process_one
from accounts.services import AccountError
from tests.knowledge_fixtures import KnowledgeFixtureCase
from tests.test_accounts import PASSWORD
from tests.test_password_reset import SMTP_SETTINGS


class PasswordResetIntegrationTests(KnowledgeFixtureCase):
    """自编完整授权夹具无外层事务，线程与维护连接可观察真实提交。"""

    def setUp(self):
        """无参数；独立私有目录与两个可找回账号，不修改主库或真实身份。"""
        super().setUp()
        self.addCleanup(self.cleanup_reset)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        override = self.settings(SB_MAIL_MODE='local_capture', SB_PRIVATE_DATA_ROOT=self.directory / 'private',
            SB_DELETION_LEDGER_ROOT=self.directory / 'ledger')
        override.enable()
        self.addCleanup(override.disable)
        for user in (self.user_a, self.user_b):
            user.set_password(PASSWORD)
            user.save(update_fields=['password'])

    def cleanup_reset(self):
        """无参数；只清除本例队列，先于既有夹具账号外键清理。"""
        self.manager.execute('DELETE FROM accounts_passwordresetdelivery WHERE user_id=ANY(%s)',
            [[self.owner_a, self.owner_b, self.owner_c]])

    def issue(self, user):
        """user为本例账号；经过真实队列和捕获获得私有令牌。"""
        self.assertEqual(request_reset(user.email)['status'], 'accepted')
        self.assertTrue(process_one(user.pk))
        row = PasswordResetDelivery.objects.filter(user=user).latest('created_at')
        path = capture_directory(user.pk) / (str(row.pk) + '.json')
        token = json.loads(path.read_text())['body'].split('#token=', 1)[1].split()[0]
        return row, path, token

    def test_concurrent_confirm_consumes_once_and_preserves_revoked_grant(self):
        """无参数；两个独立runtime连接竞争同一token，只有一个成功且不会恢复知识授权。"""
        self.change('knowledge_librarygrant', self.grant_a, status='revoked', revoked_at=timezone.now())
        row, _, token = self.issue(self.user_a)
        barrier = Barrier(2)

        def consume(index):
            """index区分两条自编密码；每个线程使用独立runtime连接并在结束关闭。"""
            try:
                barrier.wait(timeout=5)
                confirm_reset(token, f'Concurrent-Recovery-{index}-Password-692!')
                return 'consumed'
            except AccountError as error:
                return error.code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(consume, [1, 2]))
        self.assertCountEqual(outcomes, ['consumed', 'RESET_INVALID'])
        self.assertEqual(PasswordResetDelivery.objects.get(pk=row.pk).status, 'consumed')
        self.assertEqual(self.manager.execute('SELECT status FROM knowledge_librarygrant WHERE id=%s', [self.grant_a]).fetchone()[0], 'revoked')
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.auth_epoch, 1)

    def test_expiry_maintenance_cleans_only_target_queue_and_capture(self):
        """无参数；到期维护删除A的重置邮箱/链接，B未到期捕获和任务保留。"""
        from operations.maintenance import maintain_owner
        row_a, path_a, _ = self.issue(self.user_a)
        row_b, path_b, _ = self.issue(self.user_b)
        now = timezone.now() + timedelta(minutes=31)
        PasswordResetDelivery.objects.filter(pk=row_b.pk).update(expires_at=now + timedelta(minutes=30))
        result = maintain_owner(self.manager, self.owner_a, now=now)
        self.assertFalse(result['account_purged'])
        self.assertEqual(result['files_removed'], 1)
        self.assertFalse(path_a.exists())
        self.assertFalse(PasswordResetDelivery.objects.filter(pk=row_a.pk).exists())
        self.assertTrue(path_b.exists())
        self.assertTrue(PasswordResetDelivery.objects.filter(pk=row_b.pk).exists())

    def test_deletion_clears_links_now_and_purges_new_records_when_due(self):
        """无参数；注销立刻清除捕获、fence队列，七天维护清理记录且不影响另一个账号。"""
        from operations.maintenance import maintain_owner
        from operations.privacy import request_deletion
        row, path, token = self.issue(self.user_a)
        _, other_path, _ = self.issue(self.user_b)
        response = request_deletion(self.user_a, {'password': PASSWORD, 'confirmation': '删除我的账号'})
        self.assertEqual(response['status'], 'pending')
        self.assertFalse(path.exists())
        self.assertEqual(PasswordResetDelivery.objects.get(pk=row.pk).status, 'cancelled')
        with self.assertRaises(AccountError) as caught:
            confirm_reset(token, 'Deleted-Recovery-Password-826!')
        self.assertEqual(caught.exception.code, 'RESET_INVALID')
        result = maintain_owner(self.manager, self.owner_a, now=timezone.now() + timedelta(days=8))
        self.assertTrue(result['account_purged'])
        self.assertFalse(PasswordResetDelivery.objects.filter(user_id=self.owner_a).exists())
        self.assertTrue(other_path.exists())
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.status, 'disabled')

    def test_existing_worker_processes_reset_queue_with_runtime_role(self):
        """无参数；现有runworker连接生命周期真实运行，只使用runtime且不输出邮箱/令牌。"""
        request_reset(self.user_a.email)
        output = io.StringIO()
        call_command('runworker', once=True, owner=self.owner_a, stdout=output)
        self.assertEqual(PasswordResetDelivery.objects.get(user_id=self.owner_a).status, 'sent')
        self.assertNotIn(self.user_a.email, output.getvalue())
        self.assertNotIn('#token=', output.getvalue())
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT current_user')
            self.assertEqual(cursor.fetchone()[0], 'sb_runtime')

    def test_repeated_worker_crashes_end_at_retry_limit(self):
        """无参数；领取后崩溃也消耗有限重试，重启不能无限持有旧令牌。"""
        request_reset(self.user_a.email)
        for _ in range(3):
            identifier, lease = claim(self.owner_a)
            self.assertIsNotNone(lease)
            PasswordResetDelivery.objects.filter(pk=identifier).update(lease_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(claim(self.owner_a), (identifier, None))
        row = PasswordResetDelivery.objects.get(pk=identifier)
        self.assertEqual((row.status, row.attempts, row.binding), ('failed', 3, ''))
        self.assertIsNone(claim(self.owner_a))

    def test_request_does_not_wait_for_smtp_holding_identity_lock(self):
        """无参数；替身SMTP被阻塞期间，同一邮箱的新申请可独立完成，不暴露发送耗时。"""
        started, release = Event(), Event()

        def send(messages):
            """messages来自Django邮件对象；阻塞仅自编替身，不连接真实SMTP。"""
            started.set()
            if not release.wait(timeout=5):
                raise TimeoutError('fixture timeout')
            return 1

        def worker():
            """无参数；独立runtime连接在退出时关闭，避免测试库残留会话。"""
            try:
                return process_one(self.owner_a)
            finally:
                connections.close_all()

        def enqueue():
            """无参数；另一runtime连接申请相同账号，不等待正在发送的身份锁。"""
            try:
                return request_reset(self.user_a.email)
            finally:
                connections.close_all()

        with self.settings(**SMTP_SETTINGS), patch('accounts.reset_worker.get_connection') as factory:
            connection = MagicMock()
            connection.send_messages.side_effect = send
            factory.return_value.__enter__.return_value = connection
            request_reset(self.user_a.email)
            with ThreadPoolExecutor(max_workers=2) as pool:
                sending = pool.submit(worker)
                try:
                    self.assertTrue(started.wait(timeout=5))
                    queued = pool.submit(enqueue)
                    self.assertEqual(queued.result(timeout=2), {'status': 'accepted', 'delivery': 'smtp'})
                    self.assertFalse(sending.done())
                finally:
                    release.set()
                self.assertTrue(sending.result(timeout=5))
