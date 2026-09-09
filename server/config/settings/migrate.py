"""仅由显式--settings选择的迁移配置；保留runtime身份，连接使用独立迁移角色。"""
import os
from .environment import build_settings, database_settings, required

globals().update(build_settings(os.environ))
DATABASES = {'default': database_settings(required(os.environ, 'SB_MIGRATION_DATABASE_URL'),
    'SB_MIGRATION_DATABASE_URL', SB_ENV == 'production')}
