from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0060_add_staff_manage_panel_website_section_perms'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='website_display_order',
            field=models.PositiveIntegerField(
                db_index=True,
                default=0,
                help_text='Controls ordering in public website trusted clients section (lower shows first).',
            ),
        ),
    ]
