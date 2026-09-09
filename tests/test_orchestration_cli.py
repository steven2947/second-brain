"""验证调用层 CLI 的结构化输出、原子写入与兼容性。"""
import contextlib
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.interfaces.cli import main
from src.knowledge.library import Library


ROOT = Path(__file__).parents[1]
LIBRARY = ROOT / "examples/sample-library"


def run_cli(arguments):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, json.loads(stdout.getvalue()) if stdout.getvalue() else None, stderr.getvalue()


def request_document():
    return {
        "schema_version": 1,
        "question": "如何处理模糊任务并检查进展？",
        "goal": "act",
        "facts": ["任务尚未拆分"],
        "constraints": ["今天开始"],
        "assumptions": [],
        "query_expansions": ["模糊任务 小步骤", "检查 不确定性"],
    }


def draft_for(session):
    decisions = [{
        "card_id": candidate["card_id"],
        "decision": "admit",
        "reason_code": "relevant",
        "reason": "直接回答如何开始或复核。",
        "roles": ["support", "boundary"],
        "principle": "将模糊内容变成可观察动作并用反馈调整。",
        "principle_gap": False,
        "situation_mapping": "用户的任务尚未拆分。",
        "judgment_effect": "支持立即执行一个可检查步骤。",
    } for candidate in session["candidates"]]
    identifiers = [item["card_id"] for item in decisions]
    return {
        "schema_version": 1,
        "session_id": session["session_id"],
        "library_version": session["library_version"],
        "decisions": decisions,
        "cross_validation": {
            "agreements": [{"summary": "先行动再复核。", "card_ids": identifiers}],
            "conflicts": [],
            "limitations": [{"summary": "不能替代目标判断。", "card_ids": identifiers[:1]}],
            "alternatives": [],
            "evidence_gaps": [],
        },
        "verdict": {
            "conclusion": "先完成一个可检查步骤，再复核不确定性。",
            "basis_card_ids": identifiers,
            "decisive_user_facts": ["任务尚未拆分"],
            "uncertainties": [],
        },
        "actions": [{
            "step": "列出三个待处理文件。",
            "basis_card_ids": identifiers[:1],
            "completion_criteria": "出现三个文件名。",
            "validation_signal": "下一步变得明确。",
            "stop_condition": "若仍不明确则返回目标定义。",
        }],
    }


def rewrite_second_candidate(candidate):
    """将复制的 sample candidate 改写为独立的第二本书；candidate 为临时候选目录。"""
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


class OrchestrationCliTests(unittest.TestCase):
    """新命令必须安全写文件，并保持原有查询接口。"""

    def test_analyze_and_validate_analysis_write_structured_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path, session_path = root / "request.json", root / "session.json"
            draft_path, packet_path = root / "draft.json", root / "packet.json"
            request_path.write_text(json.dumps(request_document()), encoding="utf-8")
            status, result, stderr = run_cli([
                "--library", str(LIBRARY), "analyze", "--request", str(request_path),
                "--mode", "standard", "--retrieval-mode", "keyword", "--output", str(session_path),
            ])
            self.assertEqual((status, stderr), (0, ""))
            self.assertEqual(result["result"]["path"], str(session_path.resolve()))
            session = json.loads(session_path.read_text(encoding="utf-8"))
            self.assertEqual(result["result"]["session_id"], session["session_id"])

            draft_path.write_text(json.dumps(draft_for(session), ensure_ascii=False), encoding="utf-8")
            status, result, stderr = run_cli([
                "--library", str(LIBRARY), "validate-analysis", "--session", str(session_path),
                "--draft", str(draft_path), "--output", str(packet_path),
            ])
            self.assertEqual((status, stderr), (0, ""))
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            self.assertEqual(result["result"]["session_id"], packet["session_id"])
            self.assertTrue(packet["witness_cards"])

    def test_output_requires_replace_and_invalid_request_is_nonzero(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path, output = root / "request.json", root / "session.json"
            request_path.write_text(json.dumps(request_document()), encoding="utf-8")
            arguments = ["--library", str(LIBRARY), "analyze", "--request", str(request_path),
                         "--retrieval-mode", "keyword", "--output", str(output)]
            self.assertEqual(run_cli(arguments)[0], 0)
            status, _, stderr = run_cli(arguments)
            self.assertEqual(status, 2)
            self.assertIn("OUTPUT_EXISTS", stderr)
            self.assertEqual(run_cli(arguments + ["--replace"])[0], 0)

            request_path.write_text(json.dumps({**request_document(), "question": ""}), encoding="utf-8")
            status, _, stderr = run_cli(arguments + ["--replace"])
            self.assertEqual(status, 2)
            self.assertIn("INVALID_CALL_REQUEST", stderr)

    def test_existing_books_command_keeps_wrapper_contract(self):
        status, result, stderr = run_cli(["--library", str(LIBRARY), "books"])
        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(result["schema_version"], 1)
        self.assertIn("library_version", result)
        self.assertEqual(result["result"][0]["id"], "book.demo")

    def test_merge_candidates_returns_wrapped_result_and_readable_library(self):
        """合并命令按候选顺序生成可由 Library 读取的候选库。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second, destination = (root / name for name in ("first", "second", "merged"))
            shutil.copytree(LIBRARY, first)
            shutil.copytree(LIBRARY, second)
            rewrite_second_candidate(second)

            status, result, stderr = run_cli([
                "merge-candidates",
                "--candidate", str(first),
                "--candidate", str(second),
                "--destination", str(destination),
                "--library-id", "library.cli-test",
            ])

            self.assertEqual((status, stderr), (0, ""))
            self.assertEqual(result["schema_version"], 1)
            self.assertIsNone(result["library_version"])
            self.assertEqual(result["result"]["path"], str(destination.resolve()))
            self.assertEqual(len(Library(destination).list_books()), 2)

    def test_merge_candidates_reports_duplicate_candidate_as_json_error(self):
        """重复候选导致 JSON 错误并返回退出码 2。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate, destination = root / "candidate", root / "merged"
            shutil.copytree(LIBRARY, candidate)

            status, result, stderr = run_cli([
                "merge-candidates",
                "--candidate", str(candidate),
                "--candidate", str(candidate),
                "--destination", str(destination),
                "--library-id", "library.cli-duplicate-test",
            ])

            self.assertEqual(status, 2)
            self.assertIsNone(result)
            self.assertIn("DUPLICATE", stderr)

    def test_analyze_passes_explicit_index_and_model_cache_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path, output = root / "request.json", root / "session.json"
            index_root = root / "shared-indexes"
            request_path.write_text(json.dumps(request_document()), encoding="utf-8")
            session = {
                "session_id": "call.cache-test",
                "status": "ready_for_analysis",
                "candidates": [],
            }
            with patch("src.orchestration.session.create_call_session", return_value=session) as create:
                status, _, stderr = run_cli([
                    "--library", str(LIBRARY), "--index-root", str(index_root),
                    "analyze", "--request", str(request_path), "--retrieval-mode", "hybrid",
                    "--output", str(output),
                ])

            self.assertEqual((status, stderr), (0, ""))
            self.assertEqual(create.call_args.kwargs["index_root"], index_root)
            self.assertEqual(create.call_args.kwargs["model_cache"], index_root / "model-cache")


if __name__ == "__main__":
    unittest.main()
