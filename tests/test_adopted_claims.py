"""采用边界的真实装配回归；仅使用自编示例，不改历史书库。"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.knowledge.library import Library
from src.orchestration.models import validate_document
from src.orchestration.policy import load_policy
from src.orchestration.session import create_call_session
from src.orchestration.validation import build_answer_packet
from tests.test_orchestration_validation import ROOT, call_request, valid_draft, valid_v2_draft
from tools.dev.materialize_effect_draft import SECTION_KEYS, materialize


def valid_v3_draft(session):
    """session 为自编候选；显式采用首条证据支持的最小主张。"""
    draft = valid_v2_draft(session)
    draft["schema_version"] = 3
    for decision, candidate in zip(draft["decisions"], session["candidates"]):
        decision["adoption"] = {
            "claim": "采用一个可观察动作，并根据执行反馈修正下一步。",
            "source_claim_type": candidate["card"].get("source_claim_type", "unclassified"),
            "evidence_ids": candidate["card"]["evidence_ids"][:1],
            "excluded_scope": ["原卡的其他主张不作为本次裁决依据。"],
        }
    return draft


def effect_spec(draft):
    """draft 为人工草稿；提取工具接受的显式规格，不补充 adoption。"""
    return {
        "admitted_decisions": {
            item["card_id"]: {key: value for key, value in item.items()
                              if key not in {"card_id", "decision", "reason_code"}}
            for item in draft["decisions"] if item["decision"] == "admit"
        },
        "rejected_decisions": {
            item["card_id"]: {key: item[key] for key in ("reason_code", "reason")}
            for item in draft["decisions"] if item["decision"] == "reject"
        },
        **{key: draft[key] for key in SECTION_KEYS},
    }


class AdoptedClaimsTests(unittest.TestCase):
    def setUp(self):
        """每例重新读自编书库；内存变体不写磁盘。"""
        self.library = Library(ROOT / "examples/sample-library")
        self.policy = load_policy()
        self.session = create_call_session(
            self.library, call_request(), "standard", self.policy, retrieval_mode="keyword"
        )

    def build(self, draft):
        """draft 为待验证草稿；经过正式构建入口。"""
        return build_answer_packet(self.library, self.session, draft, self.policy)

    def test_v3_publishes_adoption_only_and_preserves_analysis(self):
        draft = valid_v3_draft(self.session)
        packet = self.build(draft)
        for witness, decision in zip(packet["witness_cards"], draft["decisions"]):
            self.assertEqual(witness["adopted_claim"], decision["adoption"]["claim"])
            self.assertEqual(witness["evidence_ids"], decision["adoption"]["evidence_ids"])
            self.assertEqual(witness["excluded_scope"], decision["adoption"]["excluded_scope"])
            self.assertEqual(witness["original_card_ref"], {
                "session_id": self.session["session_id"], "library_version": self.library.version,
                "card_id": decision["card_id"],
            })
            for key in ("claim", "statement", "reasoning", "conditions", "boundaries", "card"):
                self.assertNotIn(key, witness)
            for key in ("principle", "mechanism", "assumptions", "user_context_refs", "fit",
                        "independent_judgment", "confidence", "non_applicable_conditions", "misuse_risks"):
                self.assertEqual(witness[key], decision[key])
        for key in SECTION_KEYS:
            self.assertEqual(packet[key], draft[key])

    def test_missing_blank_or_malformed_adoption_is_rejected(self):
        changes = [None, {"claim": ""}, {"claim": " \n\t"}, {"evidence_ids": []},
                   {"evidence_ids": ["evidence.demo.step", "evidence.demo.step"]},
                   {"source_claim_type": "author_inference"}, {"excluded_scope": "全部"}]
        for change in changes:
            with self.subTest(change=change):
                draft = valid_v3_draft(self.session)
                if change is None:
                    del draft["decisions"][0]["adoption"]
                else:
                    draft["decisions"][0]["adoption"].update(change)
                with self.assertRaisesRegex(ValueError, "INVALID_ANALYSIS_DRAFT.*adoption"):
                    self.build(draft)

    def test_rejected_card_cannot_carry_adoption(self):
        draft = valid_v3_draft(self.session)
        draft["decisions"][0].update(decision="reject", reason_code="irrelevant")
        with self.assertRaisesRegex(ValueError, "INVALID_ANALYSIS_DRAFT.*adoption"):
            self.build(draft)

    def test_evidence_must_belong_to_adopted_card(self):
        draft = valid_v3_draft(self.session)
        decision = next(item for item in draft["decisions"] if item["card_id"].endswith("review"))
        decision["adoption"]["evidence_ids"] = ["evidence.demo.step"]
        with self.assertRaisesRegex(ValueError, "采用证据.*不属于"):
            self.build(draft)

    def test_quote_requires_selected_evidence_and_exact_text(self):
        for evidence_id, quote_text, message in (
            ("evidence.demo.review", "完成小步骤后", "引用.*采用证据"),
            ("evidence.demo.step", "并不存在的文字", "逐字定位"),
        ):
            with self.subTest(evidence_id=evidence_id):
                draft = valid_v3_draft(self.session)
                decision = next(item for item in draft["decisions"] if item["card_id"].endswith("small-step"))
                decision["quote"] = {"evidence_id": evidence_id, "text": quote_text}
                with self.assertRaisesRegex(ValueError, message):
                    self.build(draft)

    def test_valid_short_quote_is_retained_and_long_quote_is_rejected(self):
        draft = valid_v3_draft(self.session)
        decision = draft["decisions"][0]
        evidence_id = decision["adoption"]["evidence_ids"][0]
        decision["quote"] = {"evidence_id": evidence_id, "text": "面对模糊的任务"}
        if evidence_id.endswith("review"):
            decision["quote"]["text"] = "完成小步骤后"
        self.assertEqual(self.build(draft)["witness_cards"][0]["quote"], decision["quote"])
        self.policy["quote_max_chars"] = 20
        self.session = create_call_session(
            self.library, call_request(), "standard", self.policy, retrieval_mode="keyword"
        )
        draft = valid_v3_draft(self.session)
        decision = draft["decisions"][0]
        evidence_id = decision["adoption"]["evidence_ids"][0]
        decision["quote"] = {"evidence_id": evidence_id, "text": self.library.evidence[evidence_id]["text"]}
        with self.assertRaisesRegex(ValueError, "引用超过策略长度"):
            self.build(draft)

    def test_attribution_keeps_original_or_downgrades_to_system_inference(self):
        types = ["author_claim", "quoted_other", "system_inference", "unclassified"]
        for source_type in types:
            card = self.library.cards["knowledge.demo.small-step"]
            if source_type == "unclassified":
                card.pop("source_claim_type", None)
            else:
                card["source_claim_type"] = source_type
            self.session = create_call_session(
                self.library, call_request(), "standard", self.policy, retrieval_mode="keyword"
            )
            for adopted_type in types:
                with self.subTest(source=source_type, adopted=adopted_type):
                    draft = valid_v3_draft(self.session)
                    decision = next(item for item in draft["decisions"] if item["card_id"] == card["id"])
                    decision["adoption"]["source_claim_type"] = adopted_type
                    if adopted_type in {source_type, "system_inference"}:
                        packet = self.build(draft)
                        witness = next(item for item in packet["witness_cards"] if item["card_id"] == card["id"])
                        self.assertEqual(witness["source_claim_type"], adopted_type)
                    else:
                        with self.assertRaisesRegex(ValueError, "来源归属"):
                            self.build(draft)

    def test_shared_sources_only_link_cards_that_selected_them(self):
        packet = self.build(valid_v3_draft(self.session))
        sources = {item["evidence_id"]: item for item in packet["sources"]}
        self.assertEqual(sources["evidence.demo.review"]["card_ids"], ["knowledge.demo.review"])
        step = next(item for item in packet["witness_cards"] if item["card_id"].endswith("small-step"))
        self.assertEqual(step["chapters"], ["明确下一步"])
        draft = valid_v3_draft(self.session)
        for decision in draft["decisions"]:
            decision["adoption"]["evidence_ids"] = ["evidence.demo.review"]
        packet = self.build(draft)
        self.assertEqual(len(packet["sources"]), 1)
        self.assertEqual(packet["sources"][0]["card_ids"], sorted(item["card_id"] for item in draft["decisions"]))

    def test_public_witness_and_source_reject_extra_full_card_fields(self):
        packet = self.build(valid_v3_draft(self.session))
        for collection in ("witness_cards", "sources"):
            for field in ("claim", "reasoning", "conditions", "boundaries", "card"):
                with self.subTest(collection=collection, field=field):
                    invalid = copy.deepcopy(packet)
                    invalid[collection][0][field] = "不允许整卡内容泄漏"
                    with self.assertRaisesRegex(ValueError, "INVALID_ANSWER_PACKET"):
                        validate_document("answer-packet.v3.schema.json", invalid)

    def test_old_versions_keep_full_card_and_all_evidence(self):
        for make_draft in (valid_draft, valid_v2_draft):
            draft = make_draft(self.session)
            packet = self.build(draft)
            for witness in packet["witness_cards"]:
                card = self.library.cards[witness["card_id"]]
                self.assertEqual(witness["claim"], card["statement"])
                self.assertEqual(witness["conditions"], card["conditions"])
                self.assertEqual(witness["evidence_ids"], card["evidence_ids"])
                self.assertNotIn("adopted_claim", witness)
            for decision in draft["decisions"]:
                self.assertNotIn("adoption", decision)
            self.assertEqual(next(item for item in packet["sources"] if item["evidence_id"].endswith("review"))["card_ids"],
                             sorted(item["card_id"] for item in draft["decisions"]))

    def test_v2_numeric_version_retains_json_schema_compatibility(self):
        draft = valid_v2_draft(self.session)
        draft["schema_version"] = 2.0
        self.assertEqual(self.build(draft)["schema_version"], 2)

    def test_v3_inherits_context_and_roundtable_checks(self):
        for target, message in (("context", "用户上下文引用越界"), ("roundtable", "圆桌席位"),
                                ("principle", "原理缺口"), ("mechanism", "作用机制")):
            with self.subTest(target=target):
                draft = valid_v3_draft(self.session)
                if target == "context":
                    draft["decisions"][0]["user_context_refs"][0]["index"] = 99
                elif target == "roundtable":
                    draft["roundtable"]["support"]["card_ids"] = ["knowledge.missing"]
                elif target == "principle":
                    draft["decisions"][0]["principle_gap"] = True
                else:
                    draft["decisions"][0]["mechanism"] = " "
                with self.assertRaisesRegex(ValueError, message):
                    self.build(draft)

    def test_materialize_default_stays_v2_and_v3_requires_explicit_adoption(self):
        draft2 = valid_v2_draft(self.session)
        self.assertEqual(materialize(self.session, effect_spec(draft2)), draft2)
        draft3 = valid_v3_draft(self.session)
        self.assertEqual(materialize(self.session, effect_spec(draft3), schema_version=3), draft3)
        with self.assertRaisesRegex(ValueError, "adoption"):
            materialize(self.session, effect_spec(draft2), schema_version=3)
        invalid = effect_spec(draft3)
        invalid["admitted_decisions"]["knowledge.demo.review"]["adoption"]["evidence_ids"] = ["evidence.demo.step"]
        with self.assertRaisesRegex(ValueError, "采用证据.*不属于"):
            materialize(self.session, invalid, schema_version=3)

    def test_materialize_cli_explicit_v3(self):
        draft = valid_v3_draft(self.session)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            session_path, spec_path, output_path = [directory / name for name in ("session.json", "spec.json", "draft.json")]
            session_path.write_text(json.dumps(self.session), encoding="utf-8")
            spec_path.write_text(json.dumps(effect_spec(draft)), encoding="utf-8")
            result = subprocess.run([
                sys.executable, "-m", "tools.dev.materialize_effect_draft",
                "--session", str(session_path), "--spec", str(spec_path),
                "--output", str(output_path), "--schema-version", "3",
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), draft)

    def test_empty_admitted_keeps_v2_rejection_without_inventing_evidence(self):
        request = call_request()
        request.update(question="zzzxxyy", query_expansions=[], facts=[], constraints=[])
        empty_session = create_call_session(
            self.library, request, "standard", self.policy, retrieval_mode="keyword"
        )
        self.assertEqual(empty_session["candidates"], [])
        self.assertEqual(empty_session["status"], "no_relevant_knowledge")
        for session in (self.session, empty_session):
            for version in (2, 3):
                with self.subTest(version=version, empty=not session["candidates"]):
                    draft = valid_v2_draft(session)
                    draft["schema_version"] = version
                    draft["decisions"] = [{
                        "card_id": item["card_id"], "decision": "reject",
                        "reason_code": "weak_evidence", "reason": "不适合本次问题。",
                    } for item in session["candidates"]]
                    draft["knowledge_groups"] = []
                    draft["verdict"]["basis_card_ids"] = []
                    with self.assertRaisesRegex(ValueError, "INVALID_ANALYSIS_DRAFT"):
                        build_answer_packet(self.library, session, draft, self.policy)
                    self.assertTrue(all("adoption" not in item for item in draft["decisions"]))

    def test_unknown_versions_are_explicit_errors(self):
        for version in (0, 4, "3", None):
            with self.subTest(version=version):
                draft = valid_v3_draft(self.session)
                draft["schema_version"] = version
                with self.assertRaisesRegex(ValueError, "不支持.*版本"):
                    self.build(draft)
                with self.assertRaisesRegex(ValueError, "不支持.*版本"):
                    materialize(self.session, effect_spec(valid_v2_draft(self.session)), schema_version=version)


if __name__ == "__main__":
    unittest.main()
