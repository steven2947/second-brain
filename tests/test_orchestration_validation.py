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


def valid_v2_draft(session):
    """返回完整知识推演草稿；每张入席卡都有原理、机制、用户映射和独立判断。"""
    decisions = []
    for index, candidate in enumerate(session["candidates"]):
        decisions.append({
            "card_id": candidate["card_id"],
            "decision": "admit",
            "reason_code": "relevant",
            "reason": "直接解释如何开始或如何复核。",
            "roles": ["support", "action_translator"] if index == 0 else ["boundary", "evidence_auditor"],
            "principle": "把模糊目标变成可观察动作，再根据结果减少不确定性。",
            "principle_gap": False,
            "mechanism": "可观察的小动作会产生反馈，反馈可用来校正下一步。",
            "assumptions": ["任务可以拆成一个不伤害整体方向的小步骤。"],
            "user_context_refs": [{"kind": "fact", "index": 0}, {"kind": "constraint", "index": 0}],
            "situation_mapping": "用户的任务尚未拆分，而且今天需要开始。",
            "fit": "direct",
            "independent_judgment": "单独使用这张卡，也会建议先做一个可检查动作。",
            "confidence": "high",
            "judgment_effect": "支持先完成一个可检查动作，而不是继续抽象规划。",
            "non_applicable_conditions": ["如果当前目标本身有重大不可逆风险，需先审查目标。"],
            "misuse_risks": ["只拆步骤而不校验方向，可能更高效地做错事。"],
        })
    admitted = [item["card_id"] for item in decisions]
    return {
        "schema_version": 2,
        "session_id": session["session_id"],
        "library_version": session["library_version"],
        "problem_framing": {
            "surface_question": "今天应该如何开始模糊任务？",
            "reframed_question": "哪个最小动作能产生足以校正下一步的信息？",
            "diagnostic_summary": "真正缺少的不是更多计划，而是能够降低不确定性的反馈。",
            "key_uncertainties": ["任务最终目标是否正确。"],
            "hidden_assumptions": ["任务可以拆成一个不伤害整体方向的小步骤。"],
            "confidence": "medium",
        },
        "decisions": decisions,
        "knowledge_groups": [{
            "title": "启动与校正",
            "purpose": "解释如何开始，同时避免盲目执行。",
            "card_ids": admitted,
            "synthesis": "小步骤产生反馈，复核利用反馈校正方向。",
            "open_questions": ["任务最终目标是否值得继续？"],
        }],
        "argument_relations": [{
            "type": "complement",
            "from_card_ids": admitted,
            "to_claim": "先行动，再用反馈校正。",
            "explanation": "小步骤负责启动，复核负责防止盲目执行。"
        }],
        "roundtable": {
            "support": {"status": "represented", "claim": "先做可检查的最小动作。", "card_ids": admitted[:1]},
            "opposition": {"status": "gap", "claim": "当前书库未找到直接反对开始行动的证据。", "card_ids": []},
            "alternative": {"status": "gap", "claim": "当前书库未找到更强替代路线。", "card_ids": []},
            "evidence_audit": {"status": "represented", "claim": "行动后必须检查不确定性是否下降。", "card_ids": admitted[-1:]}
        },
        "system_syntheses": [{
            "title": "把第一步当成信息实验",
            "type": "new_option",
            "content": "第一步不仅要可完成，还要优先选择能改变后续判断的动作。",
            "basis_card_ids": admitted,
            "confidence": "medium",
            "validation_needed": "检查动作完成后是否真的减少了一个关键未知。",
        }],
        "verdict": {
            "conclusion": "先定义一个今天能完成的小步骤，完成后检查不确定性是否下降。",
            "reasoning_summary": "用户需要今天启动，小步骤能生成反馈，复核可防止动作偏离目标。",
            "basis_card_ids": admitted,
            "decisive_user_context_refs": [{"kind": "fact", "index": 0}, {"kind": "constraint", "index": 0}],
            "consensus": ["任务需先转化为可观察动作。"],
            "disagreements": ["当前没有真实反方，只能保留目标可能错误的边界。"],
            "uncertainties": ["尚不知道任务最终目标是否正确。"],
            "confidence": "medium",
            "change_conditions": ["如果第一步没有产生可用反馈，改为先重新定义目标。"]
        },
        "actions": [{
            "step": "列出今天要处理的三个文件。",
            "basis_card_ids": admitted[:1],
            "completion_criteria": "清单中出现三个明确文件名。",
            "validation_signal": "下一步执行对象不再模糊。",
            "stop_condition": "如果列清单没有降低不确定性，就回到目标定义。"
        }],
        "learning_takeaways": [{
            "method": "最小动作—反馈校正法",
            "how_to_reuse": "以后遇到模糊任务，先找一个能在当天产生信息的小动作，再用结果决定下一步。",
            "basis_card_ids": admitted
        }],
        "continuation_options": [{
            "intent": "diagnose",
            "title": "继续检查目标",
            "description": "补充任务目标和不可逆风险，判断是否应该先做目标审查。",
            "next_move": "请用户补充这项任务希望改变的结果。",
            "basis_card_ids": admitted,
        }],
        "next_chat_action": {
            "intent": "diagnose",
            "reason": "任务最终目标仍是当前最关键的未知。",
            "prompt": "请继续诊断这项任务的真正目标，最多问我三个会改变判断的问题。",
        },
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

    def test_v2_builds_explainable_deliberation_packet(self):
        packet = build_answer_packet(self.library, self.session, valid_v2_draft(self.session), self.policy)
        self.assertEqual(packet["schema_version"], 2)
        self.assertEqual(packet["call_ledger"]["books_with_candidates"], ["book.demo"])
        self.assertTrue(packet["argument_relations"])
        self.assertTrue(packet["problem_framing"])
        self.assertEqual(packet["knowledge_groups"][0]["card_ids"], [
            item["card_id"] for item in self.session["candidates"]
        ])
        self.assertTrue(packet["system_syntheses"])
        self.assertEqual(packet["roundtable"]["opposition"]["status"], "gap")
        self.assertTrue(packet["learning_takeaways"])
        self.assertEqual(packet["continuation_options"][0]["intent"], "diagnose")
        self.assertEqual(packet["next_chat_action"]["intent"], "diagnose")
        witness = packet["witness_cards"][0]
        for field in ("mechanism", "user_context_refs", "fit", "independent_judgment", "misuse_risks"):
            with self.subTest(field=field):
                self.assertIn(field, witness)

    def test_v2_rejects_principle_gap_and_unbound_user_context(self):
        draft = valid_v2_draft(self.session)
        draft["decisions"][0]["principle_gap"] = True
        with self.assertRaisesRegex(ValueError, "v2 .*原理缺口"):
            build_answer_packet(self.library, self.session, draft, self.policy)

        draft = valid_v2_draft(self.session)
        draft["decisions"][0]["user_context_refs"] = [{"kind": "fact", "index": 99}]
        with self.assertRaisesRegex(ValueError, "用户上下文引用越界"):
            build_answer_packet(self.library, self.session, draft, self.policy)

    def test_v2_rejects_unadmitted_roundtable_and_learning_sources(self):
        draft = valid_v2_draft(self.session)
        draft["roundtable"]["support"]["card_ids"] = ["knowledge.missing"]
        with self.assertRaisesRegex(ValueError, "圆桌席位"):
            build_answer_packet(self.library, self.session, draft, self.policy)

        draft = valid_v2_draft(self.session)
        draft["learning_takeaways"][0]["basis_card_ids"] = ["knowledge.missing"]
        with self.assertRaisesRegex(ValueError, "学习收获"):
            build_answer_packet(self.library, self.session, draft, self.policy)

    def test_v2_requires_all_admitted_cards_grouped_and_checks_free_synthesis_sources(self):
        draft = valid_v2_draft(self.session)
        draft["knowledge_groups"][0]["card_ids"] = draft["knowledge_groups"][0]["card_ids"][:1]
        with self.assertRaisesRegex(ValueError, "每张采用卡必须进入"):
            build_answer_packet(self.library, self.session, draft, self.policy)

        draft = valid_v2_draft(self.session)
        draft["system_syntheses"][0]["basis_card_ids"] = ["knowledge.missing"]
        with self.assertRaisesRegex(ValueError, "系统综合"):
            build_answer_packet(self.library, self.session, draft, self.policy)

        draft = valid_v2_draft(self.session)
        draft["continuation_options"][0]["basis_card_ids"] = ["knowledge.missing"]
        with self.assertRaisesRegex(ValueError, "继续路径"):
            build_answer_packet(self.library, self.session, draft, self.policy)

    def test_v2_allows_no_system_synthesis_when_no_honest_cognitive_delta_exists(self):
        draft = valid_v2_draft(self.session)
        draft["system_syntheses"] = []
        packet = build_answer_packet(self.library, self.session, draft, self.policy)
        self.assertEqual(packet["system_syntheses"], [])

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

    def test_validation_must_use_same_policy_snapshot(self):
        changed = copy.deepcopy(self.policy)
        changed["show_rejected_candidates"] = False
        with self.assertRaisesRegex(ValueError, "INVALID_ANALYSIS_DRAFT.*策略"):
            build_answer_packet(self.library, self.session, valid_draft(self.session), changed)


if __name__ == "__main__":
    unittest.main()
