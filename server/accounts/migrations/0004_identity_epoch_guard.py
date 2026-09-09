"""仅为accounts_user增加持久身份撤销约束；所有写路径共享同一数据库事实。"""
from django.db import migrations


class Migration(migrations.Migration):
    """身份状态或管理权限变化时推进epoch，普通更新也不能将epoch倒退。"""

    dependencies = [("accounts", "0003_auththrottle_user_deletion_requested_at_user_groups_and_more")]

    operations = [migrations.RunSQL(
        sql="""
        CREATE FUNCTION public.accounts_guard_auth_epoch()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY INVOKER
        SET search_path = pg_catalog
        AS $guard$
        BEGIN
            IF NEW.status IS DISTINCT FROM OLD.status
               OR NEW.is_staff IS DISTINCT FROM OLD.is_staff
               OR NEW.is_superuser IS DISTINCT FROM OLD.is_superuser THEN
                NEW.auth_epoch := GREATEST(NEW.auth_epoch, OLD.auth_epoch + 1);
            ELSE
                NEW.auth_epoch := GREATEST(NEW.auth_epoch, OLD.auth_epoch);
            END IF;
            RETURN NEW;
        END;
        $guard$;
        REVOKE ALL ON FUNCTION public.accounts_guard_auth_epoch() FROM PUBLIC;
        CREATE TRIGGER accounts_identity_epoch_guard
        BEFORE UPDATE ON public.accounts_user
        FOR EACH ROW EXECUTE FUNCTION public.accounts_guard_auth_epoch();
        """,
        reverse_sql="""
        DROP TRIGGER accounts_identity_epoch_guard ON public.accounts_user;
        DROP FUNCTION public.accounts_guard_auth_epoch();
        """,
    )]
