"""消费游标仅随core成功发布推进；新增非负字段不改原消息。"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('problems', '0005_message_run_database_access')]
    operations = [
        migrations.AddField(model_name='problem', name='processed_message_sequence',
                            field=models.BigIntegerField(default=0)),
        migrations.AddConstraint(model_name='problem', constraint=models.CheckConstraint(
            condition=models.Q(processed_message_sequence__gte=0), name='problem_processed_message_nonnegative')),
    ]
