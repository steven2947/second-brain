"""运营HTTP薄层；所有读取在真实管理员owner内完成，不冒充目标用户。"""
from django.db import connection
from access.context import owner_transaction
from accounts.serializers import EmptySerializer
from administration.services import SESSION_KEY
from publishing.access import current_actor
from publishing.http import endpoint
from publishing.serializers import AdminUserSerializer
from . import accounts, invitations, serializers as s


@endpoint({'POST': (s.AdminStatusInputSerializer, AdminUserSerializer, 200)}, 'accounts.disable')
def status(request, actor, data, user_id):
    """request/actor/data/user_id为真实管理员请求和明确普通账号目标。"""
    return accounts.change_status(request, user_id, data)


@endpoint({'GET': (EmptySerializer, s.AdminQuotaSerializer, 200),
           'PUT': (s.AdminQuotaInputSerializer, s.AdminQuotaSerializer, 200)}, 'quota.manage')
def quota(request, actor, data, user_id):
    """request/actor/data/user_id为额度请求；GET只投影，PUT经过近期MFA和幂等事务。"""
    if request.method == 'PUT':
        return accounts.change_quota(request, user_id, data)
    with owner_transaction(actor.pk):
        state = request.session[SESSION_KEY]
        current_actor(actor.pk, state['device_id'], state['epoch'], 'quota.manage')
        return accounts.get_quota(user_id)


@endpoint({'POST': (s.AdminInvitationInputSerializer, s.AdminInvitationSerializer, 201)}, 'accounts.invite')
def invitation(request, actor, data):
    """request/actor/data为已验证邀请；只返回本机私有投递编号。"""
    return invitations.invite(request, data)


def counts(request, actor, permission, function):
    """request/actor/permission来自服务端授权，function是路由固定的聚合函数名。"""
    with owner_transaction(actor.pk):
        state = request.session[SESSION_KEY]
        current_actor(actor.pk, state['device_id'], state['epoch'], permission)
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM ' + function + '()')
            return cursor.fetchall()


@endpoint({'GET': (EmptySerializer, s.AdminOperationsSerializer, 200)}, 'operations.view')
def operations(request, actor, data):
    """request/actor/data为统计请求；仅返回UTC本月任务分类数量。"""
    rows = counts(request, actor, 'operations.view', 'sb_admin_run_counts')
    return {'period': accounts.period().isoformat(), 'run_counts': [{'status': status, 'count': count} for status, count in rows],
        'total_runs': sum(count for _, count in rows)}


@endpoint({'GET': (EmptySerializer, s.AdminFeedbackSummarySerializer, 200)}, 'feedback.review')
def feedback(request, actor, data):
    """request/actor/data为反馈统计请求；返回历史分类计数，不读comment。"""
    rows = counts(request, actor, 'feedback.review', 'sb_admin_feedback_counts')
    return {'category_counts': [{'category': category, 'count': count} for category, count in rows],
        'total_feedback': sum(count for _, count in rows)}
