"""
Remove deprecated template_front and template_back ImageFields from IDCardGroup.

These fields were deprecated in Phase 4 (Media Refactor) in favour of the
CardMedia model in the mediafiles app.  Before removing the DB columns we do
a data migration: any existing file paths are transferred to CardMedia records
so no uploaded template image is silently discarded.
"""
from django.db import migrations, models


def migrate_template_images_forward(apps, schema_editor):
    """
    Copy existing template_front / template_back paths into CardMedia records.

    Only creates a CardMedia record when the path is non-empty and a matching
    record does not already exist (idempotent).
    """
    IDCardGroup = apps.get_model('core', 'IDCardGroup')
    CardMedia = apps.get_model('mediafiles', 'CardMedia')

    db_alias = schema_editor.connection.alias
    for group in IDCardGroup.objects.using(db_alias).all().iterator():
        client_id = group.client_id

        for media_type, path in (
            ('template_front', group.template_front),
            ('template_back', group.template_back),
        ):
            if not path:
                continue
            # Idempotent — skip if CardMedia already exists for this path
            exists = CardMedia.objects.using(db_alias).filter(
                group_id=group.pk,
                media_type=media_type,
                file=path,
            ).exists()
            if not exists:
                CardMedia.objects.using(db_alias).create(
                    group_id=group.pk,
                    client_id=client_id,
                    media_type=media_type,
                    file=path,
                    original_filename='',
                    is_migrated=True,
                )


def migrate_template_images_reverse(apps, schema_editor):
    """Reverse: nothing to do (CardMedia records are kept)."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0038_emaillog_user_welcome_email_sent'),
        ('mediafiles', '0001_create_cardmedia_model'),
    ]

    operations = [
        # Step 1: data migration — preserve existing template images in CardMedia
        migrations.RunPython(
            migrate_template_images_forward,
            reverse_code=migrate_template_images_reverse,
        ),
        # Step 2: remove the DB columns
        migrations.RemoveField(
            model_name='idcardgroup',
            name='template_front',
        ),
        migrations.RemoveField(
            model_name='idcardgroup',
            name='template_back',
        ),
    ]
