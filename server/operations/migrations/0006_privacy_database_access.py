"""导出强制本人RLS；无身份保留统计只供独立受控维护连接访问。"""
from importlib import import_module
from django.db import migrations


def access(apps, schema_editor):
    """apps/schema_editor为迁移模型与独立角色，不给普通worker跨租户能力。"""
    runtime, migrator = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    table = schema_editor.quote_name(apps.get_model('operations', 'PersonalExport')._meta.db_table)
    schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
    schema_editor.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {runtime}')
    schema_editor.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    schema_editor.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    schema_editor.execute(f'''CREATE POLICY export_owner_access ON {table} FOR ALL TO {runtime}
        USING (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))
        WITH CHECK (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))''')
    schema_editor.execute(f'''CREATE POLICY export_management ON {table}
        FOR ALL TO {migrator} USING (true) WITH CHECK (true)''')
    retained = schema_editor.quote_name(apps.get_model('operations', 'RetainedUsage')._meta.db_table)
    schema_editor.execute(f'REVOKE ALL ON TABLE {retained} FROM PUBLIC, {runtime}')


def revoke(apps, schema_editor):
    """apps/schema_editor为回退上下文；先撤权再撤RLS。"""
    runtime, _ = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    table = schema_editor.quote_name(apps.get_model('operations', 'PersonalExport')._meta.db_table)
    schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
    schema_editor.execute(f'DROP POLICY export_owner_access ON {table}')
    schema_editor.execute(f'DROP POLICY export_management ON {table}')
    schema_editor.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
    schema_editor.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [('operations', '0005_retainedusage_personalexport')]
    operations = [migrations.RunPython(access, revoke)]
