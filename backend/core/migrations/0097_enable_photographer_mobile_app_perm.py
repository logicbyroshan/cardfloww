"""
Data migration: Enable perm_mobile_app for all existing Photographer profiles.

Context: The Photographer model was created with perm_mobile_app=False as the
default. This migration sets it to True for all existing photographers so they
can log into the mobile app.  Admins can still toggle it off per-photographer
from the Manage Photographers panel.
"""

from django.db import migrations


def enable_photographer_mobile_app(apps, schema_editor):
    Photographer = apps.get_model('core', 'Photographer')
    updated = Photographer.objects.filter(perm_mobile_app=False).update(perm_mobile_app=True)
    if updated:
        print(f"\n  [migrate] Enabled perm_mobile_app for {updated} photographer(s).")


def disable_photographer_mobile_app(apps, schema_editor):
    """Reverse: set all back to False (conservative rollback)."""
    Photographer = apps.get_model('core', 'Photographer')
    Photographer.objects.filter(perm_mobile_app=True).update(perm_mobile_app=False)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0096_add_client_message_backup_download_reprint_reject'),
    ]

    operations = [
        migrations.RunPython(
            enable_photographer_mobile_app,
            reverse_code=disable_photographer_mobile_app,
        ),
    ]
