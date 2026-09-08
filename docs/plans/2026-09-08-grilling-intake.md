# Grilling 提问与质询适配

用户批准：通常 3–5 轮、最多 5 轮；直接参照上游提问提示词，保留自由生成和提前结束。

## 修改前六项检查

1. 职责：Skill 判断问题依赖与提问价值；intake 只管轮数、等待、关闭与事件重放；调用提示词负责知识取舍和质询裁决。
2. 事实源：用户原消息和已提供材料为情境依据；书籍证据仍经 v3 采用隔离。不改蒸馏卡片、原书和历史答案。
3. 依赖：参照 Matt Pocock 的 grilling 固定提交，新增本地参考提示词并保留 MIT 许可；不安装全局 Skill，不强制引入子 Agent 或其他依赖。
4. 接口：问题档案增加可选 clarification_limit，新建值为 5；无该字段的旧档案仍按 3 重放。请求允许最多 5 轮；ask/user_update/prepare 接口不变。
5. 隔离：仅补丁修改当前 Skill、v3 提示词、intake、两份 schema、活动说明和测试；v2 历史提示词、金标准历史产物、前端不改。决策树是 AI 维护的分析结构，不宣称程序已实现依赖图求解器。
6. 迁移回退：不批量迁移旧档案，不删字段重置计数；旧调用请求保持兼容。回退应用版本前须先识别新五轮档案，旧程序不能读取它们；保留文件，用新版只读查看或继续处理，禁止通过删事件伪装兼容。

## 验证安排

- 新档案第 4/5 轮可用、第 6 轮失败，任一轮可提前停；独立问题同批等待一次计一轮。
- 旧档案三轮上限、停止原因与历史请求保持不变；不重置用户补充后的计数。
- 用户更正事实后必须重建焦点，重跑既有同题真实检索测试（自编样本库），不能把保存了新背景等同于检索已改变。
- 原有 15 项生成职责逐项保留；新增提示词契约只证明入口未掉线，不证明自然语言效果。
- 增加自编问题分支演示，明确不是实际模型 A/B 或真实书籍效果验收。

## 验证结果

2026-09-08 本地执行，未提交或推送。

| 检查 | 实际结果与边界 |
| --- | --- |
| 定向 unittest：tests.test_intake + tests.test_adoption_skill_contract | 20 项通过，1.906s；含五轮等待、提前停止、补充后计数、旧档案、检索差异、v1/v2答案包与原15项生成规则 |
| unittest discover -s tests -p 'test_*.py' | 98 项通过，5.134s；包含上面20项，不相加为118项 |
| 对照 Git HEAD ac95ab1 的 intake 实现 | 在内存加载修改前代码，对同一旧档案分别重放0/1/2/3轮；新旧 compile_request 完全相同，快照除新增只读 clarification_limit 外完全相同 |
| 同题检索回归 | 自编样本原首项 knowledge.demo.small-step；补充执行事实并修改焦点后首项 knowledge.demo.review，旧会话不变；不是实际用户书库准确率 |
| git diff --check | 通过 |
| project_check.py --schemas | 示例证据及schema通过；基础环境整体未通过：缺少 configs/local.json，vendor/cangjie 没有独立Git仓库，rev-parse回溯到了主项目，导致与仓颉锁提交不符 |

环境检查脚本、路径模块和仓颉锁文件与 HEAD 无差异，本次未修环境配置或依赖。不以98项工程测试替代真实书库调用、模型A/B或用户效果验收。全套测试中有 ONNX 遥测设备ID保存警告，测试仍成功结束。

## 实际改动对照

```diff
- 新建问题档案无显式上限；ask 和 prepare 固定比较3
+ 新建档案 clarification_limit=5；按档案上限检查，无字段旧档案默认3
- call-request.context.clarification_rounds.maximum = 3
+ call-request.context.clarification_rounds.maximum = 5
- 活动入口：最多3轮，自主生成问题
+ 活动入口：通常3–5轮、最多5轮，可提前结束；按前提依赖分轮，回答后重算分支
+ 内置 grilling-intake.md：固定上游版本、中文适配与完整MIT许可
+ v3调用器：质疑指向前提，并同步裁决、行动与改判条件
```

修改13个既有文件：README.md、docs/adaptive-intake.md、docs/adopted-claims-v3.md、docs/architecture.md、prompts/answer-orchestrator.v3.md、schemas/call-request.schema.json、schemas/problem-state.schema.json、skills/second-brain/SKILL.md、skills/second-brain/references/answer-packet-rules.md、skills/second-brain/references/query-workflow.md、src/orchestration/intake.py、tests/test_adoption_skill_contract.py、tests/test_intake.py。

新增3个文件：本记录、[自编分支演示](../grilling-intake-example.md)、[内置参考提示词](../../skills/second-brain/references/grilling-intake.md)。没有删除文件。原书、蒸馏卡片、前端、v2历史提示词、历史金标准和用户全局Skill均未修改。
