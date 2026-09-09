"""知识发布与授权模型声明检查；真实数据库约束和RLS另用运行角色验收。"""
from django.apps import apps
from django.db.models import PROTECT
from django.test import SimpleTestCase


class KnowledgeModelContractTests(SimpleTestCase):
    """此处验证职责和字段接缝，不把声明当作已迁移或权限通过。"""

    def test_release_grant_rights_and_projection_models_are_registered(self):
        """无参数；只增加产品知识模块，不更换现有accounts身份事实源。"""
        self.assertTrue(apps.is_installed('knowledge'))
        for name in ('LibraryCollection', 'LibraryRelease', 'LibraryGrant', 'RightsRecord', 'ReleaseBook', 'ReleaseCard', 'ReleaseEvidence'):
            self.assertIsNotNone(apps.get_model('knowledge', name))

    def test_release_fingerprints_and_user_grants_have_database_constraints(self):
        """无参数；版本与整库授权有唯一性和状态约束，授权不能级联删掉共享书库。"""
        self.assertTrue(apps.is_installed('knowledge'))
        release = apps.get_model('knowledge', 'LibraryRelease')
        grant = apps.get_model('knowledge', 'LibraryGrant')
        self.assertEqual(release._meta.get_field('content_version').max_length, 24)
        self.assertEqual(release._meta.get_field('source_fingerprint').max_length, 64)
        self.assertTrue({'knowledge_release_version_unique', 'knowledge_release_fingerprint_valid', 'knowledge_release_version_matches', 'knowledge_release_state_valid'}.issubset({item.name for item in release._meta.constraints}))
        self.assertTrue({'knowledge_grant_owner_release_unique', 'knowledge_grant_state_valid', 'knowledge_grant_role_reader'}.issubset({item.name for item in grant._meta.constraints}))
        self.assertIs(grant._meta.get_field('release').remote_field.on_delete, PROTECT)
        self.assertEqual(grant._meta.get_field('owner').remote_field.model._meta.label, 'accounts.User')

    def test_core_ids_are_unique_within_release_not_globally(self):
        """无参数；允许不同版本复用同一核心ID，不借全局唯一掩盖跨版本串接。"""
        self.assertTrue(apps.is_installed('knowledge'))
        for name, field in (('ReleaseBook', 'core_book_id'), ('ReleaseCard', 'core_card_id'), ('ReleaseEvidence', 'core_evidence_id')):
            model = apps.get_model('knowledge', name)
            self.assertFalse(model._meta.get_field(field).unique)
            self.assertTrue(any(tuple(getattr(item, 'fields', ())) == ('release', field) for item in model._meta.constraints))
