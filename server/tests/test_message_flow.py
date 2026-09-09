"""实际CSRF登录贯通问题、消息入队、状态和取消；无模型替身。"""
from uuid import uuid4
from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone
from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb
from config.contracts import build_contract
from tests.knowledge_fixtures import KnowledgeFixtureCase


class MessageFlowTests(KnowledgeFixtureCase):
    """自编材料的端到端HTTP，只写固定测试库并精确清理本用例记录。"""

    def setUp(self):
        """无参数；普通实际登录，知识用途只在当前用例增加分析。"""
        super().setUp()
        self.addCleanup(self.cleanup_private)
        self.sessions = []
        self.addCleanup(lambda: Session.objects.filter(session_key__in=self.sessions).delete())
        self.contract = build_contract()
        self.change('knowledge_rightsrecord', self.right_a, allowed_uses=Jsonb(['browse','quote','analyze']))
        self.a = self.login(self.user_a)
        self.b = self.login(self.user_b)
        response = self.post(self.a, '/api/v1/problems',
            {'question':'我有25次访谈，但还未报价。','goal':'act','release_id':str(self.release_a)}, 'create')
        self.assertEqual(response.status_code, 201)
        self.prefix = '/api/v1/problems/'+response.json()['id']

    def login(self, user):
        """user为本用例临时普通账号，不使用force_login或模拟身份服务。"""
        password = 'Local-Messages-Orchid-672!'
        user.set_password(password)
        user.save(update_fields=['password'])
        browser = Client(enforce_csrf_checks=True)
        response = self.post(browser, '/api/v1/auth/login', {'email':user.email,'password':password})
        self.assertEqual(response.status_code, 200)
        self.sessions.append(browser.cookies[settings.SESSION_COOKIE_NAME].value)
        return browser

    def post(self, browser, url, data, key=None):
        """browser/url/data为真实写请求；key由调用场景显式指定，CSRF实际取得。"""
        token = browser.get('/api/v1/auth/csrf').json()['csrf_token']
        headers = {'HTTP_X_CSRFTOKEN':token}
        if key is not None:
            headers['HTTP_IDEMPOTENCY_KEY'] = key
        return browser.post(url, data, content_type='application/json', **headers)

    def cleanup_private(self):
        """无参数；解除本批循环引用后清理当前测试owner，不触碰主开发库。"""
        owners = [self.owner_a,self.owner_b,self.owner_c]
        self.manager.execute('UPDATE problems_message SET run_id=NULL WHERE owner_id=ANY(%s)',[owners])
        for table in ('operations_usageentry','operations_runreservation','operations_quotabucket','answers_answer','runs_jobevent','runs_analysisrun','runs_job','problems_message','problems_idempotencyrecord','problems_problem'):
            self.manager.execute(f'DELETE FROM {table} WHERE owner_id=ANY(%s)',[owners])

    def check(self, response, template, method='GET', status=200):
        """response与template/method对应唯一实际OpenAPI，逐字段核对公开载荷。"""
        self.assertEqual(response.status_code,status,response.content[:120])
        schema = self.contract['paths'][template][method.lower()]['responses'][str(status)]['content']['application/json']['schema']
        Draft202012Validator({**schema,'components':self.contract['components']}).validate(response.json())
        self.assertEqual(response['Cache-Control'],'no-store')
        for private in ('internal_state','authorization_snapshot','lease_token','system_prompt','/Users/'):
            self.assertNotIn(private,response.content.decode())
        return response.json()

    def test_message_job_cancel_and_list_are_real_and_public(self):
        """无参数；发送原文→同键重放→实际排队状态→取消，不捏造AI回复。"""
        data = {'content':'  补充：我想先用小实验报价。\n','intent':'supplement',
                'client_message_id':str(uuid4()),'expected_revision':0}
        accepted = self.check(self.post(self.a,self.prefix+'/messages',data,'message'),
            '/api/v1/problems/{problem_id}/messages','POST',202)
        self.assertEqual(self.post(self.a,self.prefix+'/messages',data,'message').json(),accepted)
        self.assertEqual(self.post(self.a,self.prefix+'/messages',{**data,'content':'不同内容'},'message').status_code,409)
        run_url, job_url = '/api/v1/runs/'+accepted['run_id'], '/api/v1/jobs/'+accepted['job_id']
        self.assertEqual(self.check(self.a.get(run_url),'/api/v1/runs/{run_id}')['status'],'queued')
        self.assertEqual(self.check(self.a.get(job_url),'/api/v1/jobs/{job_id}')['status'],'queued')
        page = self.check(self.a.get(self.prefix+'/messages'),'/api/v1/problems/{problem_id}/messages')
        self.assertEqual(page['revision'],1)
        self.assertEqual([item['content'] for item in page['items']],[data['content']])
        cancelled = self.check(self.post(self.a,job_url+'/cancel',{}),'/api/v1/jobs/{job_id}/cancel','POST',200)
        self.assertEqual(cancelled['status'],'cancelled')
        self.assertIsNotNone(cancelled['finished_at'])
        for url in (self.prefix+'/messages',run_url,job_url):
            self.assertEqual(self.b.get(url).status_code,404)

    def test_direct_analysis_conflict_and_revocation_preserve_user_messages(self):
        """无参数；直接分析有真实消息，陈旧修订无追加，撤权仍保留本人陈述。"""
        first = self.check(self.post(self.a,self.prefix+'/analyze',{'expected_revision':0},'analyze'),
            '/api/v1/problems/{problem_id}/analyze','POST',202)
        conflict = self.post(self.a,self.prefix+'/analyze',{'expected_revision':0},'new-key')
        self.assertEqual(conflict.status_code,409)
        self.assertEqual(conflict.json()['error']['current_revision'],1)
        self.change('knowledge_librarygrant',self.grant_a,status='revoked',revoked_at=timezone.now())
        page = self.a.get(self.prefix+'/messages').json()
        self.assertFalse(page['library_available'])
        self.assertEqual([item['content'] for item in page['items']],['请直接分析当前问题。'])
        self.assertEqual(self.a.get('/api/v1/jobs/'+first['job_id']).status_code,404)
        self.assertEqual(self.post(self.a,self.prefix+'/analyze',{'expected_revision':0},'analyze').status_code,404)

    def test_invalid_or_csrf_missing_message_does_not_write(self):
        """无参数；超长中文/额外owner/布尔修订/缺CSRF被拒，用户消息保持0。"""
        data = {'content':'字'*20000,'intent':'answer','client_message_id':str(uuid4()),'expected_revision':0}
        self.assertEqual(self.a.post(self.prefix+'/messages',data,content_type='application/json').status_code,403)
        for change in ({'content':'字'*20001},{'expected_revision':True},{'owner_id':str(self.owner_b)}):
            self.assertEqual(self.post(self.a,self.prefix+'/messages',{**data,**change},'invalid').status_code,400)
        self.assertEqual(self.a.get(self.prefix+'/messages').json()['items'],[])
        self.assertEqual(self.post(self.a,self.prefix+'/messages',data,'valid').status_code,202)
