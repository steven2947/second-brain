"""只增加找回专用待发记录；显式授予runtime有界队列DML，无迁移者凭据依赖。"""
import uuid
from importlib import import_module
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def grant_access(apps, schema_editor):
    """apps/schema_editor为历史模型与独立迁移连接；队列与账号身份表同属认证域。"""
    runtime, _ = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    table = schema_editor.quote_name(apps.get_model('accounts', 'PasswordResetDelivery')._meta.db_table)
    schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')
    schema_editor.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {runtime}')


def revoke_access(apps, schema_editor):
    """apps/schema_editor为回退上下文；只撤销新增队列表访问。"""
    runtime, _ = import_module('problems.migrations.0002_database_access').roles(schema_editor)
    table = schema_editor.quote_name(apps.get_model('accounts', 'PasswordResetDelivery')._meta.db_table)
    schema_editor.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC, {runtime}')


class Migration(migrations.Migration):
    dependencies = [('accounts', '0004_identity_epoch_guard')]
    operations = [
        migrations.CreateModel(name='PasswordResetDelivery', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('binding', models.CharField(max_length=64)),
            ('delivery', models.CharField(choices=[('local_capture', 'local_capture'), ('smtp', 'smtp')], max_length=16)),
            ('status', models.CharField(choices=[(v, v) for v in ('queued', 'running', 'sent', 'failed', 'cancelled', 'consumed')], default='queued', max_length=16)),
            ('attempts', models.PositiveSmallIntegerField(default=0)),
            ('available_at', models.DateTimeField()),
            ('expires_at', models.DateTimeField()),
            ('lease_token', models.UUIDField(null=True)),
            ('lease_until', models.DateTimeField(null=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={
            'indexes': [models.Index(fields=['user', 'status', 'available_at'], name='reset_delivery_pending')],
            'constraints': [
                models.CheckConstraint(condition=models.Q(status__in=['queued', 'running', 'sent', 'failed', 'cancelled', 'consumed']), name='reset_delivery_status_valid'),
                models.CheckConstraint(condition=models.Q(delivery__in=['local_capture', 'smtp']), name='reset_delivery_channel_valid'),
                models.CheckConstraint(condition=models.Q(attempts__lte=3), name='reset_delivery_attempts_bounded'),
            ],
        }),
        migrations.RunPython(grant_access, revoke_access),
    ]
