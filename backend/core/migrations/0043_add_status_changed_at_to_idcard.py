from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0042_add_modified_by_to_idcard'),
    ]

    operations = [
        migrations.AddField(
            model_name='idcard',
            name='status_changed_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='Timestamp when card status last changed (not updated by field edits — used for default list sort)',
            ),
        ),
        migrations.AddIndex(
            model_name='idcard',
            index=models.Index(fields=['status_changed_at'], name='idcard_status_changed_at_idx'),
        ),
    ]
