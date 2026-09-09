"""显式迁移配置下只读验证本机固定库并登记源。"""
import re
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.core.management.base import BaseCommand, CommandError
from administration.bootstrap import require_management_connection
from accounts.services import AccountError
from publishing.access import source_fingerprint, source_library
from publishing.models import RegisteredSource


class Command(BaseCommand):
    help = '仅用 --settings=config.settings.migrate 登记已准备的固定知识目录，不蒸馏、不发布'

    def add_arguments(self, parser):
        """parser为本机命令行解析器；登记键与存储键不同，后者永不通过API返回。"""
        parser.add_argument('--staging-key', required=True)
        parser.add_argument('--storage-key', required=True)
        parser.add_argument('--title', required=True)
        parser.add_argument('--description', default='')

    def handle(self, *args, **options):
        """args/options为显式本机输入；禁止runtime登记、覆盖同名源或任意网络内容。"""
        try:
            if options.get('settings') != 'config.settings.migrate':
                raise ValueError
            require_management_connection()
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', options['staging_key']):
                raise ValueError
            digest = source_fingerprint(options['storage_key'])
            source = RegisteredSource(staging_key=options['staging_key'], storage_key=options['storage_key'],
                title=options['title'], description=options['description'], source_fingerprint=digest,
                content_version=digest[:24], book_count=0, card_count=0)
            library = source_library(source)
            source.book_count, source.card_count = len(library.manifest['books']), len(library.cards)
            source.full_clean()
            source.save(force_insert=True)
        except (ValueError, AccountError, ValidationError, IntegrityError, OSError):
            raise CommandError('登记失败：需要独立迁移配置、唯一登记键和受控有效固定库') from None
        self.stdout.write(f'已登记 {source.staging_key}：{source.content_version}；尚未导入或发布。')
