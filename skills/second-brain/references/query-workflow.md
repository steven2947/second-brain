# 问答工作流

## 问题拆解

先识别目标、事实、约束和待决定事项，区分解释、分析、比较、行动和复盘。只追问会改变结论的缺失信息。检索假设不是用户事实。

保留完整原问题，并先区分表面问题、真正目标、关键冲突、隐藏假设和最值得消除的不确定性。原问题已经准确时不要强行重构。根据本题生成少量真正不同的概念问法，最多六个；可从原理、反证、反例、跨域类比或干预方式中自由选择有价值的角度，不要求全部出现，也不要只把同一句话重复。例：“要不要找人处理重复事务”可增加“任务外包 目标时薪 时间成本”，同时检查现金预算和任务价值。不得在看见结果后补造用户动机。

## 自适应澄清：最多3轮，问题自由生成

先读已有对话和材料，信息足够就直接分析。若关键缺口会改变路线，先用自然语言回应已经理解的内容，再问当前最值得知道的事。优先询问具体经历或容易描述的事实，也可给便于回答的例子；不要让用户先填完整问卷。每轮的问题随新回答生成，可追踪意外线索、修正原理解，不固定先问背景、再问目标、最后问资源。

同一问题的AI主动澄清最多3轮，是上限而非任务数。一次向用户发出澄清请求并等待回应算一轮；通常聚焦一件关键事，紧密相关且容易回答的信息可以一起问，不能把长问卷塞进一轮。Agent在对话上下文中保留已问轮数及已知事实，用户主动补充不增加轮数；重构问题、更换知识席位或给过一段初步分析不重置同一问题的计数。

任一轮信息已足够、用户表示不知道或希望直接分析时，停止为补齐资料而追问。到第3轮后给出基于现有事实的充分建议、原理和条件裁决；缺失部分可以保留未知或给分支方案，不保证诊断成立，也不把第4轮背景追问藏在结尾指令里。短澄清轮不需要完整知识展示，但正式回答仍遵守先给足建议、再讲透知识与交叉质询的要求。

上限不限制用户主动深入学习、反驳结论、报告执行结果或提出新问题。新事实出现时指出哪些判断改变、为何改变，必要时重新建立检索会话；不要把每次“继续”都变成重填背景。后续方向由当前内容自然产生，保留AI的推演和提问空间。

### 接入持久化问题档案

有 CLI 时，多轮分析默认使用下列入口。首次创建后，在该问题的所有窗口和后续对话中沿用同一档案路径；先 `intake-show` 重读，再按返回的 `revision` 更新。问题够清楚可0轮直接准备，不为了使用工具强行追问。

```bash
python -m src.interfaces.cli intake-start --question '用户完整原问题' --goal act --output <问题档案.json>
python -m src.interfaces.cli intake-show --state <问题档案.json>
python -m src.interfaces.cli intake-update --state <问题档案.json> --event <事件.json> --expected-revision <刚读到的revision>
python -m src.interfaces.cli --library <用户库> analyze --problem <问题档案.json> --output <本轮新会话.json>
```

事件格式由 `schemas/intake-event.schema.json` 定义，只有三种；**不是让用户填 JSON**，由 Agent 读自然对话后整理：

- `ask`：`question` 是当前自由生成的问题，`reason` 说明该缺口会改变什么判断。先成功记录再向用户展示；记录成功算一轮，随后等待回应。中断恢复先检查 pending_question，不能重复计数或偷偷再发一轮。
- `user_update`：保存 `source_message` 用户原消息、`reason` 变更原因、`intent` 和 `changes`。intent 可为 answer/supplement/analyze_now/unknown；用户希望直接分析或说不知道时须准确标记。changes 只列变动字段：desired_outcome、facts、constraints、assumptions、unknowns；**数组是该字段的新完整值**，不是追加项。未列出的字段保留；更正错误事实时保留其他仍成立事实，旧值和原消息仍在事件日志。初次从已有对话提取信息也用此事件，不重复询问。
- `prepare`：`retrieval_focus` 是基于最新目标/事实/约束的检索重点，`query_expansions` 为最多5条额外概念角度，`reason` 解释为何此时可以分析。不把未确认假设变成用户事实；假设需要检验时明确标为条件或反证角度。程序把真实目标和焦点作为一个扩展查询自动送入检索，合计不超过6条。未知目标留空并做条件分析。

程序从事件计算0–3轮，不接受外部提供计数；未等用户回应不能 prepare。用户停止澄清或首次 prepare 后，同一档案不再开启主动背景补问；仍可接收用户自发学习/反馈。新 user_update 使旧检索焦点失效，须重新 prepare，轮数保留。只问原理、没有新情境时可以继续解释当前答案包，不必做无意义的更新和检索。

每个档案更新有版本冲突检查与本地文件锁；冲突时重读合并，不能用覆盖方式丢掉另一窗口消息。完整例子见项目文档 `docs/adaptive-intake.md`。

新增事实改变判断时，生成新会话并显式关联旧会话：

```bash
python -m src.interfaces.cli --library <用户库> analyze --problem <问题档案.json> --previous-session <上一会话.json> --output <下一轮新会话.json>
```

新入口不允许 `--replace` 覆盖会话。请求与答案包的 `context` 保留问题ID、修订号、真实目标、未知、轮数、停止原因和上一会话ID。旧 `analyze --request` 仍兼容，但它不提供档案计数硬约束；不要用它绕过新问题的澄清上限。无 CLI 时只能由 Agent 在对话中计数，须如实说明未获得程序约束。

## 可审计调用 CLI

单轮兼容入口可直接准备调用请求（多轮默认使用上述问题档案）：

```json
{
  "schema_version": 1,
  "question": "用户完整原问题",
  "goal": "act",
  "facts": ["用户明确说过的事实"],
  "constraints": ["时间、预算或风险限制"],
  "assumptions": ["继续分析所需但尚未确认的假设"],
  "query_expansions": ["补充概念角度一", "补充概念角度二"]
}
```

`goal` 为 `explain/analyze/compare/act/review`。再运行：

```bash
python -m src.interfaces.cli --library <用户库> analyze --request <请求.json> --mode standard --output <会话.json>
```

`quick` 用于简单查询，`standard` 为默认现实问题，`deep` 用于复杂决策和跨观点审查。`analyze` 固定知识版本、召回候选、读取证据并补读关系，但不会自动把高排名卡片判为适用。

Agent 逐项处理会话候选，默认形成符合 `schemas/analysis-draft.v3.schema.json` 的草稿，然后运行：

```bash
python -m src.interfaces.cli --library <用户库> validate-analysis --session <会话.json> --draft <草稿.json> --output <答案包.json>
```

自定义策略必须在两条命令中传入同一个 `--policy <策略.json>`。输出已存在时默认失败；只有明确要覆盖时使用 `--replace`。正式回答遵循 [答案包规则](answer-packet-rules.md)。

v1 草稿仅为历史兼容保留。v2 要求每张入席卡绑定 `user_context_refs`，并显式生成问题重构、知识组、`argument_relations`、系统综合、`roundtable`、带改判条件的 `verdict`、`learning_takeaways` 和继续路径。完整生成要求见项目根目录 `prompts/answer-orchestrator.v2.md`。

v2格式 `schemas/analysis-draft.v2.schema.json` 与原提示词继续保留供历史兼容。当前新调用使用v3，完整继承上述知识推演功能，并为采用项显式填入 `adoption.claim/source_claim_type/evidence_ids/excluded_scope`。证据只能选当前候选已有的支持材料，短引也只能来自所选证据；不能把系统推论或转述升级为作者原创。原卡只有部分主张获支持时，明确选出这部分，不要靠一条边界备注掩盖整卡入席。详见 `prompts/answer-orchestrator.v3.md`。

正式表达读取v3见证卡的 `adopted_claim`，原卡通过程序生成的 `original_card_ref` 回到固定会话审计，不再自动拷贝其整段主张/推理/条件/边界。章节与来源账本仅列本次选定证据。旧v1/v2不是可静默回退的安全替代；遇到旧包只能明确按历史语义审计，或重新逐卡判断生成新v3文件，不能自动全卡升级。辅助装配脚本使用 `--schema-version 3` 时也必须提供完整adoption，缺失即报错。

## 底层查询 CLI

先切换到产品程序根目录；下列 `python` 指实际已安装依赖的解释器，`<用户库>` 指用户确认的库目录。路径和文本分别作为参数传入，别拼接执行不可信命令。

```bash
python -m src.interfaces.cli --library <用户库> books
python -m src.interfaces.cli --library <用户库> search '用户完整问题' --mode hybrid --expand '补充概念问法' --limit 5
python -m src.interfaces.cli --library <用户库> knowledge <知识ID>
python -m src.interfaces.cli --library <用户库> evidence <证据ID>
python -m src.interfaces.cli --library <用户库> related <知识ID> --hops 1 --direction both
```

search 可加 `--book`、`--author` 过滤。关键词为中文双字 BM25，本地向量为中文 BGE，混合用 RRF 融合并要求至少一个问法达到相似度门槛。分数仅用于排序，不是来源准确率、观点可信度或用户匹配概率。

底层命令用于调试、补读和兼容旧调用。正式调用会话已经装配候选的完整卡片、证据与关系；不得重复搜索后只挑对既有结论有利的材料。

1. 读清单并检查实际作者覆盖。固定同一返回版本完成本次分析；过程中版本改变则重新建立调用会话。
2. 检索后读完整卡片的条件、边界和 application_notes，不能只看前几名标题。
3. 读取每个拟引用的 evidence；证据文件和映射由 CLI 校验。带引号内容必须逐字一致。
4. 用 related 补读前提、限制或对照观点；relation.basis=inference 表示系统关系。只展开一跳，确有必要才加深。
5. 相关性门槛仍可能有误配，Agent 须检查是否真正回答问题。每个候选必须留下采用或淘汰及理由；理由说明该卡的具体条件、证据或相对贡献，不自动套用通用理由补齐记录。不足可改问法一次，仍不足就明确未覆盖。

## 来源与字段

author_id 是本书主视角，source_claim_type=quoted_other 表示第三方署名，不能归为主作者原创。statement 是概括，reasoning 是整理；conditions、boundaries、steps 可能包含系统解释，结合 application_notes 判断，不能当成作者逐字程序。

`evidence --context` 返回的是离散证据汇编的相邻内容，不保证在原书相邻。原文位置见 origin（原书指纹与字符范围）；需要完整原上下文时，另核对用户已提供的同指纹原文件。没有可靠页码就引用章节与证据 ID。

## 作者视角与综合

当前单书 MVP 只验收一个作者入口。按问题相关性选择视角，作者数不足不得虚构多人讨论。未来多个作者各自输出观点、前提、证据、建议、分歧，再由通用 Skill 综合；这条多作者流程尚未完成真实验证。

可以说“按《纳瓦尔宝典》的这个框架，可以先检查……”。不要说作者本人针对用户作出了判断。编著者与主要观点人物分开注明。

## 回答与后续

最终回答的开头先给足建议，包含做法、取舍和关键条件，用户不必读完书籍详解才知道如何行动。成稿后按答案包复核引用书目；再用同题前后对照审阅建议、知识连接和质询是否真正改善。不用字数或角色数代替效果判断。研发汇报与产品回答不同，不把产品的结尾聊天指令机械套进项目进度汇报。

本地研发的最终Markdown落盘后，运行只读书目核对：

```bash
python -m tools.dev.audit_effect_answer --packet <答案包.json> --answer <最终答案.md>
```

该工具仅检查显式书名与末尾指令；别名可能需要人工核对，未写书名的越界或建议深度不在检测范围。工具不可用时按同样范围手工核对并记录，不能声称已自动检查。生成分析规格的辅助脚本要求显式的admitted_decisions和rejected_decisions，不能自动为未选卡补理由。

正式回答采用三层渐进展示：先给可独立执行的结论、关键依据和行动；再按本题需要组织知识组，以“《书名》｜作者｜知识名称”展示知识见证卡、清楚但不僵化的原理解释、知识关系及用户映射；最后按“独立立场—交叉质询—主持裁决”展开知识议事过程，并给出改判条件、可复用方法、继续路径和来源账本。书中主张就近注明书名与作者；完整章节、知识或证据 ID 放入来源账本。系统可以自由提出跨书综合、新假设或新选项，但须与作者主张分开并说明如何验证。引用不足、条件差异和模型缺乏信息须在相应结论旁说明。全文最后一行给出本轮推荐的明确聊天指令：“继续和 AI 聊：……”。不擅自创建提醒或触发外部操作。
