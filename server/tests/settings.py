"""仅供显式测试命令选择的配置；不读取真实数据库或模型秘密。"""

from config.settings.environment import build_settings

globals().update(build_settings({
    "SB_ENV": "development",
    "SB_ALLOWED_HOSTS": "testserver,localhost,127.0.0.1,[::1]",
    "SB_PUBLIC_ORIGIN": "http://localhost:5173",
    "SB_DATABASE_URL": "postgresql://test_runtime:test-only@127.0.0.1:1/test_not_connected",
    "SB_MODEL_MODE": "disabled",
}))
