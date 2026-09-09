"""个人导出与软删除生命周期；身份锁保护再认证、修订和在途任务终结。"""
import hashlib
import json
from datetime import timedelta
from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from access.context import owner_transaction
from accounts.services import AccountError
from problems.models import Problem, IdempotencyRecord
from problems.services import _current_user, _get, _public, _uuid, invalid, not_found, ProblemError
from runs.models import AnalysisRun, Job
from .models import PersonalExport


def digest(value):
    """value为许可或公开数据；稳定摘要避免持久保存完整权限记录。"""
    return hashlib.sha256(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def reauthenticate(current, password):
    """current已持身份锁；password仅在内存中核验，不参与幂等摘要。"""
    if not isinstance(password, str) or not 1 <= len(password) <= 256 or not current.check_password(password):
        raise AccountError('INVALID_CREDENTIALS', '账号或密码不匹配或账号不可用', 401)


def export_public(row):
    """row为本人任务；到期即显示expired，不等待维护任务。"""
    expired = row.expires_at is not None and row.expires_at <= timezone.now()
    return {'id': str(row.pk), 'scope': row.scope, 'status': 'expired' if expired else row.status,
        'created_at': row.created_at, 'expires_at': row.expires_at, 'error_code': row.error_code}


def request_export(user, data, key):
    """user为会话身份；data为范围与瞬时密码；key绑定范围而非密码。"""
    if (not isinstance(data, dict) or set(data) != {'scope', 'password'}
            or data['scope'] not in ('problems', 'learning', 'all_personal')
            or not isinstance(key, str) or not key.strip() or len(key) > 128):
        raise invalid()
    with owner_transaction(user.pk):
        current = _current_user(user, lock=True)
        reauthenticate(current, data['password'])
        request_hash = digest({'scope': data['scope']})
        record = IdempotencyRecord.objects.filter(owner=current, method='POST',
            route_scope='/api/v1/me/exports', key=key).first()
        if record:
            if record.request_hash != request_hash:
                raise ProblemError('IDEMPOTENCY_CONFLICT', '幂等键已用于其他请求', 409)
            row = PersonalExport.objects.filter(owner=current, pk=record.resource_id).first()
            if row is None:
                raise not_found()
            return export_public(row)
        if PersonalExport.objects.filter(owner=current, status__in=['queued', 'running']).count() >= 3:
            raise ProblemError('EXPORT_LIMIT', '已有导出等待完成，请稍后重试', 429)
        row = PersonalExport.objects.create(owner=current, scope=data['scope'], auth_epoch=current.auth_epoch,
            access_revision=current.access_revision, deadline=timezone.now() + timedelta(minutes=15))
        result = export_public(row)
        IdempotencyRecord.objects.create(owner=current, method='POST', route_scope='/api/v1/me/exports',
            key=key, request_hash=request_hash, status='completed', response_status=202,
            response_payload=json.loads(json.dumps(result, cls=DjangoJSONEncoder)),
            resource_type='export', resource_id=row.pk, expires_at=timezone.now() + timedelta(hours=48))
        return result


def page(rows, query, user, kind):
    """rows为本人查询；query严格页大小，签名游标绑定身份epoch、范围和页大小。"""
    if not isinstance(query, dict) or not set(query) <= {'limit', 'cursor'}:
        raise invalid()
    limit = query.get('limit', 20)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise invalid()
    binding = [str(user.pk), user.auth_epoch, kind, limit]
    field = 'deleted_at' if kind == 'trash' else 'created_at'
    if query.get('cursor'):
        try:
            value = signing.loads(query['cursor'], salt='privacy.page.v1', max_age=900)
            if value['binding'] != binding:
                raise ValueError('binding')
            timestamp = parse_datetime(value['time'])
            if timestamp is None or timezone.is_naive(timestamp):
                raise ValueError('timestamp')
            rows = rows.filter(Q(**{field + '__lt': timestamp}) | Q(**{field: timestamp,
                'id__lt': _uuid(value['id'], invalid)}))
        except (signing.BadSignature, KeyError, TypeError, ValueError):
            raise invalid() from None
    items = list(rows.order_by('-' + field, '-id')[:limit + 1])
    cursor = signing.dumps({'binding': binding, 'id': str(items[limit - 1].pk),
        'time': getattr(items[limit - 1], field).isoformat()},
        salt='privacy.page.v1') if len(items) > limit else None
    return items[:limit], cursor


def list_exports(user, query):
    """user/query为当前身份和页参数，仅列本人元数据。"""
    with owner_transaction(user.pk):
        current = _current_user(user)
        rows, cursor = page(PersonalExport.objects.filter(owner=current), query, current, 'exports')
        return {'items': [export_public(row) for row in rows], 'next_cursor': cursor}


def get_export(user, identifier):
    """user/identifier为当前身份与导出UUID。"""
    with owner_transaction(user.pk):
        current = _current_user(user)
        row = PersonalExport.objects.filter(owner=current, pk=_uuid(identifier, not_found)).first()
        if row is None:
            raise not_found()
        return export_public(row)


def cancel_runs(current, problem=None):
    """current已持锁；problem可限定父域，立即fence旧worker并正确释放或结算额度。"""
    from runs.queue import _terminal
    runs = AnalysisRun.objects.filter(owner=current, job__status__in=['queued', 'running', 'cancel_requested'])
    if problem is not None:
        runs = runs.filter(Q(problem=problem) | Q(learning_session__problem=problem))
    for run in runs.order_by('id'):
        job = Job.objects.select_for_update().get(owner=current, pk=run.job_id)
        _terminal(job, run, 'RUN_CANCELLED', timezone.now())


def revision(row, expected):
    """row为本人行；expected必须为精确非负整数。"""
    if type(expected) is not int or not 0 <= expected <= 9223372036854775806:
        raise invalid()
    if row.revision != expected:
        raise ProblemError('REVISION_CONFLICT', '问题已更新，请刷新后重试', 409, row.revision)


def delete_problem(user, identifier, expected):
    """user/identifier/expected为本人删除请求；授权丢失不阻止删除原始记录。"""
    with owner_transaction(user.pk):
        current = _current_user(user, lock=True)
        row = _get(current, _uuid(identifier, not_found), lock=True)
        revision(row, expected)
        row.status, row.deleted_at, row.revision = 'deleted', timezone.now(), row.revision + 1
        row.save(update_fields=['status', 'deleted_at', 'revision', 'updated_at'])
        cancel_runs(current, row)


def list_trash(user, query):
    """user/query为本人和分页；回收站只暴露元数据，不返回正文。"""
    with owner_transaction(user.pk):
        current = _current_user(user)
        rows, cursor = page(Problem.objects.filter(owner=current, status='deleted'), query, current, 'trash')
        return {'items': [{'id': str(row.pk), 'title': row.title, 'status': row.status,
            'revision': row.revision, 'deleted_at': row.deleted_at,
            'purge_after': row.deleted_at + timedelta(days=30)} for row in rows], 'next_cursor': cursor}


def restore_problem(user, identifier, expected):
    """user/identifier/expected为恢复请求；30天内归档恢复，不授予任何知识权限。"""
    with owner_transaction(user.pk):
        current = _current_user(user, lock=True)
        row = Problem.objects.select_for_update().filter(owner=current,
            pk=_uuid(identifier, not_found), status='deleted').first()
        if row is None:
            raise not_found()
        if row.deleted_at + timedelta(days=30) <= timezone.now():
            raise ProblemError('TRASH_EXPIRED', '恢复期限已过', 410)
        revision(row, expected)
        row.status, row.deleted_at, row.revision = 'archived', None, row.revision + 1
        row.save(update_fields=['status', 'deleted_at', 'revision', 'updated_at'])
        return _public(row, current)


def request_deletion(user, data):
    """user为会话本人，data为密码与固定确认文字；七天后由受控维护清除。"""
    from accounts.password_reset import invalidate_resets
    if not isinstance(data, dict) or set(data) != {'password', 'confirmation'} or data['confirmation'] != '删除我的账号':
        raise invalid()
    with owner_transaction(user.pk):
        current = _current_user(user, lock=True)
        reauthenticate(current, data['password'])
        now = timezone.now()
        current.status, current.deletion_requested_at = 'deletion_pending', now
        current.auth_epoch += 1
        current.access_revision += 1
        current.save(update_fields=['status', 'deletion_requested_at', 'auth_epoch', 'access_revision', 'updated_at'])
        invalidate_resets(current)
        cancel_runs(current)
        PersonalExport.objects.filter(owner=current, status__in=['queued', 'running', 'ready']).update(
            status='expired', expires_at=now, lease_token=None, lease_until=None, error_code='ACCESS_REVOKED')
        return {'id': str(current.pk), 'status': 'pending', 'requested_at': now,
            'purge_after': now + timedelta(days=7)}
