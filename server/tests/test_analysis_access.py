"""实际用途授权区分可读与可分析，不因浏览许可自动外发知识。"""
from datetime import timedelta
from django.utils import timezone
from psycopg.types.json import Jsonb
from access import services
from tests.knowledge_fixtures import KnowledgeFixtureCase


class AnalysisAccessTests(KnowledgeFixtureCase):
    """用真实runtime和自编许可验证整版本分析覆盖。"""

    def analyze(self):
        """无参数；对当前测试用户的版本执行实际分析授权查询。"""
        self.assertTrue(hasattr(services, 'analysis_snapshot'), '分析用途入口尚未实现')
        return services.analysis_snapshot(self.user_a, self.release_a)

    def test_browse_permission_does_not_grant_analysis(self):
        """无参数；原有browse读取继续通过，分析被拒。"""
        self.assertTrue(services.access_snapshot(self.user_a, self.release_a))
        with self.assertRaises(services.KnowledgeError):
            self.analyze()

    def test_analysis_requires_whole_release_and_current_rights(self):
        """无参数；一书分析许可不覆盖整库，完整且有效才能准入。"""
        right = self.seed_rights(self.release_a, allowed_uses=Jsonb(['analyze']),
            scope_book_ids=Jsonb(['book.product-a.trials']))
        with self.assertRaises(services.KnowledgeError):
            self.analyze()
        self.change('knowledge_rightsrecord', right, scope_book_ids=Jsonb([]))
        self.assertEqual(self.analyze()['release']['id'], self.release_a)
        self.change('knowledge_rightsrecord', right, valid_until=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(services.KnowledgeError):
            self.analyze()

    def test_analysis_grant_still_requires_owner(self):
        """无参数；获准A不能把版本授权转交B。"""
        self.change('knowledge_rightsrecord', self.right_a, allowed_uses=Jsonb(['browse','analyze']))
        self.assertTrue(self.analyze())
        with self.assertRaises(services.KnowledgeError):
            services.analysis_snapshot(self.user_b, self.release_a)
