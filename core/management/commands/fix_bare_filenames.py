from django.core.management.base import BaseCommand
from django.db import transaction

from tables.models import IDCard
from mediafiles.services.image_fields import ImageFieldsMixin
from core.services.base import BaseService


class Command(BaseCommand):
    help = (
        "Fix IDCard image fields that contain bare filenames (e.g. 'xyz') by prepending 'PENDING:'."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Do not save changes; only print what would be changed.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            dest="limit",
            default=0,
            help="Limit how many cards to inspect (0 = all).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            dest="batch_size",
            default=500,
            help="How many cards to process per DB batch commit when applying.",
        )
        parser.add_argument(
            "--client-id",
            type=int,
            dest="client_id",
            default=0,
            help="Only process cards for this client id (optional).",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run")
        limit = int(options.get("limit") or 0)
        batch_size = int(options.get("batch_size") or 500)
        client_id = int(options.get("client_id") or 0)

        qs = IDCard.objects.select_related("table__group__client").all().order_by("id")
        if client_id:
            qs = qs.filter(table__group__client__id=client_id)
        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(f"Inspecting {total} cards (dry_run={dry_run})")

        to_fix = []
        processed = 0

        for card in qs.iterator():
            processed += 1
            changed = False
            if not card.field_data or not card.table or not card.table.fields:
                continue

            for field_config in card.table.fields:
                if not ImageFieldsMixin.is_image_field(field_config):
                    continue

                field_name = field_config.get("name")
                raw = card.field_data.get(field_name)
                if not raw:
                    continue
                raw = str(raw).strip()

                # Skip already-correct values
                if raw.startswith("PENDING:") or raw == "NOT_FOUND" or raw == "":
                    continue

                # If value has a path or an extension, treat differently
                has_path = "/" in raw or "\\" in raw
                last_comp = raw.split("/")[-1]
                has_extension = "." in last_comp

                if not has_path and not has_extension:
                    # bare filename like 'xyz' → mark pending
                    pending = f"PENDING:{raw}"
                    to_fix.append((card.id, field_name, raw, pending))
                    card.field_data[field_name] = pending
                    changed = True
                else:
                    # If it's a path or filename with ext, check existence
                    normalized = BaseService.normalize_image_path(raw)
                    if not BaseService.validate_image_path(normalized):
                        # missing file — convert to pending with basename
                        basename = last_comp or raw
                        pending = f"PENDING:{basename}"
                        to_fix.append((card.id, field_name, raw, pending))
                        card.field_data[field_name] = pending
                        changed = True

            # Persist changes in batches if not dry-run
            if changed and not dry_run:
                # use small transactions per-card to avoid long locks; grouping by batch_size
                with transaction.atomic():
                    card.save(update_fields=["field_data"]) 

            # Optional: show progress
            if processed % 100 == 0:
                self.stdout.write(f"Processed {processed}/{total} cards...")

        # Report
        if not to_fix:
            self.stdout.write("No cards need fixing.")
            return

        self.stdout.write("\nSummary of changes:")
        for cid, field, old, new in to_fix:
            self.stdout.write(f"Card {cid} {field}: {old!r} → {new!r}")

        self.stdout.write(f"\nTotal cards changed: {len({c for c, *_ in to_fix})}")
        if dry_run:
            self.stdout.write("Dry run complete — no database changes were made.")
        else:
            self.stdout.write("Applied changes to the database.")
