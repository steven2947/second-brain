"""真实MFA、CSRF、runtime RLS与临时自编目录的完整知识发布验收。"""
import shutil
import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import SimpleTestCase, Client, override_settings
from django.utils import timezone
from access.context import owner_transaction
from accounts.models import User
from administration.services import SESSION_KEY
from knowledge.models import LibraryRelease, LibraryCollection
from publishing.access import source_library
from publishing.import_worker import process_one, claim, finalize
from publishing.models import RegisteredSource, ImportJob
from .knowledge_fixtures import FIXTURES
from .test_administration import AdministrationTests, PASSWORD


class PublishingTests(SimpleTestCase):
    """只复用既有真实MFA夹具方法，不继承或重复执行其测试。"""
    databases = {'default'}
    migration_connection = AdministrationTests.migration_connection
    confirm = AdministrationTests.confirm
    token = AdministrationTests.token
    cleanup_records = AdministrationTests.cleanup_records
    client_with_csrf = AdministrationTests.client_with_csrf
    login = AdministrationTests.login

    def prepare(self, role='system-admin'):
        """role为真实显式权限组；使用原有密码加OTP登记夹具。"""
        return AdministrationTests.prepare(self, role)

    def setUp(self):
        """无参数；复制自编fixture到临时根，不登记或改变主库及examples。"""
        AdministrationTests.setUp(self)
        self.root = Path(self.directory.name).resolve() / 'library'
        shutil.copytree(FIXTURES / 'releaseA', self.root / 'fixed-a')
        self.library_override = override_settings(SB_LIBRARY_ROOT=self.root, SB_PRIVATE_DATA_ROOT=Path(self.directory.name).resolve())
        self.library_override.enable()
        self.addCleanup(self.library_override.disable)
        self.addCleanup(self.cleanup_publishing)
        with self.migration_connection():
            call_command('register_knowledge_source', staging_key='test-' + self.user.pk.hex,
                storage_key='fixed-a', title='自编导入', description='临时测试', settings='config.settings.migrate', verbosity=0)
        self.source = RegisteredSource.objects.get(staging_key='test-' + self.user.pk.hex)
        self.target = User.objects.create_user('reader-' + uuid4().hex + '@example.test', PASSWORD, display_name='自编普通读者')
        self.users.append(self.target.pk)
        self.assertEqual(self.login().status_code, 200)

    def cleanup_publishing(self):
        """无参数；按本用例管理员和登记源定位，外键逆序精确清理测试记录。"""
        self.manager.execute('DELETE FROM publishing_adminmutation WHERE owner_id=ANY(%s)', [self.users])
        releases = [row[0] for row in self.manager.execute(
            'SELECT id FROM knowledge_libraryrelease WHERE library_id IN (SELECT id FROM knowledge_librarycollection WHERE curator_id=ANY(%s))', [self.users]).fetchall()]
        self.manager.execute('DELETE FROM publishing_importjob WHERE owner_id=ANY(%s)', [self.users])
        for table in ('knowledge_librarygrant', 'knowledge_rightsrecord', 'knowledge_releaseevidence', 'knowledge_releasecard', 'knowledge_releasebook'):
            self.manager.execute(f'DELETE FROM {table} WHERE release_id=ANY(%s)', [releases])
        self.manager.execute('DELETE FROM knowledge_libraryrelease WHERE id=ANY(%s)', [releases])
        self.manager.execute('DELETE FROM knowledge_librarycollection WHERE curator_id=ANY(%s)', [self.users])
        self.manager.execute('DELETE FROM publishing_registeredsource WHERE staging_key=%s', ['test-' + self.user.pk.hex])

    def write(self, method, path, data, key=None, browser=None):
        """method/path/data为本次真实HTTP操作；key用于精确测试幂等，browser默认为MFA会话。"""
        return getattr(browser or self.browser, method)(path, data, content_type='application/json', HTTP_IDEMPOTENCY_KEY=key or uuid4().hex)

    def enqueue(self):
        """无参数；提交登记源并验证202对应持久任务。"""
        response = self.write('post', '/api/v1/admin/releases/import', {'staging_key': self.source.staging_key})
        self.assertEqual(response.status_code, 202, response.content)
        with owner_transaction(self.user.pk):
            return ImportJob.objects.get(pk=response.json()['job_id'])

    def imported(self):
        """无参数；真实worker解析固定目录并生成未审核版本。"""
        job = self.enqueue()
        self.assertTrue(process_one(self.user.pk))
        result = self.browser.get('/api/v1/admin/imports/' + str(job.pk)).json()
        self.assertEqual(result['status'], 'succeeded', result)
        release = LibraryRelease.objects.get(pk=result['release_id'])
        self.assertEqual((release.status, release.rights_status), ('validated', 'unreviewed'))
        return release

    def rights_record(self, **overrides):
        """overrides为本测试有意改变的许可字段，默认只声明自编fixture的人工许可。"""
        return {**{'scope_book_ids': [], 'source_description': '仅本测试自编内容', 'basis_type': 'self_authored',
            'license_name': None, 'proof_storage_key': None, 'allowed_audience': 'granted_users',
            'allowed_uses': ['browse', 'analyze', 'quote'], 'quote_policy': {'max_chars': 30},
            'valid_until': None, 'status': 'approved'}, **overrides}

    def approve_publish(self, release):
        """release为本测试导入版本；分别提交人工审核与发布操作。"""
        base = '/api/v1/admin/releases/' + str(release.pk)
        approved = self.write('put', base + '/rights', {'records': [self.rights_record()]})
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()['rights_status'], 'approved')
        published = self.write('post', base + '/publish', {'expected_status': 'validated'})
        self.assertEqual(published.status_code, 200, published.content)

    def test_real_import_review_publish_grant_author_and_immediate_revocation(self):
        """无参数；完整真实worker与用户书房链路，不用mock授权或技术校验冒充权利审核。"""
        release = self.imported()
        base = '/api/v1/admin/releases/' + str(release.pk)
        refused = self.write('post', base + '/publish', {'expected_status': 'validated'})
        self.assertEqual(refused.json()['error']['code'], 'RELEASE_NOT_READY')
        self.approve_publish(release)
        detail = self.browser.get(base).json()
        self.assertNotIn('storage_key', detail)
        self.assertNotIn('proof_storage_key', detail['rights_records'][0])
        self.assertTrue(any(book['author_display'] for book in detail['books']))
        grant_path = '/api/v1/admin/users/' + str(self.target.pk) + '/grants/' + str(release.pk)
        granted = self.write('put', grant_path, {'expires_at': None})
        self.assertEqual(granted.status_code, 200, granted.content)
        self.target.refresh_from_db()
        self.assertEqual(self.target.access_revision, 1)
        reader = self.client_with_csrf()
        response = reader.post('/api/v1/auth/login', {'email': self.target.email, 'password': PASSWORD}, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        books_path = '/api/v1/libraries/' + str(release.pk) + '/books'
        books = reader.get(books_path)
        self.assertEqual(books.status_code, 200, books.content)
        self.assertTrue(any(book['author_display'] for book in books.json()['items']))
        self.assertEqual(self.write('delete', grant_path, {'reason': '测试撤销'}).status_code, 204)
        self.assertEqual(reader.get(books_path).status_code, 404)
        self.assertEqual(self.write('put', grant_path, {'expires_at': None}).status_code, 200)
        self.assertEqual(reader.get(books_path).status_code, 200)
        self.assertEqual(self.write('post', base + '/revoke', {'expected_status': 'published', 'reason': '测试撤回'}).status_code, 200)
        self.assertEqual(reader.get(books_path).status_code, 404)

    def test_ordinary_session_all_management_paths_denied_and_csrf_enforced(self):
        """无参数；普通真实密码登录不能读取或写入任何管理端点，MFA写仍需CSRF。"""
        reader = self.client_with_csrf()
        self.assertEqual(reader.post('/api/v1/auth/login', {'email': self.target.email, 'password': PASSWORD}, content_type='application/json').status_code, 200)
        reader.defaults['HTTP_X_CSRFTOKEN'] = reader.get('/api/v1/auth/csrf').json()['csrf_token']
        identifier = str(uuid4())
        for route in ('sources', 'imports', 'imports/' + identifier, 'releases', 'releases/' + identifier, 'users'):
            self.assertEqual(reader.get('/api/v1/admin/' + route).status_code, 401)
        for method, route in (('post', 'releases/import'), ('put', 'releases/' + identifier + '/rights'),
            ('post', 'releases/' + identifier + '/publish'), ('post', 'releases/' + identifier + '/revoke'),
            ('put', 'users/' + identifier + '/grants/' + identifier), ('delete', 'users/' + identifier + '/grants/' + identifier)):
            self.assertEqual(self.write(method, '/api/v1/admin/' + route, {}, browser=reader).status_code, 401)
        no_csrf = Client(enforce_csrf_checks=True)
        no_csrf.cookies = self.browser.cookies.copy()
        self.assertEqual(no_csrf.post('/api/v1/admin/releases/import', {'staging_key': self.source.staging_key}, content_type='application/json').status_code, 403)

    def test_idempotency_freshness_explicit_permission_and_owner_scope(self):
        """无参数；同键重放不新增任务、异体409，重放仍受fresh与当前显式权限约束。"""
        path, data, key = '/api/v1/admin/releases/import', {'staging_key': self.source.staging_key}, uuid4().hex
        first = self.write('post', path, data, key)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(self.write('post', path, data, key).json(), first.json())
        conflict = self.write('post', path, {'staging_key': 'another'}, key)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(len(self.browser.get('/api/v1/admin/imports').json()['items']), 1)
        with owner_transaction(self.target.pk):
            self.assertEqual(ImportJob.objects.count(), 0)
        state = self.browser.session
        state[SESSION_KEY] = {**state[SESSION_KEY], 'verified_at': timezone.now().timestamp() - 301, 'started_at': timezone.now().timestamp() - 302,
            'expires_at': timezone.now().timestamp() - 302 + 8 * 60 * 60}
        # 保持绝对期限精确，防止把无效会话误当过期再次认证。
        state[SESSION_KEY]['expires_at'] = state[SESSION_KEY]['started_at'] + 8 * 60 * 60
        state.save()
        self.assertEqual(self.write('post', path, data, key).json()['error']['code'], 'ADMIN_REAUTH_REQUIRED')
        self.manager.execute('DELETE FROM accounts_user_groups WHERE user_id=%s', [self.user.pk])
        self.assertEqual(self.browser.get('/api/v1/admin/sources').status_code, 403)

    def test_registration_unknown_paths_fingerprint_and_runtime_boundary(self):
        """无参数；CLI固定配置与根检查、未知登记拒绝，文件变更导致真实任务失败。"""
        with self.assertRaises(CommandError):
            call_command('register_knowledge_source', staging_key='unknown', storage_key='fixed-a', title='不允许runtime登记', settings='config.settings.migrate')
        for bad in ('../fixed-a', '/tmp/elsewhere', 'https://example.test/library', 'CURRENT', 'fixed-a/../fixed-a'):
            with self.migration_connection(), self.assertRaises(CommandError):
                call_command('register_knowledge_source', staging_key='bad-' + uuid4().hex, storage_key=bad, title='非法路径', settings='config.settings.migrate')
        (self.root / 'alias').symlink_to(self.root / 'fixed-a', target_is_directory=True)
        with self.migration_connection(), self.assertRaises(CommandError):
            call_command('register_knowledge_source', staging_key='bad-' + uuid4().hex, storage_key='alias', title='拒绝链接', settings='config.settings.migrate')
        unknown = self.write('post', '/api/v1/admin/releases/import', {'staging_key': 'unknown'})
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(self.write('post', '/api/v1/admin/releases/import', {'staging_key': self.source.staging_key, 'storage_key': 'fixed-a'}).status_code, 400)
        job = self.enqueue()
        (self.root / 'fixed-a' / 'changed.txt').write_text('仅自编测试目录变动')
        self.assertTrue(process_one(self.user.pk))
        result = self.browser.get('/api/v1/admin/imports/' + str(job.pk)).json()
        self.assertEqual((result['status'], result['release_id']), ('failed', None))
        with self.assertRaises(DatabaseError):
            RegisteredSource.objects.filter(pk=self.source.pk).update(title='不应成功')
        with self.assertRaises(DatabaseError):
            LibraryCollection.objects.create(title='空上下文不应成功')
        with self.assertRaises(DatabaseError), owner_transaction(self.target.pk):
            LibraryCollection.objects.create(title='不应成功')

    def test_worker_revoked_permission_and_expired_lease_cannot_create_release(self):
        """无参数；解析期间真实撤权限以及旧租约执行者都不能提交版本与投影。"""
        job = self.enqueue()
        original_loader = source_library
        def revoke_permission(source):
            """source为真实登记源；解析后通过迁移测试连接撤销真实权限组。"""
            library = original_loader(source)
            self.manager.execute('DELETE FROM accounts_user_groups WHERE user_id=%s', [self.user.pk])
            return library
        with patch('publishing.import_worker.source_library', side_effect=revoke_permission):
            self.assertTrue(process_one(self.user.pk))
        with owner_transaction(self.user.pk):
            job.refresh_from_db()
        self.assertEqual((job.status, job.release_id, job.error_code), ('failed', None, 'ADMIN_PERMISSION_DENIED'))
        self.assertFalse(LibraryCollection.objects.filter(curator=self.user).exists())

    def test_expired_lease_is_reclaimed_without_old_execution_publication(self):
        """无参数；直接运行真实claim/finalize，过期租约不能提交，新租约可完成同一job。"""
        self.enqueue()
        old = claim(self.user.pk)
        library = source_library(self.source)
        self.manager.execute('UPDATE publishing_importjob SET lease_until=%s WHERE id=%s', [timezone.now() - timedelta(seconds=1), old.pk])
        replacement = claim(self.user.pk)
        self.assertNotEqual(old.lease_token, replacement.lease_token)
        with self.assertRaises(Exception) as error:
            finalize(old, library)
        self.assertEqual(error.exception.code, 'IMPORT_LEASE_LOST')
        self.assertFalse(LibraryCollection.objects.filter(curator=self.user).exists())
        finalize(replacement, library)
        with owner_transaction(self.user.pk):
            replacement.refresh_from_db()
        self.assertEqual(replacement.status, 'succeeded')

    def test_rights_scope_proof_expiry_published_edit_and_state_compare(self):
        """无参数；部分覆盖不批准、证明必须是私有普通文件、过期或指纹变更禁止发布。"""
        release = self.imported()
        base = '/api/v1/admin/releases/' + str(release.pk)
        book = self.browser.get(base).json()['books'][0]['id']
        partial = self.write('put', base + '/rights', {'records': [self.rights_record(scope_book_ids=[book])]})
        self.assertEqual(partial.json()['rights_status'], 'unreviewed')
        missing = self.write('put', base + '/rights', {'records': [self.rights_record(basis_type='permission')]})
        self.assertEqual(missing.status_code, 400)
        forged = self.write('put', base + '/rights', {'records': [self.rights_record(reviewer=str(self.user.pk))]})
        self.assertEqual(forged.status_code, 400)
        expired = self.write('put', base + '/rights', {'records': [self.rights_record(valid_until=(timezone.now() - timedelta(days=1)).isoformat())]})
        self.assertEqual(expired.json()['rights_status'], 'unreviewed')
        self.approve_publish(release)
        self.assertEqual(self.write('put', base + '/rights', {'records': [self.rights_record()]}).json()['error']['code'], 'RELEASE_MUST_REVOKE')
        self.assertEqual(self.write('post', base + '/revoke', {'expected_status': 'validated', 'reason': '冲突'}).status_code, 409)
        self.assertEqual(self.write('post', base + '/revoke', {'expected_status': 'published', 'reason': '撤销'}).status_code, 200)
        (self.root / 'fixed-a' / 'changed.txt').write_text('仅临时自编文件变更')
        self.assertEqual(self.write('post', base + '/publish', {'expected_status': 'revoked'}).json()['error']['code'], 'SOURCE_UNAVAILABLE')

    def test_knowledge_admin_cannot_manage_grants_and_review_permission_cannot_publish_sql(self):
        """无参数；真实数据库权限边界拒绝知识管理员grant，review权限不能直接SQL发布。"""
        release = self.imported()
        self.manager.execute('DELETE FROM accounts_user_groups WHERE user_id=%s', [self.user.pk])
        self.manager.execute('INSERT INTO accounts_user_user_permissions (user_id,permission_id) SELECT %s,p.id FROM auth_permission p JOIN django_content_type c ON c.id=p.content_type_id WHERE c.app_label=%s AND c.model=%s AND p.codename=%s',
            [self.user.pk, 'administration', 'administratordevice', 'knowledge_review'])
        self.assertEqual(self.browser.get('/api/v1/admin/releases').status_code, 200)
        self.assertEqual(self.browser.get('/api/v1/admin/users').status_code, 403)
        grant_path = '/api/v1/admin/users/' + str(self.target.pk) + '/grants/' + str(release.pk)
        self.assertEqual(self.write('put', grant_path, {'expires_at': None}).status_code, 403)
        with self.assertRaises(DatabaseError), owner_transaction(self.user.pk):
            LibraryRelease.objects.filter(pk=release.pk).update(status='published', rights_status='approved', published_at=timezone.now())

    def test_rights_chinese_payload_above_account_limit_and_private_proof_validation(self):
        """无参数；超过8KiB的正常中文审核通过独立有界读取，私有证明校验不放宽链接边界。"""
        release = self.imported()
        base = '/api/v1/admin/releases/' + str(release.pk)
        private = Path(self.directory.name).resolve() / 'proofs'
        private.mkdir()
        (private / 'approval.txt').write_text('仅自编夹具授权说明')
        record = self.rights_record(source_description='自编' * 999, basis_type='permission', proof_storage_key='proofs/approval.txt')
        payload = {'records': [record, record]}
        self.assertGreater(len(json.dumps(payload, ensure_ascii=False).encode()), 8192)
        response = self.write('put', base + '/rights', payload)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['rights_status'], 'approved')
        (private / 'alias.txt').symlink_to(private / 'approval.txt')
        self.assertEqual(self.write('put', base + '/rights', {'records': [self.rights_record(basis_type='permission', proof_storage_key='proofs/alias.txt')]}).status_code, 400)
        (private / 'approval.txt').unlink()
        self.assertEqual(self.write('post', base + '/publish', {'expected_status': 'validated'}).json()['error']['code'], 'RELEASE_NOT_READY')
        excessive = json.dumps({'records': [record] * 100}, ensure_ascii=False)
        self.assertGreater(len(excessive.encode()), 256 * 1024)
        self.assertEqual(self.write('put', base + '/rights', excessive).status_code, 400)

    def test_grants_only_permission_catalog_and_disabled_or_staff_targets(self):
        """无参数；仅grant权限能选版本并授权普通人，不能看账号目录、审核或复活禁用/管理账号。"""
        release = self.imported()
        self.approve_publish(release)
        self.manager.execute('DELETE FROM accounts_user_groups WHERE user_id=%s', [self.user.pk])
        self.manager.execute('INSERT INTO accounts_user_user_permissions (user_id,permission_id) SELECT %s,p.id FROM auth_permission p JOIN django_content_type c ON c.id=p.content_type_id WHERE c.app_label=%s AND c.model=%s AND p.codename=%s',
            [self.user.pk, 'administration', 'administratordevice', 'grants_manage'])
        self.assertEqual(self.browser.get('/api/v1/admin/releases').status_code, 200)
        self.assertEqual(self.browser.get('/api/v1/admin/users').status_code, 403)
        base = '/api/v1/admin/releases/' + str(release.pk)
        self.assertEqual(self.write('put', base + '/rights', {'records': [self.rights_record()]}).status_code, 403)
        path = '/api/v1/admin/users/' + str(self.target.pk) + '/grants/' + str(release.pk)
        self.assertEqual(self.write('put', path, {'expires_at': None}).status_code, 200)
        self.assertEqual(self.write('put', path.replace(str(self.target.pk), str(self.user.pk)), {'expires_at': None}).status_code, 404)
        self.manager.execute("UPDATE accounts_user SET status='disabled' WHERE id=%s", [self.target.pk])
        self.assertEqual(self.write('put', path, {'expires_at': None}).status_code, 404)
        self.target.refresh_from_db()
        self.assertEqual((self.target.status, self.target.access_revision), ('disabled', 1))

    def test_worker_rechecks_real_device_revocation_and_auth_epoch(self):
        """无参数；排队后撤销设备或推进账号epoch，任务均终止且不产生release。"""
        device_job, epoch_job = self.enqueue(), self.enqueue()
        self.manager.execute('UPDATE administration_administratordevice SET revoked_at=%s WHERE id=%s', [timezone.now(), device_job.device_id])
        self.assertTrue(process_one(self.user.pk))
        self.manager.execute('UPDATE administration_administratordevice SET revoked_at=NULL WHERE id=%s', [device_job.device_id])
        self.manager.execute('UPDATE accounts_user SET auth_epoch=auth_epoch+1 WHERE id=%s', [self.user.pk])
        self.assertTrue(process_one(self.user.pk))
        with owner_transaction(self.user.pk):
            device_job.refresh_from_db()
            epoch_job.refresh_from_db()
        self.assertEqual((device_job.status, epoch_job.status), ('failed', 'failed'))
        self.assertFalse(LibraryCollection.objects.filter(curator=self.user).exists())

    def test_recent_imports_first_page_and_owner_bound_cursor(self):
        """无参数；超过一页真实任务时最新仍在首项，UUID游标必须属于当前owner可见任务。"""
        first = self.enqueue()
        with owner_transaction(self.user.pk):
            jobs = ImportJob.objects.bulk_create([ImportJob(owner=self.user, source=self.source,
                source_fingerprint=self.source.source_fingerprint, device_id=first.device_id,
                auth_epoch=first.auth_epoch) for _ in range(31)])
        result = self.browser.get('/api/v1/admin/imports').json()
        self.assertEqual(len(result['items']), 30)
        self.assertEqual(result['items'][0]['id'], str(jobs[-1].pk))
        following = self.browser.get('/api/v1/admin/imports', {'cursor': result['next_cursor']}).json()
        self.assertEqual(len(following['items']), 2)
        self.assertEqual(following['items'][-1]['id'], str(first.pk))
        self.assertIsNone(following['next_cursor'])
        self.assertEqual(self.browser.get('/api/v1/admin/imports', {'cursor': str(uuid4())}).status_code, 400)
