"""验证环境配置在错误和不安全输入下拒绝启动。"""

import importlib
import secrets
import unittest


class EnvironmentTests(unittest.TestCase):
    """使用独立配置字典验证部署契约，不访问真实凭据。"""

    def setUp(self):
        """为每个测试生成仅存在内存中的生产配置。"""
        self.env = {
            "SB_ENV": "production",
            "SB_SECRET_KEY": secrets.token_urlsafe(64),
            "SB_PUBLIC_ORIGIN": "https://brain.example.org",
            "SB_ALLOWED_HOSTS": "brain.example.org",
            "SB_DATABASE_URL": "postgresql://runtime:unit-only@127.0.0.1:55439/brain",
            "SB_MIGRATION_DATABASE_URL": "postgresql://migrator:unit-only@127.0.0.1:55439/brain",
            "SB_PRIVATE_DATA_ROOT": "/srv/brain/private",
            "SB_LIBRARY_ROOT": "/srv/brain/library",
            "SB_MODEL_MODE": "disabled",
        }

    def load(self, env=None):
        """env 为待验证字典；未提供时使用当前测试配置。"""
        try:
            module = importlib.import_module("config.settings.environment")
        except ModuleNotFoundError:
            self.fail("服务端环境验证模块尚未实现")
        return module.build_settings(self.env if env is None else env)

    def test_production_uses_postgres_secure_cookies_and_exact_origin(self):
        """合法生产配置只生成运行角色连接和同源安全设置。"""
        values = self.load()
        self.assertEqual(values["DATABASES"]["default"]["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(values["DATABASES"]["default"]["USER"], "runtime")
        self.assertEqual(values.get("SB_RUNTIME_DB_ROLE"), "runtime")
        self.assertEqual(list(values["DATABASES"]), ["default"])
        self.assertEqual(values["DATABASES"]["default"]["CONN_MAX_AGE"], 0)
        self.assertFalse(values["DEBUG"])
        for key in ("SESSION_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT"):
            self.assertTrue(values[key], key)
        self.assertEqual(values["SESSION_COOKIE_SAMESITE"], "Lax")
        self.assertEqual(values["CSRF_TRUSTED_ORIGINS"], ["https://brain.example.org"])
        self.assertNotIn("SB_MIGRATION_DATABASE_URL", values)

    def test_required_production_values_fail_closed(self):
        """生产缺少必需配置时只提示变量名，不回显任何值。"""
        for key in ("SB_SECRET_KEY", "SB_PUBLIC_ORIGIN", "SB_ALLOWED_HOSTS", "SB_DATABASE_URL", "SB_PRIVATE_DATA_ROOT", "SB_LIBRARY_ROOT"):
            with self.subTest(key=key):
                env = dict(self.env)
                del env[key]
                with self.assertRaisesRegex(ValueError, key):
                    self.load(env)

    def test_invalid_values_are_rejected_without_echo(self):
        """危险来源、弱密钥、角色复用及错误枚举不能启动。"""
        cases = {
            "SB_ENV": ["staging", "", "prod"],
            "SB_DEBUG": ["true", "1", "yes", "unknown"],
            "SB_SECRET_KEY": ["short", "x" * 64, "django-insecure-" + secrets.token_urlsafe(64), "change-me-" + secrets.token_urlsafe(64)],
            "SB_PUBLIC_ORIGIN": ["http://brain.example.org", "https://brain.example.org/path", "https://user:secret@brain.example.org", "https://brain.example.org?x=1", "https://evil.org", "https://*.example.org"],
            "SB_ALLOWED_HOSTS": ["*", ".example.org", "brain.example.org:443", "https://brain.example.org", "evil.org", "brain.example.org,,localhost"],
            "SB_DATABASE_URL": ["sqlite:///test.db", "postgresql://runtime@localhost/brain", "postgresql://runtime:unit-only@localhost/", "postgresql://runtime:unit-only@localhost/brain?options=-crole=migrator", "postgresql://runtime:changeme@localhost/brain"],
            "SB_MIGRATION_DATABASE_URL": ["postgresql://runtime:unit-only@127.0.0.1:55439/brain", "postgresql://migrator:unit-only@127.0.0.1:55439/other"],
            "SB_PRIVATE_DATA_ROOT": ["relative", "/", "/srv/brain/web/public"],
            "SB_LIBRARY_ROOT": ["relative", "/", "/srv/brain/web/public"],
            "SB_MODEL_MODE": ["demo", "unknown"],
            "SB_CSRF_TRUSTED_ORIGINS": ["https://evil.org", "https://*.example.org"],
        }
        for key, invalid_values in cases.items():
            for value in invalid_values:
                with self.subTest(key=key, category=invalid_values.index(value)):
                    env = {**self.env, key: value}
                    with self.assertRaises(ValueError) as caught:
                        self.load(env)
                    self.assertNotIn(self.env["SB_SECRET_KEY"], str(caught.exception))
                    self.assertNotIn("unit-only", str(caught.exception))

    def test_runtime_does_not_require_migration_credentials(self):
        """API 可以只拿最小权限凭据，迁移秘密不得强制注入。"""
        del self.env["SB_MIGRATION_DATABASE_URL"]
        self.assertEqual(self.load()["DATABASES"]["default"]["USER"], "runtime")

    def test_development_requires_explicit_database_and_allows_demo(self):
        """开发模式允许显式演示，但不得隐式切到 SQLite。"""
        env = {"SB_ENV": "development", "SB_DATABASE_URL": self.env["SB_DATABASE_URL"], "SB_MODEL_MODE": "demo"}
        values = self.load(env)
        self.assertEqual(values["SB_MODEL_MODE"], "demo")
        self.assertFalse(values["DEBUG"])
        self.assertEqual(values["ALLOWED_HOSTS"], ["localhost", "127.0.0.1", "[::1]"])
        with self.assertRaisesRegex(ValueError, "SB_DATABASE_URL"):
            self.load({"SB_ENV": "development"})

    def test_model_modes_validate_required_values_without_fallback(self):
        """显式本地或供应商模式配置不全就失败，不能退回演示。"""
        for mode in ("local", "provider"):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(ValueError, "SB_MODEL"):
                    self.load({**self.env, "SB_MODEL_MODE": mode})
        local = {**self.env, "SB_MODEL_MODE": "local", "SB_MODEL_NAME": "configured-model", "SB_MODEL_BASE_URL": "http://127.0.0.1:11434/v1"}
        self.assertEqual(self.load(local)["SB_MODEL_MODE"], "local")
        with self.assertRaisesRegex(ValueError, "SB_MODEL_BASE_URL"):
            self.load({**local, "SB_MODEL_BASE_URL": "https://external.example.org"})
        provider = {**local, "SB_MODEL_MODE": "provider", "SB_MODEL_PROVIDER": "configured-provider", "SB_MODEL_API_KEY": secrets.token_urlsafe(32), "SB_MODEL_BASE_URL": "https://api.example.org/v1"}
        self.assertEqual(self.load(provider)["SB_MODEL_MODE"], "provider")
        with self.assertRaisesRegex(ValueError, "SB_MODEL_API_KEY"):
            self.load({**provider, "SB_MODEL_API_KEY": "your-api-key"})

    def test_percent_encoded_database_credentials_are_decoded(self):
        """连接 URL 中合法转义还原为驱动参数。"""
        self.env["SB_DATABASE_URL"] = "postgresql://runtime:p%40ss%3Aword@127.0.0.1:55439/brain?sslmode=require"
        database = self.load()["DATABASES"]["default"]
        self.assertEqual(database["PASSWORD"], "p@ss:word")
        self.assertEqual(database["OPTIONS"]["sslmode"], "require")

    def test_decoded_database_fields_reject_control_characters(self):
        """运行与迁移 URL 的账号、密码和库名解码后均不得含控制字符。"""
        from config.settings.environment import database_settings

        for key in ("SB_DATABASE_URL", "SB_MIGRATION_DATABASE_URL"):
            for production in (False, True):
                for field in ("username", "password", "database"):
                    for encoded in ("%00", "%0D", "%0A", "%09", "%1F", "%7F", "%C2%85"):
                        with self.subTest(key=key, production=production, field=field, encoded=encoded):
                            fields = {"username": "runtime", "password": "unit-only", "database": "brain"}
                            fields[field] += encoded + "suffix"
                            url = "postgresql://{username}:{password}@127.0.0.1:55439/{database}".format(**fields)
                            with self.assertRaisesRegex(ValueError, key) as caught:
                                database_settings(url, key, production)
                            self.assertNotIn("unit-only", str(caught.exception))
                            self.assertNotIn("suffix", str(caught.exception))

    def test_decoded_database_name_rejects_encoded_slash(self):
        """库名不能用百分号转义绕过单段名称约束。"""
        from config.settings.environment import database_settings

        for key in ("SB_DATABASE_URL", "SB_MIGRATION_DATABASE_URL"):
            for encoded in ("%2f", "%2F"):
                with self.subTest(key=key, encoded=encoded):
                    with self.assertRaisesRegex(ValueError, key):
                        database_settings(f"postgresql://runtime:unit-only@127.0.0.1/brain{encoded}suffix", key, False)
