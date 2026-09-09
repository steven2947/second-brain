# 账号设置与密码找回

状态：当前批次实现与整批验证中，实际结果见[施工进度](product-v1/PROGRESS.md)。本项目没有配置真实SMTP、发送真实邮件或创建真实账号；下面是部署者的配置说明。

## 用户操作

- `/app/settings`：修改称呼、用当前密码修改新密码、重新验证密码后退出全部设备。改密保留当前会话，其他旧会话失效；全退出包括当前设备。邮箱修改和逐设备管理不是本页已实现功能。
- `/forgot-password`：读取当前邮件渠道后申请；无论地址是否存在都不提示账号存在性。202只表示申请受理，不是投递证明，不自动重复发送。
- `/reset-password`：从邮件链接取得一次性令牌，立即从地址栏历史条目清除。确认两次新密码后显式提交；成功要求重新登录，不自动登录、不恢复知识授权。

重置令牌和密码只放在当前页面内存，不进localStorage/sessionStorage；刷新、隐藏或离开重置页面需要重新从邮件打开。令牌不在HTTP查询参数或路径中，邮件链接使用受控公开来源加`/reset-password#token=...`，不根据请求Host拼接。

申请有效窗口30分钟，队列等待会消耗窗口；以邮件中的到期时刻为准。已使用、到期、被篡改或身份已变化的链接统一不可用。普通找回入口不能恢复管理员MFA、被停用或待注销账号。

## 三种邮件模式

| 模式 | 配置 | 行为 |
| --- | --- | --- |
| 默认禁用 | `SB_MAIL_MODE=disabled` | 页面明确不可用；申请返回CHANNEL_UNAVAILABLE，不伪造邮件成功 |
| 本机测试 | `SB_MAIL_MODE=local_capture`，仅development | 真实处理测试待发任务，将邮件写入私有文件，不向外发邮件 |
| SMTP | `SB_MAIL_MODE=smtp`及以下完整配置 | 经后台worker调用Django邮件连接，失败有限重试，不把失败记为发送成功 |

SMTP字段以当前`server/config/settings/environment.py`为准：

| 字段 | 要求 |
| --- | --- |
| `SB_SMTP_HOST` | 精确主机名或IP，不是任意用户输入URL |
| `SB_SMTP_PORT` | 显式1–65535端口 |
| `SB_SMTP_FROM_EMAIL` | 合法单一发件邮箱 |
| `SB_SMTP_USER` / `SB_SMTP_PASSWORD` | 部署环境提供，不进仓库、前端或终端输出 |
| `SB_SMTP_USE_TLS` / `SB_SMTP_USE_SSL` | 两项显式true/false，恰好一个true；常见587 STARTTLS或465 SSL，按供应商配置 |
| `SB_SMTP_TIMEOUT_SECONDS` | 默认5秒，允许1–10秒 |
| `SB_PUBLIC_ORIGIN` | 部署者受控公开来源；生产HTTPS，链接不用请求Host |

配置缺失或互相冲突会拒绝启动；生产禁止本机捕获。SMTP配置通过不证明供应商可达或收件人已经收到邮件。付费邮件订阅、DNS及真实邮件测试由部署者另行安排，本批不擅自执行。

## 本机捕获与worker

沿用现有`server/manage.py runworker`，API与worker应使用相同邮件模式、私有目录和稳定密钥，均不持迁移凭据。无需单独启动第二套邮件服务。

本机测试捕获路径：`SB_PRIVATE_DATA_ROOT/password-reset/{userUUID}/{jobUUID}.json`；目录0700、文件0600。固定字段`to/subject/body/expires_at`，重置链接仅在body中。只能由本机开发负责人查看明确测试任务的文件；不要上传、映射到静态目录、贴到聊天或打印进共享日志。不存在公开“列出邮件”API。

持久队列只保存账号引用、身份HMAC绑定、模式、状态、时间和租约，不复制邮箱、明文令牌或邮件正文。后台在发送时重新校验当前身份。程序至多三次尝试；SMTP接收成功而进程随后崩溃时仍可能重复投递，不能承诺外部邮件exactly-once。

重置捕获和任务已纳入[个人数据维护](privacy-operations.md)的精确目标清理；账号身份变化会废弃旧链接。常规到期清理仍依赖部署工作包的完整分页调度，不能只写保留期限而不运行维护。

## 实现依据与验收边界

复用[Django认证与密码重置](https://docs.djangoproject.com/en/5.2/topics/auth/default/#django.contrib.auth.views.PasswordResetView)、[Django邮件接口](https://docs.djangoproject.com/en/5.2/topics/email/)，结合[OWASP找回密码建议](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)落实统一响应、限流、过期单次令牌与重新登录。本文不宣称安全认证。真实邮件送达、跨设备浏览器及公开运营政策须有独立证据。
