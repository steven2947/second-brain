"""从管理员维护的受控根只读加载固定 release；调用者负责授权。

加载前后检查目录与完整指纹；成功加载后以目录快照（文件集合+大小+mtime）探测变动，一致才复用缓存副本，任何变化触发完整指纹复核。不跟随 CURRENT，也不发布或复制数据。
这些检查用于路径边界和常见变动检测，不承诺抵御已控制本机的管理员。
"""

import hashlib
import re
import stat
import unicodedata
from pathlib import Path

from django.conf import settings
from src.knowledge.library import Library


class ReleaseUnavailable(Exception):
    """统一加载失败；不向调用者暴露本机路径、原文或核心校验细节。"""


def _release_directory(library_root, storage_key):
    """检查固定目录；library_root 为受控绝对根，storage_key 为根内相对存储键。"""
    if not isinstance(storage_key, str) or any(
        char in '\\:%?#' or unicodedata.category(char).startswith('C')
        for char in storage_key
    ):
        raise ValueError
    parts = storage_key.split('/')
    if any(part in ('', '.', '..') or part.upper() == 'CURRENT' for part in parts):
        raise ValueError
    root = Path(library_root)
    if not root.is_absolute() or '..' in root.parts:
        raise ValueError
    release = root.joinpath(*parts)
    for directory in (*reversed(release.parents), release):
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise ValueError
    if (release / 'CURRENT').exists() or not stat.S_ISREG((release / 'manifest.json').lstat().st_mode):
        raise ValueError
    return release


def _fingerprint(release):
    """计算完整 SHA256；release 内仅接受普通文件/目录，排序与旧核心保持一致。"""
    directories, files = [release], []
    while directories:
        for node in directories.pop().iterdir():
            mode = node.lstat().st_mode
            if stat.S_ISDIR(mode):
                directories.append(node)
            elif stat.S_ISREG(mode):
                files.append(node)
            else:
                raise ValueError
    digest = hashlib.sha256()
    for file in sorted(files):
        digest.update(file.relative_to(release).as_posix().encode())
        digest.update(b'\0')
        digest.update(file.read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()


def load_release(storage_key, source_fingerprint, content_version, *, library_root=None):
    """读取单版本；storage_key 为受控相对键，source_fingerprint 为完整 SHA256。

    content_version 为指纹前 24 位；library_root 可注入测试根，默认 SB_LIBRARY_ROOT。
    返回旧核心 Library，保留真实 schema 和逐字锚点校验；全部加载错误统一封装。
    """
    try:
        if (not isinstance(source_fingerprint, str)
                or not re.fullmatch(r'[0-9a-f]{64}', source_fingerprint)
                or not isinstance(content_version, str)
                or not re.fullmatch(r'[0-9a-f]{24}', content_version)
                or source_fingerprint[:24] != content_version):
            raise ValueError
        root = settings.SB_LIBRARY_ROOT if library_root is None else library_root
        # 快照一致才复用缓存副本；任何文件变动都会触发完整指纹复核。
        cache_key = (str(root), storage_key, source_fingerprint, content_version)
        release = _release_directory(root, storage_key)
        current_snapshot = _snapshot(release)
        entry = _release_cache.get(cache_key)
        if entry is not None and entry[1] == current_snapshot:
            return entry[0]
        if _fingerprint(release) != source_fingerprint:
            raise ValueError
        library = Library(release)
        checked = _release_directory(root, storage_key)
        if (_fingerprint(checked) != source_fingerprint
                or library.root != checked or library.version != content_version):
            raise ValueError
        _release_cache[cache_key] = (library, current_snapshot)
        return library
    except Exception:
        raise ReleaseUnavailable('RELEASE_UNAVAILABLE') from None


def _snapshot(release):
    """轻量变动快照：遍历文件取（相对路径, 大小, mtime_ns）并排序；结构异常直接抛错。"""
    directories, files = [release], []
    while directories:
        for node in directories.pop().iterdir():
            mode = node.lstat().st_mode
            if stat.S_ISDIR(mode):
                directories.append(node)
            elif stat.S_ISREG(mode):
                info = node.stat()
                files.append((node.relative_to(release).as_posix(), info.st_size, info.st_mtime_ns))
            else:
                raise ValueError
    return sorted(files)


_release_cache: dict[tuple, tuple[Library, list[tuple[str, int, int]]]] = {}
