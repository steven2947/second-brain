"""知识读取HTTP接缝的无数据库测试；真正授权内容另由PG集成验证。"""
import importlib
import importlib.util
from uuid import uuid4

from django.http import QueryDict
from django.test import SimpleTestCase


class KnowledgeHTTPTests(SimpleTestCase):
    """检查真实匿名拒绝、严格查询参数和有上下文签名的分页。"""

    def setUp(self):
        """无参数；缺少新接口时给出明确失败，不把导入错误当通过。"""
        self.assertIsNotNone(importlib.util.find_spec('knowledge.http'), '缺少知识HTTP边界')
        self.http = importlib.import_module('knowledge.http')
        self.serializers = importlib.import_module('knowledge.serializers')

    def test_all_read_routes_require_session_before_loading(self):
        """无参数；无cookie匿名请求不能访问数据库或暴露书名。"""
        release = str(uuid4())
        for path in ('/libraries', f'/libraries/{release}/books', f'/libraries/{release}/books/book.test',
                     f'/libraries/{release}/cards', f'/libraries/{release}/cards/card.test',
                     f'/libraries/{release}/evidence/evidence.test'):
            with self.subTest(path=path):
                response = self.client.get('/api/v1' + path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()['error']['code'], 'AUTH_REQUIRED')
                self.assertEqual(response['Cache-Control'], 'no-store')

    def test_query_rejects_unknown_duplicate_and_out_of_range_fields(self):
        """无参数；查询参数不接受owner、存储键、重复值或越界输入。"""
        for raw in ('owner_id=x', 'storage_key=x', 'q=a&q=b', 'limit=0', 'limit=101', 'q=' + '字' * 501):
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(ValueError):
                    self.http.read_query(QueryDict(raw), self.serializers.CardQuerySerializer)
        parsed = self.http.read_query(QueryDict('q=可逆&limit=2&type=method'), self.serializers.CardQuerySerializer)
        self.assertEqual((parsed['q'], parsed['limit'], parsed['type']), ('可逆', 2, 'method'))

    def test_cursor_is_signed_and_bound_to_owner_release_query_and_content(self):
        """无参数；两页真实数据无重复，篡改与跨身份/版本/查询复用被拒绝。"""
        rows = [{'id': str(index)} for index in range(5)]
        first = self.http.paginate(rows, limit=2, cursor='', scope='owner-a/release-a/v1/query-a')
        self.assertEqual(first['items'], rows[:2])
        second = self.http.paginate(rows, limit=2, cursor=first['next_cursor'], scope='owner-a/release-a/v1/query-a')
        self.assertEqual(second['items'], rows[2:4])
        for cursor, scope in ((first['next_cursor'] + 'x', 'owner-a/release-a/v1/query-a'),
                              (first['next_cursor'], 'owner-b/release-a/v1/query-a'),
                              (first['next_cursor'], 'owner-a/release-b/v1/query-a'),
                              (first['next_cursor'], 'owner-a/release-a/v2/query-a'),
                              (first['next_cursor'], 'owner-a/release-a/v1/query-b')):
            with self.subTest(scope=scope):
                with self.assertRaises(ValueError):
                    self.http.paginate(rows, limit=2, cursor=cursor, scope=scope)
        changed = rows + [{'id': 'new'}]
        with self.assertRaises(ValueError):
            self.http.paginate(changed, limit=2, cursor=first['next_cursor'], scope='owner-a/release-a/v1/query-a')

    def test_detail_serialization_preserves_methods_and_drops_internal_keys(self):
        """无参数；公开字段取白名单，原理和步骤不因投影丢失。"""
        book = {'id': 'b', 'title': '自编书', 'author_display': None, 'metadata_status': 'partial', 'file': '/private/example'}
        payload = {'release_id': str(uuid4()), 'card_id': 'c', 'book': book, 'type': 'method',
                   'title': '方法', 'statement': '主张', 'explanation': '原理' * 200, 'conditions': [],
                   'boundaries': [], 'steps': ['步骤一', '步骤二'], 'application_notes': '',
                   'source_claim_type': 'unknown', 'related': [], 'source_previews': [],
                   'usage_notice': '整理内容，未针对当前问题采用', 'gaps': ['作者未录入'], 'file': '/private/example'}
        public = dict(self.serializers.BrowseCardSerializer(payload).data)
        self.assertEqual(public['explanation'], payload['explanation'])
        self.assertEqual(public['steps'], payload['steps'])
        self.assertNotIn('file', public)
        self.assertNotIn('file', public['book'])
        self.assertIsNone(public['book']['author_display'])
