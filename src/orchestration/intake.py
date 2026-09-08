"""从可重放的问题事件生成请求；不调用模型、不读写文件、不判断消息语义。"""
import copy
import hashlib
import json
import uuid

from src.orchestration.models import validate_document


def _digest(state):
    """state 为档案字典；摘要排除 state_hash，用于发现意外改写而非身份认证。"""
    body = {key: value for key, value in state.items() if key != "state_hash"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def create_problem(question, goal="analyze"):
    """question 为完整用户问题，goal 为任务类型；创建独立问题，不用于重置旧问题。"""
    state = {"schema_version": 1, "problem_id": "problem." + uuid.uuid4().hex,
             "question": question, "goal": goal, "clarification_limit": 5, "events": []}
    state["state_hash"] = _digest(state)
    problem_snapshot(state)
    return state


def _apply(snapshot, event):
    """snapshot 为重放中的快照，event 为已校验事件；仅在内存执行状态转换。"""
    kind = event["type"]
    if kind == "ask":
        if snapshot["clarification_rounds"] >= snapshot["clarification_limit"]:
            raise ValueError(f"CLARIFICATION_LIMIT: 同一问题最多{snapshot['clarification_limit']}轮主动澄清")
        if snapshot["intake_closed"]:
            raise ValueError("INTAKE_CLOSED: 已停止主动背景澄清，可接收用户自发补充")
        if snapshot["pending_question"]:
            raise ValueError("AWAITING_USER: 上一轮问题尚未收到用户回应")
        normalized = "".join(event["question"].split())
        if normalized in snapshot["asked_questions"]:
            raise ValueError("REPEATED_QUESTION: 不重复已问的问题")
        snapshot["asked_questions"].append(normalized)
        snapshot["clarification_rounds"] += 1
        snapshot["pending_question"] = event["question"]
    elif kind == "user_update":
        snapshot.update(copy.deepcopy(event["changes"]))
        snapshot["pending_question"] = None
        # 新事实使上一版检索计划失效，不能静默沿用原计划。
        snapshot["ready"] = False
        snapshot["retrieval_focus"] = None
        snapshot["query_expansions"] = []
        if event["intent"] in ("analyze_now", "unknown"):
            snapshot["intake_closed"] = True
            snapshot["stop_reason"] = event["intent"]
    else:  # prepare：问题是否够用由 AI 判断，不由固定问卷判断。
        if snapshot["pending_question"]:
            raise ValueError("AWAITING_USER: 发出问题后须等待回应再正式分析")
        snapshot["ready"] = True
        snapshot["intake_closed"] = True
        snapshot["stop_reason"] = snapshot["stop_reason"] or (
            "round_limit" if snapshot["clarification_rounds"] == snapshot["clarification_limit"] else "sufficient"
        )
        snapshot["retrieval_focus"] = event["retrieval_focus"]
        snapshot["query_expansions"] = copy.deepcopy(event["query_expansions"])


def problem_snapshot(state):
    """state 为完整档案；验证摘要和全部转换并返回当前快照，不信任外部计数字段。"""
    validate_document("problem-state.schema.json", state)
    if state["state_hash"] != _digest(state):
        raise ValueError("INVALID_PROBLEM_STATE: 档案摘要不一致")
    snapshot = {
        "problem_id": state["problem_id"], "revision": len(state["events"]),
        "question": state["question"], "goal": state["goal"],
        "desired_outcome": "", "facts": [], "constraints": [], "assumptions": [], "unknowns": [],
        "clarification_rounds": 0, "pending_question": None, "asked_questions": [],
        # 无显式上限的历史档案保留三轮语义，不能因升级改变旧请求的停止原因。
        "clarification_limit": state.get("clarification_limit", 3),
        "intake_closed": False, "ready": False, "stop_reason": None,
        "retrieval_focus": None, "query_expansions": [],
    }
    for event in state["events"]:
        validate_document("intake-event.schema.json", event)
        _apply(snapshot, event)
    return snapshot


def append_event(state, event, expected_revision):
    """state 为旧档案，event 为 AI 整理的事件，expected_revision 防止旧窗口覆盖新进度。"""
    snapshot = problem_snapshot(state)
    if type(expected_revision) is not int or snapshot["revision"] != expected_revision:
        raise ValueError("REVISION_CONFLICT: 档案已更新，请重读后再提交")
    validate_document("intake-event.schema.json", event)
    _apply(snapshot, event)
    updated = copy.deepcopy(state)
    updated["events"].append(copy.deepcopy(event))
    updated["state_hash"] = _digest(updated)
    return updated


def compile_request(state, previous_session=None):
    """state 为已准备档案，previous_session 可选同一问题旧会话；生成独立请求，不改旧产物。"""
    snapshot = problem_snapshot(state)
    if not snapshot["ready"]:
        raise ValueError("INTAKE_NOT_READY: 请先整理信息并提交新的 prepare 检索焦点")
    context = {key: snapshot[key] for key in (
        "problem_id", "revision", "desired_outcome", "unknowns", "clarification_rounds", "stop_reason"
    )}
    context["state_hash"] = state["state_hash"]
    context["previous_session_id"] = None
    if previous_session is not None:
        from src.orchestration.session import session_id_for
        validate_document("call-session.schema.json", previous_session)
        validate_document("call-request.schema.json", previous_session["request"])
        body = {key: value for key, value in previous_session.items() if key != "session_id"}
        if session_id_for(body) != previous_session["session_id"]:
            raise ValueError("INVALID_CALL_SESSION: 上一会话摘要不一致")
        previous_context = previous_session["request"].get("context", {})
        if (previous_context.get("problem_id") != snapshot["problem_id"]
                or previous_context.get("revision", snapshot["revision"]) >= snapshot["revision"]):
            raise ValueError("PROBLEM_SESSION_MISMATCH: 只能关联同一问题更早修订的会话")
        prefix = {**state, "events": state["events"][:previous_context["revision"]]}
        if _digest(prefix) != previous_context["state_hash"]:
            raise ValueError("PROBLEM_SESSION_MISMATCH: 上一会话并非当前档案的历史修订")
        context["previous_session_id"] = previous_session["session_id"]
    # 焦点由 AI 根据最新事实/约束生成；不自动把未知或心理假设混作检索事实。
    contextual_query = "\n".join(filter(None, [
        "用户目标：" + snapshot["desired_outcome"] if snapshot["desired_outcome"] else "",
        "检索焦点：" + snapshot["retrieval_focus"],
    ]))
    request = {"schema_version": 1, **{key: copy.deepcopy(snapshot[key]) for key in (
        "question", "goal", "facts", "constraints", "assumptions"
    )}, "query_expansions": list(dict.fromkeys([contextual_query] + snapshot["query_expansions"])),
        "context": context}
    validate_document("call-request.schema.json", request)
    return request
