"""本机有界隐私维护；显式独立迁移配置，不提升API或普通worker权限。"""
from uuid import UUID
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone
from operations.maintenance import require_manager, maintain_owner


class Command(BaseCommand):
    help = '按明确owner或有界账号分页执行到期隐私维护；部署应至少每日执行并遍历全部页'

    def add_arguments(self, parser):
        """parser为本机参数；after-owner续扫下一页，replay用于恢复后删除清单重放。"""
        parser.add_argument('--owner', type=UUID)
        parser.add_argument('--after-owner', type=UUID)
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--replay-deletions', action='store_true')

    def handle(self, *args, **options):
        """args/options为可信本机输入；身份验证在任何清理之前，错误不输出秘密。"""
        if not 1 <= options['limit'] <= 1000 or (options['owner'] and options['after_owner']):
            raise CommandError('limit必须1至1000，owner不能与after-owner并用')
        connection.ensure_connection()
        db = connection.connection
        try:
            require_manager(db)
            parameters, where = [], 'WHERE is_staff=false AND is_superuser=false'
            if options['owner']:
                where += ' AND id=%s'
                parameters.append(options['owner'])
            if options['after_owner']:
                where += ' AND id>%s'
                parameters.append(options['after_owner'])
            owners = [row[0] for row in db.execute(f'SELECT id FROM accounts_user {where} ORDER BY id LIMIT %s',
                [*parameters, options['limit'] + 1]).fetchall()]
            totals = {'account_purged': 0, 'problems_purged': 0, 'files_removed': 0}
            for owner in owners[:options['limit']]:
                result = maintain_owner(db, owner, replay=options['replay_deletions'])
                for key in totals:
                    totals[key] += int(result[key])
            db.execute('DELETE FROM operations_retainedusage WHERE expires_at<=%s', [timezone.now()])
            self.stdout.write(f'已检查{min(len(owners), options["limit"])}个账号；清除账号{totals["account_purged"]}，问题{totals["problems_purged"]}，文件{totals["files_removed"]}。')
            if len(owners) > options['limit']:
                self.stdout.write('下一页：--after-owner ' + str(owners[options['limit'] - 1]))
        except (ValueError, OSError) as error:
            raise CommandError('隐私维护未完成，请检查独立迁移配置、私有目录与删除清单') from None
