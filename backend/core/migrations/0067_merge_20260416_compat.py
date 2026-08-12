from django.db import migrations


class Migration(migrations.Migration):
    """
    Merge legacy compatibility branch back into canonical core chain.

    This no-op merge ensures a single leaf even when older merge nodes
    (0062/0063/0064 merge files) are present in production history.
    """

    dependencies = [
        ('core', '0064_merge_20260410_2105'),
        ('core', '0066_alter_activitylog_action_and_more'),
    ]

    operations = []
