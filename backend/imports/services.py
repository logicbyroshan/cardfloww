"""
Central Import Service for Data Ingestion, Table Creation, Bulk Upload, and Reupload

Features:
- Unified parser for Excel (.xlsx, .xls), CSV, and Word (.docx).
- Embedded Photo Extraction: Saves cell-embedded photos directly to disk and assigns them to card fields.
- Fast multi-ZIP photo matching.
- High-speed bulk database insertion with atomic transactions.
"""
import os
import json
import logging
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field

from django.db import transaction
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from tables.models import Table, IDCard
from organisation.models import Organisation
from mediafiles.services import ImageService, MediaNameService
from core.services.activity_service import ActivityService

from .column_detector import detect_table_schema_from_headers
from .excel_reader import parse_excel_or_csv, ParsedSpreadsheet, ExtractedImage
from .docx_reader import parse_docx_tables
from .reupload_matcher import ReuploadMatcher, MatchResult

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    success: bool
    message: str = ''
    table_id: Optional[int] = None
    table_name: str = ''
    cards_created: int = 0
    photos_imported: int = 0
    embedded_photos_count: int = 0
    errors: List[str] = field(default_factory=list)


class ImportService:
    """
    Central orchestration service for all import & ingestion operations.
    """

    @classmethod
    def parse_file(cls, file_bytes: bytes, filename: str) -> ParsedSpreadsheet:
        """Parse file based on extension (.xlsx, .xls, .csv, .docx)."""
        fn = filename.lower().strip()
        if fn.endswith('.docx'):
            return parse_docx_tables(file_bytes)
        else:
            return parse_excel_or_csv(file_bytes, filename)

    @classmethod
    def preview_data(cls, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Generate preview metadata, detected schema, and embedded photos count.
        """
        parsed = cls.parse_file(file_bytes, filename)
        schema = detect_table_schema_from_headers(parsed.headers, parsed.rows[:10])

        return {
            'success': True,
            'filename': filename,
            'headers': parsed.headers,
            'total_rows': parsed.total_rows,
            'total_embedded_images': parsed.total_embedded_images,
            'sample_rows': parsed.rows[:5],
            'detected_schema': schema,
        }

    @classmethod
    def create_table_with_data(
        cls,
        group_id: int,
        file_bytes: bytes,
        filename: str,
        table_name: Optional[str] = None,
        custom_fields: Optional[List[Dict[str, Any]]] = None,
        zip_files: Optional[List[Any]] = None,
        user: Any = None,
    ) -> ImportResult:
        """
        Create a new Table and import all records + embedded cell photos + ZIP photos in one step.
        """
        org = Organisation.objects.filter(id=group_id).first()
        if not org:
            # Fallback to first available organisation
            org = Organisation.objects.first()
        if not org:
            return ImportResult(success=False, message="Organisation not found.")

        # 1. Parse File
        try:
            parsed = cls.parse_file(file_bytes, filename)
        except Exception as exc:
            return ImportResult(success=False, message=f"Failed to parse document: {exc}")

        if not parsed.headers or not parsed.rows:
            return ImportResult(success=False, message="No data rows found in the uploaded file.")

        # 2. Determine Fields
        table_fields = custom_fields if custom_fields else detect_table_schema_from_headers(parsed.headers, parsed.rows[:10])

        # 3. Create Table
        resolved_table_name = table_name.strip() if table_name and table_name.strip() else os.path.splitext(filename)[0]
        with transaction.atomic():
            table = Table.objects.create(
                organisation=org,
                name=resolved_table_name,
                fields=table_fields,
                is_active=True,
            )

        # 4. Map and Save Cards + Embedded Images
        return cls._save_cards_and_media(
            table=table,
            parsed=parsed,
            field_mapping={h: h for h in parsed.headers},
            zip_files=zip_files,
            user=user,
        )

    @classmethod
    def upload_data_to_existing_table(
        cls,
        table_id: int,
        file_bytes: bytes,
        filename: str,
        field_mapping: Optional[Dict[str, str]] = None,
        zip_files: Optional[List[Any]] = None,
        user: Any = None,
    ) -> ImportResult:
        """
        Append records + embedded photos + ZIP photos to an existing Table.
        """
        try:
            table = Table.objects.select_related('organisation').get(id=table_id)
        except Table.DoesNotExist:
            return ImportResult(success=False, message="Table not found.")

        # 1. Parse File
        try:
            parsed = cls.parse_file(file_bytes, filename)
        except Exception as exc:
            return ImportResult(success=False, message=f"Failed to parse document: {exc}")

        if not parsed.headers or not parsed.rows:
            return ImportResult(success=False, message="No data rows found in the uploaded file.")

        # Auto-match headers if no mapping provided
        if not field_mapping:
            field_mapping = {}
            for tf in (table.fields or []):
                tf_norm = tf['name'].lower().replace('_', '').replace(' ', '')
                for h in parsed.headers:
                    h_norm = h.lower().replace('_', '').replace(' ', '')
                    if tf_norm == h_norm:
                        field_mapping[tf['name']] = h
                        break

        # 2. Map and Save Cards + Media
        return cls._save_cards_and_media(
            table=table,
            parsed=parsed,
            field_mapping=field_mapping,
            zip_files=zip_files,
            user=user,
        )

    @classmethod
    def _save_cards_and_media(
        cls,
        table: Table,
        parsed: ParsedSpreadsheet,
        field_mapping: Dict[str, str],
        zip_files: Optional[List[Any]] = None,
        user: Any = None,
    ) -> ImportResult:
        """
        Internal batch worker — two-pass approach:
        Pass 1: Build card records and bulk_create to get PKs.
        Pass 2: Save embedded/ZIP photos with managed media names and bulk_update.
        """
        org = getattr(table, 'organisation', None)

        # Map embedded images by (row_idx, col_idx or field_name)
        embedded_img_map: Dict[Tuple[int, str], bytes] = {}
        for img in parsed.embedded_images:
            embedded_img_map[(img.row_idx, img.field_name.upper())] = img.image_bytes
            embedded_img_map[(img.row_idx, str(img.col_idx))] = img.image_bytes

        # Read ZIP photos if provided
        zip_photos_by_stem: Dict[str, Tuple[str, bytes]] = {}
        if zip_files:
            import zipfile
            for zf_obj in zip_files:
                try:
                    with zipfile.ZipFile(zf_obj, 'r') as zf:
                        for entry in zf.infolist():
                            if entry.is_dir():
                                continue
                            fname = os.path.basename(entry.filename)
                            stem, ext = os.path.splitext(fname)
                            if ext.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.bmp'):
                                norm = stem.lower().replace('_', '').replace('-', '').strip()
                                if norm:
                                    zip_photos_by_stem[norm] = (fname, zf.read(entry))
                except Exception as zerr:
                    logger.warning("Error reading uploaded ZIP: %s", zerr)

        table_fields = table.fields or []
        header_to_idx = {h: idx for idx, h in enumerate(parsed.headers)}

        # ── Pass 1: Build card records (photo fields get placeholder paths) ──
        cards_to_create: List[IDCard] = []
        # Track which (row_idx, field_name) needs photo saving after PK assignment
        deferred_photos: List[Tuple[int, str, bytes, str]] = []  # (row_idx, field_name, img_bytes, ext)

        for r_idx, row_values in enumerate(parsed.rows):
            card_field_data = {}

            for tf in table_fields:
                tf_name = tf['name']
                tf_type = (tf.get('type') or 'text').lower()
                mapped_header = field_mapping.get(tf_name)

                cell_value = ''
                col_idx = None
                if mapped_header and mapped_header in header_to_idx:
                    col_idx = header_to_idx[mapped_header]
                    if col_idx < len(row_values):
                        cell_value = str(row_values[col_idx] or '').strip()

                is_photo_field = (
                    tf_type in ('photo', 'father_photo', 'mother_photo', 'sign', 'image', 'signature')
                    or 'photo' in tf_name.lower()
                    or 'sign' in tf_name.lower()
                )

                if is_photo_field:
                    # Check 1: Embedded cell image
                    embedded_data = None
                    if mapped_header:
                        embedded_data = embedded_img_map.get((r_idx, mapped_header.upper()))
                    if not embedded_data and col_idx is not None:
                        embedded_data = embedded_img_map.get((r_idx, str(col_idx)))

                    if embedded_data:
                        # Defer photo save until we have card PK
                        deferred_photos.append((r_idx, tf_name, embedded_data, '.jpg'))
                        card_field_data[tf_name] = '__DEFERRED__'
                        continue

                    # Check 2: ZIP matching by cell filename value
                    if cell_value:
                        stem = os.path.splitext(os.path.basename(cell_value))[0].lower().replace('_', '').replace('-', '').strip()
                        if stem in zip_photos_by_stem:
                            orig_fn, img_bytes = zip_photos_by_stem[stem]
                            ext = os.path.splitext(orig_fn)[1].lower() or '.jpg'
                            deferred_photos.append((r_idx, tf_name, img_bytes, ext))
                            card_field_data[tf_name] = '__DEFERRED__'
                        else:
                            card_field_data[tf_name] = f"PENDING:{cell_value}"
                    else:
                        card_field_data[tf_name] = ''
                else:
                    card_field_data[tf_name] = cell_value

            card = IDCard(
                table=table,
                field_data=card_field_data,
                status='pending',
            )
            cards_to_create.append(card)

        # Bulk insert to get PKs
        with transaction.atomic():
            IDCard.objects.bulk_create(cards_to_create, batch_size=250)

        # ── Pass 2: Save deferred photos with managed media names ──
        photos_imported = 0
        cards_to_update = []
        cards_needing_update: Dict[int, IDCard] = {}  # pk -> card

        for r_idx, tf_name, img_bytes, ext in deferred_photos:
            if r_idx >= len(cards_to_create):
                continue
            card = cards_to_create[r_idx]

            # Generate managed filename using card PK
            if org:
                filename = MediaNameService.generate_media_name_for_card(
                    org, card.id, tf_name, version=1, ext=ext
                )
            else:
                filename = f"{card.id}_{tf_name}{ext}"

            rel_path = f"idcard_photos/{table.id}/{filename}"

            try:
                if default_storage.exists(rel_path):
                    default_storage.delete(rel_path)
                default_storage.save(rel_path, ContentFile(img_bytes))
                try:
                    ImageService.create_thumbnail(rel_path)
                except Exception:
                    pass

                fd = card.field_data or {}
                fd[tf_name] = rel_path
                card.field_data = fd
                cards_needing_update[card.pk] = card
                photos_imported += 1
            except Exception as save_err:
                logger.warning("Failed saving photo for card %s field %s: %s", card.id, tf_name, save_err)
                fd = card.field_data or {}
                fd[tf_name] = ''
                card.field_data = fd
                cards_needing_update[card.pk] = card

        # Batch update cards that got photos
        if cards_needing_update:
            with transaction.atomic():
                IDCard.objects.bulk_update(
                    list(cards_needing_update.values()), ['field_data'], batch_size=200
                )

        # Log Activity
        try:
            if user:
                ActivityService.log_cards_created(
                    request=None,
                    user=user,
                    table_id=table.id,
                    card_count=len(cards_to_create),
                    source='bulk_import'
                )
        except Exception:
            pass


        return ImportResult(
            success=True,
            message=f"Successfully imported {len(cards_to_create)} records with {photos_imported} photos into '{table.name}'.",
            table_id=table.id,
            table_name=table.name,
            cards_created=len(cards_to_create),
            photos_imported=photos_imported,
            embedded_photos_count=parsed.total_embedded_images,
        )

    @classmethod
    def reupload_images(
        cls,
        table_id: int,
        zip_file_obj,
        target_field: Optional[str] = None,
        status: Optional[str] = None,
        user: Any = None,
    ) -> MatchResult:
        """
        Match and update card photos from uploaded ZIP.
        """
        table = Table.objects.get(id=table_id)
        matcher = ReuploadMatcher(table)
        result = matcher.match_and_update_from_zip(
            zip_file_obj=zip_file_obj,
            target_field=target_field,
            status=status,
        )
        return result
