"""v3 采用边界：只公开本次采用主张及证据，原卡留在固定会话供审计。"""


ANALYSIS_FIELDS = (
    "principle", "principle_gap", "mechanism", "assumptions", "user_context_refs",
    "situation_mapping", "fit", "independent_judgment", "confidence", "judgment_effect",
    "non_applicable_conditions", "misuse_risks", "roles",
)


def validate_adoption(candidate, decision, quote_max_chars):
    """candidate 为固定原卡，decision 已过 v3 Schema；quote_max_chars 限制短引。"""
    if decision["decision"] != "admit":
        return
    identifier = candidate["card_id"]
    adoption = decision["adoption"]
    original_type = candidate["card"].get("source_claim_type", "unclassified")
    if adoption["source_claim_type"] not in {original_type, "system_inference"}:
        raise ValueError(f"INVALID_ANALYSIS_DRAFT: 采用主张不能改变或升级来源归属：{identifier}")
    selected = set(adoption["evidence_ids"])
    if not selected.issubset(candidate["card"]["evidence_ids"]):
        raise ValueError(f"INVALID_ANALYSIS_DRAFT: 采用证据不属于当前卡片：{identifier}")
    if quote := decision.get("quote"):
        if quote["evidence_id"] not in selected:
            raise ValueError(f"INVALID_ANALYSIS_DRAFT: 引用必须来自本次采用证据：{identifier}")
        evidence = {item["id"]: item for item in candidate["evidence"]}
        if quote["text"] not in evidence[quote["evidence_id"]]["text"]:
            raise ValueError(f"INVALID_ANALYSIS_DRAFT: 引用无法在采用证据中逐字定位：{identifier}")
        if len(quote["text"]) > quote_max_chars:
            raise ValueError(f"INVALID_ANALYSIS_DRAFT: 引用超过策略长度：{identifier}")


def selected_candidates(candidates, decisions):
    """candidates 为候选索引，decisions 为决定索引；只裁剪采用证据，不修改原会话。"""
    return {
        identifier: {**candidate, "evidence": [
            item for item in candidate["evidence"]
            if item["id"] in decisions[identifier].get("adoption", {}).get("evidence_ids", [])
        ]}
        for identifier, candidate in candidates.items()
    }


def build_adopted_witness(candidate, decision, session):
    """candidate 已裁剪证据，decision 含采用声明；session 提供代码生成的审计引用。"""
    card, book = candidate["card"], candidate["book"]
    adoption = decision["adoption"]
    return {
        "card_id": card["id"],
        "book_id": book["id"],
        "book_title": book["title"],
        "author_id": book["author_id"],
        "author": book.get("author"),
        "chapters": list(dict.fromkeys(item["chapter"] for item in candidate["evidence"])),
        "adopted_claim": adoption["claim"],
        "source_claim_type": adoption["source_claim_type"],
        "source_gap": card.get("source_claim_type", "unclassified") == "unclassified",
        "evidence_ids": list(adoption["evidence_ids"]),
        "excluded_scope": list(adoption["excluded_scope"]),
        "original_card_ref": {
            "session_id": session["session_id"],
            "library_version": session["library_version"],
            "card_id": card["id"],
        },
        **{key: decision[key] for key in ANALYSIS_FIELDS},
        "quote": decision.get("quote"),
    }
