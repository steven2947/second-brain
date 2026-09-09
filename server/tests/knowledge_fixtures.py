"""仅固定测试库的真实授权夹具；迁移连接准备，runtime执行被测查询。"""
import hashlib
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase
from django.utils import timezone

from accounts.models import User
from src.knowledge.library import Library

FIXTURES = Path(__file__).resolve().parent / 'fixtures/product_demo'
TABLES = ('accounts_user', 'knowledge_librarycollection', 'knowledge_libraryrelease',
          'knowledge_librarygrant', 'knowledge_rightsrecord', 'knowledge_releasebook',
          'knowledge_releasecard', 'knowledge_releaseevidence')


def fingerprint(directory):
    """directory为自编固定版本目录；计算每个相对名称与字节的完整指纹。"""
    digest = hashlib.sha256()
    for path in sorted(directory.rglob('*')):
        if path.is_file():
            digest.update(path.relative_to(directory).as_posix().encode() + b'\0')
            digest.update(path.read_bytes() + b'\0')
    return digest.hexdigest()


class KnowledgeFixtureCase(SimpleTestCase):
    """可复用的测试准备，无继承而来的测试方法，避免重复执行数据库迁移套件。"""
    databases = {'default'}

    def setUp(self):
        """无参数；核对连接身份后准备三用户和两套真实自编版本。"""
        self.assertEqual(connection.settings_dict['NAME'], 'test_sb_product')
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database(), current_user')
            self.assertEqual(cursor.fetchone(), ('test_sb_product', 'sb_runtime'))
        self.manager = psycopg.connect(settings.DEV_ENV['SB_MIGRATION_DATABASE_URL'],
                                      dbname='test_sb_product', autocommit=True)
        self.addCleanup(self.manager.close)
        self.assertEqual(self.manager.execute('SELECT current_database(), current_user').fetchone(),
                         ('test_sb_product', 'sb_migrator'))
        self.created = []
        self.addCleanup(self.cleanup_records)
        self.owner_a, self.owner_b, self.owner_c = [self.seed_user() for _ in range(3)]
        self.user_a, self.user_b, self.user_c = [User.objects.get(pk=pk)
            for pk in (self.owner_a, self.owner_b, self.owner_c)]
        self.release_a = self.seed_release('releaseA')
        self.release_b = self.seed_release('releaseB')
        self.grant_a = self.seed_grant(self.owner_a, self.release_a)
        self.grant_b = self.seed_grant(self.owner_b, self.release_b)
        self.right_a = self.seed_rights(self.release_a)
        self.right_b = self.seed_rights(self.release_b)
        self.root_override = self.settings(SB_LIBRARY_ROOT=FIXTURES)
        self.root_override.enable()
        self.addCleanup(self.root_override.disable)

    def insert(self, table, **values):
        """table为固定白名单；values为自编字段，登记每次成功插入的UUID以精确清理。"""
        if table not in TABLES:
            raise ValueError('不在测试表范围')
        identifier, now = uuid.uuid4(), timezone.now()
        values = dict(id=identifier, created_at=now, updated_at=now, **values)
        query = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(sql.Identifier(table),
            sql.SQL(', ').join(map(sql.Identifier, values)),
            sql.SQL(', ').join(sql.Placeholder() for _ in values))
        self.manager.execute(query, list(values.values()))
        self.created.append((table, identifier))
        return identifier

    def change(self, table, identifier, **values):
        """table/identifier必须是本用例创建的目标；values仅用于模拟真实管理变更。"""
        if (table, identifier) not in self.created:
            raise ValueError('非本测试记录')
        query = sql.SQL('UPDATE {} SET {} WHERE id=%s').format(sql.Identifier(table),
            sql.SQL(', ').join(sql.SQL('{}=%s').format(sql.Identifier(key)) for key in values))
        self.manager.execute(query, [*values.values(), identifier])

    def cleanup_records(self):
        """无参数；只在固定测试库按外键反序删除登记UUID。"""
        self.assertEqual(self.manager.execute('SELECT current_database(), current_user').fetchone(),
                         ('test_sb_product', 'sb_migrator'))
        for table, identifier in reversed(self.created):
            self.manager.execute(sql.SQL('DELETE FROM {} WHERE id=%s').format(sql.Identifier(table)), [identifier])

    def seed_user(self):
        """无参数；不可登录自编账号，不伪装真实会话或管理员。"""
        return self.insert('accounts_user', password='!', last_login=None,
            email=f'library-{uuid.uuid4().hex}@example.test', display_name='自编用户',
            status='active', is_staff=False, is_superuser=False, timezone='Asia/Shanghai',
            theme='system', auth_epoch=0, access_revision=0, email_verified_at=None,
            deletion_requested_at=None)

    def seed_release(self, name, *, directory=None):
        """name为测试根内存储键；directory可给另一自编目录，登记真实内容统计与投影。"""
        directory = directory or FIXTURES / name
        library = Library(directory)
        digest, now = fingerprint(directory), timezone.now()
        collection = self.insert('knowledge_librarycollection', title=f'自编{name}',
            description='仅自编集成测试', status='active', scope='demo', curator_id=None)
        release = self.insert('knowledge_libraryrelease', library_id=collection,
            content_version=digest[:24], source_fingerprint=digest, storage_key=name,
            status='published', rights_status='approved', rights_record_key='private/test-review',
            card_count=len(library.cards), book_count=len(library.manifest['books']),
            validated_at=now, published_at=now, metadata=Jsonb({}), metadata_schema_version=1)
        for book in library.manifest['books']:
            self.insert('knowledge_releasebook', release_id=release, core_book_id=book['id'],
                title='旧投影不得当真源', author_display=None, contributor_metadata=Jsonb({}),
                metadata_status='partial', cover_asset_key=None, description='', chapter_summary=Jsonb([]))
        for card in library.cards.values():
            self.insert('knowledge_releasecard', release_id=release, core_card_id=card['id'],
                core_book_id=card['book_id'], card_type=card['kind'], title='旧投影', browse_payload=Jsonb({}))
        for evidence in library.evidence.values():
            self.insert('knowledge_releaseevidence', release_id=release, core_evidence_id=evidence['id'],
                core_book_id=evidence['book_id'], chapter='旧投影', preview_payload=Jsonb({}))
        return release

    def seed_grant(self, owner, release):
        """owner/release为本测试记录；授予整版本reader权限。"""
        return self.insert('knowledge_librarygrant', owner_id=owner, release_id=release,
            role='reader', status='active', expires_at=None, granted_by_id=self.owner_a, revoked_at=None)

    def seed_rights(self, release, **overrides):
        """release为测试版本；overrides用于具体用途、审批或有效期分支。"""
        fields = dict(release_id=release, scope_book_ids=Jsonb([]), source_description='自编测试',
            basis_type='self_authored', license_name=None, proof_storage_key=None,
            allowed_audience='granted_users', allowed_uses=Jsonb(['browse', 'quote']),
            quote_policy=Jsonb({'max_chars': 30}), valid_until=None,
            reviewer_id=self.owner_a, reviewed_at=timezone.now(), status='approved')
        return self.insert('knowledge_rightsrecord', **{**fields, **overrides})
