"""
Management command: fix_dob_format
====================================
Finds all IDCard DOB fields that are pure digits (no separator) and
inserts the missing / separator back in.

Handles:
  8-digit  DDMMYYYY  →  DD/MM/YYYY   (e.g. 23032020  → 23/03/2020)
  6-digit  DDMMYY    →  DD/MM/YY     (e.g. 230320    → 23/03/20)

Usage:
    python manage.py fix_dob_format               # dry-run (shows what WOULD change)
    python manage.py fix_dob_format --apply       # actually saves to DB
    python manage.py fix_dob_format --apply --client-id 7   # only one client
"""
import re
import logging

from django.core.management.base import BaseCommand
from tables.models import IDCard

logger = logging.getLogger(__name__)

BATCH_SIZE = 500

# All field key names that could hold a date of birth
DOB_KEYS = {
    'DOB', 'dob', 'Dob',
    'DATE OF BIRTH', 'Date of Birth', 'date of birth',
    'DATE_OF_BIRTH', 'date_of_birth',
    'D.O.B', 'D.O.B.','D.O.B', 'd.o.b','D O B',
    'BIRTH DATE', 'Birth Date', 'birth_date',
    'BIRTHDATE',
}

def _is_dob_key(key: str) -> bool:
    if key in DOB_KEYS:
        return True
    k = key.lower()
    return 'dob' in k or 'birth' in k

def _fix_value(v: str):
    """
    If v is exactly 8 or 6 digits, return (fixed_string, original).
    Otherwise return (None, v).
    """
    s = v.strip()
    if re.fullmatch(r'\d{8}', s):
        # DDMMYYYY → DD/MM/YYYY
        fixed = f'{s[0:2]}/{s[2:4]}/{s[4:8]}'
        return fixed, s
    if re.fullmatch(r'\d{6}', s):
        # DDMMYY → DD/MM/YY
        fixed = f'{s[0:2]}/{s[2:4]}/{s[4:6]}'
        return fixed, s
    return None, s


class Command(BaseCommand):
    help = 'Fix DOB fields stored as pure digits (DDMMYYYY → DD/MM/YYYY)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Actually write changes to the database (default is dry-run)',
        )
        parser.add_argument(
            '--client-id',
            type=int,
            default=None,
            help='Only fix cards belonging to this client ID (optional)',
        )
        parser.add_argument(
            '--diagnose',
            action='store_true',
            default=False,
            help='Print all unique DOB-like key names found in field_data (for debugging)',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        client_id = options.get('client_id')
        diagnose = options.get('diagnose')
        mode = 'APPLY' if apply else 'DRY-RUN'

        self.stdout.write(f'\n=== fix_dob_format ({mode}) ===\n')

        qs_base = IDCard.objects.exclude(field_data__isnull=True)
        if client_id:
            qs_base = qs_base.filter(table__group__client_id=client_id)
            self.stdout.write(f'Filtering to client_id={client_id}\n')

        # --diagnose: show all DOB-like keys present, and any remaining digit-only values
        if diagnose:
            self.stdout.write('=== DIAGNOSE MODE ===\n')
            all_dob_keys = {}  # key -> list of sample values
            for card in qs_base.only('id', 'field_data').iterator(chunk_size=BATCH_SIZE):
                fd = card.field_data
                if not isinstance(fd, dict):
                    continue
                for k, v in fd.items():
                    if _is_dob_key(k):
                        if k not in all_dob_keys:
                            all_dob_keys[k] = []
                        if len(all_dob_keys[k]) < 5:
                            all_dob_keys[k].append(repr(v))
            self.stdout.write('DOB-like keys found and sample values:')
            for k, samples in sorted(all_dob_keys.items()):
                self.stdout.write(f'  {k!r:30s} → {", ".join(samples)}')
            if not all_dob_keys:
                self.stdout.write('  (no DOB-like keys found — check key name in your template)')
            self.stdout.write('')
            return

        qs = qs_base.only('id', 'field_data').iterator(chunk_size=BATCH_SIZE)

        total_scanned = 0
        total_fixed_cards = 0
        total_fixed_fields = 0
        to_update = []

        for card in qs:
            total_scanned += 1
            fd = card.field_data
            if not isinstance(fd, dict):
                continue

            card_changed = False
            for key, value in fd.items():
                if not _is_dob_key(key):
                    continue
                if not isinstance(value, str):
                    continue
                fixed, original = _fix_value(value)
                if fixed is None:
                    continue

                # Log the change
                self.stdout.write(
                    f'  card {card.id:>8}  [{key}]  {original!r}  →  {fixed!r}'
                )
                if apply:
                    fd[key] = fixed
                    card_changed = True
                total_fixed_fields += 1

            if card_changed:
                card.field_data = fd
                to_update.append(card)
                total_fixed_cards += 1

                if len(to_update) >= BATCH_SIZE:
                    IDCard.objects.bulk_update(to_update, ['field_data'])
                    self.stdout.write(f'  [batch saved — {total_fixed_cards} cards updated so far]')
                    to_update = []

        # Flush remaining
        if to_update and apply:
            IDCard.objects.bulk_update(to_update, ['field_data'])

        self.stdout.write(f'\n--- Summary ---')
        self.stdout.write(f'Scanned : {total_scanned} cards')
        self.stdout.write(f'DOB fields to fix : {total_fixed_fields}')
        self.stdout.write(f'Cards affected    : {total_fixed_cards}')

        if not apply and total_fixed_fields > 0:
            self.stdout.write(self.style.WARNING(
                f'\nDry-run only — run with --apply to save changes.'
            ))
        elif apply:
            self.stdout.write(self.style.SUCCESS(
                f'\nDone. {total_fixed_fields} DOB fields fixed across {total_fixed_cards} cards.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('\nNo DOB fields need fixing.'))
