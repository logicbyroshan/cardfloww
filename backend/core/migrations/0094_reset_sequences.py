from django.db import migrations

def reset_postgres_sequences(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("SELECT setval(pg_get_serial_sequence('assistants_assistant', 'id'), coalesce(max(id), 1), max(id) IS NOT null) FROM assistants_assistant;")
            cursor.execute("SELECT setval(pg_get_serial_sequence('operators_operator', 'id'), coalesce(max(id), 1), max(id) IS NOT null) FROM operators_operator;")

def reverse_reset(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0093_migrate_user_roles'),
    ]

    operations = [
        migrations.RunPython(reset_postgres_sequences, reverse_reset),
    ]
