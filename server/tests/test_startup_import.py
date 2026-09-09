"""正式入口的独立进程导入回归；仅加载自编知识，不连接数据库或启动端口。"""

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase


SERVER = Path(__file__).resolve().parents[1]
PROBE = f"""
from pathlib import Path
import tests
assert Path(tests.__file__).resolve().parent == Path({str(SERVER / 'tests')!r})
from src.knowledge.library import Library
from knowledge.release_loader import load_release
from tests.test_release_loader import FIXTURES, fingerprint
expected = fingerprint(FIXTURES / 'releaseA')
loaded = load_release('releaseA', expected, expected[:24], library_root=FIXTURES)
assert isinstance(loaded, Library)
assert loaded.version == expected[:24]
assert len(loaded.list_books()) == 2
print('STARTUP_CORE_AND_RELEASE_OK')
"""


class StartupImportTests(SimpleTestCase):
    """验证任意工作目录下的正式入口可加载旧核心，同时保留服务端测试包。"""

    def run_probe(self, arguments):
        """arguments 为当前产品 Python 的参数；清除继承配置并在临时工作目录运行。"""
        environment = {
            key: value for key, value in os.environ.items()
            if key != 'PYTHONPATH' and not key.startswith(('SB_', 'DJANGO_'))
        }
        with TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, *arguments], cwd=directory, env=environment,
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('STARTUP_CORE_AND_RELEASE_OK', result.stdout)

    def test_manage_imports_core_outside_repository(self):
        """无参数；真正 manage.py shell 只选择自编测试配置后加载真实核心和 releaseA。"""
        self.run_probe([
            str(SERVER / 'manage.py'), 'shell', '--settings=tests.settings', '-c', PROBE,
        ])

    def test_asgi_imports_core_outside_repository(self):
        """无参数；模拟 ASGI 的 server app-dir，导入应用后检查核心与自编 releaseA。"""
        self.run_probe(['-c', f"""
import os
import sys
sys.path.insert(0, {str(SERVER)!r})
os.environ['DJANGO_SETTINGS_MODULE'] = 'tests.settings'
import config.asgi
assert callable(config.asgi.application)
{PROBE}
"""])
