"""产品答案接缝：真实自编库与原v3校验器，模型提案不冒充真实效果测试。"""
import copy
import unittest

from src.knowledge.library import Library
from tests.test_adopted_claims import valid_v3_draft
from tests.test_orchestration_validation import ROOT, call_request


class ProductCoreAdapterTests(unittest.TestCase):
    """无数据库或网络；验证服务端生成、采用边界、公开投影和取消。"""

    def setUp(self):
        """无参数；每例读取原有自编库，不写原书或固定样例。"""
        from server.ai import core_adapter
        from server.ai.ports import Generation, ModelFailure
        self.adapter, self.Generation, self.Failure = core_adapter, Generation, ModelFailure
        self.library = Library(ROOT / 'examples/sample-library')
        self.calls = []

    def provider(self, mutate=None):
        """mutate可修改自编提案；核心检索和正式校验均不替换。"""
        outer = self
        class ScriptedProvider:
            def generate(self, request):
                """request含脱敏候选；产生结构化测试提案，不用于产品运行。"""
                outer.calls.append(request)
                draft = valid_v3_draft(request.context['session'])
                if mutate:
                    mutate(draft, len(outer.calls))
                return outer.Generation(content=draft, provider='test', model='scripted',
                                        input_tokens=31, output_tokens=52)
        return ScriptedProvider()

    def test_real_v3_assembly_preserves_rich_sections_and_accounts_calls(self):
        """无参数；实际会话→采用校验→原理/圆桌/行动/续聊全部保留。"""
        metrics, stages = [], []
        result = self.adapter.analyze_with_library(self.library, call_request(), self.provider(),
            record_call=metrics.append, stage=stages.append)
        self.assertEqual(result['packet']['schema_version'], 3)
        self.assertTrue(result['packet']['witness_cards'])
        for key in ('roundtable', 'knowledge_groups', 'actions', 'next_chat_action'):
            self.assertEqual(result['packet'][key], result['draft'][key])
        self.assertEqual(metrics[0]['input_tokens'], 31)
        self.assertEqual(stages, ['retrieving', 'evaluating', 'validating'])
        self.assertEqual(self.calls[0].max_output_tokens, 16000)
        for candidate in self.calls[0].context['session']['candidates']:
            self.assertNotIn('source_path', candidate['evidence'][0])
            self.assertNotIn('origin', candidate['evidence'][0])
        self.assertIn('source_path', result['session']['candidates'][0]['evidence'][0])

    def test_invalid_evidence_is_repaired_once_not_silently_adopted(self):
        """无参数；第一次外卡证据被拒绝，第二次才生成正式包。"""
        def mutate(draft, attempt):
            """draft为测试提案；只污染第一次证据归属。"""
            if attempt == 1:
                draft['decisions'][0]['adoption']['evidence_ids'] = ['evidence.not-in-library']
        result = self.adapter.analyze_with_library(self.library, call_request(), self.provider(mutate))
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn('evidence.not-in-library', str(result['packet']))
        self.assertEqual(self.calls[1].purpose, 'analysis_repair')

    def test_repeated_invalid_proposal_stops_after_two_calls(self):
        """无参数；不以无限修复掩盖无效模型输出，也不绕过校验。"""
        def mutate(draft, attempt):
            """两个测试提案均故意伪造来源归属。"""
            draft['decisions'][0]['adoption']['evidence_ids'] = ['evidence.invalid']
        with self.assertRaises(self.Failure) as caught:
            self.adapter.analyze_with_library(self.library, call_request(), self.provider(mutate))
        self.assertEqual(caught.exception.code, 'MODEL_OUTPUT_INVALID')
        self.assertEqual(len(self.calls), 2)

    def test_cancelled_never_calls_provider(self):
        """无参数；取消先于检索和付费调用。"""
        with self.assertRaises(self.Failure) as caught:
            self.adapter.analyze_with_library(self.library, call_request(), self.provider(), cancelled=lambda: True)
        self.assertEqual(caught.exception.code, 'RUN_CANCELLED')
        self.assertEqual(self.calls, [])

    def test_public_projection_has_authors_and_enforces_current_quote_limits(self):
        """无参数；仅许可短引可公开，分析字段不回退为原卡，私有会话不暴露。"""
        result = self.adapter.analyze_with_library(self.library, call_request(), self.provider())
        original = copy.deepcopy(result['packet'])
        public = self.adapter.public_answer(result['packet'], quote_limits={'book.demo': 8})
        self.assertTrue(public['books'][0]['author_display'])
        self.assertTrue(all(len(item['excerpt']) <= 8 for item in public['sources']))
        self.assertNotIn('session_id', public)
        for witness in public['witness_cards']:
            self.assertNotIn('original_card_ref', witness)
            self.assertNotIn('claim', witness)
            self.assertTrue(witness['mechanism'])
        denied = self.adapter.public_answer(result['packet'], quote_limits={})
        self.assertTrue(all(item['excerpt'] is None for item in denied['sources']))
        self.assertEqual(result['packet'], original)

    def test_no_candidates_keeps_coverage_gap_without_fake_books(self):
        """无参数；零检索结果不是正式v3答案，不调用模型伪造书籍采用来填空。"""
        request = {**call_request(), 'question': 'zxqv991072', 'query_expansions': []}
        result = self.adapter.analyze_with_library(self.library, request, self.provider())
        self.assertEqual(result['session']['candidates'], [])
        self.assertEqual(result['outcome'], 'coverage_gap')
        self.assertIsNone(result['packet'])
        self.assertIsNone(result['draft'])
        self.assertEqual(self.calls, [])

    def test_unconfigured_provider_does_not_retry_or_fallback(self):
        """无参数；未配置不是可修复草稿错误，不以测试提案替代真实模型。"""
        from server.ai.ports import DisabledProvider
        metrics = []
        with self.assertRaises(self.Failure) as caught:
            self.adapter.analyze_with_library(self.library, call_request(), DisabledProvider(), record_call=metrics.append)
        self.assertEqual(caught.exception.code, 'MODEL_UNAVAILABLE')
        self.assertEqual(len(metrics), 1)
        self.assertIsNone(metrics[0]['input_tokens'])
