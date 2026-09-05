"""验证分析草稿不能绕过候选、证据、边界与行动依据。"""
import copy
import unittest
from pathlib import Path

from src.knowledge.library import Library
from src.orchestration.policy import load_policy
from src.orchestration.session import create_call_session, session_id_for
from src.orchestration.validation import build_answer_packet


ROOT = Path(__file__).parents[1]


def call_request():
    return {
        "schema_version": 1,
        "question": "面对一个模糊任务，今天应该如何开始并检查进展？",
        "goal": "act",
        "facts": ["任务还没有拆分"],
        "constraints": ["今天需要开始"],
        "assumptions": [],
        "query_expansions": ["模糊任务 小步骤", "执行之后 检查不确定性"],
    }


def valid_draft(session):
    decisions = []
    for index, candidate in enumerate(session["candidates"]):
        decisions.append({
            "card_id": candidate["card_id"],
            "decision": "admit",
            "reason_code": "relevant",
            "reason": "直接提供开始或检查任务的方法。",
            "roles": ["support", "action_translator"] if index == 0 else ["boundary"],
            "principle": "把模糊目标变成可观察动作，再依据结果减少不确定性。",
            "principle_gap": False,
            "situation_mapping": "用户的任务尚未拆分，而且今天需要开始。",
            "judgment_effect": "支持先完成一个可检查动作，而不是继续抽象规划。",
        })
    admitted = [item["card_id"] for item in decisions]
    return {
        "schema_version": 1,
        "session_id": session["session_id"],
        "library_version": session["library_version"],
        "decisions": decisions,
        "cross_validation": {
            "agreements": [{"summary": "开始与复核形成闭环。", "card_ids": admitted}],
            "conflicts": [],
            "limitations": [{"summary": "小步骤不能替代目标判断。", "card_ids": admitted[:1]}],
            "alternatives": [],
            "evidence_gaps": [],
        },
        "verdict": {
            "conclusion": "先定义一个今天能完成的小步骤，并在完成后检查不确定性是否下降。",
            "basis_card_ids": admitted,
            "decisive_user_facts": ["任务尚未拆分", "今天需要开始"],
            "uncertainties": ["尚不知道任务最终目标是否正确"],
        },
        "actions": [{
            "step": "列出今天要处理的三个文件。",
            "basis_card_ids": admitted[:1],
            "completion_criteria": "清单中出现三个明确文件名。",
            "validation_signal": "下一步执行对象不再模糊。",
            "stop_condition": "如果列清单没有降低不确定性，就回到目标定义。",
        }],
    }


class OrchestrationValidationTests(unittest.TestCase):
    """答案包只允许从经过处理的真实候选和证据产生。"""

    def setUp(self):
        self.library = Library(ROOT / "examples/sample-library")
        self.policy = load_policy()
        self.session = create_call_session(
            self.library, call_request(), "standard", self.policy, retrieval_mode="keyword"
        )

    def test_valid_draft_builds_traceable_answer_packet(self):
        packet = build_answer_packet(self.library, self.session, valid_draft(self.session), self.policy)
        self.assertEqual(packet["session_id"], self.session["session_id"])
        self.assertEqual(packet["library_version"], self.library.version)
        self.assertEqual(len(packet["witness_cards"]), len(self.session["candidates"]))
        self.assertEqual(packet["call_ledger"]["admitted"], [item["card_id"] for item in self.session["candidates"]])
        self.assertTrue(packet["sources"])
        witness = packet["witness_cards"][0]
        self.assertIn("principle", witness)
        self.assertIn("conditions", witness)
        self.assertIn("boundaries", witness)
        self.assertIn("situation_mapping", witness)

    def test_every_candidate_requires_exactly_one_decision(self):
        draft = valid_draft(self.session)
        draft["decisions"].pop()
        with self.assertRaisesRegex(ValueError, "INVALID_ANALYSIS_DRAFT.*候选"):
            build_answer_packet(self.library, self.session, draft, self.policy)

        draft = valid_draft(self.session)
        draft["decisions"].append(copy.deepcopy(draft["decisions"][0]))
        with self.assertRaisesRegex(ValueError, "INVALID_ANALYSIS_DRAFT.*候选"):
            build_answer_packet(self.library, self.session, draft, self.policy)

    def test_unknown_basis_and_bad_quote_are_rejected(self):
        draft = valid_draft(self.session)
        draft["verdict"]["basis_card_ids"] = ["knowledge.missing"]
        with self.assertRaisesRegex(ValueError, "INVALID_ANALYSIS_DRAFT.*依据"):
            build_answer_packet(self.library, self.session, draft, self.policy)

        draft = valid_draft(self.session)
        draft["decisions"][0]["quote"] = {
            "evidence_id": self.session["candidates"][0]["evidence"][0]["id"],
            "text": "这段文字并不存在于证据中",
        }
        with self.assertRaisesRegex(ValueError, "INVALID_ANALYSIS_DRAFT.*引用"):
            build_answer_packet(self.library, self.session, draft, self.policy)

    def test_admitted_card_requires_principle_or_explicit_gap_and_mapping(self):
        draft = valid_draft(self.session)
        draft["decisions"][0]["principle"] = ""
        draft["decisions"][0]["principle_gap"] = False
        with self.assertRaisesRegex(ValueError, "INVALID_ANALYSIS_DRAFT.*原理"):
            build_answer_packet(self.library, self.session, draft, self.policy)

        draft = valid_draft(self.session)
        draft["decisions"][0]["principle"] = ""
        draft["decisions"][0]["principle_gap"] = True
        packet = build_answer_packet(self.library, self.session, draft, self.policy)
        self.assertTrue(packet["witness_cards"][0]["principle_gap"])

    def test_actions_require_admitted_basis_and_operational_checks(self):
        draft = valid_draft(self.session)
        draft["decisions"][0] = {
            "card_id": draft["decisions"][0]["card_id"],
            "decision": "reject",
            "reason_code": "lower_explanatory_value",
            "reason": "另一张卡足以支持答案。",
        }
        remaining = draft["decisions"][1]["card_id"]
        draft["cross_validation"]["agreements"] = [{"summary": "保留的卡片仍支持复核。", "card_ids": [remaining]}]
        draft["cross_validation"]["limitations"] = [{"summary": "仍需检查目标。", "card_ids": [remaining]}]
        draft["verdict"]["basis_card_ids"] = [remaining]
        with self.assertRaisesRegex(ValueError, "INVALID_ANALYSIS_DRAFT.*行动依据"):
            build_answer_packet(self.library, self.session, draft, self.policy)

        draft = valid_draft(self.session)
        draft["actions"][0]["stop_condition"] = ""
        with self.assertRaisesRegex(ValueError, "INVALID_ANALYSIS_DRAFT"):
            build_answer_packet(self.library, self.session, draft, self.policy)

    def test_deep_mode_must_use_available_boundary_role(self):
        session = create_call_session(
            self.library, call_request(), "deep", self.policy, retrieval_mode="keyword"
        )
        draft = valid_draft(session)
        for decision in draft["decisions"]:
            decision["roles"] = ["support"]
        with self.assertRaisesRegex(ValueError, "INVALID_ANALYSIS_DRAFT.*挑战/边界"):
            build_answer_packet(self.library, session, draft, self.policy)

    def test_changed_session_and_old_library_version_are_rejected(self):
        tampered = copy.deepcopy(self.session)
        tampered["candidates"][0]["card"]["statement"] = "被修改的候选内容"
        body = {key: value for key, value in tampered.items() if key != "session_id"}
        tampered["session_id"] = session_id_for(body)
        with self.assertRaisesRegex(ValueError, "INVALID_ANALYSIS_DRAFT.*知识库不一致"):
            build_answer_packet(self.library, tampered, valid_draft(tampered), self.policy)

        stale = copy.deepcopy(self.session)
        stale["library_version"] = "0" * 24
        body = {key: value for key, value in stale.items() if key != "session_id"}
        stale["session_id"] = session_id_for(body)
        draft = valid_draft(stale)
        with self.assertRaisesRegex(ValueError, "SOURCE_VERSION_MISMATCH"):
            build_answer_packet(self.library, stale, draft, self.policy)


if __name__ == "__main__":
    unittest.main()
