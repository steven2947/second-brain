"""隐私生命周期使用独占测试库、自编账号和私有临时目录验证。"""
import json
from unittest.mock import patch
from datetime import timedelta
from tempfile import TemporaryDirectory
from uuid import uuid4
from django.test import Client
from django.contrib.sessions.models import Session
from django.conf import settings
from django.utils import timezone
from psycopg.types.json import Jsonb
from access.context import owner_transaction
from problems.models import Problem, IdempotencyRecord
from problems.services import create_draft
from tests.knowledge_fixtures import KnowledgeFixtureCase


class PrivacyTests(KnowledgeFixtureCase):
    """本人导出、删除、恢复与注销均通过真实HTTP和RLS执行。"""

    def setUp(self):
        """无参数；每例独立临时导出目录，不接触真实账号或书库。"""
        super().setUp()
        self.addCleanup(self.cleanup_private)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        override = self.settings(SB_PRIVATE_DATA_ROOT=self.directory.name + '/private',
            SB_DELETION_LEDGER_ROOT=self.directory.name + '/ledger')
        override.enable()
        self.addCleanup(override.disable)
        self.password = 'Privacy-Test-Password-732!'
        self.user_a.set_password(self.password)
        self.user_a.save(update_fields=['password'])
        self.browser = Client(enforce_csrf_checks=True, REMOTE_ADDR='fd00::' + self.owner_a.hex[:4])
        token = self.browser.get('/api/v1/auth/csrf').json()['csrf_token']
        response = self.browser.post('/api/v1/auth/login', {'email': self.user_a.email,
            'password': self.password}, content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        session_key = self.browser.cookies[settings.SESSION_COOKIE_NAME].value
        self.addCleanup(lambda: Session.objects.filter(session_key=session_key).delete())
        self.browser.defaults['HTTP_X_CSRFTOKEN'] = self.browser.get('/api/v1/auth/csrf').json()['csrf_token']
        self.problem = create_draft(self.user_a, {'question': '我的私有原始问题', 'goal': 'act',
            'release_id': self.release_a}, str(uuid4()))

    def cleanup_private(self):
        """无参数；仅清理自编owner，新增表在迁移存在时删除。"""
        owners = [self.owner_a, self.owner_b, self.owner_c]
        self.manager.execute('UPDATE problems_message SET run_id=NULL WHERE owner_id=ANY(%s)', [owners])
        for table in ('personal_feedback', 'personal_actionrecord', 'personal_bookmark', 'learning_learningturn',
                'operations_usageentry', 'operations_runreservation', 'operations_quotabucket', 'answers_answer',
                'runs_jobevent', 'runs_analysisrun', 'runs_job', 'learning_learningsession', 'problems_message',
                'operations_personalexport', 'problems_idempotencyrecord', 'problems_problem'):
            if self.manager.execute('SELECT to_regclass(%s)', [table]).fetchone()[0]:
                self.manager.execute(f'DELETE FROM {table} WHERE owner_id=ANY(%s)', [owners])

    def personal_content(self):
        """无参数；真实发布自编答案、学习原问答以及收藏/行动/反馈。"""
        from knowledge.repository import KnowledgeRepository
        from runs.services import send_message, get_job
        from runs.worker import process_one
        from tests.answer_fixtures import AnswerProvider
        from tests.test_learning import LearningProvider
        from learning import services as learning
        from personal import services as personal
        self.change('knowledge_rightsrecord', self.right_a, allowed_uses=Jsonb(['browse', 'quote', 'analyze']))
        queued = send_message(self.user_a, self.problem['id'], {'content': '今天开始琥珀试行。',
            'intent': 'analyze_now', 'client_message_id': uuid4(), 'expected_revision': 0}, str(uuid4()))
        self.assertTrue(process_one(self.owner_a, provider=AnswerProvider()))
        answer = get_job(self.user_a, queued['job_id'])['result_ref']
        self.assertIsNotNone(answer)
        cards = [row['card_id'] for row in KnowledgeRepository(self.user_a).list_cards(self.release_a)['items']]
        session = learning.create_session(self.user_a, {'release_id': str(self.release_a),
            'basis_card_ids': cards, 'goal': '我的学习目标', 'problem_id': self.problem['id']}, str(uuid4()))
        learning.send_message(self.user_a, session['id'], {'content': '我的学习原始请求', 'client_message_id': str(uuid4()),
            'expected_revision': 0, 'mode': 'explain'}, str(uuid4()))
        self.assertTrue(process_one(self.owner_a, provider=LearningProvider()))
        personal.save_bookmark(self.user_a, self.release_a, cards[0], {'note': '本人收藏笔记'})
        action = personal.create_action(self.user_a, {'answer_id': answer, 'action_index': 0})
        personal.update_action(self.user_a, action['id'], {'expected_revision': 0, 'observation': '本人行动观察'})
        personal.create_feedback(self.user_a, {'answer_id': answer, 'category': 'helpful', 'comment': '本人反馈'})
        return answer, session

    def request_export(self, scope='all_personal', key=None):
        """scope/key为本例导出选择与幂等键。"""
        return self.browser.post('/api/v1/me/exports', {'scope': scope, 'password': self.password},
            content_type='application/json', HTTP_IDEMPOTENCY_KEY=key or str(uuid4()))

    def test_export_is_queued_private_and_downloadable(self):
        """排队后由worker生成真实JSON；公开文件不含core或密码。"""
        response = self.request_export()
        self.assertEqual(response.status_code, 202, response.content)
        from operations.export_worker import process_one
        metadata = response.json()
        self.assertEqual(metadata['status'], 'queued')
        path = '/api/v1/me/exports/' + metadata['id']
        self.assertEqual(self.browser.get(path + '/download').status_code, 409)
        self.assertTrue(process_one(self.owner_a))
        self.assertEqual(self.browser.get(path).json()['status'], 'ready')
        downloaded = self.browser.get(path + '/download')
        self.assertEqual(downloaded.status_code, 200, downloaded.content)
        self.assertIn('attachment', downloaded['Content-Disposition'])
        payload = downloaded.json()
        self.assertEqual((payload['schema_version'], payload['export_id']), (1, metadata['id']))
        self.assertEqual(payload['problems'][0]['original_question'], '我的私有原始问题')
        for secret in ('core_state', 'internal_packet', 'internal_request', self.password):
            self.assertNotIn(secret, downloaded.content.decode())

    def test_delete_restore_revision_and_trash(self):
        """删除推进修订，子域不可读，30天内恢复为归档。"""
        path = '/api/v1/problems/' + self.problem['id']
        response = self.browser.delete(path, {'expected_revision': 0}, content_type='application/json')
        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(self.browser.get(path).status_code, 404)
        trash = self.browser.get('/api/v1/me/trash').json()['items']
        self.assertEqual((trash[0]['id'], trash[0]['revision']), (self.problem['id'], 1))
        response = self.browser.post(path + '/restore', {'expected_revision': 0}, content_type='application/json')
        self.assertEqual(response.status_code, 409)
        restored = self.browser.post(path + '/restore', {'expected_revision': 1}, content_type='application/json')
        self.assertEqual(restored.status_code, 200, restored.content)
        self.assertEqual((restored.json()['status'], restored.json()['revision']), ('archived', 2))

    def test_export_password_csrf_idempotency_and_owner(self):
        """密码必须重验，幂等摘要不含密码，其他用户和匿名均不能读取。"""
        key = str(uuid4())
        first = self.request_export(key=key)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(self.request_export(key=key).json()['id'], first.json()['id'])
        bad = self.browser.post('/api/v1/me/exports', {'scope': 'all_personal', 'password': 'wrong'},
            content_type='application/json', HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(self.request_export(scope='learning', key=key).status_code, 409)
        with owner_transaction(self.owner_a):
            row = IdempotencyRecord.objects.get(route_scope='/api/v1/me/exports')
            self.assertNotIn(self.password, json.dumps(row.response_payload))
        self.assertEqual(Client().get('/api/v1/me/exports/' + first.json()['id']).status_code, 401)
        self.browser.defaults.pop('HTTP_X_CSRFTOKEN')
        self.assertEqual(self.request_export().status_code, 403)

    def test_account_deletion_revokes_session_immediately(self):
        """再次核验密码和确认文案，随后身份epoch生效。"""
        response = self.browser.post('/api/v1/me/deletion', {'password': self.password,
            'confirmation': '删除我的账号'}, content_type='application/json')
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(response.json()['status'], 'pending')
        self.assertEqual(self.browser.get('/api/v1/me').status_code, 401)
        self.user_a.refresh_from_db()
        self.assertEqual((self.user_a.status, self.user_a.auth_epoch), ('deletion_pending', 1))

    def test_trash_expiry_refuses_restore(self):
        """超过30天即拒绝恢复，不依赖清理是否已经执行。"""
        with owner_transaction(self.owner_a):
            Problem.objects.filter(pk=self.problem['id']).update(status='deleted',
                deleted_at=timezone.now() - timedelta(days=31), revision=1)
        response = self.browser.post('/api/v1/problems/' + self.problem['id'] + '/restore',
            {'expected_revision': 1}, content_type='application/json')
        self.assertEqual(response.status_code, 410, response.content)

    def test_export_expiry_revocation_and_deleted_snapshot(self):
        """24小时和实时撤权/删除都拒绝旧文件，用户原问题可重新导出。"""
        from operations.export_worker import process_one
        from operations.models import PersonalExport
        metadata = self.request_export().json()
        self.assertTrue(process_one(self.owner_a))
        path = '/api/v1/me/exports/' + metadata['id'] + '/download'
        self.change('knowledge_librarygrant', self.grant_a, status='revoked', revoked_at=timezone.now())
        self.assertEqual(self.browser.get(path).status_code, 409)
        replacement = self.request_export().json()
        process_one(self.owner_a)
        downloaded = self.browser.get('/api/v1/me/exports/' + replacement['id'] + '/download')
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.json()['problems'][0]['original_question'], '我的私有原始问题')
        with owner_transaction(self.owner_a):
            PersonalExport.objects.filter(pk=replacement['id']).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.browser.get('/api/v1/me/exports/' + replacement['id'] + '/download').status_code, 410)
        self.browser.delete('/api/v1/problems/' + self.problem['id'], {'expected_revision': 0}, content_type='application/json')
        third = self.request_export().json()
        process_one(self.owner_a)
        self.assertEqual(self.browser.get('/api/v1/me/exports/' + third['id'] + '/download').json()['problems'], [])

    def test_lease_fencing_bounds_and_runtime_rls(self):
        """重启重领取令牌后旧执行者不能发布；无上下文不可读取导出。"""
        from operations.export_worker import claim, execute, process_one
        from operations.models import PersonalExport
        metadata = self.request_export().json()
        first = claim(self.owner_a)
        self.assertIsNotNone(first)
        with owner_transaction(self.owner_a):
            PersonalExport.objects.filter(pk=metadata['id']).update(lease_until=timezone.now() - timedelta(seconds=1))
        second = claim(self.owner_a)
        self.assertNotEqual(first.token, second.token)
        self.assertFalse(execute(first))
        self.assertTrue(execute(second))
        self.assertEqual(PersonalExport.objects.count(), 0)
        with owner_transaction(self.owner_b):
            self.assertEqual(PersonalExport.objects.count(), 0)
        self.request_export()
        with patch('operations.export_worker.MAX_RECORDS', 0):
            process_one(self.owner_a)
        self.assertIn('EXPORT_TOO_LARGE', [row['error_code'] for row in self.browser.get('/api/v1/me/exports').json()['items']])

    def test_due_maintenance_purges_identity_and_replays_external_ledger(self):
        """独立迁移连接清空在线个人数据；恢复旧账号状态后删除清单可重放。"""
        from operations import maintenance
        from operations.models import PersonalExport
        from operations.export_worker import process_one
        original_email = self.user_a.email
        self.request_export()
        process_one(self.owner_a)
        self.browser.post('/api/v1/me/deletion', {'password': self.password,
            'confirmation': '删除我的账号'}, content_type='application/json')
        now = timezone.now() + timedelta(days=8)
        result = maintenance.maintain_owner(self.manager, self.owner_a, now=now)
        self.assertTrue(result['account_purged'])
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.status, 'disabled')
        self.assertNotEqual(self.user_a.email, original_email)
        self.assertEqual((self.user_a.display_name, self.user_a.password), ('已删除账号', '!'))
        with owner_transaction(self.owner_a):
            self.assertEqual((Problem.objects.count(), IdempotencyRecord.objects.count(), PersonalExport.objects.count()), (0, 0, 0))
        self.change('accounts_user', self.owner_a, status='active', email=original_email, display_name='恢复的旧个人信息')
        self.assertTrue(maintenance.maintain_owner(self.manager, self.owner_a, now=now, replay=True)['account_purged'])
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.display_name, '已删除账号')

    def test_readable_exports_scope_quotes_and_permission_omissions(self):
        """正式答案等同现有公开投影；学习导出有原问答，失权仍保留本人输入并明确省略知识。"""
        from operations.export_worker import process_one
        from answers.services import get_answer
        answer, session = self.personal_content()
        metadata = self.request_export().json()
        process_one(self.owner_a)
        path = '/api/v1/me/exports/' + metadata['id'] + '/download'
        full = self.browser.get(path)
        self.assertEqual(full.status_code, 200, full.content)
        full = full.json()
        self.assertEqual(full['answers'][0], get_answer(self.user_a, answer))
        self.assertEqual(len(full['learning_turns']), 2)
        self.assertEqual(full['bookmarks'][0]['note'], '本人收藏笔记')
        self.assertEqual(full['actions'][0]['observation'], '本人行动观察')
        self.assertEqual(full['feedback'][0]['comment'], '本人反馈')
        self.assertEqual(full['profile']['email'], self.user_a.email)
        self.change('knowledge_rightsrecord', self.right_a, allowed_uses=Jsonb(['browse', 'analyze']))
        self.assertEqual(self.browser.get(path).status_code, 409)
        without_quotes = self.request_export().json()
        process_one(self.owner_a)
        self.assertEqual(self.browser.get('/api/v1/me/exports/' + without_quotes['id'] + '/download').json()['answers'][0], get_answer(self.user_a, answer))
        self.change('knowledge_librarygrant', self.grant_a, status='revoked', revoked_at=timezone.now())
        lost = self.request_export().json()
        process_one(self.owner_a)
        data = self.browser.get('/api/v1/me/exports/' + lost['id'] + '/download').json()
        self.assertEqual(data['answers'], [])
        self.assertEqual(data['learning_turns'][0]['content']['text'], '我的学习原始请求')
        self.assertEqual(len(data['learning_turns']), 1)
        self.assertIsNone(data['actions'][0]['advice'])
        self.assertGreaterEqual(len(data['omissions']), 3)
        for scope in ('problems', 'learning'):
            metadata = self.request_export(scope).json()
            process_one(self.owner_a)
            data = self.browser.get('/api/v1/me/exports/' + metadata['id'] + '/download').json()
            self.assertEqual(data['scope'], scope)
            self.assertEqual(data['bookmarks'], [])
            self.assertEqual(data['learning'] if scope == 'problems' else data['problems'], [])

    def test_deleted_parent_hides_learning_and_fences_running_reservation(self):
        """删除父问题后学习详情/消息/任务全部不可读，在途令牌失效且未调用额度释放。"""
        from learning import services as learning
        from operations.models import RunReservation
        from runs.queue import claim, heartbeat
        from runs.models import Job
        _, session = self.personal_content()
        session = learning.get_detail(self.user_a, session['id'], {})['session']
        accepted = learning.send_message(self.user_a, session['id'], {'content': '待完成学习请求', 'client_message_id': str(uuid4()),
            'expected_revision': session['revision'], 'mode': 'explain'}, str(uuid4()))
        lease = claim(self.owner_a)
        self.assertIsNotNone(lease)
        revision = self.browser.get('/api/v1/problems/' + self.problem['id']).json()['revision']
        self.assertEqual(self.browser.delete('/api/v1/problems/' + self.problem['id'], {'expected_revision': revision},
            content_type='application/json').status_code, 204)
        self.assertFalse(heartbeat(lease))
        prefix = '/api/v1/learning/' + session['id']
        self.assertEqual(self.browser.get(prefix).status_code, 404)
        self.assertEqual(self.browser.get(prefix + '/jobs/' + accepted['job_id']).status_code, 404)
        self.assertEqual(self.browser.get('/api/v1/learning').json()['items'], [])
        with owner_transaction(self.owner_a):
            self.assertEqual(Job.objects.get(pk=accepted['job_id']).status, 'cancelled')
            self.assertEqual(RunReservation.objects.get(run_id=lease.run_id).state, 'released')

    def test_full_account_purge_removes_private_children_and_preserves_knowledge(self):
        """真实答案/学习/固定输入/反馈/幂等都清空；共享知识保留，无身份用量摘要可追踪。"""
        from operations.maintenance import maintain_owner
        from operations.export_worker import process_one
        from pathlib import Path
        self.personal_content()
        receipt = uuid4()
        self.manager.execute('''INSERT INTO publishing_adminmutation (id,owner_id,operation,key,body_hash,response,response_status,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,200,%s,%s)''', [receipt, self.owner_b,
            f'POST:/api/v1/admin/users/{self.owner_a}/status', str(uuid4()), 'a' * 64,
            Jsonb({'id': str(self.owner_a), 'email': self.user_a.email, 'display_name': '旧个人资料'}), timezone.now(), timezone.now()])
        self.addCleanup(lambda: self.manager.execute('DELETE FROM publishing_adminmutation WHERE id=%s', [receipt]))
        self.request_export()
        process_one(self.owner_a)
        path = Path(settings.SB_PRIVATE_DATA_ROOT) / ('invitation-' + str(uuid4()) + '.json')
        path.write_text(json.dumps({'email': self.user_a.email, 'invite_token': 'self-authored-fixture', 'expires_at': timezone.now().isoformat()}))
        self.browser.post('/api/v1/me/deletion', {'password': self.password, 'confirmation': '删除我的账号'}, content_type='application/json')
        result = maintain_owner(self.manager, self.owner_a, now=timezone.now() + timedelta(days=8))
        self.assertTrue(result['account_purged'])
        self.assertFalse(path.exists())
        self.assertIsNone(self.manager.execute('SELECT id FROM publishing_adminmutation WHERE id=%s', [receipt]).fetchone())
        for table in ('problems_problem', 'problems_message', 'runs_analysisrun', 'runs_job', 'learning_learningsession',
                'learning_learningturn', 'answers_answer', 'personal_bookmark', 'personal_actionrecord', 'personal_feedback',
                'operations_usageentry', 'operations_runreservation', 'operations_quotabucket', 'problems_idempotencyrecord',
                'operations_personalexport', 'knowledge_librarygrant'):
            self.assertEqual(self.manager.execute(f'SELECT count(*) FROM {table} WHERE owner_id=%s', [self.owner_a]).fetchone()[0], 0, table)
        self.assertIsNotNone(self.manager.execute('SELECT id FROM knowledge_libraryrelease WHERE id=%s', [self.release_a]).fetchone())
        self.assertEqual(list((Path(settings.SB_PRIVATE_DATA_ROOT) / 'exports' / str(self.owner_a)).glob('*.json')), [])

    def test_support_cancel_reauth_and_runtime_maintenance_denied(self):
        """取消必须仍在冷静期并复验密码；旧grant/session不会复活，runtime不能维护。"""
        from operations.maintenance import cancel_deletion, require_manager
        from django.db import connection
        self.browser.post('/api/v1/me/deletion', {'password': self.password, 'confirmation': '删除我的账号'}, content_type='application/json')
        with self.assertRaises(ValueError):
            cancel_deletion(self.manager, self.owner_a, 'wrong', '本人申请取消')
        cancel_deletion(self.manager, self.owner_a, self.password, '本人申请取消')
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.status, 'active')
        self.assertGreaterEqual(self.user_a.auth_epoch, 2)
        self.assertEqual(self.browser.get('/api/v1/me').status_code, 401)
        self.assertEqual(self.manager.execute('SELECT status FROM knowledge_librarygrant WHERE id=%s', [self.grant_a]).fetchone(), ('revoked',))
        with self.assertRaises(ValueError):
            require_manager(connection.connection)

    def test_account_not_due_and_trash_due_cleanup(self):
        """7天冷静期和30天回收期严格执行；只清到期父域及关联学习，不动收藏。"""
        from operations.maintenance import maintain_owner
        self.personal_content()
        revision = self.browser.get('/api/v1/problems/' + self.problem['id']).json()['revision']
        self.browser.delete('/api/v1/problems/' + self.problem['id'], {'expected_revision': revision}, content_type='application/json')
        first = maintain_owner(self.manager, self.owner_a, now=timezone.now() + timedelta(days=29))
        self.assertEqual(first['problems_purged'], 0)
        later = maintain_owner(self.manager, self.owner_a, now=timezone.now() + timedelta(days=31))
        self.assertEqual(later['problems_purged'], 1)
        self.assertEqual(self.manager.execute('SELECT count(*) FROM learning_learningsession WHERE owner_id=%s', [self.owner_a]).fetchone()[0], 0)
        self.assertEqual(self.manager.execute('SELECT count(*) FROM personal_bookmark WHERE owner_id=%s', [self.owner_a]).fetchone()[0], 1)

    def test_export_download_rechecks_permission_after_file_read(self):
        """打开文件前发生撤权，最后一次授权检查仍拒绝整个附件。"""
        from operations import export_worker
        metadata = self.request_export().json()
        export_worker.process_one(self.owner_a)
        original = export_worker.file_path
        def revoke_before_open(owner, key, **kwargs):
            """owner/key为已定位文件；模拟从首次鉴权到文件读取之间的撤权。"""
            self.change('knowledge_librarygrant', self.grant_a, status='revoked', revoked_at=timezone.now())
            return original(owner, key, **kwargs)
        with patch.object(export_worker, 'file_path', revoke_before_open):
            response = self.browser.get('/api/v1/me/exports/' + metadata['id'] + '/download')
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('我的私有原始问题', response.content.decode())

    def test_newest_export_visible_after_twenty_items_and_cursor_binding(self):
        """超过一页仍先显示最新任务；游标不能跨owner或篡改页大小。"""
        from operations.models import PersonalExport
        from operations.privacy import list_exports
        from problems.services import ProblemError
        with owner_transaction(self.owner_a):
            for _ in range(22):
                PersonalExport.objects.create(owner=self.user_a, scope='all_personal', status='failed',
                    auth_epoch=0, access_revision=0, deadline=timezone.now())
        latest = self.request_export().json()
        page = self.browser.get('/api/v1/me/exports').json()
        self.assertEqual(page['items'][0]['id'], latest['id'])
        self.assertEqual(len(page['items']), 20)
        next_page = self.browser.get('/api/v1/me/exports', {'cursor': page['next_cursor']}).json()
        self.assertEqual(len(next_page['items']), 3)
        self.assertFalse(set(item['id'] for item in page['items']) & set(item['id'] for item in next_page['items']))
        with self.assertRaises(ProblemError):
            list_exports(self.user_b, {'cursor': page['next_cursor']})
        self.assertEqual(self.browser.get('/api/v1/me/exports', {'cursor': page['next_cursor'], 'limit': 19}).status_code, 400)

    def test_export_integrity_expiry_file_cleanup_and_other_owner(self):
        """错误owner、文件损坏与到期都不能读取附件；只清确切到期文件。"""
        from operations.export_worker import process_one, file_path, download
        from operations.models import PersonalExport
        from operations.maintenance import maintain_owner
        from problems.services import ProblemError
        metadata = self.request_export().json()
        process_one(self.owner_a)
        with self.assertRaises(ProblemError):
            download(self.user_b, metadata['id'])
        with owner_transaction(self.owner_a):
            row = PersonalExport.objects.get(pk=metadata['id'])
        path = file_path(self.owner_a, row.file_key)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        path.write_bytes(b'{"forged":true}')
        self.assertEqual(self.browser.get('/api/v1/me/exports/' + metadata['id'] + '/download').status_code, 503)
        maintain_owner(self.manager, self.owner_a, now=timezone.now() + timedelta(hours=25))
        self.assertFalse(path.exists())

    def test_export_retries_stop_at_three_and_no_model_usage(self):
        """租约连续过期后最多三次尝试；导出完全不创建模型账本或消费额度。"""
        from operations.export_worker import claim
        from operations.models import PersonalExport, UsageEntry, RunReservation
        metadata = self.request_export().json()
        for attempt in range(1, 4):
            lease = claim(self.owner_a)
            self.assertEqual(lease.attempt, attempt)
            with owner_transaction(self.owner_a):
                PersonalExport.objects.filter(pk=metadata['id']).update(lease_until=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(claim(self.owner_a))
        with owner_transaction(self.owner_a):
            self.assertEqual(PersonalExport.objects.get(pk=metadata['id']).status, 'failed')
            self.assertEqual((UsageEntry.objects.count(), RunReservation.objects.count()), (0, 0))

    def test_retention_prunes_only_terminal_idempotency_and_internal_snapshots(self):
        """终态7天快照/事件和48小时幂等清理；仍在途请求保留，正式答案仍可读。"""
        from operations.maintenance import maintain_owner
        from answers.services import get_answer
        from runs.models import AnalysisRun, JobEvent
        answer, _ = self.personal_content()
        original = get_answer(self.user_a, answer)
        metadata = self.request_export().json()
        self.manager.execute('UPDATE problems_idempotencyrecord SET expires_at=%s WHERE owner_id=%s', [timezone.now() - timedelta(days=3), self.owner_a])
        maintain_owner(self.manager, self.owner_a, now=timezone.now() + timedelta(days=8))
        with owner_transaction(self.owner_a):
            self.assertFalse(AnalysisRun.objects.exclude(internal_state={}).exists())
            self.assertEqual(JobEvent.objects.count(), 0)
            self.assertEqual(IdempotencyRecord.objects.count(), 1)
            self.assertEqual(str(IdempotencyRecord.objects.get().resource_id), metadata['id'])
        self.assertEqual(get_answer(self.user_a, answer), original)
