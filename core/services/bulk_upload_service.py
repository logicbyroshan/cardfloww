"""
Bulk Upload Service Module

Handles disk-based ZIP extraction and shared row-processing logic
for both XLSX and CSV bulk uploads.

KEY DESIGN:
- ZIP images are extracted to disk (temp directory), NOT held in RAM.
- Small images (<256KB each, <50MB total) may be kept in RAM for speed.
- Row processing is unified across XLSX and CSV to eliminate code duplication.
- Batch processing uses bulk_create with transaction.atomic per batch.
"""
import os
import re
import json
import shutil
import logging
import tempfile
import zipfile
from collections import Counter

from django.conf import settings
from django.db import transaction
from django.core.files.storage import default_storage

from tables.models import IDCard
from ..services.base import BaseService
from tables.services_workflow import WorkflowService
from core.utils.field_utils import (
    validate_image_bytes,
)

logger = logging.getLogger(__name__)

# ── Constants ──
MAX_BULK_ROWS = 5000
BULK_BATCH_SIZE = 100
PER_FIELD_MAX_IMAGES = 5000
PER_FIELD_MAX_BYTES = 1024 * 1024 * 1024  # 1 GB total extracted
MAX_ZIP_IMAGES = 5000
MAX_ZIP_TOTAL_BYTES = 1024 * 1024 * 1024  # 1 GB uncompressed total
MAX_SINGLE_IMAGE_BYTES = 20 * 1024 * 1024  # Skip files > 20MB
# Threshold: if total ZIP content is small, keep in RAM for speed
RAM_THRESHOLD_BYTES = 50 * 1024 * 1024  # 50 MB
RAM_THRESHOLD_PER_IMAGE = 256 * 1024  # 256 KB per image

VALID_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic', '.heif'}


class DiskBackedImageStore:
    """
    Stores extracted ZIP images on disk (or in RAM for small datasets).
    
    Strategy:
    - If total extracted size < RAM_THRESHOLD_BYTES AND every image < RAM_THRESHOLD_PER_IMAGE:
      keep all images in a dict (fast, no disk I/O).
    - Otherwise: extract images to a temp directory on disk, load them
      one-at-a-time when needed during row processing.
    
    This prevents OOM when processing 5000 photos × 2MB = 10GB.
    """
    
    def __init__(
        self,
        *,
        ram_threshold_bytes=RAM_THRESHOLD_BYTES,
        ram_threshold_per_image=RAM_THRESHOLD_PER_IMAGE,
        force_ram_only=False,
    ):
        """
        Args:
            ram_threshold_bytes: Total in-memory budget before considering disk spill.
            ram_threshold_per_image: Per-image in-memory size budget.
            force_ram_only: When True, never spill to disk; raise MemoryError instead.
        """
        try:
            threshold_bytes = int(ram_threshold_bytes or RAM_THRESHOLD_BYTES)
        except (TypeError, ValueError):
            threshold_bytes = RAM_THRESHOLD_BYTES
        try:
            threshold_per_image = int(ram_threshold_per_image or RAM_THRESHOLD_PER_IMAGE)
        except (TypeError, ValueError):
            threshold_per_image = RAM_THRESHOLD_PER_IMAGE

        self._ram_threshold_bytes = max(1 * 1024 * 1024, threshold_bytes)
        self._ram_threshold_per_image = max(64 * 1024, threshold_per_image)
        if self._ram_threshold_per_image > self._ram_threshold_bytes:
            self._ram_threshold_per_image = self._ram_threshold_bytes

        self._force_ram_only = bool(force_ram_only)
        self._ram_store = {}       # { normalized_key: { bytes, ext, original_name } }
        self._disk_dir = None      # temp directory path (None if using RAM)
        self._disk_index = {}      # { normalized_key: { path, ext, original_name } }
        self._use_disk = False
        self._total_bytes = 0
        self._count = 0
    
    def _ensure_disk_dir(self):
        """Create temp directory for disk-based storage."""
        if self._disk_dir is None:
            self._disk_dir = tempfile.mkdtemp(
                prefix='bulk_upload_',
                dir=os.path.join(settings.MEDIA_ROOT, 'temp')
            )
            os.makedirs(self._disk_dir, exist_ok=True)
        return self._disk_dir
    
    def _switch_to_disk(self):
        """Move RAM-stored images to disk."""
        if self._force_ram_only:
            raise MemoryError(
                "RAM-only upload mode exceeded configured in-memory budget. "
                "Disable RAM-only mode or reduce ZIP payload size."
            )
        if self._use_disk:
            return
        self._use_disk = True
        disk_dir = self._ensure_disk_dir()
        # Move existing RAM entries to disk
        for key, info in self._ram_store.items():
            file_path = os.path.join(disk_dir, f"{key}{info['ext']}")
            with open(file_path, 'wb') as f:
                f.write(info['bytes'])
            self._disk_index[key] = {
                'path': file_path,
                'ext': info['ext'],
                'original_name': info['original_name'],
            }
        self._ram_store.clear()
    
    def add(self, normalized_key, image_bytes, ext, original_name):
        """Add an image to the store."""
        if not normalized_key:
            return
        
        byte_len = len(image_bytes)
        
        # Check if we need to switch to disk
        if not self._use_disk:
            would_exceed_ram = (
                (self._total_bytes + byte_len) > self._ram_threshold_bytes
                or byte_len > self._ram_threshold_per_image
            )
            if would_exceed_ram:
                if self._force_ram_only:
                    raise MemoryError(
                        "RAM-only upload mode exceeded configured in-memory budget. "
                        "Reduce ZIP payload size or image resolution."
                    )
                self._switch_to_disk()
        
        # Deterministic: if duplicate key, keep alphabetically-first filename
        if self._use_disk:
            existing = self._disk_index.get(normalized_key)
            if existing is not None and original_name >= existing['original_name']:
                return  # Keep existing
            disk_dir = self._ensure_disk_dir()
            file_path = os.path.join(disk_dir, f"{normalized_key}{ext}")
            with open(file_path, 'wb') as f:
                f.write(image_bytes)
            self._disk_index[normalized_key] = {
                'path': file_path,
                'ext': ext,
                'original_name': original_name,
            }
        else:
            existing = self._ram_store.get(normalized_key)
            if existing is not None and original_name >= existing['original_name']:
                return  # Keep existing
            self._ram_store[normalized_key] = {
                'bytes': image_bytes,
                'ext': ext,
                'original_name': original_name,
            }
        
        self._total_bytes += byte_len
        self._count += 1
    
    def get(self, normalized_key):
        """
        Get image data for a key.
        Returns { bytes, ext, original_name } or None.
        Loads from disk if needed (one image at a time → constant RAM).
        """
        if not normalized_key:
            return None
        
        if self._use_disk:
            info = self._disk_index.get(normalized_key)
            if info is None:
                return None
            try:
                with open(info['path'], 'rb') as f:
                    image_bytes = f.read()
                return {
                    'bytes': image_bytes,
                    'ext': info['ext'],
                    'original_name': info['original_name'],
                }
            except (IOError, OSError) as e:
                logger.warning("Failed to read image from disk: %s: %s", info['path'], e)
                return None
        else:
            return self._ram_store.get(normalized_key)
    
    def __contains__(self, normalized_key):
        if self._use_disk:
            return normalized_key in self._disk_index
        return normalized_key in self._ram_store
    
    def keys(self):
        if self._use_disk:
            return self._disk_index.keys()
        return self._ram_store.keys()
    
    def __len__(self):
        return self._count
    
    def cleanup(self):
        """Remove temp directory and all disk-stored images."""
        self._ram_store.clear()
        self._disk_index.clear()
        self._count = 0
        self._total_bytes = 0
        if self._disk_dir and os.path.isdir(self._disk_dir):
            try:
                shutil.rmtree(self._disk_dir)
            except Exception as e:
                logger.warning("Failed to cleanup temp dir %s: %s", self._disk_dir, e)
        self._disk_dir = None
    
    def __del__(self):
        self.cleanup()


def extract_zip_to_store(zip_file, store, *, max_images=PER_FIELD_MAX_IMAGES,
                         max_bytes=PER_FIELD_MAX_BYTES):
    """
    Extract valid images from a ZIP file into a DiskBackedImageStore.
    
    Uses disk path for large ZIPs (Django spills >10MB to /tmp),
    reads one image at a time to avoid loading entire ZIP into RAM.
    
    Args:
        zip_file: Django UploadedFile or path string
        store: DiskBackedImageStore instance to populate
        max_images: Maximum number of images to extract
        max_bytes: Maximum total bytes to extract
    
    Returns:
        Number of images extracted
    """
    from core.utils.upload_security import validate_zip_safety
    
    # ZIP bomb / nested archive check
    zok, zerr = validate_zip_safety(zip_file)
    if not zok:
        logger.warning("ZIP failed safety check: %s", zerr)
        return 0
    
    extracted_count = 0
    extracted_bytes = 0
    
    try:
        # Open from disk path if available (>10MB files already on disk)
        if isinstance(zip_file, str):
            zf_src = zip_file
        elif hasattr(zip_file, 'temporary_file_path'):
            zf_src = zip_file.temporary_file_path()
        else:
            zip_file.seek(0)
            zf_src = zip_file
        
        with zipfile.ZipFile(zf_src, 'r') as zf:
            for zip_info in zf.infolist():
                if zip_info.is_dir():
                    continue
                if zip_info.file_size > MAX_SINGLE_IMAGE_BYTES:
                    continue
                if extracted_count >= max_images:
                    break
                if extracted_bytes + zip_info.file_size > max_bytes:
                    break
                
                base_name = os.path.basename(zip_info.filename)
                name_without_ext = os.path.splitext(base_name)[0]
                ext = os.path.splitext(base_name)[1].lower()
                
                if ext not in VALID_IMAGE_EXTENSIONS:
                    continue
                
                try:
                    image_bytes = zf.read(zip_info.filename)
                    is_valid, _ = validate_image_bytes(image_bytes)
                    if is_valid:
                        normalized_key = BaseService.normalize_image_identifier(name_without_ext)
                        if normalized_key:
                            store.add(normalized_key, image_bytes, ext, base_name)
                            extracted_count += 1
                            extracted_bytes += len(image_bytes)
                            # Free the bytes reference immediately after storing
                            del image_bytes
                except MemoryError:
                    raise
                except Exception:
                    continue
    except MemoryError:
        raise
    except Exception as e:
        logger.warning("Error extracting ZIP: %s", e)
    
    return extracted_count


def process_data_rows(*, rows, header_to_field, image_ref_columns, image_fields,
                      all_table_fields, table, client, zip_photos_by_field,
                      unified_zip_photos, request_user, is_csv=False):
    """
    Shared row-processing logic for both XLSX and CSV bulk uploads.
    
    Processes rows in batches with transaction.atomic(), matches images,
    creates IDCard records, and creates CardMedia dual-write records.
    
    Args:
        rows: List of row data (tuples for XLSX, dicts for CSV)
        header_to_field: Mapping of column index/header to field name
        image_ref_columns: Mapping of image field name to column index/header
        image_fields: List of image field names
        all_table_fields: Full table field definitions
        table: Table instance
        client: Organisation instance
        zip_photos_by_field: Dict of {field_name: DiskBackedImageStore}
        unified_zip_photos: DiskBackedImageStore for unified ZIPs
        request_user: User making the request
        is_csv: Whether rows are CSV dicts (True) or XLSX tuples (False)
    
    Returns:
        dict: { cards_created, total_photos_matched, errors, saved_image_paths }
    """
    from mediafiles.services import ImageService
    
    cards_created = 0
    total_photos_matched = 0
    errors = []
    saved_image_paths = []
    
    field_type_lookup = {f['name']: f['type'] for f in all_table_fields}
    
    # ── Pre-scan: detect duplicate photo keys ──
    _photo_key_counts = {}
    for scan_row in rows:
        if _is_empty_row(scan_row, is_csv):
            continue
        for img_f in image_fields:
            col_ref = image_ref_columns.get(img_f)
            if col_ref is None:
                continue
            cv = _get_cell_value(scan_row, col_ref, is_csv)
            if cv is not None and str(cv).strip() and str(cv).strip().lower() != 'none':
                cv = _normalize_cell_to_str(cv)
                pk = BaseService.normalize_image_identifier(cv)
                if pk:
                    if img_f not in _photo_key_counts:
                        _photo_key_counts[img_f] = Counter()
                    _photo_key_counts[img_f][pk] += 1
    
    duplicate_keys = set()
    for img_f, counter in _photo_key_counts.items():
        for pk, cnt in counter.items():
            if cnt > 1:
                duplicate_keys.add((img_f, pk))
    
    if duplicate_keys:
        logger.info("Bulk upload: %d duplicate photo keys found — those rows will be PENDING", len(duplicate_keys))
    
    # ── Process in batches ──
    for batch_start in range(0, len(rows), BULK_BATCH_SIZE):
        batch_rows = rows[batch_start:batch_start + BULK_BATCH_SIZE]
        batch_offset = batch_start + 2  # row numbering starts at 2 (after header)
        batch_saved_paths = []
        
        try:
            with transaction.atomic():
                for row_idx, row in enumerate(batch_rows):
                    row_num = batch_offset + row_idx
                    try:
                        if _is_empty_row(row, is_csv):
                            continue
                        
                        # Build field_data from text columns
                        field_data = _build_field_data(
                            row, header_to_field, field_type_lookup,
                            all_table_fields, is_csv
                        )
                        
                        # Process image fields
                        photos_matched = 0
                        used_photo_keys_this_row = set()
                        
                        for img_field in image_fields:
                            photo_column_value = _get_image_column_value(
                                row, img_field, image_ref_columns, is_csv
                            )
                            
                            field_store = zip_photos_by_field.get(img_field)
                            photo_key = (
                                BaseService.normalize_image_identifier(photo_column_value)
                                if photo_column_value else None
                            )
                            
                            if photo_key and photo_key in used_photo_keys_this_row:
                                photo_key = None
                            
                            photo_info = None
                            if photo_key:
                                if field_store and photo_key in field_store:
                                    photo_info = field_store.get(photo_key)
                                elif unified_zip_photos and photo_key in unified_zip_photos:
                                    photo_info = unified_zip_photos.get(photo_key)
                                if photo_info:
                                    used_photo_keys_this_row.add(photo_key)
                            
                            if photo_key and (img_field, photo_key) in duplicate_keys:
                                field_data[img_field] = f'PENDING:{photo_column_value}'
                            elif photo_info:
                                try:
                                    cards_created += 1
                                    result = ImageService.save_new_image(
                                        image_bytes=photo_info['bytes'],
                                        client=client,
                                        field_name=img_field,
                                        card=None,
                                        batch_counter=cards_created,
                                        original_ext=photo_info['ext'],
                                        uploaded_by=request_user if request_user and request_user.is_authenticated else None,
                                    )
                                    # Free image bytes immediately after save
                                    del photo_info
                                    
                                    if result.success and result.data.get('final_value'):
                                        saved_path = result.data['final_value']
                                        batch_saved_paths.append(saved_path)
                                        saved_image_paths.append(saved_path)
                                        field_data[img_field] = saved_path
                                        photos_matched += 1
                                        total_photos_matched += 1
                                    else:
                                        field_data[img_field] = ''
                                    cards_created -= 1
                                except Exception as photo_error:
                                    cards_created -= 1
                                    logger.error("Error saving photo for %s: %s", photo_column_value, photo_error)
                                    field_data[img_field] = f'PENDING:{photo_column_value}' if photo_column_value else ''
                            else:
                                field_data[img_field] = f'PENDING:{photo_column_value}' if photo_column_value else ''
                        
                        # Create the card
                        card = IDCard.objects.create(
                            table=table,
                            field_data=field_data,
                            status=WorkflowService.INITIAL_STATUS,
                        )
                        cards_created += 1
                        
                        # DUAL-WRITE: Create CardMedia records
                        for img_field in image_fields:
                            img_path = field_data.get(img_field, '')
                            if img_path and not img_path.startswith('PENDING:') and img_path not in ('', 'NOT_FOUND'):
                                try:
                                    ImageService.create_media_record(
                                        saved_path=img_path,
                                        client=client,
                                        card=card,
                                        field_name=img_field,
                                        media_type='photo',
                                        original_filename=None,
                                        uploaded_by=request_user if request_user and request_user.is_authenticated else None,
                                    )
                                except Exception as media_err:
                                    logger.warning("Failed to create CardMedia for bulk %s: %s", img_field, media_err)
                    
                    except Exception as e:
                        safe_msg = str(e)[:120].replace('\n', ' ').replace('\r', '')
                        errors.append(f'Row {row_num}: Processing error — {safe_msg}')
        except Exception as atomic_err:
            # Batch transaction rolled back — clean up orphaned images
            logger.error("Bulk upload batch failed at row ~%d: %s", batch_start + 2, atomic_err)
            for orphan_path in batch_saved_paths:
                try:
                    ImageService.delete_image(orphan_path)
                except Exception:
                    pass
            errors.append(f'Batch starting at row {batch_start + 2}: Transaction error — {str(atomic_err)[:100]}')
    
    return {
        'cards_created': cards_created,
        'total_photos_matched': total_photos_matched,
        'errors': errors,
        'saved_image_paths': saved_image_paths,
    }


# ── Helper functions ──

def _is_empty_row(row, is_csv):
    """Check if a row is empty."""
    if is_csv:
        return all(not v or str(v).strip() == '' for v in row.values())
    else:
        return all(cell is None or str(cell).strip() == '' for cell in row)


def _get_cell_value(row, col_ref, is_csv):
    """Get a cell value from a row by column reference."""
    if is_csv:
        return row.get(col_ref, '')
    else:
        # col_ref is an integer index for XLSX
        if col_ref < len(row):
            return row[col_ref]
        return None


def _normalize_cell_to_str(cv):
    """Normalize a cell value to string for image matching."""
    if isinstance(cv, float) and cv == int(cv):
        return str(int(cv))
    elif isinstance(cv, int):
        return str(cv)
    else:
        return str(cv).strip()


def _get_image_column_value(row, img_field, image_ref_columns, is_csv):
    """Extract the image reference value for a given image field from a row."""
    col_ref = image_ref_columns.get(img_field)
    if col_ref is None:
        return None
    
    cv = _get_cell_value(row, col_ref, is_csv)
    if cv is None or not str(cv).strip() or str(cv).strip().lower() == 'none':
        return None
    
    return _normalize_cell_to_str(cv)


def _build_field_data(row, header_to_field, field_type_lookup, all_table_fields, is_csv):
    """Build field_data dict from a row using header-to-field mapping."""
    field_data = {}
    
    if is_csv:
        # CSV: header_to_field = { csv_header: field_name }
        for csv_header, field_name in header_to_field.items():
            value = row.get(csv_header, '')
            field_data[field_name] = str(value) if value is not None else ''
    else:
        # XLSX: header_to_field = { col_index: field_name }
        for col_idx, field_name in header_to_field.items():
            if col_idx < len(row):
                value = row[col_idx]
                if value is not None:
                    # Convert to string, handle dates and numbers
                    if hasattr(value, 'strftime'):
                        value = value.strftime('%d-%m-%Y')
                    elif isinstance(value, float):
                        if 1 < value < 60000 and _is_date_field(field_name):
                            from datetime import datetime, timedelta
                            excel_epoch = datetime(1899, 12, 30)
                            actual_date = excel_epoch + timedelta(days=int(value))
                            value = actual_date.strftime('%d-%m-%Y')
                        elif value == int(value):
                            value = str(int(value))
                        else:
                            value = str(value)
                    elif isinstance(value, int):
                        if 1 < value < 60000 and _is_date_field(field_name):
                            from datetime import datetime, timedelta
                            excel_epoch = datetime(1899, 12, 30)
                            actual_date = excel_epoch + timedelta(days=value)
                            value = actual_date.strftime('%d-%m-%Y')
                        else:
                            value = str(value)
                    else:
                        value = str(value)
                    if isinstance(value, str):
                        value = (value
                                 .replace('_X000D_', '').replace('_x000D_', '')
                                 .replace('_x000d_', '')
                                 .replace('\r\n', ' ').replace('\r', '').replace('\n', ' '))
                    field_data[field_name] = value
                else:
                    field_data[field_name] = ''
            else:
                field_data[field_name] = ''

    return field_data


def _is_date_field(field_name):
    """Check if a field name suggests it contains a date value."""
    fn = field_name.lower()
    return 'date' in fn or 'dob' in fn or 'birth' in fn


# Characters not permitted in text field data.
# Kept: letters, digits, spaces, commas, periods, plus, apostrophe, forward-slash, hyphen.
_FORBIDDEN_TEXT_CHARS_RE = re.compile(r'["_@#$%^&*()\[\]{}<>|\\:;~`!?=]')


def _sanitize_text_cell(value: str) -> str:
    """Strip forbidden special characters from a text-field cell value.

    Mirrors the JS DataSanitizer.sanitizeText() rules:
    - Removed:  " _ @ # $ % ^ & * ( ) [ ] { } < > | \\ : ; ~ ` ! ? =
    - Kept:     letters, digits, whitespace, , . + ' / -
    """
    if not value or not isinstance(value, str):
        return value
    sanitized = _FORBIDDEN_TEXT_CHARS_RE.sub('', value)
    # Collapse consecutive spaces produced by removal
    while '  ' in sanitized:
        sanitized = sanitized.replace('  ', ' ')
    return sanitized.strip()
