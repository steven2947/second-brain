"""验证调用层 CLI 的结构化输出、原子写入与兼容性。"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.interfaces.cli import main


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
