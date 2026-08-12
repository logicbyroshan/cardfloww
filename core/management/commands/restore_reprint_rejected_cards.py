"""
Restore cards moved to pool by old reprint reject behavior.

This command finds cards that were moved to pool by the legacy reprint-reject
flow (tracked in ActivityLog as "Reprint rejected and card moved to pool") and
lets you restore only selected cards back to download status.

Safety:
- Dry-run by default.
- Scoped by client + table.
- Restores only cards currently in pool.

Usage examples:
    python manage.py restore_reprint_rejected_cards --client-name "Acme School"
    python manage.py restore_reprint_rejected_cards --client-name "Acme" --apply
    python manage.py restore_reprint_rejected_cards --client-name "Acme" --card-ids 101,205 --apply
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from organisation.models import Organisation
from core.models import ActivityLog
from core.services.activity_service import ActivityService
from tables.models import IDCard, Table


REJECT_TO_POOL_DESCRIPTIONS = [
    'Reprint rejected and card moved to pool',
    'Reprint request rejected and card moved to pool',
]


class Command(BaseCommand):
    help = (
        'Restore selected cards from pool to download when they were moved by old '
        'reprint reject behavior.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--client-id',
            type=int,
            default=None,
            help='Optional exact client id.',
        )
        parser.add_argument(
            '--client-name',
            default='',
            help='Client name substring (case-insensitive). If omitted, command prompts.',
        )
        parser.add_argument(
            '--table-name',
            default='',
            help='Optional table name substring (case-insensitive).',
        )
        parser.add_argument(
            '--table-id',
            type=int,
            default=None,
            help='Optional exact table id.',
        )
        parser.add_argument(
            '--card-ids',
            default='',
            help='Comma-separated card IDs to restore (example: 12,45).',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=365,
            help='Lookback window in days for reject-to-pool activity logs. Default: 365',
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Actually write changes. Default is dry-run.',
        )
        parser.add_argument(
            '--yes',
            action='store_true',
            default=False,
            help='Skip confirmation prompts. Use carefully.',
        )

    def handle(self, *args, **options):
        apply_changes = bool(options['apply'])
        auto_yes = bool(options['yes'])
        mode = 'APPLY' if apply_changes else 'DRY-RUN'
        self.stdout.write(f'\n=== restore_reprint_rejected_cards ({mode}) ===\n')

        client = self._resolve_client(
            client_id=options.get('client_id'),
            client_name=options.get('client_name', ''),
            auto_yes=auto_yes,
        )
        table = self._resolve_table(
            client=client,
            table_id=options.get('table_id'),
            table_name=options.get('table_name', ''),
            auto_yes=auto_yes,
        )

        explicit_ids = self._parse_card_ids(options.get('card_ids', ''))
        lookback_days = max(1, int(options.get('days') or 365))
        candidates = self._collect_candidates(table, lookback_days)
        if not candidates:
            if explicit_ids:
                candidates = self._collect_explicit_candidates(table, explicit_ids)
            if not candidates:
                self.stdout.write(self.style.WARNING('No matching pool cards found for legacy reprint-reject activity.'))
                return

        self._print_candidates(candidates)

        selected_ids = self._resolve_selection(candidates, explicit_ids, auto_yes)
        if not selected_ids:
            self.stdout.write(self.style.WARNING('No cards selected. Aborting.'))
            return

        self.stdout.write(f'\nSelected card IDs to restore: {", ".join(str(cid) for cid in selected_ids)}')

        if not apply_changes:
            self.stdout.write(self.style.WARNING('Dry-run only. Re-run with --apply to persist changes.'))
            return

        if not auto_yes:
            confirm = input('Proceed with restore to download status? Type YES to continue: ').strip()
            if confirm != 'YES':
                self.stdout.write(self.style.WARNING('Cancelled.'))
                return

        now = timezone.now()
        with transaction.atomic():
            restored_qs = IDCard.objects.select_for_update().filter(
                id__in=selected_ids,
                table=table,
                status='pool',
            )
            restored_ids = list(restored_qs.values_list('id', flat=True))
            if not restored_ids:
                self.stdout.write(self.style.WARNING('No selected cards are currently in pool. Nothing to restore.'))
                return

            restored_qs.update(
                status='download',
                deleted_at=None,
                status_changed_at=now,
                updated_at=now,
            )

        for card_id in restored_ids:
            ActivityService.log(
                action='card_status',
                description='Card restored from pool to download (reprint reject recovery)',
                user=None,
                target_model='IDCard',
                target_id=card_id,
                target_name=f'Card #{card_id}',
            )

        self.stdout.write(self.style.SUCCESS(
            f'Restored {len(restored_ids)} card(s) to download: {", ".join(str(cid) for cid in restored_ids)}'
        ))

    def _resolve_client(self, client_id, client_name, auto_yes):
        if client_id:
            client = Organisation.objects.filter(id=client_id).first()
            if not client:
                raise CommandError(f'Client with id={client_id} was not found.')
            self.stdout.write(f'Selected client: {client.id} - {client.name}')
            return client

        search = str(client_name or '').strip()
        if not search:
            if auto_yes:
                raise CommandError('--client-name or --client-id is required when using --yes.')
            search = input('Enter client name (partial is fine): ').strip()
            if not search:
                raise CommandError('Client name is required.')

        matches = list(Organisation.objects.filter(name__icontains=search).order_by('name', 'id'))
        if not matches:
            raise CommandError(f'No client found matching "{search}".')
        if len(matches) == 1:
            client = matches[0]
            self.stdout.write(f'Selected client: {client.id} - {client.name}')
            return client

        self.stdout.write('\nMultiple clients matched:')
        for idx, client in enumerate(matches, start=1):
            self.stdout.write(f'  {idx}. {client.id} - {client.name}')

        if auto_yes:
            raise CommandError('Multiple clients matched. Use a more specific --client-name.')

        selected_idx = self._prompt_index('Choose client number', len(matches))
        client = matches[selected_idx]
        self.stdout.write(f'Selected client: {client.id} - {client.name}')
        return client

    def _resolve_table(self, client, table_id, table_name, auto_yes):
        tables_qs = Table.objects.filter(group__client=client).order_by('name', 'id')
        if table_id:
            tables_qs = tables_qs.filter(id=table_id)
        if table_name:
            tables_qs = tables_qs.filter(name__icontains=str(table_name).strip())

        tables = list(tables_qs)
        if not tables:
            raise CommandError('No table found for this client with the provided filters.')
        if len(tables) == 1:
            table = tables[0]
            self.stdout.write(f'Selected table: {table.id} - {table.name}')
            return table

        self.stdout.write('\nMultiple tables found:')
        for idx, table in enumerate(tables, start=1):
            card_count = IDCard.objects.filter(table=table).count()
            self.stdout.write(f'  {idx}. {table.id} - {table.name} ({card_count} cards)')

        if auto_yes:
            raise CommandError('Multiple tables matched. Provide --table-id or --table-name.')

        selected_idx = self._prompt_index('Choose table number', len(tables))
        table = tables[selected_idx]
        self.stdout.write(f'Selected table: {table.id} - {table.name}')
        return table

    def _collect_candidates(self, table, lookback_days):
        cutoff = timezone.now() - timedelta(days=lookback_days)
        logs = ActivityLog.objects.filter(
            action='reprint_status',
            description__in=REJECT_TO_POOL_DESCRIPTIONS,
            target_model='IDCard',
            target_id__isnull=False,
            created_at__gte=cutoff,
            target_id__in=IDCard.objects.filter(table=table).values('id'),
        ).order_by('-created_at')

        latest_reject_by_card = {}
        for row in logs.values('target_id', 'created_at'):
            card_id = row['target_id']
            if card_id not in latest_reject_by_card:
                latest_reject_by_card[card_id] = row['created_at']

        if not latest_reject_by_card:
            # Fallback for older DB rows where reprint reject activity may not have
            # target_id logging. Show table-scoped pool cards that were previously
            # downloaded so operator can select exact cards manually.
            fallback_cards = list(
                IDCard.objects.filter(
                    table=table,
                    status='pool',
                    downloaded_at__isnull=False,
                ).only('id', 'field_data', 'status', 'deleted_at', 'downloaded_at')
            )
            if not fallback_cards:
                fallback_cards = list(
                    IDCard.objects.filter(
                        table=table,
                        status='pool',
                    ).only('id', 'field_data', 'status', 'deleted_at', 'downloaded_at')
                )
            fallback_cards.sort(key=lambda c: c.deleted_at or c.downloaded_at, reverse=True)
            return [
                {
                    'card': card,
                    'last_reject_at': None,
                    'name': self._card_name(card),
                    'source': 'pool_fallback',
                }
                for card in fallback_cards
            ]

        cards = list(
            IDCard.objects.filter(
                id__in=list(latest_reject_by_card.keys()),
                table=table,
                status='pool',
            ).only('id', 'field_data', 'status', 'deleted_at', 'downloaded_at')
        )

        cards.sort(key=lambda c: latest_reject_by_card.get(c.id), reverse=True)
        result = []
        for card in cards:
            result.append({
                'card': card,
                'last_reject_at': latest_reject_by_card.get(card.id),
                'name': self._card_name(card),
                'source': 'activity_log',
            })
        return result

    def _collect_explicit_candidates(self, table, explicit_ids):
        cards = list(
            IDCard.objects.filter(
                id__in=explicit_ids,
                table=table,
                status='pool',
            ).only('id', 'field_data', 'status', 'deleted_at', 'downloaded_at')
        )
        cards.sort(key=lambda c: c.deleted_at or c.downloaded_at, reverse=True)
        return [
            {
                'card': card,
                'last_reject_at': None,
                'name': self._card_name(card),
                'source': 'explicit',
            }
            for card in cards
        ]

    def _resolve_selection(self, candidates, explicit_ids, auto_yes):
        candidate_ids = {item['card'].id for item in candidates}

        if explicit_ids:
            bad = [cid for cid in explicit_ids if cid not in candidate_ids]
            if bad:
                raise CommandError(
                    'These card IDs are not valid candidates for restore: ' + ', '.join(str(x) for x in bad)
                )
            return explicit_ids

        if auto_yes:
            return [item['card'].id for item in candidates]

        raw = input(
            '\nEnter card IDs to restore (comma separated), "all" for all shown, or blank to cancel: '
        ).strip()
        if not raw:
            return []
        if raw.lower() == 'all':
            return [item['card'].id for item in candidates]

        selected = self._parse_card_ids(raw)
        if not selected:
            return []

        bad = [cid for cid in selected if cid not in candidate_ids]
        if bad:
            raise CommandError(
                'These card IDs are not valid candidates for restore: ' + ', '.join(str(x) for x in bad)
            )
        return selected

    def _print_candidates(self, candidates):
        self.stdout.write('\nCandidate cards currently in pool:')
        for idx, item in enumerate(candidates, start=1):
            card = item['card']
            ts = item['last_reject_at']
            ts_text = timezone.localtime(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else '-'
            deleted_text = timezone.localtime(card.deleted_at).strftime('%Y-%m-%d %H:%M:%S') if card.deleted_at else '-'
            source_text = item.get('source', 'unknown')
            self.stdout.write(
                f'  {idx}. card_id={card.id} name="{item["name"]}" '
                f'source={source_text} last_reject={ts_text} deleted_at={deleted_text}'
            )

    @staticmethod
    def _card_name(card):
        field_data = card.field_data if isinstance(card.field_data, dict) else {}
        for key in ('Name', 'NAME', 'Student Name', 'STUDENT NAME'):
            value = str(field_data.get(key, '') or '').strip()
            if value:
                return value
        return f'Card #{card.id}'

    @staticmethod
    def _parse_card_ids(raw):
        values = []
        seen = set()
        for token in str(raw or '').split(','):
            text = token.strip()
            if not text:
                continue
            try:
                value = int(text)
            except ValueError:
                continue
            if value <= 0 or value in seen:
                continue
            seen.add(value)
            values.append(value)
        return values

    @staticmethod
    def _prompt_index(prompt, max_count):
        while True:
            raw = input(f'{prompt} [1-{max_count}]: ').strip()
            try:
                value = int(raw)
            except ValueError:
                continue
            if 1 <= value <= max_count:
                return value - 1
