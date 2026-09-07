"""把人工语义规格与固定检索会话装配成完整效果题分析草稿。"""
import argparse
import json
from pathlib import Path

from src.distillation.jobs import write_json
from src.orchestration.adoption import validate_adoption
from src.orchestration.models import validate_document


SECTION_KEYS = {
    "problem_framing", "knowledge_groups", "argument_relations", "system_syntheses",
    "roundtable", "verdict", "actions", "learning_takeaways", "continuation_options",
    "next_chat_action",
}


def materialize(session, spec, schema_version=2):
    """session 为固定会话，spec 显式覆盖全部决定；schema_version 默认保留 v2。"""
    if schema_version not in (2, 3):
        raise ValueError(f"INVALID_EFFECT_SPEC: 不支持的草稿版本：{schema_version}")
    if set(spec) != {"admitted_decisions", "rejected_decisions", *SECTION_KEYS}:
        raise ValueError("INVALID_EFFECT_SPEC: 规格字段不完整或包含未知字段")
    candidates = {item["card_id"] for item in session["candidates"]}
    selected = spec["admitted_decisions"]
    rejected = spec["rejected_decisions"]
    if (not selected or set(selected) & set(rejected)
            or set(selected) | set(rejected) != candidates):
        raise ValueError("INVALID_EFFECT_SPEC: 每个候选须且只能有一个显式决定")
    for identifier, decision in rejected.items():
        if (set(decision) != {"reason_code", "reason"}
                or decision["reason_code"] == "relevant"
                or not isinstance(decision["reason"], str)
                or not decision["reason"].strip()):
            raise ValueError(f"INVALID_EFFECT_SPEC: 淘汰记录不完整：{identifier}")

    decisions = []
    for candidate in session["candidates"]:
        identifier = candidate["card_id"]
        if identifier in selected:
            decisions.append({
                **selected[identifier],
                "card_id": identifier,
                "decision": "admit",
                "reason_code": "relevant",
            })
        else:
            decisions.append({
                "card_id": identifier,
                "decision": "reject",
                **rejected[identifier],
            })
    draft = {
        "schema_version": schema_version,
        "session_id": session["session_id"],
        "library_version": session["library_version"],
        "problem_framing": spec["problem_framing"],
        "decisions": decisions,
        **{key: spec[key] for key in SECTION_KEYS if key != "problem_framing"},
    }
    validate_document(f"analysis-draft.v{schema_version}.schema.json", draft)
    if schema_version == 3:
        candidate_index = {item["card_id"]: item for item in session["candidates"]}
        for decision in decisions:
            validate_adoption(candidate_index[decision["card_id"]], decision, session["policy"]["quote_max_chars"])
    return draft


def main():
    """CLI 读取显式会话与规格，校验成功后才写入目标草稿。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--schema-version", type=int, choices=(2, 3), default=2)
    args = parser.parse_args()
    session = json.loads(Path(args.session).read_text(encoding="utf-8"))
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    write_json(Path(args.output), materialize(session, spec, schema_version=args.schema_version))


if __name__ == "__main__":
    main()
