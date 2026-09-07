"""调用层 JSON 契约验证；领域对象不依赖命令行。"""
from pathlib import Path
import json

from jsonschema import Draft202012Validator


SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas"
ERROR_PREFIXES = {
    "intake-event.schema.json": "INVALID_INTAKE_EVENT",
    "problem-state.schema.json": "INVALID_PROBLEM_STATE",
    "call-request.schema.json": "INVALID_CALL_REQUEST",
    "call-session.schema.json": "INVALID_CALL_SESSION",
    "analysis-draft.schema.json": "INVALID_ANALYSIS_DRAFT",
    "answer-packet.schema.json": "INVALID_ANSWER_PACKET",
    "analysis-draft.v2.schema.json": "INVALID_ANALYSIS_DRAFT",
    "answer-packet.v2.schema.json": "INVALID_ANSWER_PACKET",
    "analysis-draft.v3.schema.json": "INVALID_ANALYSIS_DRAFT",
    "answer-packet.v3.schema.json": "INVALID_ANSWER_PACKET",
}


def validate_document(schema_name, document):
    """按项目内严格 Schema 验证 document，失败返回稳定错误前缀。"""
    if schema_name not in ERROR_PREFIXES:
        raise ValueError("INVALID_SCHEMA: 未知调用层 Schema")
    schema = json.loads((SCHEMA_ROOT / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(document), key=lambda item: list(item.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        raise ValueError(f"{ERROR_PREFIXES[schema_name]}: {location}: {error.message}")
    return document
