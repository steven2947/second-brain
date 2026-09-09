"""任务公开事件有同owner关联、固定负载形状和独立最小DML/RLS。"""
import uuid
from importlib import import_module

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def enable_access(apps, schema_editor):
    """apps/schema_editor为历史模型和独立迁移连接；不放大worker身份。"""
    runtime, migrator = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    table = schema_editor.quote_name(apps.get_model('runs', 'JobEvent')._meta.db_table)
    schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
    schema_editor.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {runtime}')
    schema_editor.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    schema_editor.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    schema_editor.execute(f'''CREATE POLICY event_owner_access ON {table} FOR ALL TO {runtime}
        USING (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))
        WITH CHECK (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))''')
    schema_editor.execute(f'''CREATE POLICY event_management ON {table}
        FOR ALL TO {migrator} USING (true) WITH CHECK (true)''')


def disable_access(apps, schema_editor):
    """apps/schema_editor为回退模型和迁移连接；撤权后删除策略。"""
    runtime, _ = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    table = schema_editor.quote_name(apps.get_model('runs', 'JobEvent')._meta.db_table)
    schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
    schema_editor.execute(f'DROP POLICY event_owner_access ON {table}')
    schema_editor.execute(f'DROP POLICY event_management ON {table}')
    schema_editor.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
    schema_editor.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [
        ('runs', '0001_initial'),
        ('problems', '0006_problem_processed_message_sequence'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name='JobEvent', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('seq', models.BigIntegerField()),
            ('event_type', models.CharField(max_length=20)),
            ('public_payload', models.JSONField()),
            ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='runs.job')),
            ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'constraints': [
            models.UniqueConstraint(fields=('job', 'seq'), name='job_event_sequence_unique'),
            models.CheckConstraint(condition=models.Q(seq__gte=1), name='job_event_sequence_positive'),
            models.CheckConstraint(condition=models.Q(event_type__in=['stage', 'question_ready', 'failed', 'cancelled']), name='job_event_type_valid'),
        ]}),
        migrations.RunSQL('''ALTER TABLE runs_jobevent ADD CONSTRAINT event_owner_job_fk
            FOREIGN KEY (owner_id, job_id) REFERENCES runs_job (owner_id, id)
            ON UPDATE RESTRICT ON DELETE RESTRICT;
            ALTER TABLE runs_jobevent ADD CONSTRAINT event_public_payload_shape CHECK (
                jsonb_typeof(public_payload) = 'object'
                AND public_payload ?& ARRAY['job_id', 'run_id', 'stage']
                AND public_payload - ARRAY['job_id', 'run_id', 'stage'] = '{}'::jsonb
                AND jsonb_typeof(public_payload->'job_id') = 'string'
                AND public_payload->>'job_id' = job_id::text
                AND jsonb_typeof(public_payload->'run_id') = 'string'
                AND public_payload->>'run_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                AND jsonb_typeof(public_payload->'stage') = 'string'
                AND public_payload->>'stage' IN ('accepted','understanding','retrieving','evaluating','validating','composing')
            );''', reverse_sql='''ALTER TABLE runs_jobevent DROP CONSTRAINT event_public_payload_shape;
            ALTER TABLE runs_jobevent DROP CONSTRAINT event_owner_job_fk;'''),
        migrations.RunPython(enable_access, disable_access),
    ]
