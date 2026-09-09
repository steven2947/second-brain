"""工作进程接真实数据库与旧核心；仅注入自编提案，不冒充线上模型效果。"""
import importlib
from pathlib import Path
from uuid import uuid4
from django.db.models import Max
from django.utils import timezone
from psycopg.types.json import Jsonb
from access.context import owner_transaction
from ai.ports import Generation
from problems.models import Problem, Message
from problems.services import create_draft
from runs.models import Job
from runs.services import send_message, get_job
from tests.knowledge_fixtures import KnowledgeFixtureCase


class WorkerTests(KnowledgeFixtureCase):
    """整轮领取→处理→发布/失败，不mock任务或核心状态机。"""

    def setUp(self):
        """无参数；先确认入口已实现，再创建自编授权与问题。"""
        self.assertTrue((Path(__file__).resolve().parents[1]/'runs/worker.py').exists(),'缺少执行器')
        super().setUp()
        self.worker = importlib.import_module('runs.worker')
        self.addCleanup(self.cleanup_private)
        self.change('knowledge_rightsrecord',self.right_a,allowed_uses=Jsonb(['browse','quote','analyze']))
        self.problem = create_draft(self.user_a,{'question':'我该如何验证需求？','goal':'act','release_id':self.release_a},'draft')

    def cleanup_private(self):
        """无参数；先解除循环，再按依赖反序删除当前三个测试owner记录。"""
        owners = [self.owner_a,self.owner_b,self.owner_c]
        self.manager.execute('UPDATE problems_message SET run_id=NULL WHERE owner_id=ANY(%s)',[owners])
        for table in ('operations_usageentry','operations_runreservation','operations_quotabucket','answers_answer','runs_jobevent','runs_analysisrun','runs_job','problems_message','problems_idempotencyrecord','problems_problem'):
            self.manager.execute(f'DELETE FROM {table} WHERE owner_id=ANY(%s)',[owners])

    def send(self, text, revision):
        """text/revision为实际服务原文与已读修订，客户端标识每次独立。"""
        return send_message(self.user_a,self.problem['id'],{'content':text,'intent':'supplement',
            'client_message_id':uuid4(),'expected_revision':revision},str(uuid4()))

    def scripted(self, responses):
        """responses为自编JSON提案，生产没有此provider。"""
        class Scripted:
            def generate(self, request):
                """request由真实编排器传入，仅返回测试提供的下一条提案。"""
                return Generation(content=responses.pop(0))
        return Scripted()

    def test_disabled_model_ends_job_without_fake_question(self):
        """无参数；未配置模型的任务明确失败，不在queued无限挂起或假造回复。"""
        result = self.send('还未向访谈者报过价。',0)
        self.assertTrue(self.worker.process_one(self.owner_a))
        job = get_job(self.user_a,result['job_id'])
        self.assertEqual((job['status'],job['error_code']),('failed','MODEL_UNAVAILABLE'))
        with owner_transaction(self.owner_a):
            self.assertFalse(Message.objects.filter(role='assistant').exists())
            self.assertEqual(Problem.objects.get().processed_message_sequence,0)
        self.assertFalse(self.worker.process_one(self.owner_a))

    def test_latest_run_applies_both_messages_and_publishes_one_question(self):
        """无参数；第一轮过时，第二轮包含所有尚未消费原话并原子发布一次追问。"""
        self.send('  尚未报价。\n',0)
        newest = self.send('预算只有100元。',1)
        provider = self.scripted([
            {'changes':{'facts':['尚未报价']},'reason':'第一条事实。'},
            {'changes':{'constraints':['预算100元']},'reason':'第二条约束。'},
            {'type':'ask','question':'你希望先验证价格还是场景？','reason':'这会改变实验设计。'}])
        self.assertTrue(self.worker.process_one(self.owner_a,provider=provider))
        self.assertEqual(get_job(self.user_a,newest['job_id'])['status'],'succeeded')
        with owner_transaction(self.owner_a):
            problem = Problem.objects.get()
            self.assertEqual((problem.revision,problem.processed_message_sequence),(3,2))
            self.assertEqual(Message.objects.filter(role='assistant').get().content,'你希望先验证价格还是场景？')
            self.assertEqual(Message.objects.aggregate(value=Max('sequence'))['value'],3)
            self.assertEqual(Job.objects.filter(status='failed',error_code='RUN_STALE').count(),1)
        self.change('knowledge_librarygrant',self.grant_a,status='revoked',revoked_at=timezone.now())
        from problems.services import get_draft
        self.assertIsNone(get_draft(self.user_a,self.problem['id'])['clarification']['pending_question'])

    def test_uncovered_request_reports_gap_without_fake_answer(self):
        """无参数；prepare后的真实检索无候选，发布缺口但不构造正式答案。"""
        result = self.send('先帮我梳理已经知道的情况。',0)
        provider = self.scripted([{'changes':{},'reason':'保留未知。'},
            {'type':'prepare','retrieval_focus':'需求验证方法','query_expansions':[], 'reason':'可以进入知识检索。'}])
        self.assertTrue(self.worker.process_one(self.owner_a,provider=provider))
        self.assertEqual(get_job(self.user_a,result['job_id'])['status'],'succeeded')
        with owner_transaction(self.owner_a):
            from answers.models import Answer
            from runs.models import AnalysisRun
            self.assertEqual(Problem.objects.get().processed_message_sequence,1)
            self.assertFalse(Answer.objects.exists())
            self.assertEqual(AnalysisRun.objects.get().outcome,'coverage_gap')
            self.assertEqual(Message.objects.get(role='assistant').kind,'notice')
