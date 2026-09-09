"""冷静期取消仅通过本人密码和真实TTY本机支持核验。"""
import getpass
import sys
from uuid import UUID
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from operations.maintenance import require_manager, cancel_deletion


class Command(BaseCommand):
    help = '本机支持取消七天冷静期删除；必须TTY核验目标、原因及本人密码，不恢复旧会话或grant'

    def add_arguments(self, parser):
        """parser为本机参数；密码不能通过命令参数、环境或日志传递。"""
        parser.add_argument('--owner', type=UUID, required=True)
        parser.add_argument('--reason', required=True)

    def handle(self, *args, **options):
        """args/options为本机目标与原因；只在真实TTY读取本人密码和确认目标。"""
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise CommandError('支持取消必须在本机真实TTY中核验')
        connection.ensure_connection()
        db = connection.connection
        try:
            require_manager(db)
            self.stdout.write(f'待核验账号：{options["owner"]}；支持原因：{options["reason"]}')
            if input('输入完整账号UUID确认目标：').strip() != str(options['owner']):
                raise ValueError('确认目标不匹配')
            password = getpass.getpass('请本人输入当前密码：')
            cancel_deletion(db, options['owner'], password, options['reason'])
            self.stdout.write('已取消删除；请本人重新登录，知识授权需管理员重新授予。')
        except (ValueError, OSError):
            raise CommandError('取消失败：核验不通过、冷静期已过或配置不可用') from None
