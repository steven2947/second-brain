"""实际CSRF登录后的问题建档流程，不替换服务或数据库授权。"""
import json
from uuid import uuid4

from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone
from jsonschema import Draft202012Validator

from config.contracts import build_contract
from tests.knowledge_fixtures import KnowledgeFixtureCase


class ProblemFlowTests(KnowledgeFixtureCase):
    """把创建、保存、修改、冲突和失权作为整条HTTP流程验收。"""

    def setUp(self):
        """无参数；只建立本测试用户的真实Cookie会话，结束精确清理。"""
        super().setUp()
        self.session_keys = []
        self.addCleanup(self.cleanup_private)
        self.a, self.b = self.login(self.user_a), self.login(self.user_b)
        self.contract = build_contract()

    def login(self, user):
        """user为自编测试账号；不用force_login绕过成熟密码与CSRF入口。"""
        password = 'Local-Problem-Orchid-672!'
        user.set_password(password)
        user.save(update_fields=['password'])
        client = Client(enforce_csrf_checks=True)
        token = client.get('/api/v1/auth/csrf').json()['csrf_token']
        response = client.post('/api/v1/auth/login', {'email': user.email, 'password': password},
                               content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.session_keys.append(client.cookies[settings.SESSION_COOKIE_NAME].value)
        return client

    def cleanup_private(self):
        """无参数；只清除本用例新建的会话与本人草稿，先于父夹具清理知识。"""
        Session.objects.filter(session_key__in=self.session_keys).delete()
        for table in ('problems_idempotencyrecord', 'problems_problem'):
            if self.manager.execute('SELECT to_regclass(%s)', [table]).fetchone()[0]:
                self.manager.execute(f'DELETE FROM {table} WHERE owner_id IN (%s,%s,%s)',
                                     [self.owner_a, self.owner_b, self.owner_c])

    def write(self, client, method, url, data, key=None):
        """client/method/url/data为实际写操作，key为可选显式幂等标识。"""
        token = client.get('/api/v1/auth/csrf').json()['csrf_token']
        headers = {'HTTP_X_CSRFTOKEN': token}
        if key is not None:
            headers['HTTP_IDEMPOTENCY_KEY'] = key
        return getattr(client, method)(url, json.dumps(data, ensure_ascii=False),
                                       content_type='application/json', **headers)

    def public(self, response, name='Problem', status=200):
        """response为真实HTTP结果；name/status为该操作公开契约。"""
        self.assertEqual(response.status_code, status, response.content[:240])
        self.assertEqual(response['Cache-Control'], 'no-store')
        schema = {'$ref': f'#/components/schemas/{name}', 'components': self.contract['components']}
        Draft202012Validator(schema).validate(response.json())
        for private in ('core_state', 'owner_id', 'storage_key', 'internal_prompt'):
            self.assertNotIn(private, response.json())
        return response.json()

    def create(self, question='我该怎样验证自己的想法？', key='first'):
        """question/key为自编原问题和显式提交标识；创建只获得档案。"""
        data = {'question': question, 'goal': 'act', 'release_id': str(self.release_a)}
        return self.public(self.write(self.a, 'post', '/api/v1/problems', data, key), status=201)

    def test_create_replay_read_edit_archive_and_revision_conflict(self):
        """无参数；一次提交只建一份，更新冲突不覆盖，归档和恢复保持原问题。"""
        question = '  我该怎样验证？\n保留我的表达。 '
        first = self.create(question)
        self.assertEqual(self.create(question), first)
        url = '/api/v1/problems/' + first['id']
        self.assertEqual(self.public(self.a.get(url)), first)
        changed = self.public(self.write(self.a, 'patch', url,
            {'title': '验证下一步', 'expected_revision': 0}))
        self.assertEqual(changed['revision'], 1)
        self.assertEqual(changed['original_question'], question)
        conflict = self.write(self.a, 'patch', url, {'title': '不能覆盖', 'expected_revision': 0})
        self.assertEqual(self.public(conflict, 'ProblemConflictResponse', 409)['error']['current_revision'], 1)
        archived = self.public(self.write(self.a, 'patch', url, {'status': 'archived', 'expected_revision': 1}))
        self.assertEqual(archived['revision'], 2)
        self.assertEqual(self.public(self.a.get('/api/v1/problems'), 'ProblemPage')['items'], [])
        items = self.public(self.a.get('/api/v1/problems?status=archived'), 'ProblemPage')['items']
        self.assertEqual([item['id'] for item in items], [first['id']])
        restored = self.public(self.write(self.a, 'patch', url, {'status': 'active', 'expected_revision': 2}))
        self.assertEqual(restored['original_question'], question)
        self.assertEqual(restored['clarification']['rounds'], 0)
        self.assertIsNone(restored['current_answer_id'])

    def test_other_owner_cannot_read_write_or_create_in_foreign_library(self):
        """无参数；B看不到A的档案、修订和知识版本，也不能借创建越权。"""
        first = self.create()
        url = '/api/v1/problems/' + first['id']
        self.assertEqual(self.b.get(url).status_code, 404)
        self.assertEqual(self.write(self.b, 'patch', url, {'title': '越权', 'expected_revision': 0}).status_code, 404)
        self.assertEqual(self.public(self.b.get('/api/v1/problems'), 'ProblemPage')['items'], [])
        forbidden = self.write(self.b, 'post', '/api/v1/problems',
            {'question': '不能借创建访问', 'goal': 'act', 'release_id': str(self.release_a)}, 'foreign')
        self.assertEqual(forbidden.status_code, 404)

    def test_revoked_library_keeps_own_question_but_blocks_create_replay(self):
        """无参数；本人原文仍可读取，撤权后不能从幂等历史重新获得可用授权。"""
        first = self.create()
        self.change('knowledge_librarygrant', self.grant_a, status='revoked', revoked_at=timezone.now())
        own = self.public(self.a.get('/api/v1/problems/' + first['id']))
        self.assertFalse(own['library_available'])
        self.assertEqual(own['original_question'], first['original_question'])
        replay = self.write(self.a, 'post', '/api/v1/problems',
            {'question': first['original_question'], 'goal': 'act', 'release_id': str(self.release_a)}, 'first')
        self.assertEqual(replay.status_code, 404)

    def test_long_chinese_question_and_invalid_writes_leave_account_limit_unchanged(self):
        """无参数；中文4000字符保存成功，缺幂等/未知owner/错误类型拒绝，账号仍8KB。"""
        self.assertEqual(len(self.create('问' * 4000)['original_question']), 4000)
        valid = {'question': '测试', 'goal': 'act', 'release_id': str(self.release_a)}
        self.assertEqual(self.write(self.a, 'post', '/api/v1/problems', valid).status_code, 400)
        invalid = self.write(self.a, 'post', '/api/v1/problems', {**valid, 'owner_id': str(uuid4())}, 'bad')
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.write(self.a, 'post', '/api/v1/problems', valid, 'first').status_code, 409)
        token = self.a.get('/api/v1/auth/csrf').json()['csrf_token']
        response = self.a.patch('/api/v1/me', ' ' * 9000 + '{}', content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 400)
