"""
High-Speed Photo Reupload & Filename Matching Engine

Features:
- Matches ZIP photo filenames against student card records by:
  1. Exact pending path / filename match (PENDING:101.jpg -> 101.jpg)
  2. Roll No / Serial No / Admission No match (101.jpg -> Roll 101)
  3. Normalized Student Name match (rahul_sharma.jpg -> Rahul Sharma)
  4. Card ID match (card_12.jpg -> ID 12)
- Multi-field aware: updates PHOTO, FATHER_PHOTO, MOTHER_PHOTO, SIGN
- Generates high-speed Pillow thumbnails and persists records in batch transactions
"""
import os
import re
import io
import zipfile
import logging
from typing import Dict, Any, List, Tuple, Optional, Set
from dataclasses import dataclass, field

from django.conf import settings
from django.db import transaction
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from tables.models import Table, IDCard
from mediafiles.services import ImageService

logger = logging.getLogger(__name__)

_NORM_CLEAN_RE = re.compile(r'[^a-zA-Z0-9]')


def normalize_stem(stem: str) -> str:
    """Normalize a filename stem or identifier for fast canonical matching."""
    if not stem:
        return ''
    return _NORM_CLEAN_RE.sub('', str(stem).strip().lower())


@dataclass
class MatchResult:
    matched_cards: int = 0
    updated_photos: int = 0
    unmatched_files: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class ReuploadMatcher:
    """
    Orchestrates high-speed photo matching from a ZIP file against table cards.
    """

    def __init__(self, table: Table):
        self.table = table
        self.table_fields = table.fields or []
        self.image_field_names = [
            f.get('name') for f in self.table_fields
            if (f.get('type') or '').lower() in ('photo', 'image', 'signature', 'sign', 'father_photo', 'mother_photo')
            or 'photo' in f.get('name', '').lower()
            or 'pic' in f.get('name', '').lower()
            or 'sign' in f.get('name', '').lower()
        ]

    def match_and_update_from_zip(
        self,
        zip_file_obj,
        target_field: Optional[str] = None,
        status: Optional[str] = None,
    ) -> MatchResult:
        """
        Extract photos from ZIP, match against table cards, and update card records.
        """
        result = MatchResult()

        if not self.image_field_names:
            result.errors.append("No image fields configured in this table.")
            return result

        fields_to_process = [target_field] if target_field and target_field in self.image_field_names else self.image_field_names

        # 1. Read ZIP files into in-memory/disk store
        zip_photos: Dict[str, Tuple[str, bytes]] = {}  # { norm_stem: (original_filename, bytes) }
        try:
            with zipfile.ZipFile(zip_file_obj, 'r') as zf:
                for entry in zf.infolist():
                    if entry.is_dir():
                        continue
                    fname = os.path.basename(entry.filename)
                    if not fname or fname.startswith(('.', '__MACOSX')):
                        continue
                    stem, ext = os.path.splitext(fname)
                    if ext.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.bmp'):
                        norm = normalize_stem(stem)
                        if norm:
                            zip_photos[norm] = (fname, zf.read(entry))
        except Exception as exc:
            result.errors.append(f"Failed to read ZIP archive: {exc}")
            return result

        if not zip_photos:
            result.errors.append("No valid image files (.jpg, .png, .webp) found in the ZIP archive.")
            return result

        # 2. Fetch cards
        cards_qs = IDCard.objects.filter(table=self.table)
        if status and status.lower() not in ('all', ''):
            cards_qs = cards_qs.filter(status=status.lower())

        cards = list(cards_qs)
        if not cards:
            result.errors.append("No cards found in table to match photos against.")
            return result

        # 3. Match each card against ZIP photos
        cards_to_update = []
        matched_stems: Set[str] = set()

        for card in cards:
            fd = card.field_data or {}
            card_updated = False

            # Extract card identifiers
            roll_val = normalize_stem(str(fd.get('ROLL NO') or fd.get('Roll No') or fd.get('SR NO') or fd.get('ADM NO') or ''))
            name_val = normalize_stem(str(fd.get('FULL NAME') or fd.get('NAME') or fd.get('Student Name') or ''))
            id_val = normalize_stem(str(card.id))

            for f_name in fields_to_process:
                current_val = str(fd.get(f_name) or '').strip()
                matched_photo = None
                matched_stem_key = None

                # Priority A: Check pending reference stem (e.g. PENDING:101.jpg -> 101)
                if current_val.startswith('PENDING:'):
                    pending_stem = normalize_stem(os.path.splitext(current_val.replace('PENDING:', ''))[0])
                    if pending_stem in zip_photos:
                        matched_photo = zip_photos[pending_stem]
                        matched_stem_key = pending_stem

                # Priority B: Check existing filename stem
                if not matched_photo and current_val:
                    existing_stem = normalize_stem(os.path.splitext(os.path.basename(current_val))[0])
                    if existing_stem in zip_photos:
                        matched_photo = zip_photos[existing_stem]
                        matched_stem_key = existing_stem

                # Priority C: Check Roll No / Adm No
                if not matched_photo and roll_val and roll_val in zip_photos:
                    matched_photo = zip_photos[roll_val]
                    matched_stem_key = roll_val

                # Priority D: Check Card ID
                if not matched_photo and id_val and id_val in zip_photos:
                    matched_photo = zip_photos[id_val]
                    matched_stem_key = id_val

                # Priority E: Check Full Name
                if not matched_photo and name_val and name_val in zip_photos:
                    matched_photo = zip_photos[name_val]
                    matched_stem_key = name_val

                # If matched, save image to disk and update card field_data
                if matched_photo:
                    orig_fname, img_bytes = matched_photo
                    ext = os.path.splitext(orig_fname)[1].lower() or '.jpg'

                    # Save photo to media storage
                    rel_path = f"idcard_photos/{self.table.id}/{card.id}_{f_name}{ext}"
                    try:
                        if default_storage.exists(rel_path):
                            default_storage.delete(rel_path)
                        default_storage.save(rel_path, ContentFile(img_bytes))

                        # Generate thumbnail
                        try:
                            ImageService.create_thumbnail(rel_path)
                        except Exception:
                            pass

                        fd[f_name] = rel_path
                        card.field_data = fd
                        card_updated = True
                        result.updated_photos += 1
                        matched_stems.add(matched_stem_key)
                    except Exception as save_err:
                        logger.warning("Failed to save reuploaded image %s: %s", rel_path, save_err)

            if card_updated:
                cards_to_update.append(card)
                result.matched_cards += 1

        # 4. Batch commit updates
        if cards_to_update:
            with transaction.atomic():
                IDCard.objects.bulk_update(cards_to_update, ['field_data'], batch_size=200)

        # 5. Record unmatched files
        for norm_stem, (orig_fname, _) in zip_photos.items():
            if norm_stem not in matched_stems:
                result.unmatched_files.append(orig_fname)

        return result
