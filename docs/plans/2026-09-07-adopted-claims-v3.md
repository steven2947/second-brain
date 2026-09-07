# 采用主张隔离 v3 Implementation Plan

> **For agentic workers:** Use subagent-driven-development for the isolated core task, followed by spec and code-quality review. Main Agent owns documentation, same-input evaluation and release. Steps use checkbox tracking.

**Goal:** 防止局部采用卡片时将整卡主张作为本次证据展示，保留原理详解、系统延伸、圆桌与续聊，不改原卡或旧答案。

**Architecture:** 新草稿/答案包为v3，旧v1/v2保留原行为。调用会话继续保留完整原卡；v3见证卡只公开显式采用内容和选定证据，并以只读引用定位原始候选。程序核验引用与结构，Agent负责原文忠实度和语义边界。

**Tech Stack:** Python、JSON Schema Draft 2020-12、现有CLI、pytest；无新依赖，无远程模型调用。

## 已确认设计与变更清单

用户已确认：先修本次采用与原卡内容的区分，同题对照通过后提交功能分支、推送并提PR，不合并main。没有删除项。原书、原卡、旧schema、旧prompt、历史运行产物、既有澄清与深入表达规则原样保留；现有工作区内上一阶段已获准提交的调用逻辑一并审阅提交。

### 六项影响检查

1. 职责：`orchestration`验证采用范围并装配；Skill负责分析；不在前端过滤来补救。
2. 事实源：固定版本会话中的原卡和原文证据。采用主张是派生判断，不回写书库。
3. 依赖：v3复用v2知识组织字段；Schema本地解析，不访问网络。无新外部服务。
4. 接口：新`schema_version:3`；旧1/2显式兼容，不能静默将旧稿自动升级为全卡采用。
5. 隔离：新契约及采用范围模块独立；知识提取、向量检索、问题轮数与原书目录不改变。
6. 回退：客户端可显式读取旧包供历史审计；新回答使用v3。新运行另存目录，历史输入哈希必须一致。

## Task A：隔离契约、装配与负面测试

Files: 新建`schemas/analysis-draft.v3.schema.json`、`schemas/answer-packet.v3.schema.json`、`src/orchestration/adoption.py`、`tests/test_adopted_claims.py`；局部修改`src/orchestration/models.py`、`src/orchestration/validation.py`、`tools/dev/materialize_effect_draft.py`。

- [x] 先保存工作区、93项来源输入及三题旧稿的指纹，跑当前基线测试。
- [x] 先写失败测试：空白采用主张、空/重复/外卡证据、引用未选证据、推论冒充作者、无采用字段旧稿冒充v3、公开整卡文字、共享证据错误关联均拒绝或不输出。
- [x] 在每个v3采用决定中要求`adoption`，拒绝决定不需要该字段。格式如下（内容是自编示例，不是作者引文）：

```json
{
  "claim": "小范围尝试可以提供下一步校正所需的反馈。",
  "source_claim_type": "system_inference",
  "evidence_ids": ["evidence.demo.1"],
  "excluded_scope": ["未采用原卡中的固定训练时长与成功保证。"]
}
```

- [x] 字符串非空白；证据至少一个且唯一，必须属于该候选，引用也只能来自选定证据。已核对知识卡Schema实际只有author_claim/quoted_other/system_inference三类，缺省归属为unclassified；v3采用归属仅允许这三类加unclassified。不能将非作者归属自动升级为作者。转换为系统推论可保守降级，改变成其他归属需先修源卡，不在调用时洗白。
- [x] v3见证卡公开字段为`adopted_claim`、`source_claim_type`、选定`evidence_ids`、`excluded_scope`及原v2中Agent填写的原理/机制/映射/判断；无整卡`claim/reasoning/conditions/boundaries`自动拷贝。`original_card_ref`由程序生成，包含session_id/library_version/card_id以便回到完整会话。
- [x] 见证卡章节和答案`sources`仅由选定证据装配，共享证据的card_ids仅关联真正选择它的卡；不删除调用会话的原证据。
- [x] v3答案见证结构严格校验，禁止把原卡字段塞回见证卡。v2各规则完整继承；旧v1/v2输出须与基线一致。
- [x] `materialize(session, spec, schema_version=2)`保持旧默认；新增显式3及CLI `--schema-version 3`，不为缺失采用判断补默认值。

验证命令：`.venv-mvp/bin/python -m pytest tests/test_adopted_claims.py tests/test_orchestration_validation.py tests/test_effect_answer_audit.py -q`。先见真实红测，再绿测，记录结果；主Agent与独立Agent分别作规格及质量复核。

## Task B：新默认调用入口与表达契约

Files: 新建`prompts/answer-orchestrator.v3.md`、`docs/adopted-claims-v3.md`、`tests/test_adoption_skill_contract.py`；局部修改`skills/second-brain/SKILL.md`及两份references、`README.md`、`docs/architecture.md`。旧v2提示词和测试保留。

- [x] Skill默认v3，读当前提示词和新schema；旧v2标明历史兼容，不能把旧包当已完成局部采用隔离。
- [x] 新prompt完整保留v2的15项表达能力，增加adoption与下游只读采用内容的职责说明；系统综合仍允许自由生成并明确归属。
- [x] 文档列原卡→采用主张→原理/映射→裁决的字段边界，强调原文ID匹配不证明语义正确、作者有值不等于完整、原卡审计引用不构成采用授权。
- [x] 新契约测试断言新版入口、字段和已认可表达要求共存；不依靠字数评分。

## Task C：同题、同会话前后对照

Files: 仅新增忽略提交的`data/jobs/adopted-claims-v3/`运行、证据与阅读稿；新建可提交的脱敏验收说明`docs/adopted-claims-verification.md`。

- [x] 冻结之前三题的问题档案、session、draft、packet、阅读稿和来源审计锁，不重新抽题或偷偷选新候选。
- [x] 当前Agent逐卡读取15张已采用卡原始证据与原理，显式写出adoption；不把旧原理自动复制成作者主张。
- [x] 用同一session和新草稿运行正式验证器；旧裁决、行动、知识组、圆桌、学习收获和末尾指令作结构相等检查。若语义纠错需要变化，必须单列，不称完全不变。
- [x] 新稿只改必要来源范围说明与账本；逐段对照旧稿，主建议与详解尽量字节相同，不以复制本身证明新生成稳定性。
- [x] 原始输入指纹均不变，负面测试证据未进入新版sources。列出保留、不采用及原理/建议是否改变；机械通过与用户效果验收分开。

## Task D：收尾提交与PR

- [x] 跑全部pytest、`git diff --check`，独立审阅代码和同题效果。
- [x] 查看暂存白名单和相对远端main的完整差异；确认无本机路径、凭据、私有原文/卡片/运行记录进入提交。保留已有用户改动，不全盘git add。
- [x] 分清本地commit/远端push/PR状态。用户已选择推送并提PR，完成后不合并main，不清理当前工作树。
- [x] 记录用时、工具可得token统计及不可得边界。Goal只有修复、验证、提交推送及PR均完成才标记complete；外部权限不足则如实报告，不冒充成功。

发布回执：代码提交`be9ee44`已推送至`codex/auditable-call-layer`，[PR #1](https://github.com/steven2947/second-brain/pull/1)为OPEN，base为main；核验时main仍为`e2e3c87`，未合并。用时与统计口径见验收说明；本记录随后以纯文档提交补齐，不改变已测代码。
