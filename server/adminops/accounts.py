"""普通账号状态与本UTC月次数额度；与正常消费共享账号锁。"""
from datetime import timezone as utc_timezone
from django.conf import settings
from django.utils import timezone
from accounts.models import User
from accounts.services import AccountError
from administration.models import AdminAudit
from operations.models import QuotaBucket
from publishing.services import mutate
from publishing.serializers import AdminUserSerializer


def failure(code, status=409):
    """code/status为固定公开错误；不携带数据库或用户业务内容。"""
    return AccountError(code, '后台运营操作未完成', status)


def target_user(identifier, lock=False):
    """identifier为明确目标UUID；只允许普通非删除待办账号，lock用于短写事务。"""
    query = User.objects.filter(is_staff=False, is_superuser=False, status__in=['active', 'disabled'])
    user = (query.select_for_update() if lock else query).filter(pk=identifier).first()
    if user is None:
        raise failure('NOT_FOUND', 404)
    return user


def period():
    """无参数；采用UTC自然月，独立于管理员或目标账号时区。"""
    return timezone.now().astimezone(utc_timezone.utc).date().replace(day=1)


def audit(actor, action, target, request, reason=''):
    """actor/action/target为审计身份动作和UUID；reason为必填状态变更依据。"""
    AdminAudit.objects.create(actor_id=actor.pk, action=action, target_id=target,
        request_id=request.account_request_id, reason=reason)


def change_status(request, identifier, data):
    """request/identifier/data为已验证管理员、普通账号和CAS输入；触发器撤销旧会话。"""
    def execute(actor):
        """actor为事务内再次验权管理员；仅更新状态与修改时间。"""
        user = target_user(identifier, True)
        if user.status != data['expected_status']:
            raise failure('STATUS_CONFLICT')
        user.status = data['status']
        user.save(update_fields=['status', 'updated_at'])
        audit(actor, 'accounts.disable' if data['status'] == 'disabled' else 'accounts.enable', user.pk, request, data['reason'])
        return AdminUserSerializer(user).data
    return mutate(request, 'accounts.disable', data, execute)


def quota_payload(user, month, bucket):
    """user/month为目标与UTC月；bucket缺失时仅投影默认值，不创建数据。"""
    return {'owner_id': user.pk, 'period': month.isoformat(),
        'limit_runs': bucket.limit_runs if bucket else getattr(settings, 'SB_MONTHLY_RUN_LIMIT', 100),
        'reserved_runs': bucket.reserved_runs if bucket else 0,
        'settled_runs': bucket.settled_runs if bucket else 0, 'revision': bucket.revision if bucket else 0}


def get_quota(identifier):
    """identifier为目标UUID；调用方持有真实管理员owner上下文。"""
    user, month = target_user(identifier), period()
    return quota_payload(user, month, QuotaBucket.objects.filter(owner=user, period=month).first())


def change_quota(request, identifier, data):
    """request/identifier/data为管理CAS更新；账号锁与reserve_run保持相同串行边界。"""
    def execute(actor):
        """actor为真实管理员；比较最新额度revision并保护实际预留和消费下限。"""
        user, month = target_user(identifier, True), period()
        if data['expected_period'] != month.isoformat():
            raise failure('REVISION_CONFLICT')
        bucket = QuotaBucket.objects.select_for_update().filter(owner=user, period=month).first()
        if (bucket.revision if bucket else 0) != data['expected_revision']:
            raise failure('REVISION_CONFLICT')
        if bucket and data['limit_runs'] < bucket.reserved_runs + bucket.settled_runs:
            raise failure('QUOTA_BELOW_USAGE')
        if bucket is None:
            bucket = QuotaBucket.objects.create(owner=user, period=month, limit_runs=data['limit_runs'], revision=1)
        else:
            bucket.limit_runs = data['limit_runs']
            bucket.revision += 1
            bucket.save(update_fields=['limit_runs', 'revision', 'updated_at'])
        audit(actor, 'quota.manage', user.pk, request)
        return quota_payload(user, month, bucket)
    return mutate(request, 'quota.manage', data, execute)
