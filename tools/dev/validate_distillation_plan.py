#!/usr/bin/env python3
"""只读校验十书蒸馏计划；不创建任务、不修改计划、不推断蒸馏状态。"""

import argparse
import json
import sys
from pathlib import Path

from project_paths import load_local_config, resolve_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.distillation.batch_plan import load_batch_plan, validate_batch_plan


def main() -> int:
    """解析计划校验参数并输出 JSON；无参数，失败返回退出码 1。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, help="十书计划 JSON 路径")
    parser.add_argument("--source-root", help="原书根目录；省略时读取 configs/local.json")
    parser.add_argument("--check-sources", action="store_true", help="只读检查来源文件是否存在")
    parser.add_argument("--wave", type=int, choices=(1, 2), help="只输出指定波次")
    args = parser.parse_args()

    try:
        source_root = None
        if args.check_sources:
            source_root = (
                resolve_path(args.source_root)
                if args.source_root
                else resolve_path(load_local_config()["source_books_root"])
            )
        result = validate_batch_plan(
            load_batch_plan(args.plan),
            source_root=source_root,
            check_sources=args.check_sources,
            wave=args.wave,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(
            json.dumps({"schema_version": 1, "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
