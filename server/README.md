# 产品服务端

当前已实现普通账号/会话、知识授权、问题/消息、租约worker、逐调用用量与月度额度、原v3装配及正式答案发布/读取，以及收藏笔记、行动跟进、答案反馈和独立学习练习。管理员MFA、知识发布/授权、账号运营及个人导出/回收站/注销已接入，实际进度见`docs/product-v1/PROGRESS.md`。真实模型、完整业务浏览器验收及部署恢复尚未完成，不可直接当上线成品。

已经启用auth/contenttypes/sessions和自定义accounts.User，并迁入本项目独立开发库。新部署也必须使用当前用户迁移，不能先生成默认auth_user表。普通登录/CSRF/跨用户接口及管理员MFA已有真实PostgreSQL与HTTP验证；普通账号找回已接入持久发送队列、本机私有捕获及Django SMTP连接，真实邮件送达与设备管理仍待验收。隐私维护仅独立迁移角色执行，见`docs/privacy-operations.md`。

## 环境与依赖

项目根目录运行。产品使用独立 `.venv-product`，旧 `.venv-mvp` 保留原样。

```bash
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv-product
.venv-product/bin/python -m pip install --index-url https://pypi.org/simple -r server/requirements.lock.txt
.venv-product/bin/python -m pip check
```

目标 Python 3.12、PostgreSQL 14+；本机已用 Python 3.12.14 和 PostgreSQL 16.14 验证。精确依赖在 `requirements.lock.txt`，主依赖在 `pyproject.toml`。锁定版本来源是官方 PyPI，不包含旧 CLI 的向量和蒸馏依赖；产品已通过只读适配器调用原核心关键词检索和v3验证，真实模型效果另行验收。

2026-09-08 核对：Django 5.2.17 为受支持的 5.2 LTS 安全补丁版本；DRF 3.17.2 包含近期安全修复；psycopg 3.3.5、Uvicorn 0.52.4 为稳定发布。参考：[Django 支持版本](https://www.djangoproject.com/download/)、[Django 数据库兼容要求](https://docs.djangoproject.com/en/5.2/ref/databases/#postgresql-notes)、[DRF 发布记录](https://www.django-rest-framework.org/community/release-notes/)、[psycopg 发布记录](https://www.psycopg.org/psycopg3/docs/news.html)、[Uvicorn 发布记录](https://uvicorn.dev/release-notes/)。框架遵循其原始许可证；此记录不等于完整依赖漏洞扫描或产品发布安全认证。

## 测试

```bash
.venv-product/bin/python server/manage.py test tests.test_environment tests.test_health --settings=tests.settings --noinput
```

必须使用上述明确模块标签；从仓库根执行 `test tests` 会选中旧根目录测试。测试配置仅从 `tests/settings.py` 的自编数据构造，不读取真实凭据、不创建数据库；健康检查的驱动成功/失败分支用边界替身验证，不能替代真实 PostgreSQL/ASGI 冒烟。

## 本机启动

完整后端测试用`.venv-product/bin/python server/manage.py test server/tests --top-level-directory server --settings=tests.integration_settings`，独占创建/销毁`test_sb_product`；不要与其他DB测试或浏览器测试服务并行。

正式迁移命令为`.venv-product/bin/python server/manage.py migrate --settings=config.settings.migrate`。同时提供runtime的`SB_DATABASE_URL`和独立`SB_MIGRATION_DATABASE_URL`，不要替换runtime URL，否则身份保护会拒绝角色混用。迁移后API/worker环境不需要保留迁移凭据。

服务仅读取进程环境，不自动寻找 `.env` 或用户模型凭据。先由部署者配置 `SB_DATABASE_URL`；数据库 URL 必须是 PostgreSQL，并显式提供账号、密码、主机与库名，不存在 SQLite 回退。开发默认来源为 `http://localhost:5173`，Host 允许 localhost/127.0.0.1/IPv6 回环，debug 默认关闭，模型默认 `disabled`。

如已由本项目初始化流程生成受控 `.runtime/product.env`，可显式加载，再启动：

```bash
set -a
source .runtime/product.env
set +a
unset SB_MIGRATION_DATABASE_URL
.venv-product/bin/python server/manage.py check
.venv-product/bin/python -m uvicorn config.asgi:application --app-dir server --host 127.0.0.1 --port 8019 --no-proxy-headers --no-access-log --lifespan off
```

另一个终端检查：

```bash
curl --noproxy '*' http://127.0.0.1:8019/health/live
curl --noproxy '*' http://127.0.0.1:8019/health/ready
```

`live` 在进程可用时返回 `{"status":"ok"}`；`ready` 执行只读 `SELECT 1`，成功返回相同状态，失败返回 HTTP 503 与 `{"status":"unavailable"}`。均禁止缓存且只接受 GET/HEAD。就绪只证明数据库连接可用，不证明迁移完成、角色正确、模型可用或业务已交付。

## 生产环境校验边界

后台执行器在另一个仅含runtime配置的终端运行`.venv-product/bin/python server/manage.py runworker`。默认模型disabled，任务明确报MODEL_UNAVAILABLE而非伪造结果；部署者显式配置获准模型后才调用。每次调用独立记账，新月默认100轮，未知token/费用为NULL。

普通找回默认`SB_MAIL_MODE=disabled`；显式开启`local_capture`仅允许开发环境，`smtp`必须完整配置专用邮件环境变量。原`runworker`同时处理找回队列，`--once --owner <UUID>`可受控执行一条任务。申请只返回接收状态，SMTP耗时与失败在worker中处理；租约30秒、最多3次尝试，意外中断可能重复发送，但密码重置只允许一次消费。捕获固定保存在`SB_PRIVATE_DATA_ROOT/password-reset/<用户UUID>/<任务UUID>.json`，目录0700、文件0600，正文包含30分钟有效的片段链接。文件没有公开下载接口，已用/到期记录及捕获接入本人隐私维护；不要把该目录映射到静态服务。配置、取回和验证边界见[`docs/account-recovery.md`](../docs/account-recovery.md)。

浏览器开发联调可运行`.venv-product/bin/python tools/dev/product_demo.py`：先构建web，入口独占回环8020与固定测试库，退出清理；只使用自编材料和固定提案，非真实模型效果测试，也不得用于公开部署。

设置 `SB_ENV=production` 后，以下配置缺失/无效会拒绝启动：随机 `SB_SECRET_KEY`（至少 50 字符，拒绝常见示例值）、HTTPS `SB_PUBLIC_ORIGIN`、精确 `SB_ALLOWED_HOSTS`、PostgreSQL `SB_DATABASE_URL`、私有绝对目录 `SB_PRIVATE_DATA_ROOT` 和 `SB_LIBRARY_ROOT`。目录不得在根目录或包含 web/public/static 的路径下；程序不会自动创建、复制或修改书库。

生产禁止 debug 与 demo，Cookie 设置 Secure/HttpOnly/SameSite=Lax，开启 HTTPS 重定向及安全响应头。`SB_CSRF_TRUSTED_ORIGINS` 若配置必须与公开来源完全一致；不启用跨源 CORS。开发未给 secret 时仅生成当前进程临时值；未来使用登录时应显式设置持久秘密。

`SB_MIGRATION_DATABASE_URL` 可在独立迁移流程提供；API 不要求拥有此秘密。若同时提供，两条 URL 必须指向同一主机、端口和库，但使用不同角色；迁移凭据不会注册为 Django 可用数据库连接。此静态检查不能证明 runtime 不是 superuser/BYPASSRLS/table owner，实际角色权限须由后续数据库预检和 RLS 集成测试证明。

模型模式仅校验配置，不发请求：`disabled` 有意关闭；`demo` 仅开发允许；`local` 要求模型名及显式回环 HTTP(S) 地址；`provider` 要求供应商名、模型名、HTTPS 地址和非示例 API key。配置损坏不会回退到 demo；这些值不会通过健康接口返回。

本机启动命令不信任转发请求头；生产反向代理的 HTTPS/可信代理边界、CSP、日志白名单、邮件和备份配置将在部署工作包实现与验证。不要把当前骨架直接视为公开运营成品。
