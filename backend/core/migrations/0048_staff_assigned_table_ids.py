from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0047_expand_email_log_for_mail_center'),
    ]

    operations = [
        migrations.AddField(
            model_name='staff',
            name='assigned_table_ids',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Optional table IDs this staff can access. Empty = no table-level restriction.',
            ),
        ),
    ]
