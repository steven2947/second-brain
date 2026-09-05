# 项目基础阶段验收

日期：2026-09-05，20:28–20:31（Asia/Shanghai）。状态：基础阶段通过；真实单书 MVP 尚未运行。

## 已完成

- 独立项目目录、产品文档、架构六项检查、模块职责与单书实施路线。
- 本地 Git 仓库，分支 `codex/bootstrap`；尚未创建提交。
- 仓颉标签 `v2.5.0`，实际提交 `44692125abcdb93eab7b0e7a5ecd6ccadf92dc6f`，工作副本无修改。
- 隔离 `.venv`，实际 Python 为 3.9.6；依赖版本记录于 `requirements-dev.lock.txt`。
- 本机配置和原书导航链接；现有文件保留在 MyAiStudio，未迁移、复制或修改。
- 168 本 Markdown 来源盘点，合计 113,432,619 字节；逐本 SHA-256 记录于忽略提交的 `data/jobs/source-inventory.json`。
- 三份 JSON Schema、两张自编知识卡片、两条定位证据、一条带依据类型的关系。
- 三阶段蒸馏补充提示词与项目内知识问答 Skill；未安装到任何全局 Agent 目录。

## 实际执行结果

| 检查 | 结果 | 证明范围 |
| --- | --- | --- |
| `python3 tools/dev/inventory_books.py --summary` | 168 本，113,432,619 字节 | 原书可读，非蒸馏状态 |
| `.venv/bin/python vendor/cangjie/scripts/cangjie.py doctor` | PASS，无缺失依赖警告 | 仓颉基础环境就绪 |
| `.venv/bin/python tools/dev/project_check.py --schemas` | PASS | 配置、固定提交、示例格式与证据一致 |
| Skill Creator `quick_validate.py` | Skill is valid | frontmatter 与文件基本格式 |
| `python3 -m compileall -q tools/dev` | 退出码 0 | 自有工具语法通过 |
| 在 `/tmp` 调用项目检查脚本 | PASS | 不依赖启动时工作目录 |
| 临时副本修改证据原文 | 正确拒绝：来源指纹改变 | 不接受漂移证据 |
| 临时副本设置悬空关系 | 正确拒绝：关系端点悬空 | 关系引用检查有效 |
| 临时副本设置错误卡片类型 | 正确拒绝：JSON Schema 失败 | 格式门禁有效 |
| `git check-ignore` 私有配置、原书链接、盘点、依赖与环境 | 均被忽略 | 防止默认纳入源码 |
| `.venv/bin/python -m pip check` | No broken requirements found | 已安装依赖关系一致 |
| 自有 Markdown 本地链接检查 | 20 个链接，无缺失 | 项目文档导航有效 |

负例检查只使用系统临时目录中的副本，完成后自动清理；原始自编示例随后重新通过验证。

## 未完成范围

尚未执行真实书籍的正文规范化、全书蒸馏、语义验收或入库；尚未实现混合检索服务、可查询图谱、自动批量调度、多作者问答或用户安装包。仓颉 doctor 和示例格式通过不证明这些产品能力已完成。

下一阶段入口：[单书 MVP 计划](plans/2026-09-05-single-book-mvp.md)。
