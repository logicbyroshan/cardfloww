"""
Copy UUID-named card image files to timestamp-named files and repoint DB references.

Safety model:
- Dry-run by default (no writes).
- Never deletes old files.
- Updates only IDCard.field_data, IDCard.photo, and CardMedia.file references.

Why this command exists:
- Older flows produced UUID-like image filenames.
- New flows use timestamp-based names via ImageRenamer.
- This command migrates references without risking data loss.

Usage:
    python manage.py rename_uuid_images_to_timestamp
    python manage.py rename_uuid_images_to_timestamp --apply
    python manage.py rename_uuid_images_to_timestamp --apply --client-id 12
    python manage.py rename_uuid_images_to_timestamp --apply --table-id 45
"""

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction

from core.services.base import BaseService
from tables.models import IDCard
from mediafiles.models import CardMedia
from mediafiles.services import ImageService
from mediafiles.services.image_rename import ImageRenamer
from mediafiles.services.image_thumbnail import ThumbnailService


UUID_STEM_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
UUID_HYPHEN_STEM_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass
class RefTarget:
    kind: str  # field_data or photo
    key: str
    raw_value: str


class Command(BaseCommand):
    help = "Rename UUID-like image references to timestamp filenames (copy + repoint, no delete)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Persist DB/file changes. Default is dry-run.",
        )
        parser.add_argument(
            "--client-id",
            type=int,
            default=None,
            help="Optional: limit to one client id.",
        )
        parser.add_argument(
            "--table-id",
            type=int,
            default=None,
            help="Optional: limit to one table id.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=300,
            help="Iterator chunk size. Default: 300",
        )

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        client_id = options.get("client_id")
        table_id = options.get("table_id")
        batch_size = max(1, int(options.get("batch_size") or 300))

        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(f"\n=== rename_uuid_images_to_timestamp ({mode}) ===\n")

        qs = IDCard.objects.select_related("table").only(
            "id",
            "field_data",
            "photo",
            "table_id",
            "table__fields",
        )

        if client_id:
            qs = qs.filter(table__group__client_id=client_id)
        if table_id:
            qs = qs.filter(table_id=table_id)

        scanned_cards = 0
        cards_with_candidates = 0
        file_targets = 0
        updated_cards = 0
        updated_cardmedia_rows = 0
        copied_files = 0
        skipped_missing_source = 0
        skipped_non_uuid = 0
        errors = 0

        for card in qs.iterator(chunk_size=batch_size):
            scanned_cards += 1
            try:
                plan, card_skips = self._build_card_plan(card)
                skipped_missing_source += card_skips["missing_source"]
                skipped_non_uuid += card_skips["non_uuid"]

                if not plan:
                    continue

                cards_with_candidates += 1
                file_targets += len(plan)

                if not apply:
                    continue

                card_changed, media_rows_changed, file_copies = self._apply_card_plan(card, plan)
                if card_changed:
                    updated_cards += 1
                updated_cardmedia_rows += media_rows_changed
                copied_files += file_copies

            except Exception as exc:
                errors += 1
                self.stdout.write(self.style.WARNING(f"Card {card.id}: {exc}"))

        self.stdout.write("\nSummary")
        self.stdout.write(f"  Scanned cards: {scanned_cards}")
        self.stdout.write(f"  Cards with UUID image candidates: {cards_with_candidates}")
        self.stdout.write(f"  Candidate source files: {file_targets}")
        self.stdout.write(f"  Skipped non-UUID values: {skipped_non_uuid}")
        self.stdout.write(f"  Skipped missing source files: {skipped_missing_source}")
        self.stdout.write(f"  Errors: {errors}")

        if apply:
            self.stdout.write(f"  Copied files: {copied_files}")
            self.stdout.write(f"  Updated cards: {updated_cards}")
            self.stdout.write(f"  Updated CardMedia rows: {updated_cardmedia_rows}")
            self.stdout.write(self.style.SUCCESS("\nDone. UUID references migrated to timestamp names."))
        else:
            self.stdout.write(self.style.WARNING("\nDry-run only. Re-run with --apply to perform migration."))

    def _build_card_plan(self, card) -> Tuple[Dict[str, Dict], Dict[str, int]]:
        """
        Build per-card migration plan keyed by source storage path.

        Returns:
            plan: {
                source_path: {
                    'source_path': str,
                    'ext': str,
                    'refs': [RefTarget, ...],
                }
            }
            skips: {'missing_source': int, 'non_uuid': int}
        """
        skips = {"missing_source": 0, "non_uuid": 0}
        plan: Dict[str, Dict] = {}

        field_data = card.field_data if isinstance(card.field_data, dict) else {}
        image_fields = set(ImageService.get_image_field_names(card.table.fields or []))

        # Include PHOTO-style keys even if table config is weak/legacy.
        for key in field_data.keys():
            if str(key).strip().lower() == "photo":
                image_fields.add(key)

        references: List[RefTarget] = []
        for key in image_fields:
            raw_val = field_data.get(key)
            if raw_val is None:
                continue
            references.append(RefTarget(kind="field_data", key=str(key), raw_value=str(raw_val)))

        photo_name = ""
        try:
            photo_name = str(card.photo.name or "")
        except Exception:
            photo_name = ""
        if photo_name:
            references.append(RefTarget(kind="photo", key="photo", raw_value=photo_name))

        normalized_photo = BaseService.normalize_image_path(photo_name) if photo_name else ""

        for ref in references:
            raw = (ref.raw_value or "").strip()
            if not raw or raw.startswith("PENDING:") or raw == "NOT_FOUND":
                continue

            normalized = BaseService.normalize_image_path(raw)
            if not normalized:
                continue

            stem, ext = self._split_stem_ext(normalized)
            if not self._is_uuid_stem(stem):
                skips["non_uuid"] += 1
                continue

            source_path = normalized if default_storage.exists(normalized) else ""

            if not source_path and normalized_photo:
                p_stem, _p_ext = self._split_stem_ext(normalized_photo)
                if self._is_uuid_stem(p_stem) and p_stem.lower() == stem.lower() and default_storage.exists(normalized_photo):
                    source_path = normalized_photo

            if not source_path:
                skips["missing_source"] += 1
                continue

            _, source_ext = self._split_stem_ext(source_path)
            if not source_ext:
                source_ext = ext or ".jpg"

            bucket = plan.setdefault(source_path, {
                "source_path": source_path,
                "ext": source_ext,
                "refs": [],
            })
            bucket["refs"].append(ref)

        return plan, skips

    def _apply_card_plan(self, card, plan: Dict[str, Dict]) -> Tuple[bool, int, int]:
        """Apply one card migration plan inside a transaction."""
        field_data = card.field_data if isinstance(card.field_data, dict) else {}
        changed_fields = False
        changed_photo = False
        media_rows_changed = 0
        file_copies = 0

        with transaction.atomic():
            for item in plan.values():
                source_path = item["source_path"]
                ext = item["ext"]

                target_dir = os.path.dirname(source_path).replace("\\", "/")
                if not target_dir:
                    # Keep deterministic relative storage even when source path
                    # was stored as a bare filename in very old data.
                    target_dir = "adarshimg"

                new_name = ImageRenamer.generate_filename_safe(
                    target_dir,
                    batch_counter=1,
                    extension=ext,
                )
                new_path = f"{target_dir}/{new_name}" if target_dir else new_name

                if default_storage.exists(new_path):
                    # Extremely unlikely with safe generator, but avoid accidental overwrite.
                    continue

                with default_storage.open(source_path, "rb") as src:
                    default_storage.save(new_path, ContentFile(src.read()))
                file_copies += 1

                try:
                    ThumbnailService.create_thumbnail(new_path)
                except Exception:
                    pass

                for ref in item["refs"]:
                    if ref.kind == "field_data":
                        field_data[ref.key] = new_path
                        changed_fields = True
                    elif ref.kind == "photo":
                        card.photo = new_path
                        changed_photo = True

                media_rows_changed += CardMedia.objects.filter(card=card, file=source_path).update(file=new_path)

            update_fields = []
            if changed_fields:
                card.field_data = field_data
                update_fields.append("field_data")
            if changed_photo:
                update_fields.append("photo")
            if update_fields:
                card.save(update_fields=update_fields)

        return bool(changed_fields or changed_photo), media_rows_changed, file_copies

    @staticmethod
    def _split_stem_ext(path: str) -> Tuple[str, str]:
        base = os.path.basename(str(path or "").strip())
        stem, ext = os.path.splitext(base)
        return stem, ext.lower()

    @staticmethod
    def _is_uuid_stem(stem: str) -> bool:
        if not stem:
            return False
        return bool(UUID_STEM_RE.match(stem) or UUID_HYPHEN_STEM_RE.match(stem))
