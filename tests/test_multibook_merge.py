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
        self.destination = root / "merged"

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
