"""成熟 TOTP/Fernet 组件；校验状态在行锁事务内持久化，失败由调用者提交后抛出。"""
import base64
import hashlib
from datetime import timedelta
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.utils import timezone
from django_otp.oath import TOTP
from .models import RecoveryCode


def cipher():
    """从服务端主密钥派生独立用途的 Fernet 密钥；不缓存或输出解密材料。"""
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
               info=b'second-brain/administrator-totp/v1').derive(settings.SECRET_KEY.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def recovery_digest(token):
    """对 192 位随机恢复码取摘要；数据库不保留原始恢复码。"""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_device(device, token, method, *, enrollment=False):
    """device 已持锁且 owner 已验证；只能 enrollment 确认未启用设备。"""
    now = timezone.now()
    if device.revoked_at or (not enrollment and not device.confirmed_at):
        return False
    if device.next_attempt_at and now < device.next_attempt_at:
        return False
    valid = False
    if method == 'totp' and len(token) == 6 and token.isascii() and token.isdigit():
        try:
            totp = TOTP(cipher().decrypt(device.secret_ciphertext.encode()), step=30, digits=6)
            totp.time = now.timestamp()
            valid = totp.verify(int(token), tolerance=1, min_t=device.last_t + 1)
            if valid:
                device.last_t = totp.t()
        except InvalidToken:
            valid = False
    elif method == 'recovery' and not enrollment:
        code = RecoveryCode.objects.select_for_update().filter(
            owner_id=device.owner_id, device=device, token_hash=recovery_digest(token), consumed_at=None).first()
        if code:
            code.consumed_at = now
            code.save(update_fields=['consumed_at'])
            valid = True
    if valid:
        device.failure_count, device.next_attempt_at = 0, None
    else:
        device.failure_count = min(device.failure_count + 1, 20)
        device.next_attempt_at = now + timedelta(seconds=min(2 ** (device.failure_count - 1), 3600))
    device.save(update_fields=['last_t', 'failure_count', 'next_attempt_at'])
    return valid
