from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0051_add_staff_reprint_request_permission'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='perm_reprint_request_list',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='client',
            name='perm_confirmed_list',
            field=models.BooleanField(default=False),
        ),
    ]
