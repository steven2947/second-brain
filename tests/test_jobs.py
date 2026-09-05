"""蒸馏任务缓存及结果装配的行为测试。"""
import json
import tempfile
import unittest
from pathlib import Path
from src.distillation.jobs import prepare_job


class JobTests(unittest.TestCase):
    """来源或提示词变化需要新任务，重跑不能覆盖原任务产物。"""

    def test_fingerprint_reuse_and_prompt_invalidation(self):
        """同指纹复用，提示词更新后另建任务且保留旧产物。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'source.md'; source.write_text('# 正文\n\n测试内容。')
            prompts = root/'prompts'; prompts.mkdir(); (prompts/'a.md').write_text('提取原文')
            scope = {'book_id': 'book.test', 'included_ranges': [{'start_heading': '正文', 'end_heading': None}]}
            first = prepare_job(source, scope, root/'jobs', prompts)
            marker = Path(first['path'])/'agent-result.json';marker.write_text('{}')
            second = prepare_job(source, scope, root/'jobs', prompts)
            self.assertTrue(second['reused']); self.assertTrue(marker.exists())
            (prompts/'a.md').write_text('提取原文并检查边界')
            third = prepare_job(source, scope, root/'jobs', prompts)
            self.assertNotEqual(first['job_id'], third['job_id'])
            self.assertTrue(marker.exists())


if __name__ == '__main__':
    unittest.main()
