from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0075_remove_cropper_release_model'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='staff',
            name='perm_manage_website_clients',
        ),
        migrations.RemoveField(
            model_name='staff',
            name='perm_manage_website_portfolio',
        ),
    ]