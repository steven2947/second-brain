"""多书候选合并器的真实文件与原子性测试。"""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.distillation.merge import merge_libraries
from src.knowledge.library import Library, content_version, load_records, validate_library


class MultiBookMergeTests(unittest.TestCase):
    """使用两个隔离的自编单书候选检查多书装配行为。"""

    def setUp(self):
        """建立临时候选目录；不修改项目中的示例书库。"""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        sample = Path(__file__).parents[1] / "examples/sample-library"
        self.first = root / "candidate-first"
        self.second = root / "candidate-second"
        shutil.copytree(sample, self.first)
        shutil.copytree(sample, self.second)
        self._rewrite_second_candidate(self.second)
        self.first_coverage = self._write_coverage(self.first, "book.demo")
        self.second_coverage = self._write_coverage(self.second, "book.second")
        self.destination = root / "merged"

    @staticmethod
    def _write_coverage(candidate, book_id):
        """写入测试覆盖率 fixture；candidate 为临时候选目录，book_id 为书籍标识，返回原始字节。"""
        contents = json.dumps(
            {"book_id": book_id, "status": "test_fixture", "sections": ["fixture-section"]},
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8") + b"\n"
        (candidate / "coverage.json").write_bytes(contents)
        return contents

    @staticmethod
    def _rewrite_second_candidate(candidate):
        """改写第二个测试候选；candidate 为待改写的临时候选目录。"""
        manifest_path = candidate / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        book = manifest["books"][0]
        book["id"] = "book.second"
        book["title"] = "第二本独立测试书"
        manifest["library_id"] = "library.second-test"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        replacements = {
            "knowledge.demo.": "knowledge.second.",
            "evidence.demo.": "evidence.second.",
            "relation.demo.": "relation.second.",
            "book.demo": "book.second",
        }
        for path in sorted((candidate / "cards").glob("*.json")):
            item = json.loads(path.read_text(encoding="utf-8"))
            for old, new in replacements.items():
                for field in ("id", "book_id"):
                    if field in item and isinstance(item[field], str):
                        item[field] = item[field].replace(old, new)
                item["evidence_ids"] = [value.replace(old, new) for value in item["evidence_ids"]]
            path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        source_path = candidate / "sources" / "demo.md"
        source_text = source_path.read_text(encoding="utf-8").replace("模糊", "含糊").replace("小步骤", "小行动")
        source_path.write_text(source_text, encoding="utf-8")
        source_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        for path in sorted((candidate / "evidence").glob("*.json")):
            item = json.loads(path.read_text(encoding="utf-8"))
            for old, new in replacements.items():
                for field in ("id", "book_id"):
                    if field in item and isinstance(item[field], str):
                        item[field] = item[field].replace(old, new)
            item["source_sha256"] = source_sha256
            item["text"] = item["text"].replace("模糊", "含糊").replace("小步骤", "小行动")
            path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        relation_path = candidate / "relations.json"
        graph = json.loads(relation_path.read_text(encoding="utf-8"))
        for edge in graph["edges"]:
            for field in ("id", "from", "to"):
                for old, new in replacements.items():
                    if isinstance(edge[field], str):
                        edge[field] = edge[field].replace(old, new)
            edge["evidence_ids"] = [
                value.replace("evidence.demo.", "evidence.second.") for value in edge["evidence_ids"]
            ]
        relation_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_merge_preserves_books_and_isolates_evidence_sources(self):
        """合并保留两本书，并把证据来源隔离到候选子目录。"""
        result = merge_libraries([self.first, self.second], self.destination, "library.two-book-test")

        report = validate_library(self.destination)
        self.assertEqual(report["books"], 2)
        self.assertEqual(len(Library(self.destination).list_books()), 2)
        evidence = load_records(self.destination / "evidence")
        self.assertEqual(len({item["source_path"] for item in evidence.values()}), 2)
        self.assertTrue(all(item["source_path"].startswith("sources/candidate-") for item in evidence.values()))
        self.assertEqual(result["library_id"], "library.two-book-test")
        self.assertEqual(result["books"], 2)
        self.assertEqual(result["cards"], 4)
        self.assertEqual(result["evidence"], 4)
        self.assertEqual(result["relations"], 2)
        self.assertEqual(result["source_candidates"], [str(self.first.resolve()), str(self.second.resolve())])
        self.assertEqual((self.destination / "coverage/book.demo.json").read_bytes(), self.first_coverage)
        self.assertEqual((self.destination / "coverage/book.second.json").read_bytes(), self.second_coverage)

    def test_legacy_candidate_without_coverage_remains_compatible(self):
        """没有 coverage.json 的旧候选仍可合并，并保留空 coverage 目录。"""
        sample = Path(__file__).parents[1] / "examples/sample-library"
        candidate = Path(self.temp.name) / "legacy-without-coverage"
        destination = Path(self.temp.name) / "legacy-merged"
        shutil.copytree(sample, candidate)
        merge_libraries([candidate], destination, "library.legacy-coverage-test")
        self.assertEqual(list((destination / "coverage").iterdir()), [])

    def test_accepted_candidate_requires_acceptance_marker(self):
        """accepted_candidate 输出必须拒绝无标记或评测状态的输入。"""
        for status in ("example_only", "evaluation_candidate", "blocked"):
            with self.subTest(status=status):
                for candidate in (self.first, self.second):
                    manifest_path = candidate / "manifest.json"
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["is_example"] = False
                    manifest.pop("release_status", None)
                    manifest["books"][0]["status"] = status
                    manifest_path.write_text(
                        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                    )
                with self.assertRaisesRegex(ValueError, "ACCEPT"):
                    merge_libraries([self.first, self.second], self.destination, "library.acceptance-test", "accepted_candidate")
                self.assertFalse(self.destination.exists())
                sample = Path(__file__).parents[1] / "examples/sample-library"
                shutil.copytree(sample, self.first, dirs_exist_ok=True)
                shutil.copytree(sample, self.second, dirs_exist_ok=True)
                self._rewrite_second_candidate(self.second)
                self.first_coverage = self._write_coverage(self.first, "book.demo")
                self.second_coverage = self._write_coverage(self.second, "book.second")

    def test_accepted_candidate_rejects_example_flag_even_with_marker(self):
        """is_example=true 即使带 accepted 标记也不得升格。"""
        for candidate in (self.first, self.second):
            manifest_path = candidate / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["is_example"] = True
            manifest["release_status"] = "accepted_candidate"
            manifest["books"][0]["status"] = "accepted"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "ACCEPT"):
            merge_libraries([self.first, self.second], self.destination, "library.example-acceptance-test", "accepted_candidate")
        self.assertFalse(self.destination.exists())

    def test_accepted_candidate_accepts_explicit_markers(self):
        """显式 accepted_candidate 或 accepted 标记可以通过接受门禁。"""
        first_manifest_path = self.first / "manifest.json"
        first_manifest = json.loads(first_manifest_path.read_text(encoding="utf-8"))
        first_manifest["is_example"] = False
        first_manifest["release_status"] = "accepted_candidate"
        first_manifest["books"][0]["status"] = "distilled"
        first_manifest_path.write_text(json.dumps(first_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        second_manifest_path = self.second / "manifest.json"
        second_manifest = json.loads(second_manifest_path.read_text(encoding="utf-8"))
        second_manifest["is_example"] = False
        second_manifest.pop("release_status", None)
        second_manifest["books"][0]["status"] = "accepted"
        second_manifest_path.write_text(json.dumps(second_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        result = merge_libraries([self.first, self.second], self.destination, "library.explicit-acceptance-test", "accepted_candidate")
        self.assertEqual(result["release_status"], "accepted_candidate")

    def test_current_naval_pilot_agent_reviewed_status_is_accepted_compatibility(self):
        """当前已发布 Naval 的 agent_reviewed_pilot 形态可向后兼容接受。"""
        library_root = Path(__file__).parents[1] / "data" / "library"
        current_version = (library_root / "CURRENT").read_text(encoding="utf-8").strip()
        naval = library_root / "versions" / current_version
        if not naval.is_dir():
            self.skipTest("当前本地 Naval 已发布候选不存在")
        result = merge_libraries([naval], self.destination, "library.naval-compatibility-test", "accepted_candidate")
        self.assertEqual(result["books"], 1)
        self.assertEqual(result["release_status"], "accepted_candidate")

    def test_tampered_copy_of_current_naval_is_not_accepted(self):
        """只篡改当前 Naval 副本的一张卡片也必须拒绝升格且不创建目标。"""
        library_root = Path(__file__).parents[1] / "data" / "library"
        current_version = (library_root / "CURRENT").read_text(encoding="utf-8").strip()
        naval = library_root / "versions" / current_version
        if not naval.is_dir():
            self.skipTest("当前本地 Naval 已发布候选不存在")

        tampered = Path(self.temp.name) / "tampered-naval"
        shutil.copytree(naval, tampered)
        card_path = sorted((tampered / "cards").glob("*.json"))[0]
        card = json.loads(card_path.read_text(encoding="utf-8"))
        self.assertIsInstance(card["statement"], str)
        card["statement"] += "（回归测试篡改）"
        card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "ACCEPTANCE_REQUIRED"):
            merge_libraries([tampered], self.destination, "library.naval-tampered-test", "accepted_candidate")
        self.assertFalse(self.destination.exists())

    def test_merge_lock_rejects_competing_call_without_touching_destination(self):
        """同一目标的已有合并锁应拒绝竞争调用并保留锁与目标状态。"""
        lock = self.destination.parent / f".{self.destination.name}.merge.lock"
        lock.mkdir()
        self.addCleanup(lambda: lock.rmdir())
        with self.assertRaisesRegex(ValueError, "MERGE_BUSY"):
            merge_libraries([self.first], self.destination, "library.lock-test")
        self.assertFalse(self.destination.exists())
        self.assertTrue(lock.is_dir())

    def test_duplicate_book_or_card_id_is_rejected_without_destination(self):
        """重复书籍或记录标识必须在任何输出创建前拒绝。"""
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            merge_libraries([self.first, self.first], self.destination, "library.duplicate-test")
        self.assertFalse(self.destination.exists())

    def test_invalid_candidate_and_existing_destination_are_rejected(self):
        """无效候选和已有目标都不能留下部分合并结果。"""
        (self.first / "sources/demo.md").write_text("损坏", encoding="utf-8")
        with self.assertRaises(ValueError):
            merge_libraries([self.first, self.second], self.destination, "library.invalid-test")
        self.assertFalse(self.destination.exists())

        self.destination.mkdir()
        with self.assertRaisesRegex(ValueError, "DESTINATION_EXISTS"):
            merge_libraries([self.second], self.destination, "library.existing-test")
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_repeated_ordered_merge_has_same_content_version(self):
        """相同顺序的候选重复合并应得到相同内容指纹。"""
        first_destination = self.destination
        second_destination = Path(self.temp.name) / "merged-again"
        merge_libraries([self.first, self.second], first_destination, "library.deterministic-test")
        merge_libraries([self.first, self.second], second_destination, "library.deterministic-test")
        self.assertEqual(content_version(first_destination), content_version(second_destination))

    def test_duplicate_card_evidence_or_relation_id_is_rejected(self):
        """不同书籍也不得共享知识卡、证据或关系 ID。"""
        sample = Path(__file__).parents[1] / "examples/sample-library"
        for index, (relative_path, identifier) in enumerate(
            (
            ("cards/review.json", "knowledge.demo.review"),
            ("evidence/review.json", "evidence.demo.review"),
            ("relations.json", "relation.demo.step-review"),
            )
        ):
            with self.subTest(relative_path=relative_path):
                candidate = Path(self.temp.name) / f"candidate-duplicate-{index}"
                shutil.copytree(sample, candidate)
                self._rewrite_second_candidate(candidate)
                path = candidate / relative_path
                item = json.loads(path.read_text(encoding="utf-8"))
                if relative_path == "relations.json":
                    item["edges"][0]["id"] = identifier
                elif relative_path == "cards/review.json":
                    item["id"] = identifier
                    relation_path = candidate / "relations.json"
                    graph = json.loads(relation_path.read_text(encoding="utf-8"))
                    for edge in graph["edges"]:
                        edge["to"] = edge["to"].replace("knowledge.second.review", identifier)
                    relation_path.write_text(
                        json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                    )
                else:
                    item["id"] = identifier
                    for record_path in sorted((candidate / "cards").glob("*.json")):
                        card = json.loads(record_path.read_text(encoding="utf-8"))
                        card["evidence_ids"] = [
                            value.replace("evidence.second.review", identifier) for value in card["evidence_ids"]
                        ]
                        record_path.write_text(
                            json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                        )
                    relation_path = candidate / "relations.json"
                    graph = json.loads(relation_path.read_text(encoding="utf-8"))
                    for edge in graph["edges"]:
                        edge["evidence_ids"] = [
                            value.replace("evidence.second.review", identifier) for value in edge["evidence_ids"]
                        ]
                    relation_path.write_text(
                        json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                    )
                path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "DUPLICATE"):
                    merge_libraries([self.first, candidate], self.destination, "library.duplicate-record-test")
                self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
