"""项目开发工具共享的只读路径与配置处理。"""

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict:
    """读取 JSON 对象；path 为待读取文件，不修改内容。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 顶层必须为对象：{path}")
    return value


def resolve_path(value: str) -> Path:
    """解析配置路径；value 为绝对路径或相对项目根目录的路径。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("配置路径不能为空")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def load_local_config() -> dict:
    """读取本机配置；缺失时提示配置文件位置，不生成默认私有路径。"""
    path = PROJECT_ROOT / "configs/local.json"
    if not path.is_file():
        raise ValueError("缺少 configs/local.json，请根据 local.example.json 配置本机书库")
    config = read_json(path)
    if config.get("schema_version") != 1:
        raise ValueError("不支持的本机配置版本")
    for key in ("source_books_root", "library_root", "normalized_root", "index_root", "jobs_root"):
        resolve_path(config.get(key))
    return config
