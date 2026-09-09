"""只接受 TTY 交互，秘密不进入 argv 或 stdout。"""
import getpass
import sys
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from administration.bootstrap import prepare_administrator, confirm_administrator, require_management_connection
from administration.permissions import ROLES


class Command(BaseCommand):
    """显式迁移配置下的一次本机准备与确认，不生成默认管理员。"""
    help = '本机准备管理员并验证第二因素；必须显式 --settings=config.settings.migrate'

    def add_arguments(self, parser):
        """仅登记私有交付路径；密码和验证码没有命令行参数。"""
        parser.add_argument('--output', required=True, help='本项目私有目录下尚不存在的 0600 凭据文件')

    def handle(self, *args, **options):
        """核对 TTY 与迁移身份，交互收取密码并确认认证器已正确登记。"""
        if options.get('settings') != 'config.settings.migrate' or not sys.stdin.isatty() or not sys.stdout.isatty():
            raise CommandError('必须在本机 TTY 显式使用迁移配置；不支持密码或验证码命令行参数')
        try:
            require_management_connection()
            email = input('管理员邮箱：').strip()
            name = input('显示名称：').strip()
            role = input('角色（' + '/'.join(ROLES) + '）：').strip()
            password = getpass.getpass('新密码：')
            if password != getpass.getpass('重复密码：'):
                raise CommandError('两次密码不一致')
            prepare_administrator(email, name, password, role, options['output'])
            self.stdout.write('未启用的设备与恢复码已保存至指定私有文件。请在本机认证器导入后输入当前验证码。')
            token = getpass.getpass('当前六位验证码：')
            if not confirm_administrator(email, token):
                raise CommandError('验证码未通过；设备仍未启用，稍后可使用 confirm_admin_mfa 继续确认')
            self.stdout.write('管理员初始化完成；已启用第二因素和指定角色。')
        except (ValidationError, ValueError, IntegrityError, OSError):
            raise CommandError('初始化未完成；请核对输入、迁移身份、私有目录权限和文件是否已存在') from None
