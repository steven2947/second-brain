"""管理员登记仅用于已核验的独立迁移连接；秘密仅供本机私有交付。"""
import base64
import json
import os
import secrets
from pathlib import Path
from urllib.parse import quote, urlencode
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.db import connections, transaction
from django.utils import timezone
from accounts.models import User
from .credentials import cipher, recovery_digest, verify_device
from .models import AdministratorDevice, RecoveryCode, AdminAudit
from .permissions import ROLES


def require_management_connection(using='default'):
    """连接必须为配置库的表拥有者；runtime 或另一数据库都不能登记设备。"""
    connection = connections[using]
    if connection.vendor != 'postgresql':
        raise ValueError('管理员初始化仅支持已登记 PostgreSQL')
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database(), current_user')
        database, role = cursor.fetchone()
        cursor.execute("SELECT tableowner FROM pg_tables WHERE schemaname='public' AND tablename IN ('accounts_user', 'administration_administratordevice')")
        owners = cursor.fetchall()
    if (database != connection.settings_dict['NAME'] or role == settings.SB_RUNTIME_DB_ROLE
            or len(owners) != 2 or any(owner != role for (owner,) in owners)):
        raise ValueError('必须使用本项目已登记数据库的独立迁移角色')


def private_outfile(path):
    """只在已配置私有根下独占创建 0600 文件，拒绝符号链接和已有文件。"""
    root = Path(settings.SB_PRIVATE_DATA_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.stat().st_mode & 0o077:
        raise ValueError('私有目录必须仅本人可访问（0700）')
    candidate = Path(path).absolute()
    if candidate.parent.resolve() != root:
        raise ValueError('交付文件必须直接位于本项目私有目录')
    candidate = root / candidate.name
    return os.fdopen(os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'w')


def prepare_administrator(email, display_name, password, role, output, *, using='default'):
    """受控本机准备；不会给既有账号提权，未确认设备不分配权限组。"""
    require_management_connection(using)
    if role not in ROLES:
        raise ValueError('角色无效')
    user = User(email=User.objects.normalize_email(email), display_name=display_name,
                is_staff=True, is_superuser=False)
    validate_password(password, user)
    user.set_password(password)
    # 先验证字段，实际唯一约束仍由同一事务原子判定。
    user.full_clean(validate_unique=False, validate_constraints=False)
    secret = secrets.token_bytes(20)
    recovery = [secrets.token_urlsafe(24) for _ in range(8)]
    encoded = base64.b32encode(secret).decode()
    uri = 'otpauth://totp/' + quote('SecondBrain:' + user.email, safe='') + '?' + urlencode({
        'secret': encoded, 'issuer': 'SecondBrain', 'algorithm': 'SHA1', 'digits': 6, 'period': 30})
    with transaction.atomic(using=using):
        if User.objects.using(using).filter(email__iexact=user.email).exists():
            raise ValueError('账号已存在；初始化不会覆盖或提升已有账号')
        user.save(using=using)
        device = AdministratorDevice.objects.using(using).create(owner=user,
            secret_ciphertext=cipher().encrypt(secret).decode(), requested_role=role)
        RecoveryCode.objects.using(using).bulk_create([RecoveryCode(
            owner=user, device=device, token_hash=recovery_digest(code)) for code in recovery])
        AdminAudit.objects.using(using).create(actor_id=user.pk, action='admin.provision')
        with private_outfile(output) as handle:
            json.dump({'administrator_id': str(user.pk), 'device_id': str(device.pk),
                'otpauth_uri': uri, 'manual_secret': encoded, 'recovery_codes': recovery}, handle, ensure_ascii=False)
            handle.write('\n')
    return user


def confirm_administrator(email, token, *, using='default'):
    """本机确认真实 OTP 后才分配指定组；错误尝试也提交设备退避状态。"""
    require_management_connection(using)
    valid = False
    with transaction.atomic(using=using):
        user = User.objects.using(using).select_for_update().get(email=User.objects.normalize_email(email))
        device = AdministratorDevice.objects.using(using).select_for_update().get(owner=user)
        if not user.is_active or not user.is_staff or user.is_superuser or device.confirmed_at:
            raise ValueError('账号或设备不处于待确认状态')
        valid = verify_device(device, token, 'totp', enrollment=True)
        if valid:
            device.confirmed_at = timezone.now()
            device.save(using=using, update_fields=['confirmed_at'])
            group, _ = Group.objects.using(using).get_or_create(name=device.requested_role)
            permissions = list(Permission.objects.using(using).filter(
                content_type__app_label='administration', content_type__model='administratordevice',
                codename__in=[name.replace('.', '_') for name in ROLES[device.requested_role]]))
            if len(permissions) != len(ROLES[device.requested_role]):
                raise ValueError('权限迁移不完整')
            group.permissions.set(permissions)
            user.groups.add(group)
            AdminAudit.objects.using(using).create(actor_id=user.pk, action='admin.initialize')
    return valid
