"""调用策略读取；证据、版本和来源纪律不是可配置选项。"""
from copy import deepcopy
import json
from pathlib import Path


DEFAULT_POLICY = {
    "schema_version": 1,
    "default_mode": "standard",
    "modes": {
        "quick": {"recall_limit": 12, "final_limit": 3, "relation_hops": 1},
        "standard": {"recall_limit": 30, "final_limit": 6, "relation_hops": 1},
        "deep": {"recall_limit": 50, "final_limit": 10, "relation_hops": 1},
    },
    "prefer_cross_book": True,
    "show_rejected_candidates": True,
    "deep_goal_types": ["compare", "review"],
    "quote_max_chars": 240,
    "evidence_context_chars": 600,
}

ROOT_KEYS = set(DEFAULT_POLICY)
MODE_KEYS = {"recall_limit", "final_limit", "relation_hops"}
MODES = {"quick", "standard", "deep"}
GOALS = {"explain", "analyze", "compare", "act", "review"}


def _invalid(message):
    raise ValueError(f"INVALID_CALL_POLICY: {message}")


def validate_policy(policy):
    """严格验证策略；未知字段及疑似硬规则覆盖均拒绝。"""
    if not isinstance(policy, dict) or set(policy) != ROOT_KEYS:
        _invalid("顶层字段缺失或包含未知字段")
    if policy.get("schema_version") != 1 or policy.get("default_mode") not in MODES:
        _invalid("版本或默认模式无效")
    modes = policy.get("modes")
    if not isinstance(modes, dict) or set(modes) != MODES:
        _invalid("必须完整定义 quick/standard/deep")
    for name, values in modes.items():
        if not isinstance(values, dict) or set(values) != MODE_KEYS:
            _invalid(f"{name} 字段无效")
        recall, final, hops = values["recall_limit"], values["final_limit"], values["relation_hops"]
        if (type(recall) is not int or type(final) is not int or type(hops) is not int
                or not 1 <= recall <= 50 or not 0 <= final <= recall or not 0 <= hops <= 3):
            _invalid(f"{name} 数量或关系深度无效")
    if type(policy["prefer_cross_book"]) is not bool or type(policy["show_rejected_candidates"]) is not bool:
        _invalid("布尔策略无效")
    goals = policy["deep_goal_types"]
    if not isinstance(goals, list) or len(goals) != len(set(goals)) or any(goal not in GOALS for goal in goals):
        _invalid("deep_goal_types 无效")
    quote = policy["quote_max_chars"]
    context = policy["evidence_context_chars"]
    if type(quote) is not int or not 1 <= quote <= 500 or type(context) is not int or not 0 <= context <= 2000:
        _invalid("引用或证据上下文长度无效")
    return policy


def load_policy(path=None):
    """读取调用策略；path 为空时返回默认策略的独立副本。"""
    if path is None:
        policy = deepcopy(DEFAULT_POLICY)
    else:
        source = Path(path)
        if not source.is_file() or source.is_symlink():
            _invalid("策略路径必须是普通文件")
        try:
            policy = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            _invalid(f"策略文件不可读：{exc}")
    return validate_policy(policy)

