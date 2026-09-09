#!/usr/bin/env python3
"""产品服务管理命令；与旧 CLI 环境及数据完全独立。"""

import os
import sys
from pathlib import Path


def main():
    """无参数；补齐旧核心路径，读取显式环境并将命令行参数交给 Django。"""
    project_root = str(Path(__file__).resolve().parents[1])
    if project_root not in sys.path:
        sys.path.append(project_root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
