# 开发与数据指南

## 已有书籍

本机书库路径保存在忽略提交的 `configs/local.json`。`data/originals/books-md` 为便利导航的符号链接；原始文件仍位于 MyAiStudio，不发生迁移或复制。符号链接本身不提供操作系统写保护，所有项目工具按只读方式访问。

盘点脚本只认“目录名与 Markdown 文件名一致”的书籍布局；它不会把质检报告和 README 算成书。其他布局将来由显式导入清单支持。

```bash
python3 tools/dev/inventory_books.py --summary
python3 tools/dev/inventory_books.py
python3 tools/dev/project_check.py --json
```

完整盘点输出到标准输出，包含相对路径、字节数与 SHA-256；可选择重定向到 `data/jobs/`，脚本不会自行写文件。存在不可读文件时返回非零退出码，不悄悄跳过。

## 仓颉版本

锁定信息见 `vendor/cangjie.lock.json`。新机器在项目根目录执行：

```bash
git clone --depth 1 --branch v2.5.0 https://github.com/kangarooking/cangjie-skill.git vendor/cangjie
git -C vendor/cangjie rev-parse HEAD
```

结果应等于锁文件中的 commit。若不一致停止接入，不自动切换到 main 或覆盖本地修改。

## 隔离环境

```bash
python3.12 -m venv .venv-mvp
.venv-mvp/bin/python -m pip install -r requirements-mvp.lock.txt
.venv-mvp/bin/python vendor/cangjie/scripts/cangjie.py doctor
.venv-mvp/bin/python tools/dev/project_check.py --schemas
```

依赖锁文件对应本轮验证环境，不代表所有平台均经过测试。基础盘点与项目检查不依赖此虚拟环境；完整 JSON Schema 验证需要 jsonschema，仓颉需要 PyYAML，token 静态计数需要 tiktoken。

## Skill 使用

Skill 源码位于 `skills/second-brain/`，当前没有全局安装。可以让 Agent 阅读该 SKILL.md 并明确提供书库路径。本地 CLI 已接通；完整方式见 usage.md，纳瓦尔视角还可读取 skills/naval-almanack/SKILL.md。

用 `examples/sample-library/` 做开发演示时，回答必须标明“自编测试材料”。不要让 Agent 把这份示例当成《纳瓦尔宝典》的蒸馏结果。

## 检查范围

```bash
.venv-mvp/bin/python -m compileall -q src tools/dev
.venv-mvp/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv-mvp/bin/python tools/dev/project_check.py --schemas
```

这些命令检查工程结构、锁定提交、示例格式和原文定位，不证明蒸馏语义或回答质量。真实问答按 `tests/acceptance-questions.md` 验收。

## 蒸馏与评估

可复用步骤见 distillation-workflow.md。检索评估：

```bash
.venv-mvp/bin/python tools/dev/evaluate_retrieval.py --out data/jobs/naval/retrieval-rerun.json
```

固定题集不得边改标签边报分。初始复测结果见 mvp-verification.md。开发环境为 macOS arm64 + Python 3.12；原 .venv 保留作为基础仓颉环境，不互相覆盖。
