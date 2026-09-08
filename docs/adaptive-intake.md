# 自适应澄清怎样接入知识分析

状态：本地实现；本次功能分支发布同时包含v3采用隔离，具体提交与推送结果见PR。程序提供问题档案、新问题最多5轮状态约束和检索编译；AI 仍负责理解用户、自由生成问题、知识取舍和最终答案。并非自动模型聊天服务。

[本地验收与实际变更对照](adaptive-intake-verification.md)：自动测试与真实效果验收分开记录。

2026-09-08 更新：[Grilling 适配与验证计划](plans/2026-09-08-grilling-intake.md)。新问题通常3–5轮、最多5轮，不足3轮也可提前结束；历史无 clarification_limit 的档案仍保留三轮上限和原停止原因，不批量修改历史档案。上面旧验收报告对应更新前版本，不作为本次五轮效果证据。当前分轮提示词见 [Grilling 参考](../skills/second-brain/references/grilling-intake.md)，提问分支由 AI 判断，程序未实现自动决策树求解。

## 职责与信息流

自然对话 → Agent 整理事件 → 同一问题档案 → 目标与检索重点 → analyze 候选会话 → Agent 独立判断与交叉验证 → validate-analysis 答案包 → 充分建议、知识解释和继续聊。

| 信息 | 如何影响后续 |
| --- | --- |
| 原问题 | 保留全文，是基本检索查询，不因重构而覆盖 |
| desired_outcome | 与检索焦点共同进入查询；答案包保留真实目标，避免把“行动”当具体目标 |
| facts / constraints | Agent 据此生成焦点；仍进入原有 user_context_refs，供知识与用户情境绑定 |
| assumptions / unknowns | 分开保存；不得伪装成用户确认事实，分析给出边界和分支 |
| clarification_rounds | 从事件日志计算，新问题最多5轮；不是让 AI 自报轮数 |
| revision / previous_session_id | 追踪前后变化；新事实建立新会话，不改旧答案 |

## Agent 操作示例（自编场景，非用户真实情况）

以下命令在项目根目录运行，python 指已安装项目依赖的解释器。输出父目录先创建在本地 data/jobs 中，不提交用户对话。各轮保存独立事件 JSON，避免覆盖操作历史。

```bash
python -m src.interfaces.cli intake-start --question '三个副业方向怎么选？' --goal act --output data/jobs/problem.json
```

创建后 revision=0。如果需要问：

```json
{"type":"ask","question":"你目前最希望先得到什么结果？","reason":"收入、技能积累和探索分别对应不同取舍。"}
```

把事件存为本地 ask-1.json，通过以下命令记录成功后向用户展示该问题：

```bash
python -m src.interfaces.cli intake-update --state data/jobs/problem.json --event data/jobs/ask-1.json --expected-revision 0
```

用户回答“这个月希望先有收入，每天只有一小时”。Agent 整理 answer-1.json：

```json
{
  "type": "user_update",
  "source_message": "这个月希望先有收入，每天只有一小时。",
  "intent": "answer",
  "changes": {"desired_outcome": "本月获得第一笔收入", "constraints": ["每天一小时"]},
  "reason": "明确目标和时间限制，尚未得到现有客户或需求事实。"
}
```

用 expected-revision 1 更新。此后是否继续问、问什么由 AI 判断，不固定第二轮主题。新问题最多5轮；可以1轮或2轮后提前结束。用户说“不知道”或“直接分析”则将 intent 标成 unknown 或 analyze_now，立即停止主动背景追问。纯自发补充为 supplement，不消耗轮数。

准备分析的 prepare.json 示例：

```json
{
  "type": "prepare",
  "retrieval_focus": "短期收入目标下的付费需求验证与服务交付；缺少客户事实，比较有现成需求和没有需求两种情形",
  "query_expansions": ["服务范围 交付边界 时间成本", "付费意愿 免费反馈 反例"],
  "reason": "先按已知目标给出条件分支，不假设用户已有客户。"
}
```

先读当前修订，再提交：

```bash
python -m src.interfaces.cli intake-show --state data/jobs/problem.json
python -m src.interfaces.cli intake-update --state data/jobs/problem.json --event data/jobs/prepare.json --expected-revision 2
python -m src.interfaces.cli --library <实际用户库> analyze --problem data/jobs/problem.json --output data/jobs/session-1.json
```

上例无额外事件时 revision=2；若问过第二轮必须使用实际返回的 revision，不能照抄数字。新会话中的查询实际包含目标与焦点，而不是只保存到旁边的备注。后续按当前工作流生成 v3 草稿并 validate-analysis，显式填写adoption，保留作者/书名、原理、情境映射、交叉质询、裁决和有深度的行动方案。旧v2仅为历史兼容，详见[采用隔离说明](adopted-claims-v3.md)。

## 用户继续聊

- 只是问“再讲讲这个原理”：继续解释现有证据，必要时补读，不重填背景。
- 提供新事实或纠正事实：提交 user_update，changes 为相关字段的完整新值；旧消息和旧值保留在事件中，其他字段不变。准备新的检索焦点，再用 analyze --problem ... --previous-session data/jobs/session-1.json --output data/jobs/session-2.json。
- 同一问题不另开档案、不重置轮数；第一轮正式分析后不重开背景问卷。解释、学习和用户自发深入不受主动澄清轮数限制。
- 新回答说明新事实如何改变或不改变原建议；不能为了显示“更新”硬改结论，也不能只改建议而不解释知识依据。

## 已知边界

1. CLI 没有模型调用：不自动识别意图、不判断问题质量，也不保证 AI 写入 facts 的内容忠实于 source_message；Agent 和效果审阅负责这层语义。
2. 日志摘要用于发现意外修改，不是签名或防恶意篡改。程序约束同一路径档案的规范操作，不能阻止外部 Agent 绕开入口或新建档案；本地锁适用于 macOS/Linux POSIX 环境。
3. facts/constraints 通过 Agent 的 retrieval_focus 影响检索，不自动把所有背景原文拼成长查询。补充后必须重新 prepare，但焦点是否真正反映新事实仍须语义验收。
4. 原 --request 路径与旧会话保持兼容，不拥有持久化轮数约束。每次 --problem 输出新文件；上一会话必须属于同一档案的更早历史修订。
5. 本次不修改蒸馏数据、不自动上传、不安装全局 Skill。机械通过不等于真实书库答案已通过用户效果验收。
