"""
High-Performance Photo Reupload & Dual-Path Matching Engine

Architecture:
  1. CLASSIFY — Stream ZIP entries and classify each filename:
     - Managed (O<OrgCode>_<ImageCode>V<Version>.ext):
       * Own org → version-increment re-upload
       * Other org → reject instantly (O(1), zero DB, zero I/O)
     - Unmanaged (0001.jpg, IMG_1234.jpg, student_name.jpg):
       * Match against pre-indexed in-memory card import map

  2. MATCH — Pre-load all card records into O(1) lookup dictionaries:
     - pending_map:  PENDING:filename → card
     - roll_map:     normalized roll/serial/admission number → card
     - name_map:     normalized full name → card
     - id_map:       card PK → card
     - managed_map:  image_code → (card, field_name)

  3. EXTRACT & SAVE — Only extract+write the matched entries from the ZIP.
     Never extract rejected/unmatched files.

  4. COMMIT — Batch-update all modified cards in a single atomic transaction.

Performance:
  - Zero N+1 DB queries (all lookups are in-memory)
  - Streaming ZIP — reads ZipFile.infolist() without extracting unmatched entries
  - O(1) org rejection for foreign managed files
"""
import os
import re
import zipfile
import logging
from typing import Dict, Any, List, Tuple, Optional, Set
from dataclasses import dataclass, field

from django.db import transaction
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from tables.models import Table, IDCard
from mediafiles.services import ImageService, MediaNameService

logger = logging.getLogger(__name__)

_NORM_CLEAN_RE = re.compile(r'[^a-zA-Z0-9]')

# Valid image extensions for ZIP scanning
_IMAGE_EXTS = frozenset(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.heic', '.heif'))


def normalize_stem(stem: str) -> str:
    """Normalize a filename stem or identifier for fast canonical matching."""
    if not stem:
        return ''
    return _NORM_CLEAN_RE.sub('', str(stem).strip().lower())


@dataclass
class ReuploadTelemetry:
    """Detailed execution telemetry for the reupload engine."""
    scanned_count: int = 0
    matched_count: int = 0
    reupload_versions_count: int = 0
    skipped_other_org_count: int = 0
    unmatched_count: int = 0
    updated_photos: int = 0
    matched_cards: int = 0
    errors: List[str] = field(default_factory=list)
    unmatched_files: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'scanned_count': self.scanned_count,
            'matched_count': self.matched_count,
            'reupload_versions_count': self.reupload_versions_count,
            'skipped_other_org_count': self.skipped_other_org_count,
            'unmatched_count': self.unmatched_count,
            'updated_photos': self.updated_photos,
            'matched_cards': self.matched_cards,
            'errors': self.errors,
            'unmatched_files': self.unmatched_files[:50],  # Cap for response size
        }


# Legacy MatchResult alias for backward compatibility
@dataclass
class MatchResult:
    matched_cards: int = 0
    updated_photos: int = 0
    unmatched_files: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class ReuploadMatcher:
    """
    High-Performance Dual-Path Reupload Engine.

    Orchestrates streaming ZIP classification, in-memory card matching,
    and batch persistence with zero N+1 queries.
    """

    def __init__(self, table: Table):
        self.table = table
        self.organisation = getattr(table, 'organisation', None)
        self.table_fields = table.fields or []
        self.image_field_names = self._detect_image_fields()

    def _detect_image_fields(self) -> List[str]:
        """Detect all image/photo/signature field names from table schema."""
        image_fields = []
        for f in self.table_fields:
            f_type = (f.get('type') or '').lower()
            f_name = f.get('name', '')
            f_name_lower = f_name.lower()
            if (f_type in ('photo', 'image', 'signature', 'sign', 'father_photo', 'mother_photo', 'rel_photo')
                    or 'photo' in f_name_lower
                    or 'pic' in f_name_lower
                    or 'sign' in f_name_lower):
                image_fields.append(f_name)
        return image_fields

    def _build_lookup_maps(self, cards: List[IDCard]) -> dict:
        """
        Pre-index all card records into O(1) lookup dictionaries.

        Returns dict with:
            pending_map:   { normalized_pending_stem: (card, field_name) }
            existing_map:  { normalized_existing_stem: (card, field_name) }
            roll_map:      { normalized_roll: card }
            name_map:      { normalized_name: card }
            id_map:        { normalized_card_id: card }
            managed_map:   { image_code: (card, field_name, current_version) }
        """
        pending_map = {}
        existing_map = {}
        roll_map = {}
        name_map = {}
        id_map = {}
        managed_map = {}

        for card in cards:
            fd = card.field_data or {}

            # Index by card ID
            id_map[normalize_stem(str(card.id))] = card

            # Index by roll/serial/admission number
            for key in ('ROLL NO', 'Roll No', 'SR NO', 'Sr No', 'ADM NO', 'Adm No',
                        'SERIAL NO', 'Serial No', 'ADMISSION NO', 'Admission No',
                        'roll_no', 'sr_no', 'adm_no', 'serial_no', 'admission_no'):
                val = str(fd.get(key) or '').strip()
                if val:
                    norm = normalize_stem(val)
                    if norm and norm not in roll_map:
                        roll_map[norm] = card
                    break  # Only use first found identifier

            # Index by full name
            for key in ('FULL NAME', 'NAME', 'Student Name', 'Full Name',
                        'full_name', 'name', 'student_name', 'STUDENT NAME'):
                val = str(fd.get(key) or '').strip()
                if val:
                    norm = normalize_stem(val)
                    if norm and norm not in name_map:
                        name_map[norm] = card
                    break

            # Index pending and existing photo paths per image field
            for f_name in self.image_field_names:
                current_val = str(fd.get(f_name) or '').strip()

                if current_val.startswith('PENDING:'):
                    pending_stem = normalize_stem(
                        os.path.splitext(current_val.replace('PENDING:', ''))[0]
                    )
                    if pending_stem:
                        pending_map[pending_stem] = (card, f_name)
                elif current_val:
                    # Index by existing filename stem
                    existing_stem = normalize_stem(
                        os.path.splitext(os.path.basename(current_val))[0]
                    )
                    if existing_stem:
                        existing_map[existing_stem] = (card, f_name)

                    # If it's a managed name, index by image_code for version tracking
                    parsed = MediaNameService.parse_media_name(current_val)
                    if parsed and parsed.get('is_managed'):
                        managed_map[parsed['image_code']] = (card, f_name, parsed['version'])

        return {
            'pending_map': pending_map,
            'existing_map': existing_map,
            'roll_map': roll_map,
            'name_map': name_map,
            'id_map': id_map,
            'managed_map': managed_map,
        }

    def match_and_update_from_zip(
        self,
        zip_file_obj,
        target_field: Optional[str] = None,
        status: Optional[str] = None,
    ) -> MatchResult:
        """
        Dual-path ZIP reupload engine.

        Phase 1: Scan ZIP index (no extraction)
        Phase 2: Classify each entry (Managed own / Managed other / Unmanaged)
        Phase 3: Match against pre-indexed card lookup maps
        Phase 4: Extract only matched entries and save to storage
        Phase 5: Batch-commit all card updates

        Returns:
            MatchResult with counts and unmatched file list.
        """
        telemetry = ReuploadTelemetry()
        result = MatchResult()

        if not self.image_field_names:
            result.errors.append("No image fields configured in this table.")
            return result

        fields_to_process = (
            [target_field] if target_field and target_field in self.image_field_names
            else self.image_field_names
        )

        # ── Phase 1: Scan ZIP index ──
        try:
            zf = zipfile.ZipFile(zip_file_obj, 'r')
        except Exception as exc:
            result.errors.append(f"Failed to read ZIP archive: {exc}")
            return result

        # Build list of candidate entries (files only, valid image extensions)
        candidates = []  # [(ZipInfo, basename, stem_norm, ext)]
        try:
            for entry in zf.infolist():
                if entry.is_dir():
                    continue
                fname = os.path.basename(entry.filename)
                if not fname or fname.startswith(('.', '__MACOSX')):
                    continue
                stem, ext = os.path.splitext(fname)
                if ext.lower() not in _IMAGE_EXTS:
                    continue
                telemetry.scanned_count += 1
                candidates.append((entry, fname, normalize_stem(stem), ext.lower()))
        except Exception as exc:
            zf.close()
            result.errors.append(f"Failed to scan ZIP contents: {exc}")
            return result

        if not candidates:
            zf.close()
            result.errors.append("No valid image files found in the ZIP archive.")
            return result

        # ── Phase 2: Classify ──
        org = self.organisation
        own_org_code = MediaNameService.get_org_code(org) if org else None

        # Separate into managed-own, managed-other, and unmanaged
        own_managed_entries = []   # [(entry, fname, parsed)]
        unmanaged_entries = []     # [(entry, fname, stem_norm, ext)]

        for entry, fname, stem_norm, ext in candidates:
            parsed = MediaNameService.parse_media_name(fname)

            if parsed and parsed.get('is_managed'):
                if own_org_code and parsed['org_code'] == own_org_code:
                    own_managed_entries.append((entry, fname, parsed))
                else:
                    # Other org — reject instantly
                    telemetry.skipped_other_org_count += 1
            else:
                # Unmanaged or legacy — goes to import-map matching
                unmanaged_entries.append((entry, fname, stem_norm, ext))

        # ── Phase 3: Load cards and build lookup maps ──
        cards_qs = IDCard.objects.filter(table=self.table)
        if status and status.lower() not in ('all', ''):
            cards_qs = cards_qs.filter(status=status.lower())

        cards = list(cards_qs)
        if not cards:
            zf.close()
            result.errors.append("No cards found in table to match photos against.")
            return result

        maps = self._build_lookup_maps(cards)
        pending_map = maps['pending_map']
        existing_map = maps['existing_map']
        roll_map = maps['roll_map']
        name_map = maps['name_map']
        id_map = maps['id_map']
        managed_map = maps['managed_map']

        # Track which cards were modified (set of card PKs)
        modified_cards: Dict[int, IDCard] = {}
        matched_entries: Set[str] = set()  # stems already matched

        # ── Phase 4A: Process own-org managed re-uploads ──
        for entry, fname, parsed in own_managed_entries:
            image_code = parsed['image_code']
            if image_code in managed_map:
                card, field_name, current_version = managed_map[image_code]
                new_version = parsed['version']  # Use the higher of existing or incoming + 1
                actual_next_version = max(current_version + 1, new_version)

                try:
                    img_bytes = zf.read(entry)
                    ext = parsed['ext']

                    # Generate new managed filename with incremented version
                    new_filename = MediaNameService.generate_media_name(
                        parsed['org_code'], image_code, actual_next_version, ext
                    )
                    rel_path = f"idcard_photos/{self.table.id}/{new_filename}"

                    if default_storage.exists(rel_path):
                        default_storage.delete(rel_path)
                    default_storage.save(rel_path, ContentFile(img_bytes))

                    try:
                        ImageService.create_thumbnail(rel_path)
                    except Exception:
                        pass

                    fd = card.field_data or {}
                    fd[field_name] = rel_path
                    card.field_data = fd
                    modified_cards[card.pk] = card
                    telemetry.reupload_versions_count += 1
                    telemetry.updated_photos += 1
                    telemetry.matched_count += 1

                    # Update managed_map version for subsequent re-uploads in same batch
                    managed_map[image_code] = (card, field_name, actual_next_version)
                except Exception as save_err:
                    logger.warning("Failed to save managed re-upload %s: %s", fname, save_err)
                    telemetry.errors.append(f"Save error for {fname}: {save_err}")
            else:
                # Managed name for this org but no matching card — treat as unmatched
                telemetry.unmatched_count += 1
                telemetry.unmatched_files.append(fname)

        # ── Phase 4B: Process unmanaged files via import map ──
        for entry, fname, stem_norm, ext in unmanaged_entries:
            matched_card = None
            matched_field = None

            # Priority A: Pending path match
            if stem_norm in pending_map:
                matched_card, matched_field = pending_map[stem_norm]

            # Priority B: Existing filename match
            if not matched_card and stem_norm in existing_map:
                matched_card, matched_field = existing_map[stem_norm]

            # Priority C: Roll / Adm / Serial number match
            if not matched_card and stem_norm in roll_map:
                matched_card = roll_map[stem_norm]
                matched_field = fields_to_process[0] if fields_to_process else None

            # Priority D: Card ID match
            if not matched_card and stem_norm in id_map:
                matched_card = id_map[stem_norm]
                matched_field = fields_to_process[0] if fields_to_process else None

            # Priority E: Full name match
            if not matched_card and stem_norm in name_map:
                matched_card = name_map[stem_norm]
                matched_field = fields_to_process[0] if fields_to_process else None

            if matched_card and matched_field:
                try:
                    img_bytes = zf.read(entry)

                    # Generate managed filename for this new assignment
                    if org:
                        new_filename = MediaNameService.generate_media_name_for_card(
                            org, matched_card.id, matched_field, version=1, ext=ext
                        )
                    else:
                        new_filename = f"{matched_card.id}_{matched_field}{ext}"

                    rel_path = f"idcard_photos/{self.table.id}/{new_filename}"

                    if default_storage.exists(rel_path):
                        default_storage.delete(rel_path)
                    default_storage.save(rel_path, ContentFile(img_bytes))

                    try:
                        ImageService.create_thumbnail(rel_path)
                    except Exception:
                        pass

                    fd = matched_card.field_data or {}
                    fd[matched_field] = rel_path
                    matched_card.field_data = fd
                    modified_cards[matched_card.pk] = matched_card
                    telemetry.matched_count += 1
                    telemetry.updated_photos += 1
                except Exception as save_err:
                    logger.warning("Failed to save unmanaged match %s: %s", fname, save_err)
                    telemetry.errors.append(f"Save error for {fname}: {save_err}")
            else:
                telemetry.unmatched_count += 1
                telemetry.unmatched_files.append(fname)

        zf.close()

        # ── Phase 5: Batch commit ──
        if modified_cards:
            cards_list = list(modified_cards.values())
            telemetry.matched_cards = len(cards_list)
            with transaction.atomic():
                IDCard.objects.bulk_update(cards_list, ['field_data'], batch_size=200)

        # Populate legacy MatchResult for backward compatibility
        result.matched_cards = telemetry.matched_cards
        result.updated_photos = telemetry.updated_photos
        result.unmatched_files = telemetry.unmatched_files
        result.errors = telemetry.errors

        logger.info(
            "Reupload complete for table %s: scanned=%d matched=%d versions=%d "
            "skipped_other_org=%d unmatched=%d",
            self.table.id,
            telemetry.scanned_count,
            telemetry.matched_count,
            telemetry.reupload_versions_count,
            telemetry.skipped_other_org_count,
            telemetry.unmatched_count,
        )

        return result
"""
from .reupload_matcher import ReuploadMatcher, MatchResult
"""
