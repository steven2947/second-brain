"""本人学习HTTP边界，复用会话、CSRF与固定错误。"""
from django.http import JsonResponse
from accounts.services import require_user
from knowledge.serializers import DetailQuerySerializer, PageQuerySerializer
from problems.http import problem_endpoint, read_problem_input, read_problem_query
from runs.serializers import AcceptedRunSerializer
from . import services
from .serializers import (CreateLearningSerializer, SendLearningMessageSerializer,
    ArchiveLearningSerializer, LearningQuerySerializer, LearningSessionSerializer,
    LearningSessionPageSerializer, LearningDetailSerializer, LearningJobSerializer)


@problem_endpoint({'GET', 'POST'}, input_serializer=CreateLearningSerializer)
def collection(request):
    """request为创建或本人分页；创建需要幂等头，不触发模型。"""
    user = require_user(request)
    if request.method == 'GET':
        result = services.list_sessions(user, read_problem_query(request.GET, LearningQuerySerializer))
        return JsonResponse(LearningSessionPageSerializer(result).data)
    read_problem_query(request.GET, DetailQuerySerializer)
    result = services.create_session(user, read_problem_input(request, CreateLearningSerializer),
                                     request.headers.get('Idempotency-Key'))
    return JsonResponse(LearningSessionSerializer(result).data, status=201)


@problem_endpoint({'GET'}, input_serializer=None)
def detail(request, session_id):
    """request/session_id为本人详情与签名回合分页，失权返回404。"""
    result = services.get_detail(require_user(request), session_id,
                                read_problem_query(request.GET, PageQuerySerializer))
    return JsonResponse(LearningDetailSerializer(result).data)


@problem_endpoint({'POST'}, input_serializer=SendLearningMessageSerializer)
def messages(request, session_id):
    """request/session_id为本人显式学习消息，返回真实已入队任务。"""
    read_problem_query(request.GET, DetailQuerySerializer)
    result = services.send_message(require_user(request), session_id,
        read_problem_input(request, SendLearningMessageSerializer), request.headers.get('Idempotency-Key'))
    return JsonResponse(AcceptedRunSerializer(result).data, status=202)


@problem_endpoint({'POST'}, input_serializer=ArchiveLearningSerializer)
def archive(request, session_id):
    """request/session_id为本人会话的乐观锁归档。"""
    read_problem_query(request.GET, DetailQuerySerializer)
    result = services.archive_session(require_user(request), session_id,
                                       read_problem_input(request, ArchiveLearningSerializer))
    return JsonResponse(LearningSessionSerializer(result).data)


@problem_endpoint({'GET'}, input_serializer=None)
def job_detail(request, session_id, job_id):
    """request/session_id/job_id共同绑定本人学习任务。"""
    read_problem_query(request.GET, DetailQuerySerializer)
    return JsonResponse(LearningJobSerializer(services.get_job(require_user(request), session_id, job_id)).data)


@problem_endpoint({'POST'}, input_serializer=DetailQuerySerializer)
def cancel(request, session_id, job_id):
    """request/session_id/job_id为本人指定任务的取消操作。"""
    read_problem_query(request.GET, DetailQuerySerializer)
    if request.body:
        read_problem_input(request, DetailQuerySerializer)
    result, status = services.get_job(require_user(request), session_id, job_id, cancel=True)
    return JsonResponse(LearningJobSerializer(result).data, status=status)


collection.query_serializer = LearningQuerySerializer
collection.response_serializers = {'GET': LearningSessionPageSerializer, 'POST': LearningSessionSerializer}
detail.query_serializer = PageQuerySerializer
detail.response_serializers = {'GET': LearningDetailSerializer}
messages.response_serializers = {'POST': AcceptedRunSerializer}
archive.response_serializers = {'POST': LearningSessionSerializer}
job_detail.query_serializer = DetailQuerySerializer
job_detail.response_serializers = {'GET': LearningJobSerializer}
cancel.response_serializers = {'POST': LearningJobSerializer}
