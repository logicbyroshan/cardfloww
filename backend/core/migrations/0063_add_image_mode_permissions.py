from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0062_staff_perm_manage_client_staff'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='perm_idcard_download_image_generate_mode',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='client',
            name='perm_idcard_download_image_rename_mode',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='staff',
            name='perm_idcard_download_image_generate_mode',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='staff',
            name='perm_idcard_download_image_rename_mode',
            field=models.BooleanField(default=False),
        ),
    ]
