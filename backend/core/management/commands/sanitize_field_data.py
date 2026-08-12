"""
Management command: sanitize_field_data
=======================================
Scans ALL IDCard rows and sanitizes field_data text values,
stripping characters outside the Helvetica-safe Latin range (0x20-0xFF).

Usage:
    python manage.py sanitize_field_data          # dry-run (no changes)
    python manage.py sanitize_field_data --apply  # actually save changes
"""
import logging

from django.core.management.base import BaseCommand
from tables.models import IDCard, sanitize_text_for_storage

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


class Command(BaseCommand):
    help = 'Sanitize all IDCard field_data text values (strip non-Latin chars that cause PDF black boxes)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Actually write changes to the database (default is dry-run)',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(f'\n=== sanitize_field_data ({mode}) ===\n')

        total = IDCard.objects.count()
        self.stdout.write(f'Total IDCard rows: {total}\n')

        dirty_count = 0
        scanned = 0
        to_update = []

        qs = IDCard.objects.all().only('id', 'field_data').iterator(chunk_size=BATCH_SIZE)

        for card in qs:
            scanned += 1
            if not card.field_data or not isinstance(card.field_data, dict):
                continue

            changed = False
            for key, value in card.field_data.items():
                if not isinstance(value, str):
                    continue
                cleaned = sanitize_text_for_storage(value)
                if cleaned != value:
                    card.field_data[key] = cleaned
                    changed = True

            if changed:
                dirty_count += 1
                to_update.append(card)

                # Batch update
                if len(to_update) >= BATCH_SIZE:
                    if apply:
                        IDCard.objects.bulk_update(to_update, ['field_data'])
                        self.stdout.write(f'  Updated batch ({dirty_count} dirty so far, {scanned}/{total} scanned)')
                    to_update = []

            if scanned % 5000 == 0:
                self.stdout.write(f'  Scanned {scanned}/{total}...')

        # Flush remaining
        if to_update and apply:
            IDCard.objects.bulk_update(to_update, ['field_data'])

        self.stdout.write(f'\nDone. Scanned {scanned} cards, {dirty_count} had dirty characters.')
        if not apply and dirty_count > 0:
            self.stdout.write(self.style.WARNING(
                f'  Run with --apply to actually save changes.'
            ))
        elif apply:
            self.stdout.write(self.style.SUCCESS(f'  {dirty_count} cards updated in database.'))
