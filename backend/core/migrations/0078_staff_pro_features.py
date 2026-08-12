# Generated migration for staff pro feature fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0077_merge_20260511_1532'),
    ]

    operations = [
        migrations.AddField(
            model_name='staff',
            name='perm_pro_data_deletion_guard',
            field=models.BooleanField(default=False, help_text='Allow Data Deletion Guard'),
        ),
        migrations.AddField(
            model_name='staff',
            name='perm_pro_log_deletion_guard',
            field=models.BooleanField(default=False, help_text='Allow Log Deletion Guard'),
        ),
        migrations.AddField(
            model_name='staff',
            name='perm_pro_user_options',
            field=models.BooleanField(default=False, help_text='Allow User Options (Impersonation/Login as User)'),
        ),
    ]
