from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0107_alter_notification_target'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='organisation',
                    name='org_role',
                    field=models.CharField(default='organisation', max_length=50, help_text='primary, organisation, or manager'),
                ),
            ],
            database_operations=[],
        ),
    ]
