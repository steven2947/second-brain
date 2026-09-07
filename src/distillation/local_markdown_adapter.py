"""把本地 v1.2 Markdown/YAML 蒸馏成果编译为 Second Brain 候选库。"""
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

import yaml

from src.distillation.jobs import write_json
from src.knowledge.library import validate_library


CARD_DIRECTORIES = ("01_知识卡", "02_方法卡", "03_案例与反例", "04_问题与行动")
RELATION_TYPES = {
    "DEPENDS_ON": "depends_on",
    "CONTRASTS_WITH": "contrasts_with",
    "CONTRADICTS": "contrasts_with",
    "COMPOSES_WITH": "composes_with",
    "REFINES": "composes_with",
    "APPLIES_TO": "applies_to",
    "LIMITED_BY": "limited_by",
    "SUPPORTS": "supported_by",
    "SUPPORTED_BY": "supported_by",
    "EXEMPLIFIES": "applies_to",
    "EXEMPLIFIED_BY": "applies_to",
}


def _frontmatter(path):
    """path 为单张 Markdown 卡片；返回 YAML front matter。"""
    text = Path(path).read_text(encoding="utf-8")
    match = re.match(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        raise ValueError(f"INVALID_LOCAL_CARD: 缺少 front matter: {path}")
    payload = yaml.safe_load(match.group(1)) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"INVALID_LOCAL_CARD: front matter 不是对象: {path}")
    return payload


def _strings(value):
    """把单值或列表收敛为非空字符串列表。"""
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item).strip()]


def _local_sources(card):
    """card 为本地卡元数据；兼容 v1.2 数组证据与早期单 `source` 证据。"""
    sources = list(card.get("primary_sources") or []) + list(card.get("supporting_sources") or [])
    inline = card.get("source")
    if isinstance(inline, dict) and all(key in inline for key in ("anchor_quote", "char_span", "source_hash")):
        sources.append(inline)
    unique = []
    seen = set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        span = source.get("char_span")
        key = (tuple(span) if isinstance(span, list) else None, source.get("anchor_quote"), source.get("source_hash"))
        if key not in seen:
            seen.add(key)
            unique.append(source)
    return unique


def _author_id(author):
    """author 为作者展示名；返回稳定、不依赖拼音库的 ID。"""
    digest = hashlib.sha256(author.encode("utf-8")).hexdigest()[:12]
    return f"author.local.{digest}"


def _load_book(book_dir, allow_ready):
    """book_dir 为单书成果目录；加载并验证原文指纹与验收状态。"""
    book_dir = Path(book_dir).resolve()
    metadata_path = book_dir / "book.yaml"
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
    if metadata.get("book_id") != book_dir.name:
        raise ValueError(f"INVALID_LOCAL_BOOK: book_id 与目录不一致: {book_dir}")
    status = metadata.get("distillation_status")
    if status != "accepted" and not (allow_ready and status == "ready_for_human_acceptance"):
        raise ValueError(f"LOCAL_BOOK_NOT_ACCEPTED: {book_dir.name} 未人工验收")
    source_path = Path(metadata.get("source_md", ""))
    if not source_path.is_file() or source_path.is_symlink():
        raise ValueError(f"INVALID_LOCAL_BOOK: 原文路径无效: {book_dir.name}")
    source_bytes = source_path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if source_hash != metadata.get("source_sha256"):
        raise ValueError(f"SOURCE_VERSION_MISMATCH: {book_dir.name} 原文指纹已变化")
    return book_dir, metadata, source_bytes.decode("utf-8")


def import_local_books(book_dirs, destination, allow_ready=False):
    """将 book_dirs 编译到新 destination；allow_ready 仅用于未人工验收的本地评测候选。"""
    destination = Path(destination)
    if destination.exists():
        raise ValueError("DESTINATION_EXISTS: 候选目录已存在")
    if not book_dirs:
        raise ValueError("INVALID_ARGUMENT: 至少提供一本书")
    loaded = [_load_book(path, allow_ready) for path in book_dirs]
    ids = [metadata["book_id"] for _, metadata, _ in loaded]
    if len(ids) != len(set(ids)):
        raise ValueError("INVALID_ARGUMENT: 书籍 ID 重复")

    cards = []
    sources_by_book = defaultdict(dict)
    source_id_keys = defaultdict(dict)
    for book_dir, metadata, source_text in loaded:
        book_id = metadata["book_id"]
        for dirname in CARD_DIRECTORIES:
            for path in sorted((book_dir / dirname).glob("*.md")):
                card = _frontmatter(path)
                if card.get("status") in {"draft", "rejected"}:
                    continue
                card_id = card.get("id")
                if (not isinstance(card_id, str) or
                        not re.fullmatch(r"(?:K|M|CASE|CX|Q)-" + re.escape(book_id) + r"-[A-Za-z0-9-]+", card_id)):
                    raise ValueError(f"INVALID_LOCAL_CARD: 卡片 ID 不安全或书籍归属不一致: {path}")
                if card.get("source", {}).get("book_id", book_id) != book_id:
                    raise ValueError(f"INVALID_LOCAL_CARD: 书籍归属不一致: {path}")
                local_sources = _local_sources(card)
                if not local_sources:
                    raise ValueError(f"INVALID_LOCAL_CARD: 缺少证据: {path}")
                source_keys = []
                for source in local_sources:
                    span = source.get("char_span")
                    quote = source.get("anchor_quote")
                    if (not isinstance(span, list) or len(span) != 2 or
                            not all(isinstance(value, int) for value in span) or
                            not isinstance(quote, str) or source_text[span[0]:span[1]] != quote):
                        raise ValueError(f"INVALID_LOCAL_CARD: 锚点与原文不一致: {path}")
                    if source.get("source_hash") != metadata["source_sha256"]:
                        raise ValueError(f"SOURCE_VERSION_MISMATCH: 卡片锚点指纹不一致: {path}")
                    key = (span[0], span[1], quote)
                    sources_by_book[book_id][key] = source
                    if source.get("source_id"):
                        source_id_keys[book_id][source["source_id"]] = key
                    source_keys.append(key)
                cards.append((book_id, card, source_keys))

    evidence_ids = {}
    evidence_rows = []
    corpus = "# 引用证据汇编\n\n以下仅保留卡片使用的离散短引；相邻排列不表示原书相邻。\n\n"
    counters = defaultdict(int)
    for book_id in sorted(sources_by_book):
        metadata = next(meta for _, meta, _ in loaded if meta["book_id"] == book_id)
        for key, source in sorted(sources_by_book[book_id].items()):
            index = counters[metadata["source_sha256"]]
            counters[metadata["source_sha256"]] += 1
            paragraph_id = f"paragraph.{metadata['source_sha256'][:12]}.{index:04d}"
            evidence_id = "evidence." + paragraph_id
            evidence_ids[(book_id, key)] = evidence_id
            corpus += f"## {book_id} · {source.get('chapter') or '未标章节'}\n\n"
            start = len(corpus)
            corpus += key[2]
            end = len(corpus)
            corpus += "\n\n"
            evidence_rows.append((evidence_id, book_id, source, start, end, paragraph_id))

    author_ids = {meta["book_id"]: _author_id(str(meta.get("author") or "未登记")) for _, meta, _ in loaded}
    output_cards = []
    card_evidence = {}
    for book_id, local, keys in cards:
        content = local.get("content") or {}
        application = local.get("application") or {}
        statement = str(content.get("proposition") or local.get("title") or "").strip()
        conditions = _strings(content.get("assumptions")) + _strings(application.get("prerequisites"))
        boundaries = _strings(application.get("non_applicable_conditions")) + _strings(application.get("failure_modes"))
        trigger_questions = _strings(application.get("user_language_examples"))
        trigger_questions += [
            str(test.get("question")).strip() for test in (local.get("trigger_tests") or [])
            if isinstance(test, dict) and test.get("test_type") == "positive" and test.get("question")
        ]
        notes = []
        for label, key in (("预期输出", "expected_output"), ("完成标志", "completion_criteria"), ("停止条件", "stop_conditions")):
            values = _strings(application.get(key))
            if values:
                notes.append(f"{label}: {'；'.join(values)}")
        output = {
            "schema_version": 1,
            "id": str(local["id"]),
            "book_id": book_id,
            "author_id": author_ids[book_id],
            "kind": str(local.get("type") or "claim"),
            "title": str(local.get("title") or local["id"]),
            "statement": statement,
            "reasoning": str(content.get("explanation") or ""),
            "keywords": list(dict.fromkeys(_strings(application.get("problem_types")) + _strings(application.get("trigger_signals")))),
            "trigger_questions": list(dict.fromkeys(trigger_questions)),
            "application_notes": "\n".join(notes),
            "source_claim_type": "system_inference" if content.get("inference") is True else str(content.get("attribution_layer") or "author_claim"),
            "conditions": list(dict.fromkeys(conditions)),
            "boundaries": list(dict.fromkeys(boundaries)),
            "steps": _strings(application.get("steps")),
            "evidence_ids": list(dict.fromkeys(evidence_ids[(book_id, key)] for key in keys)),
        }
        if output["source_claim_type"] not in {"author_claim", "quoted_other", "system_inference"}:
            output["source_claim_type"] = "system_inference"
        output_cards.append(output)
        card_evidence[(book_id, output["id"])] = output["evidence_ids"]

    card_ids = {card["id"] for card in output_cards}
    output_edges = []
    seen_edge_keys = set()
    for book_dir, metadata, _ in loaded:
        book_id = metadata["book_id"]
        relation_path = book_dir / "06_关系" / "relations.json"
        if not relation_path.is_file():
            continue
        relation_payload = json.loads(relation_path.read_text(encoding="utf-8"))
        for local in relation_payload.get("edges", []):
            source_id, target_id = local.get("source"), local.get("target")
            if source_id not in card_ids or target_id not in card_ids:
                continue
            edge_key = (
                book_id, source_id, target_id, str(local.get("relation") or "").upper(),
                str(local.get("explanation") or ""), tuple(local.get("evidence_ids") or []),
            )
            if edge_key in seen_edge_keys:
                continue
            seen_edge_keys.add(edge_key)
            edge_digest = hashlib.sha256(
                json.dumps(edge_key, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:12]
            linked = [
                evidence_ids[(book_id, source_id_keys[book_id][source_ref])]
                for source_ref in local.get("evidence_ids", [])
                if source_ref in source_id_keys[book_id]
            ]
            basis = "source"
            if not linked:
                linked = card_evidence[(book_id, source_id)][:1]
                basis = "inference"
            output_edges.append({
                "id": f"relation.{book_id}.{local.get('id') or 'anonymous'}.{edge_digest}",
                "from": source_id,
                "to": target_id,
                "type": RELATION_TYPES.get(str(local.get("relation") or "").upper(), "composes_with"),
                "basis": basis,
                "rationale": str(local.get("explanation") or "本地卡片关系映射。"),
                "evidence_ids": list(dict.fromkeys(linked)),
            })

    temporary = Path(tempfile.mkdtemp(prefix=".local-import-", dir=destination.parent))
    try:
        source_dir = temporary / "sources"
        source_dir.mkdir()
        corpus_path = source_dir / "evidence.md"
        corpus_path.write_text(corpus, encoding="utf-8")
        corpus_hash = hashlib.sha256(corpus.encode("utf-8")).hexdigest()
        for evidence_id, book_id, source, start, end, paragraph_id in evidence_rows:
            write_json(temporary / "evidence" / f"{evidence_id}.json", {
                "schema_version": 1,
                "id": evidence_id,
                "book_id": book_id,
                "chapter": str(source.get("heading_path") or source.get("chapter") or "未标章节"),
                "source_path": "sources/evidence.md",
                "source_sha256": corpus_hash,
                "start": start,
                "end": end,
                "text": source["anchor_quote"],
                "origin": {
                    "source_sha256": next(meta["source_sha256"] for _, meta, _ in loaded if meta["book_id"] == book_id),
                    "paragraph_id": paragraph_id,
                    "start": source["char_span"][0],
                    "end": source["char_span"][1],
                },
            })
        for card in output_cards:
            write_json(temporary / "cards" / f"{card['id']}.json", card)
        write_json(temporary / "relations.json", {"schema_version": 1, "edges": output_edges})
        manifest_books = []
        for _, metadata, source_text in loaded:
            manifest_books.append({
                "id": metadata["book_id"],
                "title": metadata["title"],
                "author_id": author_ids[metadata["book_id"]],
                "author": str(metadata.get("author") or "未登记"),
                "status": metadata.get("distillation_status"),
                "source_sha256": metadata["source_sha256"],
                "source_chars": len(source_text),
                "scope": "本地 v1.2 蒸馏成果中已验证卡片及其离散原文短引。",
            })
        write_json(temporary / "manifest.json", {
            "schema_version": 1,
            "library_id": "library.local-distillation-candidate",
            "is_example": False,
            "books": manifest_books,
            "cards_directory": "cards",
            "evidence_directory": "evidence",
            "relations_file": "relations.json",
            "distillation_mode": "local_markdown_adapter",
            "release_status": "evaluation_candidate" if allow_ready else "accepted_candidate",
        })
        report = validate_library(temporary)
        os.replace(temporary, destination)
        return {**report, "path": str(destination.resolve()), "release_status": "evaluation_candidate" if allow_ready else "accepted_candidate"}
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
