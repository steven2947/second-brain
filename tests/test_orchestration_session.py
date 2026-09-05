"""验证固定知识版本的调用会话、宽召回与显式降级。"""
import unittest
from pathlib import Path
from unittest.mock import patch

from src.knowledge.library import Library
from src.orchestration.policy import load_policy
from src.orchestration.session import create_call_session


ROOT = Path(__file__).parents[1]


def request(question="如何处理一个模糊任务？", expansions=None):
    return {
        "schema_version": 1,
        "question": question,
        "goal": "act",
        "facts": ["任务还没有拆分"],
        "constraints": ["需要今天开始"],
        "assumptions": [],
        "query_expansions": ["模糊任务 小步骤"] if expansions is None else expansions,
    }


class OrchestrationSessionTests(unittest.TestCase):
    """调用会话必须可重复、完整，并且不把相似度当采用决定。"""

    def setUp(self):
        self.library = Library(ROOT / "examples/sample-library")
        self.policy = load_policy()

    def test_session_pins_version_and_assembles_evidence_relations(self):
        session = create_call_session(
            self.library, request(), "standard", self.policy, retrieval_mode="keyword"
        )
        repeated = create_call_session(
            self.library, request(), "standard", self.policy, retrieval_mode="keyword"
        )
        self.assertEqual(session, repeated)
        self.assertEqual(session["library_version"], self.library.version)
        self.assertEqual(session["policy"], self.policy)
        self.assertRegex(session["session_id"], r"^call\.[a-f0-9]{24}$")
        self.assertEqual(session["status"], "ready")
        self.assertEqual(session["retrieval"]["queries"], ["如何处理一个模糊任务？", "模糊任务 小步骤"])
        self.assertEqual(session["retrieval"]["books_searched"], ["book.demo"])
        self.assertFalse(session["retrieval"]["degraded"])
        self.assertTrue(session["candidates"])
        candidate = session["candidates"][0]
        self.assertEqual(candidate["status"], "pending")
        self.assertEqual(candidate["card_id"], candidate["card"]["id"])
        self.assertTrue(candidate["evidence"])
        self.assertIn("context_text", candidate["evidence"][0])
        self.assertTrue(any(item["edge"]["id"] == "relation.demo.step-review" for item in candidate["relations"]))

    def test_session_keeps_filters_and_returns_explicit_empty_status(self):
        empty = create_call_session(
            self.library,
            request("火星推进器铌合金", expansions=[]),
            "quick",
            self.policy,
            retrieval_mode="keyword",
        )
        self.assertEqual(empty["status"], "no_relevant_knowledge")
        self.assertEqual(empty["candidates"], [])

        filtered_request = {**request(), "filters": {"author": "missing"}}
        filtered = create_call_session(
            self.library, filtered_request, "quick", self.policy, retrieval_mode="keyword"
        )
        self.assertEqual(filtered["retrieval"]["filters"], {"author": "missing"})
        self.assertEqual(filtered["retrieval"]["books_searched"], [])

    def test_missing_vector_dependency_degrades_to_keyword_and_records_reason(self):
        original = __import__("src.retrieval.search", fromlist=["SearchEngine"]).SearchEngine.search
        calls = []

        def fail_then_keyword(engine, query, mode="hybrid", *args, **kwargs):
            calls.append(mode)
            if mode == "hybrid":
                raise ModuleNotFoundError("No module named 'fastembed'")
            return original(engine, query, mode, *args, **kwargs)

        with patch("src.orchestration.session.SearchEngine.search", new=fail_then_keyword):
            session = create_call_session(self.library, request(), "standard", self.policy)
        self.assertEqual(calls, ["hybrid", "keyword"])
        self.assertTrue(session["retrieval"]["degraded"])
        self.assertEqual(session["retrieval"]["mode"], "keyword")
        self.assertIn("fastembed", session["retrieval"]["degraded_reason"])


if __name__ == "__main__":
    unittest.main()
