"""运行角色的事务局部身份；身份应由已认证服务端调用者提供。"""
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

from django.db import connection, transaction

_active_owner = ContextVar('sb_active_owner', default=None)


@contextmanager
def owner_transaction(owner_id):
    """owner_id必须来自已核验session，而不是用户可写请求字段。"""
    if not isinstance(owner_id, (str, UUID)):
        raise ValueError('缺少有效用户身份')
    try:
        owner = str(UUID(str(owner_id)))
    except (ValueError, AttributeError):
        raise ValueError('缺少有效用户身份') from None
    active = _active_owner.get()
    if active is not None:
        if active != owner or not connection.in_atomic_block:
            raise ValueError('禁止在授权事务中切换身份')
        yield
        return
    if connection.in_atomic_block or not connection.get_autocommit():
        raise ValueError('授权上下文必须拥有最外层短事务')
    token = _active_owner.set(owner)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('sb.owner_id', %s, true)", [owner])
            yield
    finally:
        _active_owner.reset(token)
