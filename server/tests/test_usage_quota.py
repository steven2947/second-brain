"""固定测试库以实际runtime验证并发配额、调用账本和跨归属拒绝。"""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

from django.db import DatabaseError, close_old_connections
from django.utils import timezone
from psycopg.types.json import Jsonb

from access.context import owner_transaction
from accounts.models import User
from ai.ports import Generation, GenerationRequest, ModelFailure
from operations.models import QuotaBucket, RunReservation, UsageEntry
from operations.usage import MeteredProvider, QuotaExceeded, finalize_run, reserve_run
from problems.models import Problem
from problems.services import create_draft
from runs.models import AnalysisRun, Job
from runs.queue import claim, finish_failure
from runs.services import send_message
from tests.knowledge_fixtures import KnowledgeFixtureCase


class UsageQuotaTests(KnowledgeFixtureCase):
    """仅用自编provider；不推断线上质量、价格或未报告token。"""

    def setUp(self):
        """无参数；建立有真实分析授权的测试owner与问题。"""
        super().setUp()
        self.addCleanup(self.cleanup_private)
        self.change('knowledge_rightsrecord', self.right_a, allowed_uses=Jsonb(['browse', 'quote', 'analyze']))
        self.problem = create_draft(self.user_a, {'question': '如何验证需求？', 'goal': 'act',
            'release_id': self.release_a}, 'draft')

    def cleanup_private(self):
        """无参数；只清当前fixture的三个owner，先解除消息循环再逆序清理。"""
        owners = [self.owner_a, self.owner_b, self.owner_c]
        self.manager.execute('UPDATE problems_message SET run_id=NULL WHERE owner_id=ANY(%s)', [owners])
        for table in ('operations_usageentry', 'operations_runreservation', 'operations_quotabucket',
                      'answers_answer', 'runs_jobevent', 'runs_analysisrun', 'runs_job',
                      'problems_message', 'problems_idempotencyrecord', 'problems_problem'):
            self.manager.execute(f'DELETE FROM {table} WHERE owner_id=ANY(%s)', [owners])

    def enqueue(self, revision=0):
        """revision为已知问题修订；在正式排队接入前也明确预留一次以独立验证。"""
        result = send_message(self.user_a, self.problem['id'], {'content': '用户尚未付费。',
            'intent': 'supplement', 'client_message_id': uuid4(), 'expected_revision': revision}, str(uuid4()))
        with owner_transaction(self.owner_a):
            run = AnalysisRun.objects.get(pk=result['run_id'])
            reserve_run(self.user_a, run)
        return run

    def request(self):
        """无参数；私有正文仅进provider，不应在账本中落盘。"""
        return GenerationRequest('extract', '测试提示词', {'private': '不应进入账本'}, {},
            time.monotonic()+60, 100, lambda: False)

    def finish(self, run):
        """run为本fixture记录；模拟终态调用锁序并重复结算。"""
        with owner_transaction(run.owner_id):
            User.objects.select_for_update().get(pk=run.owner_id)
            Problem.objects.select_for_update().get(pk=run.problem_id)
            Job.objects.select_for_update().get(pk=run.job_id)
            finalize_run(run)
            finalize_run(run)

    def provider(self, generation=None, action=None):
        """generation/action仅为自编响应及网络进行中的可控事件。"""
        case = self
        class Scripted:
            calls = 0

            def generate(self, request):
                """request为实际调用输入；确认网络开始前已有提交的reserved记录。"""
                self.calls += 1
                row = case.manager.execute('SELECT usage_status FROM operations_usageentry WHERE owner_id=%s ORDER BY created_at DESC LIMIT 1',
                    [case.owner_a]).fetchone()
                case.assertEqual(row, ('reserved',))
                if action:
                    action()
                return generation or Generation({})
        return Scripted()

    def test_idempotent_reserve_and_release_without_calls(self):
        """无参数；同一run重复预留不多扣；零调用终态只释放一次。"""
        run = self.enqueue()
        with owner_transaction(self.owner_a):
            first = reserve_run(self.user_a, run)
            self.assertEqual(reserve_run(self.user_a, run).pk, first.pk)
            self.assertEqual(QuotaBucket.objects.get().reserved_runs, 1)
        self.finish(run)
        with owner_transaction(self.owner_a):
            bucket = QuotaBucket.objects.get()
            self.assertEqual((bucket.reserved_runs, bucket.settled_runs, bucket.revision), (0, 0, 2))
            self.assertEqual(RunReservation.objects.get().state, 'released')

    def test_concurrent_last_slot_and_transaction_rollback(self):
        """无参数；两个连接竞争最后一份额度，失败事务不得留下新增任务。"""
        first, second = self.enqueue(), self.enqueue(1)
        self.finish(first)
        self.finish(second)
        self.manager.execute('DELETE FROM operations_runreservation WHERE owner_id=%s', [self.owner_a])
        self.manager.execute('UPDATE operations_quotabucket SET limit_runs=1 WHERE owner_id=%s', [self.owner_a])
        barrier = Barrier(2)

        def compete(run):
            """run分别来自同owner的两轮；独立连接以真实账号锁竞争。"""
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                with owner_transaction(self.owner_a):
                    user = User.objects.get(pk=self.owner_a)
                    Job.objects.create(owner=user)
                    reserve_run(user, run)
                return 'reserved'
            except QuotaExceeded:
                return 'rejected'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(compete, [first, second]))
        self.assertCountEqual(results, ['reserved', 'rejected'])
        with owner_transaction(self.owner_a):
            self.assertEqual(Job.objects.count(), 3)
            self.assertEqual(QuotaBucket.objects.get().reserved_runs, 1)
            self.assertEqual(RunReservation.objects.count(), 1)

    def test_success_records_reported_usage_and_consumes_once(self):
        """无参数；每次调用保留各自token；两次调用仍只消费一轮额度。"""
        run = self.enqueue()
        inner = self.provider(Generation({}, provider='local', model='test-model', input_tokens=17, output_tokens=0))
        metered = MeteredProvider(inner, claim(self.owner_a))
        metered.generate(self.request())
        metered.generate(self.request())
        self.finish(run)
        with owner_transaction(self.owner_a):
            rows = list(UsageEntry.objects.order_by('call_index'))
            self.assertEqual([row.call_index for row in rows], [1, 2])
            self.assertTrue(all(row.input_tokens == 17 and row.output_tokens == 0 and row.cached_tokens is None
                and row.usage_status == 'settled' and row.cost_kind == 'unknown' and row.cost_amount is None
                and row.currency is None and row.duration_ms >= 0 for row in rows))
            self.assertEqual(rows[0].prompt_version, rows[1].prompt_version)
            bucket = QuotaBucket.objects.get()
            self.assertEqual((bucket.reserved_runs, bucket.settled_runs), (0, 1))

    def test_failed_call_preserves_unknown_usage_and_consumes(self):
        """无参数；实际调用异常只留下未知usage，不将错误原文或零费用写进账本。"""
        run = self.enqueue()

        def fail():
            """无参数；模拟供应商传输或协议失败。"""
            raise ModelFailure('MODEL_OUTPUT_INVALID')

        with self.assertRaises(ModelFailure):
            MeteredProvider(self.provider(action=fail), claim(self.owner_a)).generate(self.request())
        self.finish(run)
        with owner_transaction(self.owner_a):
            row = UsageEntry.objects.get()
            self.assertEqual((row.input_tokens, row.output_tokens, row.provider, row.model), (None, None, None, None))
            self.assertEqual(row.usage_status, 'settled')
            self.assertEqual(QuotaBucket.objects.get().settled_runs, 1)

    def test_invalid_content_keeps_already_reported_usage(self):
        """无参数；正文截断或JSON无效，但供应商已报告token时仍按实际报告入账。"""
        run = self.enqueue()
        def fail():
            """无参数；固定错误只携带安全usage，不携带无效正文。"""
            raise ModelFailure('MODEL_OUTPUT_INVALID', usage=Generation({}, provider='local',
                model='test-model', input_tokens=23, output_tokens=17))
        with self.assertRaises(ModelFailure):
            MeteredProvider(self.provider(action=fail), claim(self.owner_a)).generate(self.request())
        self.finish(run)
        with owner_transaction(self.owner_a):
            row = UsageEntry.objects.get()
            self.assertEqual((row.input_tokens, row.output_tokens), (23, 17))
            self.assertEqual(row.cost_kind, 'unknown')

    def test_stale_lease_cannot_begin_but_late_completion_is_accounted(self):
        """无参数；旧token不得发起调用；调用中终止仍能补账而不恢复发布权。"""
        run = self.enqueue()
        old = claim(self.owner_a)
        self.manager.execute('UPDATE runs_job SET lease_until=%s WHERE id=%s',
            [timezone.now()-timedelta(seconds=1), old.job_id])
        current = claim(self.owner_a)
        inner = self.provider()
        with self.assertRaises(ModelFailure):
            MeteredProvider(inner, old).generate(self.request())
        self.assertEqual(inner.calls, 0)

        def terminate():
            """无参数；供应商调用已经开始后终止本轮。"""
            self.assertTrue(finish_failure(current, 'RUN_FAILED'))
            self.finish(run)

        MeteredProvider(self.provider(Generation({}, input_tokens=8), terminate), current).generate(self.request())
        with owner_transaction(self.owner_a):
            row = UsageEntry.objects.get()
            self.assertEqual((row.attempt, row.input_tokens, row.usage_status), (2, 8, 'settled'))
            self.assertEqual(Job.objects.get().status, 'failed')
            self.assertEqual(QuotaBucket.objects.get().settled_runs, 1)

    def test_call_cap_and_invalid_metadata_are_bounded(self):
        """无参数；每尝试最多24次，恶意标识及非法计数保持NULL。"""
        self.enqueue()
        inner = self.provider(Generation({}, provider='bad\nbody', model='x'*241,
            input_tokens=True, output_tokens=-1, cached_tokens=2**64))
        metered = MeteredProvider(inner, claim(self.owner_a))
        for _ in range(24):
            metered.generate(self.request())
        with self.assertRaises(ModelFailure):
            metered.generate(self.request())
        self.assertEqual(inner.calls, 24)
        with owner_transaction(self.owner_a):
            self.assertEqual(UsageEntry.objects.count(), 24)
            row = UsageEntry.objects.first()
            self.assertEqual((row.provider, row.model, row.input_tokens, row.output_tokens, row.cached_tokens),
                (None, None, None, None, None))

    def test_rls_and_composite_owner_foreign_keys(self):
        """无参数；B不可读写A账本，伪装B归属关联A运行也被数据库拒绝。"""
        run = self.enqueue()
        MeteredProvider(self.provider(), claim(self.owner_a)).generate(self.request())
        self.assertEqual(UsageEntry.objects.count(), 0)
        with owner_transaction(self.owner_b):
            self.assertEqual(UsageEntry.objects.count(), 0)
            self.assertEqual(RunReservation.objects.count(), 0)
            self.assertEqual(QuotaBucket.objects.count(), 0)
        for owner in (self.owner_a, self.owner_b):
            with self.assertRaises(DatabaseError), owner_transaction(self.owner_b):
                UsageEntry.objects.create(owner_id=owner, run=run, attempt=1, call_index=2,
                    purpose='extract', prompt_version='a'*64)
        with self.assertRaises(DatabaseError), owner_transaction(self.owner_a):
            QuotaBucket.objects.update(reserved_runs=101)
