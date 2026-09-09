"""迁移负责最小运行权限：设备 owner RLS、校验列更新及只追加审计。"""
from django.conf import settings
from django.db import migrations

AUTH_TABLES = ('auth_group', 'auth_permission', 'auth_group_permissions',
               'accounts_user_groups', 'accounts_user_user_permissions')


def roles(schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        raise RuntimeError('管理员身份仅支持 PostgreSQL')
    runtime = getattr(settings, 'SB_RUNTIME_DB_ROLE', None)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('SELECT current_user')
        migrator = cursor.fetchone()[0]
    if not runtime or runtime == migrator:
        raise RuntimeError('管理员权限迁移必须使用独立迁移角色')
    return schema_editor.quote_name(runtime), schema_editor.quote_name(migrator)


def enable_access(apps, schema_editor):
    runtime, migrator = roles(schema_editor)
    for name, columns in (('AdministratorDevice', 'last_t, failure_count, next_attempt_at'),
                          ('RecoveryCode', 'consumed_at')):
        table = schema_editor.quote_name(apps.get_model('administration', name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'GRANT SELECT, UPDATE ({columns}) ON TABLE {table} TO {runtime}')
        schema_editor.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'''CREATE POLICY administrator_owner ON {table} FOR ALL TO {runtime}
            USING (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))
            WITH CHECK (owner_id::text = nullif(current_setting('sb.owner_id', true), ''))''')
        schema_editor.execute(f'''CREATE POLICY administrator_management ON {table}
            FOR ALL TO {migrator} USING (true) WITH CHECK (true)''')
    table = schema_editor.quote_name(apps.get_model('administration', 'AdminAudit')._meta.db_table)
    schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
    schema_editor.execute(f'GRANT INSERT ON TABLE {table} TO {runtime}')
    for name in AUTH_TABLES:
        table = schema_editor.quote_name(name)
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'GRANT SELECT ON TABLE {table} TO {runtime}')
        if name.startswith('accounts_'):
            schema_editor.execute(f'GRANT DELETE ON TABLE {table} TO {runtime}')


def disable_access(apps, schema_editor):
    runtime, _ = roles(schema_editor)
    for name in ('AdministratorDevice', 'RecoveryCode', 'AdminAudit'):
        table = schema_editor.quote_name(apps.get_model('administration', name)._meta.db_table)
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        if name != 'AdminAudit':
            columns = 'last_t, failure_count, next_attempt_at' if name == 'AdministratorDevice' else 'consumed_at'
            schema_editor.execute(f'REVOKE UPDATE ({columns}) ON TABLE {table} FROM {runtime}')
            schema_editor.execute(f'DROP POLICY administrator_owner ON {table}')
            schema_editor.execute(f'DROP POLICY administrator_management ON {table}')
            schema_editor.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
            schema_editor.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')
    # 回退不重新开放旧的权限授予写入；既有账号删除权限继续保留。


class Migration(migrations.Migration):
    dependencies = [('administration', '0001_initial'), ('accounts', '0004_identity_epoch_guard'),
                    ('auth', '0012_alter_user_first_name_max_length')]
    operations = [migrations.RunPython(enable_access, disable_access)]
