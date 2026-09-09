"""把已验证的单书候选装配为可回读的多书候选库。"""

import os
import re
import shutil
import tempfile
from pathlib import Path

from src.distillation.jobs import write_json
from src.knowledge.library import content_version, load_records, read_json, validate_library


def _validate_acceptance_marker(manifest, book, candidate):
    """验证 accepted_candidate 的输入门禁；manifest 为候选清单，book 为唯一书籍，candidate 为候选目录。"""
    if manifest.get("is_example") is True:
        raise ValueError(f"ACCEPTANCE_REQUIRED: 示例候选不能标记为 accepted_candidate: {candidate}")

    rejected_statuses = {"example_only", "evaluation_candidate", "blocked"}
    accepted_statuses = {"accepted_candidate", "accepted"}
    markers = (
        manifest.get("release_status"),
        manifest.get("status"),
        book.get("release_status"),
        book.get("status"),
    )
    if any(marker in rejected_statuses for marker in markers):
        raise ValueError(f"ACCEPTANCE_REQUIRED: 候选状态未通过接受门禁: {candidate}")
    if any(marker in accepted_statuses for marker in markers):
        return

    # 兼容当前已发布 Naval 的历史 assemble manifest：它没有顶层 release_status，
    # 但固定的库/书籍标识和 agent_reviewed_pilot 状态是可审计的旧接受标记。
    if (
        manifest.get("library_id") == "library.naval-almanack-pilot"
        and book.get("id") == "book.naval-almanack"
        and book.get("author_id") == "author.naval-ravikant"
        and book.get("status") == "agent_reviewed_pilot"
    ):
        return
    raise ValueError(f"ACCEPTANCE_REQUIRED: 候选缺少 accepted_candidate 或 accepted 标记: {candidate}")


def _source_path_for_merge(candidate, evidence, source_root, candidate_index):
    """计算合并后证据来源路径；candidate 为候选目录，evidence 为证据记录，source_root 为来源目录，candidate_index 为候选序号。"""
    original = (candidate / evidence["source_path"]).resolve()
    source_root = source_root.resolve()
    if not original.is_relative_to(source_root):
        raise ValueError("INVALID_CANDIDATE: 证据来源不在 sources 目录")
    relative = original.relative_to(source_root)
    return Path("sources") / f"candidate-{candidate_index:03d}" / relative


def _book_prefix(book_id, candidate_index):
    """生成卡片和证据文件名前缀；book_id 为书籍标识，candidate_index 为候选序号。"""
    if not isinstance(book_id, str) or not book_id or Path(book_id).name != book_id:
        raise ValueError("INVALID_CANDIDATE: book_id 不能用于稳定文件名")
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", book_id).strip("-")
    if not safe_id:
        raise ValueError("INVALID_CANDIDATE: book_id 不能用于稳定文件名")
    return f"{candidate_index:03d}-{safe_id}--"


def merge_libraries(
    candidates: list[str | Path],
    destination: str | Path,
    library_id: str,
    release_status: str = "evaluation_candidate",
) -> dict:
    """原子合并已验证单书候选；candidates 为有序候选目录，destination 为不存在的目标目录，library_id 为目标库标识，release_status 为候选状态。"""
    if not candidates:
        raise ValueError("INVALID_ARGUMENT: 至少需要一个候选库")
    if not isinstance(library_id, str) or not re.fullmatch(r"library\.[a-z0-9-]+", library_id):
        raise ValueError("INVALID_ARGUMENT: library_id 格式无效")
    if release_status not in ("evaluation_candidate", "accepted_candidate"):
        raise ValueError("INVALID_ARGUMENT: release_status 无效")

    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("DESTINATION_EXISTS: 目标目录已存在")
    if not destination.parent.is_dir():
        raise ValueError("INVALID_ARGUMENT: 目标目录父级不存在或不是目录")

    candidate_paths = [Path(candidate).resolve() for candidate in candidates]
    destination_resolved = destination.resolve()
    if any(destination_resolved.is_relative_to(candidate) for candidate in candidate_paths):
        raise ValueError("INVALID_ARGUMENT: 目标目录不能位于候选目录内")
    seen_books = set()
    seen_cards = set()
    seen_evidence = set()
    seen_relations = set()
    candidate_infos = []

    # 先收集和验证所有输入，不在任何候选尚未通过验证时创建输出目录。
    for candidate_index, candidate in enumerate(candidate_paths):
        if not candidate.is_dir():
            raise ValueError(f"INVALID_CANDIDATE: 候选目录不存在或不是目录: {candidate}")
        source_root = candidate / "sources"
        if not source_root.is_dir():
            raise ValueError(f"INVALID_CANDIDATE: 缺少 sources 目录: {candidate}")
        try:
            validate_library(candidate)
            candidate_version = content_version(candidate)
            manifest = read_json(candidate / "manifest.json")
            books = manifest["books"]
            cards = load_records(candidate / "cards")
            evidence = load_records(candidate / "evidence")
            graph = read_json(candidate / "relations.json")
        except ValueError:
            raise
        except (OSError, KeyError, TypeError) as exc:
            raise ValueError(f"INVALID_CANDIDATE: 无法读取候选库: {candidate}") from exc

        if len(books) != 1:
            raise ValueError(f"INVALID_CANDIDATE: 候选必须只包含一本书: {candidate}")
        book = dict(books[0])
        book_id = book.get("id")
        if not isinstance(book_id, str) or not book_id:
            raise ValueError(f"INVALID_CANDIDATE: 书籍 ID 无效: {candidate}")
        if release_status == "accepted_candidate":
            _validate_acceptance_marker(manifest, book, candidate)
        if book_id in seen_books:
            raise ValueError(f"DUPLICATE: 书籍 ID 重复: {book_id}")
        seen_books.add(book_id)
        prefix = _book_prefix(book_id, candidate_index)

        for identifier in cards:
            if identifier in seen_cards:
                raise ValueError(f"DUPLICATE: 知识卡 ID 重复: {identifier}")
            seen_cards.add(identifier)
        for identifier in evidence:
            if identifier in seen_evidence:
                raise ValueError(f"DUPLICATE: 证据 ID 重复: {identifier}")
            seen_evidence.add(identifier)
        for edge in graph["edges"]:
            identifier = edge["id"]
            if identifier in seen_relations:
                raise ValueError(f"DUPLICATE: 关系 ID 重复: {identifier}")
            seen_relations.add(identifier)
        coverage_path = candidate / "coverage.json"
        if coverage_path.exists() and not coverage_path.is_file():
            raise ValueError(f"INVALID_CANDIDATE: 缺少 coverage.json: {candidate}")
        candidate_infos.append({
            "candidate": candidate,
            "candidate_index": candidate_index,
            "version": candidate_version,
            "book": book,
            "book_id": book_id,
            "prefix": prefix,
            "cards": cards,
            "evidence": evidence,
            "edges": graph["edges"],
            "coverage": coverage_path if coverage_path.is_file() else None,
            "source_root": source_root,
        })

    lock_path = destination.parent / f".{destination.name}.merge.lock"
    lock_held = False
    temporary = None
    try:
        try:
            lock_path.mkdir()
        except FileExistsError as exc:
            raise ValueError(f"MERGE_BUSY: 目标正在被另一个合并任务处理: {destination}") from exc
        lock_held = True
        if destination.exists() or destination.is_symlink():
            raise ValueError("DESTINATION_EXISTS: 目标目录已存在")
        temporary = Path(tempfile.mkdtemp(prefix=".merge-", dir=destination.parent))
        (temporary / "cards").mkdir()
        (temporary / "evidence").mkdir()
        (temporary / "sources").mkdir()
        (temporary / "coverage").mkdir()

        books = []
        edges = []
        for info in candidate_infos:
            candidate = info["candidate"]
            candidate_index = info["candidate_index"]
            book_id = info["book_id"]
            books.append(info["book"])
            shutil.copytree(info["source_root"], temporary / "sources" / f"candidate-{candidate_index:03d}")
            if info["coverage"] is not None:
                shutil.copyfile(info["coverage"], temporary / "coverage" / f"{book_id}.json")

            for filename in sorted((candidate / "cards").glob("*.json")):
                card = info["cards"][read_json(filename)["id"]]
                write_json(temporary / "cards" / f"{info['prefix']}{filename.name}", card)
            for filename in sorted((candidate / "evidence").glob("*.json")):
                evidence = dict(info["evidence"][read_json(filename)["id"]])
                evidence["source_path"] = _source_path_for_merge(
                    candidate, evidence, info["source_root"], candidate_index
                ).as_posix()
                write_json(temporary / "evidence" / f"{info['prefix']}{filename.name}", evidence)
            edges.extend(info["edges"])

        # 候选在读取后若发生变化，放弃本次输出，避免组合出混合版本。
        for info in candidate_infos:
            if content_version(info["candidate"]) != info["version"]:
                raise ValueError(f"SOURCE_VERSION_MISMATCH: 候选在合并期间变化: {info['candidate']}")

        manifest = {
            "schema_version": 1,
            "library_id": library_id,
            "is_example": False,
            "books": books,
            "cards_directory": "cards",
            "evidence_directory": "evidence",
            "relations_file": "relations.json",
            "coverage_directory": "coverage",
            "distillation_mode": "multi_book_candidate",
            "release_status": release_status,
        }
        write_json(temporary / "manifest.json", manifest)
        write_json(temporary / "relations.json", {"schema_version": 1, "edges": edges})
        report = validate_library(temporary)
        # 锁只串行化遵守本约定的 merge 调用；最终再检查目标，拒绝锁持有期间出现的目标。
        if destination.exists() or destination.is_symlink():
            raise ValueError("DESTINATION_EXISTS: 目标目录已存在")
        os.replace(temporary, destination)
        temporary = None
        return {
            **report,
            "path": str(destination.resolve()),
            "library_id": library_id,
            "release_status": release_status,
            "books": report["books"],
            "cards": report["cards"],
            "evidence": report["evidence"],
            "relations": report["relations"],
            "source_candidates": [str(candidate) for candidate in candidate_paths],
        }
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary)
        if lock_held:
            lock_path.rmdir()
