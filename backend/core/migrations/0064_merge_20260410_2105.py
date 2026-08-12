from django.db import migrations


class Migration(migrations.Migration):
    """
    Compatibility merge for legacy production branches.

    Keeps historical migration references valid without schema changes.
    """

    dependencies = [
        ('core', '0063_merge_20260409_1311'),
    ]

    operations = []
