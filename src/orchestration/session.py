"""建立固定知识版本的候选调用会话。"""
import hashlib
import json

from src.orchestration.models import validate_document
from src.orchestration.policy import MODES, validate_policy
from src.retrieval.search import SearchEngine


def session_id_for(document):
    """以规范 JSON 生成可复现的会话 ID。"""
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "call." + hashlib.sha256(encoded).hexdigest()[:24]


def _searched_books(library, filters):
    books = library.list_books(filters.get("author"))
    if book := filters.get("book"):
        books = [item for item in books if book in (item["id"], item.get("title"))]
    return [item["id"] for item in books]


def _search(engine, request, retrieval_mode, limit):
    filters = request.get("filters", {})
    return engine.search(
        request["question"],
        mode=retrieval_mode,
        book=filters.get("book"),
        author=filters.get("author"),
        limit=limit,
        expansions=request["query_expansions"],
    )


def create_call_session(library, request, mode, policy, retrieval_mode="hybrid", index_root=None, model_cache=None):
    """检索并装配候选卡、证据与一跳关系；不自动采用卡片。"""
    validate_document("call-request.schema.json", request)
    validate_policy(policy)
    if mode not in MODES:
        raise ValueError("INVALID_CALL_REQUEST: 未知调用模式")
    if retrieval_mode not in ("keyword", "semantic", "hybrid"):
        raise ValueError("INVALID_CALL_REQUEST: 未知检索模式")

    settings = policy["modes"][mode]
    engine = SearchEngine(library, index_root=index_root, model_cache=model_cache)
    effective_mode, degraded, degraded_reason = retrieval_mode, False, None
    try:
        results = _search(engine, request, retrieval_mode, settings["recall_limit"])
    except (ImportError, ModuleNotFoundError) as exc:
        if retrieval_mode == "keyword":
            raise
        effective_mode, degraded = "keyword", True
        degraded_reason = f"VECTOR_DEPENDENCY_UNAVAILABLE: {exc}"
        results = _search(engine, request, "keyword", settings["recall_limit"])

    candidates, seen = [], set()
    for result in results:
        card = result["card"]
        if card["id"] in seen:
            continue
        seen.add(card["id"])
        evidence = [library.get_evidence(identifier, policy["evidence_context_chars"])
                    for identifier in card["evidence_ids"]]
        relations = (library.get_related(card["id"], hops=settings["relation_hops"], direction="both")
                     if settings["relation_hops"] else [])
        match = {key: value for key, value in result.items() if key not in ("card", "book")}
        candidates.append({
            "card_id": card["id"],
            "status": "pending",
            "card": card,
            "book": result["book"],
            "match": match,
            "evidence": evidence,
            "relations": relations,
        })

    body = {
        "schema_version": 1,
        "library_version": library.version,
        "mode": mode,
        "status": "ready" if candidates else "no_relevant_knowledge",
        "request": request,
        "policy": policy,
        "retrieval": {
            "mode": effective_mode,
            "queries": [request["question"]] + request["query_expansions"],
            "books_searched": _searched_books(library, request.get("filters", {})),
            "filters": request.get("filters", {}),
            "degraded": degraded,
            "degraded_reason": degraded_reason,
        },
        "candidates": candidates,
    }
    session = {"session_id": session_id_for(body), **body}
    validate_document("call-session.schema.json", session)
    return session
