from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tables', '0002_rename_tables_idca_table_i_6bbdc1_idx_core_idcard_table_i_85127c_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='table',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
    ]
