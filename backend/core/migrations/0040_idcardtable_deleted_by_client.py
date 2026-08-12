"""
Migration: Add deleted_by_client field to IDCardTable.

When a client soft-deletes a table it is hidden from their view but
remains visible to admins as "User Deleted".
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0039_remove_deprecated_template_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='idcardtable',
            name='deleted_by_client',
            field=models.BooleanField(
                default=False,
                help_text='True when the client soft-deletes this table. Hidden from client '
                          'views; still visible in admin as "User Deleted".',
            ),
        ),
    ]
