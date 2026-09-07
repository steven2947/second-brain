"""检查新调用采用v3且保留既有深入表达与澄清要求；语义仍需同题审阅。"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class AdoptionSkillContractTests(unittest.TestCase):
    """约束新入口和迁移说明，不用词频或篇幅代替建议质量。"""

    def test_new_default_and_explicit_legacy(self):
        """Skill、工作流和提示词均指向新schema，历史兼容仍明示。"""
        skill = (ROOT/'skills/second-brain/SKILL.md').read_text()
        workflow = (ROOT/'skills/second-brain/references/query-workflow.md').read_text()
        prompt = (ROOT/'prompts/answer-orchestrator.v3.md').read_text()
        self.assertIn('默认生成 `schema_version: 3`', skill)
        self.assertIn('prompts/answer-orchestrator.v3.md', skill)
        self.assertIn('schemas/analysis-draft.v3.schema.json', workflow)
        self.assertIn('schemas/analysis-draft.v2.schema.json', workflow)
        self.assertIn('--schema-version 3', workflow)
        for field in ('adoption', 'adopted_claim', 'excluded_scope', 'original_card_ref', 'evidence_ids'):
            with self.subTest(field=field):
                self.assertIn(field, prompt)
        self.assertIn('不能证明自然语言主张一定忠于原文', prompt)
        self.assertIn('不可宣称已获得本版采用隔离', prompt)

    def test_fifteen_prior_generation_requirements_are_preserved(self):
        """v3追加采用边界，不重写旧15项生成职责。"""
        prior = (ROOT/'prompts/answer-orchestrator.v2.md').read_text()
        current = (ROOT/'prompts/answer-orchestrator.v3.md').read_text()
        original_rules = [line for line in prior.splitlines() if re.match(r'^\d+\. ', line)]
        self.assertEqual(len(original_rules), 15)
        for rule in original_rules:
            with self.subTest(rule=rule[:50]):
                self.assertIn(rule, current)
        for phrase in ('最多3轮', '建议', '自由', '独立立场—交叉质询—主持裁决', '继续和 AI 聊'):
            self.assertIn(phrase, current)

    def test_output_rules_forbid_audit_reference_as_adoption(self):
        """审计入口不是把排除部分回填答案的授权。"""
        rules = (ROOT/'skills/second-brain/references/answer-packet-rules.md').read_text()
        for phrase in ('adopted_claim', 'excluded_scope', 'original_card_ref', '只用于审计',
                       '不能因为隔离原卡字段就省略限制', '作者字段有值不等于', '系统延伸'):
            self.assertIn(phrase, rules)


if __name__ == '__main__':
    unittest.main()
