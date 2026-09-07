"""自编场景验证澄清状态、检索接入和旧接口兼容；不把机制通过视为真实回答质量。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.knowledge.library import Library
from src.orchestration.intake import append_event, compile_request, create_problem, problem_snapshot
from src.orchestration.policy import load_policy
from src.orchestration.session import create_call_session
from src.orchestration.validation import build_answer_packet
from tests.test_orchestration_cli import run_cli
from tests.test_orchestration_validation import valid_draft, valid_v2_draft


ROOT = Path(__file__).parents[1]
LIBRARY = ROOT / "examples/sample-library"


def apply(state, event):
    """state 为测试档案，event 为一条事件；使用当前事件数作为并发版本。"""
    return append_event(state, event, len(state["events"]))


def ask(question="你目前卡在哪个具体环节？"):
    """question 为自由生成的测试问题，附上为什么值得问。"""
    return {"type": "ask", "question": question, "reason": "答案会改变需要查找的方法。"}


def update(changes=None, intent="answer", message="任务尚未拆分，需要今天开始。"):
    """changes 为最新字段值，intent 为 AI 识别的意图，message 为自编用户原消息。"""
    return {"type": "user_update", "source_message": message, "intent": intent,
            "changes": changes or {}, "reason": "根据本轮用户说明更新，未涉及字段保留。"}


def prepare(focus="模糊任务 小步骤", expansions=None):
    """focus 为基于当前快照的检索重点，expansions 为自由补充角度。"""
    return {"type": "prepare", "retrieval_focus": focus, "query_expansions": expansions or [],
            "reason": "已有信息足以给出带边界的分析。"}


class IntakeTests(unittest.TestCase):
    """0轮、提前结束、3轮上限、用户主动深化和同题检索差异。"""

    def test_zero_rounds_compiles_outcome_separately_from_task_type(self):
        state = apply(create_problem("如何推进？", "act"), update({
            "desired_outcome": "今天完成可验收成果", "facts": ["任务尚未拆分"],
            "constraints": ["今天开始"], "unknowns": ["不知道最终交付给谁"],
            "assumptions": ["暂时假设交付对象不改变方法"],
        }))
        state = apply(state, prepare())
        request = compile_request(state)
        self.assertEqual(request["goal"], "act")
        self.assertEqual(request["context"]["desired_outcome"], "今天完成可验收成果")
        self.assertEqual(request["context"]["clarification_rounds"], 0)
        self.assertIn("今天完成可验收成果", request["query_expansions"][0])
        self.assertNotIn("不知道最终交付给谁", request["facts"])
        self.assertNotIn("暂时假设", request["query_expansions"][0])

    def test_two_rounds_stop_early_and_keep_history(self):
        state = create_problem("三个方向如何选？")
        for question in ("你希望先得到什么结果？", "有谁已经向你提出过具体需求？"):
            state = apply(apply(state, ask(question)), update())
        old = copy.deepcopy(state)
        ready = apply(state, prepare())
        self.assertEqual(state, old)
        self.assertEqual(ready["events"][:-1], old["events"])
        self.assertEqual(problem_snapshot(ready)["clarification_rounds"], 2)
        with self.assertRaisesRegex(ValueError, "INTAKE_CLOSED"):
            apply(ready, ask("换个圆桌角色再问背景？"))

    def test_three_round_limit_survives_rephrasing_and_supplement(self):
        state = create_problem("如何选择？")
        for index in range(3):
            state = apply(apply(state, ask(f"当前关键问题{index}是什么？")), update())
        with self.assertRaisesRegex(ValueError, "CLARIFICATION_LIMIT"):
            apply(state, ask("换个说法再问一次？"))
        state = apply(state, prepare())
        state = apply(state, update({"facts": ["用户自发补充新事实"]}, "supplement"))
        self.assertEqual(problem_snapshot(state)["clarification_rounds"], 3)
        with self.assertRaisesRegex(ValueError, "INTAKE_NOT_READY"):
            compile_request(state)
        with self.assertRaisesRegex(ValueError, "CLARIFICATION_LIMIT"):
            apply(state, ask("补充后是否能重新开始问？"))
        state = apply(state, prepare("新事实 检查不确定性"))
        self.assertEqual(compile_request(state)["context"]["stop_reason"], "round_limit")

    def test_wait_for_user_including_third_question(self):
        state = create_problem("如何选择？")
        for index in range(3):
            state = apply(state, ask(f"问题{index}？"))
            with self.assertRaisesRegex(ValueError, "AWAITING_USER"):
                apply(state, prepare())
            if index < 2:
                with self.assertRaisesRegex(ValueError, "AWAITING_USER"):
                    apply(state, ask("不能在同一轮连续发问"))
            state = apply(state, update())
        self.assertTrue(problem_snapshot(apply(state, prepare()))["ready"])

    def test_user_requests_analysis_or_does_not_know(self):
        for intent in ("analyze_now", "unknown"):
            with self.subTest(intent=intent):
                state = apply(apply(create_problem("如何选择？"), ask()), update(intent=intent))
                with self.assertRaisesRegex(ValueError, "INTAKE_CLOSED"):
                    apply(state, ask("仍然要补齐？"))
                state = apply(state, prepare())
                self.assertEqual(compile_request(state)["context"]["stop_reason"], intent)

    def test_invalid_events_repeated_questions_and_tampering_rejected(self):
        state = create_problem("如何选择？")
        for event in ({**ask(), "rounds": 0}, ask("  "), update({"fake_fact": "x"})):
            with self.subTest(event=event), self.assertRaisesRegex(ValueError, "INVALID_INTAKE_EVENT"):
                apply(state, event)
        state = apply(apply(state, ask()), update())
        with self.assertRaisesRegex(ValueError, "REPEATED_QUESTION"):
            apply(state, ask())
        with self.assertRaisesRegex(ValueError, "REVISION_CONFLICT"):
            append_event(state, prepare(), 0)
        damaged = copy.deepcopy(state)
        damaged["events"].clear()
        with self.assertRaisesRegex(ValueError, "INVALID_PROBLEM_STATE"):
            problem_snapshot(damaged)

    def test_fact_correction_keeps_original_message_and_requires_new_focus(self):
        state = apply(create_problem("怎么做？"), update({"facts": ["对方愿意付费"]}))
        state = apply(state, prepare("付费交付"))
        state = apply(state, update({"facts": ["对方只愿意免费试用"]}, "supplement", "刚确认，他只接受免费。"))
        self.assertEqual(state["events"][0]["changes"]["facts"], ["对方愿意付费"])
        self.assertEqual(state["events"][-1]["source_message"], "刚确认，他只接受免费。")
        self.assertEqual(problem_snapshot(state)["facts"], ["对方只愿意免费试用"])
        with self.assertRaisesRegex(ValueError, "INTAKE_NOT_READY"):
            compile_request(state)

    def test_same_original_question_changes_actual_search_and_keeps_old_session(self):
        library, policy = Library(LIBRARY), load_policy()
        state = apply(create_problem("怎样推进？", "act"), update({
            "facts": ["任务尚未拆分"], "constraints": ["今天开始"],
        }))
        state = apply(state, prepare("模糊任务"))
        first = create_call_session(library, compile_request(state), "standard", policy, "keyword")
        original = copy.deepcopy(first)
        state = apply(state, update({"facts": ["已经执行过动作，需要检查不确定性"]}, "supplement"))
        state = apply(state, prepare("不确定性"))
        second = create_call_session(library, compile_request(state, first), "standard", policy, "keyword")
        self.assertEqual(first, original)
        self.assertEqual(first["request"]["question"], second["request"]["question"])
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertEqual(second["request"]["context"]["previous_session_id"], first["session_id"])
        self.assertEqual([c["card_id"] for c in first["candidates"]], ["knowledge.demo.small-step"])
        # 宽召回仍可保留旧的关联卡；检验新知识进入并成为首项，而非强制只返回一张。
        self.assertEqual(second["candidates"][0]["card_id"], "knowledge.demo.review")
        self.assertNotEqual([c["card_id"] for c in first["candidates"]],
                            [c["card_id"] for c in second["candidates"]])
        self.assertIn("不确定性", second["retrieval"]["queries"][1])

    def test_context_survives_v1_and_v2_packet_without_losing_explanation(self):
        state = apply(create_problem("面对模糊任务，如何开始并检查进展？", "act"), update({
            "facts": ["任务尚未拆分"], "constraints": ["今天需要开始"],
            "desired_outcome": "今天有可检查的进展", "unknowns": ["最终交付对象待确认"],
        }))
        state = apply(state, prepare("模糊任务 检查不确定性"))
        library, policy = Library(LIBRARY), load_policy()
        session = create_call_session(library, compile_request(state), "standard", policy, "keyword")
        for factory in (valid_draft, valid_v2_draft):
            packet = build_answer_packet(library, session, factory(session), policy)
            self.assertEqual(packet["problem"]["context"], session["request"]["context"])
            self.assertTrue(packet["witness_cards"])
            self.assertTrue(packet["actions"])
            if packet["schema_version"] == 2:
                for key in ("knowledge_groups", "roundtable", "learning_takeaways", "next_chat_action"):
                    self.assertTrue(packet[key])

    def test_previous_session_must_match_problem_and_be_older(self):
        state = apply(create_problem("怎么推进？"), prepare())
        session = create_call_session(Library(LIBRARY), compile_request(state), "standard", load_policy(), "keyword")
        with self.assertRaisesRegex(ValueError, "PROBLEM_SESSION_MISMATCH"):
            compile_request(state, session)
        unrelated = apply(create_problem("同样的措辞也不等于同一档案"), prepare())
        unrelated = apply(unrelated, prepare())
        with self.assertRaisesRegex(ValueError, "PROBLEM_SESSION_MISMATCH"):
            compile_request(unrelated, session)
        state = apply(state, prepare())
        damaged = copy.deepcopy(session)
        damaged["request"]["facts"] = ["伪造旧事实"]
        with self.assertRaisesRegex(ValueError, "INVALID_CALL_SESSION"):
            compile_request(state, damaged)

    def test_diverged_history_cannot_claim_previous_session(self):
        state = create_problem("如何推进？")
        first = apply(state, prepare("模糊任务"))
        session = create_call_session(Library(LIBRARY), compile_request(first), "standard", load_policy(), "keyword")
        divergent = apply(apply(state, prepare("不确定性")), prepare("再检查"))
        with self.assertRaisesRegex(ValueError, "PROBLEM_SESSION_MISMATCH"):
            compile_request(divergent, session)

    def test_six_expansions_and_long_context_reach_search(self):
        state = apply(create_problem("如何选择？"), update({"desired_outcome": "目标" * 500}))
        state = apply(state, prepare("模糊任务" * 200, ["反例", "边界", "目标", "反馈", "替代"] ))
        request = compile_request(state)
        self.assertEqual(len(request["query_expansions"]), 6)
        self.assertGreater(len(request["query_expansions"][0]), 1000)
        session = create_call_session(Library(LIBRARY), request, "standard", load_policy(), "keyword")
        self.assertEqual(len(session["retrieval"]["queries"]), 7)


class IntakeCliTests(unittest.TestCase):
    """持久化入口不依赖书库；修订冲突和失败不得改写旧文件。"""

    def test_persistent_cli_lifecycle_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state, event, session = root / "problem.json", root / "event.json", root / "session.json"
            start = ["intake-start", "--question", "如何推进？", "--output", str(state)]
            self.assertEqual(run_cli(start)[0], 0)
            original = state.read_bytes()
            self.assertIn("OUTPUT_EXISTS", run_cli(start)[2])
            self.assertEqual(state.read_bytes(), original)
            self.assertEqual(run_cli(["intake-show", "--state", str(state)])[1]["result"]["revision"], 0)
            event.write_text(json.dumps(prepare()), encoding="utf-8")
            args = ["intake-update", "--state", str(state), "--event", str(event), "--expected-revision", "0"]
            self.assertEqual(run_cli(args)[0], 0)
            prepared_bytes = state.read_bytes()
            self.assertIn("REVISION_CONFLICT", run_cli(args)[2])
            self.assertEqual(state.read_bytes(), prepared_bytes)
            analyze = ["--library", str(LIBRARY), "analyze", "--problem", str(state),
                       "--retrieval-mode", "keyword", "--output", str(session)]
            self.assertEqual(run_cli(analyze)[0], 0)
            self.assertEqual(state.read_bytes(), prepared_bytes)
            original_session = session.read_bytes()
            self.assertIn("OUTPUT_EXISTS", run_cli(analyze)[2])
            self.assertIn("保留旧会话", run_cli(analyze + ["--replace"])[2])
            self.assertEqual(session.read_bytes(), original_session)
            # 用户自发反馈之后必须重新 prepare，且轮数不重置。
            event.write_text(json.dumps(update({"facts": ["已经执行" ]}, "supplement")), encoding="utf-8")
            self.assertEqual(run_cli(args[:-1] + ["1"])[0], 0)
            self.assertIn("INTAKE_NOT_READY", run_cli(analyze)[2])
            event.write_text(json.dumps(prepare("不确定性")), encoding="utf-8")
            self.assertEqual(run_cli(args[:-1] + ["2"])[0], 0)
            next_session = root / "session-2.json"
            self.assertEqual(run_cli(analyze[:-1] + [str(next_session), "--previous-session", str(session)])[0], 0)
            self.assertEqual(json.loads(next_session.read_text())["request"]["context"]["previous_session_id"],
                             json.loads(session.read_text())["session_id"])

    def test_lock_contention_and_symlink_rejected_without_mutation(self):
        import fcntl
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state, event = root / "problem.json", root / "event.json"
            state.write_text(json.dumps(create_problem("怎样推进？")), encoding="utf-8")
            event.write_text(json.dumps(prepare()), encoding="utf-8")
            original = state.read_bytes()
            args = ["intake-update", "--state", str(state), "--event", str(event), "--expected-revision", "0"]
            with (root / "problem.json.lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertIn("PROBLEM_BUSY", run_cli(args)[2])
            link = root / "link.json"
            link.symlink_to(state)
            self.assertIn("INVALID_ARGUMENT", run_cli(["intake-show", "--state", str(link)])[2])
            self.assertEqual(state.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
