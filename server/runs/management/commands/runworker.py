"""本机任务worker，默认循环；一次执行便于运维检查，不生成伪任务。"""
import threading
from uuid import UUID
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from accounts.models import User
from runs.worker import process_one
from publishing.import_worker import process_one as process_import
from operations.export_worker import process_one as process_export
from accounts.reset_worker import process_one as process_reset


class Command(BaseCommand):
    """运行角色按owner短事务处理任务，不持有迁移或绕过RLS的权限。"""
    help = '执行本项目后台任务；使用项目显式模型配置、运行额度和逐调用账本'

    def add_arguments(self, parser):
        """parser为Django参数解析器；owner只供可信本机运维定位，不是API权限参数。"""
        parser.add_argument('--once',action='store_true')
        parser.add_argument('--owner',type=UUID)
        parser.add_argument('--poll-seconds',type=float,default=1)

    def handle(self, *args, **options):
        """args/options为本机命令输入；禁用模式也会正常结束已入队任务而非挂起。"""
        interval = options['poll_seconds']
        if not 0.2<=interval<=30:
            raise CommandError('poll-seconds必须在0.2至30之间')
        try:
            while True:
                close_old_connections()
                handled, after = False, None
                while True:
                    users = User.objects.order_by('id')
                    if options['owner']:
                        users = users.filter(pk=options['owner'])
                    if after:
                        users = users.filter(pk__gt=after)
                    owners = list(users.values_list('id',flat=True)[:100])
                    if not owners:
                        break
                    for owner in owners:
                        if process_reset(owner) or process_import(owner) or process_export(owner) or process_one(owner):
                            handled = True
                            if options['once']:
                                self.stdout.write('已处理1个任务；结果以任务状态为准。')
                                return
                    after = owners[-1]
                if options['once']:
                    self.stdout.write('当前没有可执行任务。')
                    return
                if not handled:
                    threading.Event().wait(interval)
        except KeyboardInterrupt:
            self.stdout.write('worker已停止。')
