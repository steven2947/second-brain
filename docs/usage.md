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

给 Agent 程序目录、实际知识库路径和可用解释器，并让它读取 `skills/second-brain/SKILL.md`。限定纳瓦尔视角时也可加载 `skills/naval-almanack/SKILL.md`。Skill 没有安装到全局目录。

正式的书库驱动回答使用两阶段调用。先准备 `call-request.json`，区分用户事实、约束、假设和检索扩展词：

```bash
.venv-mvp/bin/python -m src.interfaces.cli --library data/library analyze \
  --request call-request.json --mode standard --output call-session.json
```

Agent 阅读会话中的完整候选、证据和关系，为每个候选填写采用或淘汰决定，形成 `analysis-draft.json`。再运行：

```bash
.venv-mvp/bin/python -m src.interfaces.cli --library data/library validate-analysis \
  --session call-session.json --draft analysis-draft.json --output answer-packet.json
```

默认不覆盖已有输出；确认覆盖时显式增加 `--replace`。自定义调用策略通过两条命令相同的 `--policy <文件>` 传入。向量不可用时 `analyze` 会降级到关键词并在调用账单标记，不伪装成混合检索。

Agent 只依据验证后的答案包表达正式书库回答。答案包包含调用账单、知识见证卡、交叉验证、综合裁决、行动和来源；一般常识补充必须与书库知识分开。

示例指令：“读取项目的 second-brain Skill，使用项目内 .venv-mvp/bin/python 和 data/library。我的问题是：我每天都在接零散工作，怎样积累长期价值？请核对原文，区分书中观点与应用建议。”

## 发布与回退

`publish <候选目录>` 是切换完整知识快照，不是追加书籍。先 validate；成功后保存新版本并原子更新 CURRENT，失败保留旧版本。回退可显式 publish 已存在的旧版本目录。多书自动合并尚未实现。

升级程序应解压到新目录，继续指向原外部用户库。不要在每次升级时重新发布随包 seed-library；示例种子与用户资料不能混写。

## 当前边界

首本仅《纳瓦尔宝典》主体及作者两篇写作；跳过前置序言、书单、致谢等。无可靠页码，引用章节和证据 ID。引用汇编中的相邻片段不代表原书连续上下文。原文重新核验需要用户提供同指纹源文件。

检索可能漏掉相关卡片，也可能误配。Agent 必须逐项采用或淘汰；不能用排名当正确性保证。调用验证能检查结构、ID、版本和引用，不证明 Agent 的语义判断必然正确。当前没有 Web UI、常驻服务或已验收多作者讨论。
