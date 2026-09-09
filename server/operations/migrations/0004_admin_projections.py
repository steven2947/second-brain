"""额度最小管理策略与仅返回分类数量的函数；不开放任务或反馈正文跨租户SELECT。"""
from importlib import import_module
from django.db import migrations


def enable(apps, schema_editor):
    """apps/schema_editor为独立迁移上下文；函数只有固定聚合，无用户SQL或目标owner参数。"""
    runtime, _ = import_module('publishing.migrations.0002_controlled_database_access').roles(schema_editor)
    predicate = """sb_admin_permission('quota_manage')
        AND period=date_trunc('month', CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date
        AND EXISTS (SELECT 1 FROM accounts_user u
        WHERE u.id=owner_id AND NOT u.is_staff AND NOT u.is_superuser AND u.status IN ('active','disabled'))"""
    schema_editor.execute(f'CREATE POLICY quota_admin_read ON operations_quotabucket FOR SELECT TO {runtime} USING ({predicate})')
    schema_editor.execute(f'CREATE POLICY quota_admin_insert ON operations_quotabucket FOR INSERT TO {runtime} WITH CHECK ({predicate})')
    schema_editor.execute(f'CREATE POLICY quota_admin_update ON operations_quotabucket FOR UPDATE TO {runtime} USING ({predicate}) WITH CHECK ({predicate})')
    schema_editor.execute('''CREATE FUNCTION sb_guard_admin_quota() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,pg_temp AS $$ BEGIN
        IF current_user=pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid=TG_RELID)) THEN RETURN NEW; END IF;
        IF NEW.owner_id::text=nullif(current_setting('sb.owner_id',true),'')
          AND (TG_OP='INSERT' OR OLD.owner_id=NEW.owner_id) THEN RETURN NEW; END IF;
        IF NOT public.sb_admin_permission('quota_manage') THEN
          RAISE EXCEPTION 'quota operation denied' USING ERRCODE='42501'; END IF;
        IF TG_OP='INSERT' THEN
          IF NEW.reserved_runs<>0 OR NEW.settled_runs<>0 OR NEW.revision<>1 THEN
            RAISE EXCEPTION 'quota creation denied' USING ERRCODE='42501'; END IF;
        ELSIF (to_jsonb(NEW)-ARRAY['limit_runs','revision','updated_at']) IS DISTINCT FROM
              (to_jsonb(OLD)-ARRAY['limit_runs','revision','updated_at']) OR NEW.revision<>OLD.revision+1 THEN
          RAISE EXCEPTION 'quota update denied' USING ERRCODE='42501'; END IF;
        RETURN NEW; END $$''')
    schema_editor.execute('REVOKE ALL ON FUNCTION sb_guard_admin_quota() FROM PUBLIC')
    schema_editor.execute('CREATE TRIGGER operations_admin_quota_guard BEFORE INSERT OR UPDATE ON operations_quotabucket FOR EACH ROW EXECUTE FUNCTION sb_guard_admin_quota()')
    for name, permission, query in (
        ('sb_admin_run_counts', 'operations_view', """SELECT j.status::text, count(*)::bigint FROM public.runs_job j
            WHERE j.created_at >= date_trunc('month', CURRENT_TIMESTAMP AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
              AND j.created_at < (date_trunc('month', CURRENT_TIMESTAMP AT TIME ZONE 'UTC') + interval '1 month') AT TIME ZONE 'UTC'
            GROUP BY j.status ORDER BY j.status"""),
        ('sb_admin_feedback_counts', 'feedback_review',
         'SELECT f.category::text, count(*)::bigint FROM public.personal_feedback f GROUP BY f.category ORDER BY f.category')):
        schema_editor.execute(f'''CREATE FUNCTION {name}() RETURNS TABLE(label text, count bigint)
            LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$ BEGIN
            IF NOT public.sb_admin_permission('{permission}') THEN
              RAISE EXCEPTION 'aggregate denied' USING ERRCODE='42501'; END IF;
            RETURN QUERY {query}; END $$''')
        schema_editor.execute(f'REVOKE ALL ON FUNCTION {name}() FROM PUBLIC')
        schema_editor.execute(f'GRANT EXECUTE ON FUNCTION {name}() TO {runtime}')


def disable(apps, schema_editor):
    """apps/schema_editor为回退上下文；移除管理函数和策略，保留原owner策略。"""
    for name in ('sb_admin_run_counts', 'sb_admin_feedback_counts'):
        schema_editor.execute(f'DROP FUNCTION {name}()')
    schema_editor.execute('DROP TRIGGER operations_admin_quota_guard ON operations_quotabucket')
    schema_editor.execute('DROP FUNCTION sb_guard_admin_quota()')
    for name in ('quota_admin_read', 'quota_admin_insert', 'quota_admin_update'):
        schema_editor.execute(f'DROP POLICY {name} ON operations_quotabucket')


class Migration(migrations.Migration):
    dependencies = [('operations', '0003_remove_usageentry_usage_purpose_valid_and_more'),
        ('publishing', '0002_controlled_database_access'), ('administration', '0004_operations_audit'),
        ('personal', '0002_database_access'), ('runs', '0004_remove_analysisrun_run_kind_valid_and_more')]
    operations = [migrations.RunPython(enable, disable)]
