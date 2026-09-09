# Task 4 修复轮 1 Implementation Plan

> 执行方式：当前工作区内按 executing-plans 分步执行；用户已明确要求直接实施，不另建工作树。

**Goal:** 修复范围外祖先污染，重建卡片笔记候选，完成已批准范围的刻意练习真实蒸馏，保留其他候选状态及来源。

**Architecture:** normalize 保留完整标题栈供排除清单审计，正文路径仅采用栈中属于纳入范围的标题。字符位置、ID、正文与唯一标题范围接口不变；prepare 已将 normalize 源码纳入 job 哈希，自动生成新任务。

**Tech Stack:** Python、unittest、现有 prepare/assemble/validate/complete、既有 vendor/cangjie Skill。

**Spec:** 当前用户修复轮指令及 `.superpowers/sdd/2026-09-09-ten-book-distillation/task-4-review.md` I-1/I-2/I-3/M-1。

## 全局边界与六项检查

1. 职责：通用章节归属修复在 src/distillation/normalize.py；正文蒸馏是 runtime，不加入业务代码。
2. 事实源：真实原书 bytes、原标题位置；路径为派生标注，不改正文以迎合解析器。
3. 依赖：保持纯函数，不依赖CLI/Agent；无新依赖、抽取器或模型API。
4. 接口：normalize_markdown(text, included_ranges) 字段不变，范围唯一标题约束不变；prepare 自动换job。
5. 隔离：只改 normalize 与 tests/test_normalization.py；卡片笔记使用原scope、新job和candidate-v2；刻意练习使用批准scope-v2；其他书不重蒸馏、不升格。
6. 回退：旧job/候选/失败输出原样保留；新候选不合并不发布，CURRENT不改；代码用独立提交可追踪撤销。

## Task A：TDD修复通用路径

- [x] tests/test_normalization.py 增加真实纯函数回归：排除一级/二级父级后的正文三级标题不继承排除祖先；正文四级子节保留正文父级；excluded_sections仍可保留完整路径。
- [x] 增加跨排除区后再次进入正文的回归，保留合法纳入祖先、不保留排除区子级；覆盖多范围及正文文本位置。
- [x] 运行 `.venv-mvp/bin/python -m unittest tests.test_normalization -v`，保存预期路径断言失败。
- [x] 最小修复：标题栈每项保存是否纳入；full path用于excluded，正文path只连接纳入项。不得清空每个正文标题的栈而丢掉合法嵌套。
- [x] 同命令green，再运行 normalization/jobs/assemble/library/merge/retrieval相关测试以及完整测试发现。

## Task B：卡片笔记重建

- [x] 用原scope和修复后的现有prepare创建新job，比较旧document除path/chapter外所有内容相同；source hash及snapshot逐字相同。
- [x] 验证六group sections_reviewed覆盖和所有paragraph IDs、正文bytes相同后才复用，保留原输出SHA。
- [x] 现有assemble逐一传七个输出，目标candidate-v2；validate、complete。旧candidate显式不可合并。
- [x] 保存全部531段路径与181证据的新旧映射，重审受影响归属和短引；绑定新版，独立root尚未完成则仍evaluation。
- [x] 原题集先保存hash、新candidate version、完整命令，再真实检索至fix-round-1新报告；不改题、阈值和旧报告。

## Task C：刻意练习

- [x] 保存用户范围裁决及scope-v2.json：{作者声明}到参考文献和注释；声明只用于双作者/第一人称归属，论证性引言纳入，第三方推荐与尾注排除。
- [x] prepare新job，确认170sections/964paragraphs及第1章章首完整；完整阅读全部units。
- [x] 原苍颉方法顺序执行，总览、五视角、验证/拒绝、RIA知识卡、书内关系及真实分组；所有生成内容仅本书runtime。
- [x] assemble独立candidate、validate、complete；至少12跨章语义自检，冻结5+1问题及hash后真实检索；无独立复核不得accepted。

## Task D：不变书与交接

- [x] 从0到1保持blocked，保存reviewer的不可安全续跑结论，不重复无效prepare或扩大scope。
- [x] 学会提问和定位保留旧candidate及evaluation；仅补版本绑定的审阅证据包、逐个误召回卡拒用与覆盖不足答案。
- [x] 来源计划检查、真实validate/complete与检索检查，保护目录/旧候选/原书/CURRENT指纹一致性复核。
- [x] 写task-4-fix-round-1-report.md；运行git diff --check及测试后只提交必要代码、测试与本计划，不force-add runtime。
