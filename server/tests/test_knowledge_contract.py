"""实际知识路由、公开serializer和统一OpenAPI必须一致。"""
import importlib
import importlib.util
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.conf import settings
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase
from jsonschema import Draft202012Validator, ValidationError


class KnowledgeContractTests(SimpleTestCase):
    """只读生成事实源，不连接数据库或改写实际服务响应。"""

    def setUp(self):
        """无参数；缺统一契约时先失败，再实现合并。"""
        self.assertIsNotNone(importlib.util.find_spec('config.contracts'), '缺少统一产品API契约')
        self.contracts = importlib.import_module('config.contracts')

    def test_combined_contract_preserves_every_account_operation_and_covers_knowledge(self):
        """无参数；保留原账号契约逐字段相等，知识六个操作有真实绑定。"""
        from accounts.contracts import build_contract
        account = build_contract()
        combined = self.contracts.build_contract()
        for path, value in account['paths'].items():
            self.assertEqual(combined['paths'][path], value)
        for name, value in account['components']['schemas'].items():
            self.assertEqual(combined['components']['schemas'][name], value)
        self.assertEqual(len(combined['paths']), 61)
        knowledge = {p: v for p, v in combined['paths'].items() if p.startswith('/api/v1/libraries')}
        self.assertEqual(len(knowledge), 6)
        for path, methods in knowledge.items():
            self.assertEqual(set(methods), {'get'})
            self.assertEqual(methods['get']['security'], [{'SessionCookie': []}])
            parameters = methods['get']['parameters']
            if '{release_id}' in path:
                self.assertTrue(any(p['name'] == 'release_id' and p['required'] and p['schema']['format'] == 'uuid' for p in parameters))
        self.assertNotIn('/Users/', self.contracts.contract_text())

    def test_real_public_serializer_data_validates_against_generated_schema(self):
        """无参数；通过同一响应serializer检查未知作者及完整方法字段。"""
        from knowledge.serializers import BrowseCardSerializer
        public = BrowseCardSerializer({'release_id': str(uuid4()), 'card_id': 'c',
            'book': {'id': 'b', 'title': '自编书', 'author_display': None, 'metadata_status': 'partial'},
            'type': 'method', 'title': '方法', 'statement': '主张', 'explanation': '',
            'conditions': [], 'boundaries': [], 'steps': ['真实步骤'], 'application_notes': '',
            'source_claim_type': 'unknown', 'related': [], 'source_previews': [],
            'usage_notice': '整理内容，未针对当前问题采用', 'gaps': ['原理未录入']}).data
        contract = self.contracts.build_contract()
        schema = {'$ref': '#/components/schemas/BrowseCard', 'components': contract['components']}
        Draft202012Validator(schema).validate(dict(public))
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate({**public, 'file': '/private/forbidden'})

    def test_product_export_check_and_legacy_command_share_one_contract(self):
        """无参数；旧导出命令是兼容别名，不能悄悄覆盖成账号子集。"""
        expected = self.contracts.contract_text()
        with TemporaryDirectory() as directory:
            output = str(Path(directory) / 'api.json')
            for command in ('export_api_contract', 'export_auth_contract'):
                call_command(command, output=output, stdout=io.StringIO())
                self.assertEqual(Path(output).read_text(), expected)
                call_command(command, output=output, check=True, stdout=io.StringIO())
                Path(output).write_text('{}\n')
                with self.assertRaises(CommandError):
                    call_command(command, output=output, check=True, stdout=io.StringIO())
                self.assertEqual(Path(output).read_text(), '{}\n')

    def test_checked_in_schema_matches_unified_export(self):
        """无参数；构建使用的唯一路由文档必须可复算。"""
        self.assertEqual((settings.BASE_DIR / 'openapi.json').read_text(), self.contracts.contract_text())
