"""三张个人记录强制owner隔离，并用复合外键防止跨用户关联。"""
from importlib import import_module
from django.db import migrations


def access(apps, schema_editor):
    """apps/schema_editor为迁移上下文；仅授三表DML并强制RLS。"""
    runtime, migrator = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    for name in ('Bookmark', 'ActionRecord', 'Feedback'):
        table = schema_editor.quote_name(apps.get_model('personal', name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {runtime}')
        schema_editor.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'''CREATE POLICY personal_owner_access ON {table} FOR ALL TO {runtime}
            USING (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))
            WITH CHECK (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))''')
        schema_editor.execute(f'CREATE POLICY personal_management ON {table} FOR ALL TO {migrator} USING (true) WITH CHECK (true)')


def revoke(apps, schema_editor):
    """apps/schema_editor为回退上下文；先撤普通权限，再撤策略。"""
    runtime, _ = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    for name in ('Bookmark', 'ActionRecord', 'Feedback'):
        table = schema_editor.quote_name(apps.get_model('personal', name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'DROP POLICY personal_owner_access ON {table}')
        schema_editor.execute(f'DROP POLICY personal_management ON {table}')
        schema_editor.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [('personal', '0001_initial')]
    operations = [
        migrations.RunSQL('''ALTER TABLE personal_actionrecord ADD CONSTRAINT personal_action_owner_answer_fk
            FOREIGN KEY (owner_id, problem_id, answer_id) REFERENCES answers_answer (owner_id, problem_id, id)
            ON UPDATE RESTRICT ON DELETE RESTRICT;
            ALTER TABLE personal_feedback ADD CONSTRAINT personal_feedback_owner_answer_fk
            FOREIGN KEY (owner_id, answer_id) REFERENCES answers_answer (owner_id, id)
            ON UPDATE RESTRICT ON DELETE RESTRICT;''', reverse_sql='''
            ALTER TABLE personal_feedback DROP CONSTRAINT personal_feedback_owner_answer_fk;
            ALTER TABLE personal_actionrecord DROP CONSTRAINT personal_action_owner_answer_fk;'''),
        migrations.RunPython(access, revoke),
    ]
