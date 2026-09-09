"""迁移配置不能通过替换runtime URL把两种数据库身份混为一谈。"""
import json
import os
from pathlib import Path
import subprocess
import sys
from django.test import SimpleTestCase


class MigrationSettingsTests(SimpleTestCase):
    """只解析自编配置，无数据库连接、无凭据文件读取。"""

    def test_migration_connection_preserves_runtime_role_and_requires_separate_url(self):
        """无参数；独立子进程避免导入缓存，缺少迁移URL必须拒绝。"""
        root = Path(__file__).resolve().parents[2]
        env = {key: value for key, value in os.environ.items() if not key.startswith(('SB_', 'DJANGO_', 'PYTHONPATH'))}
        env.update(SB_ENV='development', SB_DATABASE_URL='postgresql://runtime:fixture@127.0.0.1:1/test_fixture',
                   SB_MIGRATION_DATABASE_URL='postgresql://migrator:fixture@127.0.0.1:1/test_fixture')
        script = "import json;from config.settings import migrate as s;print(json.dumps([s.SB_RUNTIME_DB_ROLE,s.DATABASES['default']['USER']]))"
        result = subprocess.run([sys.executable, '-c', script], cwd=root/'server', env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ['runtime', 'migrator'])
        env.pop('SB_MIGRATION_DATABASE_URL')
        rejected = subprocess.run([sys.executable, '-c', script], cwd=root/'server', env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(rejected.returncode, 0)
