# Second Brain Product V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. If that skill name is unavailable, use the available executing-plans skill and obey repository rules. Do not spawn agents without authorization.

**Goal:** 将现有可审计知识调用层包装成真实、多用户隔离、可自托管的图书馆式分析与学习产品，保留建议深度、书籍原理和续聊能力。

**Architecture:** React/Vite客户端；Django API与同代码worker；PostgreSQL业务数据与队列；受控单release知识适配器；服务器模型调用与v3输出验证。

**Tech Stack:** TypeScript、React、Vite、Django、PostgreSQL、React Three Fiber/Drei；精确兼容版本由WP-02核验锁定，不复用或覆盖现有`.venv-mvp`。

本文件是完整产品的实施工作包与验收接缝，不是已生成的应用源码，也不是无需工程判断即可粘贴运行的逐行代码手册。系统跨度超过单功能计划，采用分子系统规格+工作包的方式；具体功能进入施工时，再依据已锁定环境展开完整测试代码和最小实现，不能把本包中的测试示意当作成品。下列新路径均为拟创建路径；现有文件显式标“已有”。每个包先完成小范围测试，再最小实现再复测，不一次性生成整站后才联调。尚未建立的命令不可拿来声称今天已跑过。

## 所有工作包的共同步骤

- [ ] 阅读本包相关设计、根AGENTS.md及子目录规则；列新增/局部修改/保持不动的清单，按授权边界执行。
- [ ] `git status --short`确认他人改动，记录基线；不清理无关文件。
- [ ] 每个验收子场景拆为2–5分钟可执行步骤：写失败测试→运行确认预期失败→最小实现→复跑→检查diff。复杂任务继续细分，不能用一个“实现全部”复选框替代。
- [ ] 只测试既定需求，不看到结果后改标准；无法运行记录环境阻塞，不伪造通过。
- [ ] 记录commit基线、文件清单、命令、实际输出、时间/token可获得性和残余风险。提交/push按当次授权执行，不整库`git add .`。

## WP-01：基线与测试素材

文件：已有 `docs/development.md`、`tests/call-v2-effect-suite.json`、`tests/test_intake.py`、`configs/local.json`（可能缺失）；新增 `docs/verification/product-v1/baseline.md`、`server/tests/fixtures/product_demo/`。

- [ ] 只读确认工作树、Python/Node/PostgreSQL/容器可用性；区分未知与未安装。
- [ ] 按已有开发指南执行 `.venv-mvp/bin/python -m unittest discover -s tests -p 'test_*.py'`，保存原结果；不为了过环境检查改仓颉锁。
- [ ] 创建纯自编三用户/两个release/有反方与无覆盖的知识fixture；记录作者为“自编测试材料”，不搬真实书进测试仓库。
- [ ] 保存旧3轮和新5轮问题事件示例；固定五类题及澄清回答，记录源文件hash，不改题标签。
- [ ] 本地真实库配置不足时只登记所需路径与核验办法，不自动搜索秘密或搬动书库。

出口：AT-23基线明确；后续可用自编fixture继续搭建，但真实效果验收不得用它替代。

## WP-02：工程骨架与开发契约

新增：`web/package.json`、`web/package-lock.json`、`web/vite.config.ts`、`web/tsconfig.json`、`server/pyproject.toml`、`server/requirements.lock.txt`、`server/manage.py`、`server/config/settings/`、`server/tests/`、`deploy/README.md`。

- [ ] 查官方兼容信息与本机环境，固定依赖和运行时；先写启动/配置校验测试，生产缺密钥必须失败。
- [ ] 建立独立`.venv-product`，不更改`.venv-mvp`；安装到项目环境的动作需在变更清单中说明。
- [ ] 建立React应用、Django API和worker入口；暂不提供假模型答案；建立test/typecheck/build明确脚本。
- [ ] 配置同源开发代理、格式检查、仅自编组件预览；默认绑定本机地址。
- [ ] 增加代码结构/环境/命令文档；verify构建和健康接口无敏感信息。

拟定统一命令（骨架实现后须实际成立）：`npm --prefix web ci`、`npm --prefix web run test -- --run`、`npm --prefix web run typecheck`、`npm --prefix web run build`；后端 `.venv-product/bin/python server/manage.py test`。锁文件之外安装失败不能改成未锁版本蒙混通过。

## WP-03：账户、会话与MFA

新增：`server/accounts/{models,services,views,serializers,urls}.py`、`server/accounts/migrations/`、`server/tests/test_accounts.py`、`server/tests/test_sessions.py`、`server/tests/test_admin_mfa.py`。

- [ ] 建库前设自定义User；先测试普通注册拒绝is_staff和owner字段，再实现邀请注册。
- [ ] 测试/实现登录、CSRF、退出、全退出、改密、单次找回token、速率限制；令牌并发只能消费一次。
- [ ] 邮件提供捕获模式与真实模式的显式区分；缺SMTP回503，不记录密码重置链接到公共日志。
- [ ] 用维护中的认证组件实现管理员MFA，核验许可/版本；禁止手写密码或TOTP算法。测试重放、失效、恢复码单次使用。
- [ ] 账号禁用与删除状态立即废弃会话；权限变更更新epochs；双浏览器冒烟。

出口：AT-03及AT-17身份部分。上线前SMTP与管理员保护未完成不得跳过。

## WP-04：知识发布模型与授权仓库

新增：`server/knowledge/{models,repository,release_loader,projections}.py`、`server/access/{services,context}.py`、对应migrations、`server/tests/test_library_access.py`、`server/tests/test_rls.py`。

- [ ] 先写未授权release不可读、过期grant不可检索测试；实现05中的release与grant模型。
- [ ] 导入只接受登记的staging键，校验指纹与内容；技术通过与rights通过分开。
- [ ] 将已有Library加载器包进权限仓库，每次只返回一个同权限release；禁止先搜全库再截断返回。
- [ ] 实现书/卡/证据只读投影；作者不明显式缺失；索引重建不改原卡或原书。
- [ ] 个人表RLS逐迁移落地，用实际runtime角色测试无上下文拒绝、A/B连接池切换；共享知识服务访问再校验。

出口：AT-04/07/22/25后端部分；查不到许可或来源不是可忽略warning。

## WP-05：问题档案与OpenAPI

新增：`server/problems/{models,services,views,serializers,urls}.py`、`server/openapi.json`、`web/src/api/{client,generated}.ts`、`server/tests/contracts/`、`server/tests/test_problem_revision.py`。

- [ ] 先测试父子owner错误、重复client_message_id、revision冲突；建立problem/message/event/answer模型。
- [ ] 原question只在创建写入；事件快照在同一事务保存，禁止两个独立真源。
- [ ] 实现创建/读取/改名/归档/删除恢复与消息接收；create不偷偷消费模型。
- [ ] 生成OpenAPI，覆盖06普通端点及12管理员动作；生成前端类型并测试额外字段被拒。
- [ ] 加入请求ID、错误码、分页、幂等持久记录和大小限制；响应只用公开DTO。

测试语义示例（非当前可运行测试；执行时写成Django TestCase，helper用真实client和PostgreSQL，不mock授权）：

```python
def test_foreign_problem_hidden(api_a, problem_b):
    response = api_a.get(f"/api/v1/problems/{problem_b.id}")
    assert response.status_code == 404

def test_repeat_create_replays(api_a, allowed_release):
    payload = {"question": "我该先验证哪个想法？", "goal": "act",
               "release_id": str(allowed_release.id)}
    first = api_a.post("/api/v1/problems", payload, idempotency_key="fixture-create-1")
    second = api_a.post("/api/v1/problems", payload, idempotency_key="fixture-create-1")
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
```

此为待实现测试helper契约，不是当前Django client现成参数；goal沿用已有call-request schema的explain/analyze/compare/act/review，不在产品端另建不同枚举。

## WP-06：队列、取消、SSE和用量

新增：`server/runs/{models,queue,worker,events,services}.py`、`server/runs/management/commands/runworker.py`、`server/operations/usage.py`、`server/tests/test_job_races.py`、`server/tests/test_budget.py`。

- [ ] 先测试两个worker不能同时合法发布、过期lease不能发布、预算并发超限；实现短事务领取/lease/heartbeat/fencing。
- [ ] 保存run输入revision与授权版本；新增事实、撤权、取消在发布事务二次检查。
- [ ] 建立provider attempt实际usage账，预算预约/结算/释放有唯一约束；未知token为NULL。
- [ ] SSE只发真实阶段/成品引用；重连seq去重、过期退回状态查询、撤权断流。
- [ ] 测试重复POST、running取消、超时、worker进程终止与重启；费用可能重复和产品结果不重复分开报告。

出口：AT-14/16/25；不能用前端setTimeout模拟状态冒充此包完成。

## WP-07：模型端口与旧核心适配

新增：`server/ai/{ports,provider,core_adapter,intake_service,schemas}.py`、`server/tests/test_core_adapter.py`、`server/tests/test_provider_contract.py`。只读复用已有 `src/orchestration/`、`schemas/`、`prompts/`。

- [ ] 先以固定provider响应验证原始消息→user_update→ask/prepare→request的真实重放；后端不得直接写轮数。
- [ ] 实现服务器prompt加载与版本记录；Provider模式disabled/demo/local/provider明确区分，不自动读其他工具的密钥。
- [ ] 校验用户事实与推断分离；明确直接分析意图有效；第五轮后不再追问，新事实不抹旧档案。
- [ ] 权限仓库提供Library后调用create_call_session，再完成v3草稿与build_answer_packet；有限修复失败明确失败。
- [ ] 做自编库真实连线后，使用获准知识和配置provider跑一条真实题；记录真实usage和耗时。
- [ ] 重跑原intake/adoption/validation测试，不因Web便利绕开core契约。

出口：AT-06/07/09/16，真实库或模型条件缺失时保留阻塞，不标完成。

## WP-08：深度答案与公开投影

新增：`server/presenters/{answer,knowledge,learning,redaction}.py`、`server/tests/test_public_answer.py`、`server/tests/test_answer_depth_contract.py`。

- [ ] 先写“未采用内容不能回流”“作者归属不可换”“内部路径不出DTO”的失败测试。
- [ ] 由验证包生成建议、知识详解、真实分歧/条件裁决、行动和最后续聊；系统延伸单独标识。
- [ ] 公开字段严格白名单；从同一公共结构生成Markdown与页面结构，避免两个版本内容不同。
- [ ] 结构检查之后单独审阅自然语言增补；语义误归属不可用schema通过掩盖。
- [ ] 固定题同输入对照，确认开头建议、原理和续聊未退化；无反方/无覆盖有诚实降级。

出口：AT-08/09/10/15；仍不能称五类题全量效果通过，等WP-14。

## WP-09：设计系统、入口与真3D

新增：`web/src/styles/tokens.css`、`web/src/brand/copy.zh-CN.ts`、`web/src/components/ui/`、`web/src/features/{auth,home,mascot}/`、`web/src/features/mascot/config.ts`、`web/src/pages/`；`assets/character/librarian.blend`、`web/public/models/librarian.glb`与poster、许可记录。

- [ ] 先做首页/对话页两张高保真方向稿并展示，保留图书馆式清爽排版；不拿紫色渐变聊天模板代替设计。
- [ ] 建立day/night token、字体、间距、空/错/加载组件，按钮/输入/抽屉可键盘操作。
- [ ] 接真实登录页面；密码字段不持久化。管理员入口不在公共导航宣传。
- [ ] 制作原创可编辑3D馆员，保留源模型；视线跟随、拖动、复位、触摸与键盘替代按03实现。
- [ ] 验证懒加载、poster、WebGL失败、prefers-reduced-motion、低性能和移动端；3D不挡登录。
- [ ] 建立只在开发环境开放的组件样本页，给出后续改主题/文案/人物的方法。

出口：AT-01/02/18/19，有真实浏览器证据；需要新软件/付费资源时先走授权，不为了模型效果乱装全局依赖。

## WP-10：对话、来源和书房

新增：`web/src/features/{problems,chat,library,bookmarks}/`、`web/src/components/knowledge/`、`web/e2e/problem-flow.spec.ts`、`web/e2e/library.spec.ts`。

- [ ] 先组件测试问题/任务状态，再接生成API类型，不手写另一套response字段。
- [ ] 实现提问、澄清、直接分析、阶段等待、重连、取消、重试、版本切换；IME组合期间Enter不发送。
- [ ] 正式答案首屏建议可用；原理展开与来源抽屉保留上下文；书名作者和实际采用关系可追踪。
- [ ] 实现真书房、搜索筛选、详情、收藏；失权立即隐藏受限内容，不以localStorage保持旧卡片。
- [ ] 续聊按钮填入明确可编辑指令、不自动发送消费；新增事实保护未提交草稿与版本冲突。

出口：AT-05/07/10/11/19；纯mock录像不算真实联调通过。

## WP-11：学习、行动、产品反馈

新增：`server/learning/`、`server/actions/`、`server/operations/feedback.py`、`web/src/features/{learning,actions,feedback}/`、`server/tests/test_learning.py`、`web/e2e/learning-action.spec.ts`。

- [ ] 先测试learning与problem的owner/release一致；学习不必先创建伪问题。
- [ ] 建立session后通过明确首条消息启动讲解；解释/练习/用户回答/反馈分别保存。
- [ ] 原理可展开，不强设卡数/字数；练习为系统自编；没有用户回答不能捏造掌握程度。
- [ ] 从真实answer行动创建记录；更新观察后显式送回同一问题继续聊，不改旧答案。
- [ ] 反馈类型区分建议浅/原理不清/来源错等，后台汇总元数据；试用访谈指标与事件埋点分开。

出口：AT-12/13/24；AI“你已掌握”一句不替代学习交互验收。

## WP-12：管理后台与许可审核

新增：`server/operations/admin.py`、`server/knowledge/admin.py`、`server/operations/audit.py`、`server/tests/test_admin_permissions.py`、`docs/admin-guide.md`。

- [ ] 先建立权限矩阵测试，再提供账号禁用、配额、知识导入校验、权利记录、发布与撤权动作。
- [ ] 管理员只能传登记staging键；压缩包路径/展开量检查；导入失败不触碰当前release。
- [ ] 发布需技术与rights双门；未审权利不得给普通用户授权；演示自编材料也留出处。
- [ ] 只显示排障必要任务/计量元数据，不默认展示全部用户聊天；重要动作重新认证并审计。
- [ ] 撤权立即阻止队列结果、SSE、缓存及下载，建立可复跑测试。

出口：AT-17/22/25；Django管理界面存在不等于产品权限正确。

## WP-13：导出、回收站和删除

新增：`server/operations/{exports,retention,erasure}.py`、清理management command、`web/src/features/settings/`、`web/src/features/trash/`、`server/tests/test_privacy_lifecycle.py`。

- [ ] 先测试下载时再次撤权、删除账户worker不再发布、恢复不能恢复grant。
- [ ] 导出个人记录，知识内容按现有许可再次过滤；不含原书、内部prompt、秘密。
- [ ] 实现30天回收站、7天账户删除冷静期、24小时导出有效期和到期任务，按08的唯一策略。
- [ ] 注销立即失效会话；过期物理清理有边界、统计、审计和幂等；备份恢复删除清单独立保存。
- [ ] 设置页展示实际数据处理范围，隐私/协议页面标版本；正式运营文本待审核，不用演示文本冒充法律审定。

出口：AT-20/25；不能只做“删除按钮返回成功”。

## WP-14：系统、效果和安全验收

新增：`web/e2e/security.spec.ts`、`server/tests/test_release_gates.py`、`docs/verification/product-v1/`报告；已有固定题只读保留。

- [ ] 按09逐项建立AT子场景结果，所有P0/P1映射；空白项记未跑。
- [ ] 运行旧底座+新server+前端typecheck/test/build+浏览器e2e，实际命令与环境写入报告。
- [ ] 两用户/多个release、并发、任务重启、取消、撤权、RLS、缓存和导出做跨层测试。
- [ ] 五类固定题真实模型评审，同题对照建议深度、原理、质询和续聊；记录审阅人和分歧。
- [ ] 检查前端产物、日志、DTO、依赖与许可；手机/键盘/减少动态/3D预算实测。
- [ ] 失败项局部修复后重跑原失败场景及相关回归；同类问题反复两次先复审职责边界。

出口：D2与D3相关证据齐备；硬失败不能降级成“后续优化”。

## WP-15：部署、备份和恢复演练

新增：10列出的deploy文件、`server/config/settings/production.py`、`server/tests/test_production_settings.py`、`docs/verification/product-v1/recovery.md`。

- [ ] 先测试生产预检缺密钥/错误DB角色/demo模型会拒绝，再编写最小容器和代理配置。
- [ ] 在新目录/新DB验证从零启动、迁移、管理员初始化、许可知识导入和一次真实问答。
- [ ] 加密备份→新DB恢复→重放删除/撤权→冒烟；记录RPO/RTO实际结果，不覆盖已有库。
- [ ] 验证升级兼容、worker排空、失败回滚；应用版本回滚不冒充数据库回滚。
- [ ] 写明域名、邮件、模型、备份目标待部署者填写；本任务不自动公网开放。

出口：AT-21实测通过，用户能自行部署但尚未替用户部署。

## WP-16：最终交付与修改指南

新增：`docs/product-handoff.md`、`docs/customization-guide.md`、`docs/licenses/asset-register.md`、`docs/verification/product-v1/final.md`；局部追加已有docs索引。

- [ ] 核对REQ01–25、WP01–16、AT01–25无遗漏；明确通过/阻塞/未来范围。
- [ ] 展示用户主流程，包括真实知识/模型答案、作者原理、继续聊、学习与行动反馈、退出重登。
- [ ] 用真实一次改主题/改文案/替换人物配置证明可维护，不只承诺“容易改”。
- [ ] 交付源码、锁文件、配置模板、API/schema、许可、验证、部署恢复与管理员手册；不打包密钥和私书。
- [ ] 展示最终diff与未提交变化；只有获得当前提交/推送授权才执行，逐路径stage。

完成条件：用户拿到可验证的首版与可自部署资料；公开运营仍受D4外部条件限制。不能把本文件的复选框全勾上替代证据。
