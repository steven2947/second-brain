"""真实问题路由及公开schema，不把规划的消息/任务端点写成已实现。"""
from uuid import uuid4

from django.test import SimpleTestCase, Client
from jsonschema import Draft202012Validator, ValidationError


class ProblemContractTests(SimpleTestCase):
    """匿名拒绝、CSRF与契约字段对照无需连接数据库。"""

    def test_draft_routes_require_session_before_input_or_database(self):
        """无参数；本人端点在解析和存储前必须已经登录。"""
        identifier = uuid4()
        for method, url in (('get', '/api/v1/problems'), ('post', '/api/v1/problems'),
                            ('get', f'/api/v1/problems/{identifier}'), ('patch', f'/api/v1/problems/{identifier}')):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, data='{}', content_type='application/json') if method != 'get' else self.client.get(url)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()['error']['code'], 'AUTH_REQUIRED')
                self.assertEqual(response['Cache-Control'], 'no-store')

    def test_real_csrf_rejects_writes_without_token(self):
        """无参数；创建和改名保留全局CSRF，而非只在测试客户端成功。"""
        client = Client(enforce_csrf_checks=True)
        for method, url in (('post', '/api/v1/problems'), ('patch', f'/api/v1/problems/{uuid4()}')):
            response = getattr(client, method)(url, data='{}', content_type='application/json')
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()['error']['code'], 'CSRF_FAILED')

    def test_problem_contract_preserves_existing_api_and_tracks_actual_bindings(self):
        """无参数；增加两个路径四操作，旧账号与知识接口逐字段不变。"""
        from config.contracts import build_contract
        from accounts.contracts import build_contract as accounts_contract
        from knowledge.contracts import build_fragment as knowledge_fragment
        from django.urls import resolve
        contract = build_contract()
        for path, methods in {**accounts_contract()['paths'], **knowledge_fragment()[0]}.items():
            self.assertEqual(contract['paths'][path], methods)
        self.assertIn('/api/v1/problems', contract['paths'])
        self.assertEqual(set(contract['paths']['/api/v1/problems']), {'get', 'post'})
        self.assertEqual(set(contract['paths']['/api/v1/problems/{problem_id}']), {'get', 'patch', 'delete'})
        for path, methods in contract['paths'].items():
            if not path.startswith('/api/v1/problems'):
                continue
            view = resolve(path.replace('{problem_id}', str(uuid4()))).func
            self.assertEqual(set(methods), {method.lower() for method in view.allowed_methods})
            for method, operation in methods.items():
                self.assertEqual(operation['security'], [{'SessionCookie': []}])
                if method in ('post', 'patch'):
                    self.assertIn({'$ref': '#/components/parameters/CsrfHeader'}, operation['parameters'])
        parameters = contract['paths']['/api/v1/problems']['post']['parameters']
        self.assertTrue(any(item.get('name') == 'Idempotency-Key' and item.get('required') for item in parameters))
        self.assertIn('/api/v1/problems/{problem_id}/messages', contract['paths'])
        self.assertNotIn('/api/v1/runs', contract['paths'])

    def test_problem_schema_and_revision_conflict_reject_internal_keys(self):
        """无参数；公开快照和冲突只使用已声明白名单。"""
        from config.contracts import build_contract
        contract = build_contract()
        self.assertIn('Problem', contract['components']['schemas'])
        fields = contract['components']['schemas']['Problem']['properties']
        self.assertIn('library_available', fields)
        self.assertNotIn('core_state', fields)
        self.assertNotIn('owner_id', fields)
        schema = {'$ref': '#/components/schemas/ProblemConflictResponse', 'components': contract['components']}
        error = {'error': {'code': 'REVISION_CONFLICT', 'message': '档案已更新，请重载后发送。',
                           'request_id': str(uuid4()), 'current_revision': 2}}
        Draft202012Validator(schema).validate(error)
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate({'error': {**error['error'], 'core_state': {}}})
