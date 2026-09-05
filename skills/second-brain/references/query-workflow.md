# 问答工作流

## 问题拆解

先识别目标、事实、约束和待决定事项，区分解释、分析、比较、行动和复盘。只追问会改变结论的缺失信息。检索假设不是用户事实。

保留完整原问题，加 1 至 3 个不同角度的概念问法；不要只把同一句话重复。例：“要不要找人处理重复事务”可增加“任务外包 目标时薪 时间成本”，同时检查现金预算和任务价值。不得在看见结果后补造用户动机。

## 可审计调用 CLI

正式分析先准备调用请求：

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

Agent 逐项处理会话候选，形成符合 `schemas/analysis-draft.schema.json` 的草稿，然后运行：

```bash
python -m src.interfaces.cli --library <用户库> validate-analysis --session <会话.json> --draft <草稿.json> --output <答案包.json>
```

自定义策略必须在两条命令中传入同一个 `--policy <策略.json>`。输出已存在时默认失败；只有明确要覆盖时使用 `--replace`。正式回答遵循 [答案包规则](answer-packet-rules.md)。

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
5. 相关性门槛仍可能有误配，Agent 须检查是否真正回答问题。每个候选必须留下采用或淘汰及理由；不足可改问法一次，仍不足就明确未覆盖。

## 来源与字段

author_id 是本书主视角，source_claim_type=quoted_other 表示第三方署名，不能归为主作者原创。statement 是概括，reasoning 是整理；conditions、boundaries、steps 可能包含系统解释，结合 application_notes 判断，不能当成作者逐字程序。

`evidence --context` 返回的是离散证据汇编的相邻内容，不保证在原书相邻。原文位置见 origin（原书指纹与字符范围）；需要完整原上下文时，另核对用户已提供的同指纹原文件。没有可靠页码就引用章节与证据 ID。

## 作者视角与综合

当前单书 MVP 只验收一个作者入口。按问题相关性选择视角，作者数不足不得虚构多人讨论。未来多个作者各自输出观点、前提、证据、建议、分歧，再由通用 Skill 综合；这条多作者流程尚未完成真实验证。

可以说“按《纳瓦尔宝典》的这个框架，可以先检查……”。不要说作者本人针对用户作出了判断。编著者与主要观点人物分开注明。

## 回答与后续

正式回答先给结论预览，再展示足以理解判断来源的调用账单、知识见证卡、交叉验证、综合裁决和行动。书中主张就近注明书名、章节、知识或证据 ID；把迁移步骤写成“据此可尝试”等系统建议。引用不足、条件差异和模型缺乏信息须在相应结论旁说明。不擅自创建提醒或触发外部操作。
