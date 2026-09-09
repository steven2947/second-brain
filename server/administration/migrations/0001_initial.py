"""管理员凭据和追加审计的可追踪数据库事实。"""
import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='AdminAudit', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('actor_id', models.UUIDField()),
            ('action', models.CharField(choices=[(v, v) for v in ('admin.provision', 'admin.initialize', 'admin.login', 'admin.reauth', 'admin.logout')], max_length=32)),
            ('target_id', models.UUIDField(null=True)),
            ('occurred_at', models.DateTimeField(auto_now_add=True)),
            ('request_id', models.UUIDField(null=True)),
        ], options={'default_permissions': (), 'constraints': [models.CheckConstraint(
            condition=models.Q(action__in=['admin.provision', 'admin.initialize', 'admin.login', 'admin.reauth', 'admin.logout']), name='admin_audit_action_valid')]}),
        migrations.CreateModel(name='AdministratorDevice', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('secret_ciphertext', models.TextField()),
            ('requested_role', models.CharField(choices=[('system-admin', 'system-admin'), ('knowledge-admin', 'knowledge-admin')], max_length=32)),
            ('confirmed_at', models.DateTimeField(null=True)),
            ('revoked_at', models.DateTimeField(null=True)),
            ('last_t', models.BigIntegerField(default=-1)),
            ('failure_count', models.PositiveIntegerField(default=0)),
            ('next_attempt_at', models.DateTimeField(null=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('owner', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
        ], options={'default_permissions': (), 'permissions': [
            (name.replace('.', '_'), name) for name in ('accounts.view', 'accounts.disable', 'quota.manage',
            'accounts.invite', 'knowledge.import', 'knowledge.review', 'knowledge.publish', 'knowledge.revoke',
            'grants.manage', 'operations.view', 'feedback.review')]}),
        migrations.CreateModel(name='RecoveryCode', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('token_hash', models.CharField(max_length=64, unique=True)),
            ('consumed_at', models.DateTimeField(null=True)),
            ('device', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='administration.administratordevice')),
            ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
        ], options={'default_permissions': ()}),
    ]
