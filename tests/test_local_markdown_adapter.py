"""本地 v1.2 Markdown 蒸馏成果导入 Second Brain 的端到端契约。"""
import hashlib
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import yaml

from src.distillation.local_markdown_adapter import import_local_books
from src.knowledge.library import Library, validate_library
from src.interfaces.cli import main as cli_main


class LocalMarkdownAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.book_dir = self.root / "BOOK-9001"
        self.book_dir.mkdir()
        self.source = self.root / "source.md"
        self.source_text = "# 第一章\n\n先看清事实，再做决定。\n\n把大任务拆成可验证的小步骤。\n"
        self.source.write_text(self.source_text, encoding="utf-8")
        self.source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        (self.book_dir / "book.yaml").write_text(yaml.safe_dump({
            "book_id": "BOOK-9001",
            "title": "测试书",
            "author": "测试作者",
            "source_md": str(self.source),
            "source_sha256": self.source_hash,
            "distillation_status": "ready_for_human_acceptance",
        }, allow_unicode=True), encoding="utf-8")
        first = "先看清事实，再做决定。"
        second = "把大任务拆成可验证的小步骤。"
        self.write_card("01_知识卡", "K-BOOK-9001-C01-A", "principle", "先看事实", first)
        self.write_card("04_问题与行动", "Q-BOOK-9001-C01-B", "question", "下一步是什么", second)
        relations = self.book_dir / "06_关系"
        relations.mkdir()
        (relations / "relations.json").write_text(json.dumps({
            "edges": [{
                "id": "E-1", "source": "K-BOOK-9001-C01-A", "target": "Q-BOOK-9001-C01-B",
                "relation": "APPLIES_TO", "explanation": "原理用于产生行动问题", "evidence_ids": []
            }]
        }, ensure_ascii=False), encoding="utf-8")

    def write_card(self, dirname, card_id, kind, title, quote):
        start = self.source_text.index(quote)
        metadata = {
            "schema_version": 1.2,
            "id": card_id,
            "type": kind,
            "title": title,
            "status": "verified",
            "source": {"chapter": "C01", "heading_path": "第一章", "speaker_role": "author"},
            "primary_sources": [{
                "source_id": "SRC-" + card_id,
                "chapter": "C01", "heading_path": "第一章", "anchor_quote": quote,
                "char_span": [start, start + len(quote)], "source_hash": self.source_hash,
                "role": "direct_claim",
            }],
            "content": {
                "proposition": quote, "explanation": "这是对原理的简明解释。",
                "assumptions": ["面临可选择的行动"], "attribution_layer": "author_claim",
            },
            "application": {"steps": ["写出一个小步骤"], "non_applicable_conditions": ["缺少基本事实"]},
        }
        target = self.book_dir / dirname / f"{card_id}.md"
        target.parent.mkdir()
        target.write_text("---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False) + "---\n# " + title + "\n", encoding="utf-8")

    def test_import_preserves_card_ids_and_verifiable_origin(self):
        destination = self.root / "candidate"

        result = import_local_books([self.book_dir], destination, allow_ready=True)

        self.assertEqual(result["books"], 1)
        self.assertEqual(result["cards"], 2)
        self.assertEqual(result["relations"], 1)
        self.assertEqual(validate_library(destination)["cards"], 2)
        library = Library(destination)
        self.assertEqual(library.get_knowledge("K-BOOK-9001-C01-A")["kind"], "principle")
        evidence_id = library.get_knowledge("K-BOOK-9001-C01-A")["evidence_ids"][0]
        self.assertEqual(library.get_evidence(evidence_id)["origin"]["start"], self.source_text.index("先看清"))

    def test_ready_book_requires_explicit_candidate_override(self):
        with self.assertRaisesRegex(ValueError, "未人工验收"):
            import_local_books([self.book_dir], self.root / "candidate")

    def test_anchor_mismatch_is_rejected(self):
        path = next((self.book_dir / "01_知识卡").glob("*.md"))
        path.write_text(path.read_text(encoding="utf-8").replace("先看清事实", "不存在的原文"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "锚点"):
            import_local_books([self.book_dir], self.root / "candidate", allow_ready=True)

    def test_unsafe_or_cross_book_card_id_is_rejected(self):
        path = next((self.book_dir / "01_知识卡").glob("*.md"))
        path.write_text(path.read_text(encoding="utf-8").replace(
            "K-BOOK-9001-C01-A", "../../K-BOOK-9999-C01-A"
        ), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "卡片 ID"):
            import_local_books([self.book_dir], self.root / "candidate", allow_ready=True)

    def test_cli_builds_evaluation_candidate_without_publishing(self):
        destination = self.root / "candidate"
        output = StringIO()

        with redirect_stdout(output):
            code = cli_main([
                "import-local", "--book-dir", str(self.book_dir),
                "--destination", str(destination), "--allow-ready",
            ])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["result"]["release_status"], "evaluation_candidate")
        self.assertFalse((self.root / "CURRENT").exists())

    def test_multi_book_import_namespaces_duplicate_relation_ids(self):
        second = self.root / "BOOK-9002"
        shutil.copytree(self.book_dir, second)
        for path in second.rglob("*"):
            if path.is_file():
                path.write_text(path.read_text(encoding="utf-8").replace("BOOK-9001", "BOOK-9002"), encoding="utf-8")

        result = import_local_books([self.book_dir, second], self.root / "candidate", allow_ready=True)

        self.assertEqual(result["books"], 2)
        self.assertEqual(result["relations"], 2)

    def test_exact_duplicate_relations_in_one_book_are_deduplicated(self):
        path = self.book_dir / "06_关系" / "relations.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["edges"].append(dict(payload["edges"][0]))
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        result = import_local_books([self.book_dir], self.root / "candidate", allow_ready=True)

        self.assertEqual(result["relations"], 1)


if __name__ == "__main__":
    unittest.main()
