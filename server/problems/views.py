"""问题HTTP只接收本人输入，建档不调用模型或创建伪运行。"""
from django.http import JsonResponse

from accounts.services import require_user
from .http import problem_endpoint, read_problem_input, read_problem_query
from .serializers import (CreateProblemSerializer, UpdateProblemSerializer,
    ProblemQuerySerializer, ProblemDetailQuerySerializer, ProblemSerializer, ProblemPageSerializer)


@problem_endpoint({'GET', 'POST'}, input_serializer=CreateProblemSerializer)
def collection(request):
    """request为列表或创建请求；会话必须先于输入解析和服务访问。"""
    user = require_user(request)
    from . import services
    if request.method == 'GET':
        query = read_problem_query(request.GET, ProblemQuerySerializer)
        return JsonResponse(ProblemPageSerializer(services.list_drafts(user, query)).data)
    read_problem_query(request.GET, ProblemDetailQuerySerializer)
    data = read_problem_input(request, CreateProblemSerializer)
    result = services.create_draft(user, data, request.headers.get('Idempotency-Key', ''))
    return JsonResponse(ProblemSerializer(result).data, status=201)


@problem_endpoint({'GET', 'PATCH', 'DELETE'}, input_serializer=UpdateProblemSerializer)
def detail(request, problem_id):
    """request为本人读取/修改；problem_id来自UUID路由，不能换owner或原问题。"""
    user = require_user(request)
    if request.method == 'DELETE':
        from operations.views import problem_mutation
        return problem_mutation(request, problem_id)
    from . import services
    read_problem_query(request.GET, ProblemDetailQuerySerializer)
    if request.method == 'GET':
        result = services.get_draft(user, problem_id)
    else:
        data = read_problem_input(request, UpdateProblemSerializer)
        try:
            result = services.update_draft(user, problem_id, data)
        except services.ProblemError as error:
            if error.code != 'REVISION_CONFLICT':
                raise
            return JsonResponse({'error': {'code': 'REVISION_CONFLICT',
                'message': '档案已更新，请重载后发送。', 'request_id': request.account_request_id,
                'current_revision': error.current_revision}}, status=409)
    return JsonResponse(ProblemSerializer(result).data)


# 真实serializer绑定供生成契约读取，不复制另一套HTTP字段。
collection.query_serializer = ProblemQuerySerializer
collection.response_serializers = {'GET': ProblemPageSerializer, 'POST': ProblemSerializer}
detail.query_serializer = ProblemDetailQuerySerializer
detail.response_serializers = {'GET': ProblemSerializer, 'PATCH': ProblemSerializer, 'DELETE': None}
from operations.serializers import PrivacyRevisionSerializer
detail.input_serializers = {'DELETE': PrivacyRevisionSerializer}
