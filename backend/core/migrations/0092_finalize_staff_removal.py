import django.db.models.deletion
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0091_migrate_staff_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='photographerassignment',
            name='photographer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='photographer_assignments', to='core.photographer'),
        ),
        migrations.DeleteModel(
            name='Staff',
        ),
    ]
