# 任务 3 实施报告：暴露 `merge-candidates` CLI

## 文件

- `src/interfaces/cli.py`：新增 `merge-candidates` 子命令、重复 `--candidate` 参数及领域层分发。
- `tests/test_orchestration_cli.py`：新增成功合并、输出包装、Library 可读性和重复候选错误测试；保持既有 `books` 断言语义不变。
- `src/interfaces/README.md`：记录命令只合并已验证候选，不读取或发布原书。

## TDD 红绿

1. 红：先加入两个 CLI 测试，运行 `.venv-mvp/bin/python -m unittest tests.test_orchestration_cli -v`；新增测试因 parser 不认识 `merge-candidates` 失败，既有测试通过。
2. 绿：加入最小 argparse 配置和 `merge_libraries` 分发后，同一聚焦命令结果为 6/6 通过。
3. 帮助回归：`.venv-mvp/bin/python -m src.interfaces.cli --help` 已列出 `merge-candidates`。

## 验证命令与结果

- `.venv-mvp/bin/python -m unittest tests.test_orchestration_cli -v`：6 项通过。
- `.venv-mvp/bin/python -m src.interfaces.cli --help`：成功，命令出现在子命令列表。
- `.venv-mvp/bin/python -m unittest discover -v`：未发现测试；项目文档指定的 discover 参数不在该命令中。
- `.venv-mvp/bin/python -m unittest discover -s tests -p 'test_*.py' -v`：117 项通过，4 项按条件跳过。
- `git diff --check`：通过。

## 契约核对

- 成功输出沿用 `schema_version=1`、`library_version=null`、`result` 包装。
- 错误由现有异常处理输出 JSON 到 stderr，并返回 2；重复候选包含 `DUPLICATE`。
- `--candidate` 使用 `action='append'`，保留输入顺序；`--destination`、`--library-id` 和候选均必填。
- `--release-status` 仅允许 `evaluation_candidate` 或 `accepted_candidate`。
- CLI 不复制领域逻辑，直接复用 `src.distillation.merge.merge_libraries`；不使用或读取 `args.library`。

## 风险与边界

- 测试使用复制的自编 sample candidate，并将第二份改写为独立测试书；这只验证 CLI 接线和结构可读性，不代表真实十本书语义验收。
- argparse 自身的缺参/非法 choice 错误仍遵循现有命令行解析行为；领域执行错误遵循项目 JSON stderr/退出码 2 契约。
- 本任务未发布候选库，未修改 `data/originals`、`vendor/cangjie`、外部书库或真实 `data/library`。
