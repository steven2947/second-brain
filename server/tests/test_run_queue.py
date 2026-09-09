"""受限运行角色的真实PostgreSQL租约/发布验证；自编provider不证明真实AI质量。"""
import copy
from datetime import timedelta
from uuid import uuid4

from django.db import DatabaseError, connection
from django.utils import timezone
from psycopg.types.json import Jsonb

from access.context import owner_transaction
from ai.intake_service import advance_intake
from ai.ports import Generation
from problems.models import Message, Problem
from problems.services import create_draft, ProblemError
from runs.models import AnalysisRun, Job, JobEvent
from runs.queue import claim, heartbeat, finish_failure, publish_question, list_events
from runs.services import send_message, cancel_job
from tests.knowledge_fixtures import KnowledgeFixtureCase


class QuestionProvider:
    """只在测试返回自编提案，仍执行实际AI适配器和原核心事件校验。"""

    def generate(self, request):
        """request为实际适配器请求；extract保留原文，plan给出一次明确追问。"""
        content = ({'changes': {'facts': request.context['snapshot']['facts'] + [request.context['message']]},
                    'reason': '记录用户实际输入。'} if request.purpose == 'extract' else
                   {'type': 'ask', 'question': '你最想先验证哪个条件？', 'reason': '此条件影响下一步。'})
        return Generation(content=content, provider='test', model='fixed')


class RunQueueTests(KnowledgeFixtureCase):
    """终态、消费游标和公开消息只能由当前租约在当前授权下原子发布。"""

    def setUp(self):
        """无参数；给当前两份自编测试许可增加分析用途并建立本人草稿。"""
        super().setUp()
        self.addCleanup(self.cleanup_private)
        for right in (self.right_a, self.right_b):
            self.change('knowledge_rightsrecord', right, allowed_uses=Jsonb(['browse', 'quote', 'analyze']))
        self.problem = create_draft(self.user_a, {'question': '最初的问题🌱', 'goal': 'analyze',
                                   'release_id': self.release_a}, 'draft')

    def cleanup_private(self):
        """无参数；先清事件及循环关联，再按精确测试owner反序清理。"""
        owners = [self.owner_a, self.owner_b, self.owner_c]
        self.manager.execute('UPDATE problems_message SET run_id=NULL WHERE owner_id IN (%s,%s,%s)', owners)
        for table in ('operations_usageentry', 'operations_runreservation', 'operations_quotabucket', 'answers_answer', 'runs_jobevent', 'runs_analysisrun', 'runs_job', 'problems_message',
                      'problems_idempotencyrecord', 'problems_problem'):
            self.manager.execute(f'DELETE FROM {table} WHERE owner_id IN (%s,%s,%s)', owners)

    def enqueue(self, revision=0, content='  尚未向这25人报价。\n ', **values):
        """revision/content为本测试用户真实输入，values允许更改显式意图。"""
        return send_message(self.user_a, self.problem['id'], {'content': content,
            'intent': 'supplement', 'client_message_id': uuid4(),
            'expected_revision': revision, **values}, str(uuid4()))

    def result(self, lease):
        """lease为实际领取结果；使用真实多消息适配器或单消息适配器生成提案。"""
        if len(lease.messages) == 1:
            message = lease.messages[0]
            return advance_intake(lease.state, message['content'], message['intent'], QuestionProvider())
        from ai.intake_service import advance_messages
        return advance_messages(lease.state, lease.messages, QuestionProvider())

    def expired(self, lease):
        """lease属于本fixture；仅管理连接模拟租约过期，不改变整体deadline。"""
        self.manager.execute('UPDATE runs_job SET lease_until=%s WHERE id=%s AND owner_id=%s',
                             [timezone.now() - timedelta(seconds=1), lease.job_id, self.owner_a])

    def assert_unpublished(self, code):
        """code为预期固定错误；确认失败没有消费事实或追加助手消息。"""
        with owner_transaction(self.owner_a):
            job = Job.objects.order_by('created_at').first()
            self.assertEqual(job.error_code, code)
            self.assertEqual(Problem.objects.get(pk=self.problem['id']).processed_message_sequence, 0)
            self.assertEqual(Message.objects.filter(role='assistant').count(), 0)

    def test_claim_once_heartbeat_and_atomic_question_publication(self):
        """无参数；领取和续租真实落库，发布仅出现一次且保留原问题和原话。"""
        accepted = self.enqueue()
        lease = claim(self.owner_a)
        self.assertIsNotNone(lease)
        self.assertEqual(lease.attempt, 1)
        self.assertIsNone(claim(self.owner_a))
        self.assertTrue(heartbeat(lease, 'validating'))
        self.assertTrue(publish_question(lease, self.result(lease)))
        self.assertFalse(publish_question(lease, self.result(lease)))
        with owner_transaction(self.owner_a):
            problem, job = Problem.objects.get(), Job.objects.get()
            self.assertEqual((job.status, problem.revision, problem.processed_message_sequence), ('succeeded', 2, 1))
            self.assertEqual(problem.original_question, '最初的问题🌱')
            self.assertEqual(problem.core_state['events'][0]['source_message'], lease.messages[0]['content'])
            self.assertEqual(Message.objects.filter(role='assistant').count(), 1)
            self.assertIsNone(job.lease_token)
        events = list_events(self.user_a, accepted['job_id'])
        self.assertEqual([row['seq'] for row in events], [1, 2, 3])
        self.assertEqual([row['event_type'] for row in events], ['stage', 'stage', 'question_ready'])
        self.assertEqual(list_events(self.user_a, accepted['job_id'], after=2), events[2:])
        self.assertTrue(all(set(row['public_payload']) == {'job_id', 'run_id', 'stage'} for row in events))

    def test_reclaim_new_token_fences_old_attempt_and_keeps_deadline(self):
        """无参数；过期任务重领后旧发布、续租和失败均不能改写当前尝试。"""
        self.enqueue()
        first = claim(self.owner_a)
        result = self.result(first)
        self.expired(first)
        second = claim(self.owner_a)
        self.assertEqual((second.attempt, second.deadline), (2, first.deadline))
        self.assertNotEqual(first.token, second.token)
        self.assertFalse(heartbeat(first))
        self.assertFalse(finish_failure(first, 'RUN_FAILED'))
        self.assertFalse(publish_question(first, result))
        self.assertTrue(publish_question(second, self.result(second)))

    def test_expired_attempt_limit_and_missing_deadline_fail_closed(self):
        """无参数；第二次租约过期不无限重试，无截止时间也不执行模型。"""
        self.enqueue()
        first = claim(self.owner_a)
        self.expired(first)
        second = claim(self.owner_a)
        self.expired(second)
        self.assertIsNone(claim(self.owner_a))
        self.assert_unpublished('RUN_FAILED')
        accepted = self.enqueue(1, '继续补充。')
        self.manager.execute('UPDATE runs_job SET deadline=NULL WHERE id=%s AND owner_id=%s',
                             [accepted['job_id'], self.owner_a])
        self.assertIsNone(claim(self.owner_a))
        with owner_transaction(self.owner_a):
            self.assertEqual(Job.objects.get(pk=accepted['job_id']).error_code, 'RUN_TIMEOUT')

    def test_later_input_stales_old_work_and_latest_claim_keeps_both_messages(self):
        """无参数；模型执行间新消息到达，旧结果不发布且下一次包含两条原话。"""
        self.enqueue()
        first = claim(self.owner_a)
        old_result = self.result(first)
        self.enqueue(1, '预算只有100元。')
        self.assertFalse(publish_question(first, old_result))
        self.assert_unpublished('RUN_STALE')
        latest = claim(self.owner_a)
        self.assertEqual([item['sequence'] for item in latest.messages], [1, 2])
        self.assertTrue(publish_question(latest, self.result(latest)))
        with owner_transaction(self.owner_a):
            state = Problem.objects.get().core_state
            self.assertEqual([event['source_message'] for event in state['events'][:-1]],
                             [item['content'] for item in latest.messages])
            self.assertEqual(Problem.objects.get().processed_message_sequence, 2)

    def test_claim_skips_stale_queued_candidate_and_keeps_unprocessed_input(self):
        """无参数；较旧queued终结后同次领取继续寻找最新修订。"""
        self.enqueue()
        latest = self.enqueue(1, '第二条事实。')
        lease = claim(self.owner_a)
        self.assertEqual(str(lease.job_id), latest['job_id'])
        self.assertEqual(len(lease.messages), 2)
        self.assert_unpublished('RUN_STALE')

    def test_revoked_rights_checked_without_access_revision_change(self):
        """无参数；许可字段发生实际变化即撤销发布，不依赖updated_at或epoch。"""
        accepted = self.enqueue()
        lease = claim(self.owner_a)
        result = self.result(lease)
        self.change('knowledge_rightsrecord', self.right_a, allowed_uses=Jsonb(['browse', 'quote']))
        self.assertFalse(publish_question(lease, result))
        self.assert_unpublished('ACCESS_REVOKED')
        with self.assertRaises(ProblemError):
            list_events(self.user_a, accepted['job_id'])

    def test_cancel_requested_is_terminalized_by_heartbeat(self):
        """无参数；运行中取消保持请求语义，下一心跳记录真实cancelled事件。"""
        accepted = self.enqueue()
        lease = claim(self.owner_a)
        self.assertEqual(cancel_job(self.user_a, accepted['job_id'])[1], 202)
        self.assertFalse(heartbeat(lease))
        self.assertFalse(publish_question(lease, self.result(lease)))
        self.assert_unpublished('RUN_CANCELLED')
        self.assertEqual(list_events(self.user_a, accepted['job_id'])[-1]['event_type'], 'cancelled')

    def test_queued_cancellation_emits_one_event_and_never_claims(self):
        """无参数；首次排队取消真实落库，重复请求不增加终态事件。"""
        accepted = self.enqueue()
        cancel_job(self.user_a, accepted['job_id'])
        cancel_job(self.user_a, accepted['job_id'])
        self.assertIsNone(claim(self.owner_a))
        events = list_events(self.user_a, accepted['job_id'])
        self.assertEqual([(event['seq'], event['event_type']) for event in events], [(1, 'cancelled')])

    def test_epoch_change_and_failure_code_are_fixed(self):
        """无参数；账户epoch变化即时阻止续租，异常原文不能成为公开错误。"""
        self.enqueue()
        lease = claim(self.owner_a)
        self.change('accounts_user', self.owner_a, auth_epoch=1)
        self.assertFalse(heartbeat(lease))
        self.assert_unpublished('ACCESS_REVOKED')

    def test_failure_unknown_code_is_normalized_and_does_not_consume(self):
        """无参数；私有异常字符串只映射固定RUN_FAILED，失败结果不消费原消息。"""
        self.enqueue()
        lease = claim(self.owner_a)
        self.assertTrue(finish_failure(lease, 'private upstream body'))
        self.assert_unpublished('RUN_FAILED')

    def test_disabled_account_and_expired_overall_deadline_do_not_publish(self):
        """无参数；账号禁用后仍可由worker收尾，但不能发布内容。"""
        self.enqueue()
        lease = claim(self.owner_a)
        self.change('accounts_user', self.owner_a, status='disabled')
        self.assertFalse(publish_question(lease, self.result(lease)))
        self.assert_unpublished('ACCESS_REVOKED')

    def test_overall_deadline_expires_even_while_lease_is_live(self):
        """无参数；整体超时不能以续租延长。"""
        self.enqueue()
        lease = claim(self.owner_a)
        self.manager.execute('UPDATE runs_job SET deadline=%s WHERE id=%s AND owner_id=%s',
                             [timezone.now() - timedelta(seconds=1), lease.job_id, self.owner_a])
        self.assertFalse(heartbeat(lease))
        self.assert_unpublished('RUN_TIMEOUT')

    def test_tampered_state_or_source_is_not_published(self):
        """无参数；合法schema不足以发布，原状态、来源和事件结果必须一致。"""
        self.enqueue()
        lease = claim(self.owner_a)
        result = copy.deepcopy(self.result(lease))
        result['events'][0]['source_message'] = '模型伪造的原话。'
        self.assertFalse(publish_question(lease, result))
        self.assert_unpublished('MODEL_OUTPUT_INVALID')

    def test_event_rls_foreign_key_payload_and_minimal_grants(self):
        """无参数；原始ORM/SQL受FORCE RLS、复合owner关联和固定负载限制。"""
        self.enqueue()
        lease = claim(self.owner_a)
        self.assertEqual(JobEvent.objects.count(), 0)
        with owner_transaction(self.owner_b):
            self.assertEqual(JobEvent.objects.count(), 0)
        with self.assertRaises(DatabaseError):
            with owner_transaction(self.owner_b):
                JobEvent.objects.create(owner=self.user_b, job_id=lease.job_id, seq=2,
                    event_type='stage', public_payload={'job_id': str(lease.job_id),
                        'run_id': str(lease.run_id), 'stage': 'understanding'})
        with self.assertRaises(DatabaseError):
            with owner_transaction(self.owner_a):
                JobEvent.objects.update(public_payload={'prompt': '禁止公开'})
        with connection.cursor() as cursor:
            cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid='runs_jobevent'::regclass")
            self.assertEqual(cursor.fetchone(), (True, True))
            for permission in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                cursor.execute("SELECT has_table_privilege(current_user,'runs_jobevent',%s)", [permission])
                self.assertEqual(cursor.fetchone()[0], permission in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'))
        with self.assertRaises(ProblemError):
            list_events(self.user_b, lease.job_id)
