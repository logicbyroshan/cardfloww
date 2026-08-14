# Generated migration to ensure core_idcardtable has client_id column
# This uses SeparateDatabaseAndState so that the real production DB
# (which already has this column) is not affected, while the test DB
# gets it via the database_operations.

import django.db.models.deletion
from django.db import migrations, models


def add_client_id_column(apps, schema_editor):
    """Add client_id and organisation_id to core_idcardtable if not present."""
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cols = set()
        if connection.vendor == 'sqlite':
            cursor.execute("PRAGMA table_info(core_idcardtable)")
            cols = {row[1].lower() for row in cursor.fetchall()}
        else:
            description = connection.introspection.get_table_description(cursor, 'core_idcardtable')
            cols = {col.name.lower() for col in description}

        if 'client_id' not in cols:
            cursor.execute("ALTER TABLE core_idcardtable ADD COLUMN client_id integer NULL")

        if 'organisation_id' not in cols:
            cursor.execute("ALTER TABLE core_idcardtable ADD COLUMN organisation_id integer NULL")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0109_alter_organisation_org_type_and_more'),
        ('tables', '0001_initial_domain_models'),
    ]

    operations = [
        migrations.RunPython(
            add_client_id_column,
            reverse_code=migrations.RunPython.noop,
            atomic=False,
        ),
    ]
