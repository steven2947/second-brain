# Second Brain 可审计知识调用层设计

日期：2026-09-06  
状态：已完成方案讨论，待用户复核书面设计后进入实施计划  
基准仓库：`steven2947/second-brain`，提交 `a4720bb3546b6f1e9fe0375d0e405b3b088aebc2`

## 1. 目标

在现有 Second Brain 的书库、检索、证据和关系能力之上，增加一个可审计的知识调用层。它不只返回答案，还要让用户看见：系统检索了哪些知识、为何采用或淘汰、知识的原理与适用边界、不同观点如何相互支持或限制，以及行动建议如何由这些依据产生。

本阶段不做前端，不重写蒸馏流程，不把模型私密思维链作为产品内容。系统输出的是由用户事实、卡片字段、证据、关系和明确判断规则构成的可验证推演记录。

## 2. 设计原则

1. **Second Brain 是运行内核。** 复用现有 `Library`、`SearchEngine`、证据校验、关系展开和版本固定能力。
2. **程序保证流程，Agent 负责语义判断。** 检索、证据装配、版本固定和结构校验由程序完成；相关性、情境映射和综合裁决由 Agent 完成并显式留下判断依据。
3. **回答必须可追溯。** 每项核心判断都要连接知识卡和证据；系统迁移不得冒充作者原话。
4. **允许证据不足。** 没有反方、跨书证据或足够知识时明确记录，不为满足格式而虚构角色。
5. **按复杂度展开。** 简单问题不强制完整圆桌，复杂决策才启用多角色交叉验证。
6. **调用层不修改知识事实源。** 调用会话和答案包是派生产物，不回写卡片、证据或原书。

## 3. 为什么不能只修改 Skill

当前 `skills/second-brain/SKILL.md`、`query-workflow.md` 和 `source-rules.md` 已有正确方向，但属于 Agent 可选择遵循的软规则。仅修改提示词仍可能出现：直接给结论、只读搜索摘要、不检查边界、不展示淘汰项、遗漏反方或把系统建议写成作者观点。

因此采用“双阶段调用 + 结构验证”：程序先生成固定知识版本下的检索会话，Agent 再提交采用/淘汰与分析结果，程序验证后生成正式答案包。

## 4. 总体架构

```text
用户问题与背景
      ↓
问题请求 CallRequest
      ↓
调用启动器：固定书库版本、执行多路召回、补读关系与证据
      ↓
检索会话 CallSession
      ↓
Agent：逐卡判断相关性、条件、边界、角色和情境映射
      ↓
分析草稿 AnalysisDraft
      ↓
调用验证器：核对 ID、证据、引用、角色、来源类别和覆盖规则
      ↓
正式答案包 AnswerPacket
      ↓
Second Brain Skill：将答案包表达为用户可读答案
```

新增 `src/orchestration/`，依赖 `knowledge` 与 `retrieval`；`interfaces` 调用它。现有模块不反向依赖调用层。

## 5. 两阶段调用协议

### 5.1 `analyze`：建立检索会话

建议命令：

```bash
python -m src.interfaces.cli --library <用户库> analyze \
  --request <call-request.json> \
  --mode standard \
  --output <call-session.json>
```

`CallRequest` 至少包含：

- `question`：用户完整原问题；
- `goal`：用户要解释、判断、比较、行动还是复盘；
- `facts`：用户明确提供的事实；
- `constraints`：预算、时间、风险偏好等限制；
- `assumptions`：继续分析所需、但尚未确认的假设；
- `query_expansions`：1 至 3 个不同概念角度，不得伪装成用户事实；
- 可选书籍、作者和领域过滤器。

程序固定当前书库版本，执行宽召回，读取完整卡片，补读一跳关系，装配所有相关证据，并生成候选调用账单。此阶段不生成最终结论。

### 5.2 `validate-analysis`：验证分析并生成答案包

建议命令：

```bash
python -m src.interfaces.cli --library <用户库> validate-analysis \
  --session <call-session.json> \
  --draft <analysis-draft.json> \
  --output <answer-packet.json>
```

Agent 必须为每张候选卡给出 `admit` 或 `reject`，并使用受控理由码。采用项还要填写问题映射、分析角色和本次判断；淘汰项保留简短理由。验证器核对会话和书库版本、卡片与证据 ID、短引逐字一致性、来源类别、角色约束及行动依据。

正式答案只能依据验证通过的 `AnswerPacket` 表达。验证失败时输出明确错误，不静默降级成普通聊天答案。

## 6. 三种调用深度

| 模式 | 使用场景 | 候选召回 | 最终知识 | 分析要求 |
| --- | --- | ---: | ---: | --- |
| `quick` | 查概念、找观点、低风险小问题 | 最多 12 | 1–3 | 原理、边界、来源 |
| `standard` | 默认现实问题 | 最多 30 | 3–6 | 支持、限制或反例、行动 |
| `deep` | 复杂决策、高风险、跨领域问题 | 最多 50 | 5–10 | 多视角、反方、替代路线、证据审计、裁决 |

数量是上限，不是凑数目标。没有合格卡片时允许为零；没有真实反方时记录“当前书库未检索到足够反方证据”。

## 7. 候选筛选规则

候选卡不能只按相似度进入答案，必须依次通过：

1. **相关性闸门**：它是否真正回答当前问题，而非仅关键词相同；
2. **证据闸门**：卡片是否具有当前版本下可定位的证据；
3. **条件闸门**：用户事实是否满足方法或观点的适用条件；
4. **边界闸门**：是否命中不适用情况、反例或限制；
5. **区分度闸门**：是否与已采用卡片重复，是否提供新增判断价值；
6. **来源闸门**：作者主张、第三方引语与系统推断是否正确区分；
7. **组合价值闸门**：它在本次分析中承担什么独立角色。

建议的淘汰理由码包括：`irrelevant`、`condition_mismatch`、`boundary_hit`、`duplicate`、`weak_evidence`、`source_ambiguous`、`lower_explanatory_value`、`outside_user_goal`。

## 8. 知识见证卡

每个采用项在 `AnswerPacket` 中生成一张知识见证卡：

- `card_id`、书名、作者、章节；
- **知识主张**：卡片表达了什么；
- **原理解释**：为什么成立、通过什么机制起作用；
- **适用条件**与**不适用边界**；
- **情境映射**：用户的哪项事实与它对应；
- **本次作用**：它改变了哪一项判断；
- **分析角色**：支持、挑战、限制、替代、证据审计或行动转化；
- `evidence_ids` 与必要的短引；
- `source_claim_type`：作者主张、第三方引语或系统推断。

如果原卡没有足够的 `reasoning` 支撑原理解释，见证卡必须标记 `principle_gap`，不能由 Agent 凭常识补成作者理论。该缺口进入后续蒸馏质量反馈，不阻塞其他书继续蒸馏。

## 9. 交叉验证与分析角色

角色不等同于虚构作者人格。它们是知识在本次问题中的功能：

- `support`：支持主要方向；
- `challenge`：质疑核心假设或提出相反判断；
- `boundary`：指出适用条件和风险；
- `alternative`：提供另一条可行路径；
- `evidence_auditor`：检查来源、归属与证据强度；
- `action_translator`：把原理转化为最小行动。

交叉验证规则：

- 同一本书中的两张近义卡不能伪装成两个独立来源；
- 跨书一致只能说明观点相互支持，不能自动证明为事实；
- 冲突观点要比较各自前提，不能用票数裁决；
- 中心结论优先寻找独立卡片、不同章节或不同作者的支持；
- 找不到独立验证时保留为单一来源判断并降低表达强度；
- `deep` 模式若候选池存在挑战或限制卡，必须纳入至少一张；不存在则显式报告缺口。

## 10. AnswerPacket 输出契约

第一版建议包含：

```json
{
  "schema_version": 1,
  "session_id": "...",
  "library_version": "...",
  "mode": "standard",
  "problem": {
    "question": "...",
    "goal": "...",
    "facts": [],
    "constraints": [],
    "assumptions": []
  },
  "call_ledger": {
    "books_searched": [],
    "queries": [],
    "candidates": [],
    "admitted": [],
    "rejected": []
  },
  "witness_cards": [],
  "cross_validation": {
    "agreements": [],
    "conflicts": [],
    "limitations": [],
    "alternatives": [],
    "evidence_gaps": []
  },
  "verdict": {
    "conclusion": "...",
    "basis_card_ids": [],
    "decisive_user_facts": [],
    "uncertainties": []
  },
  "actions": [],
  "sources": []
}
```

`actions` 中每一步必须有 `basis_card_ids`、完成标准、验证信号和停止条件。面向用户的自然语言答案可以重新组织表达，但不得删除关键不确定性或把系统推断改写成原话。

## 11. 规则如何落地

### 程序硬规则

以下规则写入 Python 和 JSON Schema，不能由配置关闭：

- 固定单次调用的知识库版本；
- 所有采用卡片必须真实存在且证据可读；
- 引号内容必须与证据逐字一致；
- 作者主张、第三方引语、系统推断分开；
- 每个中心结论和行动必须声明依据卡片；
- 每个候选必须留下采用或淘汰状态；
- 书库不足时不得制造作者、卡片、证据或反方。

### 可配置策略

新增 `configs/call-policy.example.json`，可调整：

- 默认调用模式；
- 各模式召回和采用上限；
- 关系展开深度；
- 是否优先跨书多样性；
- 是否在最终答案展示淘汰项；
- 何种问题升级为 `deep`；
- 可接受的引用长度和证据上下文长度。

配置只影响策略，不得削弱来源与证据硬规则。

### Skill 表达规则

更新通用 Skill：先调用新命令，读取验证后的答案包，再按“结论预览—调用账单—知识见证卡—交叉验证—综合裁决—行动—来源”表达。`quick` 可以压缩展示，但仍保留可追溯依据。

## 12. 错误与降级

- `LIBRARY_NOT_READY`：没有可用书库，不生成伪答案包；
- `SOURCE_VERSION_MISMATCH`：调用期间版本变化，重新建立会话；
- `NO_RELEVANT_KNOWLEDGE`：换一个检索角度一次，仍为空则明确未覆盖；
- `INSUFFICIENT_EVIDENCE`：允许保留一般建议，但与书库知识分开；
- `INVALID_ANALYSIS_DRAFT`：指出缺失字段、错误 ID 或未处理候选；
- 向量不可用：可以降级到关键词，但在调用账单中记录 `retrieval_degraded`；
- 没有反方或跨书验证：记录缺口，不阻断 `quick/standard`，不伪造完整圆桌。

## 13. 文件变更范围

实施阶段计划新增：

- `src/orchestration/models.py`：调用请求、会话、草稿和答案包的数据模型；
- `src/orchestration/session.py`：固定版本、宽召回、关系和证据装配；
- `src/orchestration/validation.py`：分析草稿与来源验证；
- `src/orchestration/policy.py`：读取并校验调用策略；
- `schemas/call-request.schema.json`；
- `schemas/analysis-draft.schema.json`；
- `schemas/answer-packet.schema.json`；
- `configs/call-policy.example.json`；
- `tests/test_orchestration.py`；
- `tests/call-golden/`：固定问题、请求、草稿和预期答案包。

实施阶段计划补丁式修改：

- `src/interfaces/cli.py`：增加 `analyze` 与 `validate-analysis`；
- `skills/second-brain/SKILL.md`：改为使用答案包；
- `skills/second-brain/references/query-workflow.md`：补充两阶段协议；
- `docs/usage.md`、`docs/architecture.md`：补充调用方式与边界；
- `tests/README.md`：增加调用层验收说明。

不删除现有命令，不修改原书和已发布书库，不实现前端，不在本阶段建设模型 API 调度或多书发布合并器。

## 14. 测试与验收

### 结构测试

- 每个候选都有采用或淘汰决定；
- 采用项的卡片、证据和关系 ID 全部有效；
- 书库版本变化时拒绝验证旧会话；
- 引用不一致、错误作者归属和虚构 ID 必须失败；
- 行动没有知识依据或停止条件时必须失败；
- `deep` 模式存在挑战候选却未处理时必须失败。

### 行为测试

至少覆盖：

- 简单概念查询；
- 现实行动问题；
- 条件不满足的方法；
- 关键词相似但语义无关的卡片；
- 作者引用第三方观点；
- 同一本书内部冲突；
- 多书支持与跨书冲突；
- 当前书库完全未覆盖；
- 向量不可用时的显式降级。

### 金标准对照

选用之前暴露问题的同一个真实问题，保存旧版回答与新版答案包。新版验收必须证明：

1. 用户能看到具体调用书目和卡片；
2. 每张采用卡都解释原理、条件和情境映射；
3. 有真实的支持、限制、反方或缺口说明；
4. 结论和行动能追溯到卡片与证据；
5. 不再只给结果，也不靠堆砌卡片制造复杂感。

## 15. 暂不纳入

- 网页、卡片动画、知识图谱界面；
- 自动调用外部大模型 API；
- 多书候选库合并与发布；
- 修改现有全书蒸馏主流程；
- 自动把所有方法生成独立 Skill；
- 保存或展示模型私密思维链。

这些能力可以在调用层通过金标准验收后分别设计，不能阻塞本阶段。

## 16. 完成定义

只有同时满足以下条件，才算调用层第一版完成：

- `analyze` 能从真实书库生成固定版本的检索会话；
- `validate-analysis` 能拒绝无来源或结构不完整的分析；
- 通用 Second Brain Skill 使用验证后的答案包回答；
- 同一真实问题的新回答完整展示调用账单、知识原理、情境映射、交叉验证、裁决、行动与来源；
- 现有查询、证据、发布和蒸馏测试没有回归；
- 前端缺失不影响通过 CLI 和 Agent 阅读完整调用过程。
