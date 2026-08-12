from django.db import migrations

def drop_officework_tables(apps, schema_editor):
    db_engine = schema_editor.connection.vendor
    cascade = " CASCADE" if db_engine == 'postgresql' else ""
    tables = [
        "core_officeworkchatgroupmember",
        "core_officeworkchatgroup",
        "core_officeworkchatmessage",
        "core_officeworktaskcomment",
        "core_officeworktask",
        "core_officeworksharedfile",
        "core_officeworklead",
    ]
    with schema_editor.connection.cursor() as cursor:
        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}{cascade};")

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0084_remove_client_logo_client_icon_and_more'),
    ]

    operations = [
        migrations.RunPython(drop_officework_tables, reverse_code=migrations.RunPython.noop)
    ]

