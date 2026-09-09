"""供 Uvicorn 等 ASGI 服务器加载的产品服务入口。"""

import os
import sys
from pathlib import Path

from django.core.asgi import get_asgi_application

# 按入口位置补齐旧核心路径，并保留 server 内模块的解析优先级。
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.append(project_root)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
application = get_asgi_application()
