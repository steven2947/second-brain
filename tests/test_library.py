"""真实文件读写测试，捕捉证据损坏、发布失败和关系方向错误。"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from src.knowledge.library import validate_library, publish_library, Library


class LibraryTests(unittest.TestCase):
    """以自编示例隔离验证知识存储行为。"""

    def setUp(self):
        """建立临时候选及库目录；不修改项目示例。"""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.candidate = self.root / 'candidate'
        shutil.copytree(Path(__file__).parents[1] / 'examples/sample-library', self.candidate)
        self.library = self.root / 'library'

    def test_invalid_source_or_graph_never_changes_current(self):
        """损坏候选不得替换已可读版本。"""
        first = publish_library(self.candidate, self.library)
        current = (self.library / 'CURRENT').read_text()
        source = self.candidate / 'sources/demo.md'
        source.write_text(source.read_text() + '篡改')
        with self.assertRaises(ValueError):
            publish_library(self.candidate, self.library)
        self.assertEqual((self.library / 'CURRENT').read_text(), current)
        self.assertEqual(Library(self.library).list_books()[0]['id'], 'book.demo')
        self.assertTrue(first['version'])

    def test_dangling_relation_and_path_escape_are_rejected(self):
        """关系与证据越界不能进入书库。"""
        path = self.candidate / 'relations.json'
        graph = json.loads(path.read_text())
        graph['edges'][0]['to'] = 'missing'
        path.write_text(json.dumps(graph))
        with self.assertRaises(ValueError):
            validate_library(self.candidate)
        graph['edges'] = []; path.write_text(json.dumps(graph))
        path = self.candidate / 'evidence/step.json'
        ev = json.loads(path.read_text());ev['source_path'] = '../outside.md'
        path.write_text(json.dumps(ev))
        with self.assertRaises(ValueError):
            validate_library(self.candidate)

    def test_idempotent_publication_and_directional_graph(self):
        """相同知识重复发布复用版本，关系展开保留方向与端点。"""
        one = publish_library(self.candidate, self.library)
        two = publish_library(self.candidate, self.library)
        self.assertEqual(one['version'], two['version'])
        api = Library(self.library)
        forward = api.get_related('knowledge.demo.small-step', direction='out')
        self.assertEqual(forward[0]['target']['id'], 'knowledge.demo.review')
        self.assertEqual(api.get_related('knowledge.demo.review', direction='out'), [])
        self.assertEqual(api.get_related('knowledge.demo.review', direction='in')[0]['target']['id'], 'knowledge.demo.small-step')
        self.assertIn('模糊', api.get_evidence('evidence.demo.step')['text'])
        with self.assertRaisesRegex(ValueError, 'NOT_FOUND'):
            api.get_knowledge('missing')

    def test_empty_library_is_explicit(self):
        """空库不能假装返回已就绪知识。"""
        with self.assertRaisesRegex(ValueError, 'LIBRARY_NOT_READY'):
            Library(self.library)

    def test_invalid_origin_and_unlinked_case_are_rejected(self):
        """来源元数据及案例不能绕过片段校验成为虚假出处。"""
        path = self.candidate / 'evidence/step.json'
        ev = json.loads(path.read_text())
        ev['origin'] = {'source_sha256':'0'*64,'paragraph_id':'wrong','start':99999,'end':1}
        path.write_text(json.dumps(ev))
        with self.assertRaises(ValueError): validate_library(self.candidate)
        del ev['origin'];path.write_text(json.dumps(ev))
        path = next((self.candidate/'cards').glob('*.json'))
        card = json.loads(path.read_text())
        card['source_cases'] = [{'summary':'未被引用支持的案例','paragraph_id':'missing'}]
        path.write_text(json.dumps(card))
        with self.assertRaises(ValueError): validate_library(self.candidate)


if __name__ == '__main__':
    unittest.main()
