"""配额和调用账本由迁移独立授予最小DML，并强制同owner关联。"""
from importlib import import_module
from django.db import migrations


def access(apps, schema_editor):
    """apps/schema_editor为历史模型与迁移连接；每表强制事务owner策略。"""
    runtime, migrator = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    for name in ('QuotaBucket', 'RunReservation', 'UsageEntry'):
        table = schema_editor.quote_name(apps.get_model('operations', name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {runtime}')
        schema_editor.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'''CREATE POLICY operations_owner_access ON {table} FOR ALL TO {runtime}
            USING (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))
            WITH CHECK (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))''')
        schema_editor.execute(f'''CREATE POLICY operations_management ON {table}
            FOR ALL TO {migrator} USING (true) WITH CHECK (true)''')


def revoke(apps, schema_editor):
    """apps/schema_editor为回退上下文；撤权后撤销策略。"""
    runtime, _ = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    for name in ('QuotaBucket', 'RunReservation', 'UsageEntry'):
        table = schema_editor.quote_name(apps.get_model('operations', name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'DROP POLICY operations_owner_access ON {table}')
        schema_editor.execute(f'DROP POLICY operations_management ON {table}')
        schema_editor.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [('operations', '0001_initial')]
    operations = [
        migrations.RunSQL('''CREATE UNIQUE INDEX operations_run_owner_id_unique ON runs_analysisrun (owner_id, id);
            ALTER TABLE operations_runreservation ADD CONSTRAINT reservation_owner_run_fk
                FOREIGN KEY (owner_id, run_id) REFERENCES runs_analysisrun (owner_id, id)
                ON UPDATE RESTRICT ON DELETE RESTRICT;
            ALTER TABLE operations_usageentry ADD CONSTRAINT usage_owner_run_fk
                FOREIGN KEY (owner_id, run_id) REFERENCES runs_analysisrun (owner_id, id)
                ON UPDATE RESTRICT ON DELETE RESTRICT;
            ALTER TABLE operations_runreservation ADD CONSTRAINT reservation_owner_bucket_fk
                FOREIGN KEY (owner_id, bucket_id) REFERENCES operations_quotabucket (owner_id, id)
                ON UPDATE RESTRICT ON DELETE RESTRICT;''', reverse_sql='''
            ALTER TABLE operations_runreservation DROP CONSTRAINT reservation_owner_bucket_fk;
            ALTER TABLE operations_usageentry DROP CONSTRAINT usage_owner_run_fk;
            ALTER TABLE operations_runreservation DROP CONSTRAINT reservation_owner_run_fk;
            DROP INDEX operations_run_owner_id_unique;'''),
        migrations.RunPython(access, revoke),
    ]
