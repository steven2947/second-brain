# 配置

复制 `local.example.json` 为 `local.json` 后填写本机路径。`local.json` 不提交、不分发，不含 API 密钥。

`source_books_root` 是原书目录，只读使用。其他路径相对项目根目录解析。部署后的用户数据目录须由安装配置指定，不能把开发者路径写进 Skill。

`pilot_book_title` 是默认建议书籍，不代表该书已蒸馏。当前 `model_execution=agent_managed` 仅表示计划由 Agent 执行蒸馏提示词；没有实现自动模型调度。
