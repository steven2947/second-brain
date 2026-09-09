"""受控单版本加载器边界测试；仅使用自编夹具与临时副本，不连接数据库。"""

import hashlib
import importlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


FIXTURES = Path(__file__).parent / 'fixtures' / 'product_demo'


def fingerprint(path):
    """计算测试声明；path 为自编单版本目录，沿用核心的排序与分隔规则。"""
    digest = hashlib.sha256()
    for file in sorted(path.rglob('*')):
        if file.is_file():
            digest.update(file.relative_to(path).as_posix().encode())
            digest.update(b'\0')
            digest.update(file.read_bytes())
            digest.update(b'\0')
    return digest.hexdigest()


class ReleaseLoaderTests(SimpleTestCase):
    """固定版本、路径边界与真实核心校验的无数据库契约。"""

    def setUp(self):
        """无参数；每例复制自编 A/B 到独立临时受控根。"""
        self.assertIsNotNone(importlib.util.find_spec('knowledge.release_loader'),
                             '缺少受控单 release 加载器')
        self.loader = importlib.import_module('knowledge.release_loader')
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for name in ('releaseA', 'releaseB'):
            shutil.copytree(FIXTURES / name, self.root / name)
        self.path = self.root / 'releaseA'
        self.hash = fingerprint(self.path)

    def load(self, key='releaseA', declared_hash=None, version=None, root=None):
        """调用边界；key 为存储键，声明与 root 未给出时使用自编 A 的默认值。"""
        return self.loader.load_release(key, declared_hash or self.hash,
            version if version is not None else self.hash[:24],
            library_root=root if root is not None else self.root)

    def assert_unavailable(self, **kwargs):
        """核对固定错误；kwargs 传给 load，异常文本不得泄露底层输入。"""
        with self.assertRaises(self.loader.ReleaseUnavailable) as raised:
            self.load(**kwargs)
        self.assertEqual(str(raised.exception), 'RELEASE_UNAVAILABLE')
        self.assertIsNone(raised.exception.__cause__)
        self.assertTrue(raised.exception.__suppress_context__)

    def test_loads_both_fixed_releases_with_core_version(self):
        """无参数；A/B 返回真实旧核心实例及与完整指纹一致的版本。"""
        from src.knowledge.library import Library, content_version
        for name, count in (('releaseA', 2), ('releaseB', 1)):
            with self.subTest(name=name):
                expected = fingerprint(self.root / name)
                loaded = self.load(name, expected, expected[:24])
                self.assertIsInstance(loaded, Library)
                self.assertEqual(loaded.version, content_version(self.root / name))
                self.assertEqual(loaded.version, expected[:24])
                self.assertEqual(len(loaded.list_books()), count)

    def test_uses_configured_root_by_default(self):
        """无参数；未注入 root 时使用 SB_LIBRARY_ROOT。"""
        with override_settings(SB_LIBRARY_ROOT=self.root):
            loaded = self.loader.load_release('releaseA', self.hash, self.hash[:24])
        self.assertEqual(loaded.root, self.path)

    def test_accepts_nested_relative_storage_key(self):
        """无参数；允许根内显式单版本的多段存储键。"""
        (self.root / 'collection').mkdir()
        self.path.rename(self.root / 'collection' / 'releaseA')
        self.assertEqual(self.load(key='collection/releaseA').version, self.hash[:24])

    def test_rejects_uncontrolled_storage_keys(self):
        """无参数；拒绝自由路径、空段、URL、控制符及 CURRENT 入口。"""
        keys = ('', '.', '..', '../releaseA', '/releaseA', str(self.path),
                'releaseA/', 'releaseA//cards', './releaseA', 'releaseA/../releaseB',
                r'releaseA\cards', 'https://host/releaseA', 'file:///releaseA',
                'C:/releaseA', 'releaseA\x00', 'releaseA\n', 'releaseA\x7f',
                'releaseA\u0085', 'CURRENT', 'collection/CURRENT', '%2e%2e/releaseA')
        for key in keys:
            with self.subTest(key=repr(key)):
                self.assert_unavailable(key=key)

    def test_rejects_wrong_or_malformed_declared_fingerprints(self):
        """无参数；完整指纹必须是 64 位小写十六进制并与目录一致。"""
        same_prefix = self.hash[:24] + ('0' if self.hash[24] != '0' else '1') + self.hash[25:]
        for declared in ('a' * 64, same_prefix, self.hash[:63], self.hash.upper(), 'g' * 64):
            with self.subTest(declared=declared):
                self.assert_unavailable(declared_hash=declared, version=declared[:24])

    def test_rejects_wrong_or_malformed_content_version(self):
        """无参数；24 位版本必须是完整指纹的前缀。"""
        for version in ('', 'b' * 24, self.hash[:23], self.hash[:24].upper()):
            with self.subTest(version=version):
                self.assert_unavailable(version=version)

    def test_rejects_changed_file_and_has_no_cache(self):
        """无参数；成功加载后改动文件，下一次仍重新检查全部字节。"""
        self.load()
        (self.path / 'unexpected.txt').write_text('临时变更', encoding='utf-8')
        self.assert_unavailable()

    def test_rejects_missing_release_or_manifest(self):
        """无参数；只接受存在且含固定 manifest 的单版本目录。"""
        self.assert_unavailable(key='missing')
        (self.path / 'manifest.json').unlink()
        self.assert_unavailable()

    def test_rejects_current_pointer_even_with_manifest(self):
        """无参数；存在 CURRENT 时不能让核心自动选择另一版本。"""
        (self.path / 'CURRENT').write_text(self.hash[:24], encoding='utf-8')
        updated = fingerprint(self.path)
        self.assert_unavailable(declared_hash=updated, version=updated[:24])

    def test_rejects_root_and_key_symlinks(self):
        """无参数；根、根的祖先和存储键任一层符号链接均不可使用。"""
        (self.root / 'alias').symlink_to(self.path, target_is_directory=True)
        self.assert_unavailable(key='alias')
        (self.root / 'root-alias').symlink_to(self.root, target_is_directory=True)
        self.assert_unavailable(root=self.root / 'root-alias')
        self.assert_unavailable(key='cards', root=self.root / 'root-alias' / 'releaseA')
        self.assert_unavailable(key='root-alias/releaseA')

    def test_rejects_internal_and_dangling_symlinks(self):
        """无参数；所有内部节点均检查，连未被核心消费的链接也拒绝。"""
        for target in (self.path / 'cards', self.root / 'missing', self.path / 'manifest.json'):
            with self.subTest(target=target.name):
                link = self.path / 'unread-link'
                link.symlink_to(target)
                self.assert_unavailable()
                link.unlink()

    def test_rejects_nonregular_internal_node(self):
        """无参数；忽略不被核心消费的 FIFO 会掩盖不受控节点，必须拒绝。"""
        os.mkfifo(self.path / 'unread-fifo')
        self.assert_unavailable()

    def test_schema_and_anchor_validation_cannot_be_replaced_by_hash(self):
        """无参数；恶意内容重算完整指纹后，仍必须通过真实核心验证。"""
        cases = (('cards/reversible-trial.json', 'kind', 'invalid-schema-value'),
                 ('evidence/reversible-trial.json', 'text', 'PRIVATE_INVALID_ANCHOR'))
        for name, field, value in cases:
            with self.subTest(name=name):
                file = self.path / name
                original = file.read_text(encoding='utf-8')
                record = json.loads(original)
                record[field] = value
                file.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
                changed = fingerprint(self.path)
                self.assert_unavailable(declared_hash=changed, version=changed[:24])
                file.write_text(original, encoding='utf-8')

    def test_json_error_is_sanitized(self):
        """无参数；损坏 JSON 的语法错误和本机路径不得进入边界异常。"""
        (self.path / 'manifest.json').write_text('PRIVATE_BROKEN_JSON', encoding='utf-8')
        changed = fingerprint(self.path)
        self.assert_unavailable(declared_hash=changed, version=changed[:24])

    def test_detects_changes_during_core_loading(self):
        """无参数；以真实核心完成加载后制造变更，验证返回前的二次检查。"""
        from src.knowledge.library import Library

        def load_then_change(path):
            """path 为加载器传入的单版本目录；真实加载后模拟管理员变动。"""
            loaded = Library(path)
            (path / 'added-during-load.txt').write_text('changed', encoding='utf-8')
            return loaded

        with patch.object(self.loader, 'Library', side_effect=load_then_change):
            self.assert_unavailable()

    def test_rechecks_directory_after_core_loading(self):
        """无参数；加载后若目录替换成同内容符号链接，二次路径检查仍拒绝。"""
        from src.knowledge.library import Library

        def load_then_link(path):
            """path 为传入目录；先运行真实核心，再模拟管理员替换目录。"""
            loaded = Library(path)
            replacement = self.root / 'replacement'
            path.rename(replacement)
            path.symlink_to(replacement, target_is_directory=True)
            return loaded

        with patch.object(self.loader, 'Library', side_effect=load_then_link):
            self.assert_unavailable()
