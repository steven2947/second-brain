"""固定测试库的真实登录→获准查询→撤权闭环；公开响应对照唯一OpenAPI。"""
from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone
from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb

from config.contracts import build_contract
from tests.knowledge_fixtures import KnowledgeFixtureCase


class LibraryHTTPTests(KnowledgeFixtureCase):
    """不用force_login或替换权限查询，实际认证会话调用只读接口。"""

    def setUp(self):
        """无参数；本测试创建的账号设置测试密码，实际CSRF登录并登记session精确清理。"""
        super().setUp()
        self.contract = build_contract()
        self.session_keys = []
        self.addCleanup(self.cleanup_sessions)
        self.a = self.login_browser(self.user_a)
        self.b = self.login_browser(self.user_b)

    def login_browser(self, user):
        """user为本用例自编账号；密码仅在测试进程与测试库中使用。"""
        password = 'Local-Library-Orchid-672!'
        user.set_password(password)
        user.save(update_fields=['password'])
        browser = Client(enforce_csrf_checks=True)
        token = browser.get('/api/v1/auth/csrf').json()['csrf_token']
        response = browser.post('/api/v1/auth/login', {'email': user.email, 'password': password},
            content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.session_keys.append(browser.cookies[settings.SESSION_COOKIE_NAME].value)
        return browser

    def cleanup_sessions(self):
        """无参数；只删除本用例通过实际登录创建的session，知识记录由父夹具逆序清理。"""
        Session.objects.filter(session_key__in=self.session_keys).delete()

    def assert_public_response(self, response, template):
        """response为真实GET结果，template为规范路径；逐字段验证而非仅检查HTTP200。"""
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.assertEqual(response['Cache-Control'], 'no-store')
        schema = self.contract['paths'][template]['get']['responses']['200']['content']['application/json']['schema']
        Draft202012Validator({**schema, 'components': self.contract['components']}).validate(response.json())
        for field in ('source_path', 'source_sha256', 'context_text', 'proof_storage_key', 'storage_key', '/Users/', 'private/test-review'):
            self.assertNotIn(field, response.content.decode())
        return response.json()

    def test_all_six_successful_endpoints_match_public_contract(self):
        """无参数；真实A会话读取书目、原理方法及受许可控制的证据，B内容不可见。"""
        prefix = f'/api/v1/libraries/{self.release_a}'
        cases = (
            ('/api/v1/libraries', '/api/v1/libraries'),
            (prefix + '/books', '/api/v1/libraries/{release_id}/books'),
            (prefix + '/books/book.product-a.trials', '/api/v1/libraries/{release_id}/books/{book_id}'),
            (prefix + '/cards?q=琥珀试行', '/api/v1/libraries/{release_id}/cards'),
            (prefix + '/cards/knowledge.product-a.reversible-trial', '/api/v1/libraries/{release_id}/cards/{card_id}'),
            (prefix + '/evidence/evidence.product-a.reversible-trial', '/api/v1/libraries/{release_id}/evidence/{evidence_id}'),
        )
        for url, template in cases:
            with self.subTest(template=template):
                data = self.assert_public_response(self.a.get(url), template)
                self.assertNotIn('releaseB', str(data))
        card = self.a.get(prefix + '/cards/knowledge.product-a.reversible-trial').json()
        self.assertEqual(len(card['steps']), 3)
        self.assertEqual(card['explanation'], '')
        self.assertEqual(card['book']['author_display'], '自编测试材料')
        self.assertEqual(card['related'][0]['basis'], 'inference')
        self.assertTrue(card['source_previews'][0]['truncated'])

    def test_cross_owner_unknown_and_quote_denied_are_uniform_404(self):
        """无参数；B会话不能探查A，缺原文许可不影响卡片浏览但拒绝直接证据读取。"""
        prefix = f'/api/v1/libraries/{self.release_a}'
        foreign = self.b.get(prefix + '/books')
        missing = self.a.get(prefix + '/cards/missing')
        for response in (foreign, missing):
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()['error']['code'], 'NOT_FOUND')
            self.assertEqual(response.json()['error']['message'], '资源不存在')
        self.change('knowledge_rightsrecord', self.right_a, allowed_uses=Jsonb(['browse']))
        card = self.a.get(prefix + '/cards/knowledge.product-a.reversible-trial')
        self.assertEqual(card.status_code, 200)
        self.assertEqual(card.json()['source_previews'], [])
        self.assertEqual(self.a.get(prefix + '/evidence/evidence.product-a.reversible-trial').status_code, 404)

    def test_pages_and_filters_are_bound_and_still_require_current_grant(self):
        """无参数；分页不重复，篡改游标与查询变化被拒，到期后旧游标不恢复访问。"""
        url = f'/api/v1/libraries/{self.release_a}/books'
        first = self.a.get(url, {'limit': 1}).json()
        cursor = first['next_cursor']
        self.assertTrue(cursor)
        second = self.a.get(url, {'limit': 1, 'cursor': cursor})
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first['items'][0]['id'], second.json()['items'][0]['id'])
        self.assertIsNone(second.json()['next_cursor'])
        self.assertEqual(self.a.get(url, {'cursor': cursor, 'q': '不存在'}).status_code, 400)
        self.assertEqual(self.a.get(url, {'cursor': cursor + 'x'}).status_code, 400)
        self.assertEqual(self.b.get(url, {'cursor': cursor}).status_code, 404)
        self.change('knowledge_librarygrant', self.grant_a, expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.a.get(url, {'cursor': cursor}).status_code, 404)
        self.assertEqual(self.a.get('/api/v1/libraries').json()['items'], [])

    def test_invalid_inputs_and_write_attempts_cannot_call_repository(self):
        """无参数；真实已登录请求仍不能扩大查询或提交管理写入。"""
        url = f'/api/v1/libraries/{self.release_a}/cards'
        for query in ('owner_id=x', 'limit=101', 'q=a&q=b', 'storage_key=/private/test'):
            self.assertEqual(self.a.get(url + '?' + query).status_code, 400)
        token = self.a.get('/api/v1/auth/csrf').json()['csrf_token']
        response = self.a.post(url, {}, content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response['Allow'], 'GET')
        self.assertEqual(self.a.get(url + '/missing?context=2000').status_code, 400)
