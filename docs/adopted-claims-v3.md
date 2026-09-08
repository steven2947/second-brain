# 本次采用主张与原卡隔离（v3）

## 修复什么

旧答案包的见证卡自动拷贝整卡`statement/reasoning`。即使Agent只想采用其中一个原理，消费者仍可能把其他步骤或保证当成已支持内容。v3在调用层装配时隔离，而不依赖前端隐藏一部分文字。

| 信息 | 保存位置 | 能否直接当作本次书库依据 |
| --- | --- | --- |
| 原卡完整主张、解释及所有证据 | 固定版本CallSession和书库 | 不能；这是待分析材料 |
| 本次采用主张及证据 | AnalysisDraft的adoption；AnswerPacket的adopted_claim/evidence_ids | 仅限显式采用范围，仍需语义核对 |
| 未采用部分 | excluded_scope | 不能作为正面依据 |
| 原理解释、用户映射、边界 | 原有principle/mechanism/assumptions/non_applicable_conditions等 | 须区分作者内容与系统解释 |
| 跨书推演、新选项 | system_syntheses | 作为有依据、待验证的系统综合，不署名为作者原话 |
| 原卡回查入口 | original_card_ref | 只作审计，不构成整卡采用授权 |

原书、原卡、索引、澄清轮数和旧答案文件不发生变化。旧v1/v2契约与提示词保留原行为；新版使用3，不悄悄更改旧字段语义。

## Agent如何填写

每个采用决定除原有v2字段外，还必须填写：

```json
{
  "adoption": {
    "claim": "这里写本次准确采用的主张，不把整卡自动复制进来。",
    "source_claim_type": "system_inference",
    "evidence_ids": ["替换为该候选已有的证据ID"],
    "excluded_scope": ["这里明确不采用哪些步骤、阈值或保证。"]
  }
}
```

以上只是字段说明，不是可直接运行的事实材料。claim可充分解释、不限固定字数。没有排除项时数组可为空，但不能用空数组证明整卡已合格。

证据至少一个且唯一，只能选该卡已有证据；quote必须逐字存在于所选证据中。保留原归属或保守改为system_inference，不能把转述、推论和未知归属改为作者原创。原库没有登记归属时可用unclassified，并明示缺口。书籍署名不自动等于第三方被引述观点的原创署名。

## 运行与下游读取

```bash
python -m src.interfaces.cli --library <库目录> analyze --problem <问题档案.json> --output <新会话.json>
python -m tools.dev.materialize_effect_draft --schema-version 3 --session <新会话.json> --spec <显式分析规格.json> --output <新草稿.json>
python -m src.interfaces.cli --library <库目录> validate-analysis --session <新会话.json> --draft <新草稿.json> --output <新答案包.json>
```

辅助装配脚本不作语义分析，不补采用主张或淘汰理由；直接由Agent编写符合schema的草稿也可。为旧测试保留其Python函数和CLI默认v2，当前Skill必须显式使用v3。

消费者先检查schema_version。v3读取`adopted_claim`及所选证据，不读取旧claim字段，也不从审计引用回填原卡全文。章节、来源列表和共享证据的card_ids都只反映本次选择；完整候选证据仍留在会话。未知版本应明确拒绝，不能套旧模板。

旧1/2只能按历史语义审计，或经Agent重新逐卡判断产出新v3文件；不提供“自动全卡升级”。升级程序不覆盖用户库，历史答案应与其原版本一起保留。

## 不承诺的事情

结构检查能发现证据ID越界、归属升级、缺失采用范围及不符合契约的整卡字段；不能自动证明任意自然语言都忠于原文，也不能发现所有巧妙改写的越界主张。作者字段有值不代表合著者完整。仍需按原文审阅，并对同题建议、原理解释、实际质询与续聊作效果对照。

本改动不限制AI充分讲解和生成新方案，也不额外规定卡片数、原理长度或专家数。原有三层展示、新问题最多5轮澄清（历史档案沿用原上限）和最后明确续聊指令继续有效。
