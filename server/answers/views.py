"""真实正式答案只读HTTP入口；认证先于路径对象读取，错误不泄露来源路径。"""
from django.http import JsonResponse
from accounts.services import require_user
from problems.http import problem_endpoint, read_problem_query
from problems.serializers import ProblemDetailQuerySerializer
from .serializers import AnswerSerializer


@problem_endpoint({'GET'}, input_serializer=None)
def detail(request, answer_id):
    """request/answer_id为公开读取；服务端按当前许可重新投影，不使用旧公开缓存。"""
    user = require_user(request)
    read_problem_query(request.GET, ProblemDetailQuerySerializer)
    from .services import get_answer
    return JsonResponse(AnswerSerializer(get_answer(user, answer_id)).data)


detail.query_serializer = ProblemDetailQuerySerializer
detail.response_serializer = AnswerSerializer
