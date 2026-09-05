#!/usr/bin/env python3
"""检查项目基础、固定依赖和自编示例；不证明真实全书蒸馏质量。"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from project_paths import PROJECT_ROOT, load_local_config, read_json, resolve_path


def require(condition: bool, message: str) -> None:
    """验证不变量；condition 为检查结果，message 为失败说明。"""
    if not condition:
        raise ValueError(message)


def check_vendor() -> str:
    """核对仓颉工作副本与锁定提交；不运行或修改上游代码。"""
    lock = read_json(PROJECT_ROOT / "vendor/cangjie.lock.json")
    root = PROJECT_ROOT / lock["directory"]
    actual = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            check=True, capture_output=True, text=True).stdout.strip()
    require(actual == lock["commit"], "仓颉提交与锁文件不一致")
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                           check=True, capture_output=True, text=True).stdout.strip()
    require(not dirty, "仓颉工作副本存在修改，请检查后再接入")
    return f"{lock['tag']} @ {actual[:12]}，工作副本无修改"


def check_paths() -> str:
    """检查本机配置与项目数据目录；不创建目录或文件。"""
    config = load_local_config()
    for key in ("source_books_root", "library_root", "normalized_root", "index_root", "jobs_root"):
        require(resolve_path(config[key]).is_dir(), f"配置目录不存在：{key}")
    for name in ("docs", "schemas", "src/knowledge", "src/distillation", "src/retrieval",
                 "src/interfaces", "skills/second-brain", "prompts/distillation", "tests", "dist"):
        require((PROJECT_ROOT / name).is_dir(), f"缺少目录：{name}")
    return "本机来源与项目职责目录可访问"


def indexed_documents(root: Path) -> dict:
    """按唯一 ID 读取目录内 JSON；root 为卡片或证据目录。"""
    result = {}
    for path in sorted(root.glob("*.json")):
        item = read_json(path)
        identifier = item.get("id")
        require(isinstance(identifier, str) and bool(identifier), f"缺少 ID：{path.name}")
        require(identifier not in result, f"重复 ID：{identifier}")
        result[identifier] = item
    require(bool(result), f"示例目录为空：{root.name}")
    return result


def check_sample(root: Path, schemas: bool = False) -> str:
    """核对自编示例引用；root 为示例库根目录，schemas 决定是否额外执行 JSON Schema。"""
    root = root.resolve()
    manifest = read_json(root / "manifest.json")
    require(manifest.get("is_example") is True, "示例库必须显式标注 is_example")
    books = {item["id"]: item for item in manifest["books"]}
    require(len(books) == len(manifest["books"]), "书籍 ID 重复")
    cards = indexed_documents(root / "cards")
    evidence = indexed_documents(root / "evidence")
    graph = read_json(root / "relations.json")
    for item in evidence.values():
        require(item["book_id"] in books, f"证据书籍不存在：{item['id']}")
        path = (root / item["source_path"]).resolve()
        require(not Path(item["source_path"]).is_absolute() and path.is_relative_to(root),
                f"来源路径越界：{item['id']}")
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        require(hashlib.sha256(raw).hexdigest() == item["source_sha256"], f"来源指纹改变：{item['id']}")
        start, end = item["start"], item["end"]
        require(type(start) is int and type(end) is int and 0 <= start < end <= len(text),
                f"证据范围无效：{item['id']}")
        require(text[start:end] == item["text"], f"原文与证据不一致：{item['id']}")
    for card in cards.values():
        require(card["book_id"] in books, f"知识书籍不存在：{card['id']}")
        require(card["author_id"] == books[card["book_id"]]["author_id"], f"作者归属错误：{card['id']}")
        require(bool(card["evidence_ids"]), f"缺少证据：{card['id']}")
        for identifier in card["evidence_ids"]:
            require(identifier in evidence, f"证据引用悬空：{identifier}")
            require(evidence[identifier]["book_id"] == card["book_id"], f"跨书证据归属错误：{identifier}")
    edge_ids = set()
    for edge in graph["edges"]:
        require(edge["id"] not in edge_ids, f"关系 ID 重复：{edge['id']}")
        edge_ids.add(edge["id"])
        require(edge["from"] in cards and edge["to"] in cards, f"关系端点悬空：{edge['id']}")
        require(bool(edge["evidence_ids"]), f"关系缺少依据：{edge['id']}")
        require(all(key in evidence for key in edge["evidence_ids"]), f"关系证据悬空：{edge['id']}")
    if schemas:
        validate_schemas(cards, evidence, graph)
    return f"{len(cards)} 张自编卡片、{len(evidence)} 条证据、{len(graph['edges'])} 条关系可核对"


def validate_schemas(cards: dict, evidence: dict, graph: dict) -> None:
    """执行完整格式验证；cards、evidence 为按 ID 索引的对象，graph 为关系文件。"""
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise ValueError("缺少 jsonschema，请使用已安装开发依赖的 .venv/bin/python") from exc
    groups = (("knowledge-card.schema.json", cards.values()),
              ("evidence.schema.json", evidence.values()), ("relations.schema.json", [graph]))
    for filename, items in groups:
        schema = read_json(PROJECT_ROOT / "schemas" / filename)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for item in items:
            errors = list(validator.iter_errors(item))
            require(not errors, f"{filename} 格式失败：{errors[0].message if errors else ''}")


def main() -> int:
    """运行检查并返回退出码；--json 输出结构化结果，--schemas 增加严格格式验证。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--schemas", action="store_true", help="使用 jsonschema 完整验证示例")
    args = parser.parse_args()
    checks = []
    for name, action in (("paths", check_paths), ("cangjie", check_vendor),
                         ("sample", lambda: check_sample(PROJECT_ROOT / "examples/sample-library", args.schemas))):
        try:
            checks.append({"name": name, "passed": True, "detail": action()})
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            checks.append({"name": name, "passed": False, "detail": str(exc)})
    passed = all(item["passed"] for item in checks)
    result = {"bootstrap_ready": passed, "mvp_record_available": (PROJECT_ROOT / "docs/mvp-verification.md").is_file(), "checks": checks}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in checks:
            print(f"{'PASS' if item['passed'] else 'FAIL'} {item['name']}: {item['detail']}")
        print("基础检查通过" if passed else "基础检查未通过")
        print("本命令仅检查开发基础；真实单书验收见 docs/mvp-verification.md")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
