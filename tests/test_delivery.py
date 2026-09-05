"""交付白名单测试，防止本机数据与原书混入安装包。"""
import tempfile
import unittest
import zipfile
from pathlib import Path
from src.interfaces.delivery import build_release


class DeliveryTests(unittest.TestCase):
    """使用真实项目构建，验证用户库由显式参数选择。"""

    def test_release_excludes_private_inputs_and_includes_runtime(self):
        """默认示例包必须包含运行代码，且没有原书、配置、模型缓存或 Git。"""
        project = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as directory:
            result = build_release(project,Path(directory)/'release.zip',project/'examples/sample-library')
            with zipfile.ZipFile(result['path']) as archive:
                names = archive.namelist()
                self.assertTrue(any(name.endswith('src/interfaces/cli.py') for name in names))
                self.assertTrue(any(name.endswith('seed-library/manifest.json') for name in names))
                self.assertFalse(any('/configs/' in name or '/data/' in name or '/.git/' in name or '.venv' in name for name in names))
                self.assertFalse(any(name.endswith('source.md') for name in names))


if __name__ == '__main__':
    unittest.main()
