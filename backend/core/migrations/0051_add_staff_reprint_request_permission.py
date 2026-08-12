from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0050_remove_client_perm_idcard_created_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='staff',
            name='perm_reprint_request_list',
            field=models.BooleanField(default=False),
        ),
    ]
