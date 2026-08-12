"""
Repair relation-photo data after table column renames.

This command backfills values from legacy relation-photo keys (for example
FATHER PHOTO/MOTHER PHOTO/REL_1PHOTO/REL_2PHOTO) into the current relation
photo fields on each table by slot order.

Dry-run by default.

Usage:
    python manage.py restore_renamed_relation_photo_fields
    python manage.py restore_renamed_relation_photo_fields --apply
    python manage.py restore_renamed_relation_photo_fields --apply --table-id 123
    python manage.py restore_renamed_relation_photo_fields --apply --client-id 10
"""

import re

from django.core.management.base import BaseCommand

from tables.models import IDCard, Table
from mediafiles.models import CardMedia


REL_1_PATTERN = re.compile(r"^(REL[ _-]*1[ _-]*PHOTO|REL1PHOTO|RELATION[ _-]*1[ _-]*PHOTO)$", re.IGNORECASE)
REL_2_PATTERN = re.compile(r"^(REL[ _-]*2[ _-]*PHOTO|REL2PHOTO|RELATION[ _-]*2[ _-]*PHOTO)$", re.IGNORECASE)


def _norm(name):
    return str(name or "").strip().upper()


def _has_value(value):
    return bool(str(value or "").strip())


def _get_ci(data, key):
    if not isinstance(data, dict):
        return ""
    wanted = _norm(key)
    for existing_key, value in data.items():
        if _norm(existing_key) == wanted:
            return value
    return ""


def _legacy_candidates_for_index(index):
    if index == 0:
        return [
            'FATHER PHOTO', 'F PHOTO', 'FATHER_PHOTO', 'REL_1PHOTO', 'REL 1 PHOTO', 'REL1PHOTO',
            'REL NO 1 PHOTO', 'REL1', 'REL 1', 'REL_1',
        ]
    if index == 1:
        return [
            'MOTHER PHOTO', 'M PHOTO', 'MOTHER_PHOTO', 'REL_2PHOTO', 'REL 2 PHOTO', 'REL2PHOTO',
            'REL NO 2 PHOTO', 'REL2', 'REL 2', 'REL_2',
        ]
    return [
        f'REL_{index + 1}PHOTO',
        f'REL {index + 1} PHOTO',
        f'REL{index + 1}PHOTO',
        f'REL NO {index + 1} PHOTO',
        f'REL{index + 1}',
        f'REL {index + 1}',
        f'REL_{index + 1}',
    ]


class Command(BaseCommand):
    help = "Backfill renamed relation-photo column values into current relation-photo fields."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', default=False, help='Persist DB updates.')
        parser.add_argument('--table-id', type=int, default=None, help='Only process one table id.')
        parser.add_argument('--client-id', type=int, default=None, help='Only process one client id.')
        parser.add_argument('--batch-size', type=int, default=500, help='Bulk update batch size.')

    def handle(self, *args, **options):
        apply = bool(options.get('apply'))
        table_id = options.get('table_id')
        client_id = options.get('client_id')
        batch_size = max(1, int(options.get('batch_size') or 500))

        qs = Table.objects.all().only('id', 'fields', 'group_id')
        if table_id:
            qs = qs.filter(id=table_id)
        if client_id:
            qs = qs.filter(group__client_id=client_id)

        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(f'\n=== restore_renamed_relation_photo_fields ({mode}) ===\n')

        tables_seen = 0
        cards_scanned = 0
        cards_updated = 0
        media_updated = 0
        pending = []

        for table in qs.iterator(chunk_size=200):
            tables_seen += 1
            fields = table.fields if isinstance(table.fields, list) else []
            rel_fields = [
                _norm((f or {}).get('name'))
                for f in fields
                if _norm((f or {}).get('type')) in {'REL_PHOTO', 'MOTHER_PHOTO', 'FATHER_PHOTO'} and _norm((f or {}).get('name'))
            ]
            if not rel_fields:
                continue

            # Update CardMedia field_name aliases to current relation-photo fields.
            for idx, target in enumerate(rel_fields):
                aliases = _legacy_candidates_for_index(idx)
                for alias in aliases:
                    media_updated += CardMedia.objects.filter(
                        card__table_id=table.id,
                        field_name__iexact=alias,
                    ).exclude(field_name=target).update(field_name=target)

            card_qs = IDCard.objects.filter(table_id=table.id).only('id', 'field_data')
            for card in card_qs.iterator(chunk_size=batch_size):
                cards_scanned += 1
                fd = card.field_data if isinstance(card.field_data, dict) else {}
                changed = False

                for idx, target in enumerate(rel_fields):
                    current_val = _get_ci(fd, target)
                    if _has_value(current_val):
                        continue

                    value_to_copy = ''
                    for candidate in _legacy_candidates_for_index(idx):
                        found = _get_ci(fd, candidate)
                        if _has_value(found):
                            value_to_copy = found
                            break

                    if not value_to_copy:
                        for key, value in fd.items():
                            key_norm = _norm(key)
                            if idx == 0 and REL_1_PATTERN.match(key_norm) and _has_value(value):
                                value_to_copy = value
                                break
                            if idx == 1 and REL_2_PATTERN.match(key_norm) and _has_value(value):
                                value_to_copy = value
                                break

                    if value_to_copy:
                        fd[target] = value_to_copy
                        changed = True

                if changed:
                    card.field_data = fd
                    pending.append(card)
                    cards_updated += 1
                    if apply and len(pending) >= batch_size:
                        IDCard.objects.bulk_update(pending, ['field_data'], batch_size=batch_size)
                        pending.clear()

        if apply and pending:
            IDCard.objects.bulk_update(pending, ['field_data'], batch_size=batch_size)

        self.stdout.write('Summary')
        self.stdout.write(f'  Tables scanned: {tables_seen}')
        self.stdout.write(f'  Cards scanned: {cards_scanned}')
        self.stdout.write(f'  Cards updated: {cards_updated}')
        self.stdout.write(f'  CardMedia rows updated: {media_updated}')

        if apply:
            self.stdout.write(self.style.SUCCESS('Done. Changes were saved.'))
        else:
            self.stdout.write(self.style.WARNING('Dry-run only. Re-run with --apply to save changes.'))
