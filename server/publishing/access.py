"""后台身份复查与本地只读文件边界。"""
import re
import stat
from pathlib import Path
from django.conf import settings
from accounts.models import User
from accounts.services import AccountError
from administration.models import AdministratorDevice
from administration.permissions import granted_permissions
from knowledge.release_loader import _release_directory, _fingerprint, load_release, ReleaseUnavailable


def failure(code, status=409):
    """code为固定公开错误码，status为HTTP状态；不暴露文件与证据内容。"""
    return AccountError(code, '知识管理操作未完成', status)


def current_actor(owner, device_id, epoch, permission):
    """owner/device_id/epoch为服务端MFA快照，permission为固定操作权限；事务内重新查事实。"""
    user = User.objects.select_for_update().filter(pk=owner, status='active', is_staff=True, auth_epoch=epoch).first()
    device = AdministratorDevice.objects.filter(pk=device_id, owner_id=owner, confirmed_at__isnull=False, revoked_at=None).first()
    if user is None or device is None or permission not in granted_permissions(user):
        raise failure('ADMIN_PERMISSION_DENIED', 403)
    return user


def bounded_directory(storage_key):
    """storage_key为登记目录键；限制总文件数与字节后才允许旧核心加载。"""
    try:
        directory = _release_directory(settings.SB_LIBRARY_ROOT, storage_key)
        pending, count, size = [directory], 0, 0
        while pending:
            for node in pending.pop().iterdir():
                info = node.lstat()
                count += 1
                size += info.st_size if stat.S_ISREG(info.st_mode) else 0
                if count > 10000 or size > 100 * 1024 * 1024:
                    raise ValueError
                if stat.S_ISDIR(info.st_mode):
                    pending.append(node)
                elif not stat.S_ISREG(info.st_mode):
                    raise ValueError
        return directory
    except (OSError, ValueError):
        raise failure('SOURCE_UNAVAILABLE') from None


def source_library(source):
    """source为登记源或release；只读且校验完整指纹与真实核心结构。"""
    bounded_directory(source.storage_key)
    try:
        return load_release(source.storage_key, source.source_fingerprint, source.content_version)
    except ReleaseUnavailable:
        raise failure('SOURCE_UNAVAILABLE') from None


def source_fingerprint(storage_key):
    """storage_key为本机登记键；有界安全目录检查后读取真实SHA256。"""
    return _fingerprint(bounded_directory(storage_key))


def proof_exists(key):
    """key为私有根内证明文件相对键；拒绝URL、父路径和任意链接。"""
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*', key):
        return False
    if any(part in ('.', '..') or part.upper() == 'CURRENT' for part in key.split('/')):
        return False
    root = Path(settings.SB_PRIVATE_DATA_ROOT)
    candidate = root.joinpath(*key.split('/'))
    try:
        return (root.is_absolute() and all(stat.S_ISDIR(path.lstat().st_mode) for path in reversed(candidate.parents))
                and stat.S_ISREG(candidate.lstat().st_mode))
    except OSError:
        return False
