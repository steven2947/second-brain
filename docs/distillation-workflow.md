# 可复用单书蒸馏工作流

这是一条 Agent 管理、脚本执行确定性步骤的工作流。仓颉锁定 v2.5.0，项目补充提示词位于 prompts/distillation/。没有自动调用模型 API 的批量服务；费用和 token 不可观测时保持 null。

## 1. 确定范围并准备

原书先转换为有标题的 Markdown。扫描件的 OCR 质量另行验证。创建书籍 scope.json，包含 book_id（book.slug）、author_id、title、author、compiler（如适用）、edition、scope_rationale 与 included_ranges。每个范围是 start_heading 与 end_heading 的半开区间；最后可用 null。边界标题必须唯一，中间小标题可重复。跳过他人序言，不将正文中的第三方署名去掉。

```bash
python -m src.interfaces.cli prepare --source <原书.md> --scope <scope.json> --jobs-root <用户任务目录> --prompts-root prompts/distillation
```

输出 job_id、规范化正文、来源快照、units 与 state.json。指纹相同则复用，来源/范围/提示词/执行标识/解析代码变化则新建任务。原书不改写。不要改动任务的原文和 units；已完成阶段的结果另存 outputs。

## 2. 全文蒸馏

Agent 读取 vendor/cangjie/SKILL.md、methodology 与本项目 01/02/03/04 提示词。对完整正文做结构、解释、批判和应用阅读；框架、原则、案例、反例、术语五个视角都要覆盖。每组使用独立输出 JSON；格式见 04-output-contract.md，不能只给一句总结。

当前串行逐书处理；单书章节可按独立分组并行。维护待处理/已读/失败单位，失败时只重试受影响单元，保留成功输出。脚本 prepare 不会自行读取书籍产生知识。

## 3. 全书复核及装配

逐卡核对证据、归属和条件；处理重合概念与冲突，不把系统行动编排当作者原话。所有有正文的 section_id 必须出现在 sections_reviewed 中。需要人工审计时另行记录，不把 Agent 自检称为人工审核。

```bash
python -m src.interfaces.cli assemble --document <任务/document.json> --output <组1.json> --output <组2.json> --destination <新候选目录>
python -m src.interfaces.cli validate <新候选目录>
python -m src.interfaces.cli complete --job <任务目录> --output <组1.json> --output <组2.json> --candidate <新候选目录>
```

complete 从任务正文及输出重新装配核对版本，登记完成状态及输出指纹；相同结果重复登记不覆盖旧产物。结构验证不能证明改写意思正确。

## 4. 方法筛选及作者入口

一般观点全部保留，不受仓颉方法门槛限制。根审阅者回读双情境依据、测试新情境迁移、检查区分度；仅将批准的方法写入 review.json 的 cangjie_candidates，增加 promotion_decision=approved。目前生成入口至少需要三项已审阅方法；不足时直接使用通用知识 Skill，不硬凑。

```bash
python -m src.interfaces.cli --library <新候选目录> bundle --review <review.json> --destination <新Bundle目录>
python vendor/cangjie/scripts/cangjie.py compile --bundle <新Bundle目录> --out <新编译目录> --output single --purpose reference
python -m src.interfaces.cli --library <新候选目录> author-skill --compiled <新编译目录> --destination <新作者Skill目录>
python vendor/cangjie/scripts/validate_skill_pack.py <新作者Skill目录>
```

项目作者入口接入完整知识库；仓颉方法卡仅是部分知识。未命中方法路由不能说全书没有答案。

## 5. 验收、入库、交付

先比较关键词、向量和混合召回，再做真正带引用的回答；加入范围不足、反向引语、条件冲突和未用于调整的问题。保存失败案例。满意后才发布候选。

```bash
python -m src.interfaces.cli --library <用户版本库> publish <新候选目录>
python -m src.interfaces.cli --library <用户版本库> package --project . --destination <新试用包.zip> --author-skill <作者Skill目录>
```

publish 切换完整快照，当前不自动合并多个单书。第二本先发布到单独试验库；多书合并、跨作者图谱和专家团回答要另验收后再进入主库。升级程序继续使用外部数据目录，不自动重装种子。

## 从单书扩到批量

复用相同命令和提示词，每本分开 source/scope/job/output/candidate。下一步可增加队列调度、预算上限、重试与跨书合并，不能用 shell 循环伪装模型已自动蒸馏。本轮已跑通单书并记录可复用产物，未进行 168 本批量处理。
