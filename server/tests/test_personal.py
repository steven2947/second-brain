"""真实PG、受限runtime与会话HTTP验证收藏、行动和反馈；不调用真实模型。"""
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import connection, transaction, IntegrityError, DatabaseError
from django.test import Client
from django.utils import timezone
from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb
from access.context import owner_transaction
from answers.models import Answer
from config.contracts import build_contract
from knowledge.repository import KnowledgeRepository
from operations.models import UsageEntry
from personal import services
from personal.models import Bookmark, ActionRecord, Feedback
from problems.services import create_draft, ProblemError
from runs.services import send_message, get_job
from runs.worker import process_one
from tests.answer_fixtures import AnswerProvider
from tests.knowledge_fixtures import KnowledgeFixtureCase


class PersonalTests(KnowledgeFixtureCase):
    """每例真实发布一个v3答案，独占测试库并按owner清理。"""

    def setUp(self):
        """无参数；真实知识、运行和发布构成行动事实源。"""
        super().setUp()
        self.addCleanup(self.cleanup_private)
        self.change('knowledge_rightsrecord', self.right_a, allowed_uses=Jsonb(['browse', 'quote', 'analyze']))
        self.problem = create_draft(self.user_a, {'question': '今天如何开始琥珀试行？', 'goal': 'act',
            'release_id': self.release_a}, str(uuid4()))
        accepted = send_message(self.user_a, self.problem['id'], {'content': '今天开始琥珀试行。',
            'intent': 'analyze_now', 'client_message_id': uuid4(), 'expected_revision': 0}, str(uuid4()))
        self.assertTrue(process_one(self.owner_a, provider=AnswerProvider()))
        self.answer_id = get_job(self.user_a, accepted['job_id'])['result_ref']
        self.assertIsNotNone(self.answer_id)
        self.card_ids = [item['card_id'] for item in KnowledgeRepository(self.user_a).list_cards(self.release_a)['items']]

    def cleanup_private(self):
        """无参数；只清理本fixture三owner，复合外键按反序删除。"""
        owners = [self.owner_a, self.owner_b, self.owner_c]
        self.manager.execute('UPDATE problems_message SET run_id=NULL WHERE owner_id=ANY(%s)', [owners])
        for table in ('personal_feedback', 'personal_actionrecord', 'personal_bookmark',
                      'operations_usageentry', 'operations_runreservation', 'operations_quotabucket',
                      'answers_answer', 'runs_jobevent', 'runs_analysisrun', 'runs_job',
                      'problems_message', 'problems_idempotencyrecord', 'problems_problem'):
            self.manager.execute(f'DELETE FROM {table} WHERE owner_id=ANY(%s)', [owners])

    def login(self, user):
        """user为fixture普通账号；实际登录并保留真实CSRF与session。"""
        password = 'Personal-Test-Password-732!'
        user.set_password(password)
        user.save(update_fields=['password'])
        browser = Client(enforce_csrf_checks=True)
        token = browser.get('/api/v1/auth/csrf').json()['csrf_token']
        response = browser.post('/api/v1/auth/login', {'email': user.email, 'password': password},
            content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        session_key = browser.cookies[settings.SESSION_COOKIE_NAME].value
        self.addCleanup(lambda: Session.objects.filter(session_key=session_key).delete())
        token = browser.get('/api/v1/auth/csrf').json()['csrf_token']
        browser.defaults['HTTP_X_CSRFTOKEN'] = token
        return browser

    def assert_schema(self, response, name, status=200):
        """response为真实HTTP结果；name/status是公开契约预期。"""
        self.assertEqual(response.status_code, status, response.content[:300])
        self.assertEqual(response['Cache-Control'], 'no-store')
        Draft202012Validator({'$ref': '#/components/schemas/' + name,
            'components': build_contract()['components']}).validate(response.json())
        return response.json()

    def new_action(self):
        """无参数；为本例正式答案的第一项真实行动建档。"""
        return services.create_action(self.user_a, {'answer_id': self.answer_id, 'action_index': 0})

    def test_http_complete_flow_and_other_owner(self):
        """无参数；登录A收藏/跟进行动/反馈，登录B不能读取或修改A资源。"""
        a, b = self.login(self.user_a), self.login(self.user_b)
        path = f'/api/v1/bookmarks/{self.release_a}/{self.card_ids[0]}'
        saved = self.assert_schema(a.put(path, {'note': '我的备注'}, content_type='application/json'), 'Bookmark')
        preserved = self.assert_schema(a.put(path, {}, content_type='application/json'), 'Bookmark')
        self.assertEqual((saved['id'], preserved['note']), (preserved['id'], '我的备注'))
        self.assert_schema(a.get('/api/v1/bookmarks'), 'BookmarkPage')
        self.assertEqual(b.get('/api/v1/bookmarks').json()['items'], [])
        self.assertEqual(b.put(path, {}, content_type='application/json').status_code, 404)
        action = self.assert_schema(a.post('/api/v1/actions', {'answer_id': self.answer_id, 'action_index': 0},
            content_type='application/json'), 'ActionRecord', 201)
        updated = self.assert_schema(a.patch('/api/v1/actions/' + action['id'], {'expected_revision': 0,
            'status': 'done', 'observation': '清单完成'}, content_type='application/json'), 'ActionRecord')
        self.assertEqual(updated['revision'], 1)
        again = self.assert_schema(a.post('/api/v1/actions', {'answer_id': self.answer_id, 'action_index': 0},
            content_type='application/json'), 'ActionRecord', 201)
        self.assertEqual((again['id'], again['observation']), (action['id'], '清单完成'))
        conflict = a.patch('/api/v1/actions/' + action['id'], {'expected_revision': 0,
            'observation': '旧窗口'}, content_type='application/json')
        self.assertEqual((conflict.status_code, conflict.json()['error']['current_revision']), (409, 1))
        self.assert_schema(a.get('/api/v1/actions', {'problem_id': self.problem['id'], 'status': 'done'}), 'ActionPage')
        self.assertEqual(b.get('/api/v1/actions').json()['items'], [])
        self.assertEqual(b.patch('/api/v1/actions/' + action['id'], {'expected_revision': 1,
            'status': 'doing'}, content_type='application/json').status_code, 404)
        self.assertEqual(b.post('/api/v1/actions', {'answer_id': self.answer_id, 'action_index': 0},
            content_type='application/json').status_code, 404)
        feedback = {'answer_id': self.answer_id, 'category': 'helpful', 'comment': '行动可以执行'}
        self.assert_schema(a.post('/api/v1/feedback', feedback, content_type='application/json'), 'Feedback', 201)
        self.assertEqual(b.post('/api/v1/feedback', feedback, content_type='application/json').status_code, 404)
        self.assertEqual(b.delete(path).status_code, 204)
        self.assertEqual(len(a.get('/api/v1/bookmarks').json()['items']), 1)
        self.assertEqual(a.delete(path).status_code, 204)
        self.assertEqual(a.delete(path).status_code, 204)
        with owner_transaction(self.owner_a):
            self.assertEqual(UsageEntry.objects.count(), 3)
            self.assertEqual(Feedback.objects.get().review_status, 'new')

    def test_revocation_and_expiry_hide_content_but_allow_bookmark_delete(self):
        """无参数；许可过期或撤回后不返回备注/行动/反馈目标，仍可删收藏。"""
        services.save_bookmark(self.user_a, self.release_a, self.card_ids[0], {'note': '私有原理摘记'})
        action = self.new_action()
        self.change('knowledge_librarygrant', self.grant_a, expires_at=timezone.now() - timedelta(seconds=1))
        item = services.list_bookmarks(self.user_a, {})['items'][0]
        self.assertEqual((item['available'], item['note']), (False, None))
        self.assertEqual(services.list_actions(self.user_a, {})['items'], [])
        for operation in (
            lambda: services.update_action(self.user_a, action['id'], {'expected_revision': 0, 'status': 'done'}),
            lambda: services.create_feedback(self.user_a, {'answer_id': self.answer_id, 'category': 'other', 'comment': ''}),
            lambda: services.save_bookmark(self.user_a, self.release_a, self.card_ids[0], {}),
        ):
            with self.assertRaises(Exception) as error:
                operation()
            self.assertEqual(error.exception.status, 404)
        self.change('knowledge_librarygrant', self.grant_a, expires_at=None, status='revoked', revoked_at=timezone.now())
        self.assertEqual(services.list_actions(self.user_a, {})['items'], [])
        services.delete_bookmark(self.user_a, self.release_a, self.card_ids[0])
        self.assertEqual(services.list_bookmarks(self.user_a, {})['items'], [])

    def test_invalid_inputs_csrf_and_no_fabricated_action(self):
        """无参数；未知字段、浮点/bool序号、伪目标与缺失CSRF全部拒绝。"""
        a = self.login(self.user_a)
        for index in (True, 0.0, 0.5, -1, '0'):
            response = a.post('/api/v1/actions', {'answer_id': self.answer_id, 'action_index': index}, content_type='application/json')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(a.post('/api/v1/actions', {'answer_id': self.answer_id, 'action_index': 999}, content_type='application/json').status_code, 404)
        for path, data in (
            ('/api/v1/actions', {'answer_id': self.answer_id, 'action_index': 0, 'step': '伪造动作'}),
            ('/api/v1/feedback', {'answer_id': self.answer_id, 'category': 'other', 'comment': '', 'review_status': 'reviewed'}),
        ):
            self.assertEqual(a.post(path, data, content_type='application/json').status_code, 400)
        self.assertEqual(a.post('/api/v1/feedback', {'answer_id': str(uuid4()), 'category': 'other', 'comment': ''}, content_type='application/json').status_code, 404)
        self.assertEqual(a.put(f'/api/v1/bookmarks/{self.release_a}/missing', {}, content_type='application/json').status_code, 404)
        self.assertEqual(a.post('/api/v1/actions', '{"answer_id":"' + self.answer_id + '","action_index":0,"action_index":1}', content_type='application/json').status_code, 400)
        a.defaults.pop('HTTP_X_CSRFTOKEN')
        self.assertEqual(a.post('/api/v1/actions', {'answer_id': self.answer_id, 'action_index': 0}, content_type='application/json').status_code, 403)
        self.assertEqual(Client().get('/api/v1/bookmarks').status_code, 401)

    def test_pagination_binds_owner_filter_epoch_and_expiry(self):
        """无参数；真实收藏两页不重复，游标不可跨owner/筛选/epoch或延长有效期。"""
        for card in self.card_ids[:2]:
            services.save_bookmark(self.user_a, self.release_a, card, {})
        first = services.list_bookmarks(self.user_a, {'limit': 1})
        self.assertIsNotNone(first['next_cursor'])
        second = services.list_bookmarks(self.user_a, {'limit': 1, 'cursor': first['next_cursor']})
        self.assertNotEqual(first['items'][0]['id'], second['items'][0]['id'])
        for user, query in ((self.user_b, {'limit': 1}), (self.user_a, {'limit': 2})):
            with self.assertRaises(ProblemError):
                services.list_bookmarks(user, {**query, 'cursor': first['next_cursor']})
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp() + 1000):
            with self.assertRaises(ProblemError):
                services.list_bookmarks(self.user_a, {'limit': 1, 'cursor': first['next_cursor']})
        self.change('accounts_user', self.owner_a, auth_epoch=1)
        self.user_a.refresh_from_db()
        with self.assertRaises(ProblemError):
            services.list_bookmarks(self.user_a, {'limit': 1, 'cursor': first['next_cursor']})

    def test_rls_and_composite_foreign_keys(self):
        """无参数；无上下文与B看不到A，绕过服务写跨owner关联仍由PG拒绝。"""
        self.new_action()
        services.save_bookmark(self.user_a, self.release_a, self.card_ids[0], {})
        services.create_feedback(self.user_a, {'answer_id': self.answer_id, 'category': 'other', 'comment': ''})
        for model in (Bookmark, ActionRecord, Feedback):
            self.assertEqual(model.objects.count(), 0)
            with owner_transaction(self.owner_b):
                self.assertEqual(model.objects.count(), 0)
        with owner_transaction(self.owner_b):
            with self.assertRaises(IntegrityError), transaction.atomic():
                ActionRecord.objects.create(owner=self.user_b, problem_id=self.problem['id'], answer_id=self.answer_id, action_index=0)
            with self.assertRaises(IntegrityError), transaction.atomic():
                Feedback.objects.create(owner=self.user_b, answer_id=self.answer_id, category='other')
        with self.assertRaises(DatabaseError), transaction.atomic():
            Bookmark.objects.create(owner=self.user_a, release_id=self.release_a, core_card_id='no-context')
        with connection.cursor() as cursor:
            cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN ('personal_bookmark','personal_actionrecord','personal_feedback')")
            self.assertEqual(cursor.fetchall(), [(True, True)] * 3)
            cursor.execute("SELECT has_table_privilege(current_user,'personal_feedback','TRUNCATE')")
            self.assertEqual(cursor.fetchone(), (False,))

    def test_action_pages_filter_cursor_and_quote_reprojection(self):
        """无参数；两个真实答案行动分页、筛选绑定、短引撤销和删除目标均保持正确。"""
        first_action = self.new_action()
        second_problem = create_draft(self.user_a, {'question': '今天如何开始第二次琥珀试行？',
            'goal': 'act', 'release_id': self.release_a}, str(uuid4()))
        accepted = send_message(self.user_a, second_problem['id'], {'content': '今天开始琥珀试行。',
            'intent': 'analyze_now', 'client_message_id': uuid4(), 'expected_revision': 0}, str(uuid4()))
        self.assertTrue(process_one(self.owner_a, provider=AnswerProvider()))
        second_answer = get_job(self.user_a, accepted['job_id'])['result_ref']
        second_action = services.create_action(self.user_a, {'answer_id': second_answer, 'action_index': 0})
        page = services.list_actions(self.user_a, {'limit': 1})
        self.assertIsNotNone(page['next_cursor'])
        following = services.list_actions(self.user_a, {'limit': 1, 'cursor': page['next_cursor']})
        self.assertEqual({page['items'][0]['id'], following['items'][0]['id']}, {first_action['id'], second_action['id']})
        for filters in ({'status': 'planned'}, {'problem_id': self.problem['id']}):
            with self.assertRaises(ProblemError):
                services.list_actions(self.user_a, {'limit': 1, 'cursor': page['next_cursor'], **filters})
        self.assertEqual(len(services.list_actions(self.user_a, {'problem_id': self.problem['id']})['items']), 1)
        self.change('knowledge_rightsrecord', self.right_a, allowed_uses=Jsonb(['browse', 'analyze']))
        self.assertEqual(len(services.list_actions(self.user_a, {})['items']), 2)
        self.manager.execute('UPDATE problems_problem SET status=%s, deleted_at=%s WHERE id=%s',
                             ['deleted', timezone.now(), second_problem['id']])
        current = services.list_actions(self.user_a, {'limit': 1})
        self.assertEqual([item['id'] for item in current['items']], [first_action['id']])
        self.assertIsNone(current['next_cursor'])

    def test_write_rechecks_access_after_projection(self):
        """无参数；完成投影到写入间撤权，收藏/行动不得入库。"""
        original = KnowledgeRepository.get_card
        def revoke_after_card(repository, release_id, card_id):
            """repository/release_id/card_id为真实读取参数；读取后模拟管理撤权。"""
            self.assertFalse(connection.in_atomic_block)
            result = original(repository, release_id, card_id)
            self.change('knowledge_librarygrant', self.grant_a, status='revoked', revoked_at=timezone.now())
            return result
        with patch.object(KnowledgeRepository, 'get_card', revoke_after_card):
            with self.assertRaises(Exception) as error:
                services.save_bookmark(self.user_a, self.release_a, self.card_ids[0], {})
            self.assertEqual(error.exception.status, 404)
        self.change('knowledge_librarygrant', self.grant_a, status='active', revoked_at=None)
        original_context = services._answer_context
        def revoke_after_answer(user, answer_id):
            """user/answer_id为真实投影目标；在返回后撤权验证最终写复核。"""
            result = original_context(user, answer_id)
            self.change('knowledge_librarygrant', self.grant_a, status='revoked', revoked_at=timezone.now())
            return result
        with patch.object(services, '_answer_context', revoke_after_answer):
            with self.assertRaises(Exception) as error:
                self.new_action()
            self.assertEqual(error.exception.status, 404)
        with owner_transaction(self.owner_a):
            self.assertEqual(Bookmark.objects.count(), 0)
            self.assertEqual(ActionRecord.objects.count(), 0)

    def test_deleted_problem_and_unpublished_answer_are_not_action_sources(self):
        """无参数；已删除档案和未成功发布运行的答案都不能成为行动来源。"""
        action = self.new_action()
        self.manager.execute('UPDATE problems_problem SET status=%s, deleted_at=%s WHERE id=%s', ['deleted', timezone.now(), self.problem['id']])
        self.assertEqual(services.list_actions(self.user_a, {})['items'], [])
        with self.assertRaises(ProblemError):
            services.update_action(self.user_a, action['id'], {'expected_revision': 0, 'status': 'done'})
        self.manager.execute('UPDATE problems_problem SET status=%s, deleted_at=NULL WHERE id=%s', ['active', self.problem['id']])
        with owner_transaction(self.owner_a):
            run_id = Answer.objects.get(pk=self.answer_id).run_id
        self.manager.execute('UPDATE runs_analysisrun SET outcome=%s WHERE id=%s', ['failed', run_id])
        with self.assertRaises(ProblemError):
            self.new_action()
