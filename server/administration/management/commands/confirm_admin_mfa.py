"""仅本机继续确认已准备的管理员设备。"""
import getpass
import sys
from django.core.management.base import BaseCommand, CommandError
from administration.bootstrap import confirm_administrator
from accounts.models import User
from administration.models import AdministratorDevice


class Command(BaseCommand):
    """中断初始化后的受控本机续接，不重置或覆盖已有凭据。"""
    help = '继续确认管理员设备；必须在本机 TTY 显式使用迁移配置'

    def handle(self, *args, **options):
        """仅 TTY 收取邮箱和隐藏验证码，成功后启用既定角色。"""
        if options.get('settings') != 'config.settings.migrate' or not sys.stdin.isatty() or not sys.stdout.isatty():
            raise CommandError('必须在本机 TTY 显式使用迁移配置')
        email = input('管理员邮箱：').strip()
        token = getpass.getpass('当前六位验证码：')
        try:
            if not confirm_administrator(email, token):
                raise CommandError('验证码无效或需要稍后重试；设备仍未启用')
        except (ValueError, User.DoesNotExist, AdministratorDevice.DoesNotExist):
            raise CommandError('管理员或设备不可确认') from None
        self.stdout.write('设备已确认；已启用指定角色。')
