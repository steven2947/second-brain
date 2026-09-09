"""自编知识和自编provider跑真实学习队列；不消费真实模型。"""
from unittest.mock import patch
from uuid import uuid4
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import DatabaseError
from django.test import Client
from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb
from access.context import owner_transaction
from ai.ports import Generation, DisabledProvider
from config.contracts import build_contract
from knowledge.repository import KnowledgeRepository
from learning import services
from learning.models import LearningSession, LearningTurn
from operations.models import UsageEntry, QuotaBucket, RunReservation
from problems.models import Problem
from problems.services import ProblemError, create_draft
from runs.models import AnalysisRun, Job
from runs.queue import claim, heartbeat
from runs.services import get_job as problem_job, cancel_job as problem_cancel
from runs.worker import process_one
from tests.knowledge_fixtures import KnowledgeFixtureCase


class LearningProvider:
    """可审阅自编提案，断言原理输入完整且反馈具有真实原回答。"""
    def __init__(self, invalid=False, action=None):
        """invalid模拟错卡，action模拟调用期间授权或状态变化。"""
        self.calls, self.invalid, self.action = [], invalid, action

    def generate(self, request):
        """request为共享MeteredProvider提交后的固定服务器输入。"""
        self.calls.append(request)
        if self.action:
            self.action()
        card = request.context['fixed_input']['cards'][0]
        assert card['book']['title']
        assert 'author_display' in card['book']
        assert request.context['history'][-1] == request.context['input_turn']
        if request.context['mode'] == 'respond':
            assert request.context['input_turn']['kind'] == 'user_response'
            assert request.context['exercise']['kind'] == 'exercise'
        return Generation({'text': '根据原理具体分析：先明确可逆边界，再在可控范围进行试验。',
            'sections': [{'title': '原理与条件', 'body': '可逆试验让信息逐步增加；损失超出边界应停止。',
                          'basis_card_ids': ['invented'] if self.invalid else [card['id']]},
                         {'title': '应用例子', 'body': '设定一次小范围尝试并记录原始结果。', 'basis_card_ids': []}]})


class LearningTests(KnowledgeFixtureCase):
    """真实runtime RLS、数据库约束、HTTP与worker的一组纵向验证。"""
    def setUp(self):
        """无参数；只使用自编固定库，授权沿用browse与analyze。"""
        super().setUp()
        self.addCleanup(self.cleanup_private)
        self.change('knowledge_rightsrecord', self.right_a, allowed_uses=Jsonb(['browse', 'analyze']))
        self.ids = [item['card_id'] for item in KnowledgeRepository(self.user_a).list_cards(self.release_a)['items']]
        self.data = {'release_id': str(self.release_a), 'basis_card_ids': self.ids, 'goal': '理解可逆试验的原理与边界'}

    def cleanup_private(self):
        """无参数；只清理本fixture owner，按学习和共享外键反序删除。"""
        owners = [self.owner_a, self.owner_b, self.owner_c]
        for table in ('learning_learningturn', 'operations_usageentry', 'operations_runreservation',
                      'operations_quotabucket', 'runs_jobevent', 'runs_analysisrun', 'runs_job',
                      'learning_learningsession', 'problems_idempotencyrecord', 'problems_problem'):
            self.manager.execute(f'DELETE FROM {table} WHERE owner_id=ANY(%s)', [owners])

    def create(self):
        """无参数；显式创建本人独立学习会话。"""
        return services.create_session(self.user_a, self.data, str(uuid4()))

    def enqueue(self, session, mode='explain', content='请展开原理和边界。', responds=None):
        """session为已读公开会话；mode/content/responds构成本次实际用户消息。"""
        data = {'content': content, 'client_message_id': str(uuid4()),
                'expected_revision': session['revision'], 'mode': mode}
        if responds:
            data['responds_to_turn_id'] = responds
        return services.send_message(self.user_a, session['id'], data, str(uuid4()))

    def detail(self, session):
        """session为本人公开会话；读取当前回合和实际修订。"""
        return services.get_detail(self.user_a, session['id'], {})

    def login(self, user):
        """user为自编普通账号；实际会话登录获取CSRF，不伪造认证。"""
        password = 'Learning-Test-Password-732!'
        user.set_password(password)
        user.save(update_fields=['password'])
        browser = Client(enforce_csrf_checks=True)
        token = browser.get('/api/v1/auth/csrf').json()['csrf_token']
        response = browser.post('/api/v1/auth/login', {'email': user.email, 'password': password},
                                content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        session_key = browser.cookies[settings.SESSION_COOKIE_NAME].value
        self.addCleanup(lambda: Session.objects.filter(session_key=session_key).delete())
        browser.defaults['HTTP_X_CSRFTOKEN'] = browser.get('/api/v1/auth/csrf').json()['csrf_token']
        return browser

    def test_full_http_and_worker_learning_loop(self):
        """无参数；创建零任务，解释/自编练习/原回答/针对反馈分别持久化并按轮计量。"""
        browser = self.login(self.user_a)
        response = browser.post('/api/v1/learning', self.data, content_type='application/json', HTTP_IDEMPOTENCY_KEY='create')
        self.assertEqual(response.status_code, 201, response.content)
        session = response.json()
        with owner_transaction(self.owner_a):
            self.assertEqual((Problem.objects.count(), Job.objects.count(), UsageEntry.objects.count()), (0, 0, 0))
        provider = LearningProvider()
        for mode in ('explain', 'practice', 'respond'):
            detail = self.detail(session)
            original = '我先限制损失预算，再测试可撤回的步骤。' if mode == 'respond' else '请帮助我学习。'
            data = {'content': original, 'client_message_id': str(uuid4()),
                    'expected_revision': detail['session']['revision'], 'mode': mode}
            if mode == 'respond':
                data['responds_to_turn_id'] = detail['items'][-1]['id']
            response = browser.post(f"/api/v1/learning/{session['id']}/messages", data,
                content_type='application/json', HTTP_IDEMPOTENCY_KEY=str(uuid4()))
            self.assertEqual(response.status_code, 202, response.content)
            self.assertEqual(self.detail(session)['active_job']['status'], 'queued')
            self.assertTrue(process_one(self.owner_a, provider=provider))
            self.assertEqual(services.get_job(self.user_a, session['id'], response.json()['job_id'])['status'], 'succeeded')
        response = browser.get(f"/api/v1/learning/{session['id']}")
        self.assertEqual(response.status_code, 200, response.content)
        Draft202012Validator({'$ref': '#/components/schemas/LearningDetail',
            'components': build_contract()['components']}).validate(response.json())
        detail = response.json()
        self.assertEqual([turn['kind'] for turn in detail['items']],
                         ['user_request', 'explanation', 'user_request', 'exercise', 'user_response', 'feedback'])
        self.assertIn('系统自编练习', detail['items'][3]['content']['text'])
        self.assertEqual(detail['items'][4]['content']['text'], original)
        self.assertEqual(detail['items'][5]['responds_to_turn_id'], detail['items'][4]['id'])
        self.assertTrue(detail['items'][1]['content']['sections'][1]['title'].startswith('AI延伸：'))
        self.assertIsNone(detail['active_job'])
        self.assertEqual(len(provider.calls), 3)
        self.assertEqual([len(call.context['history']) for call in provider.calls], [1, 3, 5])
        with owner_transaction(self.owner_a):
            self.assertEqual(set(UsageEntry.objects.values_list('purpose', flat=True)), {'learning'})
            self.assertTrue(all(row.input_tokens is None and row.output_tokens is None for row in UsageEntry.objects.all()))
            self.assertEqual((QuotaBucket.objects.get().reserved_runs, QuotaBucket.objects.get().settled_runs), (0, 3))
        raw = response.content.decode()
        self.assertNotIn('fixed_input', raw)
        self.assertNotIn('authorization_snapshot', raw)

    def test_idempotency_revision_and_real_response_required(self):
        """无参数；双重去重不多排队，空回答/跨会话练习/旧修订不可接受。"""
        session = services.create_session(self.user_a, self.data, 'same')
        self.assertEqual(services.create_session(self.user_a, self.data, 'same'), session)
        data = {'content': '请设计练习', 'client_message_id': str(uuid4()), 'expected_revision': 0, 'mode': 'practice'}
        first = services.send_message(self.user_a, session['id'], data, 'message')
        self.assertEqual(services.send_message(self.user_a, session['id'], data, 'message'), first)
        self.assertEqual(services.send_message(self.user_a, session['id'], data, 'second-key'), first)
        with self.assertRaises(ProblemError) as error:
            self.enqueue(session)
        self.assertEqual(error.exception.code, 'REVISION_CONFLICT')
        process_one(self.owner_a, provider=LearningProvider())
        exercise = self.detail(session)['items'][-1]
        current = self.detail(session)['session']
        for content, target in [('', exercise['id']), ('   ', exercise['id']), ('我的回答', str(uuid4()))]:
            with self.assertRaises(ProblemError):
                self.enqueue(current, 'respond', content, target)
        other = self.create()
        with self.assertRaises(ProblemError):
            self.enqueue(other, 'respond', '我的回答', exercise['id'])
        with owner_transaction(self.owner_a):
            self.assertEqual((AnalysisRun.objects.count(), LearningTurn.objects.count()), (1, 2))

    def test_owner_release_and_parent_domain_isolation(self):
        """无参数；B不可见A，问题任务端点不能读取或取消学习任务，DB阻止跨归属。"""
        session = self.create()
        accepted = self.enqueue(session)
        self.assertEqual(services.list_sessions(self.user_b, {})['items'], [])
        for operation in (lambda: services.get_detail(self.user_b, session['id'], {}),
                          lambda: services.get_job(self.user_b, session['id'], accepted['job_id'], cancel=True),
                          lambda: problem_job(self.user_a, accepted['job_id']),
                          lambda: problem_cancel(self.user_a, accepted['job_id'])):
            with self.assertRaises(ProblemError) as error:
                operation()
            self.assertEqual(error.exception.status, 404)
        with owner_transaction(self.owner_b):
            self.assertEqual(LearningSession.objects.count(), 0)
        with self.assertRaises(DatabaseError), owner_transaction(self.owner_b):
            LearningTurn.objects.create(owner=self.user_b, learning_session_id=session['id'], sequence=8,
                kind='user_request', content={'text': '跨用户', 'sections': []})
        with self.assertRaises(DatabaseError), owner_transaction(self.owner_a):
            AnalysisRun.objects.filter(pk=accepted['run_id']).update(release_id=self.release_b)
        problem = create_draft(self.user_a, {'question': '真正的问题', 'goal': 'explain', 'release_id': self.release_a}, 'problem')
        linked = services.create_session(self.user_a, {**self.data, 'problem_id': problem['id']}, 'linked')
        self.assertEqual(linked['problem_id'], problem['id'])

    def test_revocation_cancellation_and_archival_block_publication(self):
        """无参数；取消释放未调用额度，归档令租约失效，撤权隐藏已有学习并阻止迟到输出。"""
        session = self.create()
        accepted = self.enqueue(session)
        result, status = services.get_job(self.user_a, session['id'], accepted['job_id'], cancel=True)
        self.assertEqual((status, result['status']), (200, 'cancelled'))
        self.assertFalse(process_one(self.owner_a, provider=LearningProvider()))
        current = self.detail(session)['session']
        accepted = self.enqueue(current)
        lease = claim(self.owner_a)
        services.archive_session(self.user_a, session['id'], {'expected_revision': accepted['revision']})
        self.assertFalse(heartbeat(lease))
        self.assertEqual(services.get_job(self.user_a, session['id'], accepted['job_id'])['error_code'], 'RUN_STALE')
        session = self.create()
        accepted = self.enqueue(session)
        provider = LearningProvider(action=lambda: self.change('knowledge_rightsrecord', self.right_a,
            allowed_uses=Jsonb(['browse'])))
        self.assertTrue(process_one(self.owner_a, provider=provider))
        with self.assertRaises(ProblemError):
            self.detail(session)
        with owner_transaction(self.owner_a):
            self.assertEqual(Job.objects.get(pk=accepted['job_id']).error_code, 'ACCESS_REVOKED')
            self.assertEqual(LearningTurn.objects.filter(kind='explanation').count(), 0)

    def test_disabled_invalid_output_and_quota_have_no_fake_success(self):
        """无参数；disabled零调用释放额度，错卡不发布，配额拒绝原子回滚原消息。"""
        session = self.create()
        accepted = self.enqueue(session)
        process_one(self.owner_a, provider=DisabledProvider())
        self.assertEqual(services.get_job(self.user_a, session['id'], accepted['job_id'])['error_code'], 'MODEL_UNAVAILABLE')
        with owner_transaction(self.owner_a):
            self.assertEqual(UsageEntry.objects.count(), 0)
            self.assertEqual(RunReservation.objects.get().state, 'released')
        accepted = self.enqueue(self.detail(session)['session'])
        process_one(self.owner_a, provider=LearningProvider(invalid=True))
        self.assertEqual(services.get_job(self.user_a, session['id'], accepted['job_id'])['error_code'], 'MODEL_OUTPUT_INVALID')
        self.manager.execute('UPDATE operations_quotabucket SET limit_runs=settled_runs WHERE owner_id=%s', [self.owner_a])
        with self.assertRaises(ProblemError) as error:
            self.enqueue(self.detail(session)['session'])
        self.assertEqual(error.exception.code, 'QUOTA_EXCEEDED')
        with owner_transaction(self.owner_a):
            self.assertEqual((AnalysisRun.objects.count(), LearningTurn.objects.count()), (2, 2))

    def test_pagination_signature_and_single_library_read(self):
        """无参数；分页不跨owner/会话复用，卡输入与摘要只加载一次完整版本。"""
        from knowledge.release_loader import load_release
        with patch('knowledge.repository.load_release', wraps=load_release) as loader:
            session = self.create()
            self.assertEqual(loader.call_count, 1)
        self.enqueue(session)
        process_one(self.owner_a, provider=LearningProvider())
        with patch('knowledge.repository.load_release', wraps=load_release) as loader:
            page = services.get_detail(self.user_a, session['id'], {'limit': 1})
            self.assertEqual(loader.call_count, 1)
        self.assertIsNotNone(page['next_cursor'])
        second = services.get_detail(self.user_a, session['id'], {'limit': 1, 'cursor': page['next_cursor']})
        self.assertEqual(second['items'][0]['sequence'], 2)
        other = self.create()
        with self.assertRaises(ProblemError):
            services.get_detail(self.user_a, other['id'], {'limit': 1, 'cursor': page['next_cursor']})
        with owner_transaction(self.owner_a):
            target = LearningTurn.objects.filter(kind='user_request').first()
            with self.assertRaises(DatabaseError), owner_transaction(self.owner_a):
                LearningTurn.objects.create(owner=self.user_a, learning_session_id=session['id'], sequence=3,
                    kind='feedback', responds_to_turn=target, content={'text': '没有真实回答不能反馈', 'sections': []})
