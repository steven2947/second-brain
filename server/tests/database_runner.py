"""只在 test_sb_product 创建迁移表，测试本体始终以受限运行角色访问。"""
from django.conf import settings
from django.db import connections
from django.test.runner import DiscoverRunner
from tools.dev.product_db import validate_roles, verify_identity


class RuntimeDatabaseRunner(DiscoverRunner):
    """迁移与销毁使用 migrator；HTTP/ORM 测试使用 runtime。"""

    def setup_databases(self, **kwargs):
        """kwargs 为 Django 标准测试选项；拒绝复用或自动覆盖已有测试库。"""
        if self.keepdb or self.parallel > 1:
            raise RuntimeError("账号集成测试禁止 keepdb 和并行建库")
        verify_identity(settings.DEV_CONFIG)
        if not validate_roles(settings.DEV_CONFIG):
            raise RuntimeError("开发角色未初始化")
        connection = connections["default"]
        if connection.settings_dict["NAME"] != "sb_product" or connection.settings_dict["TEST"]["NAME"] != "test_sb_product":
            raise RuntimeError("测试库名称不在许可范围")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'test_sb_product'")
            if cursor.fetchone():
                raise RuntimeError("测试库已存在；请先核对，禁止自动覆盖")
        old_config = super().setup_databases(**kwargs)
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user")
            if cursor.fetchone() != ("test_sb_product", "sb_migrator"):
                raise RuntimeError("迁移连接身份不符")
            cursor.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
            cursor.execute("GRANT USAGE ON SCHEMA public TO sb_runtime")
            # 知识表权限完全由knowledge迁移负责；测试准备不可重新放大为管理DML。
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            for (table,) in cursor.fetchall():
                if (not table.startswith(('knowledge_', 'problems_', 'runs_', 'answers_', 'operations_', 'personal_', 'learning_', 'administration_', 'publishing_'))
                        and table not in ('auth_group', 'auth_permission', 'auth_group_permissions',
                                          'accounts_user_groups', 'accounts_user_user_permissions')):
                    cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {connection.ops.quote_name(table)} TO sb_runtime")
            cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sb_runtime")
        self.migration_credentials = {key: connection.settings_dict[key] for key in ("USER", "PASSWORD")}
        connection.close()
        connection.settings_dict.update({key: settings.RUNTIME_DATABASE[key] for key in ("USER", "PASSWORD")})
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, rolsuper, rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname=current_user")
            if cursor.fetchone() != ("test_sb_product", "sb_runtime", False, False, False):
                raise RuntimeError("测试本体必须使用受限运行角色")
        return old_config

    def teardown_databases(self, old_config, **kwargs):
        """old_config/kwargs 为框架生命周期数据；仅恢复迁移身份销毁固定测试库。"""
        connection = connections["default"]
        if connection.settings_dict["NAME"] != "test_sb_product":
            raise RuntimeError("拒绝销毁非测试库")
        connection.close()
        connection.settings_dict.update(self.migration_credentials)
        super().teardown_databases(old_config, **kwargs)
