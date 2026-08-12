from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0048_staff_assigned_table_ids'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='perm_set_temp_password',
            field=models.BooleanField(
                default=False,
                help_text='Allow client to set temporary passwords for own staff accounts',
            ),
        ),
    ]
