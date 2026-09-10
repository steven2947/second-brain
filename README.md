# 第二大脑

把书籍蒸馏为可追溯的知识，让用户的 AI Agent 运用书中观点分析真实问题。

## 当前状态

**《纳瓦尔宝典》单书 MVP 已在本地跑通。** 当前有 109 张知识卡、776 条原文证据、79 条有向关系，以及通用问答 Skill 和一位作者入口。知识来自纳入正文的完整分组阅读，不用模型记忆填充书库。

- [开始试用](docs/usage.md)：实际查询命令与 Agent 调用方式。
- [单书验收报告](docs/mvp-verification.md)：范围、检索复测、真实回答、交付验证和已知不足。
- [问答示例](docs/mvp-answer-examples.md)：基于真实检索与证据的回答。
- [可复用蒸馏流程](docs/distillation-workflow.md)：提示词、准备、复核、装配与交付。
- [产品设计](docs/product-design.md) · [架构](docs/architecture.md) · [开发指南](docs/development.md)。

## 产品组成

| 组成 | 用户价值 | 当前状态 |
| --- | --- | --- |
| 蒸馏知识库 | 观点、方法、条件、关联和来源证据 | 真实单书已入库，含来源与条件 |
| 蒸馏工具 | 用户可持续导入自己的书籍 | 仓颉 v2.5.0 与 prepare/assemble/complete/bundle 流程已跑通 |
| 查询与调用工具 | 为不同 Agent 提供稳定检索、证据与可审计答案包 | 五项查询 + analyze/validate-analysis 已实现，无需常驻服务 |
| Agent Skill | 理解问题、逐卡判断、交叉验证并形成建议 | 通用 Skill 使用验证后的调用会话与答案包；纳瓦尔作者入口继续可用 |

## 快速查询

在项目根目录运行：

```bash
.venv-mvp/bin/python -m src.interfaces.cli books
.venv-mvp/bin/python -m src.interfaces.cli search '如何减少用时间换钱' --expand '代码媒体 杠杆 可复制成果'
```

环境安装与自检见开发指南。首次向量查询会下载模型文件，文本在本地计算；可用 `--mode keyword` 运行关键词模式。

当前是 Agent 管理的单书闭环。检索复测不是回答准确率证明；自动批量模型调用、多书合并和多作者综合尚未验收。

## 目录

```text
configs/       可提交配置模板与忽略提交的本机配置
docs/          产品、架构、开发指南、实施及验收记录
src/           knowledge / distillation / retrieval / interfaces 的实现边界
skills/        供用户 Agent 加载的问答 Skill
prompts/       项目自定义的蒸馏补充规则
schemas/       知识卡片与关系的版本化数据格式
vendor/        固定版本的仓颉工作副本及锁定信息
data/          原书引用、规范化正文、书库、索引、任务记录
examples/      可独立分发的自编测试知识库
tests/         单元测试、固定检索题集与问答验收题
tools/dev/     本地盘点与基础检查
dist/          由白名单构建流程生成的本地试用包
```

运行数据与交付内容分开管理。产品升级不覆盖用户书库；原书路径和开发缓存不进入默认交付包。

## 许可证

本项目由 StevenHe（GitHub：`steven2947`）原创的源码、文档、提示词、Schema 与自编示例采用 [Apache License 2.0](LICENSE)。

允许商业使用、修改、复制和分发；再分发时请保留 `LICENSE`、`NOTICE` 及原有版权/归属声明，修改过的文件应标明修改。项目名称和标识不随本许可证授权为商标使用权。完整条款见 [`LICENSE`](LICENSE) 和 [`NOTICE`](NOTICE)。

仓库中的第三方依赖、供应商代码，以及外部原书或用户导入内容不适用本项目许可证，以各自随附的许可证或权利声明为准。

## GitHub 源码备份范围

私有源码仓库按 `.gitignore` 管理：包含源码、设计和验收文档、通用 Skill、提示词、格式、自编示例与测试。原书、真实生成书库、纳瓦尔生成入口、本机配置、虚拟环境、模型缓存及 ZIP 仍保留本地，不随普通 Git 提交上传。仓颉工作副本按 vendor/cangjie.lock.json 重新获取。

因此，全新克隆后的目录没有本机已验收书库；可先按开发指南安装依赖，使用 `--library examples/sample-library` 验证自编示例，或显式导入自己的书籍。文档中的真实单书统计是本地验收结果，不代表克隆后已包含这些数据。
