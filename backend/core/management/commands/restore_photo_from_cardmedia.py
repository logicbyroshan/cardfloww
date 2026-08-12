"""
Restore accidentally-cleared photo fields from CardMedia records.

This command finds ID cards where a photo field was accidentally converted to
PENDING: state (by clicking the PHOTO PATH cell), and restores the real image
path from the associated CardMedia record.

Usage:
    # Dry-run (shows what would be fixed without changing anything):
    python manage.py restore_photo_from_cardmedia --client-id 5

    # Apply the fix:
    python manage.py restore_photo_from_cardmedia --client-id 5 --apply

    # Specify a particular field name (default: checks all image-type fields):
    python manage.py restore_photo_from_cardmedia --client-id 5 --field-name "PHOTO" --apply

    # Search by client name instead of ID:
    python manage.py restore_photo_from_cardmedia --client-name "Ladaesh" --apply
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from organisation.models import Organisation
from tables.models import IDCard
from mediafiles.models import CardMedia
from core.services.base import BaseService


class Command(BaseCommand):
    help = (
        "Restore accidentally-cleared photo fields from CardMedia records. "
        "Finds cards where PHOTO field became PENDING: and restores the real "
        "uploaded image path from CardMedia. Safe to run multiple times."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--client-id",
            type=int,
            default=None,
            help="Client ID to process.",
        )
        parser.add_argument(
            "--client-name",
            type=str,
            default="",
            help="Client name (icontains match). Use --client-id for exact targeting.",
        )
        parser.add_argument(
            "--field-name",
            type=str,
            default="",
            help=(
                "Specific photo field name to target (e.g. 'PHOTO', 'PHOTO N'). "
                "If empty, all image-type fields are checked."
            ),
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Apply the fix. Without this flag, only a dry-run report is shown.",
        )

    def handle(self, *args, **options):
        client_id = options["client_id"]
        client_name = options["client_name"].strip()
        target_field = options["field_name"].strip().upper()
        apply = options["apply"]

        # ── Resolve client ──────────────────────────────────────────────────
        if client_id:
            try:
                client = Organisation.objects.get(id=client_id)
            except Client.DoesNotExist:
                raise CommandError(f"Client with id={client_id} not found.")
        elif client_name:
            clients = Organisation.objects.filter(name__icontains=client_name)
            if not clients.exists():
                raise CommandError(f"No client matching name: {client_name!r}")
            if clients.count() > 1:
                self.stdout.write(
                    self.style.WARNING("Multiple clients matched:")
                )
                for c in clients:
                    self.stdout.write(f"  id={c.id}  name={c.name!r}")
                raise CommandError(
                    "Use --client-id to select one client specifically."
                )
            client = clients.first()
        else:
            raise CommandError("Provide --client-id or --client-name.")

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n{'[DRY RUN] ' if not apply else ''}Restoring photos for client: "
                f"{client.name!r} (id={client.id})\n"
            )
        )

        # ── Build CardMedia lookup: card_id -> {field_name_upper -> real_path} ─
        self.stdout.write("Building CardMedia lookup...")
        cm_lookup = {}
        card_media_qs = CardMedia.objects.filter(
            client=client,
            card__isnull=False,
        ).select_related('card')

        cm_count = 0
        for cm in card_media_qs:
            card_id = cm.card_id
            file_path = str(cm.file or "").strip()
            if not file_path:
                continue
            field_key = str(cm.field_name or "").strip().upper()
            if not field_key:
                mt = str(cm.media_type or "").lower()
                if mt == "photo":
                    field_key = "PHOTO"

            if card_id not in cm_lookup:
                cm_lookup[card_id] = {}
            if field_key and field_key not in cm_lookup[card_id]:
                cm_lookup[card_id][field_key] = file_path
            cm_count += 1

        self.stdout.write(
            f"  Found {cm_count} CardMedia records for {len(cm_lookup)} unique cards.\n"
        )

        # ── Also build a secondary lookup by original_filename ───────────────
        orig_lookup = {}
        for cm in CardMedia.objects.filter(client=client):
            file_path = str(cm.file or "").strip()
            if not file_path:
                continue
            orig = str(cm.original_filename or "").strip()
            if orig:
                base = os.path.splitext(os.path.basename(orig.replace("\\", "/")))[0].lower()
                if base and base not in orig_lookup:
                    orig_lookup[base] = file_path
            file_base = os.path.splitext(os.path.basename(file_path.replace("\\", "/")))[0].lower()
            if file_base and file_base not in orig_lookup:
                orig_lookup[file_base] = file_path

        self.stdout.write(
            f"  Secondary filename lookup: {len(orig_lookup)} entries.\n"
        )

        # ── Scan all cards for this client ───────────────────────────────────
        cards_qs = IDCard.objects.filter(
            table__group__client=client
        ).select_related('table__group')

        total_cards = cards_qs.count()
        self.stdout.write(f"Scanning {total_cards} cards...\n")

        fixable = []    # (card, field_name, old_val, new_val)
        not_found = []  # (card, field_name, old_val)

        for card in cards_qs.iterator(chunk_size=200):
            fd = card.field_data or {}
            table = card.table

            image_fields = set()
            for f in (table.fields or []):
                fn = f.get("name", "")
                ftype = f.get("type", "text")
                if BaseService.is_image_field(f):
                    image_fields.add(fn.upper())
                if BaseService.is_show_path_enabled(f) and ftype in (
                    "photo", "rel_photo", "mother_photo", "father_photo"
                ):
                    image_fields.add(fn.upper())

            for raw_key, raw_val in fd.items():
                key_upper = raw_key.strip().upper()

                if target_field and key_upper != target_field:
                    continue

                if image_fields and key_upper not in image_fields:
                    if not any(
                        w in key_upper
                        for w in ("PHOTO", "IMAGE", "PIC", "SIGNATURE", "BARCODE")
                    ):
                        continue

                val_str = str(raw_val or "").strip()
                if not val_str:
                    continue

                if not val_str.upper().startswith("PENDING:"):
                    continue

                pending_ref = val_str[8:].strip()
                pending_base = os.path.splitext(
                    os.path.basename(pending_ref.replace("\\", "/"))
                )[0].lower()

                real_path = None
                if card.id in cm_lookup:
                    real_path = cm_lookup[card.id].get(key_upper)
                    if not real_path:
                        for v in cm_lookup[card.id].values():
                            real_path = v
                            break

                if not real_path and pending_base:
                    real_path = orig_lookup.get(pending_base)

                if real_path:
                    fixable.append((card, raw_key, val_str, real_path))
                else:
                    not_found.append((card, raw_key, val_str))

        # ── Report ───────────────────────────────────────────────────────────
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(
            self.style.SUCCESS(f"Fixable cards (CardMedia found):   {len(fixable)}")
        )
        self.stdout.write(
            self.style.WARNING(f"Cannot fix (no CardMedia record): {len(not_found)}")
        )
        self.stdout.write(f"{'='*60}\n")

        if fixable:
            self.stdout.write(self.style.MIGRATE_HEADING("Fixable records:"))
            for card, field, old_val, new_path in fixable[:30]:
                fd = card.field_data or {}
                sid = (
                    fd.get("STUDENT ID") or fd.get("ADMI NO") or
                    fd.get("ID") or str(card.id)
                )
                self.stdout.write(
                    f"  Card {card.id} (SID={sid}) | {field}: "
                    f"{old_val!r}  ->  {new_path!r}"
                )
            if len(fixable) > 30:
                self.stdout.write(f"  ... and {len(fixable) - 30} more")

        if not_found:
            self.stdout.write(self.style.WARNING("\nCannot fix (no matching CardMedia):"))
            for card, field, old_val in not_found[:20]:
                fd = card.field_data or {}
                sid = (
                    fd.get("STUDENT ID") or fd.get("ADMI NO") or
                    fd.get("ID") or str(card.id)
                )
                self.stdout.write(
                    f"  Card {card.id} (SID={sid}) | {field}: {old_val!r}"
                )
            if len(not_found) > 20:
                self.stdout.write(f"  ... and {len(not_found) - 20} more")

        # ── Apply fix ────────────────────────────────────────────────────────
        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    "\nDry-run complete. Use --apply to actually restore the photos."
                )
            )
            return

        if not fixable:
            self.stdout.write(
                self.style.WARNING(
                    "\nNothing to fix — no matching CardMedia records found."
                )
            )
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nApplying fix to {len(fixable)} fields..."
            )
        )

        fixed_count = 0
        error_count = 0

        with transaction.atomic():
            for card, raw_key, old_val, new_path in fixable:
                try:
                    card.refresh_from_db()
                    fd = dict(card.field_data or {})
                    fd[raw_key] = new_path
                    card.field_data = fd
                    card.save(update_fields=["field_data", "updated_at"])
                    fixed_count += 1
                    self.stdout.write(
                        f"  Fixed card {card.id}: {raw_key} -> {new_path!r}"
                    )
                except Exception as exc:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ERROR card {card.id}: {exc}"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone! Fixed: {fixed_count}  Errors: {error_count}"
            )
        )
        if error_count:
            self.stdout.write(
                self.style.ERROR(
                    "Some cards could not be fixed. Check the errors above."
                )
            )
