"""任务HTTP只接线已保存消息与真实队列，不同步伪造模型输出。"""
from django.http import JsonResponse
from accounts.services import require_user
from accounts.serializers import EmptySerializer
from knowledge.serializers import PageQuerySerializer
from problems.http import problem_endpoint, read_problem_input, read_problem_query
from problems.serializers import ProblemDetailQuerySerializer
from problems.services import ProblemError
from .serializers import (SendMessageSerializer, AnalyzeSerializer, AcceptedRunSerializer,
                          MessagePageSerializer, JobSerializer, RunSerializer)


def _write(request, operation, *args):
    """request供公开追踪ID；operation/args是已验证的服务调用，冲突仅附本人修订。"""
    try:
        result = operation(*args)
    except ProblemError as error:
        if error.code != 'REVISION_CONFLICT':
            raise
        return JsonResponse({'error': {'code': error.code,
            'message': '档案已更新，请重载后发送。', 'request_id': request.account_request_id,
            'current_revision': error.current_revision}}, status=409)
    return JsonResponse(AcceptedRunSerializer(result).data, status=202)


@problem_endpoint({'GET','POST'}, input_serializer=SendMessageSerializer)
def messages(request, problem_id):
    """request/problem_id为本人消息入口；身份先于输入解析与消息查询。"""
    user = require_user(request)
    from . import services
    if request.method == 'GET':
        query = read_problem_query(request.GET, PageQuerySerializer)
        return JsonResponse(MessagePageSerializer(services.list_messages(user, problem_id, query)).data)
    read_problem_query(request.GET, ProblemDetailQuerySerializer)
    data = read_problem_input(request, SendMessageSerializer)
    return _write(request, services.send_message, user, problem_id, data,
                  request.headers.get('Idempotency-Key', ''))


@problem_endpoint({'POST'}, input_serializer=AnalyzeSerializer)
def analyze(request, problem_id):
    """request/problem_id为明确直接分析按钮，不由模型覆盖停止追问意图。"""
    user = require_user(request)
    from . import services
    read_problem_query(request.GET, ProblemDetailQuerySerializer)
    data = read_problem_input(request, AnalyzeSerializer)
    return _write(request, services.start_analysis, user, problem_id, data,
                  request.headers.get('Idempotency-Key', ''))


@problem_endpoint({'GET'}, input_serializer=None)
def run_detail(request, run_id):
    """request/run_id为公开运行查询，私有输入与供应商原响应不可见。"""
    user = require_user(request)
    from . import services
    read_problem_query(request.GET, ProblemDetailQuerySerializer)
    return JsonResponse(RunSerializer(services.get_run(user, run_id)).data)


@problem_endpoint({'GET'}, input_serializer=None)
def job_detail(request, job_id):
    """request/job_id为当前任务状态，只由后端状态机决定。"""
    user = require_user(request)
    from . import services
    read_problem_query(request.GET, ProblemDetailQuerySerializer)
    return JsonResponse(JobSerializer(services.get_job(user, job_id)).data)


@problem_endpoint({'POST'}, input_serializer=EmptySerializer)
def cancel(request, job_id):
    """request/job_id为取消当前任务，终态保留已发生结果，不声称取消免计费。"""
    user = require_user(request)
    from . import services
    read_problem_query(request.GET, ProblemDetailQuerySerializer)
    if request.body:
        read_problem_input(request, EmptySerializer)
    result, status = services.cancel_job(user, job_id)
    return JsonResponse(JobSerializer(result).data, status=status)


messages.query_serializer = PageQuerySerializer
messages.response_serializers = {'GET': MessagePageSerializer, 'POST': AcceptedRunSerializer}
analyze.response_serializers = {'POST': AcceptedRunSerializer}
run_detail.query_serializer = job_detail.query_serializer = ProblemDetailQuerySerializer
run_detail.response_serializers = {'GET': RunSerializer}
job_detail.response_serializers = {'GET': JobSerializer}
cancel.response_serializers = {'POST': JobSerializer}
