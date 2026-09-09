"""显式选择的真实本机 PostgreSQL 集成配置；不改变无数据库测试配置。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.dev.product_db import read_config, environment
from config.settings.environment import build_settings, database_settings

DEV_CONFIG = read_config(ROOT)
DEV_ENV = environment(DEV_CONFIG)
# 集成测试必须封闭：无论本机部署登记了什么模型，测试一律显式禁用，模型行为由桩提供。
DEV_ENV["SB_MODEL_MODE"] = "disabled"
for key in ("SB_MODEL_NAME", "SB_MODEL_BASE_URL", "SB_MODEL_PROVIDER", "SB_MODEL_API_KEY", "SB_MODEL_EXTRA_JSON"):
    DEV_ENV.pop(key, None)
globals().update(build_settings(DEV_ENV))
RUNTIME_DATABASE = DATABASES["default"].copy()
DATABASES["default"] = database_settings(DEV_ENV["SB_MIGRATION_DATABASE_URL"], "SB_MIGRATION_DATABASE_URL", False)
DATABASES["default"]["TEST"] = {"NAME": "test_sb_product"}
TEST_RUNNER = "tests.database_runner.RuntimeDatabaseRunner"
