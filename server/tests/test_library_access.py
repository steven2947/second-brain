"""公开仓库接缝的真实PostgreSQL授权、投影和竞争验证。"""
import json
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.db import connection
from django.utils import timezone
from psycopg.types.json import Jsonb

from tests.knowledge_fixtures import FIXTURES, KnowledgeFixtureCase
from access.context import owner_transaction
from knowledge.models import LibraryRelease
from knowledge.repository import KnowledgeError, KnowledgeRepository
from knowledge.release_loader import load_release


class LibraryAccessTests(KnowledgeFixtureCase):
    """通过可信用户仓库访问真实自编固定版本；不替换任何授权ORM。"""

    def assert_denied(self, action, code='NOT_FOUND', status=404):
        """action为公开仓库调用；code/status是固定公开错误契约。"""
        with self.assertRaises(KnowledgeError) as caught:
            action()
        self.assertEqual((caught.exception.code, caught.exception.status), (code, status))
        self.assertEqual(caught.exception.message, '资源不存在' if status == 404 else '知识版本暂不可用')

    def temporary_release(self, mutate):
        """mutate仅修改临时目录中的自编副本；原fixture和原书不变，自动清理临时目录。"""
        temporary = tempfile.TemporaryDirectory(prefix='sb-knowledge-test-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        directory = root / 'variant'
        shutil.copytree(FIXTURES / 'releaseA', directory)
        mutate(directory)
        release = self.seed_release('variant', directory=directory)
        self.seed_grant(self.owner_a, release)
        right = self.seed_rights(release)
        override = self.settings(SB_LIBRARY_ROOT=root)
        override.enable()
        self.addCleanup(override.disable)
        return release, directory, right

    def test_books_are_authorized_and_materialized_on_same_connection(self):
        """无参数；A/B/C与空上下文不串用户，未经授权不加载任何目录。"""
        physical = connection.connection
        result = KnowledgeRepository(self.user_a).list_books(self.release_a)
        self.assertEqual({book['id'] for book in result['items']},
                         {'book.product-a.trials', 'book.product-a.boundaries'})
        self.assertEqual(result['items'][0]['author_display'], '自编测试材料')
        self.assertNotIn('旧投影', str(result))
        self.assertEqual(len(KnowledgeRepository(self.user_b).list_books(self.release_b)['items']), 1)
        with patch('knowledge.repository.load_release') as loader:
            for user, release in ((self.user_a, self.release_b), (self.user_b, self.release_a),
                                  (self.user_c, self.release_a)):
                with self.assertRaises(KnowledgeError) as caught:
                    KnowledgeRepository(user).list_books(release)
                self.assertEqual((caught.exception.code, caught.exception.status), ('NOT_FOUND', 404))
            loader.assert_not_called()
        with connection.cursor() as cursor:
            cursor.execute('SELECT count(*) FROM knowledge_librarygrant')
            self.assertEqual(cursor.fetchone(), (0,))
        self.assertIs(connection.connection, physical)

    def test_browse_details_preserve_method_and_controlled_sources(self):
        """无参数；原理缺口、完整步骤、推断关系和原文连续短引均为独立字段。"""
        repo = KnowledgeRepository(self.user_a)
        card = repo.get_card(self.release_a, 'knowledge.product-a.reversible-trial')
        self.assertEqual(card['steps'], ['写明要验证的疑问和损失上限',
            '保留原有材料后执行短时试行', '比较结果，决定继续还是撤回'])
        self.assertEqual(card['explanation'], '')
        self.assertEqual(card['source_claim_type'], 'unknown')
        self.assertIn('未提供原理说明', card['gaps'])
        self.assertEqual(card['usage_notice'], '整理内容，未针对当前问题采用')
        self.assertEqual(card['related'][0]['basis'], 'inference')
        self.assertTrue(card['related'][0]['rationale'].startswith('系统推断：'))
        self.assertEqual(set(card['related'][0]), {'id', 'from', 'to', 'type', 'basis', 'rationale'})
        preview = card['source_previews'][0]
        self.assertEqual(preview, repo.get_evidence(self.release_a, 'evidence.product-a.reversible-trial'))
        self.assertEqual(preview['text'], '当任务迟迟没有开始，且试行能够撤回、损失可以事先封顶时，可先')
        self.assertTrue(preview['truncated'])
        self.assertEqual(preview['location']['start'], 37)
        self.assertEqual(preview['location']['end'], 67)
        self.assertEqual(preview['location']['kind'], 'evidence_compilation')
        for secret in ('source_path', 'source_sha256', 'context_text', 'proof_storage_key', 'private/test-review'):
            self.assertNotIn(secret, str(card))
        book = repo.get_book(self.release_a, 'book.product-a.trials')
        self.assertEqual(book['chapters'], ['正文'])
        self.assertIn('章节仅来自已有证据，不代表全书目录', book['gaps'])

    def test_release_enumeration_and_keyword_search_are_scoped(self):
        """无参数；仅列本人可浏览版本，BM25确实命中、空匹配、书/作者/类型过滤。"""
        repo = KnowledgeRepository(self.user_a)
        releases = repo.list_releases()['items']
        self.assertEqual([item['id'] for item in releases], [str(self.release_a)])
        self.assertEqual(set(releases[0]), {'id', 'library_id', 'title', 'description',
            'content_version', 'book_count', 'card_count'})
        self.assertEqual(KnowledgeRepository(self.user_c).list_releases(), {'items': []})
        result = repo.list_cards(self.release_a, q='封顶')
        self.assertEqual([card['card_id'] for card in result['items']], ['knowledge.product-a.reversible-trial'])
        self.assertEqual(repo.list_cards(self.release_a, q='量子纠缠')['items'], [])
        self.assertEqual(repo.list_cards(self.release_a, book='book.product-b.labels')['items'], [])
        cards = repo.list_cards(self.release_a, author='author.product-a.trial-writer', card_type='method')['items']
        self.assertEqual(len(cards), 1)
        self.assertEqual(set(cards[0]), {'release_id', 'card_id', 'book', 'type', 'title', 'statement'})
        self.assertEqual(len(repo.list_cards(self.release_a, author='自编测试材料')['items']), 2)
        self.assertEqual(repo.list_cards(self.release_a, card_type='not-a-type')['items'], [])

    def test_no_knowledge_read_inside_an_outer_transaction(self):
        """无参数；即使同owner外层上下文存在，仓库也不能在长事务中打开文件。"""
        with owner_transaction(self.owner_a):
            with patch('knowledge.repository.load_release') as loader:
                self.assert_denied(lambda: KnowledgeRepository(self.user_a).list_books(self.release_a),
                                   'RELEASE_UNAVAILABLE', 503)
                loader.assert_not_called()

    def test_expired_revoked_and_inactive_versions_never_load(self):
        """无参数；到期、撤销、停用、未发布、知识集暂停与缺审查键均在加载前拒绝。"""
        collection = LibraryRelease.objects.get(pk=self.release_a).library_id
        cases = [
            ('knowledge_librarygrant', self.grant_a, {'expires_at': timezone.now() - timedelta(seconds=1)}, {'expires_at': None}),
            ('knowledge_librarygrant', self.grant_a, {'status': 'revoked', 'revoked_at': timezone.now()}, {'status': 'active', 'revoked_at': None}),
            ('accounts_user', self.owner_a, {'status': 'disabled'}, {'status': 'active'}),
            ('knowledge_libraryrelease', self.release_a, {'status': 'validated'}, {'status': 'published'}),
            ('knowledge_librarycollection', collection, {'status': 'suspended'}, {'status': 'active'}),
            ('knowledge_libraryrelease', self.release_a, {'rights_record_key': ''}, {'rights_record_key': 'private/test-review'}),
        ]
        for table, identifier, changes, restore in cases:
            with self.subTest(table=table, fields=list(changes)):
                self.change(table, identifier, **changes)
                with patch('knowledge.repository.load_release') as loader:
                    self.assert_denied(lambda: KnowledgeRepository(self.user_a).list_books(self.release_a))
                    loader.assert_not_called()
                self.change(table, identifier, **restore)
                self.user_a.refresh_from_db()

    def test_invalid_manifest_metadata_cannot_hide_in_empty_search(self):
        """无参数；manifest元数据类型异常时，即使没有搜索结果也不能绕过公开投影校验。"""
        def corrupt_manifest(directory):
            """directory为临时自编副本；仅把书名改为错误类型以验证核心适配边界。"""
            path = directory / 'manifest.json'
            manifest = json.loads(path.read_text())
            manifest['books'][0]['title'] = {'private': 'not-a-title'}
            path.write_text(json.dumps(manifest), encoding='utf-8')
        release, _, _ = self.temporary_release(corrupt_manifest)
        self.assert_denied(lambda: KnowledgeRepository(self.user_a).list_cards(release, q='量子纠缠'),
                           'RELEASE_UNAVAILABLE', 503)

    def test_original_location_and_full_reasoning_are_preserved(self):
        """无参数；有origin时用原书字符坐标，完整原理/应用说明不受quote字符额度影响。"""
        reasoning = '这是完整自编原理说明。' * 300
        notes = '具体应用仍需检查条件。' * 300
        def add_origin(directory):
            """directory为临时副本；添加合法自编原书定位与长原理供公开接口验证。"""
            evidence_path = directory / 'evidence/reversible-trial.json'
            evidence = json.loads(evidence_path.read_text())
            old_id = evidence['id']
            paragraph = 'paragraph.' + evidence['source_sha256'][:12] + '.1'
            evidence['id'] = 'evidence.' + paragraph
            evidence['origin'] = {'source_sha256': evidence['source_sha256'],
                'paragraph_id': paragraph, 'start': 500, 'end': 613}
            evidence_path.write_text(json.dumps(evidence), encoding='utf-8')
            manifest_path = directory / 'manifest.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['books'][0].update(source_sha256=evidence['source_sha256'], source_chars=1000)
            manifest['books'][0].pop('author')
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            card_path = directory / 'cards/reversible-trial.json'
            card = json.loads(card_path.read_text())
            card.update(reasoning=reasoning, application_notes=notes, source_claim_type='quoted_other',
                        evidence_ids=[evidence['id']])
            card_path.write_text(json.dumps(card), encoding='utf-8')
            relation_path = directory / 'relations.json'
            graph = json.loads(relation_path.read_text())
            graph['edges'][0]['evidence_ids'] = [evidence['id'] if key == old_id else key
                                                for key in graph['edges'][0]['evidence_ids']]
            relation_path.write_text(json.dumps(graph), encoding='utf-8')
        release, _, _ = self.temporary_release(add_origin)
        card = KnowledgeRepository(self.user_a).get_card(release, 'knowledge.product-a.reversible-trial')
        self.assertEqual(card['explanation'], reasoning)
        self.assertEqual(card['application_notes'], notes)
        self.assertEqual(card['source_claim_type'], 'quoted_other')
        self.assertIsNone(card['book']['author_display'])
        self.assertEqual(card['book']['metadata_status'], 'partial')
        self.assertNotIn('未提供原理说明', card['gaps'])
        self.assertEqual(card['source_previews'][0]['location'], {
            'kind': 'original', 'start': 500, 'end': 530,
            'paragraph_id': 'paragraph.2151e20397c8.1', 'notice': '原书字符位置，非页码'})

    def test_source_mutation_and_registered_counts_fail_closed(self):
        """无参数；源字节与登记统计不一致统一503，不回显文件或底层校验细节。"""
        release, directory, _ = self.temporary_release(lambda directory: None)
        source = directory / 'sources/reversible-trial.md'
        original = source.read_bytes()
        source.write_bytes(original + b'changed')
        self.assert_denied(lambda: KnowledgeRepository(self.user_a).list_books(release), 'RELEASE_UNAVAILABLE', 503)
        source.write_bytes(original)
        self.change('knowledge_libraryrelease', release, card_count=9)
        self.assert_denied(lambda: KnowledgeRepository(self.user_a).list_books(release), 'RELEASE_UNAVAILABLE', 503)

    def test_repeated_core_card_id_is_not_a_cross_release_lookup(self):
        """无参数；新自编版本复用旧cardID但改变statement，仓库仍按release加载及授权。"""
        def change_card(directory):
            """directory为临时副本；新版本保留核心ID并改写自编内容。"""
            path = directory / 'cards/reversible-trial.json'
            card = json.loads(path.read_text())
            card['statement'] = '另一版本的独立自编内容。'
            path.write_text(json.dumps(card), encoding='utf-8')
        release, _, _ = self.temporary_release(change_card)
        repo = KnowledgeRepository(self.user_a)
        card = repo.get_card(release, 'knowledge.product-a.reversible-trial')
        self.assertEqual(card['statement'], '另一版本的独立自编内容。')
        self.assertEqual(card['release_id'], str(release))
        with self.settings(SB_LIBRARY_ROOT=FIXTURES):
            original = repo.get_card(self.release_a, 'knowledge.product-a.reversible-trial')
        self.assertNotEqual(original['statement'], card['statement'])
        self.assert_denied(lambda: KnowledgeRepository(self.user_b).get_card(release, card['card_id']))

    def test_missing_ids_and_cross_release_evidence_are_indistinguishable(self):
        """无参数；合法release内未知资源及另一release资源统一404，没有任意路径读取。"""
        repo = KnowledgeRepository(self.user_a)
        for action in (lambda: repo.get_book(self.release_a, 'book.product-b.labels'),
                       lambda: repo.get_card(self.release_a, 'knowledge.product-b.shelf-label'),
                       lambda: repo.get_evidence(self.release_a, 'evidence.product-b.shelf-label'),
                       lambda: repo.get_evidence(self.release_a, '../private/proof'),
                       lambda: repo.list_books('not-a-uuid')):
            self.assert_denied(action)

    def test_invalid_rights_are_not_browse_permission(self):
        """无参数；每种无效审批、用途、受众、范围均不可授权整版本文件加载。"""
        cases = [({'status': 'unreviewed', 'reviewer_id': None, 'reviewed_at': None},
                  {'status': 'approved', 'reviewer_id': self.owner_a, 'reviewed_at': timezone.now()}),
            ({'valid_until': timezone.now() - timedelta(seconds=1)}, {'valid_until': None}),
            ({'source_description': '  '}, {'source_description': '自编测试'}),
            ({'basis_type': 'license', 'proof_storage_key': None}, {'basis_type': 'self_authored'}),
            ({'basis_type': 'permission', 'proof_storage_key': ' '}, {'basis_type': 'self_authored', 'proof_storage_key': None}),
            ({'basis_type': 'other', 'proof_storage_key': None}, {'basis_type': 'self_authored'}),
            ({'allowed_audience': 'public'}, {'allowed_audience': 'granted_users'}),
            ({'allowed_uses': Jsonb(['browse', 'unknown'])}, {'allowed_uses': Jsonb(['browse', 'quote'])}),
            ({'allowed_uses': Jsonb('browse')}, {'allowed_uses': Jsonb(['browse', 'quote'])}),
            ({'scope_book_ids': Jsonb(['book.product-a.trials'])}, {'scope_book_ids': Jsonb([])}),
            ({'scope_book_ids': Jsonb(['book.product-a.trials', 'book.product-a.trials'])}, {'scope_book_ids': Jsonb([])}),
            ({'scope_book_ids': Jsonb(['unknown'])}, {'scope_book_ids': Jsonb([])}),
            ({'scope_book_ids': Jsonb([{}])}, {'scope_book_ids': Jsonb([])}),
            ({'scope_book_ids': Jsonb([''])}, {'scope_book_ids': Jsonb([])}),
        ]
        for changes, restore in cases:
            with self.subTest(fields=changes):
                self.change('knowledge_rightsrecord', self.right_a, **changes)
                with patch('knowledge.repository.load_release') as loader:
                    self.assert_denied(lambda: KnowledgeRepository(self.user_a).list_books(self.release_a))
                    self.assertEqual(KnowledgeRepository(self.user_a).list_releases(), {'items': []})
                    loader.assert_not_called()
                self.change('knowledge_rightsrecord', self.right_a, **restore)

    def test_split_scope_must_cover_every_book_before_loading(self):
        """无参数；两条明确scope组成完整browse覆盖，可短引仅属相应获准书。"""
        self.change('knowledge_rightsrecord', self.right_a,
                    scope_book_ids=Jsonb(['book.product-a.trials']))
        self.seed_rights(self.release_a, scope_book_ids=Jsonb(['book.product-a.boundaries']),
                         allowed_uses=Jsonb(['browse']))
        repo = KnowledgeRepository(self.user_a)
        self.assertEqual(len(repo.list_books(self.release_a)['items']), 2)
        card = repo.get_card(self.release_a, 'knowledge.product-a.stop-irreversible')
        self.assertEqual(card['source_previews'], [])
        self.assert_denied(lambda: repo.get_evidence(self.release_a, 'evidence.product-a.stop-irreversible'))

    def test_quote_policy_is_strict_and_smallest_applicable_limit_wins(self):
        """无参数；非法quote只禁原文；browse继续，多个有效短引策略逐书取最小值。"""
        repo = KnowledgeRepository(self.user_a)
        for policy in ({}, {'max_chars': True}, {'max_chars': 0}, {'max_chars': 2001},
                       {'max_chars': '30'}, {'max_chars': 30, 'extra': 1}, []):
            with self.subTest(policy=policy):
                self.change('knowledge_rightsrecord', self.right_a, quote_policy=Jsonb(policy))
                self.assertEqual(repo.get_card(self.release_a, 'knowledge.product-a.reversible-trial')['source_previews'], [])
                self.assert_denied(lambda: repo.get_evidence(self.release_a, 'evidence.product-a.reversible-trial'))
        self.change('knowledge_rightsrecord', self.right_a, quote_policy=Jsonb({'max_chars': 2000}))
        full = repo.get_evidence(self.release_a, 'evidence.product-a.reversible-trial')
        self.assertFalse(full['truncated'])
        self.assertEqual(len(full['text']), 113)
        self.seed_rights(self.release_a, allowed_uses=Jsonb(['quote']), quote_policy=Jsonb({'max_chars': 1}))
        short = repo.get_evidence(self.release_a, 'evidence.product-a.reversible-trial')
        self.assertEqual(short['text'], '当')
        self.assertEqual(short['location']['end'], 38)

    def test_final_recheck_discards_revoked_or_changed_permissions(self):
        """无参数；实际加载之后用独立管理连接改状态，不依赖updated_at变化。"""
        cases = [
            ('knowledge_librarygrant', self.grant_a, {'expires_at': timezone.now() - timedelta(seconds=1)}, {'expires_at': None}),
            ('knowledge_librarygrant', self.grant_a, {'status': 'revoked', 'revoked_at': timezone.now()}, {'status': 'active', 'revoked_at': None}),
            ('accounts_user', self.owner_a, {'access_revision': 1}, {'access_revision': 0}),
            ('accounts_user', self.owner_a, {'auth_epoch': 1}, {'auth_epoch': 0}),
            ('knowledge_rightsrecord', self.right_a, {'quote_policy': Jsonb({'max_chars': 1})}, {'quote_policy': Jsonb({'max_chars': 30})}),
            ('knowledge_rightsrecord', self.right_a, {'valid_until': timezone.now() - timedelta(seconds=1)}, {'valid_until': None}),
            ('knowledge_libraryrelease', self.release_a, {'storage_key': 'releaseB'}, {'storage_key': 'releaseA'}),
        ]
        for table, identifier, changes, restore in cases:
            with self.subTest(table=table, fields=list(changes)):
                def change_after_load(*args):
                    """args是已授权固定版本加载参数；真实读取后模拟并发管理变更。"""
                    self.assertFalse(connection.in_atomic_block)
                    library = load_release(*args)
                    self.change(table, identifier, **changes)
                    return library
                with patch('knowledge.repository.load_release', side_effect=change_after_load):
                    self.assert_denied(lambda: KnowledgeRepository(self.user_a).get_card(
                        self.release_a, 'knowledge.product-a.reversible-trial'))
                self.change(table, identifier, **restore)
                self.user_a.refresh_from_db()
