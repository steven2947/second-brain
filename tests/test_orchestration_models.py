"""验证知识调用的数据契约与可配置策略边界。"""
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from src.orchestration.models import SCHEMA_ROOT, validate_document
from src.orchestration.policy import DEFAULT_POLICY, load_policy


def valid_request():
    """返回可复用的最小调用请求。"""
    return {
        "schema_version": 1,
        "question": "面对一个模糊任务，应该如何开始？",
        "goal": "act",
        "facts": ["任务尚未拆分"],
        "constraints": ["今天需要开始"],
        "assumptions": [],
        "query_expansions": ["模糊任务 最小步骤"],
    }


class OrchestrationModelTests(unittest.TestCase):
    """外部输入必须经过严格 Schema，策略不能削弱硬规则。"""

    def test_request_rejects_empty_question_unknown_mode_and_excess_expansions(self):
        request = valid_request()
        validate_document("call-request.schema.json", request)

        for mutation in (
            {"question": ""},
            {"mode": "unbounded"},
            {"query_expansions": ["一", "二", "三", "四"]},
        ):
            invalid = {**request, **mutation}
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "INVALID_CALL_REQUEST"):
                validate_document("call-request.schema.json", invalid)

    def test_request_rejects_wrong_fact_and_assumption_types(self):
        for mutation in ({"facts": "不是数组"}, {"assumptions": [3]}):
            invalid = {**valid_request(), **mutation}
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "INVALID_CALL_REQUEST"):
                validate_document("call-request.schema.json", invalid)

    def test_all_call_schemas_are_valid_draft_2020_12(self):
        for filename in (
            "call-request.schema.json",
            "call-session.schema.json",
            "analysis-draft.schema.json",
            "answer-packet.schema.json",
        ):
            with self.subTest(filename=filename):
                schema = json.loads((SCHEMA_ROOT / filename).read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)

    def test_policy_loads_three_bounded_modes(self):
        policy = load_policy()
        self.assertEqual(policy["default_mode"], "standard")
        self.assertEqual(set(policy["modes"]), {"quick", "standard", "deep"})
        for values in policy["modes"].values():
            self.assertLessEqual(values["final_limit"], values["recall_limit"])
            self.assertLessEqual(values["recall_limit"], 50)
            self.assertIn(values["relation_hops"], (0, 1, 2, 3))

    def test_policy_rejects_unknown_fields_and_hard_rule_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            for extra in (
                {"typo_setting": True},
                {"require_evidence": False},
                {"allow_unverified_quotes": True},
            ):
                path.write_text(json.dumps({**DEFAULT_POLICY, **extra}), encoding="utf-8")
                with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, "INVALID_CALL_POLICY"):
                    load_policy(path)

    def test_policy_rejects_final_limit_above_recall_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            policy = json.loads(json.dumps(DEFAULT_POLICY))
            policy["modes"]["quick"]["recall_limit"] = 2
            policy["modes"]["quick"]["final_limit"] = 3
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "INVALID_CALL_POLICY"):
                load_policy(path)


if __name__ == "__main__":
    unittest.main()
