"""学习父域、真实回答引用和owner隔离在数据库再次约束。"""
from importlib import import_module
from django.db import migrations


def access(apps, schema_editor):
    """apps/schema_editor为迁移上下文；仅授两张学习表DML并强制owner策略。"""
    runtime, migrator = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    for name in ('LearningSession', 'LearningTurn'):
        table = schema_editor.quote_name(apps.get_model('learning', name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {runtime}')
        schema_editor.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'''CREATE POLICY learning_owner_access ON {table} FOR ALL TO {runtime}
            USING (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))
            WITH CHECK (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))''')
        schema_editor.execute(f'CREATE POLICY learning_management ON {table} FOR ALL TO {migrator} USING (true) WITH CHECK (true)')


def revoke(apps, schema_editor):
    """apps/schema_editor为回退上下文；撤回普通角色表权限与策略。"""
    runtime, _ = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    for name in ('LearningSession', 'LearningTurn'):
        table = schema_editor.quote_name(apps.get_model('learning', name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'DROP POLICY learning_owner_access ON {table}')
        schema_editor.execute(f'DROP POLICY learning_management ON {table}')
        schema_editor.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [('learning', '0001_initial'), ('runs', '0004_remove_analysisrun_run_kind_valid_and_more'),
                    ('problems', '0005_message_run_database_access')]
    operations = [migrations.RunSQL('''
        ALTER TABLE learning_learningsession ADD CONSTRAINT learning_owner_problem_release_fk
            FOREIGN KEY (owner_id, problem_id, release_id) REFERENCES problems_problem (owner_id, id, release_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT;
        ALTER TABLE runs_analysisrun ADD CONSTRAINT run_owner_learning_release_fk
            FOREIGN KEY (owner_id, learning_session_id, release_id) REFERENCES learning_learningsession (owner_id, id, release_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT;
        ALTER TABLE learning_learningturn ADD CONSTRAINT learning_turn_owner_session_fk
            FOREIGN KEY (owner_id, learning_session_id) REFERENCES learning_learningsession (owner_id, id)
            ON UPDATE RESTRICT ON DELETE RESTRICT;
        ALTER TABLE learning_learningturn ADD CONSTRAINT learning_turn_owner_run_fk
            FOREIGN KEY (owner_id, learning_session_id, run_id) REFERENCES runs_analysisrun (owner_id, learning_session_id, id)
            ON UPDATE RESTRICT ON DELETE RESTRICT;
        ALTER TABLE learning_learningturn ADD CONSTRAINT learning_turn_response_fk
            FOREIGN KEY (owner_id, learning_session_id, responds_to_turn_id) REFERENCES learning_learningturn (owner_id, learning_session_id, id)
            ON UPDATE RESTRICT ON DELETE RESTRICT;
        CREATE FUNCTION learning_check_response() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.kind IN ('user_response', 'feedback') AND NOT EXISTS (
                SELECT 1 FROM learning_learningturn target WHERE target.id = NEW.responds_to_turn_id
                AND target.owner_id = NEW.owner_id AND target.learning_session_id = NEW.learning_session_id
                AND target.sequence < NEW.sequence
                AND target.kind = CASE WHEN NEW.kind = 'feedback' THEN 'user_response' ELSE 'exercise' END
                AND length(btrim(target.content->>'text')) > 0
            ) THEN RAISE EXCEPTION 'invalid learning response'; END IF;
            IF length(btrim(NEW.content->>'text')) IS NULL OR length(btrim(NEW.content->>'text')) = 0
                THEN RAISE EXCEPTION 'empty learning content'; END IF;
            RETURN NEW;
        END; $$;
        REVOKE ALL ON FUNCTION learning_check_response() FROM PUBLIC;
        CREATE TRIGGER learning_response_guard BEFORE INSERT OR UPDATE ON learning_learningturn
            FOR EACH ROW EXECUTE FUNCTION learning_check_response();
        ''', reverse_sql='''
        DROP TRIGGER learning_response_guard ON learning_learningturn;
        DROP FUNCTION learning_check_response();
        ALTER TABLE learning_learningturn DROP CONSTRAINT learning_turn_response_fk;
        ALTER TABLE learning_learningturn DROP CONSTRAINT learning_turn_owner_run_fk;
        ALTER TABLE learning_learningturn DROP CONSTRAINT learning_turn_owner_session_fk;
        ALTER TABLE runs_analysisrun DROP CONSTRAINT run_owner_learning_release_fk;
        ALTER TABLE learning_learningsession DROP CONSTRAINT learning_owner_problem_release_fk;
        '''), migrations.RunPython(access, revoke)]
