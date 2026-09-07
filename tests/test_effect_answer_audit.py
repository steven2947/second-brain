"""用自编数据复现遗漏淘汰理由、最终文案夹带未入席书籍的故障。"""
import unittest
from unittest.mock import patch

from tools.dev.audit_effect_answer import audit_answer
from tools.dev.materialize_effect_draft import SECTION_KEYS, materialize


class EffectAuditTests(unittest.TestCase):
    def test_rejected_book_in_prose_is_flagged(self):
        packet = {"witness_cards": [{"book_title": "自编方法"}],
                  "next_chat_action": {"prompt": "请继续分析具体条件。"}}
        answer = "《自编方法》与《未入席的书》都支持结论。\n继续和 AI 聊：请继续分析具体条件。"
        report = audit_answer(packet, answer)
        self.assertFalse(report["mechanical_pass"])
        self.assertEqual(report["unmatched_book_mentions"], ["未入席的书"])

    def test_edition_suffix_and_last_line(self):
        packet = {"witness_cards": [{"book_title": "自编方法（原书第3版）"}],
                  "next_chat_action": {"prompt": "请继续分析具体条件。"}}
        answer = "《自编方法》提供方法。\n继续和 AI 聊：请继续分析具体条件。"
        self.assertTrue(audit_answer(packet, answer)["mechanical_pass"])
        self.assertFalse(audit_answer(packet, answer + "\n附注")["mechanical_pass"])
        self.assertEqual(audit_answer(packet, answer)["semantic_status"], "not_evaluated")

    def test_missing_rejection_is_not_invented(self):
        session = {"candidates": [{"card_id": "a"}, {"card_id": "b"}]}
        spec = {key: [] for key in SECTION_KEYS}
        spec.update(admitted_decisions={"a": {}}, rejected_decisions={})
        with self.assertRaisesRegex(ValueError, "显式决定"):
            materialize(session, spec)

    def test_specific_rejection_survives_assembly(self):
        session = {"session_id": "s", "library_version": "v",
                   "candidates": [{"card_id": "a"}, {"card_id": "b"}]}
        spec = {key: [] for key in SECTION_KEYS}
        reason = {"reason_code": "condition_mismatch", "reason": "需要团队排班，当前为个人半小时任务。"}
        spec.update(admitted_decisions={"a": {}}, rejected_decisions={"b": reason})
        with patch("tools.dev.materialize_effect_draft.validate_document"):
            draft = materialize(session, spec)
        self.assertEqual(draft["decisions"][1], {"card_id": "b", "decision": "reject", **reason})


if __name__ == "__main__":
    unittest.main()
