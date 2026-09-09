"""消息入队真实PostgreSQL验证；仅自编授权，模型始终禁用。"""
from uuid import uuid4

from django.db import connection, DatabaseError
from django.utils import timezone
from psycopg.types.json import Jsonb

from access.context import owner_transaction
from problems.services import create_draft, ProblemError
from tests.knowledge_fixtures import KnowledgeFixtureCase


class MessageRunTests(KnowledgeFixtureCase):
    """服务与数据库共同验证幂等、原文、授权与取消语义。"""

    def setUp(self):
        """无参数；只把当前用例两份自编许可补充analyze用途。"""
        super().setUp()
        self.addCleanup(self.cleanup_private)
        for right in (self.right_a, self.right_b):
            self.change('knowledge_rightsrecord', right, allowed_uses=Jsonb(['browse', 'quote', 'analyze']))
        self.problem = create_draft(self.user_a, {'question': '最初的问题🌱', 'goal': 'analyze',
                                   'release_id': self.release_a}, 'draft')

    def cleanup_private(self):
        """无参数；解除循环后精确清理本测试三用户产生的私有记录。"""
        owners = [self.owner_a, self.owner_b, self.owner_c]
        self.manager.execute('UPDATE problems_message SET run_id=NULL WHERE owner_id IN (%s,%s,%s)', owners)
        for table in ('operations_usageentry', 'operations_runreservation', 'operations_quotabucket', 'answers_answer', 'runs_jobevent', 'runs_analysisrun', 'runs_job', 'problems_message',
                      'problems_idempotencyrecord', 'problems_problem'):
            self.manager.execute(f'DELETE FROM {table} WHERE owner_id IN (%s,%s,%s)', owners)

    def data(self, revision=0, **overrides):
        """revision和overrides控制用户输入，UUID对象必须被正常接受。"""
        return {'content': '  我的补充：\n汉字😀 café e\u0301  ', 'intent': 'supplement',
                'client_message_id': uuid4(), 'expected_revision': revision, **overrides}

    def test_exact_replays_and_client_uuid_keep_original_input_and_core_snapshot(self):
        """无参数；同key及换key相同client UUID均不重复写，核心状态保持原样。"""
        from problems.models import Message, Problem
        from runs.models import AnalysisRun, Job
        from runs.services import send_message, list_messages
        data = self.data()
        first = send_message(self.user_a, self.problem['id'], data, 'first')
        self.assertEqual(send_message(self.user_a, self.problem['id'], data, 'first'), first)
        self.assertEqual(send_message(self.user_a, self.problem['id'], data, 'second'), first)
        self.assertEqual(first['revision'], 1)
        page = list_messages(self.user_a, self.problem['id'], {})
        self.assertEqual([item['content'] for item in page['items']], [data['content']])
        with owner_transaction(self.owner_a):
            self.assertEqual((Message.objects.count(), Job.objects.count(), AnalysisRun.objects.count()), (1, 1, 1))
            run, problem = AnalysisRun.objects.get(), Problem.objects.get()
            self.assertEqual(run.internal_state, problem.core_state)
            self.assertEqual(problem.core_state['original_question'] if 'original_question' in problem.core_state else problem.original_question,
                             '最初的问题🌱')
            self.assertEqual(run.input_message.intent, 'supplement')
            self.assertEqual(run.input_revision, 1)
            self.assertEqual(run.job.status, 'queued')
            self.assertIsNotNone(run.job.deadline)
            self.assertTrue(run.authorization_snapshot)

    def test_conflicts_and_invalid_input_have_no_partial_write(self):
        """无参数；不同body/intent/revision冲突以及越权字段均无额外任务。"""
        from runs.services import send_message
        from runs.models import Job
        data = self.data()
        send_message(self.user_a, self.problem['id'], data, 'first')
        cases = [(dict(data, content='异体'), 'first', 'IDEMPOTENCY_CONFLICT'),
                 (dict(data, intent='answer'), 'new', 'IDEMPOTENCY_CONFLICT'),
                 (dict(data, expected_revision=1), 'new', 'IDEMPOTENCY_CONFLICT'),
                 (self.data(), 'stale', 'REVISION_CONFLICT'),
                 (self.data(expected_revision=True), 'bad', 'INVALID_INPUT'),
                 (self.data(role='assistant'), 'bad', 'INVALID_INPUT'),
                 (self.data(content=' '), 'bad', 'INVALID_INPUT')]
        for request, key, code in cases:
            with self.subTest(code=code), self.assertRaises(ProblemError) as caught:
                send_message(self.user_a, self.problem['id'], request, key)
            self.assertEqual(caught.exception.code, code)
        with owner_transaction(self.owner_a):
            self.assertEqual(Job.objects.count(), 1)

    def test_analysis_button_and_cancellation_report_actual_job_state(self):
        """无参数；直接分析按钮保存原意图，排队取消终结且重复取消幂等。"""
        from runs.services import start_analysis, cancel_job, get_run, get_job, list_messages
        from runs.models import Job
        result = start_analysis(self.user_a, self.problem['id'], {'expected_revision': 0}, 'analysis')
        self.assertEqual(start_analysis(self.user_a, self.problem['id'], {'expected_revision': 0}, 'analysis'), result)
        item = list_messages(self.user_a, self.problem['id'], {})['items'][0]
        self.assertEqual(item['content'], '请直接分析当前问题。')
        payload, status = cancel_job(self.user_a, result['job_id'])
        self.assertEqual((payload['status'], status), ('cancelled', 200))
        self.assertIsNotNone(payload['finished_at'])
        self.assertEqual(cancel_job(self.user_a, result['job_id']), (payload, 200))
        run = get_run(self.user_a, result['run_id'])
        self.assertEqual(run['status'], 'cancelled')
        self.assertNotIn('internal_state', run)
        with owner_transaction(self.owner_a):
            Job.objects.filter(pk=result['job_id']).update(status='running', finished_at=None)
        self.assertEqual(cancel_job(self.user_a, result['job_id'])[1], 202)
        self.assertEqual(get_job(self.user_a, result['job_id'])['status'], 'cancel_requested')

    def test_revocation_hides_assistant_and_blocks_tasks_and_replay(self):
        """无参数；撤权保留本人原文，但任何助手内容与任务状态都不可再读取。"""
        from problems.models import Message
        from runs.services import send_message, list_messages, get_run, get_job, cancel_job
        data = self.data()
        result = send_message(self.user_a, self.problem['id'], data, 'first')
        with owner_transaction(self.owner_a):
            Message.objects.create(owner=self.user_a, problem_id=self.problem['id'], sequence=2,
                role='assistant', kind='notice', content='私有助手内容', intent='unknown',
                run_id=result['run_id'], published_at=timezone.now())
        self.assertEqual(len(list_messages(self.user_a, self.problem['id'], {})['items']), 2)
        self.change('knowledge_librarygrant', self.grant_a, status='revoked', revoked_at=timezone.now())
        page = list_messages(self.user_a, self.problem['id'], {})
        self.assertFalse(page['library_available'])
        self.assertEqual([item['role'] for item in page['items']], ['user'])
        for action, args in ((get_run, (result['run_id'],)), (get_job, (result['job_id'],)),
                             (cancel_job, (result['job_id'],)),
                             (send_message, (self.problem['id'], data, 'first'))):
            with self.assertRaises(Exception) as caught:
                action(self.user_a, *args)
            self.assertEqual(caught.exception.status, 404)

    def test_composite_foreign_keys_rls_and_explicit_migration_permissions(self):
        """无参数；数据库拒绝跨owner、跨问题、跨release关联且权限来自迁移。"""
        from problems.models import Message
        from runs.models import Job, AnalysisRun
        from runs.services import send_message
        result = send_message(self.user_a, self.problem['id'], self.data(), 'one')
        b = create_draft(self.user_b, {'question': 'B', 'goal': 'analyze', 'release_id': self.release_b}, 'b')
        other = send_message(self.user_b, b['id'], self.data(), 'b')
        for model in (Message, Job, AnalysisRun):
            self.assertEqual(model.objects.count(), 0)
            with owner_transaction(self.owner_a):
                self.assertEqual(model.objects.count(), 1)
            with owner_transaction(self.owner_b):
                self.assertEqual(model.objects.count(), 1)
        for model, values in ((Message, {'problem_id': b['id']}),
                              (Message, {'run_id': other['run_id']}),
                              (AnalysisRun, {'job_id': other['job_id']}),
                              (AnalysisRun, {'release_id': self.release_b}),
                              (AnalysisRun, {'problem_id': b['id']})):
            with self.assertRaises(DatabaseError):
                with owner_transaction(self.owner_a):
                    model.objects.update(**values)
        for table in ('problems_message', 'runs_job', 'runs_analysisrun'):
            with connection.cursor() as cursor:
                cursor.execute('SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid=%s::regclass', [table])
                self.assertEqual(cursor.fetchone(), (True, True))
                for permission in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                    cursor.execute('SELECT has_table_privilege(current_user,%s,%s)', [table, permission])
                    self.assertEqual(cursor.fetchone()[0], permission in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'))

    def test_cursor_is_bounded_and_bound_to_problem_owner_epoch_limit(self):
        """无参数；连续消息升序分页，游标不得跨问题、owner或limit复用。"""
        from runs.services import send_message, list_messages
        for revision in range(3):
            send_message(self.user_a, self.problem['id'], self.data(revision), str(revision))
        page = list_messages(self.user_a, self.problem['id'], {'limit': 2})
        self.assertEqual([item['sequence'] for item in page['items']], [1, 2])
        following = list_messages(self.user_a, self.problem['id'], {'limit': 2, 'cursor': page['next_cursor']})
        self.assertEqual([item['sequence'] for item in following['items']], [3])
        self.assertIsNone(following['next_cursor'])
        for query in ({'limit': 1, 'cursor': page['next_cursor']}, {'limit': True}, {'q': 'x'},
                      {'cursor': page['next_cursor'] + 'x'}):
            with self.assertRaises(ProblemError):
                list_messages(self.user_a, self.problem['id'], query)
