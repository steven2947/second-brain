"""在固定测试库验证知识数据库边界；管理准备与runtime断言使用不同连接。"""
import uuid
from datetime import timedelta

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from django.conf import settings
from django.db import connection, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import ConnectionHandler
from django.test import SimpleTestCase
from django.utils import timezone

from access.context import owner_transaction
from config.settings.environment import database_settings


TABLES = (
    'knowledge_librarycollection', 'knowledge_libraryrelease', 'knowledge_librarygrant',
    'knowledge_rightsrecord', 'knowledge_releasebook', 'knowledge_releasecard',
    'knowledge_releaseevidence',
)


class KnowledgeMigrationTests(SimpleTestCase):
    """检查真实迁移记录和角色，不把模型注册或syncdb当作迁移验收。"""
    databases = {'default'}

    def test_seven_knowledge_tables_are_migrated_and_owned_by_migrator(self):
        """无参数；测试本体为runtime，七表必须来自可追踪的knowledge迁移。"""
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls FROM pg_roles WHERE rolname=current_user")
            self.assertEqual(cursor.fetchone(), ('test_sb_product', 'sb_runtime', False, False, False, False))
            cursor.execute("SELECT name FROM django_migrations WHERE app='knowledge'")
            self.assertIn('0001_initial', {row[0] for row in cursor.fetchall()})
            cursor.execute("SELECT tablename, tableowner FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'knowledge_%'")
            self.assertEqual(dict(cursor.fetchall()), {
                'knowledge_librarycollection': 'sb_migrator',
                'knowledge_libraryrelease': 'sb_migrator',
                'knowledge_librarygrant': 'sb_migrator',
                'knowledge_rightsrecord': 'sb_migrator',
                'knowledge_releasebook': 'sb_migrator',
                'knowledge_releasecard': 'sb_migrator',
                'knowledge_releaseevidence': 'sb_migrator',
            })


class KnowledgeDatabaseTests(SimpleTestCase):
    """管理连接只准备/清理自编UUID记录；权限断言始终使用默认runtime连接。"""
    databases = {'default'}

    def setUp(self):
        """无参数；双重核验固定库和角色后才启用独立管理连接。"""
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
        self.collection = self.insert('knowledge_librarycollection', title='自编数据库测试',
            description='', status='active', scope='demo', curator_id=None)
        self.release_a = self.seed_release('a')
        self.release_b = self.seed_release('b')
        self.grant_a = self.seed_grant(self.owner_a, self.release_a)
        self.grant_b = self.seed_grant(self.owner_b, self.release_b)

    def insert(self, table, **values):
        """table为固定测试表白名单，values为自编字段；以管理连接插入并登记精确清理ID。"""
        if table not in (*TABLES, 'accounts_user'):
            raise ValueError('测试管理写入表不在范围')
        identifier = uuid.uuid4()
        now = timezone.now()
        values = {'id': identifier, 'created_at': now, 'updated_at': now, **values}
        query = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(sql.Identifier(table),
            sql.SQL(', ').join(map(sql.Identifier, values)),
            sql.SQL(', ').join(sql.Placeholder() for _ in values))
        self.manager.execute(query, list(values.values()))
        self.created.append((table, identifier))
        return identifier

    def cleanup_records(self):
        """无参数；仅删本测试成功创建的UUID记录，按外键反序，不TRUNCATE或清整表。"""
        self.assertEqual(self.manager.execute('SELECT current_database(), current_user').fetchone(),
            ('test_sb_product', 'sb_migrator'))
        for table, identifier in reversed(self.created):
            self.manager.execute(sql.SQL('DELETE FROM {} WHERE id=%s').format(sql.Identifier(table)), [identifier])

    def seed_user(self):
        """无参数；仅创建不可登录的测试账号，不用管理账号代替runtime业务权限。"""
        return self.insert('accounts_user', password='!', last_login=None,
            email=f'knowledge-{uuid.uuid4().hex}@example.test', display_name='自编测试用户',
            status='active', is_staff=False, is_superuser=False, timezone='Asia/Shanghai',
            theme='system', auth_epoch=0, access_revision=0, email_verified_at=None,
            deletion_requested_at=None)

    def seed_release(self, marker, **overrides):
        """marker为固定合法hex标记，overrides用于测试单项数据库约束。"""
        fields = dict(library_id=self.collection, content_version=marker * 24,
            source_fingerprint=marker * 64, storage_key=f'test/{marker}', status='staged',
            rights_status='unreviewed', rights_record_key=None, card_count=0, book_count=0,
            validated_at=None, published_at=None, metadata=Jsonb({}), metadata_schema_version=1)
        return self.insert('knowledge_libraryrelease', **{**fields, **overrides})

    def seed_grant(self, owner, release, **overrides):
        """owner/release为本测试已建ID，overrides用于测试状态；只通过管理连接签发。"""
        fields = dict(owner_id=owner, release_id=release, role='reader', status='active',
            expires_at=None, granted_by_id=self.owner_a, revoked_at=None)
        return self.insert('knowledge_librarygrant', **{**fields, **overrides})

    def visible_grants(self):
        """无参数；runtime直接SQL读取，故意不添加应用owner过滤来验证实际RLS。"""
        with connection.cursor() as cursor:
            cursor.execute('SELECT id FROM knowledge_librarygrant ORDER BY id')
            return {row[0] for row in cursor.fetchall()}

    def seed_book(self, release, core_id='book.self-authored'):
        """release为本测试版本，core_id为自编书ID；不同release允许复用同一核心ID。"""
        return self.insert('knowledge_releasebook', release_id=release, core_book_id=core_id,
            title='自编书目', author_display=None, contributor_metadata=Jsonb({}),
            metadata_status='partial', cover_asset_key=None, description='', chapter_summary=Jsonb([]))

    def seed_projection(self, table, release, core_book_id='book.self-authored'):
        """table仅为卡或证据表，release/core_book_id为被测组合关联。"""
        fields = dict(release_id=release, core_book_id=core_book_id)
        if table == 'knowledge_releasecard':
            fields.update(core_card_id='card.shared-core-id', card_type='method',
                title='自编方法', browse_payload=Jsonb({}))
        elif table == 'knowledge_releaseevidence':
            fields.update(core_evidence_id='evidence.shared-core-id', chapter='自编正文', preview_payload=Jsonb({}))
        else:
            raise ValueError('测试投影表不在范围')
        return self.insert(table, **fields)

    def seed_rights(self, **overrides):
        """overrides为测试审批状态；此管理准备仅自编记录，不构成真实版权审批。"""
        fields = dict(release_id=self.release_a, scope_book_ids=Jsonb([]),
            source_description='仅数据库测试自编记录', basis_type='self_authored',
            license_name=None, proof_storage_key=None, allowed_audience='test-only',
            allowed_uses=Jsonb(['browse']), quote_policy=Jsonb({'max_chars': 50}),
            valid_until=None, reviewer_id=None, reviewed_at=None, status='unreviewed')
        return self.insert('knowledge_rightsrecord', **{**fields, **overrides})

    def test_runtime_grants_are_invisible_without_context_and_owner_scoped(self):
        """无参数；同一物理连接A/空/B/无grant用户切换，跨owner与未知身份均不可见。"""
        physical_connection = connection.connection
        self.assertEqual(self.visible_grants(), set())
        with owner_transaction(self.owner_a):
            self.assertEqual(self.visible_grants(), {self.grant_a})
        self.assertEqual(self.visible_grants(), set())
        with owner_transaction(self.owner_b):
            self.assertEqual(self.visible_grants(), {self.grant_b})
        with owner_transaction(self.owner_c):
            self.assertEqual(self.visible_grants(), set())
        self.assertEqual(self.visible_grants(), set())
        self.assertIs(connection.connection, physical_connection)

    def test_runtime_knowledge_tables_reject_ordinary_owner_writes(self):
        """无参数；显式管理通道有受限DML，普通owner与空上下文仍不可写知识事实。"""
        for table in TABLES:
            with self.subTest(table=table):
                with connection.cursor() as cursor:
                    cursor.execute('SELECT has_table_privilege(current_user, %s, %s)', [table, 'SELECT'])
                    self.assertTrue(cursor.fetchone()[0])
                    for privilege in ('DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                        cursor.execute('SELECT has_table_privilege(current_user, %s, %s)', [table, privilege])
                        self.assertFalse(cursor.fetchone()[0], f'{table} 不得授予 {privilege}')
                statements = (
                    (f'INSERT INTO {table} (id) VALUES (%s)', [uuid.uuid4()]),
                    (f'DELETE FROM {table} WHERE false', []),
                )
                for query, params in statements:
                    with self.subTest(statement=query.split()[0]):
                        with self.assertRaises(DatabaseError) as caught:
                            with owner_transaction(self.owner_a):
                                with connection.cursor() as cursor:
                                    cursor.execute(query, params)
                        self.assertEqual(caught.exception.__cause__.sqlstate, '42501')
                for owner in (None, self.owner_a):
                    if owner is None:
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid=%s::regclass', [table])
                            self.assertEqual(cursor.fetchone(), (True, True))
                    elif table in ('knowledge_libraryrelease', 'knowledge_rightsrecord', 'knowledge_librarygrant'):
                        with owner_transaction(owner), connection.cursor() as cursor:
                            cursor.execute(f'UPDATE {table} SET id=id')
                            self.assertEqual(cursor.rowcount, 0)

    def test_card_and_evidence_database_foreign_keys_reject_cross_release_books(self):
        """无参数；书只在A存在时，不允许B的卡/证据以该书ID建立串接。"""
        self.seed_book(self.release_a)
        for table in ('knowledge_releasecard', 'knowledge_releaseevidence'):
            with self.subTest(table=table):
                with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                    self.seed_projection(table, self.release_b)

    def test_database_preserves_release_scoped_core_ids_and_rejects_duplicates(self):
        """无参数；两版本可使用同coreID，单版本重复及修改成异版书目则由数据库拒绝。"""
        for release in (self.release_a, self.release_b):
            self.seed_book(release)
            for table in ('knowledge_releasecard', 'knowledge_releaseevidence'):
                self.seed_projection(table, release)
                with self.assertRaises(psycopg.errors.UniqueViolation):
                    self.seed_projection(table, release)
            with self.assertRaises(psycopg.errors.UniqueViolation):
                self.seed_book(release)
        self.seed_book(self.release_a, 'book.a-only')
        for table in ('knowledge_releasecard', 'knowledge_releaseevidence'):
            with self.subTest(table=table):
                with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                    self.manager.execute(sql.SQL('UPDATE {} SET core_book_id=%s WHERE release_id=%s').format(sql.Identifier(table)),
                        ['book.a-only', self.release_b])
        with connection.cursor() as cursor:
            cursor.execute('SELECT release_id, core_card_id FROM knowledge_releasecard')
            self.assertEqual(set(cursor.fetchall()), {
                (self.release_a, 'card.shared-core-id'), (self.release_b, 'card.shared-core-id')})

    def test_database_rejects_duplicate_versions_and_invalid_fingerprints(self):
        """无参数；直接管理SQL也不能绕过唯一性、hex长度/字符和完整指纹前缀一致性。"""
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.seed_release('a')
        cases = (
            {'content_version': 'g' * 24, 'source_fingerprint': 'g' * 64},
            {'content_version': 'c' * 23},
            {'source_fingerprint': 'c' * 63},
            {'content_version': 'd' * 24},
        )
        for fields in cases:
            with self.subTest(fields=fields):
                with self.assertRaises(psycopg.errors.CheckViolation):
                    self.seed_release('c', **fields)

    def test_database_requires_published_release_prerequisites(self):
        """无参数；published要求有效状态、技术时间、权利状态与正计数，非宣称文件已验证。"""
        now = timezone.now()
        valid = dict(status='published', rights_status='approved', validated_at=now,
            published_at=now, card_count=2, book_count=1)
        for fields in ({'status': 'invented'}, {'rights_status': 'invented'},
                       {'validated_at': None}, {'published_at': None},
                       {'rights_status': 'unreviewed'}, {'card_count': 0}, {'book_count': 0},
                       {'card_count': -1}):
            with self.subTest(fields=fields):
                with self.assertRaises(psycopg.errors.CheckViolation):
                    self.seed_release('c', **{**valid, **fields})
        self.seed_release('c', **valid)

    def test_database_enforces_grant_unique_role_and_revocation_state(self):
        """无参数；重复授权、写角色、非法状态与撤销时间矛盾都无法靠管理SQL绕过。"""
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.seed_grant(self.owner_a, self.release_a)
        for fields in ({'role': 'writer'}, {'status': 'invented'}, {'status': 'revoked'},
                       {'revoked_at': timezone.now()}):
            with self.subTest(fields=fields):
                with self.assertRaises(psycopg.errors.CheckViolation):
                    self.seed_grant(self.owner_c, self.release_a, **fields)
        expired_at = timezone.now() - timedelta(seconds=1)
        expired = self.seed_grant(self.owner_c, self.release_a, expires_at=expired_at)
        # RLS只按owner隔离授权记录；到期是否允许知识访问由下一单元实时检查。
        with owner_transaction(self.owner_c):
            with connection.cursor() as cursor:
                cursor.execute('SELECT expires_at FROM knowledge_librarygrant WHERE id=%s', [expired])
                self.assertEqual(cursor.fetchone(), (expired_at,))
        self.manager.execute("UPDATE knowledge_librarygrant SET status='revoked', revoked_at=%s WHERE id=%s",
            [timezone.now(), expired])

    def test_database_requires_rights_review_evidence_before_approved(self):
        """无参数；审批状态须有reviewer和时间，测试记录不作为真实版权通过证据。"""
        for fields in ({'status': 'approved'},
                       {'status': 'approved', 'reviewer_id': self.owner_a},
                       {'status': 'approved', 'reviewed_at': timezone.now()},
                       {'status': 'invented'}, {'basis_type': 'invented'}):
            with self.subTest(fields=fields):
                with self.assertRaises(psycopg.errors.CheckViolation):
                    self.seed_rights(**fields)
        self.seed_rights(status='approved', reviewer_id=self.owner_a, reviewed_at=timezone.now())

    def test_grant_rls_survives_rollback_and_management_remains_separate(self):
        """无参数；FORCE RLS开启且回滚清身份；迁移角色可管理，runtime不能提升或关策略。"""
        with connection.cursor() as cursor:
            cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid='knowledge_librarygrant'::regclass")
            self.assertEqual(cursor.fetchone(), (True, True))
            cursor.execute("SELECT policyname, roles, cmd FROM pg_policies WHERE schemaname='public' AND tablename='knowledge_librarygrant'")
            self.assertEqual(set((name, tuple(roles), command) for name, roles, command in cursor.fetchall()), {
                ('knowledge_grant_owner_read', ('sb_runtime',), 'SELECT'),
                ('knowledge_grant_management', ('sb_migrator',), 'ALL'),
                ('publishing_grant_read', ('sb_runtime',), 'SELECT'),
                ('publishing_insert', ('sb_runtime',), 'INSERT'),
                ('publishing_update', ('sb_runtime',), 'UPDATE'),
            })
        with self.assertRaisesRegex(ValueError, '测试回滚'):
            with owner_transaction(self.owner_a):
                self.assertEqual(self.visible_grants(), {self.grant_a})
                raise ValueError('测试回滚')
        self.assertEqual(self.visible_grants(), set())
        with owner_transaction(self.owner_b):
            self.assertEqual(self.visible_grants(), {self.grant_b})
        self.assertEqual(self.visible_grants(), set())
        for query in ('SET ROLE sb_migrator', 'ALTER TABLE knowledge_librarygrant DISABLE ROW LEVEL SECURITY'):
            with self.assertRaises(DatabaseError) as caught:
                with connection.cursor() as cursor:
                    cursor.execute(query)
            self.assertEqual(caught.exception.__cause__.sqlstate, '42501')
        self.manager.execute("UPDATE knowledge_librarygrant SET status='revoked', revoked_at=%s WHERE id=%s",
            [timezone.now(), self.grant_a])
        with owner_transaction(self.owner_a):
            with connection.cursor() as cursor:
                cursor.execute('SELECT status FROM knowledge_librarygrant WHERE id=%s', [self.grant_a])
                self.assertEqual(cursor.fetchone(), ('revoked',))

    def test_access_migration_reverses_closed_and_reapplication_removes_broad_grants(self):
        """无参数；仅固定测试库回退/重迁移，保留行并证明迁移本身能撤掉旧式宽权限。"""
        configuration = database_settings(settings.DEV_ENV['SB_MIGRATION_DATABASE_URL'],
            'SB_MIGRATION_DATABASE_URL', False)
        configuration['NAME'] = 'test_sb_product'
        # 独立连接供MigrationExecutor使用，绝不切换全局default业务连接身份。
        migration_connection = ConnectionHandler({'default': configuration})['default']
        self.addCleanup(migration_connection.close)
        with migration_connection.cursor() as cursor:
            cursor.execute('SELECT current_database(), current_user')
            self.assertEqual(cursor.fetchone(), ('test_sb_product', 'sb_migrator'))
        try:
            MigrationExecutor(migration_connection).migrate([('knowledge', '0001_initial')])
            with connection.cursor() as cursor:
                for table in TABLES:
                    cursor.execute('SELECT has_table_privilege(current_user, %s, %s)', [table, 'SELECT'])
                    self.assertFalse(cursor.fetchone()[0], '回退必须先撤runtime读权')
            self.assertEqual(self.manager.execute('SELECT count(*) FROM knowledge_librarygrant').fetchone(), (2,))
            for table in TABLES:
                # 模拟旧default privileges/运维误授的结果；未执行任何runtime写入。
                self.manager.execute(sql.SQL('GRANT ALL ON TABLE {} TO sb_runtime, PUBLIC').format(sql.Identifier(table)))
            with connection.cursor() as cursor:
                cursor.execute("SELECT has_table_privilege(current_user, 'knowledge_librarygrant', 'INSERT')")
                self.assertTrue(cursor.fetchone()[0])
            MigrationExecutor(migration_connection).migrate([('knowledge', '0002_database_access')])
            with connection.cursor() as cursor:
                for table in TABLES:
                    cursor.execute('SELECT has_table_privilege(current_user, %s, %s)', [table, 'SELECT'])
                    self.assertTrue(cursor.fetchone()[0])
                    for privilege in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                        cursor.execute('SELECT has_table_privilege(current_user, %s, %s)', [table, privilege])
                        self.assertFalse(cursor.fetchone()[0], f'{table} 迁移未收回 {privilege}')
                    cursor.execute('SELECT count(*) FROM pg_class, LATERAL aclexplode(relacl) AS acl '
                        'WHERE oid=%s::regclass AND acl.grantee=0', [table])
                    self.assertEqual(cursor.fetchone(), (0,))
            self.assertEqual(self.visible_grants(), set())
            with owner_transaction(self.owner_a):
                self.assertEqual(self.visible_grants(), {self.grant_a})
            with owner_transaction(self.owner_b):
                self.assertEqual(self.visible_grants(), {self.grant_b})
        finally:
            # 即使断言失败，也恢复完整迁移后再按UUID清理测试记录。
            executor = MigrationExecutor(migration_connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
