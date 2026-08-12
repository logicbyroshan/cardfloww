"""
Django management command to normalize image fields on all IDCards.

Converts bare filenames and invalid paths to PENDING: references or
validates paths against disk. Designed to be safe: supports dry-run,
batching, and comprehensive logging.

Usage:
    python manage.py normalize_image_fields                    # live run
    python manage.py normalize_image_fields --dry-run          # preview only
    python manage.py normalize_image_fields --batch-size=100   # smaller batches
    python manage.py normalize_image_fields --verbose           # detailed output
"""
import logging
from django.core.management.base import BaseCommand
from django.db import transaction

from tables.models import IDCard
from core.services.idcard_card_service import IDCardCardService
from mediafiles.services import ImageService
from mediafiles.services.image_fields import ImageFieldsMixin

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Normalize image fields on all IDCards."""

    help = 'Normalize image fields: convert bare filenames to PENDING:, validate paths.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without writing to DB',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Process cards in batches of N (default: 500)',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Log detailed changes per card',
        )
        parser.add_argument(
            '--client-id',
            type=int,
            help='Limit normalization to a specific client ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        verbose = options['verbose']
        client_id = options['client_id']

        self.stdout.write(
            self.style.HTTP_INFO(
                f'\n{"=" * 70}\n'
                f'Normalize Image Fields\n'
                f'Mode: {"DRY RUN" if dry_run else "LIVE"}\n'
                f'Batch Size: {batch_size}\n'
                f'{"=" * 70}\n'
            )
        )

        stats = {
            'total_cards': 0,
            'cards_with_changes': 0,
            'fields_changed': 0,
            'errors': 0,
            'changes_by_action': {},
        }

        try:
            # Build queryset
            cards_query = IDCard.objects.select_related('table__group__client')

            if client_id:
                cards_query = cards_query.filter(table__group__client_id=client_id)
                self.stdout.write(f'Filtering to client_id={client_id}')

            total = cards_query.count()
            self.stdout.write(f'Found {total} cards to check.\n')

            if total == 0:
                self.stdout.write(self.style.WARNING('No cards found.'))
                return

            # Process in batches to avoid memory bloat
            processed = 0
            for batch_start in range(0, total, batch_size):
                batch_end = min(batch_start + batch_size, total)
                batch = cards_query[batch_start:batch_end]

                for card in batch:
                    try:
                        stats['total_cards'] += 1
                        table = card.table
                        client = table.group.client
                        field_data = card.field_data or {}
                        original_data = dict(field_data)  # snapshot for diff
                        updated = False

                        # Check each image field
                        for field_config in (table.fields or []):
                            if not ImageFieldsMixin.is_image_field(field_config):
                                continue

                            field_name = field_config.get('name')
                            if not field_name:
                                continue

                            raw_value = field_data.get(field_name)
                            if raw_value is None:
                                continue

                            # Skip already-normalized values
                            if isinstance(raw_value, str):
                                if (raw_value.startswith('PENDING:') or
                                    raw_value == '' or
                                    raw_value == 'NOT_FOUND'):
                                    continue

                            # Process via ImageService
                            try:
                                result = ImageService.process_image_field(
                                    field_name=field_name,
                                    new_value=raw_value,
                                    existing_value=field_data.get(field_name, ''),
                                    client=client,
                                    card=card,
                                    uploaded_file=None,
                                    batch_counter=1,
                                    uploaded_by=None,
                                )

                                if result.success:
                                    final_value = result.data.get('final_value')
                                    action = result.data.get('action', 'unknown')

                                    if final_value != raw_value:
                                        field_data[field_name] = final_value
                                        updated = True
                                        stats['fields_changed'] += 1
                                        stats['changes_by_action'][action] = (
                                            stats['changes_by_action'].get(action, 0) + 1
                                        )

                                        if verbose:
                                            self.stdout.write(
                                                f'  Card {card.id} / {field_name}: '
                                                f'{raw_value!r} → {final_value!r} ({action})'
                                            )
                                else:
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'  Card {card.id} / {field_name}: '
                                            f'process failed: {result.message}'
                                        )
                                    )
                                    stats['errors'] += 1

                            except Exception as field_err:
                                self.stdout.write(
                                    self.style.ERROR(
                                        f'  Card {card.id} / {field_name}: '
                                        f'exception: {field_err}'
                                    )
                                )
                                stats['errors'] += 1
                                logger.exception('Field processing error for card %s', card.id)

                        # Write changes (if not dry-run)
                        if updated:
                            stats['cards_with_changes'] += 1

                            if dry_run:
                                if verbose:
                                    self.stdout.write(
                                        self.style.SUCCESS(f'[DRY RUN] Card {card.id} would be updated')
                                    )
                            else:
                                try:
                                    with transaction.atomic():
                                        card.field_data = field_data
                                        card.save(update_fields=['field_data'])
                                    if verbose:
                                        self.stdout.write(
                                            self.style.SUCCESS(f'Card {card.id} updated')
                                        )
                                except Exception as save_err:
                                    self.stdout.write(
                                        self.style.ERROR(
                                            f'Card {card.id} save failed: {save_err}'
                                        )
                                    )
                                    stats['errors'] += 1
                                    logger.exception('Save error for card %s', card.id)

                    except Exception as card_err:
                        self.stdout.write(
                            self.style.ERROR(f'Card {card.id}: unexpected error: {card_err}')
                        )
                        stats['errors'] += 1
                        logger.exception('Unexpected error for card %s', card.id)

                processed = batch_end
                pct = int(100 * processed / total)
                self.stdout.write(f'Progress: {processed}/{total} ({pct}%)')

            # Print summary
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n{"=" * 70}\n'
                    f'SUMMARY\n'
                    f'{"=" * 70}\n'
                    f'Total cards checked:          {stats["total_cards"]}\n'
                    f'Cards with changes:           {stats["cards_with_changes"]}\n'
                    f'Image fields normalized:      {stats["fields_changed"]}\n'
                    f'Errors:                       {stats["errors"]}\n'
                )
            )

            if stats['changes_by_action']:
                self.stdout.write('\nChanges by action:')
                for action, count in sorted(stats['changes_by_action'].items()):
                    self.stdout.write(f'  {action:15s}: {count}')

            if dry_run:
                self.stdout.write(
                    self.style.HTTP_INFO(
                        '\n[DRY RUN] No changes written to DB. '
                        'Run without --dry-run to apply changes.\n'
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('\nNormalization complete!\n')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\nFatal error: {e}')
            )
            logger.exception('Fatal error in normalize_image_fields')
            raise
