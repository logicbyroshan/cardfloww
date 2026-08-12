"""
Management command: revert_kg_dash_for_client
=============================================
Revert class values KG1/KG2 back to KG-I/KG-II for a single client.

Default client name target is "saket mgm schol" (case-insensitive contains).

Usage:
    python manage.py revert_kg_dash_for_client
    python manage.py revert_kg_dash_for_client --apply
    python manage.py revert_kg_dash_for_client --client-name "Saket MGM School" --apply
    python manage.py revert_kg_dash_for_client --client-id 123 --apply
"""

from django.core.management.base import BaseCommand, CommandError

from organisation.models import Organisation
from tables.models import IDCard


BATCH_SIZE = 500


class Command(BaseCommand):
    help = (
        "Revert KG1/KG2 to KG-I/KG-II in IDCard class fields for one client "
        "(dry-run by default)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Actually write changes to the database (default is dry-run)",
        )
        parser.add_argument(
            "--client-name",
            default="saket mgm schol",
            help="Client name substring (case-insensitive). Ignored if --client-id is used.",
        )
        parser.add_argument(
            "--client-id",
            type=int,
            default=None,
            help="Target a specific client by ID.",
        )

    def _resolve_client(self, client_id, client_name):
        if client_id:
            client = Organisation.objects.filter(id=client_id).first()
            if not client:
                raise CommandError(f"Client with id={client_id} not found.")
            return client

        matches = list(Organisation.objects.filter(name__icontains=client_name).order_by("id"))
        if not matches:
            raise CommandError(
                f'No client found with name containing "{client_name}". '
                "Use --client-id to target directly."
            )
        if len(matches) > 1:
            rows = ", ".join([f"{c.id}:{c.name}" for c in matches[:10]])
            raise CommandError(
                f"Multiple clients matched ({len(matches)}): {rows}. "
                "Use --client-id for an exact target."
            )
        return matches[0]

    def handle(self, *args, **options):
        apply = options["apply"]
        client_name = options["client_name"]
        client_id = options["client_id"]

        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(f"\n=== revert_kg_dash_for_client ({mode}) ===\n")

        client = self._resolve_client(client_id, client_name)
        self.stdout.write(f"Target client: {client.id} - {client.name}\n")

        table_class_field = {}
        table_qs = client.id_card_groups.all().prefetch_related("tables")
        for group in table_qs:
            for table in group.tables.all():
                fields = table.fields or []
                class_field_name = None
                for fld in fields:
                    if fld.get("type") == "class":
                        class_field_name = fld.get("name")
                        break
                if class_field_name:
                    table_class_field[table.id] = class_field_name

        if not table_class_field:
            self.stdout.write(self.style.WARNING("No tables with class field found for this client."))
            return

        cards_qs = (
            IDCard.objects
            .filter(table__group__client=client, table_id__in=table_class_field.keys())
            .only("id", "table_id", "field_data")
        )
        total_cards = cards_qs.count()
        self.stdout.write(f"Cards scanned: {total_cards}")

        scanned = 0
        changed_cards = 0
        changed_fields = 0
        preview_limit = 30
        preview_shown = 0
        to_update = []

        for card in cards_qs.iterator(chunk_size=BATCH_SIZE):
            scanned += 1
            fd = card.field_data
            if not isinstance(fd, dict):
                continue

            class_key = table_class_field.get(card.table_id)
            if not class_key:
                continue

            raw = fd.get(class_key)
            if not isinstance(raw, str):
                continue

            val = raw.strip().upper()
            if val == "KG1":
                new_val = "KG-I"
            elif val == "KG2":
                new_val = "KG-II"
            else:
                continue

            changed_fields += 1
            if preview_shown < preview_limit:
                self.stdout.write(
                    f"  card {card.id:>8} [{class_key}] {raw!r} -> {new_val!r}"
                )
                preview_shown += 1

            if apply:
                fd[class_key] = new_val
                card.field_data = fd
                to_update.append(card)
                changed_cards += 1

                if len(to_update) >= BATCH_SIZE:
                    IDCard.objects.bulk_update(to_update, ["field_data"], batch_size=BATCH_SIZE)
                    to_update = []

            elif raw != new_val:
                changed_cards += 1

            if scanned % 5000 == 0:
                self.stdout.write(f"  Scanned {scanned}/{total_cards}...")

        if apply and to_update:
            IDCard.objects.bulk_update(to_update, ["field_data"], batch_size=BATCH_SIZE)

        self.stdout.write("\n--- Summary ---")
        self.stdout.write(f"Scanned cards        : {scanned}")
        self.stdout.write(f"Cards affected       : {changed_cards}")
        self.stdout.write(f"Class fields changed : {changed_fields}")

        if not apply and changed_cards > 0:
            self.stdout.write(self.style.WARNING("Dry-run only. Re-run with --apply to save changes."))
        elif apply:
            self.stdout.write(self.style.SUCCESS("Done. Changes saved."))
        else:
            self.stdout.write(self.style.SUCCESS("No KG1/KG2 values found for this client."))
