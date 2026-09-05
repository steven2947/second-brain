"""装配器检查书籍命名空间、输入路径和来源指纹。"""
import json
import tempfile
import unittest
from pathlib import Path
from src.distillation.normalize import normalize_markdown
from src.distillation.assemble import assemble_library


class AssembleTests(unittest.TestCase):
    """使用全新测试书，防止纳瓦尔专用逻辑渗入公共流程。"""

    def test_generic_book_and_invalid_slug(self):
        """任意书应有独立 ID，恶意 slug 不能写到候选目录之外。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); text = '# 正文\n\n先观察事实。'
            (root/'source.md').write_text(text)
            doc = normalize_markdown(text,[{'start_heading':'正文','end_heading':None}])
            doc['book'] = {'book_id':'book.test','title':'测试书','author_id':'author.test','author':'自编'}
            (root/'document.json').write_text(json.dumps(doc))
            card = {'slug':'observe','title':'观察事实','kind':'claim','statement':'先观察事实。','conditions':[],
                    'boundaries':[],'evidence_paragraph_ids':[doc['paragraphs'][0]['id']]}
            output = {'sections_reviewed':[doc['sections'][0]['id']],'cards':[card],'relations':[]}
            (root/'output.json').write_text(json.dumps(output))
            assemble_library(root/'document.json',[root/'output.json'],root/'candidate')
            result = json.loads((root/'candidate/cards/observe.json').read_text())
            self.assertEqual(result['id'],'knowledge.test.observe')
            card['slug']='../../escaped'
            (root/'output.json').write_text(json.dumps(output))
            with self.assertRaises(ValueError):
                assemble_library(root/'document.json',[root/'output.json'],root/'bad')
            self.assertFalse((root/'escaped.json').exists())


if __name__ == '__main__':
    unittest.main()
