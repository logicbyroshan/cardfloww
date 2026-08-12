"""
Migration: Add table_type field to IDCardTable

The column was already added directly via SQL due to a pre-existing migration
history inconsistency (assistants.0001 applied before core.0090 in the DB).
This file records the schema change for code-first tracking.

NOTE: RunPython is a no-op because the column already exists.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0098_photographer_perm_mobile_app_default_true'),
    ]

    operations = [
        migrations.AddField(
            model_name='idcardtable',
            name='table_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('school_student', 'School Student'),
                    ('college_student', 'College Student'),
                    ('staff', 'Staff'),
                    ('custom', 'Custom'),
                ],
                default='custom',
                help_text=(
                    'Auto-detected from table name and organisation name. '
                    'school_student / college_student / staff / custom'
                ),
            ),
        ),
    ]
