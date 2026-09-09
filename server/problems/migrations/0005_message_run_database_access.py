"""消息和任务同owner/问题/版本的数据库约束；三私有表独立最小DML和FORCE RLS。"""
from importlib import import_module

from django.db import migrations


TABLES = (('problems', 'Message'), ('runs', 'Job'), ('runs', 'AnalysisRun'))


def enable_access(apps, schema_editor):
    """apps为历史模型；迁移连接以独立角色建立owner策略并明确授予运行DML。"""
    runtime, migrator = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    for app, name in TABLES:
        table = schema_editor.quote_name(apps.get_model(app, name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {runtime}')
        schema_editor.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'''CREATE POLICY task_owner_access ON {table}
            FOR ALL TO {runtime}
            USING (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))
            WITH CHECK (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))''')
        schema_editor.execute(f'''CREATE POLICY task_management ON {table}
            FOR ALL TO {migrator} USING (true) WITH CHECK (true)''')


def disable_access(apps, schema_editor):
    """apps/schema_editor为回退状态和独立迁移连接；先撤运行权限再移除策略。"""
    runtime, _ = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    for app, name in TABLES:
        table = schema_editor.quote_name(apps.get_model(app, name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'DROP POLICY task_owner_access ON {table}')
        schema_editor.execute(f'DROP POLICY task_management ON {table}')
        schema_editor.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    """循环关系在两模型存在后建立；回退移除复合FK及runtime访问。"""
    dependencies = [
        ('problems', '0004_message_run_message_message_problem_sequence_unique_and_more'),
        ('runs', '0001_initial'),
    ]
    operations = [
        migrations.RunSQL(
            sql='''
                ALTER TABLE problems_problem ADD CONSTRAINT problem_owner_release_id_unique
                    UNIQUE (owner_id, id, release_id);
                ALTER TABLE problems_message ADD CONSTRAINT message_owner_problem_fk
                    FOREIGN KEY (owner_id, problem_id) REFERENCES problems_problem (owner_id, id)
                    ON UPDATE RESTRICT ON DELETE RESTRICT;
                ALTER TABLE runs_analysisrun ADD CONSTRAINT run_owner_problem_release_fk
                    FOREIGN KEY (owner_id, problem_id, release_id)
                    REFERENCES problems_problem (owner_id, id, release_id)
                    ON UPDATE RESTRICT ON DELETE RESTRICT;
                ALTER TABLE runs_analysisrun ADD CONSTRAINT run_owner_job_fk
                    FOREIGN KEY (owner_id, job_id) REFERENCES runs_job (owner_id, id)
                    ON UPDATE RESTRICT ON DELETE RESTRICT;
                ALTER TABLE problems_message ADD CONSTRAINT message_owner_problem_run_fk
                    FOREIGN KEY (owner_id, problem_id, run_id)
                    REFERENCES runs_analysisrun (owner_id, problem_id, id)
                    ON UPDATE RESTRICT ON DELETE RESTRICT;
                ALTER TABLE runs_analysisrun ADD CONSTRAINT run_owner_problem_input_fk
                    FOREIGN KEY (owner_id, problem_id, input_message_id)
                    REFERENCES problems_message (owner_id, problem_id, id)
                    ON UPDATE RESTRICT ON DELETE RESTRICT;
            ''',
            reverse_sql='''
                ALTER TABLE runs_analysisrun DROP CONSTRAINT run_owner_problem_input_fk;
                ALTER TABLE problems_message DROP CONSTRAINT message_owner_problem_run_fk;
                ALTER TABLE runs_analysisrun DROP CONSTRAINT run_owner_job_fk;
                ALTER TABLE runs_analysisrun DROP CONSTRAINT run_owner_problem_release_fk;
                ALTER TABLE problems_message DROP CONSTRAINT message_owner_problem_fk;
                ALTER TABLE problems_problem DROP CONSTRAINT problem_owner_release_id_unique;
            ''',
        ),
        migrations.RunPython(enable_access, disable_access),
    ]
