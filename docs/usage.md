# 本地试用

项目开发环境使用 `.venv-mvp/bin/python`。以下在程序根目录运行，分发包中的解释器改用 `.venv/bin/python`；将 data/library 换成实际用户库路径。

```bash
.venv-mvp/bin/python -m src.interfaces.cli --library data/library books
.venv-mvp/bin/python -m src.interfaces.cli --library data/library search '我接了很多零散工作，怎样不再用时间换钱？' --expand '代码媒体 复制成本 杠杆 产出与工时'
.venv-mvp/bin/python -m src.interfaces.cli --library data/library knowledge knowledge.naval-almanack.wealth-permissionless-leverage
.venv-mvp/bin/python -m src.interfaces.cli --library data/library related knowledge.naval-almanack.wealth-outputs-not-hours --hops 1
.venv-mvp/bin/python -m src.interfaces.cli --library data/library evidence evidence.paragraph.c8b057e6f398.0198
```

不需要向量或首次模型下载不可用时，加 `--mode keyword`。语义和混合查询默认启用本地模型，原书和问题文本不会提交给 Embedding API。Agent 对话本身仍由使用者选择的 AI 客户端处理。

## 让 Agent 回答

给 Agent 程序目录、实际知识库路径和可用解释器，并让它读取 `skills/second-brain/SKILL.md`。限定纳瓦尔视角时也可加载 `skills/naval-almanack/SKILL.md`。它会整理问题、检索、回读出处、检查关系和条件，再给建议。Skill 没有安装到全局目录。

示例指令：“读取项目的 second-brain Skill，使用项目内 .venv-mvp/bin/python 和 data/library。我的问题是：我每天都在接零散工作，怎样积累长期价值？请核对原文，区分书中观点与应用建议。”

## 发布与回退

`publish <候选目录>` 是切换完整知识快照，不是追加书籍。先 validate；成功后保存新版本并原子更新 CURRENT，失败保留旧版本。回退可显式 publish 已存在的旧版本目录。多书自动合并尚未实现。

升级程序应解压到新目录，继续指向原外部用户库。不要在每次升级时重新发布随包 seed-library；示例种子与用户资料不能混写。

## 当前边界

首本仅《纳瓦尔宝典》主体及作者两篇写作；跳过前置序言、书单、致谢等。无可靠页码，引用章节和证据 ID。引用汇编中的相邻片段不代表原书连续上下文。原文重新核验需要用户提供同指纹源文件。

检索可能漏掉相关卡片，也可能误配。Agent 必须复核，必要时有针对性再搜；不能用排名当正确性保证。当前没有 Web UI、常驻服务或已验收多作者讨论。
