"""运营审计增加动作与有界原因；保留全部既有审计事实。"""
from django.db import migrations, models

ACTIONS = ('admin.provision', 'admin.initialize', 'admin.login', 'admin.reauth', 'admin.logout',
    'knowledge.import', 'knowledge.review', 'knowledge.publish', 'knowledge.revoke', 'grants.manage', 'grants.revoke',
    'accounts.disable', 'accounts.enable', 'quota.manage', 'accounts.invite')


class Migration(migrations.Migration):
    dependencies = [('administration', '0003_remove_adminaudit_admin_audit_action_valid_and_more')]
    operations = [
        migrations.AddField(model_name='adminaudit', name='reason', field=models.CharField(max_length=500, blank=True, default='')),
        migrations.RemoveConstraint(model_name='adminaudit', name='admin_audit_action_valid'),
        migrations.AlterField(model_name='adminaudit', name='action', field=models.CharField(max_length=32, choices=[(v, v) for v in ACTIONS])),
        migrations.AddConstraint(model_name='adminaudit', constraint=models.CheckConstraint(
            condition=models.Q(action__in=ACTIONS), name='admin_audit_action_valid')),
    ]
