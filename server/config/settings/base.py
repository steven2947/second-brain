"""运行配置仅从进程环境生成；不自动加载任何开发配置文件。"""

import os

from .environment import build_settings

globals().update(build_settings(os.environ))
