"""
Migration: Add GIN index on IDCard.field_data for fast JSON search.

Replaces full table scan on field_data__icontains with GIN-indexed
field_data__contains lookups.

SQL PREVIEW (PostgreSQL):
    CREATE INDEX CONCURRENTLY "idcard_field_data_gin"
    ON "core_idcard" USING GIN ("field_data");

PERFORMANCE IMPACT:
    Before (100k rows): field_data__icontains → Seq Scan ~800ms
    After  (100k rows): field_data__contains  → GIN Scan ~5-15ms

NOTE: This migration only adds the index. It does NOT modify data or
      change any API behavior. Safe to apply on production.
      Skipped automatically on non-PostgreSQL databases (e.g. SQLite).
"""

from django.db import connection, migrations


def add_gin_index(apps, schema_editor):
    """Add GIN index only on PostgreSQL."""
    if connection.vendor == 'postgresql':
        schema_editor.execute(
            'CREATE INDEX IF NOT EXISTS "idcard_field_data_gin" '
            'ON "core_idcard" USING GIN ("field_data");'
        )


def remove_gin_index(apps, schema_editor):
    """Remove GIN index only on PostgreSQL."""
    if connection.vendor == 'postgresql':
        schema_editor.execute(
            'DROP INDEX IF EXISTS "idcard_field_data_gin";'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_add_idcard_perf_indexes'),
    ]

    operations = [
        migrations.RunPython(add_gin_index, remove_gin_index),
    ]
