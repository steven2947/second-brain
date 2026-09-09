# 数据字典与关系约束

最新追加（2026-09-08，隐私联调）：新增`operations_personalexport`，字段为owner/scope/status/auth_epoch/access_revision/attempts/lease_token/lease_until/deadline/expires_at/error_code/binding/file_key/content_hash和UUID/时间戳。导出使用独立持久租约，不为它制造分析Job或Run；最多3次领取、60秒租约、15分钟任务期限，完成后24小时失效。公开DTO只含id/scope/status/created_at/expires_at/error_code，绑定摘要及存储键不公开。新增`operations_retainedusage`仅保存period/call_count/可空input_tokens/output_tokens/expires_at及UUID/时间，无owner或run；普通runtime无读取权限。

删除请求复用User.status与deletion_requested_at，7天后清理；未另建旧设计中的deletion_requests表。问题复用status/deleted_at/revision，恢复为archived。注销清理保留失效账号占位行以维护共享知识外键，但清空在线个人身份和私有业务记录；不能描述为User行消失。独立HMAC删除清单不在业务库内，流程及密钥要求见[隐私维护](../privacy-operations.md)。本条是实际模型对照，迁移与实测状态见PROGRESS。

最新追加（2026-09-08，后台运营）：复用账号、Invitation、QuotaBucket与AdminMutation，不另建运营事实表。AdminAudit新增有界`reason`，停用/恢复分别记录`accounts.disable/accounts.enable`；额度和邀请记录各自操作。新增额度当前月管理策略与保护触发器，只允许改次数上限和推进revision，不允许改目标owner、历史结算或预留；原用户隔离策略保留。任务和反馈只通过固定、独立权限校验的聚合函数输出数量，不给运行角色跨用户读取原表正文的权限。私有邀请捕获文件不属于公开API或知识库；主开发库迁移状态及实测结果见PROGRESS。

最新追加（2026-09-08，知识管理）：新增`publishing_registeredsource/importjob/adminmutation`已迁入开发库。登记源只能由独立迁移命令创建，runtime只读；ImportJob保存真实owner/device/auth_epoch/source指纹、独立租约、状态和结果release；AdminMutation按owner/operation/key唯一记录body_hash与公开结果。两私有表FORCE RLS，知识表增加受明确管理权限控制的写入策略与版本不可变/状态权限触发器，普通用户仍不能写知识授权。旧RightsRecord不删除，重新审核使旧approved失效并追加新记录；grant修改同事务增加目标access_revision。审计扩展knowledge/grants固定动作，不记录证明正文。

最新追加（2026-09-08，管理身份）：`administration_administratordevice/recoverycode/adminaudit`已迁入开发库；设备保存Fernet密文、last_t防重放、失败计数与下次尝试时刻，恢复码只存SHA256和consumed_at。设备/恢复码FORCE RLS，runtime只读及更新校验所需列；审计runtime只INSERT。管理组及权限不可由runtime授予。当前采用密码与第二因素一次提交、成功后建会话，不落早期设想的mfa_challenges表；明确权限仍用Django组/权限关系，不用is_superuser捷径。主密钥轮换要求见[管理员入口](../admin-guide.md)。

最新追加（2026-09-08，学习）：`learning_learningsession`与`learning_learningturn`已迁入开发库，FORCE RLS和同owner/release/run/回应回合约束生效。Session问题可空、固定选卡带真实书名作者；Run的问题/学习父域恰一，内部保存截至本轮的历史与原文。Turn实际kind另含`user_request`，内容为`{text,sections:[{title,body,basis_card_ids}]}`；feedback必须回应真实user_response，后者回应exercise。学习用途使用现有browse+analyze授权；共用UsageEntry新增purpose=learning。下方早期“学习表尚未实现”为历史状态；learning目标的产品评价接口仍未实现。

最新实现（2026-09-08，个人实践）：`personal_bookmark`（owner/release/core_card_id唯一，note最多2000字符）、`personal_actionrecord`（owner/answer/action_index唯一，四种status、observation最多10000字符、revision）、`personal_feedback`（本人answer、五类category、comment最多2000字符、review_status）已迁入开发库。三表最小DML与FORCE RLS；行动通过owner/problem/answer复合外键保持归属，反馈通过owner/answer复合外键保持归属。行动不另存建议文本，读取当前获准正式答案的原序号；收藏撤权时API不返note。learning_session反馈目标与学习表尚未实现，不能由这些个人记录代替。

2026-09-08追加：`answers_answer`、`operations_quotabucket/runreservation/usageentry`已迁入开发库。Answer存原v3包/公开投影/Markdown/hash，读取按当前权限重新投影；一run只发布一次。QuotaBucket实际用`period`（UTC月首date）而非两个起止列；RunReservation唯一run保存reserved/settled/released。UsageEntry按owner/run/attempt/call_index唯一，实际purpose为extract/plan/analysis/analysis_repair；费用当前仅unknown，token未知NULL。四表最小DML、FORCE RLS与同owner复合FK独立迁移，详细字段以models/migrations为准。

最新施工更新（WP05-B/WP06-A，2026-09-08）：新增`problems_message`、`runs_job`、`runs_analysisrun`三表已迁入本项目开发库，三表FORCE RLS和同owner/同problem/同release复合FK已建立。Message额外保存显式intent；Run额外固定auth_epoch、authorization_snapshot和internal_state，均只在服务端。Job本批仅kind=run、owner不可空；实际字段deadline对应下文deadline_at。学习父域/答案FK/逐调用用量与配额、事件投影随后连同实际执行器一起实现，不使用无约束假对象占位。消息接收只追加用户原文和输入修订，未执行模型前不假写core事件。

当前更新（2026-09-08 15:35）：WP04-B授权/用途与到期过滤、公开DTO及固定版本查询已通过整批回归和独立审查。仍沿用已验收七张知识表，无额外建表。本段使用独立测试库自编材料，产品主库没有知识release，不能宣称实际书籍可商用发布；下方早期“未实现”表述为历史记录。

状态：数据库设计契约，尚未创建数据库。字段的类型、空值、约束和暴露范围以本文件为准；不把JSON示例当已经存在的数据库。

施工更新（2026-09-08）：以上为设计时快照；现已建立独立本机PostgreSQL开发实例，但本文所列业务表尚未创建。当前证据与后续建表状态以[施工进度](PROGRESS.md)为准，实例启动不代表字段、认证或RLS已实现。

后续施工校正（2026-09-08）：普通账号子段已迁移`accounts_user`、`accounts_invitation`、`accounts_policyacceptance`、`accounts_auththrottle`及Django标准session/auth关联表，12张表归迁移角色所有。`accounts_user`对应下方users字段；Invitation目前仅邀请用途，不能冒充多用途account_tokens；PolicyAcceptance以单次实际接受的terms/privacy版本对象记录本机测试同意，尚不是逐文档通用consent_records。MFA、设备清单、业务RLS、知识授权及其他业务表仍待各自实施。四条accounts迁移包含状态变更推进auth_epoch的数据库触发器，避免重新启用后旧cookie复活。

## 通用约定

知识数据库更新（2026-09-08 12:20）：开发库已创建`knowledge_librarycollection`、`knowledge_libraryrelease`、`knowledge_librarygrant`、`knowledge_rightsrecord`、`knowledge_releasebook`、`knowledge_releasecard`、`knowledge_releaseevidence`七表，对应下方libraries/releases/grants/rights与三类投影。实际DDL见`server/knowledge/migrations/0001_initial.py`及`0002_database_access.py`：同release书目复合FK、指纹/唯一性/状态与发布前提约束已落库。运行角色七表仅SELECT，grant强制按owner行级读取，无身份不返回grant。授权到期/权利用途过滤、公开查询DTO和其余业务表尚未完成；建表不代表真实书获准发布。

- 除注明外，各业务表包含 `id UUID PK`（服务端生成）、`created_at timestamptz NOT NULL`、`updated_at timestamptz NOT NULL`。外部接口ISO8601 UTC，前端按用户时区显示。
- `?`表示可NULL；未标?必须有值；JSON默认仅允许指定schema，不收任意对象。文本长度为产品上限，非原理讲解配额。
- `owner_id UUID FK users`用于私有数据，由服务端session注入，禁止客户端写入。UUID不代替权限。
- 有owner的父子关系建立 `UNIQUE(owner_id,id)` 与复合FK `(owner_id,parent_id)`，防止跨用户关联；写入前仍需业务授权检查。
- `revision bigint`用于乐观并发，不等于知识版本；存储修订与核心event revision分别命名，不混用。
- 删除时间默认NULL。用户数据适用08/10的保留规则；授权记录、审计和共享知识不会因一个用户删除就被错误级联。

## 关系概览

```text
users ──< problems ──< messages
              │          │
              ├──< problem_events
              ├──< analysis_runs ──1 jobs ──< job_events
              │         └──< answers ──< action_records
              └──< learning_sessions ──< learning_turns

libraries ──< library_releases ──< library_grants >── users
                    └── release_book/card/evidence projections
users ──< bookmarks / feedback / export_requests
```

`learning_sessions.problem_id`可空；从书房学习不必伪造一个现实问题。一次问题绑定一个release，多书内容在该release内部组织。

## 账号与认证

### users（自定义Django用户，建库前确定）

| 字段 | 类型/约束 | 含义与暴露 |
| --- | --- | --- |
| email | varchar(254)，规范化后唯一 | 登录标识；仅本人/授权账号管理员可见 |
| display_name | varchar(80) | 昵称；避免把邮箱自动当公开昵称 |
| password | Django编码哈希字段 | 仅服务端；不明文、不自制hash算法、不出API |
| status | active/disabled/deletion_pending | disabled立即撤销session与在途任务 |
| email_verified_at | timestamptz? | 无验证证据不得填入 |
| is_staff / is_superuser | bool default false | 创建普通用户时不可传入；运维控制 |
| timezone | varchar(64)，有效IANA值 | 默认Asia/Shanghai，可改 |
| theme | system/light/dark | 默认system |
| auth_epoch | bigint default 0 | 改密/全退出递增，使旧会话失效 |
| access_revision | bigint default 0 | 授权变更时递增，用于缓存与结果发布复核 |
| deletion_requested_at | timestamptz? | 删除请求与保留时钟 |

sessions使用Django服务器端会话存储，另建`session_devices`：owner_id、session_key_hash varchar(128)唯一、auth_epoch bigint、last_seen_at、expires_at、revoked_at?、device_label varchar(120)。原session密钥不出API；保留粗粒度设备说明，不采集浏览器指纹。

`account_tokens`：purpose invite/email_verify/password_reset；email varchar(254)、owner_id?、token_hash char(64)唯一、expires_at、consumed_at?、issued_by?。只存令牌hash、单次原子消费；找回默认30分钟、邀请7天、验证24小时，均为可配置产品默认。令牌不放审计正文。

管理员MFA逻辑字段：`mfa_devices`含owner_id、kind=totp、secret_ciphertext text（仅加密存储）、confirmed_at?、last_accepted_counter bigint?、revoked_at?；`mfa_recovery_codes`含owner_id、device_id、code_hash char(64)、consumed_at?。恢复码单次原子使用，秘密和hash均不出DTO。实现使用经过维护的认证组件，其实际表结构/加密密钥轮换方式需在WP-03映射并迁移，不自己编写认证算法。

`mfa_challenges`：owner_id、challenge_hash char(64)唯一、expires_at、consumed_at?、failed_attempts int。管理员密码正确后只创建短期challenge，尚未获得完整会话；默认3分钟、最多5次尝试。challenge不授予普通或后台业务访问权。`consent_records`：owner_id、document_type terms/privacy、document_version varchar(80)、accepted_at；唯一(owner_id,document_type,document_version)，保留实际接受的已发布版本，不替用户自动同意新版。政策正文作为版本化静态文档管理，默认不额外采集IP作接受证据。

## 知识与授权

### libraries / library_releases / library_grants

| 表 | 字段 | 约束与说明 |
| --- | --- | --- |
| libraries | title varchar(120), description text, status active/suspended | 知识集逻辑名；不等于磁盘路径 |
| libraries | scope demo/licensed/private, curator_id UUID? | scope不是授权，仍必须检查grant；private不自动共享 |
| library_releases | library_id FK, content_version char(24), source_fingerprint char(64) | UNIQUE(library_id,content_version)，校验核心版本一致 |
| library_releases | storage_key varchar(240) | 服务端受控映射；不是任意客户端绝对路径 |
| library_releases | status staged/validated/published/revoked | validated为技术检查，不自动等于rights approved |
| library_releases | rights_status unreviewed/approved/rejected/expired, rights_record_key varchar(240)? | 许可证明私有保存；公开分发必须approved |
| library_releases | card_count int>=0, book_count int>=0, validated_at?, published_at? | 从实际文件统计；禁止手填虚假总数 |
| library_releases | metadata jsonb, metadata_schema_version int | 存正文类型、来源与构建信息，不缓存模型密钥 |
| library_grants | owner_id FK, release_id FK, role reader | UNIQUE(owner_id,release_id)；首版仅整release读授权 |
| library_grants | status active/revoked, expires_at?, granted_by FK, revoked_at? | 到期等同无权；不可只查status不查expires_at |

无普通用户“publish”接口。公共demo只用自编材料。某release失效不重写其hash；撤销grant时提高用户access_revision。共享release的内容由管理员维护，用户删除不级联删除共享知识。

`rights_records`：release_id、scope_book_ids jsonb（空数组表示整个release）、source_description text、basis_type self_authored/public_domain/license/permission/other、license_name text?、proof_storage_key text?、allowed_audience text、allowed_uses jsonb、quote_policy jsonb、valid_until?、reviewer_id?、reviewed_at?、status unreviewed/approved/rejected/expired。审批证明私有；发布时所有书的用途须落在已批准范围内，不能只看release上一个bool。rights_record_key用于版本化审查汇总引用。

WP04-B读取契约细化（施工规格，测试通过前不视为已实现）：

- `allowed_audience`本段只识别`granted_users`，含义是已获得该release有效grant的登录用户；不是公开访问。未知文本不靠AI猜含义，拒绝作为授权依据。
- `allowed_uses`用明确用途名：`browse`为书目和整理卡浏览，`quote`为原文预览，`analyze`保留给后续分析。每个使用目的分别判定，不因可读卡就自动拥有原文或模型出站许可。
- 在加载目录前，以本release完整ReleaseBook投影ID集合核验browse覆盖；加载后再核验投影书目集合/总数与实际manifest一致。非整release覆盖时拒绝整库加载，不能先搜索再隐藏无权书。
- `quote_policy`本段形状为`{"max_chars": 正整数}`，有效上限1–2000 Unicode码点；缺失、布尔值、未知格式均不授quote。这个上限是技术预览控制，不是法律安全线。多条同时适用的批准quote记录取较小上限，保留原文连续前缀并标明截断，绝不拼接伪原话。
- 仅status approved、审批人和时间齐全、来源说明非空、尚未到期的记录可参与判断；非自编/公版依据还须有私有证明键。这只核对录入条件，不代替运营者的许可真实性审核。过期和未覆盖按无权处理，不回显内部审批材料。
- 同一请求在内容读取前后分别复查用户有效状态、grant/collection/release/rights及版本元数据，撤权或到期后的结果不发送；不保留授权结果缓存。短事务身份上下文不可跨文件加载持有。

### 只读知识投影

| 对象 | 字段 | 说明 |
| --- | --- | --- |
| release_books | release_id, core_book_id varchar(240), title text, author_display text?, contributor_metadata jsonb, metadata_status verified/partial | 唯一(release_id,core_book_id)；原编著者/观点人物信息保留，显示缺口不猜 |
| release_books | cover_asset_key?, description text, chapter_summary jsonb | 封面需许可；没有则文字封面 |
| release_cards | release_id, core_card_id varchar(240), core_book_id, card_type varchar(40), title text, browse_payload jsonb | 唯一(release_id,core_card_id)，外键同release书；原卡浏览不等于本次采用 |
| release_evidence | release_id, core_evidence_id varchar(240), core_book_id, chapter text, preview_payload jsonb | 只在授权接口输出批准短引；原书路径与内部上下文不出API |

知识投影可从固定版本重建，不反向修改来源。正文、关系和证据的完整权威结构继续使用原有schema与只读文件，不重复设计一套互相漂移的知识真源。

## 问题与原始消息

WP05-A施工更新（2026-09-08）：`problems_problem`、`problems_idempotencyrecord`两表及owner强制RLS已迁移本项目开发库，真实runtime存储与HTTP批量测试通过。Problem本批采用下列字段但暂不建`current_answer_id`列（待真实答案表和同owner/problem外键一起接入）；原问题使用TextField+数据库1–4000字符约束，公开与服务仍保留4000上限。messages/problem_events、答案与run字段随后接入，不用无约束UUID占位冒充外键。删除状态在模型保留，但本批没有删除/恢复接口。幂等记录48小时到期元数据已记录，尚无自动清理器；未清理记录继续重放检查，不因时钟到期自行新建重复业务。

### problems

| 字段 | 类型/约束 | 说明 |
| --- | --- | --- |
| owner_id | UUID FK | 私有归属 |
| title | varchar(160) | 默认从问题截取，可改，不改原问题 |
| original_question | varchar(4000) | 原问题原样保留，符合核心上限 |
| goal | explain/analyze/compare/act/review | 核心任务类型，不是用户具体目标 |
| release_id | UUID FK | 必须有有效grant，默认固定版本 |
| core_problem_id | varchar(40) unique | 原核心problem.*标识，服务端生成；不直接使用用户提供值 |
| core_state | jsonb | 完整problem-state，含hash与事件；唯一权威核心状态 |
| revision | bigint default 0 | 产品消息/编辑并发版本；核心event数量在core_state内计算 |
| status | active/archived/deleted | 不承载任务状态或澄清状态 |
| current_answer_id | UUID? FK | 同owner、同problem、已发布答案；过期任务不能更新 |
| deleted_at | timestamptz? | 回收站时间 |

不要再建可由客户端任意修改的clarification_rounds列。列表要显示轮数时从已验证快照派生或用事务内更新的只读缓存，快照失配时重算。

### messages / problem_events

| 表 | 字段 | 约束与说明 |
| --- | --- | --- |
| messages | owner_id, problem_id, sequence bigint | 唯一(problem_id,sequence)，同owner FK |
| messages | role user/assistant, kind user_text/clarification/answer/notice | 不允许用户指定assistant角色 |
| messages | content text, client_message_id UUID?, run_id UUID? | 用户内容1–20000字符；唯一(owner_id,problem_id,client_message_id)仅对非NULL |
| messages | published_at?, visibility visible/withdrawn | 系统内部提示不进入该表的公开内容 |
| problem_events | owner_id, problem_id, core_revision bigint, event jsonb, source_message_id UUID? | 唯一(problem_id,core_revision)；事件满足既有schema |
| problem_events | resulting_hash char(64) | 作为审计投影，必须与core_state事务同步，不能两边独立写 |

问题状态更新、消息接收、任务提交、幂等记录在同一事务完成。拒绝并发修订时不得留下半条用户消息。隐私删除优先于事件“长期不可变”，删除策略应清理整份私有档案而非留可回溯正文。

## 运行、答案与异步任务

### analysis_runs

| 字段 | 类型/约束 | 说明 |
| --- | --- | --- |
| owner_id | UUID FK | 非前端传入 |
| problem_id / learning_session_id | UUID? / UUID? | 恰有一个非NULL，CHECK保证；同owner |
| input_revision | bigint | 固定本轮输入的产品修订 |
| kind | turn/analysis/learning | turn可能产生追问；不是所有run都有答案 |
| release_id | UUID FK | 固定知识版本 |
| access_revision | bigint | 启动授权快照，发布仍复查实时grant |
| job_id | UUID unique FK | 同owner，执行状态由jobs唯一承载 |
| previous_run_id | UUID? FK | 同问题/同owner更早运行，学习运行同session |
| core_session_id | varchar(40)? | 仅建立知识会话后才有 |
| internal_request / internal_session / internal_draft | jsonb? | 仅服务端，非普通API DTO |
| prompt_version / policy_version | varchar(120) / varchar(120) | 可审计版本，不等于提示词正文 |
| provider / model | varchar(80)? / varchar(120)? | 配置后实际采用值 |
| outcome | question/answer/learning/coverage_gap/unavailable? | 成功或明确无覆盖后的产品结果 |
| stale_at | timestamptz? | 输入修订变化，不能发布到当前答案 |

### answers

| 字段 | 类型/约束 | 说明 |
| --- | --- | --- |
| owner_id, problem_id, run_id | FK，run_id唯一 | 首版现实问题正式答案；学习输出存learning_turns |
| schema_version | int const 3 | 核心AnswerPacket版本 |
| internal_packet | jsonb | 原答案包完整保留，仅服务端 |
| public_payload | jsonb | 通过白名单投影的公开答案DTO，可失权后禁止读取 |
| rendered_markdown | text | 由验证包生成，经过内容/来源复核与安全渲染 |
| content_hash | char(64) | 用于检测产物变更，不是身份认证 |
| validation_status | structure_passed/semantic_reviewed | 结构通过不自动晋升语义验收 |
| published_at | timestamptz | 发布事务设置 |

### jobs / job_events

| 表 | 字段 | 约束与说明 |
| --- | --- | --- |
| jobs | owner_id?, kind run/export/erase/import | 全局管理任务owner可空且必须admin发起 |
| jobs | status queued/running/cancel_requested/succeeded/failed/cancelled | 状态机见06；terminal不原地重开 |
| jobs | attempt int, max_attempts int, lease_token UUID?, lease_until?, heartbeat_at? | 原子claim；超时worker不能越过新租约发布 |
| jobs | started_at?, finished_at?, deadline_at, error_code varchar(80)?, result_ref UUID? | 错误对外白名单；内部trace另存且脱敏 |
| jobs | retry_of_id UUID?, idempotency_key varchar(128)?, request_hash char(64)? | 绑定owner+接口+key；同key不同payload冲突 |
| job_events | owner_id?, job_id, seq bigint, event_type varchar(60), public_payload jsonb | UNIQUE(job_id,seq)，SSE重连游标；禁止含模型原始token或密钥 |

默认模型单次运行墙钟上限180秒、结构修复额外最多1次、后台失租最多1次重新尝试；为首版配置值，真实模型测试后调。显式手动重试新建任务，重新授权与预约预算。

`idempotency_records`：owner_id、method varchar(10)、route_scope varchar(240)、key varchar(128)、request_hash char(64)、status processing/completed、response_status smallint?、response_payload jsonb?（公开白名单结果）、resource_type?、resource_id?、expires_at。唯一(owner_id,method,route_scope,key)。覆盖创建问题等没有job的POST，不能只依赖jobs上的key。业务落盘与完成记录同事务；重放前仍鉴权，撤权/删除不能从旧response_payload泄露。默认48小时清理，任务较长时不得在终态前过期释放键。

## 用户积累与反馈

| 表 | 字段 | 规则 |
| --- | --- | --- |
| bookmarks | owner_id, release_id, core_card_id, note text default空 | 唯一(owner_id,release_id,core_card_id)；撤权后不返回卡片内容 |
| learning_sessions | owner_id, release_id, problem_id?, title varchar(160), goal text, basis_card_ids jsonb, revision bigint, status active/archived/deleted, deleted_at? | knowledge ID必须同release且有权；学习不重置原问题澄清 |
| learning_turns | owner_id, learning_session_id, sequence bigint, kind explanation/exercise/user_response/feedback, content jsonb, run_id?, responds_to_turn_id? | 唯一(session,sequence)；feedback必须通过responds_to_turn_id关联同session实际user_response，不能凭阅读标掌握 |
| action_records | owner_id, problem_id, answer_id, action_index int>=0, status planned/doing/done/dropped, observation text default空, revision bigint | 唯一(owner_id,answer_id,action_index)；引用答案原行动，不改原建议 |
| feedback | owner_id, answer_id?, learning_session_id?, category helpful/shallow/unclear_principle/wrong_source/other, comment varchar(2000), review_status new/reviewed | 恰一目标，相关管理员处理前遵循隐私访问流程 |
| export_requests | owner_id, job_id unique, scope problems/learning/all_personal, storage_key?, expires_at?, status queued/ready/failed/expired | ready后24小时失效；生成与下载均检查实时权限 |
| deletion_requests | owner_id, requested_at, purge_after, status pending/cancelled/completed, completed_at? | 与账号状态和任务停止同步；到期后台清理 |

## 用量与审计

`usage_entries`：owner_id、run_id、attempt int、call_index int、call_purpose extract/ask/draft/repair/compose/learning、provider、model、input_tokens? bigint、output_tokens? bigint、cached_tokens? bigint、duration_ms bigint、cost_amount? numeric(18,8)、currency? char(3)、cost_kind unknown/provider_reported/estimated、usage_status reserved/settled/released。唯一(run_id,attempt,call_index)；一个run可能多次调用，逐次登记再汇总，不能只记最后一次。token未知为NULL；estimated成本必须有定价版本，不以估算token冒充实际计量。

`quota_buckets`：owner_id、period_start/period_end、reserved_runs/settled_runs int、limit_runs int、reserved_budget/settled_budget numeric、currency、revision；唯一(owner_id,period_start)。用原子更新预约预算，防多标签页/多worker超额；无费用数据时仍以运行数与输出token上限限制。

`audit_events`：actor_id?、subject_id?、action varchar(80)、target_type、target_id、request_id UUID、result allow/deny/error、metadata jsonb白名单。只保存动作与对象标识，不记密码、提示词、完整问题、令牌或原书片段。管理员操作不得绕过审计。

## 索引、删除与一致性

- 常用索引：problems(owner_id,status,updated_at desc,id)、messages(problem_id,sequence)、jobs(status,lease_until,created_at)、grants(owner_id,status,expires_at)、bookmarks(owner_id,created_at)、usage(owner_id,created_at)。索引不能替代RLS。
- 私有子对象随档案的最终删除清理；回收站期内只标记父档案并在所有接口统一过滤。账户purge清理原消息、答案、学习、收藏、个人导出、私有索引与文件。
- 共享知识release使用PROTECT/RESTRICT，不跟随单用户删除；管理员可撤销但不可在仍被历史引用时静默替换文件。
- audit、usage保留最小字段并在删除账户后去标识；不得以审计为由保留完整私密正文。
- 需要跨表维护current_answer时同事务验证owner/problem/run/status/revision；并发失败返回409，不用最后写入获胜。
- RLS、普通事务、worker短事务、权限过期与备份恢复后删除重放，均须用真实PostgreSQL测试；SQLite不是这些测试的替代。
