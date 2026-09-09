"""隐私HTTP入口维持普通本人会话、CSRF、限流和严格白名单。"""
from django.contrib.auth import logout
from django.http import HttpResponse, JsonResponse
from accounts.services import require_user, throttle
from accounts.serializers import EmptySerializer
from problems.http import problem_endpoint, read_problem_input, read_problem_query
from problems.serializers import ProblemSerializer
from knowledge.serializers import PageQuerySerializer
from . import privacy
from .serializers import (ExportRequestSerializer, PersonalExportSerializer, PersonalExportPageSerializer,
    PrivacyRevisionSerializer, TrashPageSerializer, AccountDeletionRequestSerializer, AccountDeletionSerializer)


@problem_endpoint({'GET', 'POST'}, input_serializer=ExportRequestSerializer)
def exports(request):
    """request为本人分页或带密码/幂等键的新导出请求。"""
    user = require_user(request)
    if request.method == 'GET':
        query = read_problem_query(request.GET, PageQuerySerializer)
        return JsonResponse(PersonalExportPageSerializer(privacy.list_exports(user, query)).data)
    read_problem_query(request.GET, EmptySerializer)
    data = read_problem_input(request, ExportRequestSerializer)
    throttle(user.email, request.META.get('REMOTE_ADDR', 'unknown'), 'privacy-export')
    return JsonResponse(PersonalExportSerializer(privacy.request_export(user, data,
        request.headers.get('Idempotency-Key', ''))).data, status=202)


@problem_endpoint({'GET'}, input_serializer=EmptySerializer)
def export_detail(request, export_id):
    """request/export_id为本人任务状态读取。"""
    user = require_user(request)
    read_problem_query(request.GET, EmptySerializer)
    return JsonResponse(PersonalExportSerializer(privacy.get_export(user, export_id)).data)


@problem_endpoint({'GET'}, input_serializer=EmptySerializer)
def export_download(request, export_id):
    """request/export_id为一次受控下载，永不返回永久公开URL。"""
    from .export_worker import download
    user = require_user(request)
    read_problem_query(request.GET, EmptySerializer)
    return HttpResponse(download(user, export_id), content_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="personal-export-{export_id}.json"',
            'X-Content-Type-Options': 'nosniff'})


@problem_endpoint({'GET'}, input_serializer=EmptySerializer)
def trash(request):
    """request为本人回收站元数据分页。"""
    user = require_user(request)
    query = read_problem_query(request.GET, PageQuerySerializer)
    return JsonResponse(TrashPageSerializer(privacy.list_trash(user, query)).data)


def problem_mutation(request, problem_id, *, restore=False):
    """request/problem_id为已登录修改；restore控制恢复或删除且统一冲突格式。"""
    user = require_user(request)
    read_problem_query(request.GET, EmptySerializer)
    data = read_problem_input(request, PrivacyRevisionSerializer)
    try:
        if restore:
            result = privacy.restore_problem(user, problem_id, data['expected_revision'])
            return JsonResponse(ProblemSerializer(result).data)
        privacy.delete_problem(user, problem_id, data['expected_revision'])
        return HttpResponse(status=204)
    except privacy.ProblemError as error:
        if error.code != 'REVISION_CONFLICT':
            raise
        return JsonResponse({'error': {'code': error.code, 'message': error.message,
            'request_id': request.account_request_id, 'current_revision': error.current_revision}}, status=409)


@problem_endpoint({'POST'}, input_serializer=PrivacyRevisionSerializer)
def restore(request, problem_id):
    """request/problem_id为本人30天内恢复请求。"""
    return problem_mutation(request, problem_id, restore=True)


@problem_endpoint({'POST'}, input_serializer=AccountDeletionRequestSerializer)
def deletion(request):
    """request为本人密码和确认文案；成功立即销毁当前会话。"""
    user = require_user(request)
    read_problem_query(request.GET, EmptySerializer)
    data = read_problem_input(request, AccountDeletionRequestSerializer)
    throttle(user.email, request.META.get('REMOTE_ADDR', 'unknown'), 'privacy-deletion')
    result = privacy.request_deletion(user, data)
    logout(request)
    return JsonResponse(AccountDeletionSerializer(result).data, status=202)


exports.query_serializer = PageQuerySerializer
exports.response_serializers = {'GET': PersonalExportPageSerializer, 'POST': PersonalExportSerializer}
export_detail.query_serializer = EmptySerializer
export_detail.response_serializers = {'GET': PersonalExportSerializer}
export_download.query_serializer = EmptySerializer
export_download.response_serializers = {'GET': None}
trash.query_serializer = PageQuerySerializer
trash.response_serializers = {'GET': TrashPageSerializer}
restore.response_serializers = {'POST': ProblemSerializer}
deletion.response_serializers = {'POST': AccountDeletionSerializer}
