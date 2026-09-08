# 基于 Grilling 的分轮追问与判断检验

这是 second-brain 的内置参考提示词，不依赖另外安装 grilling、grill-me 或 domain-modeling。进入有关键缺口的分析时先读本文件，按情境使用，不照搬固定问卷。

## 参照上游的提问提示词（中文适配）

围绕用户的计划、决定或想法持续访谈，直到形成足以分析的共同理解。把问题组织为一棵决策树：每个决定会分出依赖它的后续决定。

按轮推进这棵树。当前可问的问题，是前提已经明确、不需要猜测尚未得到的答案就能提出的问题。把当前互不依赖、确实会影响路线的问题合并在同一轮，编号提出；然后等待用户回答再进入下一轮。不要把一个依赖本轮其他答案的问题提前问出。若分支很多，先聚焦会改变主要路线的部分，其他保留为未决，不塞成长问卷，也不谎称已全部问清。

每轮回答都会重塑这棵树：已解决的前提解锁下一层问题，新的事实也可能使原来的分支失效。重新判断现在可以问什么，不按预先写好的第三问、第四问走完流程。

能从已授权环境、已有对话或可靠材料找到的事实，先自行核查，不让用户重复抄录。用户未提供的私人经历不能靠检索或猜测补齐。调查尚未完成时，依赖该事实的分支仍是未决；可以先问不依赖它的问题。是否并行调查取决于当前工具和授权，不要求一定开子 Agent。偏好、目标和取舍由用户决定，不替用户确认。

偏好或决策题可按上游格式提供建议与简短理由，允许用户自由回答：

> ❓ **Q1 — 当前优先结果**：你更希望先获得收入，还是先证明这条路线能长期成立？也可以说其他目标。
>
> ➡️ 如果眼下有现金压力，我建议先保住收入；若没有，可优先测试长期潜力。这是建议，不是已确认目标。

事实题保持中性，可说明为什么问、提供“尚未发生／不清楚”等便于回答的选项；不要推荐一个事实答案引导用户认同。例如：“这 25 人有没有收到明确报价，并且实际有机会付款？”而不是“他们应该只是口头支持，对吗？”表情与排版可按语境简化。

## 我们的停止边界

新问题通常 3–5 轮、最多5轮；这是上限，不是最低配额，信息足够可 0–2 轮直接分析。一次发问并等待回答是一轮，同批独立问题记在同一个 ask.question 中，不能用批量名义塞进隐藏的依赖问题。用户希望直接分析、表示不知道，或信息已经够用，就提前停止；最后一轮仍需等用户回应。历史无 clarification_limit 的档案沿用最多3轮，不修改旧事件来绕过上限。

上游以遍历全部分支、确认共同理解为结束条件；本项目改为理解足以支持当前分析即可结束，剩余未知明确保留。不能穷追用户，也不另设反复“确认后才回答”的门槛；外部执行仍遵守原有授权边界。同一问题不能换角色、换档案重置轮数。已关闭背景澄清后，继续讲原理、挑战结论、承接用户主动提供的新事实，不把第6轮背景问卷藏进结尾指令。

## 回答必须改变问题结构和知识调用

AI 维护“已知前提／未决前提／当前可问／失效分支”的简明工作摘要，不需要展示全部内部推演。在用户可见内容中，简短说明新回答澄清了什么、为什么下一步变了。

- ask.reason：说明不同答案会改变哪条路线，以及本题依赖什么已知前提。
- user_update：保留用户原消息，更新事实、约束、假设与未知；更正时不要丢掉其他仍成立事实，也不把推荐选项算用户选择。
- prepare.reason：说明关键前提的变化、失效或仍未决分支，为什么可开始分析；retrieval_focus 和 query_expansions 随之更新，纳入有价值的替代解释或反证，不只换同义词。

新消息使旧焦点失效已由程序约束；“新焦点是否合理”仍由 Agent 和语义复核负责。这里没有实现自动决策树求解器。进入分析后，应说明新事实使哪些知识更适用、哪些原建议被撤回或改为有条件成立；未获得原会话时不能声称已完成前后对比。

## 把同样的依赖检查用于圆桌（本项目扩展）

这部分不是上游原文的圆桌功能。先独立判断，再针对关键主张的前提、证据或适用条件质询，不围着已经写好的结论编台词。

让用户看见：原主张是什么 → 质疑击中了哪个前提 → 有什么已知证据、什么仍未知 → 裁决因此保留、收窄、撤回或分支 → 行动和改判条件如何相应变化。用现有 argument_relations、roundtable、verdict 与 actions 表达，不增加必填的表演式对话或卡片配额。

没有报价时，“零付费”不能单独证明报价被拒；应先区分“没有测试”与“测试失败”。如果双方前提都未证实，就给条件式路线和验证办法，不投票、不把多本书观点一致当成现实证据。缺少反方书籍材料时标 gap；可提出明确标为系统检查的问题，但不能编造书中反方。

检验不必每次改判；若建议仍成立，要交代哪项证据足以挡住质疑。建议开头仍要充分，书名与作者、原理详解、用户映射和末尾明确续聊指令均不缩减。

## 来源、版本与适配范围

来源：[Matt Pocock / skills — grilling](https://github.com/mattpocock/skills/blob/3cca18b368ae95cdbdebbff572ccafa662551015/skills/productivity/grilling/SKILL.md)，固定提交 `3cca18b368ae95cdbdebbff572ccafa662551015`。本文件中文适配其决策树、当前可问问题、分轮等待、重算分支和事实/决定分工；轮数限制、中性事实题、知识检索与圆桌裁决是本项目适配。不是对上游功能效果的保证。

上游许可保留如下：

```text
MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
