# 知识格式 v1

此版本为单书 MVP 的初始文件契约。卡片、证据和关系分别验证；跨文件引用、来源范围和文本一致性需要额外检查。JSON Schema 通过不证明原文支持观点。

- `knowledge-card.schema.json`：观点、方法、条件、边界、书籍/作者和证据 ID。
- `evidence.schema.json`：原文片段、来源位置、正文指纹。`start`/`end` 是 Python Unicode 字符串的零基字符偏移，`end` 不包含在片段内。
- `relations.schema.json`：关系方向与依据。节点 ID 使用卡片 ID；`source` 表示原文明确支持的关联，`inference` 表示系统推断。

示例使用 `examples/sample-library/`。来源位置按书库根目录解析，不能越出根目录；真实本地原书的额外位置由私有配置映射，不写进分发用卡片。
