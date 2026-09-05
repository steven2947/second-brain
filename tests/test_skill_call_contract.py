"""检查通用 Skill 已接入真实调用命令和可解释答案结构。"""
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class SkillCallContractTests(unittest.TestCase):
    """文档命令必须存在，Skill 不能退回只靠搜索摘要回答。"""

    def test_skill_requires_validated_answer_packet_and_explanation_sections(self):
        skill = (ROOT / "skills/second-brain/SKILL.md").read_text(encoding="utf-8")
        workflow = (ROOT / "skills/second-brain/references/query-workflow.md").read_text(encoding="utf-8")
        rules = (ROOT / "skills/second-brain/references/answer-packet-rules.md").read_text(encoding="utf-8")
        combined = skill + workflow + rules
        for phrase in ("analyze", "validate-analysis", "调用账单", "知识见证卡", "交叉验证", "综合裁决", "停止条件"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)
        self.assertIn("不得绕过验证器", skill)
        self.assertIn("不是模型隐藏思维链", rules)

    def test_documented_commands_exist_in_cli_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "src.interfaces.cli", "--help"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        self.assertIn("analyze", result.stdout)
        self.assertIn("validate-analysis", result.stdout)


if __name__ == "__main__":
    unittest.main()
