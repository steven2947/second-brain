"""请求内真实投影回归；仅替换_read隔离数据库，不用于证明授权或加载校验。"""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from django.test import SimpleTestCase

from knowledge.repository import KnowledgeRepository


class CountingBooks(list):
    """记录manifest书目实际遍历次数，不替换投影或字典查找。"""
    scans = 0

    def __iter__(self):
        """无参数；保留原列表迭代行为，并统计每次完整扫描入口。"""
        self.scans += 1
        return super().__iter__()


def projection_library(count=3):
    """count为自编卡片数；只构造投影使用的内存记录，不声明为已验收知识版本。"""
    books = CountingBooks([
        {'id': 'book.a', 'title': '自编甲书', 'author': '甲作者', 'private': '不得输出'},
        {'id': 'book.b', 'title': '自编乙书', 'author': None},
    ])
    cards = {f'card.{index:03}': {'id': f'card.{index:03}',
        'book_id': 'book.a' if index % 2 == 0 else 'book.b',
        'author_id': 'author.a' if index % 2 == 0 else 'author.b',
        'kind': 'method', 'title': f'自编方法{index}', 'statement': f'自编主张{index}',
        'evidence_ids': [], 'private': '不得输出'} for index in reversed(range(count))}
    return SimpleNamespace(manifest={'books': books}, cards=cards,
                           version='projection-only-version', edges=[], evidence={})


class KnowledgeProjectionTests(SimpleTestCase):
    """禁止数据库访问；通过实际仓库入口执行投影闭包。"""

    def setUp(self):
        """无参数；固定公开版本ID，仓库user仅是未使用的占位对象。"""
        self.release_id = UUID('00000000-0000-0000-0000-000000000001')
        self.repo = KnowledgeRepository(object())

    def project_read(self, library):
        """library为本次自编内存记录；仅隔离_read的授权、磁盘与事务职责。"""
        def read(release_id, project):
            """release_id来自仓库入口；project仍执行生产代码的真实投影。"""
            return project(library, {'release': {'id': release_id}, 'quotes': {}})
        return patch.object(self.repo, '_read', side_effect=read)

    def test_list_cards_manifest_scans_do_not_grow_with_card_count(self):
        """无参数；卡片从1增至256时，每次请求的投影仍只扫描书目一次。"""
        for count in (1, 64, 256):
            with self.subTest(count=count):
                library = projection_library(count)
                with self.project_read(library):
                    result = self.repo.list_cards(self.release_id)
                self.assertEqual(len(result['items']), count)
                self.assertEqual(library.manifest['books'].scans, 1)

    def test_list_cards_preserves_full_json_and_fresh_nested_books(self):
        """无参数；白名单、顺序、未知作者和每卡独立书目字典保持不变。"""
        library = projection_library()
        with self.project_read(library):
            result = self.repo.list_cards(self.release_id)
        known = {'id': 'book.a', 'title': '自编甲书', 'author_display': '甲作者',
                 'metadata_status': 'verified'}
        unknown = {'id': 'book.b', 'title': '自编乙书', 'author_display': None,
                   'metadata_status': 'partial'}
        self.assertEqual(result, {'release_id': str(self.release_id),
            'content_version': 'projection-only-version', 'items': [
                {'release_id': str(self.release_id), 'card_id': f'card.{index:03}',
                 'book': book, 'type': 'method', 'title': f'自编方法{index}',
                 'statement': f'自编主张{index}'}
                for index, book in enumerate((known, unknown, known))]})
        result['items'][0]['book']['title'] = '调用方改动'
        self.assertEqual(result['items'][2]['book'], known)
        self.assertEqual(library.manifest['books'][0]['title'], '自编甲书')

    def test_same_ids_in_sequential_requests_use_current_manifest(self):
        """无参数；同仓库和相同ID的后续请求使用新书名/作者，过滤亦不复用旧映射。"""
        first, second = projection_library(), projection_library()
        second.manifest['books'][0].update(title='新版甲书', author='新版作者')
        with self.project_read(first):
            original = self.repo.list_cards(self.release_id, author='甲作者')
        with self.project_read(second):
            current = self.repo.list_cards(self.release_id, author='新版作者')
            stale = self.repo.list_cards(self.release_id, author='甲作者')
        self.assertEqual(stale['items'], [])
        self.assertEqual([item['card_id'] for item in current['items']], ['card.000', 'card.002'])
        self.assertEqual(original['items'][0]['book']['author_display'], '甲作者')
        for item in current['items']:
            self.assertEqual(item['book'], {'id': 'book.a', 'title': '新版甲书',
                'author_display': '新版作者', 'metadata_status': 'verified'})

    def test_each_projected_book_still_validates_metadata(self):
        """无参数；第二张卡所属书的非法标题或作者仍由真实book_payload拒绝。"""
        for changes in ({'title': ''}, {'title': {}}, {'author': []}):
            with self.subTest(changes=changes):
                library = projection_library()
                library.manifest['books'][1].update(changes)
                with self.project_read(library), self.assertRaises(ValueError):
                    self.repo.list_cards(self.release_id)

    def test_browse_card_preserves_full_json_with_unknown_authors(self):
        """无参数；详情调用点保留所有字段，缺失/空白/空值作者均为未知。"""
        for author in (None, '', '  ', 'missing'):
            with self.subTest(author=author):
                library = projection_library(1)
                if author == 'missing':
                    library.manifest['books'][0].pop('author')
                else:
                    library.manifest['books'][0]['author'] = author
                with self.project_read(library):
                    result = self.repo.get_card(self.release_id, 'card.000')
                self.assertEqual(result, {'release_id': str(self.release_id), 'card_id': 'card.000',
                    'book': {'id': 'book.a', 'title': '自编甲书', 'author_display': None,
                             'metadata_status': 'partial'},
                    'type': 'method', 'title': '自编方法0', 'statement': '自编主张0',
                    'explanation': '', 'conditions': [], 'boundaries': [], 'steps': [],
                    'application_notes': '', 'source_claim_type': 'unknown', 'related': [],
                    'source_previews': [], 'usage_notice': '整理内容，未针对当前问题采用',
                    'gaps': ['未提供原理说明', '未标明来源主张归属', '当前许可不提供原文预览']})
