"""新增实际正式答案与知识缺口事件；不放宽公开负载白名单。"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('runs', '0002_jobevent')]
    operations = [
        migrations.RemoveConstraint(model_name='jobevent', name='job_event_type_valid'),
        migrations.AddConstraint(model_name='jobevent', constraint=models.CheckConstraint(
            condition=models.Q(event_type__in=['stage', 'question_ready', 'answer_ready', 'coverage_gap', 'failed', 'cancelled']), name='job_event_type_valid')),
    ]
