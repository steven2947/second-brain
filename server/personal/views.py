"""个人记录HTTP入口复用会话、CSRF、固定错误及严格JSON边界。"""
from django.http import JsonResponse, HttpResponse
from accounts.services import require_user
from knowledge.serializers import DetailQuerySerializer, PageQuerySerializer
from problems.http import problem_endpoint, read_problem_input, read_problem_query
from . import services
from .serializers import (SaveBookmarkSerializer, BookmarkSerializer, BookmarkPageSerializer,
    CreateActionSerializer, UpdateActionSerializer, ActionQuerySerializer, ActionRecordSerializer,
    ActionPageSerializer, CreateFeedbackSerializer, FeedbackSerializer)


@problem_endpoint({'GET'}, input_serializer=None)
def bookmarks(request):
    """request为本人收藏分页读取。"""
    user = require_user(request)
    query = read_problem_query(request.GET, PageQuerySerializer)
    return JsonResponse(BookmarkPageSerializer(services.list_bookmarks(user, query)).data)


@problem_endpoint({'PUT', 'DELETE'}, input_serializer=SaveBookmarkSerializer)
def bookmark(request, release_id, card_id):
    """request为保存或删除；release_id/card_id为真实固定版本卡标识。"""
    user = require_user(request)
    read_problem_query(request.GET, DetailQuerySerializer)
    if request.method == 'DELETE':
        if request.body:
            read_problem_input(request, DetailQuerySerializer)
        services.delete_bookmark(user, release_id, card_id)
        return HttpResponse(status=204)
    data = read_problem_input(request, SaveBookmarkSerializer)
    return JsonResponse(BookmarkSerializer(services.save_bookmark(user, release_id, card_id, data)).data)


@problem_endpoint({'GET', 'POST'}, input_serializer=CreateActionSerializer)
def actions(request):
    """request为本人行动列表或从已发布答案创建行动。"""
    user = require_user(request)
    if request.method == 'GET':
        query = read_problem_query(request.GET, ActionQuerySerializer)
        return JsonResponse(ActionPageSerializer(services.list_actions(user, query)).data)
    read_problem_query(request.GET, DetailQuerySerializer)
    data = read_problem_input(request, CreateActionSerializer)
    return JsonResponse(ActionRecordSerializer(services.create_action(user, data)).data, status=201)


@problem_endpoint({'PATCH'}, input_serializer=UpdateActionSerializer)
def action(request, action_id):
    """request为乐观锁更新；action_id必须属于当前用户。"""
    user = require_user(request)
    read_problem_query(request.GET, DetailQuerySerializer)
    data = read_problem_input(request, UpdateActionSerializer)
    try:
        result = services.update_action(user, action_id, data)
    except services.ProblemError as error:
        if error.code != 'REVISION_CONFLICT':
            raise
        return JsonResponse({'error': {'code': error.code, 'message': error.message,
            'request_id': request.account_request_id, 'current_revision': error.current_revision}}, status=409)
    return JsonResponse(ActionRecordSerializer(result).data)


@problem_endpoint({'POST'}, input_serializer=CreateFeedbackSerializer)
def feedback(request):
    """request为本人答案反馈，不接受学习目标或审核状态。"""
    user = require_user(request)
    read_problem_query(request.GET, DetailQuerySerializer)
    data = read_problem_input(request, CreateFeedbackSerializer)
    return JsonResponse(FeedbackSerializer(services.create_feedback(user, data)).data, status=201)


bookmarks.query_serializer = PageQuerySerializer
bookmarks.response_serializers = {'GET': BookmarkPageSerializer}
bookmark.response_serializers = {'PUT': BookmarkSerializer, 'DELETE': None}
actions.query_serializer = ActionQuerySerializer
actions.response_serializers = {'GET': ActionPageSerializer, 'POST': ActionRecordSerializer}
action.response_serializers = {'PATCH': ActionRecordSerializer}
feedback.response_serializers = {'POST': FeedbackSerializer}
