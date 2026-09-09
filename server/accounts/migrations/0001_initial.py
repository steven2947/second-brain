import accounts.models
import django.db.models.functions.text
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('display_name', models.CharField(max_length=80)),
                ('status', models.CharField(choices=[('active', 'active'), ('disabled', 'disabled'), ('deletion_pending', 'deletion_pending')], default='active', max_length=20)),
                ('is_staff', models.BooleanField(default=False)),
                ('is_superuser', models.BooleanField(default=False)),
                ('timezone', models.CharField(default='Asia/Shanghai', max_length=64, validators=[accounts.models.validate_timezone])),
                ('theme', models.CharField(choices=[('system', 'system'), ('light', 'light'), ('dark', 'dark')], default='system', max_length=10)),
                ('auth_epoch', models.PositiveBigIntegerField(default=0)),
                ('access_revision', models.PositiveBigIntegerField(default=0)),
                ('email_verified_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'constraints': [models.UniqueConstraint(django.db.models.functions.text.Lower('email'), name='account_email_case_unique'), models.CheckConstraint(condition=models.Q(('status__in', ['active', 'disabled', 'deletion_pending'])), name='account_status_valid'), models.CheckConstraint(condition=models.Q(('theme__in', ['system', 'light', 'dark'])), name='account_theme_valid')],
            },
        ),
    ]
