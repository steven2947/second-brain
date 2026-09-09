"""凭据密文、单次恢复摘要与不包含业务内容的追加审计。"""
import uuid
from django.conf import settings
from django.db import models
from .permissions import PERMISSIONS

AUDIT_ACTIONS = ('admin.provision', 'admin.initialize', 'admin.login', 'admin.reauth', 'admin.logout',
                 'knowledge.import', 'knowledge.review', 'knowledge.publish', 'knowledge.revoke', 'grants.manage', 'grants.revoke',
                 'accounts.disable', 'accounts.enable', 'quota.manage', 'accounts.invite')


class AdministratorDevice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    secret_ciphertext = models.TextField()
    requested_role = models.CharField(max_length=32, choices=[('system-admin', 'system-admin'), ('knowledge-admin', 'knowledge-admin')])
    confirmed_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)
    last_t = models.BigIntegerField(default=-1)
    failure_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        permissions = [(name.replace('.', '_'), name) for name in PERMISSIONS]


class RecoveryCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    device = models.ForeignKey(AdministratorDevice, on_delete=models.PROTECT)
    token_hash = models.CharField(max_length=64, unique=True)
    consumed_at = models.DateTimeField(null=True)

    class Meta:
        default_permissions = ()


class AdminAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_id = models.UUIDField()
    action = models.CharField(max_length=32, choices=[(v, v) for v in AUDIT_ACTIONS])
    target_id = models.UUIDField(null=True)
    occurred_at = models.DateTimeField(auto_now_add=True)
    request_id = models.UUIDField(null=True)
    reason = models.CharField(max_length=500, blank=True, default='')

    class Meta:
        default_permissions = ()
        constraints = [models.CheckConstraint(condition=models.Q(action__in=AUDIT_ACTIONS),
            name='admin_audit_action_valid')]
