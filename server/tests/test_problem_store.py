"""问题草稿公开服务接缝；真实自编知识授权及受限PostgreSQL运行角色。"""
import importlib.util
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID
from pathlib import Path

from django.db import connection, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import ConnectionHandler
from django.conf import settings
from django.utils import timezone
from psycopg.types.json import Jsonb

from access.context import owner_transaction
from config.settings.environment import database_settings

from tests.knowledge_fixtures import KnowledgeFixtureCase


class ProblemStoreTests(KnowledgeFixtureCase):
    """只经公开服务断言草稿行为，管理连接仅准备和清理。"""

    def setUp(self):
        """无参数；沿用自编知识夹具并在其清理前移除本人草稿。"""
        super().setUp()
        self.addCleanup(self.cleanup_problems)

    def cleanup_problems(self):
        """无参数；仅清理本测试用户的问题和幂等记录。"""
        for table in ('problems_idempotencyrecord', 'problems_problem'):
            if self.manager.execute('SELECT to_regclass(%s)', [table]).fetchone()[0]:
                self.manager.execute(f'DELETE FROM {table} WHERE owner_id IN (%s,%s,%s)',
                                     [self.owner_a, self.owner_b, self.owner_c])

    def test_create_preserves_question_and_returns_five_round_draft(self):
        """无参数；保存原文并重新读取，只公开真实核心快照派生的澄清状态。"""
        self.assertIsNotNone(importlib.util.find_spec('problems'), '缺少问题草稿服务')
        from problems.services import create_draft, get_draft
        question = '  我该如何选择？\n请保留这段原文。  '
        draft = create_draft(self.user_a, {'question': question, 'goal': 'analyze',
                                          'release_id': str(self.release_a)}, 'create-1')
        self.assertEqual(get_draft(self.user_a, draft['id']), draft)
        self.assertEqual(draft['original_question'], question)
        self.assertEqual(draft['revision'], 0)
        self.assertEqual(draft['clarification'], {'rounds': 0, 'limit': 5,
                         'pending_question': None, 'closed': False})
        self.assertEqual(draft['status'], 'active')
        self.assertIsNone(draft['current_answer_id'])
        self.assertTrue(draft['library_available'])
        self.assertEqual(set(draft), {'id', 'title', 'original_question', 'goal', 'release_id',
                         'revision', 'status', 'clarification', 'current_answer_id',
                         'library_available', 'created_at', 'updated_at'})

    def create(self, *, user=None, release=None, key='one', question='自编问题原文'):
        """user/release默认本人A，key/question用于创建独立问题；经公开服务写入。"""
        from problems.services import create_draft
        return create_draft(user or self.user_a, {'question': question, 'goal': 'analyze',
                            'release_id': release or self.release_a}, key)

    def test_empty_cursor_is_first_page_and_lists_only_owner(self):
        """无参数；HTTP首屏空游标可用，A/B读取与写入互不可见。"""
        from problems.services import get_draft, list_drafts, update_draft, ProblemError
        a = self.create()
        b = self.create(user=self.user_b, release=self.release_b)
        self.assertEqual([item['id'] for item in list_drafts(self.user_a, {'cursor': ''})['items']], [a['id']])
        self.assertEqual([item['id'] for item in list_drafts(self.user_b, {})['items']], [b['id']])
        for action in (get_draft, update_draft):
            with self.assertRaises(ProblemError) as caught:
                args = (self.user_b, a['id'])
                action(*args, *([{'title': '盗改', 'expected_revision': 0}] if action == update_draft else []))
            self.assertEqual(caught.exception.status, 404)

    def test_idempotency_replay_conflict_expiry_and_revoked_access(self):
        """无参数；相同key重放原201，异体冲突，过期不覆盖，撤权后只允许本人读原问题。"""
        from problems.services import get_draft, update_draft, ProblemError
        from problems.models import IdempotencyRecord
        a = self.create()
        update_draft(self.user_a, a['id'], {'title': '新标题', 'expected_revision': 0})
        self.assertEqual(self.create(), a)
        with owner_transaction(self.owner_a):
            records = IdempotencyRecord.objects.filter(owner_id=self.owner_a)
            self.assertEqual(records.count(), 1)
            record = records.get()
            self.assertEqual(record.response_status, 201)
            self.assertAlmostEqual((record.expires_at - record.created_at).total_seconds(), 172800, delta=2)
            self.assertEqual(set(record.response_payload), set(a))
            records.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.create(), a)
        with self.assertRaises(ProblemError) as caught:
            self.create(question='不同原文')
        self.assertEqual(caught.exception.code, 'IDEMPOTENCY_CONFLICT')
        b = self.create(user=self.user_b, release=self.release_b)
        self.assertNotEqual(a['id'], b['id'])
        self.change('knowledge_librarygrant', self.grant_a, status='revoked', revoked_at=timezone.now())
        with self.assertRaises(ProblemError) as caught:
            self.create()
        self.assertEqual(caught.exception.status, 404)
        self.assertFalse(get_draft(self.user_a, a['id'])['library_available'])
        archived = update_draft(self.user_a, a['id'], {'status': 'archived', 'expected_revision': 1})
        self.assertFalse(archived['library_available'])

    def test_stale_revision_has_no_partial_change_and_archive_restores(self):
        """无参数；旧窗口不能覆盖名称或状态，一次成功仅增加一次修订。"""
        from problems.services import get_draft, list_drafts, update_draft, ProblemError
        a = self.create()
        edited = update_draft(self.user_a, a['id'], {'title': '新名称', 'status': 'archived', 'expected_revision': 0})
        self.assertEqual(edited['revision'], 1)
        self.assertEqual(list_drafts(self.user_a, {})['items'], [])
        self.assertEqual(list_drafts(self.user_a, {'status': 'archived'})['items'], [edited])
        with self.assertRaises(ProblemError) as caught:
            update_draft(self.user_a, a['id'], {'title': '旧窗口', 'status': 'active', 'expected_revision': 0})
        self.assertEqual((caught.exception.code, caught.exception.current_revision), ('REVISION_CONFLICT', 1))
        self.assertEqual(get_draft(self.user_a, a['id']), edited)
        restored = update_draft(self.user_a, a['id'], {'status': 'active', 'expected_revision': 1})
        self.assertEqual(restored['revision'], 2)
        self.assertEqual(list_drafts(self.user_a, {})['items'], [restored])

    def test_search_pagination_rejects_forged_other_owner_query_and_expired_cursor(self):
        """无参数；搜索分页不重复，游标绑定本人epoch、过滤条件和15分钟期限。"""
        from problems.services import list_drafts, ProblemError
        a = self.create(question='苹果第一问')
        b = self.create(key='two', question='苹果第二问')
        self.create(key='three', question='香蕉')
        first = list_drafts(self.user_a, {'q': '苹果', 'limit': 1})
        second = list_drafts(self.user_a, {'q': '苹果', 'limit': 1, 'cursor': first['next_cursor']})
        self.assertEqual({first['items'][0]['id'], second['items'][0]['id']}, {a['id'], b['id']})
        self.assertIsNone(second['next_cursor'])
        for user, query in ((self.user_a, {'q': '香蕉'}), (self.user_b, {'q': '苹果'}),
                            (self.user_a, {'q': '苹果', 'cursor': first['next_cursor'] + 'x'})):
            with self.assertRaises(ProblemError) as caught:
                list_drafts(user, {'limit': 1, 'cursor': first['next_cursor'], **query})
            self.assertEqual(caught.exception.status, 400)
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp() + 901):
            with self.assertRaises(ProblemError):
                list_drafts(self.user_a, {'q': '苹果', 'limit': 1, 'cursor': first['next_cursor']})
        self.change('accounts_user', self.owner_a, auth_epoch=1)
        self.user_a.refresh_from_db()
        with self.assertRaises(ProblemError):
            list_drafts(self.user_a, {'q': '苹果', 'limit': 1, 'cursor': first['next_cursor']})

    def test_runtime_rls_empty_context_owner_switch_and_foreign_write(self):
        """无参数；真实runtime同连接A/空/B无残留，owner变更被数据库WITH CHECK拒绝。"""
        from problems.models import Problem, IdempotencyRecord
        a = self.create()
        b = self.create(user=self.user_b, release=self.release_b)
        physical = connection.connection
        for model in (Problem, IdempotencyRecord):
            self.assertEqual(model.objects.count(), 0)
            for owner in (self.owner_a, self.owner_b):
                with owner_transaction(owner):
                    self.assertEqual(model.objects.count(), 1)
                self.assertEqual(model.objects.count(), 0)
            with self.assertRaises(DatabaseError) as caught:
                with owner_transaction(self.owner_a):
                    model.objects.update(owner_id=self.owner_b)
            self.assertEqual(caught.exception.__cause__.sqlstate, '42501')
        self.assertIs(physical, connection.connection)
        connection.close()
        self.assertEqual(Problem.objects.count(), 0)
        with owner_transaction(self.owner_b):
            self.assertEqual(list(Problem.objects.values_list('id', flat=True)), [UUID(b['id'])])

    def test_invalid_core_and_deleted_problem_fail_closed(self):
        """无参数；损坏摘要、核心ID/原文/goal不匹配固定503，删除对象包含重放均404。"""
        from problems.services import get_draft, ProblemError
        from src.orchestration.intake import create_problem
        draft = self.create()
        for state in ({}, create_problem('另一个问题', 'analyze'), create_problem('自编问题原文', 'review')):
            self.manager.execute('UPDATE problems_problem SET core_state=%s WHERE id=%s', [Jsonb(state), draft['id']])
            with self.assertRaises(ProblemError) as caught:
                get_draft(self.user_a, draft['id'])
            self.assertEqual((caught.exception.status, caught.exception.message), (503, '问题暂不可用'))
        self.manager.execute("UPDATE problems_problem SET status='deleted', deleted_at=%s WHERE id=%s", [timezone.now(), draft['id']])
        for action in (lambda: get_draft(self.user_a, draft['id']), self.create):
            with self.assertRaises(ProblemError) as caught:
                action()
            self.assertEqual(caught.exception.status, 404)

    def test_service_rejects_unvalidated_fields_types_and_stale_identity(self):
        """无参数；绕过HTTP也不能写归属、原文或非法修订，失效账号无法访问。"""
        from problems.services import create_draft, get_draft, list_drafts, update_draft, ProblemError
        draft = self.create()
        for data in ({'title': 'x'}, {'expected_revision': True, 'title': 'x'},
                     {'expected_revision': 0}, {'expected_revision': 0, 'owner_id': str(self.owner_b)},
                     {'expected_revision': 0, 'title': ' '}, {'expected_revision': 0, 'status': 'deleted'},
                     {'expected_revision': 0, 'original_question': '篡改'}):
            with self.assertRaises(ProblemError) as caught:
                update_draft(self.user_a, draft['id'], data)
            self.assertEqual(caught.exception.status, 400)
        for query in ({'limit': True}, {'limit': 0}, {'q': 'x' * 501}, {'status': 'deleted'}, {'owner': 'x'}):
            with self.assertRaises(ProblemError):
                list_drafts(self.user_a, query)
        for data in ({'question': 'x', 'goal': 'analyze', 'release_id': True},
                     {'question': 'x' * 4001, 'goal': 'analyze', 'release_id': self.release_a},
                     {'question': 'x', 'goal': 'analyze', 'release_id': self.release_a, 'owner_id': self.owner_b}):
            with self.assertRaises(ProblemError):
                create_draft(self.user_a, data, 'bad')
        self.change('accounts_user', self.owner_a, auth_epoch=1)
        for action in (lambda: get_draft(self.user_a, draft['id']), self.create,
                       lambda: list_drafts(self.user_a, {})):
            with self.assertRaises(ProblemError) as caught:
                action()
            self.assertEqual(caught.exception.status, 404)

    def test_creation_works_with_no_library_files_or_model_enabled(self):
        """无参数；禁用模型且知识路径不存在时仍只借助已有授权元数据创建问题。"""
        with self.settings(SB_LIBRARY_ROOT=Path('/nonexistent/problem-test-library'), SB_MODEL_MODE='disabled'):
            draft = self.create(question='字' * 4000)
        self.assertEqual(draft['original_question'], '字' * 4000)
        self.assertEqual(len(draft['title']), 160)

    def test_database_constraints_reject_invalid_drafts(self):
        """无参数；真实runtime直接写也无法绕过状态、文本长度、枚举和修订约束。"""
        from problems.models import Problem, IdempotencyRecord
        draft = self.create()
        for values in ({'title': ' '}, {'title': 'x' * 161}, {'original_question': ''},
                       {'original_question': '字' * 4001}, {'goal': 'invalid'}, {'revision': -1},
                       {'status': 'invalid'}, {'status': 'deleted'}, {'deleted_at': timezone.now()}):
            with self.subTest(values=list(values)):
                with self.assertRaises(DatabaseError):
                    with owner_transaction(self.owner_a):
                        Problem.objects.filter(pk=draft['id']).update(**values)
        for values in ({'status': 'invalid'}, {'request_hash': 'g' * 64}, {'key': 'x' * 129}):
            with self.assertRaises(DatabaseError):
                with owner_transaction(self.owner_a):
                    IdempotencyRecord.objects.update(**values)

    def test_migration_grants_only_dml_and_reverses_closed(self):
        """无参数；回退重施真实迁移，证明权限来自迁移本身而非runner补授。"""
        tables = ('problems_problem', 'problems_idempotencyrecord')
        configuration = database_settings(settings.DEV_ENV['SB_MIGRATION_DATABASE_URL'],
                                           'SB_MIGRATION_DATABASE_URL', False)
        configuration['NAME'] = 'test_sb_product'
        migration_connection = ConnectionHandler({'default': configuration})['default']
        self.addCleanup(migration_connection.close)
        with migration_connection.cursor() as cursor:
            cursor.execute('SELECT current_database(), current_user')
            self.assertEqual(cursor.fetchone(), ('test_sb_product', 'sb_migrator'))
        try:
            MigrationExecutor(migration_connection).migrate([('problems', '0001_initial')])
            with connection.cursor() as cursor:
                for table in tables:
                    cursor.execute('SELECT has_table_privilege(current_user, %s, %s)', [table, 'SELECT'])
                    self.assertFalse(cursor.fetchone()[0])
                    self.manager.execute(f'GRANT ALL ON TABLE {table} TO sb_runtime, PUBLIC')
            MigrationExecutor(migration_connection).migrate([('problems', '0002_database_access')])
            with connection.cursor() as cursor:
                for table in tables:
                    for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
                        cursor.execute('SELECT has_table_privilege(current_user, %s, %s)', [table, privilege])
                        self.assertTrue(cursor.fetchone()[0])
                    for privilege in ('TRUNCATE', 'REFERENCES', 'TRIGGER'):
                        cursor.execute('SELECT has_table_privilege(current_user, %s, %s)', [table, privilege])
                        self.assertFalse(cursor.fetchone()[0])
                    cursor.execute('SELECT relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) FROM pg_class WHERE oid=%s::regclass', [table])
                    self.assertEqual(cursor.fetchone(), (True, True, 'sb_migrator'))
                    cursor.execute('SELECT count(*) FROM pg_class, LATERAL aclexplode(relacl) AS acl WHERE oid=%s::regclass AND acl.grantee=0', [table])
                    self.assertEqual(cursor.fetchone(), (0,))
                    cursor.execute('SELECT roles, cmd, qual, with_check FROM pg_policies WHERE tablename=%s ORDER BY policyname', [table])
                    policies = cursor.fetchall()
                    self.assertEqual([(row[0], row[1]) for row in policies], [(['sb_migrator'], 'ALL'), (['sb_runtime'], 'ALL')])
                    self.assertIn('sb.owner_id', policies[1][2])
                    self.assertEqual(policies[1][2], policies[1][3])
            # 使用该迁移版本的历史模型，不能让现行模型访问尚未存在的新列。
            historical = MigrationExecutor(migration_connection).loader.project_state(
                [('problems', '0002_database_access')]).apps.get_model('problems', 'Problem')
            from src.orchestration.intake import create_problem
            state = create_problem('历史迁移读写验证', 'analyze')
            with owner_transaction(self.owner_a):
                historical.objects.create(owner_id=self.owner_a, release_id=self.release_a,
                    title='历史迁移读写验证', original_question=state['question'],
                    goal='analyze', core_problem_id=state['problem_id'], core_state=state)
        finally:
            # 权限回退只验证旧迁移；结束必须恢复当前完整模型，不能撤掉后续消息/任务表。
            executor = MigrationExecutor(migration_connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
