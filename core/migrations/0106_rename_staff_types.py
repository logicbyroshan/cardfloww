from django.db import migrations


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0105_assistant_org_fk_and_tables_m2m'),
    ]

    operations = [
        migrations.RunPython(noop, noop),
    ]

