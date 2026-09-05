"""验证检索排序、空结果和过滤边界。"""
import unittest
import tempfile
from unittest.mock import Mock
from pathlib import Path
from src.knowledge.library import Library
from src.retrieval.search import SearchEngine, fuse_rankings


class RetrievalTests(unittest.TestCase):
    """关键词基线与结果合并的可独立测试规则。"""

    def test_keyword_search_filters_and_unknown_queries(self):
        """按书籍/作者过滤，不能把无关词硬配成答案。"""
        library = Library(Path(__file__).parents[1] / 'examples/sample-library')
        engine = SearchEngine(library)
        results = engine.search('模糊任务 小步骤', mode='keyword')
        self.assertEqual(results[0]['card']['id'], 'knowledge.demo.small-step')
        self.assertEqual(engine.search('火星推进器铌合金', mode='keyword'), [])
        self.assertEqual(engine.search('小步骤', mode='keyword', book='missing'), [])
        self.assertEqual(engine.search('小步骤', mode='keyword', author='missing'), [])
        with self.assertRaises(ValueError):
            engine.search('', mode='keyword')

    def test_fusion_rewards_agreement_without_duplicate_ids(self):
        """多通道一致命中应优先，重复 ID 不得重复加权。"""
        result = fuse_rankings([['a', 'b', 'a'], ['b', 'c']])
        self.assertEqual(result[0][0], 'b')
        self.assertEqual(len(result), 3)

    def test_corrupt_cache_is_rebuilt_and_hybrid_rejects_noise(self):
        """索引是可重建派生物；关键词噪声不能绕过混合相关性门槛。"""
        library = Library(Path(__file__).parents[1] / 'examples/sample-library')
        with tempfile.TemporaryDirectory() as temporary:
            engine = SearchEngine(library,Path(temporary))
            engine.model = Mock();engine.model.passage_embed.return_value = [[1.,0.],[0.,1.]]
            cache = Path(temporary)/library.version/'vectors.npz'
            cache.parent.mkdir();cache.write_bytes(b'broken cache')
            engine.load_vectors()
            self.assertEqual(engine.vectors.shape,(2,2))
            engine.semantic_scores = lambda query: {key:0.1 for key in engine.ids}
            self.assertEqual(engine.search('模糊任务 小步骤',mode='hybrid'),[])


if __name__ == '__main__':
    unittest.main()
