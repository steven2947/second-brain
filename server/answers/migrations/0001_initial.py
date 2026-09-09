"""正式答案与运行同owner/同problem绑定；普通运行角色受FORCE RLS限制。"""
import uuid
from importlib import import_module
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def access(apps, schema_editor):
    """apps/schema_editor为迁移上下文；只授本表DML，不授管理员或TRUNCATE权限。"""
    runtime, migrator = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    table = schema_editor.quote_name(apps.get_model('answers', 'Answer')._meta.db_table)
    schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
    schema_editor.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {runtime}')
    schema_editor.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    schema_editor.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    schema_editor.execute(f'''CREATE POLICY answer_owner_access ON {table} FOR ALL TO {runtime}
        USING (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))
        WITH CHECK (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))''')
    schema_editor.execute(f'CREATE POLICY answer_management ON {table} FOR ALL TO {migrator} USING (true) WITH CHECK (true)')


def revoke(apps, schema_editor):
    """apps/schema_editor为回退上下文；先撤普通访问，再撤策略与表。"""
    runtime, _ = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    table = schema_editor.quote_name(apps.get_model('answers', 'Answer')._meta.db_table)
    schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
    schema_editor.execute(f'DROP POLICY answer_owner_access ON {table}')
    schema_editor.execute(f'DROP POLICY answer_management ON {table}')
    schema_editor.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
    schema_editor.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [('runs', '0002_jobevent'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='Answer', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('schema_version', models.PositiveSmallIntegerField(default=3)),
            ('internal_packet', models.JSONField()), ('public_payload', models.JSONField()),
            ('rendered_markdown', models.TextField()), ('content_hash', models.CharField(max_length=64)),
            ('validation_status', models.CharField(default='structure_passed', max_length=24)),
            ('published_at', models.DateTimeField()),
            ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ('problem', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='problems.problem')),
            ('run', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='runs.analysisrun')),
        ], options={'constraints': [
            models.UniqueConstraint(fields=('owner', 'problem', 'id'), name='answer_owner_problem_id_unique'),
            models.CheckConstraint(condition=models.Q(schema_version=3), name='answer_schema_v3'),
            models.CheckConstraint(condition=models.Q(content_hash__regex=r'^[0-9a-f]{64}$'), name='answer_hash_valid'),
            models.CheckConstraint(condition=models.Q(validation_status__in=['structure_passed', 'semantic_reviewed']), name='answer_validation_status'),
        ], 'indexes': [models.Index(fields=['owner', 'problem', '-published_at', 'id'], name='answer_owner_problem_time')]}),
        migrations.RunSQL('''ALTER TABLE answers_answer ADD CONSTRAINT answer_owner_problem_run_fk
            FOREIGN KEY (owner_id, problem_id, run_id) REFERENCES runs_analysisrun (owner_id, problem_id, id)
            ON UPDATE RESTRICT ON DELETE RESTRICT;''',
            reverse_sql='ALTER TABLE answers_answer DROP CONSTRAINT answer_owner_problem_run_fk'),
        migrations.RunPython(access, revoke),
    ]
