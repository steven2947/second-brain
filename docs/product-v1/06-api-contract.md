# HTTP API与异步交互契约

最新追加（2026-09-08，账号找回联调）：OpenAPI **0.12.0，61路径72操作**。新增匿名但须CSRF的POST `/auth/password-reset/request`（email，202统一status=accepted及delivery）和`/auth/password-reset/confirm`（token/new_password，204无正文）。AuthOptions.password_reset增加delivery=disabled/local_capture/smtp及token_ttl_seconds，available与实际模式一致；未知邮箱不会获得存在性提示，缺渠道统一503。token只通过邮件fragment交给页面，再放确认POST body，不进入URL查询或公开响应。`/app/settings`复用原PATCH `/me`、POST `/me/password`与`/auth/logout-all`，不新增相似端点。实测及迁移状态见PROGRESS；操作见[账号找回](../account-recovery.md)。

最新追加（2026-09-08，隐私联调）：OpenAPI **0.11.0，59路径70操作**。新增GET/POST `/me/exports`、GET `/me/exports/{id}`、GET其`/download`、GET `/me/trash`、DELETE `/problems/{id}`、POST其`/restore`及POST `/me/deletion`。导出申请带scope/password和Idempotency-Key，202为任务元数据，下载是受控JSON附件而非永久URL。删除/恢复输入expected_revision，无额外幂等键要求；注销输入password及精确confirmation，202只代表pending，随后登出。重验密码失败401 `INVALID_CREDENTIALS`不等于会话失效；`EXPORT_STALE`须重新生成，`TRASH_EXPIRED`不可恢复。前端类型已生成，后端整批/开发库接线状态见PROGRESS，操作见[隐私维护](../privacy-operations.md)。

最新追加（2026-09-08，后台运营）：OpenAPI **0.10.0，53路径62操作**。新增POST `/admin/users/{user_id}/status`、GET/PUT `/admin/users/{user_id}/quota`、POST `/admin/invitations`、GET `/admin/operations`、GET `/admin/feedback/summary`。状态输入为`status/expected_status/reason`；额度输入为`limit_runs/expected_revision/expected_period`，跨UTC月份或修订冲突拒绝写入。邀请201只返回`delivery=local_capture/delivery_id/expires_at`，不含token、邮箱或本机路径；未配置真实邮件时不能宣称邮件已发。运营统计为本UTC月任务状态数量，反馈为全部历史分类数量，不输出业务正文。重要写操作继续近期MFA+CSRF+幂等；不同权限不会因共享管理入口自动互通。实际迁移和验证状态见PROGRESS。

最新追加（2026-09-08，知识管理）：OpenAPI **0.9.0，48路径56操作**。新增管理sources/imports/releases及其详情、rights、publish/revoke、users与grant操作；撤grant返回204。所有管理写要求近期MFA、CSRF、Idempotency-Key，同体重放且仍重新检查当前权限；审核输入为`{records:[...]}`，后台独立JSON上限256KiB，不复用账号8KB限制。GET imports按created_at/id倒序，游标锚点仍限本人；刷新能恢复最新任务。导入202只表示真实持久任务入队，worker成功只生成validated/unreviewed版本，发布与授权仍需独立动作。具体字段以当前serializers与生成契约为准。

最新追加（2026-09-08，管理身份）：OpenAPI **0.8.0，37路径44操作**。新增POST `/admin/auth/login`、GET `/admin/me`、POST `/admin/auth/reauth`和POST `/admin/auth/logout`。登录一次提交email/password/token/method，method为totp或recovery，成功才建立管理会话；普通会话不可替代。返回当前明确权限及verified_at/fresh_until/session_expires_at，无设备秘密或恢复码。高风险管理操作必须复用`require_admin(permission=..., fresh=True)`；知识发布动作仍在实施。与早期两阶段challenge设想不同，当前直接提交双因素、不创建未验证管理会话，因此没有独立challenge表。使用说明见[管理员入口](../admin-guide.md)。

最新追加（2026-09-08，学习）：OpenAPI **0.7.0，33路径40操作**。已实现GET/POST `/learning`、GET `/learning/:id`、POST其`/messages`与`/archive`、GET其`/jobs/:job_id`及POST其`/jobs/:job_id/cancel`。创建与消息需要Idempotency-Key；消息mode=explain/practice/respond，respond必须带真实exercise的responds_to_turn_id及非空原回答。detail含session/items/next_cursor/library_available/basis_cards/active_job，失权404；只有当前有效browse+analyze许可可用。入队与发布各推进一次revision，下一轮从detail读取最新revision。普通问题runs/jobs接口不接学习父域。下方旧版本计数保留为历史记录，具体字段以生成契约为准。

最新实现（2026-09-08，个人实践）：OpenAPI 0.6.0，27路径33操作。新增GET `/bookmarks`、PUT/DELETE `/bookmarks/:release_id/:card_id`、GET/POST `/actions`、PATCH `/actions/:action_id`、POST `/feedback`。收藏PUT省略note表示保留已有备注；明确note可更新或清空。行动只接answer_id/action_index，返回的四项建议说明始终从当前获准答案读取；修改需expected_revision。答案反馈五类已实现，learning目标暂未实现。上述写操作不要求Idempotency-Key；收藏/行动以唯一约束幂等，反馈仅显式单次提交，不自动重试。所有接口会话/CSRF及no-store规则不变，下方旧阶段计数为历史记录。

2026-09-08追加：现为22路径26操作，新增已实现GET `/answers/:answer_id`。GET job的result_ref现在返回实际已发布同run答案UUID（其他情况NULL）。答案按当前analyze/quote许可重投影，结构化content与rendered_markdown来自同一公开结构，不返回内部包/会话/提示词。用量和额度已接worker，额度不足429 QUOTA_EXCEEDED，拒绝时不留半条消息或任务；SSE仍待实施。实际OpenAPI版本0.5.0。

最新施工更新（WP05-B/WP06-A，2026-09-08）：已实现21路径25操作。新增GET/POST `/problems/:id/messages`（消息分页独立于Problem详情，兼容旧详情DTO）、POST `/problems/:id/analyze`、GET `/runs/:id`、GET `/jobs/:id`、POST `/jobs/:id/cancel`。202返回run_id/job_id/revision，只表示任务持久化；worker/SSE/实际模型输出尚未接通。queued取消直接200 cancelled，running取消202 cancel_requested，终态不改写。分析用途必须整release获准，不能从browse许可推定。实际用量和预算表仍待worker批次，当前未发生模型费用。

当前更新（2026-09-08 15:35）：统一OpenAPI已有14条路径15操作（账号8路径9操作、知识6个GET）。授权仓库、公开DTO及分页通过后端124项整批回归和独立规格/质量审查。下文12:20的404为历史记录，当前六知识接口匿名实际返回401。问题/任务/模型接口仍未实现，规划表不等于实际路由；书房UI也尚未接通。

后续更新（2026-09-08，WP10-A）：六知识GET已接入实际书房，前端使用生成类型与白名单解码，来源重读同时核对release/evidence/book归属。认证默认10秒超时不变，知识请求单独45秒；这只是有界等待策略，不代表整库性能验收。问题/任务/模型接口仍待实施，详见[施工进度](PROGRESS.md)。

后续更新（WP05-A）：创建/列表/详情/改名与归档已实现，实际契约16路径19操作。Problem公开增加`library_available`以区分本人原文可读和知识授权丧失；目前没有消息分页，详情拒绝未实现的cursor。`current_answer_id`返回null，尚未创建答案关联，不冒充分析结果。PATCH只收title/status/expected_revision，status仅active/archived，409含`error.current_revision`；POST须幂等键且不调用模型。消息、删除恢复、任务和答案端点仍待后批实施。

状态：供实现和联调的契约设计，不代表端点已存在。实现WP-05时生成并版本控制 `server/openapi.json`，前端类型从该文件生成；不同时手写第二套枚举。当前Markdown定义语义，OpenAPI生成后须回查此文。

施工更新（2026-09-08）：认证接缝已先行生成 [实际 OpenAPI](../../server/openapi.json)，目前只覆盖8条账号路径、9个操作。`/me`当前返回`{user: PublicUser}`，尚不含未来业务capabilities；MFA、找回邮件、问题档案等下表规划端点未实现，不能据本文推断可调用。新增匿名`GET /auth/options`返回实际注册开关、邀请要求、两份本机测试说明及版本、密码长度限制、找回/MFA可用状态；不是已审核的运营政策。前端必须显示当次说明并显式征得同意，不硬编码或自动接受版本。

生成命令：`.venv-product/bin/python server/manage.py export_api_contract --settings=tests.settings`；`npm --prefix web run generate:api`。旧`export_auth_contract`命令保留为完整产品契约的兼容别名，不能覆盖成账号子集。一致性检查分别加`--check`及运行`npm --prefix web run check:api`。生成只描述已经绑定的实际请求serializer和公开响应；不输出模型提示词、密码值、邀请令牌或私有配置。`tools/api-types`隔离OpenAPI工具要求的TypeScript5，web仍使用既有TypeScript7，不用忽略peer冲突安装。

## 通用协议

历史知识接缝记录（2026-09-08 12:20）：当时知识七表已迁移，`/libraries`系列未登记到实际路由，HTTP返回404。现实现进度以上方15:35更新为准。

同源 `/api/v1`；JSON UTF-8；Cookie会话；所有写操作验证CSRF和Origin。用户身份仅取session，客户端传owner_id/user_id/is_staff/internal_prompt等未知字段直接400，不静默接受。外部对象UUID，知识核心ID需正确URL编码，不当文件路径。

列表默认20条、最大100，cursor分页、稳定排序；搜索q上限500字符；body默认256KB，用户消息≤20000字符，原问题≤4000。服务端限制与UI同时生效，不能只前端拦。

私有响应 `Cache-Control: no-store`；错误为 `{"error":{"code":"REVISION_CONFLICT","message":"档案已更新，请重载后发送。","request_id":"72a3b4c5-d6e7-4890-a123-456789abcdef"}}`。无堆栈、SQL、环境配置或原始供应商报文。

创建问题、发送消息、创建分析/学习/导出任务必须提供 `Idempotency-Key`。键作用域为(owner,method,route,key)，同key同body重放原响应，同key不同body返回409；保留至少24小时。任务失败后的“重试”使用新key和retry_of，不自动重放旧POST。

写问题或学习需要 `expected_revision`；并发冲突返回409并附当前revision，不回传其他用户数据。revision为产品修订，核心event revision只由后端转换计算。

## 端点清单

表中“本人”同时要求对象owner和知识grant；无权对象返回404。邀请/账号存在性统一措辞但不能伪造邮件发送成功。

| Method / path（省略/api/v1） | 输入 | 成功 | 权限及失败 |
| --- | --- | --- | --- |
| GET /auth/csrf | 无 | 200 CSRF bootstrap | 匿名可用，不是登录凭证 |
| POST /auth/register | invite_token,email,password,display_name,policy_versions | 201 user | 有效邀请+CSRF；接受当前已发布政策版本；400输入、409邀请不可用 |
| POST /auth/login | email,password | 普通用户200 user，设置Cookie；启用MFA者202 challenge | 401统一错误，429限流；challenge不是业务会话 |
| POST /auth/mfa/verify | challenge,code | 200 user，设置完整会话Cookie | 单次challenge与验证码；失败限次，过期重登 |
| POST /auth/logout | 无 | 204并撤销会话 | 已退出仍幂等204 |
| POST /auth/logout-all | password | 204 | 本人再次认证；所有会话失效 |
| POST /auth/password-reset/request | email | 202通用受理 | SMTP未配置503 CHANNEL_UNAVAILABLE；不得假称已发送 |
| POST /auth/password-reset/confirm | token,new_password | 204 | 单次token；400不可用；撤销旧会话 |
| GET /me | 无 | 200 profile,capabilities | 401；不返回哈希或管理员内部配置 |
| PATCH /me | display_name,timezone,theme | 200 profile | 本人，邮箱更改首版不开放 |
| POST /me/password | current_password,new_password | 204 | 重新认证；会话轮换 |
| GET /me/usage | 无 | 200实际用量和限额 | NULL计量保持未知 |
| GET /libraries | cursor | 200获准release列表 | 不列出无权书库标题 |
| GET /libraries/:release/books | q,author,cursor | 200 books | grant有效；分页前鉴权 |
| GET /libraries/:release/books/:book | 无 | 200 book及可浏览章节 | 404统一处理 |
| GET /libraries/:release/cards | q,type,book,author,cursor | 200卡片概要 | 不提供无限下载上限 |
| GET /libraries/:release/cards/:card | 无 | 200 BrowseCard | 明示原卡整理，不等于采用 |
| GET /libraries/:release/evidence/:evidence | 无 | 200 SourcePreview | 受限短引/定位，不提供原书文件路径 |
| GET /problems | q,status,cursor | 200列表 | 默认排除deleted |
| POST /problems | question,goal,release_id | 201 Problem | grant校验；只建档，不隐含模型消费 |
| GET /problems/:id | cursor | 200 Problem及消息分页 | 本人；失权可返本人原消息但知识内容标不可用 |
| PATCH /problems/:id | title或status,expected_revision | 200新revision | 只允许active/archived；不能改原问题/owner |
| POST /problems/:id/messages | content,intent,client_message_id,expected_revision | 202 run_id,job_id,revision | 保存原消息并入队；409冲突、429配额 |
| POST /problems/:id/analyze | expected_revision | 202 run_id,job_id | 明确要求直接分析；待回答时用此意图结束问诊而非静默prepare |
| GET /problems/:id/answers/:answer | 无 | 200 PublicAnswer | owner+同problem+实时grant；失权404 |
| DELETE /problems/:id | expected_revision | 204回收站 | 取消在途任务，不立刻物理删除 |
| POST /problems/:id/restore | expected_revision | 200恢复 | 保留期内、本人；不恢复已撤销知识权限 |
| GET /runs/:id | 无 | 200 run公开状态 | 本人+实时grant，不返回internal_* |
| GET /jobs/:id | 无 | 200 job_id,status,stage,result_ref?,error? | 本人及该任务涉及的实时授权；无内部路径 |
| GET /jobs/:id/events | Last-Event-ID | SSE阶段和公开结果引用 | 每次读重新检查账号/grant；终态关闭 |
| POST /jobs/:id/cancel | 无 | 202 cancel_requested或200 terminal | 本人；已完成不假装取消成功 |
| POST /runs/:id/retry | expected_revision | 202新run/job | 原失败/取消、未过时；重新授权和预算预约 |
| GET /bookmarks | cursor | 200列表 | 失权卡仅给不可用占位，不泄露标题/备注中的受限摘录 |
| PUT /bookmarks/:release/:card | note | 200收藏 | 本人+grant，幂等 |
| DELETE /bookmarks/:release/:card | 无 | 204 | 本人，幂等 |
| GET /learning | cursor,status | 200 sessions | 本人 |
| POST /learning | release_id,basis_card_ids,goal,problem_id? | 201 session | 同release、grant；problem同owner |
| GET /learning/:id | cursor | 200 session/turns | 本人+grant |
| POST /learning/:id/messages | content,client_message_id,expected_revision | 202 run_id,job_id | 原回答入库后再反馈，不伪造掌握 |
| POST /learning/:id/archive | expected_revision | 200 | 本人，学习内容保留 |
| GET /actions | problem_id?,status?,cursor | 200 action_records | 本人+grant |
| POST /actions | answer_id,action_index | 201 action_record | 本人答案中真实行动；不让用户写伪依据 |
| PATCH /actions/:id | status,observation,expected_revision | 200 | 本人；不覆盖原分析动作 |
| POST /feedback | answer_id或learning_session_id,category,comment | 201 | 恰一归属正确的目标 |
| POST /me/exports | scope | 202 job_id | 再次认证；不包含原书、提示词、密钥 |
| GET /me/exports/:id/download | 无 | 200受控下载 | 本人+未过期+实时grant，不发长期公开链接 |
| POST /me/deletion | password,confirmation | 202 | 明确确认后禁用访问，清理任务；取消/恢复走支持流程重新核验身份 |

管理端通过 `/admin` 的显式staff权限提供管理动作，非上述普通API的任意参数开关。知识导入只接受管理员登记的受控staging标识，不能传任意绝对路径或URL。端点需在管理实施包中按角色拆分并纳入OpenAPI/权限测试。

### 管理操作契约

以下在`/api/v1/admin`下，要求完成MFA且有对应显式权限；Django后台若使用HTML表单，必须调用同一服务及权限检查，不能另开绕过通道。所有重要写操作验证CSRF、幂等键与再次认证时效，并写审计。

| Method / path（省略/api/v1/admin） | 输入/输出 | 权限边界 |
| --- | --- | --- |
| GET /users | 分页账号状态/配额摘要 | accounts.view；无聊天正文 |
| POST /users/:id/disable | reason→账号状态 | accounts.disable；不得自我提权或静默禁用最后管理员 |
| PUT /users/:id/quota | 运行数/金额限额与币种→限额 | quota.manage；非普通profile字段 |
| POST /invites | email→邀请受理状态 | accounts.invite；未配置邮件走明确本机交付流程，不假发信 |
| POST /releases/import | staging_key→202 job_id | knowledge.import；受控路径与展开限制 |
| PUT /releases/:id/rights | 05规定权利记录→审核状态 | knowledge.review；记录证据和审核人 |
| POST /releases/:id/publish | expected_status→新状态 | knowledge.publish；技术+权利双门 |
| POST /releases/:id/revoke | reason→新状态 | knowledge.revoke；停止相关后续访问 |
| PUT /users/:id/grants/:release | expires_at?→授权 | grants.manage；release合格，不允许普通用户自授 |
| DELETE /users/:id/grants/:release | reason→204 | grants.manage；增加access_revision并失效缓存 |
| GET /jobs | 分页任务元数据 | operations.view；不回原模型请求 |
| GET /feedback | 分类/版本/必要反馈摘要 | feedback.review；正文访问按08核验 |

首次管理员MFA登记/恢复使用本机受控管理流程；验证通过后才能开放管理操作。首版没有自助关闭管理员MFA的网页端点。

## 核心公开DTO

**Problem**：id,title,original_question,goal,release_id,revision,status,clarification {rounds,limit,pending_question,closed},current_answer_id,created_at,updated_at。clarification从核心快照派生，不返回core_state或内部reason。

**Run**：id,problem_id或learning_session_id,job_id,status,stage,input_revision,outcome,stale,answer_id?,error?,started_at?,finished_at?。没有provider原始请求或system prompt。

**BrowseCard**：release_id,card_id,book {id,title,author_display,metadata_status},type,title,statement,explanation,conditions,boundaries,related,source_previews,usage_notice。内容取允许浏览投影；字段不足显式为空并附gap，不用模型记忆补齐。

读取接缝补充（WP04-B施工规格）：保留原卡`steps`、`application_notes`及`source_claim_type`，`explanation`对应原卡`reasoning`；未填原理则为空并写入`gaps`，不生成看似来自书中的解释。归属类型未录入则明确unknown，不默认变成作者主张。`related`只含关系ID/类型/方向端点/依据类别/理由，不嵌套整张内部卡片；系统推断的关系仍标inference。无quote授权的卡可以浏览，但`source_previews`为空并说明原文预览未获准。

**SourcePreview（本段施工规格）**：release_id,evidence_id,book {id,title,author_display,metadata_status},chapter,text,truncated,location。`text`是已逐字校验片段按批准上限截取的连续前缀，不自行转述为原话；location只含已知字符位置/段落ID及定位类型，没有file/source_path、绝对路径或上下文全文。缺quote授权的直接证据查询与不存在ID统一404。定位若仅来自证据汇编，明确说明不等于原书页码。

接口实装字段补充：关系端点在HTTP中命名`from_id/to_id`，分别映射原关系的`from/to`；location为`{kind: original|evidence_compilation,start,end,paragraph_id: string|null,notice}`。详情不开放context或磁盘参数。列表返回`items,next_cursor`，书/卡列表另有`release_id,content_version`；默认20、最大100条，游标签名且绑定当前用户、查询、版本及授权结果集合，15分钟失效。游标不是访问授权，每页仍重新检查权限。卡片检索目前明确使用本机BM25关键词，不暗示已启用向量或模型搜索。

**PublicAnswer**：id,run_id,problem_revision,library {release_id,content_version},status=validated,summary,actions,knowledge_groups,witness_cards,argument_relations,roundtable,verdict,learning_takeaways,continuation_options,next_chat_action,sources,rendered_markdown,quality_notice。

其中witness_cards采用v3的 `adopted_claim`、作者/书名、原理/机制、适用与用户映射、选定证据；剔除original_card_ref里的服务器路径和未采用整卡内容。sources只有本次选定证据。summary由服务端表达层从已验证材料生成并复核，不能让前端根据一个标题另编结论。

## 自编请求示例

```json
{
  "content": "我还没有向这25个人报过价，只是聊过想法。",
  "intent": "answer",
  "client_message_id": "c8b71801-2088-4c4c-9a3c-593fbb1f5b11",
  "expected_revision": 2
}
```

intent允许answer/supplement/analyze_now/unknown；普通输入框由后端根据已知状态判断，按钮意图必须显式保留。模型不能无视用户点“直接分析”。客户端不传facts数组或轮数来绕过状态机。

## SSE与取消

事件格式为 `id: <seq>`、`event: stage|question_ready|answer_ready|learning_ready|export_ready|import_ready|failed|cancelled`、`data: <JSON>`。AI阶段白名单：accepted、understanding、retrieving、evaluating、validating、composing；导出/导入用accepted、processing、validating，界面按任务kind选文案。只在该阶段真实发生后发送。payload只含job_id、可空run_id、stage、可见说明和已授权结果引用，不流出未验证草稿。import_ready仅面向获准管理员；export_ready给受控下载对象ID而非公开文件URL。

连接恢复用Last-Event-ID，重复seq客户端去重；缺口过大返回重新获取任务状态的指令。心跳注释不算业务事件。断线不自动重试POST；登录过期结束流并保留页面提示。API不能在整个SSE期间持有数据库事务或泄露tenant上下文。

取消可在queued直接终止，在running标请求，worker检测后取消HTTP/停止后续处理。模型供应商可能仍计费；不承诺取消等于免费。取消与成功同时发生时以发布事务检查为准，前端展示服务端最终状态。

## 错误与界面行为

| HTTP/code | 用户看到什么 | 客户端允许做什么 |
| --- | --- | --- |
| 400 INVALID_INPUT | 对应字段错误 | 保留非密码输入，修正后提交 |
| 401 AUTH_REQUIRED | 登录已失效 | 重新登录，不自动发送此前敏感内容 |
| 403 CSRF_FAILED | 请求校验失败 | 更新CSRF并由用户重试 |
| 404 NOT_FOUND | 不存在或不可访问 | 不继续猜ID或显示缓存正文 |
| 409 REVISION_CONFLICT | 档案已更新 | 重载并保留未提交草稿 |
| 409 IDEMPOTENCY_CONFLICT | 同提交标识对应不同内容 | 不自动换key重复扣费；检查客户端逻辑 |
| 409 RUN_STALE | 原运行基于旧背景 | 由用户发起最新分析 |
| 429 RATE_LIMITED/QUOTA_EXCEEDED | 等待时间或配额用尽 | 遵守Retry-After，不能无限重试 |
| 503 MODEL_UNAVAILABLE/CHANNEL_UNAVAILABLE | 模型/邮件未配置或不可用 | 保留数据，不转成假成功 |
| 502 MODEL_OUTPUT_INVALID | 本次未形成可验证答案 | 保留旧答案与重试入口，内部有限修复 |
| 504 RUN_TIMEOUT | 运行超时 | 显式重试；显示可能已发生的用量 |

空知识结果是 `coverage_gap`，不是服务异常，也不能填充虚构引用。运行展示说明与失败详细堆栈分开保存。
