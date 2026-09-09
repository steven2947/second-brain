"""十书蒸馏批次计划的只读加载与确定性校验。"""

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "schemas/distillation-batch-plan.schema.json"
VALID_STATUSES = {"planned", "prepared", "distilled", "accepted", "blocked"}
EXPECTED_WAVES = {"1": 5, "2": 5}


def _load_schema() -> dict[str, Any]:
    """读取批次计划 JSON Schema；无参数，返回 schema 对象。"""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate_schema(plan: dict[str, Any]) -> None:
    """验证计划的 JSON Schema；plan 为待校验的计划对象。"""
    errors = sorted(Draft202012Validator(_load_schema()).iter_errors(plan), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or "root"
        field = str(error.path[-1]) if error.path else ""
        code = {
            "book_id": "BOOK_ID",
            "order": "ORDER",
            "source_relative_path": "SOURCE_PATH",
            "status": "STATUS",
            "wave": "WAVE",
        }.get(field, "SCHEMA")
        raise ValueError(f"{code}: {location}: {error.message}")


def _normalise_source_path(value: str) -> PurePosixPath:
    """校验并规范来源相对路径；value 为计划中的 POSIX 相对路径。"""
    if "\\" in value or re.match(r"^[A-Za-z]:[\\/]", value):
        raise ValueError(f"SOURCE_PATH: 路径必须是项目内 POSIX 相对路径：{value}")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"SOURCE_PATH: 路径不能绝对化或越界：{value}")
    normalised = PurePosixPath(*[part for part in relative.parts if part != "."])
    if not normalised.parts:
        raise ValueError(f"SOURCE_PATH: 路径不能为空：{value}")
    return normalised


def _validate_entries(plan: dict[str, Any]) -> list[PurePosixPath]:
    """校验书目字段、顺序、波次和来源唯一性；plan 为已通过 schema 的计划。"""
    books = plan["books"]
    book_ids: set[str] = set()
    orders: set[int] = set()
    source_paths: set[PurePosixPath] = set()
    normalised_paths: list[PurePosixPath] = []

    for book in books:
        book_id = book["book_id"]
        if book_id in book_ids:
            raise ValueError(f"BOOK_ID: 书籍 ID 重复：{book_id}")
        book_ids.add(book_id)

        order = book["order"]
        if order in orders:
            raise ValueError(f"ORDER: 书籍顺序重复：{order}")
        orders.add(order)

        if book["wave"] not in (1, 2):
            raise ValueError(f"WAVE: 不支持的蒸馏波次：{book['wave']}")
        if book["status"] not in VALID_STATUSES:
            raise ValueError(f"STATUS: 不支持的书籍状态：{book['status']}")

        source_path = _normalise_source_path(book["source_relative_path"])
        if source_path in source_paths:
            raise ValueError(f"SOURCE_PATH: 来源路径重复：{source_path.as_posix()}")
        source_paths.add(source_path)
        normalised_paths.append(source_path)

    if orders != set(range(1, 11)):
        raise ValueError(f"ORDER: 书籍顺序必须完整覆盖 1 到 10：{sorted(orders)}")

    actual_waves = {str(wave): sum(book["wave"] == wave for book in books) for wave in (1, 2)}
    if actual_waves != EXPECTED_WAVES or plan["waves"] != EXPECTED_WAVES:
        raise ValueError(
            f"WAVE_COUNT: 波次必须各有五本且与计划一致：实际 {actual_waves}，计划 {plan['waves']}"
        )
    return normalised_paths


def _check_sources(
    paths: list[PurePosixPath], source_root: str | Path | None
) -> int:
    """只读检查来源文件存在性；paths 为相对路径，source_root 为原书根目录。"""
    if source_root is None:
        raise ValueError("SOURCE_ROOT: 启用来源检查时必须提供原书根目录")
    root = Path(source_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"SOURCE_ROOT: 原书根目录不存在：{root}")

    checked = 0
    for relative in paths:
        candidate = (root / relative.as_posix()).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"SOURCE_PATH: 来源路径越出原书根目录：{relative}") from exc
        if not candidate.is_file():
            raise ValueError(f"SOURCE_PATH: 来源文件不存在：{relative}")
        checked += 1
    return checked


def load_batch_plan(path: str | Path) -> dict[str, Any]:
    """读取并校验计划 JSON；path 为十书计划文件路径，返回计划对象。"""
    plan_path = Path(path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("SCHEMA: root: 计划 JSON 顶层必须为对象")
    _validate_schema(plan)
    _validate_entries(plan)
    return plan


def validate_batch_plan(
    plan: dict[str, Any],
    source_root: str | Path | None = None,
    check_sources: bool = False,
    wave: int | None = None,
) -> dict[str, Any]:
    """校验十书计划及可选来源；plan 为计划对象，source_root 为原书根目录，check_sources 控制文件检查，wave 限制结果波次。"""
    if not isinstance(plan, dict):
        raise ValueError("SCHEMA: root: 计划必须为对象")
    if wave is not None and wave not in (1, 2):
        raise ValueError(f"WAVE: 不支持的波次过滤器：{wave}")
    _validate_schema(plan)
    source_paths = _validate_entries(plan)

    selected = [book for book in plan["books"] if wave is None or book["wave"] == wave]
    selected_paths = [
        source_path
        for book, source_path in zip(plan["books"], source_paths)
        if wave is None or book["wave"] == wave
    ]
    checked = _check_sources(selected_paths, source_root) if check_sources else 0
    wave_counts = {
        str(number): sum(book["wave"] == number for book in selected)
        for number in (1, 2)
        if wave is None or wave == number
    }
    return {
        "schema_version": 1,
        "plan_id": plan["plan_id"],
        "wave": wave,
        "books": len(selected),
        "waves": wave_counts,
        "source_paths_checked": checked,
    }
