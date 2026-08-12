from django.db import migrations


class Migration(migrations.Migration):
    """
    Compatibility merge for legacy production branches.

    This no-op node keeps older migration histories resolvable when
    environments still reference 0062_merge_20260407_2043.
    """

    dependencies = [
        ('core', '0061_client_website_display_order'),
    ]

    operations = []
