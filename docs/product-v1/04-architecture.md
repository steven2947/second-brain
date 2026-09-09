# 技术架构与变化隔离

状态：拟实施。选择React/Vite/TypeScript前端、Django+REST接口/ASGI服务、PostgreSQL；不引入付费数据库或强制托管服务。选用支持中的稳定版本，安装前核对官方兼容矩阵、许可与安全公告，将精确版本锁入新产品依赖文件，不改旧 `.venv-mvp`。

## 六项影响检查

1. 职责：Web只展示与收集输入；server管身份/权限/数据/调度；src原领域模块管知识检索与验证。
2. 事实源：原书只读；知识版本不可变；问题事件与用户原消息是情境事实源；UI和缓存是派生物。
3. 依赖：server→src，不让src依赖Django或浏览器。前端只读公开DTO，不导入Python提示词或内部运行对象。
4. 接口：REST `/api/v1`、JSON DTO、可恢复SSE；适配现有intake/session/validation，不对外开放底层任意CLI。
5. 隔离：`web/`、`server/`、`deploy/`新增；旧CLI和schema保持历史兼容。新知识授权适配器单独测试。
6. 迁移回退：数据库有迁移历史；知识目录不随代码覆盖；固定版本答案保留。破坏性迁移另行确认，备份恢复演练后才执行。

## 运行拓扑

```text
浏览器 ──同源HTTPS── 静态前端与反向代理
                       │ /api/v1
                       ▼
                  Django ASGI API
                  │            │
          PostgreSQL任务表     私有授权文件访问
                  ▼            │
             Worker进程        │
             │      │          │
          模型适配器  现有知识调用底座
             │          │
        经配置的模型   只读固定知识版本+私有索引
```

部署为同一后端镜像的api/worker两个进程、PostgreSQL、静态代理；一台服务器即可起步，不等于已证明该服务器承载量。初期不加Redis、独立向量数据库或微服务网关。前端不直接连数据库或模型供应商。

## 模块分工

| 目录（待创建） | 职责 | 不负责 |
| --- | --- | --- |
| web/src/features | 页面与用户交互 | 认证可信判断、提示词拼装 |
| web/src/api | 类型化客户端、CSRF、错误与SSE恢复 | 自动猜用户归属 |
| server/config | 环境、URL、ASGI、日志配置 | 业务事实 |
| server/accounts | 自定义用户、邀请、登录、会话与找回 | 自制密码学 |
| server/access | 所有者检查、知识集授权、RLS上下文 | 让用户自己声明管理员 |
| server/problems | 档案、原消息、修订和事件事务 | 改旧来源 |
| server/runs | 队列、取消、租约、运行状态、幂等 | 未验证草稿直接发给用户 |
| server/knowledge | 获准知识集、版本解析、浏览投影 | 对外提供任意本地路径读取 |
| server/ai | 模型协议、intake/classifier、v3草稿生成、表达 | 让模型执行任意系统命令 |
| server/presenters | 内部包→公开DTO白名单 | 返回完整内部对象后让前端隐藏 |
| server/learning / actions | 练习、反馈、行动进度 | 用完成勾选证明知识正确 |
| server/operations | 配额、审计、数据删除/导出、健康检查 | 默认查看所有聊天内容 |
| deploy | 本地启动、生产示例、备份恢复、升级检查 | 替用户购买或部署 |

## 身份与数据库

使用Django成熟密码哈希与会话框架，显式补上对象级权限、登录限流、邀请和验证流程；框架自带账号不等于已实现多租户隔离。[Django官方身份说明](https://docs.djangoproject.com/en/5.2/topics/auth/)

同源Cookie会话；HttpOnly、生产Secure、SameSite=Lax；CSRF覆盖所有状态变化；退出/改密/禁用时撤销对应会话。注册建立owner，owner不允许通过API更换。

私有业务表显式owner_id与复合关联；应用过滤+PostgreSQL RLS双层检查。运行角色非superuser、非表owner、无BYPASSRLS；迁移角色单独保存。事务内设置用户上下文，缺失fail closed；连接池不得跨请求遗留上下文。RLS不是抵御已被攻陷后端的万能边界，仍须输入验证和最小权限。

## 知识访问与现有单库接口的适配

首版一次问题选一个知识集的固定release，它可包含多本书。**同一release内所有书具有同一访问范围**；不同范围不得混进同一release。不设计“先在全库检索，再把无权结果从页面过滤”。

server先校验用户对release的有效grant，再取得受控只读路径，建立现有Library。索引缓存键包含release指纹，用户查询/答案缓存还要包含owner和access_revision。逐书授权、同时联查多个独立release均属后续扩展，首版不伪装已实现。

原库来源字段不能直接发给浏览器；源定位通过服务端证据ID和受控摘要呈现。撤权提高access_revision、取消未完成任务、清理派生缓存与导出；历史答案的知识内容也重新校验访问。

## 可靠执行

任务入队与用户消息/幂等记录同事务。Worker短事务用 `SELECT ... FOR UPDATE SKIP LOCKED` 领任务并写租约，不跨模型HTTP请求持有数据库锁。心跳、租约到期回收、attempt计数和幂等发布避免重复答案；不保证第三方模型账单exactly-once。

SSE仅传已落库的阶段事件与验证后内容，断开连接不等于取消。取消单独POST；结果发布时再查用户/授权/修订与cancel标志。过期结果保留内部状态，不更新用户的“当前答案”。

## 运行模式

- `demo`：自编知识与确定性演示，明显标注，不允许计为真实AI效果验收。
- `local`：显式配置本机模型，满足本地资料边界；模型能力需实测，不能默认质量等同云模型。
- `provider`：管理员配置供应商、模型和密钥，数据出站范围在政策和UI明确；不从用户电脑现有私密配置中自动提取凭据。

没有可用模型时保留真实登录/书房/保存问题，分析返回配置缺口，不悄悄切到假数据。生产默认禁用demo自动回退。

配置值`disabled`表示有意未启用模型服务，与配置损坏区分；统一枚举为disabled/demo/local/provider，以10的环境配置契约为准。
