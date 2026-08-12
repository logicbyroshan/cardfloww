"""
Ensure missing thumbnails exist for card image paths.

Safety model:
- Dry-run by default.
- Never modifies original images.
- Only creates missing thumbnail files.

Usage:
    python manage.py ensure_missing_card_thumbnails
    python manage.py ensure_missing_card_thumbnails --apply
    python manage.py ensure_missing_card_thumbnails --apply --client-id 12
    python manage.py ensure_missing_card_thumbnails --apply --table-id 45
"""

from urllib.parse import urlparse
from typing import Set

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from core.services.base import BaseService
from tables.models import IDCard
from mediafiles.services import ImageService
from mediafiles.services.image_thumbnail import ThumbnailService


class Command(BaseCommand):
    help = "Find card image paths and create missing thumbnails."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Actually create thumbnails. Default is dry-run.",
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
            default=400,
            help="Iterator chunk size. Default: 400",
        )

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        client_id = options.get("client_id")
        table_id = options.get("table_id")
        batch_size = max(1, int(options.get("batch_size") or 400))

        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(f"\n=== ensure_missing_card_thumbnails ({mode}) ===\n")

        qs = IDCard.objects.select_related("table").only(
            "id",
            "table_id",
            "table__fields",
            "field_data",
            "photo",
        )
        if client_id:
            qs = qs.filter(table__group__client_id=client_id)
        if table_id:
            qs = qs.filter(table_id=table_id)

        scanned_cards = 0
        candidate_paths = 0
        originals_missing = 0
        thumbs_existing = 0
        thumbs_missing = 0
        thumbs_created = 0
        errors = 0
        created_examples = []

        seen_paths: Set[str] = set()

        for card in qs.iterator(chunk_size=batch_size):
            scanned_cards += 1
            paths = self._collect_card_image_paths(card)
            for path in paths:
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                candidate_paths += 1

                if not default_storage.exists(path):
                    originals_missing += 1
                    continue

                thumb_path = ThumbnailService.get_thumbnail_path(path)
                if not thumb_path:
                    continue

                if default_storage.exists(thumb_path):
                    thumbs_existing += 1
                    continue

                thumbs_missing += 1
                if apply:
                    try:
                        created = ThumbnailService.ensure_thumbnail_exists(path)
                        if created:
                            thumbs_created += 1
                            if len(created_examples) < 10:
                                created_examples.append((path, created))
                    except Exception:
                        errors += 1

        self.stdout.write("\nSummary")
        self.stdout.write(f"  Scanned cards: {scanned_cards}")
        self.stdout.write(f"  Unique candidate image paths: {candidate_paths}")
        self.stdout.write(f"  Missing original files: {originals_missing}")
        self.stdout.write(f"  Existing thumbnails: {thumbs_existing}")
        self.stdout.write(f"  Missing thumbnails: {thumbs_missing}")
        self.stdout.write(f"  Errors: {errors}")

        if apply:
            self.stdout.write(f"  Thumbnails created: {thumbs_created}")
            if created_examples:
                self.stdout.write("  Created thumbnail paths:")
                for original_path, thumb_path in created_examples:
                    self.stdout.write(f"    {original_path} -> /media/{thumb_path}")
            self.stdout.write(self.style.SUCCESS("\nDone. Missing thumbnails processed."))
        else:
            self.stdout.write(self.style.WARNING("\nDry-run only. Re-run with --apply to create thumbnails."))

    def _collect_card_image_paths(self, card):
        fd = card.field_data if isinstance(card.field_data, dict) else {}
        image_field_names = set(ImageService.get_image_field_names(card.table.fields or []))
        paths = []

        # Include all configured image fields.
        for field_name in image_field_names:
            value = fd.get(field_name, "")
            value = self._normalize_image_value(value)
            if value:
                paths.append(value)

        # Include PHOTO-like keys from legacy/mobile payloads.
        for k, v in fd.items():
            if str(k).strip().lower() == "photo":
                value = self._normalize_image_value(v)
                if value:
                    paths.append(value)

        # Legacy field fallback.
        try:
            photo_name = str(card.photo.name or "").strip()
        except Exception:
            photo_name = ""
        if photo_name:
            value = self._normalize_image_value(photo_name)
            if value:
                paths.append(value)

        return paths

    @staticmethod
    def _normalize_image_value(value):
        if not value:
            return ""
        text = str(value).strip()
        if not text or text == "NOT_FOUND" or text.startswith("PENDING:"):
            return ""

        if text.startswith(("http://", "https://")):
            parsed = urlparse(text)
            text = parsed.path or ""

        text = text.split("?", 1)[0].split("#", 1)[0]

        normalized = BaseService.normalize_image_path(text)
        if not normalized:
            return ""
        if "." not in normalized:
            return ""
        return normalized
