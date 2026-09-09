"""明确授予两表DML并强制owner隔离；回退先撤权限再撤策略。"""
from django.conf import settings
from django.db import migrations


def roles(schema_editor):
    """schema_editor为迁移连接；只接受独立PostgreSQL迁移者和配置运行角色。"""
    if schema_editor.connection.vendor != 'postgresql':
        raise RuntimeError('问题存储仅支持PostgreSQL')
    runtime = getattr(settings, 'SB_RUNTIME_DB_ROLE', None)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('SELECT current_user')
        migrator = cursor.fetchone()[0]
    if not isinstance(runtime, str) or not runtime or runtime == migrator:
        raise RuntimeError('问题权限迁移必须使用独立迁移角色')
    return schema_editor.quote_name(runtime), schema_editor.quote_name(migrator)


def enable_access(apps, schema_editor):
    """apps为历史模型；schema_editor先收回旧授权，再设置仅本人读写和独立管理策略。"""
    runtime, migrator = roles(schema_editor)
    for name in ('Problem', 'IdempotencyRecord'):
        table = schema_editor.quote_name(apps.get_model('problems', name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {runtime}')
        schema_editor.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'''CREATE POLICY problem_owner_access ON {table}
            FOR ALL TO {runtime}
            USING (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))
            WITH CHECK (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))''')
        schema_editor.execute(f'''CREATE POLICY problem_management ON {table}
            FOR ALL TO {migrator} USING (true) WITH CHECK (true)''')


def disable_access(apps, schema_editor):
    """apps/schema_editor为历史状态和回退连接；撤runtime访问后才移除owner隔离。"""
    runtime, _ = roles(schema_editor)
    for name in ('Problem', 'IdempotencyRecord'):
        table = schema_editor.quote_name(apps.get_model('problems', name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'DROP POLICY problem_owner_access ON {table}')
        schema_editor.execute(f'DROP POLICY problem_management ON {table}')
        schema_editor.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    """本批只处理问题两表权限，不调整账号或知识表。"""
    dependencies = [('problems', '0001_initial'), ('knowledge', '0002_database_access')]
    operations = [migrations.RunPython(enable_access, disable_access)]
