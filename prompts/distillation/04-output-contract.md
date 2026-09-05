# Agent 输出契约 v1

读取 prepare 输出的 document.json 和 units/，逐节完整阅读并保留段落 ID。分组并行仅用于独立章节，每组独占一个输出 JSON；章节跨组时显式分配，不让两个 Agent 写同文件。全文足以超过上下文时按 units 分批，处理后记录 sections_reviewed，不能只检索关键词或读头尾。

每个输出遵循：

```json
{
  "group": "chapter-group",
  "sections_reviewed": ["真实 section_id"],
  "summary": "本组完整论述综述",
  "limitations": [],
  "cards": [{
    "slug": "group-unique-slug",
    "title": "概念标题",
    "kind": "claim",
    "statement": "有证据的概括",
    "reasoning": "论证解释",
    "conditions": [], "boundaries": [], "steps": [],
    "application_notes": "哪些是系统整理或延伸",
    "evidence_paragraph_ids": ["真实 paragraph_id"],
    "keywords": [], "trigger_questions": [],
    "source_cases": [{"summary": "保留亲历、转述或假设性质", "paragraph_id": "真实 paragraph_id"}],
    "source_claim_type": "author_claim"
  }],
  "relations": [{
    "from_slug": "现有卡 slug", "to_slug": "现有卡 slug",
    "type": "depends_on", "basis": "source",
    "rationale": "有方向的关系理由", "evidence_paragraph_ids": ["真实 paragraph_id"]
  }],
  "review_notes": [],
  "cangjie_candidates": []
}
```

kind 为 claim/definition/method/case/counterexample；source_claim_type 为 author_claim/quoted_other/system_inference。relation.type 为 depends_on/contrasts_with/composes_with/limited_by，basis 为 source/inference。跨章关系由全书综合阶段另建输出（sections_reviewed 可为空），不补不存在的端点。暂无案例就输出空列表，不捏造。

仓颉候选需 slug、V1:{paragraph_ids,reason}、V2:{new_question,derived_answer}、V3:{reason}。候选不自动获准晋级；根审阅者回读后在独立 review.json 的 cangjie_candidates 中增加 promotion_decision=approved。至少两个独立情境并非两段重复句子，V2 明确为迁移测试，不伪称已在用户生活中验证。

全书综合检查同义重复、观点冲突、第三方署名和首尾覆盖。不强求卡数。普通知识不受仓颉能力筛选限制。装配器验证定位与字段，语义质量仍需审阅。
