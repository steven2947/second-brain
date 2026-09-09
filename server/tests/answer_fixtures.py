"""自编模型提案复用原核心测试样例；不模拟检索、权限或v3验证器。"""
import importlib.util
from pathlib import Path
from ai.ports import Generation


class AnswerProvider:
    """仅在测试中生成固定答案结构；线上模式从不导入本模块。"""

    def generate(self, request):
        """request为实际worker请求；测试用户已明确当天执行的事实与约束。"""
        if request.purpose == 'extract':
            content = {'changes': {'facts': [request.context['message']], 'constraints': ['今天需要开始']},
                       'reason': '自编测试消息明确今天需要开始。'}
        elif request.purpose == 'plan':
            content = {'type': 'prepare', 'retrieval_focus': '小步骤试行与反馈',
                       'query_expansions': ['琥珀试行', '反馈'], 'reason': '明确要求直接分析。'}
        else:
            path = Path(__file__).resolve().parents[2] / 'tests/test_orchestration_validation.py'
            spec = importlib.util.spec_from_file_location('_product_core_test_fixture', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            content = module.valid_v2_draft(request.context['session'])
            content['schema_version'] = 3
            for decision, candidate in zip(content['decisions'], request.context['session']['candidates']):
                decision['adoption'] = {'claim': candidate['card']['statement'],
                    'source_claim_type': candidate['card'].get('source_claim_type', 'unclassified'),
                    'evidence_ids': candidate['card']['evidence_ids'][:1], 'excluded_scope': ['原卡其他未选证据不作为本次依据。']}
        return Generation(content=content, provider='test', model='self-authored', input_tokens=37, output_tokens=91)
