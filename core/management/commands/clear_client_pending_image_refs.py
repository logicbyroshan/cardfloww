"""
Clear pending image references for one client's ID cards.

What it does:
- Finds cards for one client (selected by --client-name or --client-id).
- Looks only at image fields in card.field_data.
- Counts values like "PENDING:some_reference".
- Dry-run by default (shows counts only).
- With --apply, replaces those pending values with empty string.

Usage:
    python manage.py clear_client_pending_image_refs --client-name "Acme School"
    python manage.py clear_client_pending_image_refs --client-name "Acme" --apply
    python manage.py clear_client_pending_image_refs --client-id 12 --apply
"""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from organisation.models import Organisation
from core.services.base import BaseService
from tables.models import IDCard


class Command(BaseCommand):
    help = (
        "Count and optionally clear PENDING:* image references in IDCard.field_data "
        "for a single client."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--client-name",
            type=str,
            default="",
            help="Client name to match (icontains by default).",
        )
        parser.add_argument(
            "--client-id",
            type=int,
            default=None,
            help="Client ID (preferred when names are similar).",
        )
        parser.add_argument(
            "--exact",
            action="store_true",
            default=False,
            help="Use case-insensitive exact name match for --client-name.",
        )
        parser.add_argument(
            "--table-id",
            type=int,
            default=None,
            help="Optional: limit to one table id under the selected client.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Actually write changes. Default is dry-run.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Bulk update batch size. Default: 500",
        )
        parser.add_argument(
            "--show-samples",
            type=int,
            default=10,
            help="Number of sample pending refs to print. Default: 10",
        )

    def handle(self, *args, **options):
        client = self._resolve_client(
            client_id=options.get("client_id"),
            client_name=(options.get("client_name") or "").strip(),
            exact=bool(options.get("exact")),
        )

        apply = bool(options.get("apply"))
        batch_size = max(1, int(options.get("batch_size") or 500))
        table_id = options.get("table_id")
        max_samples = max(0, int(options.get("show_samples") or 0))
        mode = "APPLY" if apply else "DRY-RUN"

        self.stdout.write(
            f"\n=== clear_client_pending_image_refs ({mode}) ===\n"
            f"Client: {client.name} (ID: {client.id})"
        )

        qs = IDCard.objects.select_related("table").filter(table__group__client_id=client.id)
        if table_id:
            qs = qs.filter(table_id=table_id)

        total_cards = qs.count()
        self.stdout.write(f"Cards in scope: {total_cards}")

        scanned = 0
        cards_with_pending = 0
        pending_refs_found = 0
        cards_updated = 0
        field_counter = Counter()
        samples = []
        pending_updates = []

        for card in qs.only("id", "table__fields", "field_data").iterator(chunk_size=batch_size):
            scanned += 1
            field_data = card.field_data if isinstance(card.field_data, dict) else {}
            if not field_data:
                continue

            image_keys = self._resolve_image_keys(field_data, card.table.fields or [])
            if not image_keys:
                continue

            card_changed = False
            card_has_pending = False

            for display_key, actual_key in image_keys:
                value = field_data.get(actual_key)
                if not isinstance(value, str):
                    continue

                value_text = value.strip()
                if not value_text.startswith("PENDING:"):
                    continue

                pending_ref = value_text[len("PENDING:") :].strip()
                if not pending_ref:
                    continue

                card_has_pending = True
                pending_refs_found += 1
                field_counter[str(display_key)] += 1

                if len(samples) < max_samples:
                    samples.append((card.id, str(display_key), pending_ref))

                if apply:
                    field_data[actual_key] = ""
                    card_changed = True

            if card_has_pending:
                cards_with_pending += 1

            if apply and card_changed:
                card.field_data = field_data
                pending_updates.append(card)
                cards_updated += 1

                if len(pending_updates) >= batch_size:
                    self._flush_updates(pending_updates, batch_size)
                    pending_updates.clear()

        if apply and pending_updates:
            self._flush_updates(pending_updates, batch_size)

        self.stdout.write("\nSummary")
        self.stdout.write(f"  Scanned cards: {scanned}")
        self.stdout.write(f"  Cards with pending image refs: {cards_with_pending}")
        self.stdout.write(f"  Pending image refs found: {pending_refs_found}")
        if apply:
            self.stdout.write(f"  Cards updated: {cards_updated}")

        if field_counter:
            self.stdout.write("\nPending refs by field")
            for field_name, count in field_counter.most_common():
                self.stdout.write(f"  {field_name}: {count}")

        if samples:
            self.stdout.write("\nSample pending refs")
            for card_id, field_name, pending_ref in samples:
                self.stdout.write(f"  Card #{card_id} | {field_name} | {pending_ref}")

        if apply:
            self.stdout.write(self.style.SUCCESS("\nDone. Pending references were cleared."))
        else:
            apply_hint = f"python manage.py clear_client_pending_image_refs --client-id {client.id} --apply"
            if table_id:
                apply_hint += f" --table-id {table_id}"
            self.stdout.write(self.style.WARNING("\nDry-run only. No data changed."))
            self.stdout.write(self.style.WARNING(f"Run this to apply: {apply_hint}"))

    def _resolve_client(self, *, client_id, client_name, exact):
        if client_id:
            client = Organisation.objects.filter(id=client_id).only("id", "name", "status").first()
            if not client:
                raise CommandError(f"No client found with id={client_id}")
            return client

        if not client_name:
            raise CommandError("Provide either --client-id or --client-name")

        if exact:
            matches = Organisation.objects.filter(name__iexact=client_name).only("id", "name", "status")
        else:
            matches = Organisation.objects.filter(name__icontains=client_name).only("id", "name", "status")

        count = matches.count()
        if count == 0:
            mode = "iexact" if exact else "icontains"
            raise CommandError(f"No client found for {mode}='{client_name}'")

        if count > 1:
            self.stdout.write(self.style.WARNING(f"Multiple clients matched '{client_name}':"))
            for c in matches.order_by("name", "id")[:30]:
                self.stdout.write(f"  ID={c.id} | {c.name} | status={c.status}")
            raise CommandError("Please rerun with --client-id to select exactly one client")

        return matches.first()

    @staticmethod
    def _resolve_image_keys(field_data, table_fields):
        configured_names = BaseService.get_image_field_names(table_fields or [])
        normalized_to_actual = {}
        for key in field_data.keys():
            normalized_to_actual[str(key).strip().lower()] = key

        resolved = []
        seen_actual = set()

        for cfg_name in configured_names:
            actual = normalized_to_actual.get(str(cfg_name).strip().lower())
            if actual is None or actual in seen_actual:
                continue
            resolved.append((cfg_name, actual))
            seen_actual.add(actual)

        if resolved:
            return resolved

        # Fallback for legacy/misaligned table config: detect image-like keys by name.
        for key in field_data.keys():
            key_text = str(key)
            if not BaseService.is_image_field_by_name(key_text):
                continue
            if key in seen_actual:
                continue
            resolved.append((key_text, key))
            seen_actual.add(key)

        return resolved

    @staticmethod
    def _flush_updates(cards, batch_size):
        with transaction.atomic():
            IDCard.objects.bulk_update(cards, ["field_data"], batch_size=batch_size)
