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
        for phrase in ("analyze", "validate-analysis", "调用账单", "知识见证卡", "原理解释",
                       "独立判断", "反方", "证据审计", "主持裁决", "改判条件", "停止条件",
                       "知识组", "系统综合", "继续路径", "隐藏假设", "继续和 AI 聊"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)
        self.assertIn("不得绕过验证器", skill)
        self.assertIn("不是模型隐藏思维链", rules)
        self.assertIn("三层渐进展示", rules)
        self.assertIn("用户只读这一层也能执行", skill)
        self.assertIn("《书名》｜作者｜知识名称", combined)
        self.assertIn("独立立场—交叉质询—主持裁决", combined)
        self.assertIn("系统延伸", rules)
        self.assertIn("不规定固定文案、固定专家数或固定分析框架", rules)
        self.assertIn("没有可靠认知增量时", skill)
        self.assertIn("analysis-draft.v2.schema.json", workflow)

    def test_documented_commands_exist_in_cli_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "src.interfaces.cli", "--help"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        self.assertIn("analyze", result.stdout)
        self.assertIn("validate-analysis", result.stdout)
        for command in ("intake-start", "intake-update", "intake-show"):
            self.assertIn(command, result.stdout)
        analyze_help = subprocess.run(
            [sys.executable, "-m", "src.interfaces.cli", "analyze", "--help"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        self.assertIn("--problem", analyze_help.stdout)
        self.assertIn("--previous-session", analyze_help.stdout)


if __name__ == "__main__":
    unittest.main()
