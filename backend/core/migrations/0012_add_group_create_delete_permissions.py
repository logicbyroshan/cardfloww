from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_add_assigned_groups_to_staff'),
    ]

    operations = [
        # Client model
        migrations.AddField(
            model_name='client',
            name='perm_idcard_group_create',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='client',
            name='perm_idcard_group_delete',
            field=models.BooleanField(default=False),
        ),
        # Staff model
        migrations.AddField(
            model_name='staff',
            name='perm_idcard_group_create',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='staff',
            name='perm_idcard_group_delete',
            field=models.BooleanField(default=False),
        ),
    ]
