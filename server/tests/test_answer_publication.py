"""真实PG与原v3答案链路；实际模型质量须另做真人题评估。"""
import copy
from uuid import uuid4
from django.utils import timezone
from psycopg.types.json import Jsonb
from access.context import owner_transaction
from ai.intake_service import advance_messages
from answers.models import Answer
from answers.publisher import analyze_release, publish_answer
from answers.services import get_answer
from problems.models import Problem, Message
from problems.services import create_draft
from runs.models import Job, AnalysisRun
from runs.queue import claim
from runs.services import send_message, cancel_job
from tests.answer_fixtures import AnswerProvider
from tests.knowledge_fixtures import KnowledgeFixtureCase


class AnswerPublicationTests(KnowledgeFixtureCase):
    """正式发布只发生一次，输入更新/撤权/取消不能产出新答案。"""

    def setUp(self):
        """无参数；仅在固定测试库创建已授权自编知识和用户问题。"""
        super().setUp()
        self.addCleanup(self.cleanup_private)
        self.change('knowledge_rightsrecord', self.right_a, allowed_uses=Jsonb(['browse', 'quote', 'analyze']))
        self.problem = create_draft(self.user_a, {'question': '琥珀试行今天应该如何开始？',
            'goal': 'act', 'release_id': self.release_a}, 'answer-fixture')

    def cleanup_private(self):
        """无参数；只删除本fixture owner数据，按实际外键反序清理。"""
        owners = [self.owner_a, self.owner_b, self.owner_c]
        self.manager.execute('UPDATE problems_message SET run_id=NULL WHERE owner_id IN (%s,%s,%s)', owners)
        for table in ('operations_usageentry', 'operations_runreservation', 'operations_quotabucket',
                      'answers_answer', 'runs_jobevent', 'runs_analysisrun', 'runs_job',
                      'problems_message', 'problems_idempotencyrecord', 'problems_problem'):
            self.manager.execute(f'DELETE FROM {table} WHERE owner_id IN (%s,%s,%s)', owners)

    def prepare(self):
        """无参数；真实入队领取，并把固定提案经实际入口、检索和v3校验。"""
        accepted = send_message(self.user_a, self.problem['id'], {'content': '今天需要开始琥珀试行。',
            'intent': 'analyze_now', 'client_message_id': uuid4(), 'expected_revision': 0}, str(uuid4()))
        lease = claim(self.owner_a)
        intake = advance_messages(lease.state, lease.messages, AnswerProvider())
        library, analysis = analyze_release(lease, intake, AnswerProvider(), timeout_seconds=120, cancelled=lambda: False)
        return accepted, lease, intake, library, analysis

    def test_publish_real_packet_once_and_private_owner_isolation(self):
        """无参数；原消息/核心游标/公开内容/实际run/job同事务成功，B和无上下文均不可读。"""
        _, lease, intake, library, analysis = self.prepare()
        self.assertTrue(publish_answer(lease, intake, analysis, library))
        self.assertFalse(publish_answer(lease, intake, analysis, library))
        with owner_transaction(self.owner_a):
            answer, job, problem = Answer.objects.get(), Job.objects.get(), Problem.objects.get()
            self.assertEqual(job.status, 'succeeded')
            self.assertEqual(problem.processed_message_sequence, 1)
            self.assertEqual(problem.revision, 2)
            self.assertEqual(answer.internal_packet, analysis['packet'])
            self.assertEqual(answer.validation_status, 'structure_passed')
            self.assertIn('原理：', answer.rendered_markdown)
            self.assertIn('继续和 AI 聊：', answer.rendered_markdown.splitlines()[-1])
            self.assertNotIn('session_id', answer.public_payload)
            self.assertEqual(AnalysisRun.objects.get().outcome, 'answer')
            self.assertEqual(Message.objects.filter(kind='answer').count(), 1)
        with owner_transaction(self.owner_b):
            self.assertEqual(Answer.objects.count(), 0)
        self.assertEqual(Answer.objects.count(), 0)

    def test_tampered_packet_never_publishes_or_consumes_messages(self):
        """无参数；计算完成后的包被改写时必须拒绝，而非保存未核验建议。"""
        _, lease, intake, library, analysis = self.prepare()
        altered = copy.deepcopy(analysis)
        altered['packet']['verdict']['conclusion'] = '伪造的裁决'
        self.assertFalse(publish_answer(lease, intake, altered, library))
        with owner_transaction(self.owner_a):
            self.assertEqual(Answer.objects.count(), 0)
            self.assertEqual(Problem.objects.get().processed_message_sequence, 0)
            self.assertEqual(Job.objects.get().error_code, 'MODEL_OUTPUT_INVALID')

    def test_cancelled_or_revoked_cannot_publish(self):
        """无参数；已算出的真实答案仍受最终取消/许可检查约束。"""
        accepted, lease, intake, library, analysis = self.prepare()
        cancel_job(self.user_a, accepted['job_id'])
        self.assertFalse(publish_answer(lease, intake, analysis, library))
        with owner_transaction(self.owner_a):
            self.assertEqual(Answer.objects.count(), 0)
            self.assertEqual(Job.objects.get().status, 'cancelled')

    def test_revoked_grant_after_generation_rejects_publication(self):
        """无参数；生成结束后撤权，产物不得入本人可读答案。"""
        _, lease, intake, library, analysis = self.prepare()
        self.change('knowledge_librarygrant', self.grant_a, status='revoked', revoked_at=timezone.now())
        self.assertFalse(publish_answer(lease, intake, analysis, library))
        with owner_transaction(self.owner_a):
            self.assertEqual(Answer.objects.count(), 0)
            self.assertEqual(Job.objects.get().error_code, 'ACCESS_REVOKED')

    def test_actual_worker_records_each_call_and_public_http_hides_internal_data(self):
        """无参数；真实登录→入队→完整worker/v3/三次用量→GET正式答案，普通B不可读。"""
        from django.test import Client
        from django.conf import settings
        from django.contrib.sessions.models import Session
        from jsonschema import Draft202012Validator
        from config.contracts import build_contract
        from operations.models import UsageEntry, QuotaBucket, RunReservation
        from runs.worker import process_one
        from runs.services import get_job
        password = 'Local-Answer-Library-830!'
        self.user_a.set_password(password)
        self.user_a.save(update_fields=['password'])
        browser = Client(enforce_csrf_checks=True)
        token = browser.get('/api/v1/auth/csrf').json()['csrf_token']
        response = browser.post('/api/v1/auth/login', {'email': self.user_a.email, 'password': password},
                                content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        key = browser.cookies[settings.SESSION_COOKIE_NAME].value
        self.addCleanup(lambda: Session.objects.filter(session_key=key).delete())
        accepted = send_message(self.user_a, self.problem['id'], {'content': '今天需要开始琥珀试行。',
            'intent': 'analyze_now', 'client_message_id': uuid4(), 'expected_revision': 0}, 'worker-answer')
        self.assertTrue(process_one(self.owner_a, provider=AnswerProvider()))
        job = get_job(self.user_a, accepted['job_id'])
        self.assertEqual(job['status'], 'succeeded')
        self.assertIsNotNone(job['result_ref'])
        response = browser.get('/api/v1/answers/' + job['result_ref'])
        self.assertEqual(response.status_code, 200, response.content[:160])
        self.assertEqual(response['Cache-Control'], 'no-store')
        contract = build_contract()
        Draft202012Validator({'$ref': '#/components/schemas/Answer', 'components': contract['components']}).validate(response.json())
        for private in ('internal_packet', 'internal_session', 'system_prompt', 'original_card_ref', '/Users/'):
            self.assertNotIn(private, response.content.decode())
        self.assertIn('原理：', response.json()['rendered_markdown'])
        with owner_transaction(self.owner_a):
            self.assertEqual(list(UsageEntry.objects.order_by('call_index').values_list('purpose', flat=True)),
                             ['extract', 'plan', 'analysis'])
            self.assertEqual(UsageEntry.objects.filter(input_tokens=37, output_tokens=91).count(), 3)
            self.assertEqual(QuotaBucket.objects.get().settled_runs, 1)
            self.assertEqual(QuotaBucket.objects.get().reserved_runs, 0)
            self.assertEqual(RunReservation.objects.get().state, 'settled')

    def test_quote_revoke_reprojects_answer_and_keeps_chat_free_of_old_quotes(self):
        """无参数；撤销quote但保留analyze时重投影短引，不返回旧rendered_markdown缓存。"""
        _, lease, intake, library, analysis = self.prepare()
        self.assertTrue(publish_answer(lease, intake, analysis, library))
        with owner_transaction(self.owner_a):
            answer = Answer.objects.get()
        first = get_answer(self.user_a, answer.pk)
        self.assertTrue(any(item['excerpt'] for item in first['content']['sources']))
        self.change('knowledge_rightsrecord', self.right_a, allowed_uses=Jsonb(['browse', 'analyze']))
        current = get_answer(self.user_a, answer.pk)
        self.assertTrue(all(item['excerpt'] is None for item in current['content']['sources']))
        self.assertIn('当前许可不提供原文短引', current['rendered_markdown'])
        from runs.services import list_messages
        page = list_messages(self.user_a, self.problem['id'], {})
        self.assertEqual(page['items'][-1]['content'], '分析已完成。请打开正式答案查看建议、书籍原理与依据。')
        from problems.services import ProblemError
        with self.assertRaises(ProblemError):
            get_answer(self.user_b, answer.pk)
        self.change('knowledge_librarygrant', self.grant_a, status='revoked', revoked_at=timezone.now())
        with self.assertRaises(ProblemError):
            get_answer(self.user_a, answer.pk)
