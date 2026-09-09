# 本地运行、部署交付与运维

状态：部署契约仍待WP-15逐条实机验证；`server/`和`web/`已在本地实现并运行，当前证据见PROGRESS及`server/README.md`，`deploy/`交付与完整恢复演练尚未完成。本文件下方拟定配置不覆盖已实现配置，不代表已公开部署或购买服务。

## 最小部署形态

本机开发使用前端开发服务、Django API、同代码worker、PostgreSQL；生产由同源反向代理提供静态前端和API，API/worker独立进程，数据库独立服务，知识与导出在非公开持久卷。先不增加Redis、专门向量服务或微服务。

PostgreSQL数据库软件无需购买；是否使用托管数据库是后续运维选择。服务器、模型调用、邮件、备份空间及维护有可能产生费用，未获授权不订阅或付费。用户最终自行部署，本项目交付容器/配置模板和经过验证的手册，不擅自操作其域名。

目标交付文件（尚未存在）：`deploy/compose.yaml`、`deploy/compose.dev.yaml`、`deploy/Dockerfile`、`deploy/proxy.conf`、`deploy/env.example`、`deploy/README.md`、`deploy/scripts/backup.sh`、`restore.sh`、`preflight.sh`。首次施工确认本机已有运行时和容器工具，不把安装新全局环境作为默认步骤。

## 配置清单

环境变量名为拟定契约，实施后以env.example为源；秘密示例只放空值和说明，禁止提交真实值。

| 配置组 | 拟定变量 | 作用/失败方式 |
| --- | --- | --- |
| 运行 | SB_ENV、SB_PUBLIC_ORIGIN、SB_ALLOWED_HOSTS | development/production；生产来源缺失拒绝启动 |
| 会话 | SB_SECRET_KEY、SB_CSRF_TRUSTED_ORIGINS | 生产密钥缺失/示例值拒绝启动；安全Cookie按环境启用 |
| 数据库 | SB_DATABASE_URL、SB_MIGRATION_DATABASE_URL | 运行最小权限与迁移高权限分开；前者不得兼任owner |
| 私有文件 | SB_PRIVATE_DATA_ROOT、SB_LIBRARY_ROOT | 均非web/public；只允许登记后的内部存储键 |
| 模型 | SB_MODEL_MODE、SB_MODEL_PROVIDER、SB_MODEL_NAME、SB_MODEL_API_KEY、SB_MODEL_BASE_URL | disabled/demo/local/provider；demo明确标识，外部地址由部署者控制 |
| 预算 | SB_RUN_DEADLINE_SECONDS、SB_USER_DAILY_RUN_LIMIT、SB_GLOBAL_CONCURRENCY、SB_DAILY_COST_LIMIT | 安全默认值，缺失不用无限；币种/未知usage处理要明示 |
| 邮件 | SB_SMTP_HOST、SB_SMTP_PORT、SB_SMTP_USER、SB_SMTP_PASSWORD、SB_MAIL_FROM | 未配置找回邮件不可用，生产预检阻止公开注册 |
| 注册 | SB_REGISTRATION_MODE | 首版invite；公开模式预检附加条件 |
| 运维 | SB_LOG_LEVEL、SB_BACKUP_TARGET、SB_BACKUP_KEY_FILE | 日志默认元数据，备份密钥不同于DB备份本身存放 |

生产不能运行demo模型冒充真答案。开发邮件可进入仅本机可见的邮件捕获服务，不输出找回token到公共日志；它不等于外部邮件已送达。

## 初始化与发布顺序

1. 只读预检：系统/容器/磁盘、端口、来源配置、依赖锁、DB连接与角色、模型/邮件设置、私有卷权限。
2. 建立独立开发或目标数据库，不向已有生产库自动迁移；备份已有状态。
3. 使用迁移账号执行迁移和RLS策略，验证运行账号无法绕过；API/worker只拿运行凭据。
4. 首个管理员通过一次性本地受控命令创建，无默认密码；立即启用MFA和网络限制。
5. 导入自编演示或已审核的知识release；先校验manifest和索引，再发布/授权，失败不改当前版本。
6. 配置模型、预算和邮件；真实闭环检查不使用mock，日志里保留版本和实际usage。
7. 静态前端构建并扫描秘密；反向代理配置HTTPS和同源路由；首次生产冒烟使用测试账户。
8. 只有09的发布门禁满足后才允许邀请真实用户；用户自行完成最终部署操作。

生产遵循Django部署检查，不能把开发runserver当生产服务。HTTPS、关闭调试、秘密配置和恢复能力要逐项验证。[Django部署检查清单](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)

## 健康与故障处理

- `/health/live`只返回进程存活；`/health/ready`检查必要DB/配置，匿名只见简短状态，不见拓扑、凭据、库名和异常堆栈。
- worker心跳、队列最长等待、终态失败率、DB空间、用量/预算、磁盘和备份最近成功时间都有内部指标。
- 供应商不可用时停止自动扩散重试、保留原问题和旧答案，明确提示“暂时不可用”；不静默切换到未经授权的新供应商。
- 本版不自动向外发监控消息。交付可接入的告警接口/指南，配置实际通知渠道时再取得授权。
- 服务日志包括request/job/run关联ID、阶段耗时、错误码、版本；不默认存聊天全文、卡片全文和模型原始请求。
- 受限知识投诉/撤权时优先暂停release、终止运行和阻止下载，再调查；恢复权限需新审计动作。

## 备份与恢复

默认设计目标RPO≤24小时、RTO≤4小时，需在实际硬件和数据量下演练后才可承诺。每日加密备份PostgreSQL；同时保存知识release指纹和对应私有数据、必要模型/政策版本元数据。秘密文件不随普通仓库打包。

恢复演练必须在新数据库与隔离目录，不覆盖在线库。流程为解密验证→恢复→迁移兼容检查→重放删除/撤权清单→阻止遗留在途任务自动计费→账号/权限/来源/导出冒烟→记录耗时。单有dump成功不等于能恢复。

备份滚动35天，导出24小时，内部草稿7天、事件7天、审计/用量90天；账户删除与回收站清理按08执行。清理作业可重复执行、有游标与统计、不使用宽泛目录递归删除；保留清理日志，不把已删正文再写进去。

## 升级与回滚

- 镜像、前端、迁移、知识release、prompt/policy各有版本；页面故障不能通过改原卡临时遮掩。
- 迁移采用先扩展兼容→部署读写适配→验证→后续独立清理；禁止在同一发布中先删旧字段再尝试启动旧版。
- 应用回滚不自动回滚数据库；必须证明旧版兼容，或走已演练恢复方案并说明数据损失窗口。
- 发布前停止领取不兼容任务并排空/安全取消；重启后通过lease重领，不重复发布，不承诺供应商调用exactly-once。
- 每次发布记录变更、已知问题、兼容范围、恢复点和回滚触发条件，不以“能打开网页”代替交付。

## 最终交接包

源码与锁文件、部署配置模板、管理员初始化指南、知识导入/撤销指南、主题和人物修改指南、DB字段/API契约、验证报告、备份恢复实测、许可证清单、故障手册。附“尚需部署者配置”的域名/模型/邮件/备份目的地表，不包含用户真实密钥。
