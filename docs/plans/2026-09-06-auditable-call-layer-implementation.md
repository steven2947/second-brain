# Second Brain 可审计知识调用层实施计划

日期：2026-09-06  
依据：[可审计知识调用层设计](../superpowers/specs/2026-09-06-auditable-knowledge-call-layer-design.md)  
范围：只实现调用层、CLI 与通用 Skill 接入；不做前端，不修改蒸馏主流程，不实现多书合并。

## 实施纪律

- 使用测试驱动的补丁式修改；每一阶段先加入失败测试，再实现最小能力。
- 保留现有 `books/search/knowledge/evidence/related` 等接口和返回格式。
- 所有测试默认使用 `examples/sample-library` 或新建的自编夹具，不读取私有原书。
- 调用会话和答案包是派生产物，不回写已发布知识库。
- 每阶段形成独立提交，失败时可以按提交回退。
- 运行完整回归时区分产品缺陷与缺失可选依赖；不得把环境缺包写成通过。

## 阶段 1：数据契约与策略

### 变更

- 新增 `schemas/call-request.schema.json`。
- 新增 `schemas/call-session.schema.json`。
- 新增 `schemas/analysis-draft.schema.json`。
- 新增 `schemas/answer-packet.schema.json`。
- 新增 `configs/call-policy.example.json`。
- 新增 `src/orchestration/__init__.py`、`models.py`、`policy.py`。
- 新增 `tests/test_orchestration_models.py`。

### 先写的失败测试

1. 空问题、未知模式、超过上限的扩展问法必须失败。
2. `facts` 与 `assumptions` 类型错误必须失败。
3. 策略不能关闭证据、版本和来源硬规则。
4. `quick/standard/deep` 的召回与采用上限必须有效。
5. 未知策略字段必须失败，避免拼写错误被静默忽略。

### 实现要求

- 统一用 JSON Schema 2020-12 验证外部输入。
- 领域对象不依赖 argparse；文件读取和 CLI 参数解析留在接口层。
- 受控枚举集中定义：调用模式、角色、采用状态、淘汰理由、错误码。
- `call-policy.example.json` 只控制召回数量、展示和升级策略，不能削弱硬规则。

### 验证命令

```bash
python -m unittest discover -s tests -p 'test_orchestration_models.py' -v
```

### 建议提交

```text
feat: define auditable call contracts and policy
```

## 阶段 2：调用会话与宽召回

### 变更

- 新增 `src/orchestration/session.py`。
- 新增 `tests/test_orchestration_session.py`。
- 必要时为 `SearchEngine.search` 增加不破坏现有调用方的内部参数或辅助函数。

### 先写的失败测试

1. 会话必须固定 `library_version`，并生成稳定 `session_id`。
2. 原问题和扩展问法必须分别保留在调用账单中。
3. 候选必须去重，并记录各检索通道、排名与匹配信息。
4. 每个候选必须带完整卡片、书籍、证据摘要和一跳关系，而非只带标题。
5. 无匹配时返回明确的 `NO_RELEVANT_KNOWLEDGE` 状态，不制造候选。
6. 关键词降级必须在会话中记录 `retrieval_degraded` 及原因。
7. 相同书库版本、相同请求和策略产生内容一致的会话主体。

### 实现要求

- 调用现有 `SearchEngine`，不复制 BM25、向量或 RRF 实现。
- 宽召回数量取决于策略模式；最终采用数量不在本阶段决定。
- 调用 `Library.get_knowledge/get_evidence/get_related` 装配完整上下文。
- 自动关系展开最多一跳；深度调整由策略限制在现有 `Library` 允许范围内。
- 所有候选初始状态为 `pending`，不得由相似度自动判定为采用。
- 保存书目搜索范围，区分“全库检索”和“只检索了过滤后的书目”。

### 验证命令

```bash
python -m unittest discover -s tests -p 'test_orchestration_session.py' -v
python -m unittest discover -s tests -p 'test_retrieval.py' -v
python -m unittest discover -s tests -p 'test_library.py' -v
```

### 建议提交

```text
feat: build version-pinned knowledge call sessions
```

## 阶段 3：分析草稿验证与答案包

### 变更

- 新增 `src/orchestration/validation.py`。
- 新增 `tests/test_orchestration_validation.py`。
- 新增 `tests/call-golden/` 的最小自编请求、会话、草稿与答案包夹具。

### 先写的失败测试

1. 候选没有全部被 `admit/reject` 处理时必须失败。
2. 采用不存在的卡片、证据或关系 ID 必须失败。
3. 会话与当前书库版本不一致必须失败。
4. 短引不能在对应证据中逐字定位时必须失败。
5. `author_claim/quoted_other/system_inference` 混淆必须失败。
6. 采用项缺少原理、条件、边界或情境映射时必须失败；原卡本身缺原理时允许显式 `principle_gap`。
7. 中心结论和行动没有 `basis_card_ids` 必须失败。
8. 行动缺少完成标准、验证信号或停止条件必须失败。
9. `deep` 模式存在挑战/限制候选却完全忽略时必须失败。
10. 没有真实反方时，声明证据缺口应通过，虚构反方 ID 必须失败。

### 实现要求

- 验证器只接受会话候选集合中的 ID。
- 淘汰理由使用受控理由码，并允许一段简短的人类可读说明。
- 生成知识见证卡，组合卡片事实字段与 Agent 提交的本次情境映射；两者明确分区。
- 交叉验证区分同书近义支持、独立章节支持、跨书支持和冲突，不把数量转成置信度百分比。
- `AnswerPacket` 保留所有关键不确定性和证据缺口。
- 生成过程为确定性纯函数；同输入得到字节等价或语义等价输出。

### 验证命令

```bash
python -m unittest discover -s tests -p 'test_orchestration_validation.py' -v
```

### 建议提交

```text
feat: validate analysis drafts and build answer packets
```

## 阶段 4：CLI 接入

### 变更

- 补丁修改 `src/interfaces/cli.py`。
- 新增 `tests/test_orchestration_cli.py`。
- 补丁修改 `docs/usage.md`、`docs/architecture.md`、`tests/README.md`。

### CLI 契约

```bash
python -m src.interfaces.cli --library <用户库> analyze \
  --request <call-request.json> \
  --mode standard \
  --policy <call-policy.json> \
  --output <call-session.json>

python -m src.interfaces.cli --library <用户库> validate-analysis \
  --session <call-session.json> \
  --draft <analysis-draft.json> \
  --output <answer-packet.json>
```

### 先写的失败测试

1. 两条命令成功时 stdout 返回包含路径、会话 ID 和知识版本的 JSON。
2. 输出采用临时文件加原子替换，不留下半文件。
3. 已存在输出默认不静默覆盖；需显式 `--replace`，并且只允许具体文件目标。
4. 无效请求、旧会话和无效草稿返回非零状态及稳定错误码。
5. 新命令不得改变原有五项查询命令的输出。

### 实现要求

- CLI 只负责读写和参数解析，不承载领域判断。
- 输入路径必须为普通文件；拒绝目录、符号链接和不安全输出目标。
- 异常沿用当前 JSON 错误风格，并增加稳定的调用层错误前缀。

### 验证命令

```bash
python -m unittest discover -s tests -p 'test_orchestration_cli.py' -v
python -m unittest discover -s tests -v
```

### 建议提交

```text
feat: expose auditable analysis workflow through cli
```

## 阶段 5：Second Brain Skill 接入

### 变更

- 补丁修改 `skills/second-brain/SKILL.md`。
- 补丁修改 `skills/second-brain/references/query-workflow.md`。
- 新增 `skills/second-brain/references/answer-packet-rules.md`。
- 新增或更新 Skill 静态检查测试。

### 行为规则

1. Skill 先建立 `CallRequest`，明确区分用户事实和检索假设。
2. 调用 `analyze` 获取候选，而非自行猜测书目和卡片。
3. 阅读候选完整字段及证据后，为每项提交采用或淘汰决定。
4. 调用 `validate-analysis`；未通过时修复草稿，不绕过验证器直接宣称来自书库。
5. 只从验证后的 `AnswerPacket` 生成书库驱动回答。
6. 默认表达顺序为：结论预览、调用账单、知识见证卡、交叉验证、综合裁决、行动、来源。
7. `quick` 可压缩调用账单，但用户追问时必须能展开完整记录。
8. 一般常识建议可以补充，但必须与书库证据区隔。

### 验证

- 使用自编示例库完整演练 quick、standard、deep 三种模式。
- 检查 Skill 中每条命令与 CLI `--help` 一致。
- 检查没有要求 Agent 输出隐藏思维链、虚构作者发言或固定凑卡。

### 建议提交

```text
feat: route second brain answers through validated call packets
```

## 阶段 6：真实单书金标准与回归

### 前置条件

- 明确本机真实知识库路径，确认其 `CURRENT` 版本和《纳瓦尔宝典》卡片可读。
- 使用用户此前认为“回答效果一般”的同一个问题；若日志中能可靠恢复原问题，则直接复用，不重新改写题目。

### 对照产物

- `tests/call-golden/naval/<case-id>/request.json`：问题与已知背景；
- `session.json`：真实检索会话；
- `analysis-draft.json`：逐卡采用/淘汰和角色判断；
- `answer-packet.json`：验证后的答案包；
- `answer.md`：新版可读答案；
- `comparison.md`：旧版与新版逐项对照。

真实书库内容默认不提交公共仓库；若上述文件包含私有证据，保存到 gitignored 的本地验收目录，只提交去原文的指标与结论。

### 验收维度

| 维度 | 通过标准 |
| --- | --- |
| 调用透明度 | 展示搜索范围、采用和淘汰卡片及理由 |
| 知识解释 | 每张采用卡说明原理、条件、边界和情境映射 |
| 交叉验证 | 展示真实支持、冲突、限制、替代或明确缺口 |
| 可追溯性 | 中心结论和行动都能定位到卡片与证据 |
| 行动质量 | 有完成标准、验证信号和停止条件 |
| 阅读体验 | 不靠堆卡制造复杂感，用户能理解答案如何产生 |
| 来源纪律 | 不误署第三方观点，不把系统迁移写成原话 |

### 完整回归

```bash
python -m unittest discover -s tests -v
python tools/dev/project_check.py --schemas
python -m src.interfaces.cli --library examples/sample-library books
python -m src.interfaces.cli --library examples/sample-library search '如何处理模糊任务' --mode keyword
```

向量测试需在锁定依赖环境运行。若公开克隆缺少 `vendor/cangjie/scripts`，先按 `vendor/cangjie.lock.json` 恢复固定版本，再执行交付测试；不得通过删除测试或跳过文件来制造全绿。

### 建议提交

```text
test: verify knowledge call quality against golden questions
```

## 最终交付

完成后提供：

1. 新增和修改文件清单；
2. 每阶段提交号；
3. 完整测试结果及未通过原因；
4. 同一问题旧版与新版回答对照；
5. 调用耗时、可观测 Token 和费用；不可观测项明确记为 `unknown`；
6. 已知边界和下一阶段建议。

不把“测试通过”表述为“答案必然正确”；结构、来源和回归测试与用户主观效果验收分别报告。
