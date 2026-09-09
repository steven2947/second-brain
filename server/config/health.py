"""匿名健康检查仅公开最小状态，绝不返回基础设施信息。"""

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def live(request):
    """request 为 HTTP 请求；进程存活不依赖数据库、模型或书库。"""
    return JsonResponse({"status": "ok"}, headers={"Cache-Control": "no-store"})


@require_safe
def ready(request):
    """request 为 HTTP 请求；用只读查询检查数据库，失败只返回 503 状态。"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            available = cursor.fetchone() == (1,)
    except DatabaseError:
        available = False
    return JsonResponse(
        {"status": "ok" if available else "unavailable"},
        status=200 if available else 503,
        headers={"Cache-Control": "no-store"},
    )
