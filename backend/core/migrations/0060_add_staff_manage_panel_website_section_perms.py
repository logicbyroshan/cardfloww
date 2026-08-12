from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0059_client_website_is_visible'),
    ]

    operations = [
        migrations.AddField(
            model_name='staff',
            name='perm_manage_panel_backup',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='staff',
            name='perm_manage_panel_email',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='staff',
            name='perm_manage_website_clients',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='staff',
            name='perm_manage_website_portfolio',
            field=models.BooleanField(default=False),
        ),
    ]
