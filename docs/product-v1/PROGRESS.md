# 产品施工进度与验收证据

更新：2026-09-08（隐私批次已进入开发库：个人导出/受控下载、30天回收站、7天注销及有界本机维护；后端282项、前端178项通过，API/worker已更新。本轮Mac仍锁屏，隐私和后续业务页面实机交互未验；调度/完整备份恢复及真实模型效果仍待补）。其他设计文档中的早期施工状态为历史快照，以这里和实际代码为准。

## 总体状态

完整产品目标进行中，尚未达到本地完整演示或可部署候选。账号/书房/问题对话/正式答案/收藏/行动反馈/独立学习练习、管理知识发布及账号运营已接入真实数据库与接口；其中登录、邀请注册、书房和问题管理已有真实浏览器联调，后续业务页面待补。正式模型链已实现但配置仍disabled，尚无真实供应商效果验收。原创GLB馆员已实际加载并通过键盘旋转/复位截图核验；账号剩余能力、隐私与部署仍需继续，不把局部闭环当成产品完成。

授权仓库与六个知识只读API及请求内投影优化已通过129项后端整批回归、独立规格及质量审查。书房前端63项测试通过，两轮独立审查通过；真实浏览器验证使用独立测试库自编材料。产品主库当前无用户/邀请/会话/知识release/登记源；管理发布流程已用自编材料验证，真实书籍尚未登记、导入或发布。

- 分支：`codex/auditable-call-layer`；源码基线：`e74bf5f38ff12b1f855fbc9f6d75d48ec62b85a5`。本批尚未提交或推送。
- 新工程位于`server/`与`web/`，独立`.venv-product`；原`.venv-mvp`保留。
- PostgreSQL16开发实例只绑定127.0.0.1:55439；运行角色与迁移角色分开。角色限制不等于已完成用户RLS隔离。
- 预览地址：http://127.0.0.1:5173/ 。需要开发服务运行，不能直接双击`web/index.html`。现在显示真实登录入口；`/register`为邀请注册，`/app`为受保护账号页，原联调页保留在仅开发可用的`/dev/status`。
- 模型模式disabled；无真实供应商调用。没有购买、对外发布、复制原书或使用其他工具密钥。

## 工作包状态

WP03找回与设置前端进展（2026-09-08）：`/forgot-password`、`/reset-password`与`/app/settings`已接公开API，0.12生成类型/类型检查/构建一致通过。新增找回12项、设置7项，完整前端 **197/197通过13.65秒**；主JS503.56kB/gzip146.12kB，CSS40.24kB/gzip7.88kB，3D块927.67kB大包提示保留。首次全量因旧测试仍把settings当未知页失败，改为真正未知地址；第二次发现旧聊天测试在消息未loaded时断言可发送，独立14项通过后补显式等待加载条件，保留Unicode/IME/幂等原断言。第三次整批全部通过，未修改聊天业务逻辑。后端找回整批正在运行，尚未在开发库迁移，SMTP依旧未配置；本条不冒充真实邮件或浏览器验收。

当前WP03找回密码批次（连续授权内）：新增普通账号密码重置申请/一次性确认、受控邮件待发记录与worker接线、SMTP/本机捕获/禁用配置及对应测试；局部扩展匿名auth-options、公开契约和隐私清理；前端新增忘记密码/重置页，替换原未开放提示，其他入口保留。职责为普通账号找回，不处理管理员MFA恢复或更改知识授权；事实源为当前账号状态/密码/epoch与实际待发及消费记录，不能把202队列受理当邮件送达；依赖accounts→Django认证/邮件、受控worker，不改原调用核心；接缝验证未知邮箱统一响应、CSRF/限流、令牌到期/并发单次/改密注销失效、SMTP失败不假成功、URL不采用Host注入、token不进入前端持久存储/日志；变化隔离在recovery模块和必要配置/路由/任务及清理接线，无新付费依赖；先独占测试库整批验证，再开发库必要迁移，回退禁用新找回入口且保留旧登录。默认邮件disabled，不向真实邮箱发送、不读取其他工具秘密、不公开部署或推送。按本人前端/文档与一个后端Agent分工，不重复细粒度双审。

同批账号前端补齐（连续授权内）：新增`/app/settings`，接现有PATCH `/me`、POST `/me/password`及`/auth/logout-all`，添加真实资料修改/密码重验/退出全部设备的确认和测试，账号导航局部新增链接。以当前`/me`及写响应为事实源；前端只用公开接口，不增后端数据表/权限、不自动改邮箱、不影响原调用。验证密码原样发送/失败清空、未登录与隐藏销毁、全退出不假成功；其余账号/书房页面保留。

WP13前端接线进展（2026-09-08）：`/app/privacy`与`/app/trash`已接真实OpenAPI 0.11元数据类型，账号入口、问题删除、导出申请/状态/受控JSON下载、回收站恢复及注销确认均已实现。新增隐私17项包含下载失败不报成功、临时Blob释放、密码清空、隐藏身份重验、修订号提交及过期/超限准确提示；完整前端 **178/178通过13.10秒**，typecheck随build通过，主JS490.81kB/gzip143.04kB、CSS40.24kB/gzip7.88kB。3D独立块927.67kB警告保留。本条只证明前端整批，后端清理专项/全量仍执行中，开发库尚未迁入隐私表，不能据此宣称下载或注销实机全流程完成。

当前WP13隐私生命周期批次（连续授权内）：新增个人导出任务/受控下载、问题回收站、账号删除请求及有界后台清理、核验后取消删除的本机支持命令与测试；前端新增隐私设置/导出进度/回收站/注销确认页，局部接问题删除、账号导航和公开类型。职责为本人数据生命周期，不改变知识事实或代用户申请导出；事实源为当前账号、原问题/个人记录、真实任务/删除时刻及实时权限；依赖privacy→现有accounts/problems/learning/answers/access和队列，核心原书只读；验证本人再次认证、CSRF/幂等、双用户隔离、下载到期与撤权、删除阻止晚任务、30天回收站/7天冷静期和有界物理清理；变化隔离在新privacy及必要过滤/worker/迁移，其他内容保留；先独立测试库验证，再本项目开发库向前迁移，清理仅匹配到期记录和精确私有文件，保留共享知识与最小去标识计量/恢复删除清单。不清理主库真实数据，不执行支持恢复实际账号、不公开部署或推送。完整保留期限/恢复演练属于整体交付要求，不把删除请求返回成功当物理清理完成。

当前WP12后台运营批次（连续授权内）：新增后台运营服务/API/最小数据库策略及测试；前端新增`/admin/operations`账号状态、月度次数额度、邀请与任务/反馈统计，局部接管理导航及生成类型。账号停用与恢复仅针对普通账号，不恢复旧会话，不处理删除待办账号；邀请明确本机捕获交付，不冒充已发邮件。职责为账号运营，不读取聊天、提示词或反馈正文；事实源为当前账号、月度额度、实际任务和反馈分类计数；依赖运营管理→现有administration/publishing幂等接缝/accounts/operations，核心只读；验证显式权限、近期MFA、CSRF/幂等、并发额度下限、撤销会话和私有字段不出DTO；改动隔离于新模块和必要路由/数据库策略，其余内容原样保留；迁移先独立测试库再开发库，回退先撤新增管理权限，不删除账号或原书。次数额度不冒充金额预算，模型依旧disabled。按前后端分工整批验收，不提交或推送。

下一整批WP12知识管理（连续授权内）：新增`server/publishing/`受控源登记、导入任务、权利审核、发布/撤销、用户授权与对应迁移/API/测试；局部扩展worker、知识表最小写入策略与公开管理契约，父端新增管理知识页面及API适配。职责为管理固定知识版本，不重新蒸馏；事实源为本机登记的固定目录及真实权利记录，技术通过不自动批准版权；依赖publishing→administration/knowledge，API和worker始终用runtime，不放入迁移密钥；接口验证明确权限、近期MFA、CSRF/幂等、指纹、完整权利覆盖、撤权与普通用户拒写；变化隔离在新应用及必要接线，原书/core/prompts/examples只读；迁移先独立测试库再本项目开发库，回退先撤新写权限，不删除已发布历史或源目录。无真实书籍自动登记/导入/发布，只用临时自编素材测试。用户要求先搭完整流程，前后端并行后集中一次验收。

当前WP03-B/WP12管理入口批次（连续授权内）：新增`server/administration/`管理员MFA/明确权限/安全审计/受控初始化命令、对应迁移与测试，局部接身份后端/settings/urls/契约；前端新增独立`/admin/login`与`/admin`管理身份/权限页面及测试，不在普通导航宣传。复用Django密码与django-otp校验，加密TOTP秘密、哈希单次恢复码，不手写认证算法；父代理补项目内免费精确依赖并同步锁。职责为管理身份和后续管理动作的唯一授权入口；事实源为当前账号/确认设备/显式权限及会话验证时刻；依赖管理层→账号与成熟认证组件，不允许读个人聊天或知识表任意写；测试接缝为密码+OTP、重放/失效/恢复码、重新认证、权限撤销和普通接口边界；变化隔离在administration与必要接线，原书/核心提示词保留；迁移先测试库再开发库，回退先关闭管理路由，不删除旧账号。先完成可用身份入口，知识发布动作随后复用它，不将本段标整个后台完成。按用户要求合批，不重复细审。

当前WP11学习闭环批次（连续授权内）：新增`server/learning/`独立学习会话/回合/讲解与练习输出、对应迁移/API/测试；局部扩展既有runs为问题与学习恰一父域，复用worker租约、当前授权、额度和真实逐调用账。前端新增学习列表/选卡创建/讲解/练习/提交回答/反馈与导航。职责为独立学习，不伪造Problem；事实源为实际选中卡、原始请求及真实练习回答，系统延伸与自编练习明确标注；依赖learning→access/knowledge及现有任务服务，原核心与提示词只读；接口检查同owner/release、幂等、旧修订、撤权、取消及无回答不生成讲评；变化隔离在新learning及必要任务接线；迁移先独立测试库再本项目开发库，回退不删除旧问题或原书。按用户加速要求前后端并行、合批测试，不逐模块重复双审或润色文档。

当前WP09-B真3D馆员批次（连续授权内）：新增`features/mascot/`参数/按需3D/交互与降级测试、局部替换AuthShell静态展示并保留poster；新增原创建模脚本、blend制作源、glb网页模型与许可/再生成说明。新增并锁定项目内Three/Fiber依赖，建模用官方免费Blender仅解包在本项目忽略的工具目录，不安装系统服务、不购买资产。职责为视觉且不接身份/聊天；事实源为原创模型与参数，图像不是3D替身；web只读公共glb；接缝测试拖动限角/复位/键盘/无WebGL/减少动态/离屏释放；变化隔离在mascot和AuthShell，不改原书/提示词/backend；回退保留静态图，不迁移DB。按整段合并测试，不逐模块双审。

当前WP10收藏/WP11行动反馈批次（连续授权内）：新增`server/personal/`收藏、行动记录与答案反馈模型/服务/API/迁移和对应测试；新增`web/src/features/personal/`、公开API适配与页面，局部接卡片收藏、答案行动按钮、导航及生成契约。职责为个人实践记录；事实源为本人记录和原正式答案，不复制原书、不改原行动；依赖personal→answers/knowledge/access，不改核心提示词；接口验证同owner/当前授权/真实action_index/修订冲突/取消收藏；变化隔离在新应用及必要接线；迁移先独立测试库再开发库，回退不删除原书或旧问题。前后端分工实现，集中一次主流程验收，无逐模块双审；学习讲解及练习另接真实模型，不以收藏代替学习完成。

当前WP10-C/WP07正式答案接缝：新增web/api/runs与features/chat及测试/样式，局部把Problem详情的对话占位替换为真实消息分页、发送、直接分析、任务轮询和取消；父代理新增ai/core_adapter与公开答案投影接缝、对应测试。职责分别为公开API交互和已授权Library→原v3验证包；原消息/核心会话/验证包为事实源；依赖web→公开DTO、server→原core，不反向；测试同键重试、修订冲突、隐藏清理、采用/证据边界；改动隔离在新chat/ai，原提示词只读；无本批必需DDL，后续答案持久化与预算随发布事务接入，不能把内存包当已保存正式答案。继续整段集中验收，不新增每模块双审。

当前WP06-B/WP07接线清单：新增runs/queue.py与执行入口，补任务租约/实际事件和问题已消费消息游标的事务投影；局部修改ai/intake_service支持先合并未处理的多条原消息、再问一次或准备分析，保留原单消息API；新增相应测试与局部开发说明。职责为任务生命周期与core调用接缝；core_state和原消息仍为事实源，游标只和核心成功发布同事务推进；依赖worker→ai→原core，原核心和提示词只读；接口检验过期租约/取消/撤权/新修订/多消息不丢失；变化隔离在runs、ai及必要模型字段；迁移先测试库再项目开发库，回退不删除用户原文。本批不伪造模型或答案；真实网络传输、预算与完整答案发布继续接入，不以基础worker代替完整产品。

同批受限网络接缝：按既有项目内免费依赖授权补`httpx==0.28.1`到独立产品venv、pyproject和锁文件，新增ai/provider.py及回环测试服务契约；普通用户不能指定base_url/key，不读取环境代理或跟随重定向。版本与异步/超时行为核对[PyPI](https://pypi.org/project/httpx/0.28.1/)、[HTTPX接口](https://www.python-httpx.org/api/)；本批只测试自编回环响应，不自动消费真实供应商。

下一批WP05-B/WP06-A执行清单（已在连续授权内）：新增问题Message、runs的Job/AnalysisRun及同owner迁移，消息接收/分页、直接分析任务、状态和取消服务与测试；父代理局部接HTTP/serializer/contracts/urls/settings并生成类型。职责为原消息与任务持久化，不提前制造已完成的AI结果；原文和core_state仍是事实源，jobs独占执行状态；server依赖原core不反向；事务/幂等/revision/RLS/父域/取消是接口接缝；新增runs和messages局部隔离，无新依赖；迁移先独立测试库，回退先撤访问再撤表，不改原书或原核心。worker、预算/逐调用账与完整答案链随后继续，不把入队当成已分析。批次末集中验证，不另派细粒度双审。

当前批次（WP10-B + WP07入口接缝）：前端新增问题工作台/创建/详情页面和局部导航，复用实际四个问题操作；父代理并行新增`server/ai/ports.py`与`intake_service.py`、对应入口测试，将原消息与模型提案转换为现有intake事件，不改原核心或prompt文件。职责为页面交互和服务端入口编排；事实源仍为原消息/核心快照；server→core依赖不变；接口校验停止意图/五轮上限/来源绑定，候选推断不冒充用户原文；隔离在新features/problems和ai目录；前端回退撤路由，纯入口模块无DDL，任务和消息落库由后续WP06执行。本段没有真实模型调用，不能把可重放提案测试当真实AI效果验收。

执行节奏调整（2026-09-08）：用户明确要求“不要审核这么精细，先搭建或加速”。后续改为按完整用户流程批量实现、阶段末集中验收，不再为每个小模块重复派规格/质量双审或反复全量回归。保留用户隔离、原书只读、私有提示词、真实模型/演示区分及必要数据完整性检查；非阻断样式和文档细节集中收尾。这是执行节奏变更，不缩减完整产品目标或把未测项目标为通过。

WP05-A下一批执行清单（已含在“按清单连续执行”的问题/对话授权内）：新增`server/problems/`的Problem、IdempotencyRecord、迁移、服务、公开serializer/views/contracts及测试；局部接`server/config/settings/environment.py`、`urls.py`、`contracts.py`，生成OpenAPI与前端类型并补进度。先打通创建/列表/读取/改名/active与archived切换，创建不调用模型；消息/事件投影、答案FK、删除恢复和任务入队随WP05-B/WP06接入，不建伪run或未约束答案指针。本批不安装依赖、不删除原内容、不改core/prompts、不发布或推送；新迁移先在独立测试库验收，主开发库待复核后执行。

六项检查：问题服务负责本人档案/并发/幂等；`core_state`和不可改写原问题为情境事实源，不另设可写轮数；依赖server→现有intake，页面仅公开DTO；测试接缝包括真实runtime RLS、A/B父域、同key重放/异体冲突、旧revision拒绝、失权读取降级；本批隔离在新problems应用，不改知识读取性能路径；迁移回退先撤runtime再撤RLS，不碰知识表/用户表数据，不把测试库销毁当成生产回退证明。

2026-09-08后续整批授权：用户在goal目标中明确追加“按清单连续执行”，确认书房、对话与分析闭环，以及必要的项目内依赖、开发库建表及配置/文档更新。继续冻结原核心与提示词，不购买、不公开部署、不提交或推送；真实供应商凭据缺失时不读取其他工具密钥。

当前进入WP10-A书房只读闭环：新增`web/src/api/knowledge.ts`与对应测试、`features/library/`页面/测试及独立样式；局部接`ProductApp.tsx`与账号页导航、更新旧“书房未接通”的测试断言，保留其他账号行为。客户端仅为知识读取提供较长有界等待，不改变账号请求默认超时；不安装新依赖、不迁移或导入真实书库。执行顺序：接口与页面失败测试→并行最小实现→联合回归、独立双审→真实浏览器回读。收藏、学习、分析写入作为后续整批工作，不用假按钮或模拟答案冒充。

WP10-A六项检查：职责为公开DTO适配与阅读呈现；服务端固定版本响应是页面事实源，原书不复制；web仅依赖公开API、不导入src或提示词；输入转义/响应校验/竞态取消/失权遮蔽/分页等是测试接缝；知识读取独立于原账号代码，旧账号路由保留；本段无数据库迁移或持久客户端缓存，回退只撤本段页面接线与文件。

2026-09-08后续授权：用户回复“好的 继续”，确认补装并锁定免费依赖、授权仓库、书籍/卡片/来源查询与测试、局部路由及文档。本轮不改原书/src/prompts/schemas/examples，不购买、不公开部署、不提交或推送。

本段步骤：受控固定版本加载及失败测试 → 有效授权/用途与到期检查 → 公开查询和DTO → 独立规格/质量审查、串行PG和真实HTTP复验。继续使用现有linked worktree；开工80项基线通过7.327秒，测试库已销毁。

六项影响检查：职责分别在release_loader（受控只读加载）、access（实时授权）、repository（知识读取）、views/DTO（公开契约）；PG授权与固定源文件为事实源；依赖只server→src；接口先鉴权后磁盘读取，失权/路径/hash/跨用户/公开字段均设反例；旧核心、认证与文件原样保留，只新增业务接缝；无新DDL或主库业务内容写入，本段代码回退不删除已建知识表。

jsonschema4.26.0依据[官方PyPI](https://pypi.org/project/jsonschema/4.26.0/)核验MIT、Python>=3.10及Draft2020-12支持；只补到独立产品venv，并锁定本次解析的传递依赖，不引入向量模型或旧venv路径。安装和验收结果另记，不以依赖存在宣称业务完成。

安装复核：产品环境15条精确依赖全部与锁一致，pip check通过；新增jsonschema/attrs/referencing/rpds-py/jsonschema-specifications元数据均为MIT，旧核心在产品venv对A/B自编库真实校验成功。加载器16项测试：实现者0.111秒、父代理0.113秒、独立规格0.117秒、独立质量0.112秒，均通过且两审查无阻断项。发现普通`manage.py`入口无法导入src（此前PG配置插入root掩盖了这个问题）；计划在本段服务入口补最小、与cwd无关的路径接入和子进程回归，不改src，也不把`PYTHONPATH=.`临时测试命令当最终运行契约。

同输入对照：分别用`.venv-mvp`与`.venv-product`读取A/B自编夹具，比较完整books/cards/evidence/relations及同一“琥珀试行”关键词查询JSON，结果相等；仅证明该自编材料核心读出没有变化，不证明真实书籍语义或AI建议质量。

启动入口补丁：manage.py与config/asgi.py仅按`__file__`定位项目根并append到sys.path，不前插遮蔽server/tests。两个独立子进程测试先因ModuleNotFoundError:src失败，再通过；从临时cwd清除继承PYTHONPATH/SB_/DJANGO_，实际导入核心并加载自编release。独立规格复验18项（入口2+加载器16）通过，质量复核进行中。旧底座另跑125项通过7.381秒，既有ONNX遥测落盘受限警告未消除。

| 工作包 | 状态 | 实际进度 / 剩余 |
| --- | --- | --- |
| WP-01 基线与素材 | 进行中 | 已跑旧底座基线；新增三persona/两release、反方/无覆盖、旧三轮与新五轮材料，6项测试通过，独立规格与质量复核通过；真实库配置与vendor差异仍需定位 |
| WP-02 工程骨架 | 进行中 | server/runtime独立复核通过；web中文白名单修复后规格与质量复核通过；统一测试入口、worker入口、部署开发说明仍未齐备 |
| WP-03 账号会话 | 普通身份与管理MFA已接，整包未完成 | 普通账号/邀请/会话/改密/全退出/限流，独立管理双因素/恢复码/重新验证与明确权限、普通账号停用恢复及本机邀请已实现；最新后端全量264项通过。SMTP找回和设备管理等剩余能力待补 |
| WP-04 知识授权 | 本地技术与管理接缝通过，整包未完成 | RLS/约束、受控版本加载、有效grant/权利覆盖/到期、quote独立限制、六个GET及管理导入发布/任务撤权已接；真实书籍许可、全库容量及完整跨层验收未完成 |
| WP-05 问题API | 问题、消息、任务与答案已接，整包未完成 | 创建/列表/读取/改名/归档、消息分页、实际事件、答案关联及删除恢复已接；当前契约59路径70操作，后端282项通过，完整跨层浏览器验收待补 |
| WP-06 任务计量 | 任务/用量/额度已接 | 实际逐调用账与月度运行限额已迁移，失败无调用释放，有调用仅结算一轮；SSE等仍待接入。当前模型配置disabled |
| WP-07 核心适配 | 正式worker/v3发布已接 | 原消息→入口→固定库→v3验证→答案/游标同事务发布；真实模型与效果未验收 |
| WP-08 答案呈现 | 结构化API/页面已接 | 当前许可重投影、书名作者/原理/圆桌/行动/续聊已实现；完整答案页面浏览器交互及真实回答效果仍待补验 |
| WP-09 首页与3D | 源模型与交互已接，部分实机验证通过 | 原创blend/GLB/真实poster；真实GPU加载、键盘旋转和Home复位已实测；拖动中间帧、移动端性能和完整公共首页仍待验收/搭建 |
| WP-10 对话书房 | 阅读/对话/答案/收藏已接 | 含历史答案、收藏笔记、失权占位和取消收藏；续聊仅填框不自动发送 |
| WP-11 学习行动 | 学习与行动主流程已接 | 独立session/选卡/讲解/自编练习/真实回答与讲评/历史上下文，共用任务与计量；真实学习效果、浏览器联调及学习目标的产品评价接口待补 |
| WP-12 管理发布 | 管理知识与运营主流程已接，整包未完成 | 管理MFA、受控源登记/导入任务/权利审核/发布撤销/用户grant、普通账号状态/次数额度/本机邀请/任务与反馈聚合已接；264项后端与161项前端通过。运营迁移已入开发库，完整管理浏览器流程与真实书籍发布未验 |
| WP-13 隐私流程 | 本地接口/维护与开发库接线完成，整包未完成 | 导出/受控下载、30天回收站、7天注销与本机维护/取消命令已实现；后端282项、前端178项通过。未配置定时调度、常规90天审计清理或完成备份恢复/浏览器演练 |
| WP-14 全量验收 | 未开始 | 当前小范围测试不代替产品或真实效果验收 |
| WP-15 部署恢复 | 未开始 | 本机开发启动不等于部署与备份恢复演练 |
| WP-16 最终交接 | 未开始 | 完整源码功能、修改指南与最终证据尚未齐备 |

## 实际验证记录

### WP13个人隐私生命周期（2026-09-08，整批接通）

- 新增`operations/privacy.py/export_worker.py/maintenance.py`、公开serializer/views/contracts、两个管理命令及0005/0006迁移；局部接问题删除恢复、关联学习父域过滤与普通worker导出处理。前端新增`api/privacy`、`features/privacy/`与两组测试、样式，局部接账号/问题入口和路由。原src/prompts/schemas/examples及锁定效果题无diff。
- 后端专项 **18/18通过**，唯一全量 **282/282通过43.981秒**，模型无迁移漂移，测试库已销毁；覆盖真实JSON附件、正式答案公开投影、许可省略/短引撤回、下载二次复核、租约重领/耗尽、超过20项分页、关联学习/行动/反馈/用量清理、7天冷静期、独立删除清单重放和支持取消。不是完整备份恢复演练或真实供应商效果验收。
- 前端 **178/178通过13.10秒**，build/typecheck通过；OpenAPI **0.11，59路径70操作**与生成类型一致。新增4项准确错误提示先失败后通过，避免把过期恢复和过时导出建议为无效重试。主JS490.81kB/gzip143.04kB，3D独立块927.67kB警告保留。
- 本项目开发库已迁入`operations0005/0006`。runtime仍为`sb_runtime`且super/createdb/bypass均false；导出表ENABLE/FORCE RLS均true，runtime不可读无身份保留统计。主库用户0、登记源0；未执行真实账号清理、支持取消或真实书籍导入。
- 精确正常停止旧API45572/worker45582后更新为API **53516**（8019，会话88621）及worker **53527**（会话12309）；两者不含迁移凭据、模型disabled。5173代理ready200，匿名exports/trash401且no-store，隐私/回收站页面路由200。Mac锁屏，以上HTTP检查不冒充登录后浏览器交互。
- 到期清理必须由独立迁移角色显式执行；普通worker没有跨租户维护权限。已新增[隐私操作说明](../privacy-operations.md)，42天删除清单依赖稳定密钥及独立目录。真实定时调度、常规90天审计/日志清理、备份撤权重放和完整恢复仍待部署批次；本批未删除真实资料、购买、公开部署、提交或推送。批次token不能可靠独立分摊，不估算。

实际接线对照：
```diff
- 问题只有归档；账号页无个人导出、回收站或注销入口
+ 问题删除确认 → revision校验 → 回收站 → 30天内恢复为归档
+ 隐私页密码重验 → 导出队列 → 受控JSON下载 → 24小时失效
+ 注销确认 → 会话/任务立即失效 → 7天冷静期 → 本机有界清理
```

下一批优先补账号找回/邮件接缝及可部署运行配置，再统一浏览器和真实效果验收；完整产品goal仍进行中，不把本批通过当最终交付。

### WP12后台运营（2026-09-08，加速合批完成）

- 新增`server/adminops/{accounts,invitations,views,serializers,contracts}.py`及`test_adminops.py`；复用现有账号、额度和管理幂等事务。只新增`administration.0004_operations_audit`与`operations.0004_admin_projections`，没有新运营事实表或新依赖。普通账号状态按CAS修改，恢复与停用分开审计，旧会话不会因恢复重新生效。
- 月度额度GET无写副作用；PUT同时核对当前UTC月与修订号，复用账号锁保护占用下限。新增数据库策略只开放管理员当前月的额度操作，禁止改历史消费/预留、转owner或删除。任务/反馈只提供固定聚合函数，测试实际跨两个普通owner统计任务2条/反馈4条，原表跨用户内容仍不可读。
- 邀请仅开发本机捕获；0600独占文件位于0700私有根，公开响应只有投递编号/方式/到期。同键重放不会重复邀请，写文件失败回滚数据库，只清理本次实际创建的文件。没有发送邮件或为主库创建真实邀请。
- 新增`web/src/api/adminops.ts`、`features/admin/OperationsManager.tsx`、`AccountOperations.tsx`和独立样式；局部接管理路由/导航/固定错误提示。次数不冒充费用、邀请不冒充已发邮件；账号列表需主动读取，只有quota权限时可直接指定UUID。原始账号/原因/凭据不持久化客户端，隐藏时清空。API使用生成类型并额外校验owner/月/安全整数/总数/公开字段。
- 验证：前端先6个缺路由测试失败，再6/6通过；受影响新旧测试24/24通过；唯一前端全量 **161/161，13.68秒**，typecheck/build/check-api通过。主包472.58kB/gzip138.36kB，CSS38.36kB/gzip7.62kB；既有3D延迟块927.67kB警告保留。后端首次全量264项只有旧路径计数48的断言失败（实际53），更新该契约计数并强化跨owner聚合后，最终 **264/264，36.052秒**；OpenAPI **0.10.0，53路径62操作**、Django check通过。测试库已销毁，不用自编材料替代真实模型效果。
- 两条迁移已成功进入本项目`sb_product`；runtime仍`sb_runtime`且非super/createdb/bypass，主库用户/release/登记源仍0/0/0。API PID45572（8019，session20767）、worker PID45582（session72318）已更新，Vite5173继续运行；ready返回ok，新增operations/feedback摘要匿名HTTP401，页面路由200。API与worker未带迁移密钥，模型仍disabled。
- CUA本轮报告Mac锁屏，**没有验证已登录运营页的真实浏览器操作**；该项并入后续完整业务演示。新增迁移回退尚未实测，不把正向迁移当回退证据。原`src/prompts/schemas/examples`及固定题无diff。本批不购买、不公开部署、不commit/push，独立token无法可靠分摊，未估算；测试时间不是全部开发时间。下一批进入隐私导出/回收站/注销，再补账号剩余能力与部署交接。

实际接线对照（原管理/知识能力保留）：
```diff
  /admin → 管理身份
  /admin/knowledge → 知识版本与授权
+ /admin/operations → 账号状态 / UTC月次数额度 / 本机邀请 / 有界聚合
+ 额度写请求：limit_runs + expected_revision + expected_period
+ 聚合读取：固定函数返回分类数量，不开放任务/反馈正文
```

### WP03-B/WP12管理员身份（2026-09-08，加速整批）

- 新增`server/administration/`双因素登录、显式权限、重新验证、追加审计、受控TTY初始化与三张管理表；新增`web/src/api/admin.ts`、`features/admin/AdminPage.tsx`、管理样式和7项交互测试，局部接路由与普通登录说明。没有创建真实管理员或在普通导航开放管理提权。
- 后端最终 **239/239通过34.760秒**，模型无迁移漂移；包括真实OTP失效/重放、失败退避、双连接恢复码仅一次成功、权限撤销、普通会话边界、运行列权限与实际初始化prepare/confirm。测试库已销毁。前端整批144项通过后，生成0.8.0真实契约修正权限类型收窄及非法权限测试载荷，最终管理 **7/7通过3.95秒**、build通过。
- 免费项目依赖精确锁定django-otp1.7.3/cryptography50.0.1/cffi2.1.1/pycparser3.0，pip check通过，原环境保留；使用与许可见`docs/admin-guide.md`。不是自行编写TOTP或密码算法。
- `administration0001/0002`已在本项目开发库迁入，runtime回验两表FORCE RLS=true；audit INSERT=true、SELECT=false；修改TOTP密文及自行插入权限关联=false。主库用户/版本=0/0，测试库残留0。
- API与worker已精确重启；启动临时参数误写不存在的`config.settings.dev`导致失败，已移除该猜测覆盖，使用项目真实默认`config.settings.base`，未修改配置文件。API PID28899运行，worker已启动；5173管理页200、匿名管理身份401、正确`/health/ready`返回ok。错误的`/api/v1/health/ready`不是健康路由，404不代表服务故障。
- 实际接线：`/admin/login`→双因素POST成功→`/admin`，没有密码正确但未验证MFA的临时管理会话；高风险动作5分钟再次认证，绝对会话8小时，设备秘密不进公开DTO。仍无真实浏览器/GPU与供应商效果验证，未提交或推送。

### WP12知识管理前端与接缝（2026-09-08，进行中）

- 新增`api/publishing.ts`、`features/admin/KnowledgeManager.tsx`、`PublishingForms.tsx`、`publishing-shared.tsx`、样式和7项交互测试；局部新增`/admin/knowledge`及内部管理导航。原账号页、知识读取和核心提示词保留。管理API关键类型来自实际OpenAPI0.9.0，不由页面自由声明后台权限。
- 实际交互：登记来源选择→显式导入→持久任务状态恢复/轮询→书名作者与独立技术/权利状态→多份人工记录及用途/期限→单独发布确认→指定普通用户授权/撤权。无自动批准/发布/授权；账号检索仅在具备权限且点击后执行。公开接口不返回来源绝对路径或证明正文。
- 客户端变更对照：`requestJson`原仅允许POST携带Idempotency-Key，现允许POST/PUT/PATCH/DELETE，仍拒绝GET且不自动重发；原写请求默认行为保持。发布单次请求等待60秒，超时不假定成功；同页面同内容手动重试保留原键。自动GET刷新保留未提交审核草稿；页面隐藏仍清理身份和私有草稿。
- 前端集中 **151/151通过14.26秒**，build/check-api通过。补发布等待及缺范围/用途表单提示后，受影响 **7/7通过2.31秒**并重新build通过；主包457.03kB/gzip134.30kB，3D依旧独立懒加载块，有大包警告。未声称真实浏览器验收。
- 后端第一轮247项通过35.344秒后，修正知识专用256KiB JSON读取（账号8KB不变），补中文审核>8KB、证明文件存在/链接/删除、设备和epoch撤销、grants-only及32条任务的最新顺序分页。最终 **251/251通过37.438秒**；迁移无漂移，OpenAPI检查一致。固定测试库已销毁。生成契约0.9.0、48路径56操作。
- 新迁移`administration0003`及`publishing0001/0002`已在本项目开发库应用，runtime不持迁移凭据；知识管理写入通过RLS、明确权限及状态触发器，原普通grant只读策略保留。主库用户/版本/登记源=0/0/0，新私有表及知识版本/grant FORCE RLS均true；runtime无身份管理权限false，无法登记源。真实资料没有被导入或发布。
- 本机API PID36809和新worker已重启（会话30286/95164）；5173代理`/health/ready`=ok，匿名sources/releases=401，管理知识页面200。最终前端build主包457.99kB/gzip134.74kB，check-api与git diff --check通过；原src/prompts/schemas/examples无diff。管理使用说明已更新`docs/admin-guide.md`。
- CUA本轮可操作和截图：真实登录页静态馆员→点击3D→真实WebGL馆员，方向键四次后出现明显侧面，Home回正；拖动调用完成但释放即回正，未用释放后的同姿态截图伪称拖动中间动画已验。未登录访问`/admin/knowledge`实际跳至`/admin/login`。当前不再是全面锁屏阻塞；已登录管理全过程、后续业务页面及不同设备性能仍待统一实测。Three.Clock只出现弃用警告，无捕获到error，不等于所有运行错误均已排除。
- 本批按用户要求前后端并行、整批验收，无逐模块双重审查、购买、公开部署或提交推送；本批独立token无法可靠拆分，不估算。下一批优先补账号/运营和隐私能力，再统一端到端展示。

### WP11独立学习闭环（2026-09-08，加速合批）

- 新增`server/learning/`模型/服务/生成发布/API/迁移/6组纵向测试；局部扩展runs为问题与学习恰一父域，共用worker租约、当前授权、额度及逐调用账。创建不建伪Problem、不调用模型；实际选卡带书名作者，历史回合与原回答固定到本次输入。三轮测试history长度1/3/5，后续提问保留上文。
- 五类记录分别保存：user_request/explanation/exercise/user_response/feedback。讲评绑定同session真实非空回答，回答绑定已发布练习；AI自编练习及无卡依据的延伸显式标注。详情撤权404，列表隐藏失权记录；普通问题任务API保持旧父域，学习使用专用任务路径。
- 新增`web/src/api/learning.ts`（生成类型+解码）、`features/learning/`、独立样式和9项交互测试；局部接ProductApp/账号/书房导航。列表、跨搜索选卡创建、讲解、练习回答及反馈已可操作；段落下带知识卡、书名作者。续聊只填可编辑草稿，不自动发送；实际状态轮询、active_job恢复、同体重试、冲突保留输入与隐藏清理已接。
- 后端专项 **6/6通过1.018秒**，唯一全量 **228/228通过23.544秒**（真实PostgreSQL受限运行角色）；前端唯一全量 **137/137通过12.54秒**，typecheck/build/生成契约一致通过。OpenAPI **0.7.0，33路径40操作**。JS419.89kB/gzip125.04kB、CSS31.87kB/gzip6.51kB；3D延迟块既有927.67kB警告保留。自编provider证明接线，不替代真实效果验收。
- 四条迁移已在本项目`sb_product`完成；runtime仍sb_runtime且非super/createdb/bypass，两张学习表FORCE RLS=true。主库用户/release仍0/0，test_sb_product已销毁。API PID20071（8019）与worker已重启，模型disabled；未导入真书或测试用户。`tools/dev/product_demo.py`局部补学习表的受限清理顺序，本批未启动浏览器demo。
- CUA再次报告Mac锁屏，浏览器及GPU待验。原src/prompts/schemas/examples无diff，固定效果题SHA256仍`32fc53e3518087f983e1ee13a629c9cc2ab5c6bd3fa5ad0a7ffd737c0a4e51bf`。批次token不可独立取得，不估算；无提交/推送/购买/公开部署。下一批继续管理发布与账号/隐私基础能力，保持合批节奏。

主要接线前后对照：
```diff
- AnalysisRun仅问题父域，学习页面未挂载
+ AnalysisRun的问题/学习父域恰一；共用任务、授权、计量
+ 学习列表 → 选卡创建 → 显式讲解/练习 → 原回答 → 针对本次回答的反馈
```

### WP09-B原创3D馆员与按需交互（2026-09-08）

- 子代理通过官方Blender4.5.13 ARM64及SHA256清单在`.runtime/model-tools/`建立项目私有制作工具，未全局安装、未禁用安全机制、只读挂载已卸载。新增`assets/character/build_librarian.py`、`librarian.blend`、README/许可；网页资产为1,333,852字节GLB、878,280字节真实渲染poster。101节点/96网格/17材质/64,192三角形/0纹理及外部URI；原概念图保持不变。
- 父代理新增`features/mascot/`与样式、局部替换AuthShell展示。Three0.185.1/Fiber9.7.0/@types-three0.185.4锁到本项目web，未执行安装脚本；React版本落在实际peer范围。模型第一帧前显示poster，导入包和加载均不阻塞登录；指针仅在展示区、ref姿态不逐帧刷新业务；释放回中/键盘/短问候翻页、离屏及后台卸载、超时和上下文丢失降级均接上。
- 手机/减少动态/低规格/省流量默认静态，可显式打开；低规格DPR1、无阴影，桌面最高DPR1.5、512阴影。手动减少动态3D只即时旋转，不自动跟随/问候。`frameloop=demand`静止不申请连续帧，实际帧率仍待GPU测量。
- 13项本批测试覆盖纯姿态、组件交互/降级、实际Three GLTFLoader解析交付模型。前端一次全量 **128/128通过12.10秒**，typecheck/build/API一致通过。入口394.29kB/gzip118.56kB；3D独立延迟块927.67kB/gzip247.66kB，Vite大块提示保留不掩盖；CSS28.54kB/gzip5.87kB。未改后端，不重复其222项整批测试。
- 主代理实际view_image查看Blender海报；本机5173模型/海报返回200且长度与文件一致，API健康正常。Mac锁屏仍使真实WebGL/拖动/GPU/移动端截图待补；自编视觉替身和Blender图**不代替浏览器验收**。GLB hash`6fb6fa236c32cb6a93f8f1add35e0ca0e18ed30ed6d678e0450ba6eabd4e0f14`；[修改指南](../../web/src/features/mascot/README.md)已写。模型为刚性轻动作，无走路骨骼；没有购买、真实模型消费、主库迁移或commit/push。批次独立token不可得。

### WP10-D/WP11-A个人实践整段（2026-09-08）

- 新增`server/personal/`及三表，七个实际操作：收藏列表/保存/取消，行动列表/创建/修改，答案反馈。收藏不复制知识正文；PUT省略note保留已有笔记，撤权后note=null仍可取消。行动绑定本人正式答案真实序号，重复加入不覆盖观察，修改使用expected_revision；失权或删除父问题不可读写。答案反馈不启动模型。
- 新增`web/src/api/personal.ts`、`features/personal/`、样式及两个测试文件，局部接书卡/答案按钮、两个页面与导航。记录执行后显式带回同问题对话框，私有草稿只在React内存传递，不写URL/history/storage，不自动POST。首次交互测试发现路由转换期间提前清空草稿，改为一次性ref交接后6/6交互通过；收藏按钮不清空旧笔记，冲突保留输入。
- 子代理个人记录8项真实PG通过；父代理一次全后端 **222/222通过21.823秒**，无系统检查问题，测试库已销毁。前端全量 **115/115通过11.85秒**；typecheck/build/API生成一致通过，JS381.62kB/gzip114.34kB、CSS27.27kB/gzip5.58kB。OpenAPI 0.6.0现27路径33操作。
- 迁移前核对`sb_product/sb_migrator`与runtime身份保持`sb_runtime`、测试库不存在；迁入`answers0002`、`personal0001/0002`。三表FORCE RLS均true，主库用户/releases仍0/0。API PID9826已更新，worker已恢复（仅runtime权限、模型disabled）；5173代理ready正常，匿名actions/bookmarks均401。匿名检查不替代已登录业务测试。
- 真实PG的A/B登录HTTP及自编worker发布→行动跟进通过；CUA再次确认Mac锁屏，**没有声称本批真实浏览器验收通过**。原src/prompts/schemas/examples无diff，固定效果题SHA256仍`32fc53e3518087f983e1ee13a629c9cc2ab5c6bd3fa5ad0a7ffd737c0a4e51bf`。没有新依赖、真实模型消费、真实书发布、commit或push。独立批次token不可得，不估算。

关键接线对照：`卡片阅读 → BookmarkControl → PUT收藏`；`正式答案.actions[index] → POST行动`；`PATCH观察+revision → 同problem内存草稿 → 用户确认发送`。旧原行动与知识卡不改，旧续聊末尾保留，未实现的学习不由收藏冒充。

### WP06-C/WP08正式答案与计量整段（2026-09-08）

- 新增`server/answers/`发布/读取/表达/HTTP/契约及同owner模型迁移，新增`server/operations/`月度额度、运行预留和逐调用账；局部接enqueue/terminal/worker。答案、原核心状态/消费游标、完成通知、任务终态同事务落库。取消/撤权/新输入/旧租约不能发布；无候选是独立coverage_gap，不造空v3包。
- GET答案按当前quote许可重投影，聊天只存完成通知，防旧聊天绕过短引撤权。包与草稿的嵌套对象已分离，发布前重跑原v3验证。原src/prompts/schemas/examples不改。
- 每次调用先reserved再结算实际usage；即使正文无效也保留已报告的token。缺失为NULL，不估算费用。新月默认100轮，每尝试最多24次调用；一轮有调用只结算一次，无调用释放。主worker仍使用disabled配置，未产生真实供应商消费。
- 真实登录→发送→worker自编提案→v3保存→GET答案通过，3次调用分别记账、结算1轮。43项集成通过4.476秒；首次完整测试命令误选顶层同名tests，改用明确server/tests。随后发现旧知识迁移测试只恢复knowledge、留下依赖表缺失，修正finally恢复全部leaf而非放宽业务权限；**212项后端全量通过18.095秒**。之后新增失效正文usage测试1项通过0.056秒、迁移配置1项通过0.045秒；两项不包含在212里。原采用+产品接缝23项通过1.482秒。
- 新增`config/settings/migrate.py`保留runtime身份、连接独立migrator。首次临时命令替换runtime URL，被身份保护拒绝并回滚；正式配置下answers0001、operations0001/0002、runs0003迁移成功。四个新表runtime FORCE RLS均true，主库users/releases=0/0。
- 前端新增`api/answers`、自编fixture、`features/answers/AnswerView`和样式/测试；局部接Conversation的真实job.result_ref→GET答案。支持历史答案、作者/原理/边界、圆桌和缺口、短引/来源预览分开；最后续聊仅填框，保留全部草稿。**104项前端全量通过11.39秒**，typecheck/build通过，JS361.43kB/gzip109.71kB、CSS25.28kB/gzip5.32kB。
- 契约22路径26操作，与生成类型检查一致。新API PID4038、worker PID4035已启动，受限runtime且模型disabled；5173代理ready=200、匿名答案GET=401。未购买、提交、推送或导入真实书。
- 新增`tools/dev/product_demo.py`可重跑独立测试库浏览器联调。CUA报告Mac锁屏，已请用户手动解锁；**本批浏览器验收未完成**。临时PID1515已停止、自编测试库已清理，可重建，不影响主库。批次独立token不可得。

### WP10-C真实对话页面（2026-09-08，加速合批）

- 新增`web/src/api/runs.ts`与测试、`features/chat/Conversation.tsx`、`styles/chat.css`、`ChatFlow.test.tsx`；局部替换Problem详情对话占位并同步实际revision，保留未提交草稿；ProblemPage只增加按问题ID隔离的组件key。没有新增依赖、假答案或模型权限。
- 页面接真实消息分页、显式发送/直接分析、约2秒GET轮询、取消、终态重读；网络结果不明时同内容保留原幂等键/客户端消息ID，409手动核对，401/404/隐藏清理，429等待后手动重试。仅加载到末页才恢复最后用户消息关联任务，不假称最新任务。正常成功追问使revision+1，不再被误报为旧背景。
- 子代理相关28项与typecheck通过；父代理最终前端全量 **93/93通过11.22秒**，`npm run build`通过（JS344.15kB/gzip104.52kB，CSS22.40kB/gzip4.83kB）。本批未重复浏览器或PG全流程测试，留到答案发布接齐后统一联调；先前浏览器证据仅覆盖账号/书房/问题管理。
- 下一整段：答案持久化/授权发布、逐调用用量与运行配额→接worker正式结果→公开答案接口和完整解释页面→一次端到端联调。模型仍disabled，不以自编提案代替用户真实回答。原核心/prompt/schema/examples无diff，锁定效果题SHA256未变，无提交/推送。

### WP07正式答案接缝（2026-09-08，集中验证）

- 新增`server/ai/core_adapter.py`与`tests/test_product_core_adapter.py`；只给原`ai/intake_service._generate`增加可选输出预算参数，入口默认6000不变，正式分析使用16000。原核心、提示词与固定样例没有修改。模型仅获得候选语义白名单，不获得证据source_path/origin；完整固定会话仅留服务端参与核验。
- 自编测试提案经真实检索、逐卡决定/证据归属、v3包校验后才返回；无候选标coverage_gap，取消不调用模型，disabled不回退模拟，非法提案仅重试一次。公开投影保留作者、采用主张/原理、圆桌、行动及续聊；私有原包不被裁剪操作改写。尚无公开答案路由和发布事务，不能把函数返回当用户已收到正式答案。
- 首次测试命令因顶层namespace tests与server/tests同名而导入失败，改为顶层测试通过server.ai命名空间导入；随后取得预期缺模块RED。最初21项通过后增加无候选/disabled反例，发现原v3明确要求非空采用依据，不能把coverage_gap包装成空正式答案。已将无候选作为独立结果返回packet/draft=null，并不调用模型；未放宽原schema。最终新接缝7项+原采用16项 **23/23通过1.836秒**；入口8项通过0.402秒。仅自编提案，不是实际模型建议深度验收；本批token独立计量不可得。

### WP06-B/WP07任务执行和多消息入口（2026-09-08）

- 新增`runs/queue.py`的claim/heartbeat/finish_failure/publish_question/list_events，使用User→Problem→Job短事务锁序与每次新租约UUID；最多检查20候选、30秒租约、整体deadline不延长。过期输入/撤权/取消/耗尽尝试不能覆盖当前结果。成功发布才同事务推进core_state、processed_message_sequence、产品revision、助手消息和真实question_ready事件。JobEvent公开负载只含job_id/run_id/stage，带RLS及同owner FK；不是SSE接口已完成。
- `ai/intake_service.py`保持原advance_intake API，新增advance_messages，逐条原话/意图对应user_update，合并后仅一个ask或prepare。明确直接分析意图不会被随后补充撤销；第五轮限制保留。8项测试通过0.429秒，原core不改。模型提案测试是自编输入，不替代真实建议质量评估。
- 新增`ai/provider.py`：项目设置控制chat-completions JSON端点；仅local回环或明确openai-compatible HTTPS配置，拒绝demo自动回退，不接受普通用户地址/key；HTTPX不使用环境代理、不跟随重定向、不自动重试，有整体取消/截止点和有界载荷。只向独立产品venv补httpx0.28.1及5包合计（httpx/anyio/certifi/httpcore/idna），20条锁定依赖与实际版本逐项一致，pip check通过。5项真实回环HTTP测试通过35.481秒，包括实际usage/未知null、重定向拒绝、取消与超时；没有调用外部供应商。异常输出后的usage持久账尚未接通，不能据端口字段宣称完成计费。
- 新增`runs/worker.py`和`manage.py runworker`：领取任务后事务外整理，独立连接续租线程每5秒检查，旧租约无法发布；未配置模型明确failed MODEL_UNAVAILABLE，不生成假消息。prepare仍返回ANALYSIS_UNAVAILABLE，因为正式答案适配尚未接上；不会把检索准备当已回答。命令对非disabled配置暂拒绝执行，等待逐调用账/配额及完整答案接齐；底层provider本批仅供协议联调。
- 实现者前11项队列真实PG通过0.718秒，随后3项由父代理合批。父代理55项中54通过、1项历史迁移测试误用当前模型访问回退后的旧字段；该类问题按职责纠正为使用migration project_state历史模型，而非继续加当前字段兼容补丁。修补首次误匹配了测试另一处create，发现后立即还原并在精确迁移上下文修复。另新增真实追问后撤权反例，修正Problem DTO把pending_question置null，不只依赖前端隐藏。最终受影响执行器/问题存储/队列 **28/28通过1.859秒**；非此28项未声称修后重复全跑。
- 测试覆盖真实旧核心→追问发布、连续两消息只发布一次且消费游标为2、失效旧run不丢原文、disabled失败无假助手、prepare不伪装答案、queued取消仅一次事件、原令牌不能改写新尝试。无真实多worker进程压力测试或完整答案效果验收。
- 两条新迁移已在授权`sb_product`执行：problems0006消费游标、runs0002事件；runtime回验JobEvent FORCE RLS=true，受限一次worker命令输出“当前没有可执行任务”。没有向主库插测试用户/书籍或开启模型；固定测试库已销毁。下一批优先补用量/预算与正式答案适配、对话UI，保持完整产品目标。

### WP05-B/WP06-A消息、任务与集中联调（2026-09-08）

- 新增Message及problems0003–0005迁移；新增runs模型/服务/迁移/HTTP/公开serializer/contracts，局部接settings/urls/合并契约并生成web类型。实际新增5路径6操作。用户原文与intent、client_message_id、固定输入core_state/授权快照同事务保存；expected_revision冲突无半写，同键/同客户端消息ID重放无重复任务。core事件未执行前不更新，不产生假助手消息。
- `access.services.analysis_snapshot`通过原许可检查额外要求整版本analyze覆盖，browse用途不自动提升；原书房调用接口默认仍browse。三项真实PG通过0.100秒。私有消息/任务三表最小DML、FORCE RLS与同owner/父域/版本复合外键由迁移提供，测试runner不再补授problems/runs权限。
- 实现者6项真实PG通过；父代理集中70项中69项通过、1项实际HTTP契约失败：可空outcome返回null，通用生成器只改type却未给enum加入null。局部修复`accounts/contracts.py`两行（仅allow_null枚举），不改账号字段/认证逻辑；增加null与非法outcome反例。随后实际消息HTTP+新任务输入/契约+旧账号契约 **17/17通过1.167秒**，固定测试库销毁。该表述不是“修后70项全量重跑”。
- 实际CSRF登录验证：创建问题→发送原文→同键重放/异体409→GET run/job为queued→消息读回→queued取消200 cancelled；B不能读A对象；20,000中文字符消息成功，超限/伪owner/布尔修订/缺CSRF拒绝；直接分析保存明确按钮意图，撤权保留本人原文而拒绝任务内容。没有真实模型请求、worker或SSE，不把HTTP排队验收当问答完成。
- 无DB旧账号/知识/问题与新任务契约22项通过0.098秒；生成类型与typecheck通过。makemigrations --check显示No changes detected，tests.settings故意断开的DB地址产生连接警告，不能视为主库迁移历史已验证；之后实际迁移连接执行四条新迁移全部OK，并用runtime核验三表FORCE RLS=true。
- 已授权主开发库完成三表建表，没有导入自编测试账号、正式书籍、模型密钥或额外依赖。旧迁移测试finally改为恢复当前leaf，避免验完旧0002后把新表留在回退状态；旧契约仅更新真实路径数/新增消息存在断言。
- 本机API已受控重启加载新代码；实际经5173代理health为200、消息/run/job匿名均401，路由生效且未开放匿名访问。原src/prompts/schemas/examples无diff，固定五类效果题SHA256仍为`32fc53e3518087f983e1ee13a629c9cc2ab5c6bd3fa5ad0a7ffd737c0a4e51bf`；实际契约--check通过。
- 下一步直接接实际worker/受限模型传输、消息消费与结果发布，并接对话页面；多条尚未处理消息必须按顺序并入核心，不能只取最后一条导致背景丢失。token本批独立计量不可得，未提交/推送。

### WP10-B问题工作台与WP07入口接缝（2026-09-08，集中一次验收）

- 新增`web/src/features/problems/ProblemPage.tsx`、`ProblemViews.tsx`、`styles/problems.css`与12项流程测试；局部接`ProductApp.tsx`三路由、账号与书房导航。未改旧核心、原提示词、依赖或发布状态。页面复用实际问题API，不提供假消息、假模型进度或假答案。
- 实际改动接线：新增`/app/problems`、`/app/problems/new`、`/app/problems/:id`；`createProblem`保留用户原文和显式幂等键；`updateProblem`发送已读`expected_revision`。名称160字符、原文4000 Unicode字符与后端一致，冲突保留编辑且由用户手动重读后再保存。
- 集中前端 **77/77通过6.73秒**；typecheck随build通过，生产构建JS329.39kB/gzip100.17kB、CSS20.10kB/gzip4.45kB。开发API已受控重启，5173代理实际问题接口匿名401，说明新路由已加载；401不代替已登录验收。
- 真实浏览器使用独立`test_sb_product`、真实ASGI和构建产物：A实际登录→创建包含换行的问题→改名→归档（修订2）→恢复→列表显示修订3；原问题呈现保持不变。A退出、B登录后问题列表为0。使用自编账号与知识，未导入真实书籍或主库测试数据。旧revision/幂等/跨用户详情的反例沿用已通过的实际HTTP与前端测试，不再重复另派两轮审查。
- 临时8020测试进程已精确关闭，退出成功打印`Isolated problem test database cleaned.`。只清理本批临时测试库与数据，无用户正式内容被删除；正常5173/8019开发服务保留。
- 新增`server/ai/ports.py`、`intake_service.py`：Provider协议、取消/有界截止时间交接、结构化提案验证、调用元数据回调；原消息与明确意图由服务端绑定，提案进入原`append_event`/`compile_request`，原Grilling参考只读使用，保留五轮上限和直接分析意图。**6/6测试通过0.374秒**，是自编提案驱动真实核心，不是实际模型效果测试；没有模型网络传输、消息持久化、worker或自动分析结果。
- token计量本批不可得，不估算。下一批优先消息保存→任务→追问/分析结果的完整纵向链路；非阻断样式与文档细节集中后置。

### WP05-A问题草稿与实际HTTP（2026-09-08，按用户要求批量推进）

- 实现者负责`problems/models.py`、`services.py`、两条迁移与存储测试；父代理并行`http.py`、`serializers.py`、`views.py`、`contracts.py`及HTTP流程。没有逐模块另派双审，合并测试后继续接页面，不把“未做双审”写成已通过双审。
- 四个实际操作：POST/GET `/api/v1/problems`、GET/PATCH `/api/v1/problems/:id`。创建只调用现有`create_problem`保存原文和核心快照，绝不调用模型；产品revision与核心轮数分离。同幂等键同体重放、异体409，撤权后重放404；本人原问题仍可读但`library_available=false`。
- 输入先验证session与CSRF；原问题4000 Unicode字符原样保留。发现原全局8KB上限挡住中文长问题，局部提高全局到256KB，账号`read_input`独立8KB保持；真实HTTP确认9000字节账号写请求仍400。重复JSON键、未知owner/core字段与非整数revision拒绝。普通首屏空cursor已与现有前端契约对齐。
- 新增`server/tests/test_problem_store.py`、`test_problem_http.py`、`test_problem_contract.py`、`test_problem_flow.py`；只局部调整旧知识契约路径总数14→16，逐字段旧账号/知识对照保持。实际生成OpenAPI和web类型，新增两个路径四操作；消息与run接口未虚报存在。
- 实现者11项真实runtime PG通过0.469秒；父代理真实CSRF登录HTTP初跑3项通过，另1项测试准备违反已有撤权时间约束（未改生产约束，补测试revoked_at）。随后问题存储/输入/契约/实际流程+旧账号/知识契约/环境合批 **49/49通过1.925秒**，固定测试库已销毁。覆盖创建、重放、读取、改名、陈旧修订拒绝、归档恢复、A/B越权、撤权保留本人原文、输入限制；没有线程并发压力测试，不能把串行重复/陈旧revision测试称为并发容量验收。
- 两表`problems_problem`、`problems_idempotencyrecord`及RLS已迁移到本项目`sb_product`。迁移前核对runtime身份与test库不存在，配置保留`SB_RUNTIME_DB_ROLE=sb_runtime`后仅切migrator执行；迁移后runtime只读回验两表RLS=true、无owner上下文行数0。没有导入真实用户/书籍或修改现有表数据。
- 新增前端`api/problems.ts`及测试，复用生成类型、白名单解码；`api/client.ts`只新增显式POST幂等头，不自动重发或生成重试键。客户端相关8项通过、typecheck通过。提问/档案页面尚未接通，是紧接着的工作，不能把API适配器当成可用对话界面。
- 本批前端集中收尾 **65/65通过6.47秒**，typecheck/build/check:api均通过，JS309.00kB/gzip95.61kB、CSS17.27kB/gzip4.05kB。没有另派重复审查；普通开发API尚需在下一次页面联调前受控重启加载新路由，测试客户端成功不等于原常驻进程自动热更新。
- 原src/prompts/schemas/examples无diff，固定五类效果题SHA256仍为`32fc53e3518087f983e1ee13a629c9cc2ab5c6bd3fa5ad0a7ffd737c0a4e51bf`。未购买、调用真实模型、公开部署、提交或推送；本段独立token计量不可得。

### WP10-A书房只读闭环（2026-09-08）

- 新增`web/src/api/knowledge.ts`及测试、`features/library/LibraryPage.tsx`、`LibraryViews.tsx`、`styles/library.css`、`LibraryFlow.test.tsx`；局部修改客户端超时选项、`ProductApp.tsx`路由、账号导航与对应测试。没有新依赖、数据库迁移或旧核心改动。
- 六个GET使用生成类型与运行时公开字段校验；仅知识请求45秒有界等待，认证仍默认10秒。超时调整不代表解决真实165本库26.926秒完整校验瓶颈。
- 页面显示真实书名/作者、完整原理、条件、边界、步骤、应用说明及关系依据；未知作者/原理缺口不猜补。来源为获准连续短引，标注截断与字符位置，不能换算成未知页码。关联与本次采用明确区分。
- 独立规格审查发现来源重读缺少原书ID比较；新增同release/evidence却换book的反例先失败，补`expectedBookId`比较后通过。质量审查发现分页与来源正例只断言请求、不等最终内容；补正确跨版本fixture与最终呈现断言后，定向2/2通过1.78秒。两项审查最终PASS，无未处理Critical/Important/Minor。
- 父代理前端整批 **63/63通过6.72秒**；质量审查独立63/63通过6.59秒。随后仅加强已有两项测试，实现者阅读/认证38项通过，审查者上述2项通过。typecheck/build/check:api通过；最终生产产物JS308.84kB/gzip95.55kB，CSS17.27kB/gzip4.05kB。
- 真实浏览器使用构建产物、Django ASGI与独立`test_sb_product`，不是mock接口：A登录→书架→书籍→方法卡→原文；桌面1280与390窄屏无横向溢出；作者/书名/类型/关键词联合筛选；真实撤销A授权后清空旧卡片及原文；A退出换B只见B版本、直接访问A卡被拒。最终构建B来源重读成功且书籍归属不变。未完成的1440/768/200%缩放/深色全套验收仍归WP14，不能据两种尺寸标AT19全过。
- 临时8020服务已关闭，退出输出`Isolated browser test database cleaned.`。父代理只读复核主库身份为`sb_product/sb_runtime`，用户/邀请/session/release均0，`test_sb_product`残留0。没有向主库塞测试账号、发布真实书籍或使用模型。
- 功能仍为只读：没有假收藏/学习/分析按钮，不用自编材料证明真实书质量。前端无私有内容持久缓存，隐藏/恢复重新鉴权，晚响应丢弃，401/404清空私有树。
- 本段独立token计量不可得，不估算。下一批按已确认清单进入问题档案与对话接入；原书、src、prompts与固定效果题继续保留。

关键生产补丁：

```diff
+ <Route path="/app/library" ... />
+ <Route path="/app/library/:release/books/:book" ... />
+ <Route path="/app/library/:release/cards/:card" ... />
+ <ReloadedSource ... expectedBookId={source.book.id} />
+ if (source.book.id !== expectedBookId) throw new ApiFailure('INVALID_RESPONSE');
```

以上路由片段省略组件属性，仅说明接线位置；完整实际新增源码须直接阅读，不用未跟踪文件的空git diff当成“没有改动”。

### WP04-B整批验收（2026-09-08 15:35）

- 提速方式：授权仓库、HTTP、DTO与契约合为一批审查；实现agent负责仓库与PG夹具，父代理并行HTTP/契约/生成类型。开发跑相关测试，收尾一次全量；PG始终独占串行，不缩减关键反例。
- 加载器、启动接缝两轮独立审查均PASS；入口2项+加载器16项无需临时PYTHONPATH即可通过。上方“质量复核进行中”为该小段当时记录。
- 实现者仓库14项PG通过0.636秒；父代理整批 **124/124通过11.193秒**（原80+loader16+startup2+HTTP4+契约4+仓库14+真实登录HTTP4），测试库销毁。整批独立规格及质量均PASS；质量审查另跑无DB19项0.054秒及生成类型check通过，无Critical/Important。
- 六个端点通过真实Django CSRF/login建立会话后，逐字段核对200响应与OpenAPI；A/B越权、游标篡改/跨用户/查询变化、到期与无quote分别拒绝。不是只靠mock或匿名请求验收。
- web **35/35通过7.14秒**，typecheck/build/生成类型检查通过；JS277.06kB/gzip87.87kB，CSS10.34kB/gzip2.81kB。生成类型不增加页面功能，书房UI仍未接入。
- 本机旧PID不存在且8019/5173均无人监听，确认后恢复仅127.0.0.1的前后端。实际网络回读 **12/12通过**：首页/注册/health/公开能力200、六知识接口匿名401、未实现runs404，no-store/request-id一致。不将匿名网络检查代替已登录测试库验收。
- 主库仍sb_product/sb_runtime，用户/邀请/会话/release均0，test_sb_product残留0。本段无主库业务记录或DDL写入，没有自动给真实书赋予许可。
- 原src/prompts/schemas/examples/固定五类题无diff，固定题SHA256未变；旧底座125项通过7.381秒。pip check无依赖冲突，沙箱pip缓存权限警告仅禁用缓存，未修改系统权限。
- 非阻断性能维护：card_summary逐卡重建书目字典，批量摘要有O(卡数×书数)重复工作。后续实际书库规模验收时可在单次请求内复用映射，不引入授权或跨请求缓存；当前正确性通过不代表完成性能容量验收。

整批复跑（项目根目录，禁止并行PG）：

```sh
PATH=/opt/homebrew/opt/postgresql@16/bin:$PATH .venv-product/bin/python server/manage.py test tests.test_environment tests.test_health tests.test_accounts tests.test_sessions tests.test_accounts_bootstrap tests.test_auth_contract tests.test_auth_contract_integration tests.test_rls_context tests.test_knowledge_models tests.test_knowledge_database tests.test_release_loader tests.test_startup_import tests.test_knowledge_http tests.test_knowledge_contract tests.test_library_access tests.test_library_http --settings=tests.integration_settings --noinput
```

### WP04-B请求内投影提速与真实规模测量（2026-09-08 15:52）

本段继续已确认的仓库、测试与进度文档范围，不扩展为下一阶段配置授权。六项影响：职责仍是repository/projections；manifest仍为书目事实源；server→core依赖不变；公开DTO完整相等及真实授权回归为验收接缝；只移除单次请求内重复建表，不保存任何跨请求内容或权限缓存；无DDL/数据迁移，回退仅恢复三个内部调用处。

- 局部修改：`server/knowledge/projections.py`的`card_summary(card, book, release_id)`直接使用对应书目，详情调用同步；`server/knowledge/repository.py`列表复用已有`books`。每卡仍调用`book_payload`校验并产生独立公开字典。没有修改加载器、授权检查、HTTP、原书、旧核心、提示词或固定题。
- 新增`server/tests/test_knowledge_projection.py`五项无DB测试。RED实测1/64/256卡分别重复扫描书目2/65/257次，三个subTest失败；GREEN同规模均为1次。完整JSON、未知作者、嵌套对象独立、同ID后续请求新元数据及非法元数据均有检查。`_read`只在这些投影测试中隔离，不用它们证明授权。
- 独立规格与代码质量审查均PASS，分别复跑五项测试0.002秒。父代理整批 **129/129通过9.685秒**，命令为上方124项命令追加`tests.test_knowledge_projection`。测试库已销毁；只读复核主库用户/邀请/会话/release仍全0。前端代码与契约未改，本段不重复宣称前端新增功能。
- 同输入性能对照：150本自编内存材料、15,000卡，前后各7次，只测实际`list_cards`的投影闭包，不含数据库、磁盘或HTTP。中位数 **60.241ms→10.569ms**；完整结果规范JSON的SHA256前后均为`6cae4477f235a751c9cae811f9d09099107c0a79c972be358511f55ff0454389`。这是局部实验，不代表整站提速倍数，也不证明真实书籍语义质量。
- 真实规模只读测量：`data/jobs/library-165-candidate-v3`有165本、7,075卡、15,884证据、4,913关系；完整指纹`0cbf07974c2da8cb4f8b68717e9b459fc9cbbb3b1348e24b7d1fade730691f86`。调用真实受控`load_release`并保留全部旧核心校验，**26.926秒，通过**；这是一次本机测量，不是P95容量结论。manifest仍为`evaluation_candidate`，没有发布、导入产品主库或赋予版权许可。
- 为确认瓶颈另跑一次只读cProfile（插桩40.762秒，不能与普通延迟混用）：`verify_span`15,884次累计19.449秒；旧核心`content_version`2次累计7.675秒，外层完整`_fingerprint`2次5.772秒；`read_bytes`91,849次累计6.154秒。累积时间相互嵌套，不能相加。代码显示每条证据均重新哈希来源全文；小投影优化不能解决整库重复校验。
- 下一阶段待设计/授权：比较“同一不可变来源只计算一次指纹、每条仍核对字符锚点”与“发布后固定版本的已验证读取产物”的实现边界，保留实时授权/撤权及内容变更检测。不以模块级monkeypatch、只看mtime或关闭验证换速度，也未静默修改旧核心。书房UI与真实发布仍未完成。
- 耗时使用实际命令输出；本段token消费没有独立可核验计量，不估算。原固定五类题SHA256仍为`32fc53e3518087f983e1ee13a629c9cc2ab5c6bd3fa5ad0a7ffd737c0a4e51bf`。

本段实际生产补丁（其他生产内容原样保留）：

```diff
-def card_summary(card, library, release_id):
+def card_summary(card, book, release_id):
-            'book': book_payload(books_by_id(library)[card['book_id']]),
+            'book': book_payload(book),
-    result = card_summary(card, library, snapshot['release']['id'])
+    result = card_summary(card, books_by_id(library)[card['book_id']], snapshot['release']['id'])
-                    'items': [card_summary(card, library, snapshot['release']['id']) for card in cards]}
+                    'items': [card_summary(card, books[card['book_id']], snapshot['release']['id']) for card in cards]}
```

### 前序历史记录

| 时间/范围 | 实际命令或检查 | 结果与边界 |
| --- | --- | --- |
| 工程扩展前 | `.venv-mvp/bin/python -m unittest discover -s tests -p 'test_*.py'` | 98项通过；底座基线，不是产品通过 |
| 10:03，新增fixture前 | 同上 | 119项通过，含21项runtime测试；ONNX遥测设备ID落盘受限，使用内存后测试通过 |
| server骨架 | `.venv-product/bin/python server/manage.py test tests.test_environment tests.test_health --settings=tests.settings --noinput -v 1` | 17项通过；使用驱动边界替身，真实连通另测；尚不能承诺无参数统一test命令 |
| runtime规格与质量 | 独立读取实现、21项测试与隔离临时目录反例 | 均通过，有两项非阻断维护问题，见下文 |
| 本机HTTP | `/health/live`、`/health/ready`、web首页、代理ready、`/src/main.tsx` | 均200；仅输出状态码/长度，不输出秘密 |
| 开发文件访问 | web下`/@fs/`访问项目私有env与prompt | 均403；未输出文件内容；不代表全站安全通过 |
| 真实浏览器 | 打开5173页面 | 显示前端/后端/数据库连通，重新检查按钮存在；不是登录或AI通过 |
| 10:10，中文路径修复 | `npm --prefix web test -- --run src/dev-boundary.test.ts` | 修复前1失败1通过：合法web文件被误拒绝；修复后通过 |
| 中文路径修复后 | `npm --prefix web test -- --run`；`run typecheck`；`run build` | 5项通过，类型与构建通过；独立规格复核通过 |
| 10:12，自编材料 | `.venv-mvp/bin/python -m unittest tests.test_product_fixtures -v` | 6项通过；真实Library、字符锚点、关键词检索、intake重放，无mock授权结论 |
| 10:14，加入fixture后 | `.venv-mvp/bin/python -m unittest discover -s tests -p 'test_*.py'` | 125项通过，4.727秒；此前119项加6项材料测试；ONNX遥测落盘受限警告仍在 |
| 修复后实际HTTP | 首页、ready、web内package.json、web外env与prompt | 前三者200，后两者403；不只依靠静态白名单测试 |
| 文档链接 | 只读核验本轮5个文档的相对链接 | 20个链接均可解析，无失效链接 |
| 受保护范围 | `git diff --exit-code HEAD -- src prompts schemas examples tests/call-v2-effect-suite.json` | 无差异；未改原调用核心、规则、示例或固定题 |
| 10:40，web复验 | 5项测试、typecheck、build | 均通过；页面HTTP200 |
| 10:42，底座复验 | `.venv-mvp/bin/python -m unittest discover -s tests -p 'test_*.py'` | 125项通过，4.987秒；未修改旧核心与固定五类题 |
| WP03-A父代理独立复验 | `.venv-product/bin/python server/manage.py test tests.test_accounts tests.test_sessions tests.test_accounts_bootstrap tests.test_environment tests.test_health --settings=tests.integration_settings -v 1` | 38项通过，3.690秒；独立PG测试库、运行角色HTTP/ORM，测试库已销毁；不是完整产品验收 |
| WP03-A主库只读复核 | 实例身份、角色权限、pg_tables与账号/会话计数 | sb_product，sb_runtime无super/CREATEDB/CREATEROLE/BYPASSRLS；12表均归sb_migrator；账号0、会话0、test_sb_product残留0 |
| WP03-A返修后父代理独立复验 | 同上完整PG测试命令 | 最终48项通过，6.715秒；较38项增加身份恢复/错误契约/不同邀请竞态等10项；测试库已销毁 |
| WP03-A迁移一致性 | `makemigrations --check --dry-run` | No changes detected；只读，不生成文件 |
| API重启后的真实HTTP | 经5173代理验证首页/ready/csrf、匿名me、错误方法、未知路由、缺CSRF、合法CSRF错误输入、匿名退出、跨域拒绝 | 10项通过；分别200/200/200/401/405/404/403/400/204/403；检查no-store、嵌套error及request_id一致；不创建真实用户或发送邮件 |
| 最终主库只读复核 | accounts.0004、触发器、函数归属与角色/计数 | 触发器启用，函数SECURITY INVOKER且属sb_migrator；runtime仍低权；用户0、session0、测试库残留0；私有env和DB配置仍被git忽略 |
| 11:35，认证契约父代理复验 | 旧48 + 契约新增13，显式tests.integration_settings | 61项通过7.413秒，固定测试库已销毁；两位独立规格/质量审查通过 |
| 11:44，授权事务上下文 | `test_rls_context`，实际runtime PG | 5项通过0.003秒，含A→空→B同连接、回滚、拒绝跨身份与手动外部事务；不代表业务表RLS已完成 |
| 11:50，真实浏览器账号闭环 | 临时本机邀请→页面注册→登录→独立browser context→退出 | 实际注册201、注册后me401、登录后me200、独立上下文me401、退出后me401；只删除本次临时邀请/账号/同意记录，未输出密码令牌；不验证书库授权 |
| 11:57，前端最终复验 | `npm --prefix web test -- --run`；`run build`；`run check:api`；后端`export_auth_contract --check` | 35项通过9.24秒、类型检查和生产构建通过；JS277.06kB/gzip87.87kB，CSS10.34kB/gzip2.81kB；生成类型一致；组件独立规格/质量PASS |
| 浏览器布局与生命周期 | 1440桌面、390移动、深色移动；实际HTTP；触发pagehide/pageshow | 无横向溢出或页面脚本错误；失败后清密码、隐藏后清密码/邀请码、恢复重读政策并清同意均实测通过。此事件测试不等于所有浏览器BFCache兼容性认证 |
| 12:00，浏览器键盘 | 等待React标题实际出现后Tab→跳转主要内容→Enter→Tab | 首个焦点为跳转链接，其后到邮箱输入框；初次未等待React的探针落在body，不计通过 |
| 12:05，原底座复验 | `.venv-mvp/bin/python -m unittest discover -s tests -p 'test_*.py'` | 125项通过10.732秒；ONNX遥测持久化受限，退回内存的既有警告仍在；固定效果题指纹未变 |
| 前端分发与文档 | 构建目录限定敏感标识/绝对路径扫描、私有env HTTP访问、Markdown链接 | 限定标识扫描无命中、env访问403、24个本地链接均可解析；不是完整秘密扫描或安全认证 |

固定五类题SHA256：`32fc53e3518087f983e1ee13a629c9cc2ab5c6bd3fa5ad0a7ffd737c0a4e51bf`。状态仍为`rework_required`，未因新工程测试通过而修改。

## 已知问题和后续接缝

2026-09-08 12:20补充：

- 父代理独立复跑80/80项通过，6.853秒：旧61项、上下文5项、模型3项、数据库11项。实现者另跑80项6.832秒；独立规格与质量审查均PASS。固定测试库已销毁。
- 主库仅向前应用knowledge.0001/0002。只读复核sb_product共19表，新7表归sb_migrator，sb_runtime七表仅SELECT，grant ENABLE+FORCE RLS且两条角色策略存在；用户/邀请/会话均0、测试库残留0。无原书导入或真实版权授权声明。
- 后端以不含迁移连接环境变量的运行环境受控重启，5173代理9项HTTP检查符合预期：首页/注册/账号SPA、live/ready、options/csrf均200，匿名me401，尚未开放libraries404。SPA状态200不代表获得私有内容。
- 测试须显式列服务端模块：裸`test tests`会收集根目录旧测试，并在身份核验处拒绝执行，不能作为统一入口。WP02仍需修正这一接缝。
- 数据库子段只隔离grant行及知识表写权限，其余知识表供受信任后端读取；不能据此宣称完整知识授权已完成。下一段须在加载前校验grant、release、rights、到期，并严格投影公开字段。产品venv缺核心校验所需jsonschema；补装锁定依赖与只读查询接缝已另列清单待确认，不绕过核心校验。

从项目根目录串行复跑本子段（禁止并行PG测试）：

```sh
PATH=/opt/homebrew/opt/postgresql@16/bin:$PATH .venv-product/bin/python server/manage.py test tests.test_environment tests.test_health tests.test_accounts tests.test_sessions tests.test_accounts_bootstrap tests.test_auth_contract tests.test_auth_contract_integration tests.test_rls_context tests.test_knowledge_models tests.test_knowledge_database --settings=tests.integration_settings --noinput
```

主库迁移先用runtime环境构建设置保留`SB_RUNTIME_DB_ROLE=sb_runtime`，再仅替换迁移进程的数据库连接为sb_migrator，不能先替换运行连接再派生角色。本次主库无DROP/flush；0002回退撤权与保留记录、宽权限注入后重新收紧仅在独立测试库演练。

1. Vite中文路径：`.pathname`保留URL编码导致合法文件误拒绝；已用`fileURLToPath`局部修复，保留web外拒绝测试。规格与质量复核通过；质量评审建议以后补HTTP错误、超时/卸载/重试的组件回归，当前源码未发现对应缺陷。
2. runtime测试依赖本机PG工具定位及Homebrew路径，换环境可能在错误的分支提前失败；需局部改进测试隔离，不影响本机已验证结果，但不得据此宣称跨平台通过。
3. 初始化两份私有配置的第二次写入失败会留下半初始化状态；当前保守拒绝覆盖，需补恢复诊断，不自动删除或重置凭据。
4. 原`project_check.py --schemas`发现本工作树缺`configs/local.json`、vendor版本核对未通过。进一步只读定位：`git -C vendor/cangjie rev-parse --show-toplevel HEAD`实际返回父项目根目录及`e74bf5f`，当前检查读到了父仓库commit，不能据此断言vendor内容偏离锁定版本。vendor实际内容版本仍未证明，后续应校验明确边界与锁定源；本轮不改工具、锁或上游文件。此前sample校验通过，真实效果阶段不能绕过本机库配置缺口。
5. 账号实现先确定自定义User再迁移；运行进程不能使用迁移角色。实际RLS和对象归属留在对应业务迁移与双用户测试中验证。
6. 自编材料质量审查通过但建议补必需场景ID集合/唯一性、persona数组基数及release UUID唯一性断言，防止未来误删场景被循环测试掩盖。当前材料内容均存在且唯一；后续补防退化检查，不当成真实权限已通过。
7. WP03-A采用accounts.User、Invitation、PolicyAcceptance、AuthThrottle与Django数据库session，三条accounts迁移；概念数据字典的设备/多用途token/MFA/capabilities映射留后续子段。当前只允许接受local-test-2026-09-08版本，生产注册503，未验证邮箱保持null；没有发邮件。管理员MFA未实现时拒绝建立或恢复完整会话，不提供临时绕过。
8. 对照06接口契约发现logout-all遗漏再次认证，已按原契约补password输入、缺失400/错误401、正确204及双客户端撤销回归。原会话在失败认证后保持有效。审查未完成前不把接口测试通过写成最终通过。
9. 独立规格审查提出的旧cookie复活和错误契约问题已修复并复审SPEC_PASS：表级触发器覆盖save/QuerySet.update/原生SQL，停用期间未访问的第二客户端恢复后仍401；嵌套error、AUTH_REQUIRED、404 NOT_FOUND、405 METHOD_NOT_ALLOWED与Allow均已对齐。38项是历史记录，最终48项才包括新增反例。
10. 质量审查提出不同邀请同邮箱竞态：旧实现可能在full_clean抛500；已用两条真实事务确定性复现，并改为由DB原子判定唯一性，仅将两个已知邮箱唯一约束映射409，其他IntegrityError仍抛出。新增测试确认只创建一个用户、一次政策接受及消费一个邀请；质量复审无Critical/Important，父代理48项复验通过，WP03-A记QUALITY_PASS。
11. 非阻断容量维护：AuthThrottle尚无到期行清理，随机邮箱会积累记录；未来公开部署前需结合清理任务与真实反向代理来源边界处理。当前`--no-proxy-headers`只信直接来源，避免本机伪造XFF；不能直接照搬为未配置可信代理的公网容量方案。
12. 登录门面独立审查关闭两个实质问题：响应字符长度改为Unicode码点（80 emoji合法昵称不再误拒）；登录/注册pagehide及hidden清敏感数据并取消请求，注册恢复重读政策。新增回归均先失败再通过。质量审查剩一项非阻断测试建议：账号页进一步补hidden→visible与挂起readMe迟到结果的组合测试；现实现已有abort防护，当前测试覆盖pagehide→pageshow。

## 时间、用量和授权

认证接缝补充证据（北京时间11:35）：实现者61项测试通过17.759秒；父代理独立串行复验同一61项通过7.413秒并销毁`test_sb_product`。两位独立审查者分别完成规格/质量审查及11项无DB测试、OpenAPI `--check`，无阻断项。新增13项覆盖公开能力、配置一致性、全部成功响应、旧政策拒绝；不是完整产品验收。前端传输/解码/跳转当前16项通过，类型检查通过，登录页面尚在接入。

类型生成工具采用[openapi-typescript官方本地CLI](https://openapi-ts.dev/cli)。7.13.0的TypeScript peer为5.x，与web已锁7.0.2冲突；未强制安装或降级web，局部新增独立`tools/api-types`并锁TypeScript5.9.3。web增加Testing Library/jsdom组件测试依赖；两套安装当时分别报告0漏洞，仅代表该次依赖审计结果，不等于产品安全通过。

本表仅记录实际可观察的测试时间与结果，不估算全产品完成百分比。产品模型调用为0次（disabled）；开发Agent token的按工作包精确分摊 unavailable，不能用产品模型usage代替。最终耗时应从实际工作记录汇总，不能把测试耗时当全部开发耗时。

2026-09-08用户明确确认下一阶段清单：修正Vite路径并补测试；新增账号/会话/邀请注册及测试，局部接入server配置和路由，仅对本项目开发库建表；补正进度文档。原书、现有调用核心、提示词不改，不购买、不公开部署、不推送。超出这份清单的配置/文档变更继续按工作区规则处理。

### 第二阶段已确认清单与实施接缝

用户再次明确回复“按清单连续执行”：新增正式登录/邀请注册界面并保留联调页；接已验收账号API并补测试，必要时局部调整web测试配置；新增知识版本、用户授权与隔离测试，局部接入server配置/路由，仅迁移本项目开发库；更新进度、接口和字段映射。不购买、不公开部署、不提交或推送；原书、旧核心与提示词保持不动。

本阶段执行顺序：账号公开能力与OpenAPI/生成类型接缝 → 登录/注册和已登录入口 → 知识权限仓库/RLS → 真实浏览器及串行PG复验。尚未实现的产品功能不摆放假成功入口。

六项影响检查：

1. 职责：accounts负责真实身份与可用认证能力；前端auth只收集输入和展示响应；knowledge/access在核心加载前鉴权。
2. 事实源：账号与授权来自本机PG，认证能力/测试政策版本来自server；OpenAPI与前端类型从服务端契约导出；原书与固定知识目录只读。
3. 依赖：web只依赖公开HTTP契约；server包装src.Library，不能让src依赖Django或前端。
4. 接口测试：匿名公开能力、CSRF/登录/注册、失效会话、白名单/跳转/密码不落盘；A/B/C授权、同ID跨release、RLS上下文、撤权竞争、路径与DTO泄漏。
5. 变化隔离：新增auth页面、公开契约与知识适配器；现联调App保留独立开发入口；原src/prompts/schema和固定题不改。新依赖限本项目测试/类型生成工具，先核验官方版本并锁定，不动全局或旧venv。
6. 迁移回退：本段认证接缝无需数据迁移；WP04仅对本项目开发库做向前迁移；授权管理表不沿用测试runner的全表DML授权。主库不DROP/flush，不以应用回滚冒充数据回滚。

前置只读核查发现：核心Library可直接加载单个固定版本；SearchEngine初始化会读取该库全部卡片，所以必须先鉴权再加载。证据返回含绝对file/source_path，应严格公开投影。现测试runner对public全表授DML，新增grant/rights表时必须收紧；无有效grant不得自行写入授权。

## 本清单局部改动对照

WP04-A新增`server/knowledge/models.py`、两条迁移、`server/access/context.py`与三组测试。实际配置接缝新增`"SB_RUNTIME_DB_ROLE": database["USER"]`及knowledge app，保留既有配置。测试runner的权限授予逻辑由“public全表DML”改为“枚举表，仅非knowledge_表保留原DML”；迁移自身收回PUBLIC/runtime旧权限再只授SELECT，测试不能替它制造低权限假通过。新增文件尚未跟踪，需审查实际源码，不能只看tracked diff。原书及旧调用核心未改。

`web/src/main.tsx`只切换入口，原`App.tsx`保留给开发状态页；新增组件未被git跟踪，因此不能用空`git diff`说“没有改动”。

```diff
- import { App } from './App';
+ import { ProductApp } from './ProductApp';
- ReactDOM.createRoot(root).render(<React.StrictMode><App /></React.StrictMode>);
+ ReactDOM.createRoot(root).render(<React.StrictMode><ProductApp /></React.StrictMode>);
```

认证相关新增文件：`ProductApp.tsx`、`ProductApp.test.tsx`、`features/auth/{LoginPage,RegisterPage,AccountPage,shared,navigation}`及测试、`api/{client,auth,generated}`及测试、`styles/auth.css`。依赖与配置只增测试工具、生成命令及TSX测试收集；`.gitignore`另加`tools/api-types/node_modules/`避免提交生成工具依赖。`styles/tokens.css`、原连通`App.tsx`、原核心与原书保持不动。

`web/vite.config.ts`：新增Node标准库`fileURLToPath`导入，仅修正web目录白名单的路径解码，不扩大到项目根目录。

```diff
- allow: [new URL('.', import.meta.url).pathname]
+ allow: [fileURLToPath(new URL('.', import.meta.url))]
```

`server/accounts/http.py`：新增账号HTTP层在复审中对齐既有06契约，错误码不放到顶层。

```diff
- {"code": code, "message": message, "request_id": request_id}
+ {"error": {"code": code, "message": message, "request_id": request_id}}
```

会话恢复反例的修复是新增`accounts.0004`迁移，不重写旧迁移；`accounts_user`状态或管理身份改变时持久推进auth_epoch，禁止旧值回写使epoch倒退。新增测试保留原38项，并增加三种真实写入方式和闲置客户端反例。

账号创建的并发修复保留字段校验，移除可竞态的唯一性预检，以数据库约束作为唯一性事实源；只改变新账号代码，不更改原知识调用模块。

```diff
- user.full_clean()
+ user.full_clean(validate_unique=False, validate_constraints=False)
```

同时将注册处泛化的IntegrityError处理缩小到`accounts_user_email_key`和`account_email_case_unique`两个约束，未知数据库错误不伪装成邮箱冲突。

新增账号模型、输入校验、服务、HTTP适配、认证后端、迁移和测试均位于`server/`。配置只局部接入accounts、Django标准认证/session中间件、密码校验、限流与CSRF；urls登记实际实现的接口。原`src/`、`prompts/`、`schemas/`、`examples/`与固定五类效果题无diff；没有删除原内容。新增文件尚未被git跟踪，不用空的git diff掩盖这些新增文件。

## 馆员视觉准备（02:39 UTC / 北京时间10:39）

沿用已批准的产品视觉准备范围，使用内置图像生成能力生成第一版原创馆员，保存为[馆员概念图](../../assets/character/librarian-concept-v1.png)。原始生成文件保留；项目使用独立副本。不使用付费CLI或其他工具密钥。此图仅为二维外观参考，不是已建模的人物，不能拖动旋转，也不代表首页已完成。真正的可编辑模型、动作与无障碍降级仍待实现。

生成提示词（builtin imagegen；单次概念生成）：

> Use case: stylized-concept. Asset type: original librarian character concept for a modern Chinese knowledge-library product named Second Brain, to later be modeled as real editable 3D; this is a single 2D concept render, not a UI screenshot. Create one refined original androgynous young adult librarian character, approachable and thoughtful, short sculpted dark hair, simple round thin-frame glasses, forest-green overshirt over an off-white shirt, dark trousers and soft shoes, holding one small open unmarked book naturally at waist level. Tasteful stylized 3D sculpture, matte ceramic and soft fabric, restrained proportions (not oversized baby head), elegant clean silhouette with meaningful folds, natural warm skin tone. Full body entirely visible with generous clean margins, front three-quarter view, camera level around chest height, centered figure occupying about 70 percent of height. Plain pale green-gray studio backdrop matching #f4f6f2 with soft grounded contact shadow, gentle diffuse daylight. Clear separated arms and hands for future modeling, friendly relaxed expression. One character only, no furniture, no floating ornaments, no holograms, no text, no watermark, no logo, no readable book text, no recognizable existing fictional character or celebrity. Portrait 4:5 composition. Polished professional character-design presentation suitable for an adult learning product, not a children's game.
