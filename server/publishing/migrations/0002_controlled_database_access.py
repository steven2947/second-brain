"""受限管理通道：当前owner的真实设备和显式权限决定知识写，源仅迁移角色登记。"""
from django.conf import settings
from django.db import migrations


def roles(schema_editor):
    """schema_editor为独立迁移连接；返回安全引用角色并禁止runtime执行迁移。"""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('SELECT current_user')
        migrator = cursor.fetchone()[0]
    runtime = settings.SB_RUNTIME_DB_ROLE
    if schema_editor.connection.vendor != 'postgresql' or not runtime or migrator == runtime:
        raise RuntimeError('知识管理迁移需要独立PostgreSQL迁移身份')
    return schema_editor.quote_name(runtime), schema_editor.quote_name(migrator)


def enable_access(apps, schema_editor):
    """apps为历史模型，schema_editor为迁移连接；所有DML先启用RLS再授予权限。"""
    runtime, migrator = roles(schema_editor)
    schema_editor.execute('''CREATE FUNCTION sb_admin_permission(required_code text) RETURNS boolean
        LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public,pg_temp AS $$
        SELECT EXISTS (SELECT 1 FROM accounts_user u
          JOIN administration_administratordevice d ON d.owner_id=u.id
          WHERE u.id::text=nullif(current_setting('sb.owner_id', true), '')
            AND u.status='active' AND u.is_staff AND d.confirmed_at IS NOT NULL AND d.revoked_at IS NULL
            AND EXISTS (SELECT 1 FROM auth_permission p
              JOIN django_content_type ct ON ct.id=p.content_type_id
              WHERE ct.app_label='administration' AND ct.model='administratordevice' AND p.codename=required_code
                AND (EXISTS (SELECT 1 FROM accounts_user_user_permissions up WHERE up.user_id=u.id AND up.permission_id=p.id)
                  OR EXISTS (SELECT 1 FROM accounts_user_groups ug JOIN auth_group_permissions gp ON gp.group_id=ug.group_id
                             WHERE ug.user_id=u.id AND gp.permission_id=p.id)))) $$''')
    schema_editor.execute('REVOKE ALL ON FUNCTION sb_admin_permission(text) FROM PUBLIC')
    schema_editor.execute(f'GRANT EXECUTE ON FUNCTION sb_admin_permission(text) TO {runtime}, {migrator}')
    # 注册源没有runtime写权限；移除测试runner旧泛化授权的可能性。
    schema_editor.execute(f'REVOKE ALL ON TABLE publishing_registeredsource FROM PUBLIC, {runtime}')
    schema_editor.execute(f'GRANT SELECT ON TABLE publishing_registeredsource TO {runtime}')
    for table in ('publishing_importjob', 'publishing_adminmutation'):
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        schema_editor.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'''CREATE POLICY publishing_owner ON {table} FOR ALL TO {runtime}
            USING (owner_id::text=nullif(current_setting('sb.owner_id', true), ''))
            WITH CHECK (owner_id::text=nullif(current_setting('sb.owner_id', true), ''))''')
        schema_editor.execute(f'CREATE POLICY publishing_migrator ON {table} FOR ALL TO {migrator} USING (true) WITH CHECK (true)')
        schema_editor.execute(f'GRANT SELECT, INSERT, UPDATE ON TABLE {table} TO {runtime}')
    tables = {'knowledge_librarycollection': ['knowledge_import'], 'knowledge_libraryrelease': ['knowledge_import', 'knowledge_review', 'knowledge_publish', 'knowledge_revoke', 'grants_manage'],
        'knowledge_rightsrecord': ['knowledge_review'], 'knowledge_releasebook': ['knowledge_import'],
        'knowledge_releasecard': ['knowledge_import'], 'knowledge_releaseevidence': ['knowledge_import'], 'knowledge_librarygrant': ['grants_manage']}
    for table, permissions in tables.items():
        expression = '(' + ' OR '.join(f"sb_admin_permission('{permission}')" for permission in permissions) + ')'
        if table == 'knowledge_rightsrecord':
            expression += " AND EXISTS (SELECT 1 FROM knowledge_libraryrelease r WHERE r.id=release_id AND r.status<>'published')"
        if table == 'knowledge_librarygrant':
            expression += " AND EXISTS (SELECT 1 FROM accounts_user u WHERE u.id=owner_id AND u.status='active' AND NOT u.is_staff AND NOT u.is_superuser)"
        if table != 'knowledge_librarygrant':
            schema_editor.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
            schema_editor.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
            schema_editor.execute(f'CREATE POLICY publishing_shared_read ON {table} FOR SELECT TO {runtime} USING (true)')
            schema_editor.execute(f'CREATE POLICY publishing_migrator ON {table} FOR ALL TO {migrator} USING (true) WITH CHECK (true)')
        else:
            schema_editor.execute(f'CREATE POLICY publishing_grant_read ON {table} FOR SELECT TO {runtime} USING ({expression})')
        insert_expression = "sb_admin_permission('knowledge_import') AND status='validated' AND rights_status='unreviewed'" if table == 'knowledge_libraryrelease' else expression
        if table == 'knowledge_librarycollection':
            insert_expression += " AND curator_id::text=nullif(current_setting('sb.owner_id', true), '')"
        if table == 'knowledge_libraryrelease':
            insert_expression += " AND EXISTS (SELECT 1 FROM knowledge_librarycollection c WHERE c.id=library_id AND c.curator_id::text=nullif(current_setting('sb.owner_id', true), ''))"
        if table in ('knowledge_releasebook', 'knowledge_releasecard', 'knowledge_releaseevidence'):
            insert_expression += " AND EXISTS (SELECT 1 FROM knowledge_libraryrelease r JOIN knowledge_librarycollection c ON c.id=r.library_id WHERE r.id=release_id AND r.status='validated' AND r.rights_status='unreviewed' AND c.curator_id::text=nullif(current_setting('sb.owner_id', true), ''))"
        schema_editor.execute(f'CREATE POLICY publishing_insert ON {table} FOR INSERT TO {runtime} WITH CHECK ({insert_expression})')
        schema_editor.execute(f'GRANT INSERT ON TABLE {table} TO {runtime}')
        if table in ('knowledge_libraryrelease', 'knowledge_rightsrecord', 'knowledge_librarygrant'):
            schema_editor.execute(f'CREATE POLICY publishing_update ON {table} FOR UPDATE TO {runtime} USING ({expression}) WITH CHECK ({expression})')
            schema_editor.execute(f'GRANT UPDATE ON TABLE {table} TO {runtime}')
    # RLS按行控制，状态/权限字段组合由触发器进一步限制；迁移连接仍可维护历史事实。
    schema_editor.execute(f'''CREATE FUNCTION sb_guard_release_update() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$ BEGIN
        IF current_user = pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid=TG_RELID)) THEN RETURN NEW; END IF;
        IF (to_jsonb(NEW) - ARRAY['status','rights_status','rights_record_key','published_at','updated_at'])
            IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','rights_status','rights_record_key','published_at','updated_at']) THEN
            RAISE EXCEPTION 'immutable release' USING ERRCODE='42501'; END IF;
        IF NEW.status IS DISTINCT FROM OLD.status OR NEW.published_at IS DISTINCT FROM OLD.published_at THEN
          IF NOT ((NEW.status='published' AND sb_admin_permission('knowledge_publish'))
              OR (NEW.status='revoked' AND sb_admin_permission('knowledge_revoke'))) THEN
            RAISE EXCEPTION 'release transition denied' USING ERRCODE='42501'; END IF;
        END IF;
        IF NEW.rights_status IS DISTINCT FROM OLD.rights_status OR NEW.rights_record_key IS DISTINCT FROM OLD.rights_record_key THEN
          IF OLD.status='published' OR NOT sb_admin_permission('knowledge_review') THEN
            RAISE EXCEPTION 'release review denied' USING ERRCODE='42501'; END IF;
        END IF;
        RETURN NEW; END $$''')
    schema_editor.execute('REVOKE ALL ON FUNCTION sb_guard_release_update() FROM PUBLIC')
    schema_editor.execute('CREATE TRIGGER publishing_release_guard BEFORE UPDATE ON knowledge_libraryrelease FOR EACH ROW EXECUTE FUNCTION sb_guard_release_update()')


def disable_access(apps, schema_editor):
    """apps/schema_editor为回退上下文；先撤写权限，撤策略后保留旧共享SELECT与grant owner RLS。"""
    runtime, _ = roles(schema_editor)
    tables = ('knowledge_librarycollection', 'knowledge_libraryrelease', 'knowledge_rightsrecord',
        'knowledge_releasebook', 'knowledge_releasecard', 'knowledge_releaseevidence', 'knowledge_librarygrant')
    for table in tables:
        schema_editor.execute(f'REVOKE INSERT, UPDATE, DELETE ON TABLE {table} FROM {runtime}')
        schema_editor.execute(f'DROP POLICY IF EXISTS publishing_insert ON {table}')
        schema_editor.execute(f'DROP POLICY IF EXISTS publishing_update ON {table}')
        if table == 'knowledge_librarygrant':
            schema_editor.execute(f'DROP POLICY publishing_grant_read ON {table}')
        else:
            schema_editor.execute(f'DROP POLICY publishing_shared_read ON {table}')
            schema_editor.execute(f'DROP POLICY publishing_migrator ON {table}')
            schema_editor.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
            schema_editor.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')
    for table in ('publishing_importjob', 'publishing_adminmutation', 'publishing_registeredsource'):
        schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
        if table != 'publishing_registeredsource':
            schema_editor.execute(f'DROP POLICY publishing_owner ON {table}')
            schema_editor.execute(f'DROP POLICY publishing_migrator ON {table}')
            schema_editor.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
            schema_editor.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')
    schema_editor.execute('DROP TRIGGER publishing_release_guard ON knowledge_libraryrelease')
    schema_editor.execute('DROP FUNCTION sb_guard_release_update()')
    schema_editor.execute('DROP FUNCTION sb_admin_permission(text)')


class Migration(migrations.Migration):
    dependencies = [('publishing', '0001_initial'), ('knowledge', '0002_database_access'),
        ('administration', '0003_remove_adminaudit_admin_audit_action_valid_and_more')]
    operations = [migrations.RunPython(enable_access, disable_access)]
