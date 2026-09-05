"""核验 Agent 的语义判断，并从真实候选生成可追溯答案包。"""
from collections import defaultdict

from src.orchestration.models import validate_document
from src.orchestration.policy import validate_policy
from src.orchestration.session import session_id_for


def _invalid(message):
    raise ValueError(f"INVALID_ANALYSIS_DRAFT: {message}")


def _validate_session(library, session):
    validate_document("call-session.schema.json", session)
    validate_document("call-request.schema.json", session["request"])
    body = {key: value for key, value in session.items() if key != "session_id"}
    if session["session_id"] != session_id_for(body):
        _invalid("检索会话内容或 session_id 已改变")
    if session["library_version"] != library.version:
        raise ValueError("SOURCE_VERSION_MISMATCH: 调用会话与当前知识版本不一致")

    book_index = {book["id"]: book for book in library.manifest["books"]}
    edge_index = {edge["id"]: edge for edge in library.edges}
    identifiers = []
    for candidate in session["candidates"]:
        identifier = candidate["card_id"]
        identifiers.append(identifier)
        if candidate["card"] != library.get_knowledge(identifier):
            _invalid(f"候选卡内容与知识库不一致：{identifier}")
        if candidate["book"] != book_index[candidate["card"]["book_id"]]:
            _invalid(f"候选书籍信息不一致：{identifier}")
        allowed_evidence = set(candidate["card"]["evidence_ids"])
        if {item["id"] for item in candidate["evidence"]} != allowed_evidence:
            _invalid(f"候选证据集合不一致：{identifier}")
        for evidence in candidate["evidence"]:
            current = library.get_evidence(evidence["id"], 0)
            for key in ("id", "book_id", "source_sha256", "start", "end", "text"):
                if evidence.get(key) != current.get(key):
                    _invalid(f"候选证据内容不一致：{evidence['id']}")
        for related in candidate["relations"]:
            edge = related.get("edge", {})
            if edge.get("id") not in edge_index or edge_index[edge["id"]] != edge:
                _invalid(f"候选关系不一致：{edge.get('id')}")
    if len(identifiers) != len(set(identifiers)):
        _invalid("检索会话包含重复候选")


def _validate_decisions(session, draft, policy):
    candidates = {item["card_id"]: item for item in session["candidates"]}
    decisions = draft["decisions"]
    identifiers = [item["card_id"] for item in decisions]
    if len(identifiers) != len(set(identifiers)) or set(identifiers) != set(candidates):
        _invalid("每个候选必须且只能有一个采用或淘汰决定")

    admitted = set()
    for decision in decisions:
        identifier = decision["card_id"]
        if decision["decision"] == "reject":
            if decision["reason_code"] == "relevant":
                _invalid(f"淘汰候选不能使用 relevant：{identifier}")
            continue
        if decision["reason_code"] != "relevant":
            _invalid(f"采用候选必须使用 relevant：{identifier}")
        if not decision.get("roles"):
            _invalid(f"采用候选缺少分析角色：{identifier}")
        if not decision.get("situation_mapping", "").strip() or not decision.get("judgment_effect", "").strip():
            _invalid(f"采用候选缺少情境映射或判断作用：{identifier}")
        if not decision.get("principle", "").strip() and decision.get("principle_gap") is not True:
            _invalid(f"采用候选缺少原理解释或明确原理缺口：{identifier}")
        if quote := decision.get("quote"):
            evidence = {item["id"]: item for item in candidates[identifier]["evidence"]}
            if quote["evidence_id"] not in evidence or quote["text"] not in evidence[quote["evidence_id"]]["text"]:
                _invalid(f"引用无法在候选证据中逐字定位：{identifier}")
            if len(quote["text"]) > policy["quote_max_chars"]:
                _invalid(f"引用超过策略长度：{identifier}")
        admitted.add(identifier)

    if len(admitted) > policy["modes"][session["mode"]]["final_limit"]:
        _invalid("采用卡片超过当前模式上限")
    if session["status"] == "no_relevant_knowledge" and admitted:
        _invalid("无相关知识的会话不能采用卡片")
    return candidates, admitted


def _validate_references(session, draft, admitted, candidates):
    for category in ("agreements", "conflicts", "limitations", "alternatives"):
        for finding in draft["cross_validation"][category]:
            if not set(finding["card_ids"]).issubset(admitted):
                _invalid(f"交叉验证 {category} 引用了未采用卡片")
    if not set(draft["verdict"]["basis_card_ids"]).issubset(admitted):
        _invalid("综合裁决依据包含未采用卡片")
    for action in draft["actions"]:
        if not set(action["basis_card_ids"]).issubset(admitted):
            _invalid("行动依据包含未采用卡片")

    challenge_available = any(
        candidate["card"].get("kind") == "counterexample"
        or bool(candidate["card"].get("boundaries"))
        or any(item.get("edge", {}).get("type") in ("contrasts_with", "limited_by")
               for item in candidate["relations"])
        for candidate in candidates.values()
    )
    admitted_roles = {role for item in draft["decisions"] if item["card_id"] in admitted
                      for role in item.get("roles", [])}
    if session["mode"] == "deep" and challenge_available and not admitted_roles.intersection({"challenge", "boundary"}):
        _invalid("deep 模式存在挑战或限制候选，但没有纳入挑战/边界角色")


def _build_witness(candidate, decision):
    card, book = candidate["card"], candidate["book"]
    chapters = list(dict.fromkeys(item["chapter"] for item in candidate["evidence"]))
    source_type = card.get("source_claim_type", "unclassified")
    return {
        "card_id": card["id"],
        "book_id": book["id"],
        "book_title": book["title"],
        "author_id": book["author_id"],
        "author": book.get("author"),
        "chapters": chapters,
        "claim": card["statement"],
        "reasoning": card.get("reasoning", ""),
        "principle": decision.get("principle", ""),
        "principle_gap": decision.get("principle_gap", False),
        "conditions": card.get("conditions", []),
        "boundaries": card.get("boundaries", []),
        "situation_mapping": decision["situation_mapping"],
        "judgment_effect": decision["judgment_effect"],
        "roles": decision["roles"],
        "source_claim_type": source_type,
        "source_gap": source_type == "unclassified",
        "evidence_ids": card["evidence_ids"],
        "quote": decision.get("quote"),
    }


def _build_sources(candidates, admitted, quote_max_chars):
    sources = {}
    card_links = defaultdict(list)
    for identifier in admitted:
        for evidence in candidates[identifier]["evidence"]:
            card_links[evidence["id"]].append(identifier)
            if evidence["id"] not in sources:
                book = candidates[identifier]["book"]
                sources[evidence["id"]] = {
                    "evidence_id": evidence["id"],
                    "book_id": book["id"],
                    "book_title": book["title"],
                    "author": book.get("author"),
                    "chapter": evidence["chapter"],
                    "excerpt": evidence["text"][:quote_max_chars],
                    "card_ids": [],
                }
    for evidence_id, identifiers in card_links.items():
        sources[evidence_id]["card_ids"] = sorted(set(identifiers))
    return [sources[key] for key in sorted(sources)]


def build_answer_packet(library, session, draft, policy):
    """验证完整分析草稿，并生成只引用真实候选的正式答案包。"""
    validate_policy(policy)
    _validate_session(library, session)
    if session["policy"] != policy:
        _invalid("验证策略与建立调用会话时的策略不一致")
    validate_document("analysis-draft.schema.json", draft)
    if draft["session_id"] != session["session_id"] or draft["library_version"] != library.version:
        raise ValueError("SOURCE_VERSION_MISMATCH: 分析草稿与调用会话版本不一致")
    candidates, admitted = _validate_decisions(session, draft, policy)
    _validate_references(session, draft, admitted, candidates)

    decision_index = {item["card_id"]: item for item in draft["decisions"]}
    admitted_order = [item["card_id"] for item in session["candidates"] if item["card_id"] in admitted]
    rejected = [{"card_id": item["card_id"], "reason_code": item["reason_code"], "reason": item["reason"]}
                for item in draft["decisions"] if item["decision"] == "reject"]
    witnesses = [_build_witness(candidates[identifier], decision_index[identifier]) for identifier in admitted_order]
    request = session["request"]
    packet = {
        "schema_version": 1,
        "session_id": session["session_id"],
        "library_version": session["library_version"],
        "mode": session["mode"],
        "problem": {key: request[key] for key in ("question", "goal", "facts", "constraints", "assumptions")},
        "call_ledger": {
            "books_searched": session["retrieval"]["books_searched"],
            "queries": session["retrieval"]["queries"],
            "retrieval_mode": session["retrieval"]["mode"],
            "retrieval_degraded": session["retrieval"]["degraded"],
            "candidates": [{"card_id": item["card_id"], "title": item["card"]["title"],
                            "book_id": item["book"]["id"]} for item in session["candidates"]],
            "admitted": admitted_order,
            "rejected": rejected,
        },
        "witness_cards": witnesses,
        "cross_validation": draft["cross_validation"],
        "verdict": draft["verdict"],
        "actions": draft["actions"],
        "sources": _build_sources(candidates, admitted, policy["quote_max_chars"]),
    }
    validate_document("answer-packet.schema.json", packet)
    return packet
