"""十书批次计划的结构、安全边界和只读来源检查。"""

import copy
import tempfile
import unittest
from pathlib import Path

from src.distillation.batch_plan import load_batch_plan, validate_batch_plan


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN = PROJECT_ROOT / "configs/ten-book-distillation-plan.json"


def _plan_with_test_sources(root: Path) -> dict:
    """为测试计划创建临时占位来源；root 为临时只读来源根目录。"""
    plan = load_batch_plan(PLAN)
    for book in plan["books"]:
        source = root / book["source_relative_path"]
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("测试占位来源，不代表真实书籍内容。", encoding="utf-8")
    return plan


class BatchPlanTests(unittest.TestCase):
    """验证十书清单的固定结构、路径隔离和波次约束。"""

    def test_approved_plan_has_ten_unique_books_in_two_waves(self):
        """固定计划必须包含十本唯一书目，并按两波各五本分组。"""
        result = validate_batch_plan(load_batch_plan(PLAN), wave=None)
        self.assertEqual(result["books"], 10)
        self.assertEqual(result["waves"], {"1": 5, "2": 5})

    def test_source_check_accepts_relative_files_and_rejects_absolute_escape(self):
        """来源检查只接受临时根目录内的相对文件，拒绝越界路径。"""
        with tempfile.TemporaryDirectory() as directory:
            source_root = Path(directory)
            plan = _plan_with_test_sources(source_root)
            result = validate_batch_plan(
                plan, source_root=source_root, check_sources=True
            )
            self.assertEqual(result["source_paths_checked"], 10)

            plan["books"][0]["source_relative_path"] = "../outside.md"
            with self.assertRaisesRegex(ValueError, "SOURCE_PATH"):
                validate_batch_plan(plan, source_root=source_root, check_sources=True)

            plan["books"][0]["source_relative_path"] = str(
                source_root / "absolute.md"
            )
            with self.assertRaisesRegex(ValueError, "SOURCE_PATH"):
                validate_batch_plan(plan, source_root=source_root, check_sources=True)

    def test_duplicate_book_id_and_invalid_wave_are_rejected(self):
        """重复书籍 ID 和非法波次必须分别被明确拒绝。"""
        plan = load_batch_plan(PLAN)
        plan["books"][1]["book_id"] = plan["books"][0]["book_id"]
        with self.assertRaisesRegex(ValueError, "BOOK_ID"):
            validate_batch_plan(plan)

        plan = load_batch_plan(PLAN)
        plan["books"][0]["wave"] = 3
        with self.assertRaisesRegex(ValueError, "WAVE"):
            validate_batch_plan(plan)

    def test_duplicate_order_source_and_wrong_wave_counts_are_rejected(self):
        """重复顺序、重复来源和错误波次计数不得通过校验。"""
        plan = load_batch_plan(PLAN)
        plan["books"][1]["order"] = plan["books"][0]["order"]
        with self.assertRaisesRegex(ValueError, "ORDER"):
            validate_batch_plan(plan)

        plan = load_batch_plan(PLAN)
        plan["books"][1]["source_relative_path"] = plan["books"][0][
            "source_relative_path"
        ]
        with self.assertRaisesRegex(ValueError, "SOURCE_PATH"):
            validate_batch_plan(plan)

        plan = load_batch_plan(PLAN)
        plan["waves"]["1"] = 4
        with self.assertRaisesRegex(ValueError, "WAVE_COUNT"):
            validate_batch_plan(plan)

    def test_source_files_are_not_checked_without_explicit_flag(self):
        """未启用来源检查时，不应因不存在的来源根目录而读取原书。"""
        plan = load_batch_plan(PLAN)
        result = validate_batch_plan(
            copy.deepcopy(plan), source_root=Path("/path/that/does/not/exist")
        )
        self.assertEqual(result["source_paths_checked"], 0)


if __name__ == "__main__":
    unittest.main()
