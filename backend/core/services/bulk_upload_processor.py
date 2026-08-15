"""
Bulk Upload Processor

Memory-efficient bulk upload processing for ID cards.

CRITICAL DESIGN RULES:
1. NEVER load entire file into memory
2. Process ZIP images ONE at a time
3. Batch database inserts (100 records)
4. Update progress after each batch
5. Cleanup temp files on completion/failure

Usage:
    # Called from background worker
    from core.services.bulk_upload_processor import process_bulk_upload
    process_bulk_upload(task)
"""
import os
import logging
import zipfile

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

# Batch size for database operations
BATCH_SIZE = 100

# Maximum rows to process
MAX_BULK_ROWS = 5000


def process_bulk_upload(task):
    """
    Process a bulk upload task from files saved on disk.
    
    CRITICAL:
    - ZIP files are opened from disk, not loaded into memory
    - Images are extracted and processed one at a time
    - Database inserts are batched
    - Progress is updated incrementally
    
    Args:
        task: BackgroundTask instance with:
            - file_path: Path to saved XLSX/CSV file
            - metadata: {
                'table_id': int,
                'zip_paths': {field_name: relative_path, ...},  # Optional
                'unified_zip_paths': [relative_path, ...],  # Optional
            }
    """
    from tables.models import Table, IDCard
    from core.services.base import BaseService
    from mediafiles.services import ImageService
    from core.utils.field_utils import validate_image_bytes
    
    metadata = task.metadata or {}
    table_id = metadata.get('table_id')
    
    if not table_id:
        task.mark_failed("Missing table_id in metadata")
        return
    
    try:
        table = Table.objects.select_related('organisation').get(id=table_id)
        client = getattr(table, 'organisation', None) or getattr(getattr(table, 'group', None), 'client', None)
    except Table.DoesNotExist:
        task.mark_failed(f"Table {table_id} not found")
        return
    
    # Get full path to uploaded file
    file_path = os.path.join(settings.MEDIA_ROOT, task.file_path) if task.file_path else None
    if not file_path or not os.path.exists(file_path):
        task.mark_failed(f"Upload file not found: {task.file_path}")
        return
    
    file_name = os.path.basename(file_path).lower()
    
    # Get field configuration
    all_table_fields = table.fields or []
    table_fields = [f['name'] for f in all_table_fields if not BaseService.is_image_field(f)]
    image_fields = [f['name'] for f in all_table_fields if BaseService.is_image_field(f)]
    frontend_mapping = metadata.get('field_mapping', {})
    
    # Initialize counters
    cards_created = 0
    photos_matched = 0
    errors = []
    open_zip_handles = []  # ZipFile objects kept open during row loop; closed in finally

    try:
        # Parse XLSX/CSV and get rows
        if file_name.endswith(('.xlsx', '.xls')):
            rows_data, headers, header_to_field, image_ref_columns = _parse_excel_file(
                file_path, table_fields, image_fields, all_table_fields, frontend_mapping
            )
        elif file_name.endswith('.csv'):
            rows_data, headers, header_to_field, image_ref_columns = _parse_csv_file(
                file_path, table_fields, image_fields, all_table_fields, frontend_mapping
            )
        else:
            task.mark_failed("Invalid file format. Expected .xlsx, .xls, or .csv")
            return
        
        if not rows_data:
            task.mark_failed("No data rows found in file")
            return
        
        if len(rows_data) > MAX_BULK_ROWS:
            task.mark_failed(f"File has {len(rows_data)} rows. Maximum allowed is {MAX_BULK_ROWS}.")
            return
        
        # Update total count
        task.update_progress(0, len(rows_data))
        
        # Reverse rows so first Excel row gets highest DB id (preserves order when displayed newest-first)
        rows_data = list(reversed(rows_data))
        
        # Get ZIP file paths from metadata
        zip_paths = metadata.get('zip_paths', {})
        unified_zip_paths = metadata.get('unified_zip_paths', [])
        task_user = getattr(task, 'user', None)

        # Build ZIP indexes ONCE before the row loop.
        # Field-specific ZIPs are indexed separately to prevent key collisions
        # across columns (e.g., PHOTO zip and SIGNATURE zip both containing "1.jpg").
        # Unified ZIPs are indexed into a shared fallback index.
        field_zip_indexes = {}  # {field_name: {normalized_key: (ZipFile_handle, internal_path, ext)}}
        unified_zip_index = {}  # {normalized_key: (ZipFile_handle, internal_path, ext)}

        for _field_name, _zip_rel in zip_paths.items():
            _zip_full = os.path.join(settings.MEDIA_ROOT, _zip_rel)
            if not os.path.exists(_zip_full):
                continue
            try:
                _zf = zipfile.ZipFile(_zip_full, 'r')
                open_zip_handles.append(_zf)
                field_index = {}
                _populate_zip_index(_zf, field_index)
                field_zip_indexes[_field_name] = field_index
                logger.info("Field ZIP indexed: %s (%s)  keys=%d", _zip_rel, _field_name, len(field_index))
            except Exception as _idx_err:
                logger.warning("Could not index field ZIP %s (%s): %s", _zip_rel, _field_name, _idx_err)

        for _zip_rel in unified_zip_paths:
            _zip_full = os.path.join(settings.MEDIA_ROOT, _zip_rel)
            if not os.path.exists(_zip_full):
                continue
            try:
                _zf = zipfile.ZipFile(_zip_full, 'r')
                open_zip_handles.append(_zf)
                _populate_zip_index(_zf, unified_zip_index)
                logger.info("Unified ZIP indexed: %s  keys=%d", _zip_rel, len(unified_zip_index))
            except Exception as _idx_err:
                logger.warning("Could not index unified ZIP %s: %s", _zip_rel, _idx_err)

        # Process rows in batches
        batch = []
        saved_image_paths = []  # Track for rollback cleanup
        field_type_lookup = {f['name']: f['type'] for f in all_table_fields}
        
        for row_idx, row in enumerate(rows_data):
            try:
                # Skip empty rows
                if _is_empty_row(row):
                    continue
                
                # Parse field data from row
                field_data = _parse_row_fields(row, header_to_field, field_type_lookup)
                
                # Process image fields - match with ZIP photos ONE AT A TIME
                for img_field in image_fields:
                    photo_column_value = _get_image_reference_from_row(
                        row, img_field, image_ref_columns, headers
                    )
                    
                    if photo_column_value:
                        # Try to find and save image from ZIP (O(1) index lookup)
                        result = _find_and_save_image_from_zips(
                            photo_column_value=photo_column_value,
                            img_field=img_field,
                            field_zip_indexes=field_zip_indexes,
                            unified_zip_index=unified_zip_index,
                            client=client,
                            batch_counter=len(batch) + cards_created + 1,
                            uploaded_by=task_user if getattr(task_user, 'is_authenticated', False) else None,
                        )
                        
                        if result['success']:
                            field_data[img_field] = result['path']
                            # Preserve original Excel reference so reupload can
                            # match by reference even after the file is saved
                            # with an auto-generated name.
                            field_data[f'__ref_{img_field}'] = photo_column_value
                            saved_image_paths.append(result['path'])
                            photos_matched += 1
                        else:
                            # Save as PENDING for later reupload
                            field_data[img_field] = f'PENDING:{photo_column_value}'
                    else:
                        field_data[img_field] = ''
                
                # Create card object (don't save yet)
                # Sanitize field_data before bulk_create (which skips save())
                from tables.models import sanitize_text_for_storage
                for _k, _v in field_data.items():
                    if isinstance(_v, str):
                        field_data[_k] = sanitize_text_for_storage(_v)
                card = IDCard(
                    table=table,
                    field_data=field_data,
                    status='pending'
                )
                batch.append(card)
                
                # Batch insert when batch is full
                if len(batch) >= BATCH_SIZE:
                    with transaction.atomic():
                        IDCard.objects.bulk_create(batch)
                        # Bulk-create all CardMedia records in one query instead of N inserts
                        _bulk_create_media_for_batch(batch, image_fields, client, task.user)
                        cards_created += len(batch)
                    batch = []
                    
                    # Update progress
                    task.update_progress(row_idx + 1)
                    logger.info("Bulk upload progress: %d/%d", row_idx + 1, len(rows_data))
                    
            except Exception as row_err:
                errors.append(f"Row {row_idx + 2}: {str(row_err)}")
                logger.error("Error processing row %d: %s", row_idx + 2, row_err)
        
        # Insert remaining batch
        if batch:
            with transaction.atomic():
                IDCard.objects.bulk_create(batch)
                _bulk_create_media_for_batch(batch, image_fields, client, task.user)
                cards_created += len(batch)
        
        # Update final progress
        task.update_progress(len(rows_data))
        
        # Build result message
        result_msg = f"Created {cards_created} ID cards with {photos_matched} photos matched"
        
        # Store results in metadata
        task.metadata['result'] = {
            'cards_created': cards_created,
            'photos_matched': photos_matched,
            'error_count': len(errors),
            'errors': errors[:10] if errors else []
        }
        # Invalidate row scope distinct list cache upon new cards bulk upload completion
        from core.views.idcard_helpers import invalidate_table_distinct_cache
        invalidate_table_distinct_cache(table_id)

        # Mark completed
        task.mark_completed()
        logger.info(
            "UPLOAD_DONE task_id=%d cards=%d photos=%d errors=%d",
            task.id, cards_created, photos_matched, len(errors),
        )
        
    except Exception as e:
        logger.exception("Bulk upload failed: %s", e)
        task.mark_failed(str(e))
    
    finally:
        # Close open ZIP handles before cleanup
        for _zf in open_zip_handles:
            try:
                _zf.close()
            except Exception:
                pass
        # Cleanup temp files
        _cleanup_task_files(task)


def _parse_excel_file(file_path, table_fields, image_fields, all_table_fields, frontend_mapping=None):
    """
    Parse Excel file and return rows with header mapping.
    
    CRITICAL: Uses openpyxl's read_only mode for memory efficiency.
    """
    import openpyxl

    def _clean_header_cell(value):
        if value is None:
            return ''
        return (
            str(value)
            .strip()
            .replace('_x000D_', '')
            .replace('_X000D_', '')
            .replace('_x000d_', '')
            .replace('\r', '')
        )
    
    # Read magic bytes to detect format
    with open(file_path, 'rb') as f:
        magic_bytes = f.read(4)
    
    is_zip = magic_bytes[:2] == b'PK'
    is_old_xls = magic_bytes[0] == 0xD0 and magic_bytes[1] == 0xCF
    
    headers = []
    rows_data = []
    
    if is_zip or file_path.lower().endswith('.xlsx'):
        # New xlsx format - use openpyxl with read_only for memory efficiency
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        
        row_iter = ws.iter_rows(values_only=True)
        
        # Get header row
        try:
            header_row = next(row_iter)
            headers = [
                _clean_header_cell(cell)
                for cell in header_row
            ]
        except StopIteration:
            return [], [], {}, {}
        
        # Get data rows
        for row in row_iter:
            rows_data.append(row)
        
        wb.close()
        
    elif is_old_xls or file_path.lower().endswith('.xls'):
        # Old xls format - use xlrd
        import xlrd
        wb = xlrd.open_workbook(file_path)
        ws = wb.sheet_by_index(0)
        
        # Get headers
        for col_idx in range(ws.ncols):
            cell_val = ws.cell_value(0, col_idx)
            headers.append(_clean_header_cell(cell_val))
        
        # Get data rows
        for row_idx in range(1, ws.nrows):
            row = []
            for col_idx in range(ws.ncols):
                row.append(ws.cell_value(row_idx, col_idx))
            rows_data.append(tuple(row))
    
    # Map headers to fields
    header_to_field, image_ref_columns = _map_headers_to_fields(
        headers, table_fields, image_fields, all_table_fields, frontend_mapping
    )
    
    return rows_data, headers, header_to_field, image_ref_columns


def _parse_csv_file(file_path, table_fields, image_fields, all_table_fields, frontend_mapping=None):
    """
    Parse CSV file and return rows with header mapping.
    """
    import csv
    
    rows_data = []
    headers = []
    
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        
        # Get headers
        try:
            headers = [str(h).strip() for h in next(reader)]
        except StopIteration:
            return [], [], {}, {}
        
        # Get data rows as tuples
        for row in reader:
            rows_data.append(tuple(row))
    
    # Map headers to fields
    header_to_field, image_ref_columns = _map_headers_to_fields(
        headers, table_fields, image_fields, all_table_fields, frontend_mapping
    )
    
    return rows_data, headers, header_to_field, image_ref_columns


def _map_headers_to_fields(headers, table_fields, image_fields, all_table_fields, frontend_mapping=None):
    """
    Map Excel/CSV headers to table field names.
    """
    from core.services.base import BaseService
    
    header_to_field = {}
    image_ref_columns = {}
    available_fields = table_fields.copy()
    unmatched_image_fields = list(image_fields)

    if isinstance(frontend_mapping, dict) and frontend_mapping:
        header_index = {}
        for idx, header in enumerate(headers):
            key = str(header or '').strip().replace('\r', '')
            if key and key not in header_index:
                header_index[key] = idx

        normalized_available = {
            str(f).strip().replace('\r', ''): f
            for f in available_fields
        }

        for table_field_name, upload_header in frontend_mapping.items():
            orig_field_name = str(table_field_name or '').strip()
            norm_field_name = orig_field_name.replace('\r', '')
            header_name = str(upload_header or '').strip().replace('\r', '')

            if not orig_field_name or norm_field_name not in normalized_available:
                continue

            col_idx = header_index.get(header_name)
            if col_idx is None:
                continue

            original_field_name = normalized_available[norm_field_name]
            header_to_field[col_idx] = original_field_name
            available_fields.remove(original_field_name)
            del normalized_available[norm_field_name]

        for idx, header in enumerate(headers):
            if idx in header_to_field:
                continue
            if not header:
                continue

            matched_img_field = BaseService.find_best_image_field_match(header, unmatched_image_fields)
            if matched_img_field:
                image_ref_columns[matched_img_field] = idx
                unmatched_image_fields.remove(matched_img_field)

        return header_to_field, image_ref_columns
    
    for idx, header in enumerate(headers):
        if not header:
            continue
        
        # Try to match against image fields first
        matched_img_field = BaseService.find_best_image_field_match(header, unmatched_image_fields)
        if matched_img_field:
            image_ref_columns[matched_img_field] = idx
            unmatched_image_fields.remove(matched_img_field)
            continue
        
        # Try text field matching
        match = BaseService.find_best_field_match(header, available_fields)
        if match:
            header_to_field[idx] = match
            available_fields.remove(match)
    
    return header_to_field, image_ref_columns


def _is_empty_row(row):
    """Check if a row is empty."""
    if isinstance(row, dict):
        return all(not v or str(v).strip() == '' for v in row.values())
    return all(cell is None or str(cell).strip() == '' for cell in row)


def _parse_row_fields(row, header_to_field, field_type_lookup):
    """
    Parse field values from a row.
    """
    from datetime import datetime, timedelta
    
    field_data = {}
    
    for col_idx, field_name in header_to_field.items():
        if col_idx < len(row):
            value = row[col_idx]
            if value is not None:
                # Handle different value types
                if hasattr(value, 'strftime'):
                    value = value.strftime('%d-%m-%Y')
                elif isinstance(value, float):
                    # Check for Excel date serial numbers
                    if 1 < value < 60000 and any(x in field_name.lower() for x in ['date', 'dob', 'birth']):
                        excel_epoch = datetime(1899, 12, 30)
                        actual_date = excel_epoch + timedelta(days=int(value))
                        value = actual_date.strftime('%d-%m-%Y')
                    elif value == int(value):
                        value = str(int(value))
                    else:
                        value = str(value)
                elif isinstance(value, int):
                    if 1 < value < 60000 and any(x in field_name.lower() for x in ['date', 'dob', 'birth']):
                        excel_epoch = datetime(1899, 12, 30)
                        actual_date = excel_epoch + timedelta(days=value)
                        value = actual_date.strftime('%d-%m-%Y')
                    else:
                        value = str(value)
                else:
                    value = str(value)
                
                # Clean openpyxl carriage-return artifacts (_x000D_ / _X000D_)
                # Excel cells with Alt+Enter line breaks produce these when
                # read by openpyxl. Remove them to prevent data corruption.
                if isinstance(value, str):
                    value = value.replace('_X000D_', '').replace('_x000D_', '').replace('_x000d_', '').replace('\r\n', '\n').replace('\r', '')
                
                field_data[field_name] = value
            else:
                field_data[field_name] = ''
        else:
            field_data[field_name] = ''
    
    return field_data


def _get_image_reference_from_row(row, img_field, image_ref_columns, headers):
    """
    Get image reference value from row for a specific image field.
    """
    if img_field not in image_ref_columns:
        return None
    
    col_idx = image_ref_columns[img_field]
    if col_idx < len(row):
        cell_value = row[col_idx]
        if cell_value is not None and str(cell_value).strip() and str(cell_value).strip().lower() != 'none':
            # Handle numeric values
            if isinstance(cell_value, float) and cell_value == int(cell_value):
                return str(int(cell_value))
            elif isinstance(cell_value, int):
                return str(cell_value)
            else:
                return str(cell_value).strip()
    
    return None


def _populate_zip_index(zf, index):
    """
    Scan an open ZipFile and populate index:
        index[normalized_key] = (ZipFile_handle, internal_path, ext)

    Only stores metadata — no image bytes are loaded into memory.
    First encountered entry wins when two files share the same normalized key.
    """
    from core.services.base import BaseService
    ALLOWED_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    MAX_SINGLE_FILE = 30 * 1024 * 1024  # 30 MB — matches upload limit
    for info in zf.infolist():
        if info.is_dir():
            continue
        if info.file_size > MAX_SINGLE_FILE:
            continue
        base_name = os.path.basename(info.filename)
        name_no_ext, ext = os.path.splitext(base_name)
        ext = ext.lower()
        if ext not in ALLOWED_EXTS:
            continue
        key = BaseService.normalize_image_identifier(name_no_ext)
        if key and key not in index:
            index[key] = (zf, info.filename, ext)


def _find_and_save_image_from_zips(
    photo_column_value,
    img_field,
    field_zip_indexes,
    unified_zip_index,
    client,
    batch_counter,
    uploaded_by=None,
):
    """
    Find an image using pre-built ZIP indexes and save it.

    Resolution order:
    1) Field-specific ZIP index for current image field
    2) Unified ZIP index fallback

    This prevents collisions where different field ZIPs contain the same key.
    """
    from core.services.base import BaseService
    from core.utils.field_utils import validate_image_bytes

    normalized_key = BaseService.normalize_image_identifier(photo_column_value)
    if not normalized_key:
        return {'success': False, 'error': 'Invalid photo reference'}

    entry = None

    field_index = (field_zip_indexes or {}).get(img_field)
    if field_index:
        entry = field_index.get(normalized_key)

    if not entry:
        entry = (unified_zip_index or {}).get(normalized_key)

    if not entry:
        return {'success': False, 'error': 'Image not found in any ZIP'}

    zf, internal_path, ext = entry
    try:
        image_bytes = zf.read(internal_path)
    except Exception as e:
        return {'success': False, 'error': f'Failed to read image from ZIP: {e}'}

    is_valid, error_msg = validate_image_bytes(image_bytes)
    if not is_valid:
        return {'success': False, 'error': f'Invalid image: {error_msg}'}

    return _save_extracted_image(
        {'bytes': image_bytes, 'ext': ext, 'original_name': os.path.basename(internal_path)},
        client,
        batch_counter,
        uploaded_by=uploaded_by,
    )


def _save_extracted_image(result, client, batch_counter, uploaded_by=None):
    """
    Save an extracted image using ImageService single-authority entry point.
    """
    from mediafiles.services import ImageService
    
    try:
        save_result = ImageService.save_new_image(
            image_bytes=result['bytes'],
            client=client,
            field_name='photo',  # generic; caller sets real field in field_data
            card=None,  # card not yet created during bulk upload
            batch_counter=batch_counter,
            original_ext=result['ext'],
            uploaded_by=uploaded_by,
        )
        
        if save_result.success and save_result.data.get('final_value'):
            return {'success': True, 'path': save_result.data['final_value']}
        else:
            return {'success': False, 'error': save_result.message}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _bulk_create_media_for_batch(batch, image_fields, client, user):
    """
    Bulk-create CardMedia records for an entire batch of cards in one INSERT.
    Replaces the old per-card create loop (N inserts → 1 insert).
    """
    from mediafiles.models import CardMedia

    records = []
    for card in batch:
        field_data = card.field_data or {}
        for img_field in image_fields:
            img_path = field_data.get(img_field, '')
            if img_path and not img_path.startswith('PENDING:') and img_path not in ('', 'NOT_FOUND'):
                records.append(CardMedia(
                    card=card,
                    group=None,
                    client=client,
                    file=img_path,
                    media_type='photo',
                    field_name=img_field,
                    original_filename=None,
                    uploaded_by=user,
                ))

    if records:
        try:
            CardMedia.objects.bulk_create(records, ignore_conflicts=True)
        except Exception as e:
            logger.warning("Bulk CardMedia create failed, falling back to individual inserts: %s", e)
            for rec in records:
                try:
                    rec.save()
                except Exception as rec_err:
                    logger.warning("CardMedia individual save also failed for card %s field %s: %s", rec.card_id, rec.field_name, rec_err)


def _cleanup_task_files(task):
    """
    Clean up all temporary files associated with a task.
    """
    from core.services.background_worker import cleanup_temp_file
    
    # Clean up main file
    if task.file_path:
        cleanup_temp_file(task.file_path)
    
    # Clean up ZIP files from metadata
    metadata = task.metadata or {}
    
    for field_name, zip_path in metadata.get('zip_paths', {}).items():
        cleanup_temp_file(zip_path)
    
    for zip_path in metadata.get('unified_zip_paths', []):
        cleanup_temp_file(zip_path)
