"""任务HTTP输入/契约的小范围检查，数据库主链另用真实会话覆盖。"""
import importlib
from pathlib import Path
from uuid import uuid4
from django.test import SimpleTestCase, Client


class RunHTTPTests(SimpleTestCase):
    """不接数据库验证匿名拒绝和精确输入类型。"""

    def test_routes_require_login_before_any_body_or_lookup(self):
        """无参数；真实已注册路径匿名应401，不应404占位或处理载荷。"""
        identifier = str(uuid4())
        browser = Client()
        for url, method in ((f'/api/v1/problems/{identifier}/messages', 'get'),
                            (f'/api/v1/problems/{identifier}/messages', 'post'),
                            (f'/api/v1/problems/{identifier}/analyze', 'post'),
                            (f'/api/v1/runs/{identifier}', 'get'),
                            (f'/api/v1/jobs/{identifier}', 'get'),
                            (f'/api/v1/jobs/{identifier}/cancel', 'post')):
            with self.subTest(url=url, method=method):
                response = getattr(browser, method)(url)
                self.assertEqual(response.status_code, 401)

    def test_message_fields_preserve_raw_text_and_reject_forged_inputs(self):
        """无参数；消息原文不裁剪，禁止角色和核心状态等额外字段。"""
        self.assertTrue((Path(__file__).resolve().parents[1]/'runs/serializers.py').exists())
        serializer = importlib.import_module('runs.serializers').SendMessageSerializer
        data = {'content': '  还未报价。\n', 'intent': 'answer',
                'client_message_id': str(uuid4()), 'expected_revision': 0}
        parsed = serializer(data=data)
        self.assertTrue(parsed.is_valid(), parsed.errors)
        self.assertEqual(parsed.validated_data['content'], data['content'])
        for change in ({'content': 12}, {'content': '  '}, {'content': '字'*20001},
                       {'expected_revision': True}, {'expected_revision': '0'},
                       {'intent': 'system'}, {'role': 'assistant'}, {'owner_id': str(uuid4())}):
            with self.subTest(change=list(change)):
                self.assertFalse(serializer(data={**data, **change}).is_valid())

    def test_actual_contract_has_new_routes_and_no_internal_state(self):
        """无参数；导出基于真实路由字段，消息只返回公开结构。"""
        from config.contracts import build_contract
        contract = build_contract()
        self.assertIn('/api/v1/problems/{problem_id}/messages', contract['paths'])
        schema = contract['components']['schemas']['MessagePage']
        self.assertFalse(schema['additionalProperties'])
        self.assertNotIn('internal_state', str(schema))
        from jsonschema import Draft202012Validator, ValidationError
        outcome = contract['components']['schemas']['Run']['properties']['outcome']
        Draft202012Validator(outcome).validate(None)
        with self.assertRaises(ValidationError):
            Draft202012Validator(outcome).validate('private internal output')
