# 个人数据与隐私维护

状态：本地后端/前端整批测试与开发库接线完成，浏览器、定时调度及完整恢复演练待补，实际证据见[施工进度](product-v1/PROGRESS.md)。这是工程说明，不替代正式运营政策；没有替真实用户申请导出、注销或执行清理。

## 用户入口

- `/app/privacy`：选择问题、学习或全部个人记录，重新验证密码后申请导出；按真实任务状态显式下载 JSON。完成后 24 小时有效。
- 问题详情的“删除这个问题”：确认后移入回收站，停止该问题及关联学习的在途任务，不是立即物理删除。
- `/app/trash`：30 天内恢复为归档问题，不重新启动任务或恢复知识授权；超过期限即使尚未清理也不可恢复。
- “了解并申请注销账号”：本人密码、准确文字及勾选确认后受理。会话立即失效，7 天冷静期后由维护任务清理。

导出不含原书、内部提示词、模型快照、密码或密钥；不纳入回收站问题及关联学习。无权取得的知识内容省略并记录原因，自己的问题和笔记不冒充书籍内容。下载再次检查身份、记录版本和知识许可；旧导出失效须重新申请。已经下载的文件不能远程收回。

## 到期维护

API 和普通 `runworker` 只持运行角色。跨账号维护使用可信本机终端的独立迁移连接，拒绝运行角色、超级用户及 BYPASSRLS 角色。先由部署环境注入本项目配置，包含运行角色信息及 `SB_MIGRATION_DATABASE_URL`；不要提前把运行连接换成迁移连接，否则角色派生失真。不要输出或提交秘密。

```bash
.venv-product/bin/python server/manage.py privacy_maintenance \
  --settings=config.settings.migrate --limit 100

# 使用上一页真实返回的 UUID 继续，不猜测目标。
.venv-product/bin/python server/manage.py privacy_maintenance \
  --settings=config.settings.migrate --limit 100 --after-owner <上一页返回的UUID>

# 只处理已核对账号的实际到期记录，不提前强制删除。
.venv-product/bin/python server/manage.py privacy_maintenance \
  --settings=config.settings.migrate --owner <目标账号UUID>
```

`--owner` 不可与 `--after-owner` 同用，limit 为 1–1000。部署调度须遍历全部页，至少每日执行并检查退出码。仅启动 worker 不等于配置到期清理；持续失败时不能声称满足到期 24 小时内清理。本批未安装系统定时服务，调度在部署工作包完成。

范围包括到期导出、30 天回收站及关联子记录、7 天注销个人数据、终态 7 天后的内部快照和到期幂等记录。共享知识不随用户删除。注销后保留不可登录、移除在线身份信息的账号占位行以维护共享知识外键；不是“数据库连 UUID 都不存在”。计量仅保留必要无 owner 汇总，未知 token 不估算。更广的 90 天审计/日志轮转与备份保留在部署验收另核对。

## 冷静期取消

仅适用于尚未过 7 天且尚未清理的账号。支持人员先确认本人请求，不静默恢复。

```bash
.venv-product/bin/python server/manage.py cancel_account_deletion \
  --settings=config.settings.migrate \
  --owner <核验后的账号UUID> --reason '本人申请取消注销'
```

要求真实 TTY、再次输入完整 UUID、本人隐藏输入当前密码。密码不能放参数、环境、聊天或日志。成功后重新登录，旧会话与知识授权不会恢复；管理员仍须按原许可重新授予。支持原因不要含额外敏感信息。

## 恢复不能复活已删除数据

`SB_DELETION_LEDGER_ROOT` 不可位于 `SB_PRIVATE_DATA_ROOT` 内，也不能随旧备份回退。记录以 UUID 的 HMAC 定位并签名，保留 42 天以覆盖 35 天备份窗口及额外 7 天，不保存邮箱或原始 UUID。独立保管清单和密钥。

当前签名和 HMAC 使用本项目 `SECRET_KEY`；恢复必须使用兼容密钥，不能直接换密钥后仍声称能匹配旧清单。正式轮换尚需专门迁移策略。

隔离恢复环境在开放服务前，用**最新独立清单**运行：

```bash
.venv-product/bin/python server/manage.py privacy_maintenance \
  --settings=config.settings.migrate --replay-deletions --limit 100
```

遍历全部分页后核验被删除账号不可登录、个人内容不存在。这只覆盖删除重放，不替代知识撤权重放、加密备份、耗时测量或完整恢复演练。不要在日常在线库为测试任意恢复旧数据。
