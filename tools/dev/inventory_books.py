#!/usr/bin/env python3
"""只读盘点原书 Markdown；不调用模型，不移动或修改原文件。"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from project_paths import load_local_config, resolve_path


def collect_books(root: Path) -> dict:
    """盘点书籍与指纹；root 为原书根目录，按目录名和文件名一致识别书籍。"""
    if not root.is_dir():
        raise ValueError(f"原书目录不存在：{root}")
    books = []
    for path in sorted(root.rglob("*.md")):
        # 当前来源布局为“书名/书名.md”，自然排除独立质检报告。
        if path.stem != path.parent.name:
            continue
        content = path.read_bytes()
        books.append({
            "title": path.stem,
            "relative_path": path.relative_to(root).as_posix(),
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "distillation_status": "not_assessed",
        })
    # 目录清单不是蒸馏状态事实源，不从原文件存在推导已经入库。
    return {"schema_version": 1, "book_count": len(books),
            "total_bytes": sum(item["bytes"] for item in books), "books": books}


def main() -> int:
    """解析命令行；--summary 仅输出数量和大小，完整模式输出书目指纹。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true", help="仅显示书籍数量与大小")
    args = parser.parse_args()
    try:
        root = resolve_path(load_local_config()["source_books_root"])
        result = collect_books(root)
        if args.summary:
            result.pop("books")
            result["note"] = "仅原书盘点，不代表已蒸馏、已验收或已入库"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f"盘点失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
