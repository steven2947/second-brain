# 产品实现

当前建立模块职责，业务实现由 [单书 MVP 计划](../docs/plans/2026-09-05-single-book-mvp.md) 驱动。没有实现的接口不得在 Skill 中伪装为可调用工具。

- `knowledge/`：知识与证据领域规则。
- `distillation/`：正文加工、仓颉适配、任务状态。
- `retrieval/`：检索、关系展开、原文回读。
- `interfaces/`：共享领域能力的 CLI / Agent 工具入口。
