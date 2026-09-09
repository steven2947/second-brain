"""知识管理表权限与grant行级读取；回退时收回runtime访问，防止撤掉RLS后开放授权行。"""
from django.conf import settings
from django.db import migrations


MODELS = ('LibraryCollection', 'LibraryRelease', 'LibraryGrant', 'RightsRecord',
          'ReleaseBook', 'ReleaseCard', 'ReleaseEvidence')


def roles(schema_editor):
    """schema_editor为当前迁移连接；返回已引用的运行/迁移角色，拒绝同角色操作。"""
    if schema_editor.connection.vendor != 'postgresql':
        raise RuntimeError('知识权限迁移仅支持PostgreSQL')
    runtime = getattr(settings, 'SB_RUNTIME_DB_ROLE', None)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('SELECT current_user')
        migrator = cursor.fetchone()[0]
    if not isinstance(runtime, str) or not runtime or runtime == migrator:
        raise RuntimeError('知识权限迁移必须使用独立迁移角色和已登记运行角色')
    return schema_editor.quote_name(runtime), schema_editor.quote_name(migrator)


def enable_access(apps, schema_editor):
    """apps为历史模型注册表，schema_editor为迁移连接；明确区分owner读策略和管理写策略。"""
    runtime, migrator = roles(schema_editor)
    for name in MODELS:
        managed_table = schema_editor.quote_name(apps.get_model('knowledge', name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {managed_table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'GRANT SELECT ON TABLE {managed_table} TO {runtime}')
    table = schema_editor.quote_name(apps.get_model('knowledge', 'LibraryGrant')._meta.db_table)
    schema_editor.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    schema_editor.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    schema_editor.execute(f'''CREATE POLICY knowledge_grant_owner_read ON {table}
        FOR SELECT TO {runtime}
        USING (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))''')
    schema_editor.execute(f'''CREATE POLICY knowledge_grant_management ON {table}
        FOR ALL TO {migrator} USING (true) WITH CHECK (true)''')


def disable_access(apps, schema_editor):
    """apps/schema_editor为回退历史状态；先撤runtime权限再撤RLS，不恢复已删业务记录。"""
    runtime, _ = roles(schema_editor)
    for name in MODELS:
        managed_table = schema_editor.quote_name(apps.get_model('knowledge', name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {managed_table} FROM PUBLIC, {runtime}')
    table = schema_editor.quote_name(apps.get_model('knowledge', 'LibraryGrant')._meta.db_table)
    schema_editor.execute(f'DROP POLICY knowledge_grant_owner_read ON {table}')
    schema_editor.execute(f'DROP POLICY knowledge_grant_management ON {table}')
    schema_editor.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
    schema_editor.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    """只处理新知识表，不调整账号/会话既有权限。"""
    dependencies = [('knowledge', '0001_initial')]
    operations = [
        migrations.RunSQL(
            sql='''
                ALTER TABLE knowledge_releasecard ADD CONSTRAINT knowledge_card_release_book_fk
                FOREIGN KEY (release_id, core_book_id)
                REFERENCES knowledge_releasebook (release_id, core_book_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT;
                ALTER TABLE knowledge_releaseevidence ADD CONSTRAINT knowledge_evidence_release_book_fk
                FOREIGN KEY (release_id, core_book_id)
                REFERENCES knowledge_releasebook (release_id, core_book_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT;
            ''',
            reverse_sql='''
                ALTER TABLE knowledge_releasecard DROP CONSTRAINT knowledge_card_release_book_fk;
                ALTER TABLE knowledge_releaseevidence DROP CONSTRAINT knowledge_evidence_release_book_fk;
            ''',
        ),
        migrations.RunPython(enable_access, disable_access),
    ]
