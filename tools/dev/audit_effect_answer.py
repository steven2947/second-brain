"""只读核对最终文案的显式书目和下一轮指令；不评判语义质量。"""
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path


def normalized_title(title):
    """title 为书名；只归一化空白、字符宽度及明确的版本后缀。"""
    title = unicodedata.normalize("NFKC", title)
    title = re.sub(r"\((?:原书)?第\d+版\)$", "", title)
    return re.sub(r"\s+", "", title)


def audit_answer(packet, answer):
    """packet 为已验证答案包，answer 为 Markdown；返回确定性检查及其局限。"""
    admitted = {normalized_title(w["book_title"]) for w in packet["witness_cards"]}
    mentions = {normalized_title(t) for t in re.findall(r"《([^《》\n]+)》", answer)}
    unexpected = sorted(mentions - admitted)
    missing = sorted(admitted - mentions)
    expected_last = "继续和 AI 聊：" + packet["next_chat_action"]["prompt"]
    lines = answer.rstrip().splitlines()
    final_matches = bool(lines) and lines[-1] == expected_last
    return {
        "schema_version": 1,
        "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
        "packet_sha256": hashlib.sha256(json.dumps(
            packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest(),
        "unmatched_book_mentions": unexpected,
        "unmentioned_admitted_books": missing,
        "next_chat_action_matches": final_matches,
        "mechanical_pass": not unexpected and not missing and final_matches,
        "semantic_status": "not_evaluated",
        "limitations": [
            "只识别书名号中的显式书名，不能识别未写书名的来源越界或判断主张是否被证据支持。",
            "其他书名写法或用于反例的未入席书名需人工核对，不能静默放行。",
            "不以篇幅、卡片数量、标题或 PASS 字样判断建议深度；仍需语义审阅。",
        ],
    }


def main():
    """读取 --packet 与 --answer 文件，将审计 JSON 输出到终端，不改写原文件。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True)
    parser.add_argument("--answer", required=True)
    args = parser.parse_args()
    packet = json.loads(Path(args.packet).read_text(encoding="utf-8"))
    report = audit_answer(packet, Path(args.answer).read_text(encoding="utf-8"))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["mechanical_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
