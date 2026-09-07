"""固定 v2 效果验收题，避免运行后按答案临时改题。"""
import json
import unittest
from pathlib import Path

from src.orchestration.models import validate_document
from tools.dev.audit_effect_answer import audit_answer
from tools.dev.materialize_effect_draft import materialize


SUITE = Path(__file__).with_name("call-v2-effect-suite.json")
DEPTH_PREVIEW = (Path(__file__).parents[1] / "data/jobs/effect-acceptance/personal-positioning-v2"
                 / "answer-depth-preview.md")
REMAINING_PREVIEWS = [
    Path(__file__).parents[1] / "data/jobs/effect-acceptance" / name / "answer-preview.md"
    for name in (
        "method-boundary", "cross-book-conflict", "psychology-evidence-audit",
        "out-of-scope-current-fact",
    )
]
FORMAL_CASE_DIRS = [
    Path(__file__).parents[1] / "data/jobs/effect-acceptance" / name
    for name in (
        "action-prioritization", "method-boundary", "cross-book-conflict",
        "psychology-evidence-audit", "out-of-scope-current-fact",
    )
]


class CallV2EffectSuiteTests(unittest.TestCase):
    def test_suite_keeps_five_distinct_cases_with_valid_requests(self):
        document = json.loads(SUITE.read_text(encoding="utf-8"))
        self.assertEqual(document["status"], "rework_required")
        self.assertEqual(len(document["cases"]), 5)
        self.assertEqual(len({case["id"] for case in document["cases"]}), 5)
        self.assertEqual(len({case["category"] for case in document["cases"]}), 5)
        for case in document["cases"]:
            validate_document("call-request.schema.json", case["request"])
            self.assertGreaterEqual(len(case["checks"]), 3)

    def test_depth_preview_keeps_books_explainable_and_invites_real_continuation(self):
        if not DEPTH_PREVIEW.exists():
            self.skipTest("真实本地金标准样例不随源码分发")
        preview = DEPTH_PREVIEW.read_text(encoding="utf-8")
        for phrase in (
            "这次调用的知识地图", "知识组一", "书中主张", "原理为什么成立",
            "两本书连接后得到什么", "系统综合", "继续诊断", "深入学习",
            "继续调用书库", "制作成执行材料",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, preview)
        self.assertGreaterEqual(preview.count("### 《"), 6)
        self.assertTrue(preview.rstrip().splitlines()[-1].startswith("继续和 AI 聊："))

    def test_every_effect_preview_ends_with_a_concrete_next_chat_instruction(self):
        if not DEPTH_PREVIEW.exists():
            self.skipTest("真实本地效果材料不随源码分发")
        action_preview = FORMAL_CASE_DIRS[0] / "answer-preview.md"
        for path in [DEPTH_PREVIEW, action_preview, *REMAINING_PREVIEWS]:
            with self.subTest(path=path):
                preview = path.read_text(encoding="utf-8")
                self.assertTrue(preview.rstrip().splitlines()[-1].startswith("继续和 AI 聊："))
                self.assertGreater(len(preview.rstrip().splitlines()[-1]), 30)

    def test_every_fixed_case_has_auditable_artifacts_and_authored_sources(self):
        if not all(path.exists() for path in FORMAL_CASE_DIRS):
            self.skipTest("真实本地效果材料不随源码分发")
        required = {
            "request.json", "session.json", "analysis-spec.json",
            "analysis-draft.json", "answer-packet.json", "answer-preview.md",
            "manual-review.md",
        }
        for case_dir in FORMAL_CASE_DIRS:
            with self.subTest(case=case_dir.name):
                self.assertTrue(required.issubset({path.name for path in case_dir.iterdir()}))
                session = json.loads((case_dir / "session.json").read_text(encoding="utf-8"))
                draft = json.loads((case_dir / "analysis-draft.json").read_text(encoding="utf-8"))
                packet = json.loads((case_dir / "answer-packet.json").read_text(encoding="utf-8"))
                validate_document("analysis-draft.v2.schema.json", draft)
                validate_document("answer-packet.v2.schema.json", packet)
                self.assertEqual(len(session["candidates"]), len(draft["decisions"]))
                for witness in packet["witness_cards"]:
                    self.assertTrue(witness["book_title"])
                    self.assertTrue(witness["author"])
                    self.assertTrue(witness["principle"])
                    self.assertTrue(witness["mechanism"])

    def test_revised_case_uses_the_same_request_and_explicit_decisions(self):
        original = FORMAL_CASE_DIRS[0]
        revision = original / "revision-2"
        if not (revision / "answer-packet.json").exists():
            self.skipTest("真实本地返工样例不随源码分发")
        session = json.loads((original / "session.json").read_text(encoding="utf-8"))
        spec = json.loads((revision / "analysis-spec.json").read_text(encoding="utf-8"))
        draft = json.loads((revision / "analysis-draft.json").read_text(encoding="utf-8"))
        packet = json.loads((revision / "answer-packet.json").read_text(encoding="utf-8"))
        suite = json.loads(SUITE.read_text(encoding="utf-8"))
        self.assertEqual(session["request"], suite["cases"][0]["request"])
        self.assertEqual(materialize(session, spec), draft)
        self.assertEqual(packet["session_id"], session["session_id"])
        validate_document("answer-packet.v2.schema.json", packet)
        answer = (revision / "answer-preview.md").read_text(encoding="utf-8")
        report = audit_answer(packet, answer)
        self.assertTrue(report["mechanical_pass"], report)


if __name__ == "__main__":
    unittest.main()
