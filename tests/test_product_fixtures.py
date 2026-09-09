"""自编产品材料的结构、检索和历史重放检查；不代表真实授权或真实书籍质量验收。"""

import copy
import hashlib
import json
import unittest
import uuid
from pathlib import Path

from src.knowledge.library import Library, validate_library
from src.orchestration.intake import append_event, compile_request, problem_snapshot
from src.orchestration.policy import load_policy
from src.orchestration.session import create_call_session
from src.retrieval.search import SearchEngine


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "server/tests/fixtures/product_demo"
ORIGINAL_SUITE_SHA256 = "32fc53e3518087f983e1ee13a629c9cc2ab5c6bd3fa5ad0a7ffd737c0a4e51bf"


class ProductFixtureTests(unittest.TestCase):
    """只检查静态测试材料及调用层真实接口，不实现权限服务。"""

    def fixture(self, relative):
        """self 为测试实例；relative 为材料目录内的相对文件路径。"""
        path = FIXTURES / relative
        self.assertTrue(path.is_file(), f"缺少产品测试材料：{relative}")
        return json.loads(path.read_text(encoding="utf-8"))

    def library(self, release):
        """self 为测试实例；release 为自编 release 目录名。"""
        self.fixture(f"{release}/manifest.json")
        return Library(FIXTURES / release)

    def test_personas_and_expected_grants_are_unique_and_explicit(self):
        """self 为测试实例；校验预期权限材料的引用，不检验服务端授权。"""
        data = self.fixture("personas.json")
        self.assertTrue(data["is_example"])
        self.assertEqual(data["purpose"], "预期授权矩阵；不是授权实现或安全测试结果")
        personas = {item["label"]: item for item in data["personas"]}
        self.assertEqual(set(personas), {"A", "B", "C"})
        ids = [item["id"] for item in data["personas"]]
        self.assertEqual(len(set(ids)), 3)
        for person in data["personas"]:
            self.assertEqual(str(uuid.UUID(person["id"])), person["id"])
            self.assertTrue(person["email"].endswith("@example.test"))
            self.assertNotIn("password", person)
        self.assertEqual(len({p["email"] for p in data["personas"]}), 3)
        releases = {item["label"]: item for item in data["releases"]}
        self.assertEqual(set(releases), {"releaseA", "releaseB"})
        for label, release in releases.items():
            self.assertEqual(str(uuid.UUID(release["id"])), release["id"])
            self.assertEqual(self.library(label).manifest["library_id"], release["library_id"])
        grants = data["expected_grants"]
        self.assertEqual(len({g["id"] for g in grants}), 2)
        for grant in grants:
            self.assertEqual(str(uuid.UUID(grant["id"])), grant["id"])
        self.assertEqual({(g["user_id"], g["release_id"]) for g in grants}, {
            (personas["A"]["id"], releases["releaseA"]["id"]),
            (personas["B"]["id"], releases["releaseB"]["id"]),
        })
        self.assertEqual(data["expected_no_grants"], [personas["C"]["id"]])
        self.assertEqual(data["expected_access"], [
            {"user_id": personas[label]["id"], "release_id": releases[release]["id"],
             "allowed": (label, release) in {("A", "releaseA"), ("B", "releaseB")}}
            for label in ("A", "B", "C") for release in ("releaseA", "releaseB")
        ])

    def test_releases_validate_with_disjoint_ids_and_exact_evidence(self):
        """self 为测试实例；用实际库验证来源摘要、字符锚点和独立命名。"""
        libraries = [self.library(label) for label in ("releaseA", "releaseB")]
        id_sets = []
        for library in libraries:
            self.assertTrue(library.manifest["is_example"])
            self.assertEqual(validate_library(library.root)["cards"], len(library.cards))
            for book in library.list_books():
                self.assertEqual(book["author"], "自编测试材料")
                self.assertEqual(book["status"], "example_only")
            for ev in library.evidence.values():
                source = (library.root / ev["source_path"]).read_bytes()
                self.assertEqual(hashlib.sha256(source).hexdigest(), ev["source_sha256"])
                self.assertEqual(source.decode("utf-8")[ev["start"]:ev["end"]], ev["text"])
                self.assertEqual(library.get_evidence(ev["id"])["text"], ev["text"])
            id_sets.append(set(library.cards) | set(library.evidence) |
                           {b["id"] for b in library.list_books()})
        self.assertFalse(id_sets[0] & id_sets[1])
        self.assertNotEqual(libraries[0].version, libraries[1].version)
        self.assertEqual(len(libraries[0].list_books()), 2)
        self.assertEqual(len({b["author_id"] for b in libraries[0].list_books()}), 2)

    def test_counter_method_really_limits_action_across_two_books(self):
        """self 为测试实例；验证反方关系与两端的实际证据和方法边界。"""
        library = self.library("releaseA")
        method = library.get_knowledge("knowledge.product-a.reversible-trial")
        counter = library.get_knowledge("knowledge.product-a.stop-irreversible")
        self.assertEqual(method["kind"], "method")
        self.assertEqual(counter["kind"], "principle")
        self.assertNotEqual(method["book_id"], counter["book_id"])
        edges = library.get_related(method["id"], relation_type="limited_by", direction="out")
        self.assertEqual(len(edges), 1)
        edge = edges[0]["edge"]
        self.assertEqual(edge["to"], counter["id"])
        self.assertEqual(edge["basis"], "inference")
        self.assertEqual(set(edge["evidence_ids"]), set(method["evidence_ids"] + counter["evidence_ids"]))
        self.assertIn("不可逆", " ".join(method["boundaries"]))
        self.assertIn("停止", counter["statement"])
        for evidence_id in edge["evidence_ids"]:
            self.assertIn("不可逆", library.get_evidence(evidence_id)["text"])

    def test_keyword_scenarios_have_real_empty_and_counter_results(self):
        """self 为测试实例；真实关键词检索验证覆盖不足、反方召回及独立标记。"""
        scenarios = self.fixture("scenarios.json")
        libraries = {name: self.library(name) for name in ("releaseA", "releaseB")}
        for case in scenarios["retrieval_cases"]:
            with self.subTest(case=case["id"]):
                request = case["request"]
                library = libraries[case["release"]]
                hits = SearchEngine(library).search(request["question"], mode="keyword",
                    expansions=request["query_expansions"], limit=10)
                self.assertEqual({h["card"]["id"] for h in hits}, set(case["expected_card_ids"]))
                session = create_call_session(library, request, "standard", load_policy(), "keyword")
                self.assertEqual({c["card_id"] for c in session["candidates"]}, set(case["expected_card_ids"]))
                self.assertEqual(session["status"], case["expected_status"])
                self.assertFalse(session["retrieval"]["degraded"])
        counter_case = next(c for c in scenarios["retrieval_cases"] if c["id"] == "counter-perspective")
        self.assertEqual(len({libraries["releaseA"].cards[c]["book_id"]
                             for c in counter_case["expected_card_ids"]}), 2)

    def test_three_and_five_round_states_replay_without_extra_questions(self):
        """self 为测试实例；逐事件重放旧三轮和新五轮，核验原答与上限。"""
        for name, limit in (("legacy-three", 3), ("current-five", 5)):
            with self.subTest(name=name):
                state = self.fixture(f"problem_states/{name}.json")
                transcript = self.fixture(f"transcripts/{name}.json")
                if limit == 3:
                    self.assertNotIn("clarification_limit", state)
                else:
                    self.assertEqual(state["clarification_limit"], 5)
                self.assertEqual(len(state["events"]), 2 * limit + 1)
                self.assertEqual(len(transcript["turns"]), limit)
                self.assertEqual(state["question"], transcript["question"])
                replay = {**state, "events": []}
                body = {k: v for k, v in replay.items() if k != "state_hash"}
                replay["state_hash"] = hashlib.sha256(json.dumps(
                    body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()).hexdigest()
                for index, turn in enumerate(transcript["turns"]):
                    ask, update = state["events"][2 * index:2 * index + 2]
                    self.assertEqual((ask["type"], update["type"]), ("ask", "user_update"))
                    self.assertEqual(ask["question"], turn["ask"])
                    self.assertEqual(update["source_message"], turn["user_answer"])
                    self.assertEqual(update["intent"], "answer")
                    replay = append_event(replay, ask, len(replay["events"]))
                    self.assertEqual(problem_snapshot(replay)["pending_question"], turn["ask"])
                    replay = append_event(replay, update, len(replay["events"]))
                    self.assertIsNone(problem_snapshot(replay)["pending_question"])
                with self.assertRaisesRegex(ValueError, "CLARIFICATION_LIMIT"):
                    append_event(replay, {"type": "ask", "question": "能否再补一轮？",
                        "reason": "测试必须拒绝越过已有上限。"}, len(replay["events"]))
                self.assertEqual(state["events"][-1]["type"], "prepare")
                replay = append_event(replay, state["events"][-1], len(replay["events"]))
                self.assertEqual(replay, state)
                before = copy.deepcopy(state)
                snapshot = problem_snapshot(state)
                self.assertEqual(snapshot["clarification_limit"], limit)
                request = compile_request(state)
                self.assertEqual(request["context"]["clarification_rounds"], limit)
                self.assertEqual(request["context"]["stop_reason"], "round_limit")
                self.assertEqual(request["context"]["revision"], 2 * limit + 1)
                self.assertEqual(state, before)

    def test_original_five_class_suite_is_unchanged(self):
        """self 为测试实例；锁定原题集字节，不宣称原五类真实评审已通过。"""
        self.assertEqual(hashlib.sha256((ROOT / "tests/call-v2-effect-suite.json").read_bytes()).hexdigest(),
                         ORIGINAL_SUITE_SHA256)


if __name__ == "__main__":
    unittest.main()
