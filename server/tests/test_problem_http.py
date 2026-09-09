"""问题HTTP的纯输入与公开投影测试；不以这些用例代替真实PG隔离。"""
import importlib
import json
from uuid import uuid4

from django.conf import settings
from django.http import QueryDict
from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone


class ProblemHTTPTests(SimpleTestCase):
    """原问题不裁剪，未知字段与修订类型严格拒绝。"""

    def setUp(self):
        """无参数；先明确检查新增模块存在，避免用导入异常当成功。"""
        self.assertTrue((settings.BASE_DIR / 'problems/serializers.py').exists(), '缺少问题公开边界')
        self.serializers = importlib.import_module('problems.serializers')
        self.http = importlib.import_module('problems.http')
        self.factory = RequestFactory()

    def test_original_question_preserves_whitespace_and_full_chinese_limit(self):
        """无参数；四千中文字符可超过旧账号8KB，但仍符合问题产品限制。"""
        question = '  ' + '思' * 3996 + '\n '
        data = {'question': question, 'goal': 'act', 'release_id': str(uuid4())}
        request = self.factory.post('/api/v1/problems', json.dumps(data, ensure_ascii=False), content_type='application/json')
        parsed = self.http.read_problem_input(request, self.serializers.CreateProblemSerializer)
        self.assertEqual(parsed['question'], question)
        self.assertEqual(parsed['goal'], 'act')

    def test_create_rejects_unknown_fields_and_coerced_text(self):
        """无参数；不能传owner、伪造档案、空白或数值问题。"""
        valid = {'question': '如何验证？', 'goal': 'act', 'release_id': str(uuid4())}
        for change in ({'owner_id': str(uuid4())}, {'core_state': {}}, {'question': 123},
                       {'question': '  \n'}, {'question': '字' * 4001}, {'goal': 'diagnose'}, {'release_id': True}):
            with self.subTest(change=list(change)):
                value = self.serializers.CreateProblemSerializer(data={**valid, **change})
                self.assertFalse(value.is_valid())

    def test_update_requires_strict_revision_and_actual_edit(self):
        """无参数；不把bool/浮点/字符串当修订，不允许直接改问题或删除状态。"""
        for value in ({'expected_revision': 0}, {'expected_revision': True, 'title': '新标题'},
                      {'expected_revision': '0', 'title': '新标题'}, {'expected_revision': 0.0, 'title': '新标题'},
                      {'expected_revision': -1, 'status': 'active'}, {'expected_revision': 0, 'status': 'deleted'},
                      {'expected_revision': 0, 'title': '  '}, {'expected_revision': 0, 'question': '替换原文'}):
            with self.subTest(value=value):
                self.assertFalse(self.serializers.UpdateProblemSerializer(data=value).is_valid())
        self.assertTrue(self.serializers.UpdateProblemSerializer(data={'expected_revision': 0, 'status': 'archived'}).is_valid())

    def test_json_rejects_duplicate_keys_and_oversize(self):
        """无参数；歧义JSON、非JSON和超过256KB的载荷不进入服务。"""
        values = [('{"question":"a","question":"b"}', 'application/json'),
                  ('{}', 'text/plain'), (' ' * (256 * 1024 + 1), 'application/json'),
                  ('{"question":NaN}', 'application/json')]
        for body, content_type in values:
            with self.subTest(length=len(body), content_type=content_type):
                request = self.factory.post('/api/v1/problems', body, content_type=content_type)
                with self.assertRaises(ValueError):
                    self.http.read_problem_input(request, self.serializers.CreateProblemSerializer)

    def test_query_rejects_duplicates_unknown_and_out_of_range(self):
        """无参数；查询仅限本人档案的分页与过滤。"""
        for raw in ('owner_id=x', 'status=deleted', 'q=a&q=b', 'limit=101', 'limit=0', 'q=' + '字' * 501):
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(ValueError):
                    self.http.read_problem_query(QueryDict(raw), self.serializers.ProblemQuerySerializer)
        actual = self.http.read_problem_query(QueryDict('limit=2&status=archived'), self.serializers.ProblemQuerySerializer)
        self.assertEqual((actual['limit'], actual['status'], actual['q']), (2, 'archived', ''))

    def test_projection_omits_private_state_and_preserves_explicit_unavailability(self):
        """无参数；只公开本人原问题与派生澄清，不返回内核档案或伪答案。"""
        sample = {'id': uuid4(), 'title': '自己的问题', 'original_question': '  我需要什么？ ',
            'goal': 'analyze', 'release_id': uuid4(), 'revision': 0, 'status': 'active',
            'clarification': {'rounds': 0, 'limit': 5, 'pending_question': None, 'closed': False},
            'current_answer_id': None, 'library_available': False, 'created_at': timezone.now(),
            'updated_at': timezone.now(), 'core_state': {'secret': 'internal'}, 'owner_id': uuid4()}
        result = dict(self.serializers.ProblemSerializer(sample).data)
        self.assertNotIn('core_state', result)
        self.assertNotIn('owner_id', result)
        self.assertIs(result['library_available'], False)
        self.assertEqual(result['original_question'], sample['original_question'])
        self.assertIsNone(result['current_answer_id'])
