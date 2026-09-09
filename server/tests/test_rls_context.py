"""真实PostgreSQL连接验证事务身份不残留；不以mock证明用户隔离。"""
import uuid

from django.db import connection, transaction
from django.test import SimpleTestCase

from access.context import owner_transaction


class OwnerContextTests(SimpleTestCase):
    """runtime单连接在A/空/B和回滚间切换，仅验证身份接缝，不冒充业务RLS。"""
    databases = {'default'}

    def current_owner(self):
        """无参数；读取当前物理连接的事务局部owner配置。"""
        with connection.cursor() as cursor:
            cursor.execute("SELECT nullif(current_setting('sb.owner_id', true), '')")
            return cursor.fetchone()[0]

    def test_identity_is_transaction_local_on_same_connection(self):
        """无参数；提交清身份，同连接下一个用户不会继承上一个用户。"""
        owner_a, owner_b = uuid.uuid4(), uuid.uuid4()
        self.assertIsNone(self.current_owner())
        physical_connection = connection.connection
        with owner_transaction(owner_a):
            self.assertEqual(self.current_owner(), str(owner_a))
        self.assertIsNone(self.current_owner())
        with owner_transaction(owner_b):
            self.assertEqual(self.current_owner(), str(owner_b))
        self.assertIsNone(self.current_owner())
        self.assertIs(connection.connection, physical_connection)

    def test_rollback_removes_identity(self):
        """无参数；业务异常导致回滚，身份也不能泄漏到后续查询。"""
        with self.assertRaisesRegex(ValueError, 'business failure'):
            with owner_transaction(uuid.uuid4()):
                raise ValueError('business failure')
        self.assertIsNone(self.current_owner())

    def test_same_owner_nested_allowed_but_switch_rejected(self):
        """无参数；复用同一身份可嵌套，不允许服务中途切换其他用户。"""
        owner = uuid.uuid4()
        with owner_transaction(owner):
            with owner_transaction(str(owner)):
                self.assertEqual(self.current_owner(), str(owner))
            with self.assertRaises(ValueError):
                with owner_transaction(uuid.uuid4()):
                    self.fail('不应进入其他身份')
            self.assertEqual(self.current_owner(), str(owner))
        self.assertIsNone(self.current_owner())

    def test_invalid_owner_and_unknown_outer_transaction_fail_closed(self):
        """无参数；身份缺失或外部事务接缝不明确时不创建上下文。"""
        for invalid in (None, '', 'not-a-uuid', 123):
            with self.assertRaises(ValueError):
                with owner_transaction(invalid):
                    self.fail('不应接受无效身份')
        with transaction.atomic():
            with self.assertRaises(ValueError):
                with owner_transaction(uuid.uuid4()):
                    self.fail('不应沿用未声明的外层事务')

    def test_manual_transaction_is_rejected_without_leaking_identity(self):
        """无参数；手动关闭autocommit也算未知外层事务，不能误当顶层atomic。"""
        connection.set_autocommit(False)
        try:
            self.assertFalse(connection.in_atomic_block)
            with self.assertRaises(ValueError):
                with owner_transaction(uuid.uuid4()):
                    self.fail('不应进入手动开启的外层事务')
        finally:
            connection.rollback()
            connection.set_autocommit(True)
        self.assertIsNone(self.current_owner())
        with owner_transaction(uuid.uuid4()):
            self.assertIsNotNone(self.current_owner())
        self.assertIsNone(self.current_owner())
