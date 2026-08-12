"""
ID Card Bulk API — bulk upload, reupload images, and modals HTML.

Contains:
- api_idcard_bulk_upload
- _parse_excel_file, _parse_csv_file, _map_headers_to_fields
- api_idcard_reupload_images
- api_idcard_modals_html
"""
import json
import logging
import os
import re

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.conf import settings
from django.core.cache import cache as django_cache
from django.core.files.uploadhandler import MemoryFileUploadHandler

from tables.models import IDCard, Table
from ..services import IDCardService
from mediafiles.services import ImageService
from ..services.base import BaseService
from ..services.cache_version_service import CacheVersionService
from ..services.permission_service import (
    api_require_any_authenticated,
    api_require_permission,
)
from ..utils.upload_security import validate_zip_safety
from core.utils.folder_image_ingest import (
    build_zip_from_uploaded_folder_files,
    build_zip_from_folder_path,
)

from .idcard_helpers import (
    _safe_error,
    _check_client_scope_by_table,
    _CLIENT_READONLY_STATUSES,
    _is_client_readonly,
    validate_image_bytes,
)

# Logger for this module
logger = logging.getLogger(__name__)

_REUPLOAD_NAME_BASE_RE = re.compile(r'^(?:[ac]\d{14}|\d{14})$')

# Keep strict matching first; legacy timestamp-number stems are fallback only.
# Fallback is intentionally permissive and matches any non-empty filename stem.
REUPLOAD_ALLOW_LEGACY_FALLBACK = True


def _ensure_folder_upload_allowed(request):
    """Allow folder-based upload sources only for Pro User accounts."""
    folder_upload_files = request.FILES.getlist('photos_folder_files')
    folder_path = str(request.POST.get('photos_folder_path', '') or '').strip()
    if not folder_upload_files and not folder_path:
        return None
    if getattr(request.user, 'role', '') == 'pro_user':
        return None
    return JsonResponse(
        {
            'success': False,
            'message': 'Select Folder is available only for Pro User accounts. Use ZIP upload instead.',
        },
        status=403,
    )


class _SuperModeMemoryUploadHandler(MemoryFileUploadHandler):
    """Force Django multipart uploads to stay in memory for Super Mode sync path."""

    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        self.activated = True


def _extract_reupload_stem(value):
    """Extract filename stem without fuzzy normalization."""
    base_name = os.path.basename(str(value or '').strip())
    stem, _ = os.path.splitext(base_name)
    return stem.strip()


def _is_strict_reupload_stem(stem):
    """Strict canonical stems from system-generated image names."""
    return bool(_REUPLOAD_NAME_BASE_RE.match(stem))


def _is_fallback_reupload_stem(stem):
    """Fallback accepts any non-empty exact stem from DB/ZIP names."""
    return bool(str(stem or '').strip())


def _is_supported_reupload_stem(stem):
    """Validation used while indexing ZIP entries."""
    if _is_strict_reupload_stem(stem):
        return True
    return bool(REUPLOAD_ALLOW_LEGACY_FALLBACK and _is_fallback_reupload_stem(stem))


def _resolve_reupload_photo(stem, zip_photos):
    """Resolve match with strict-first behavior and open fallback."""
    if not stem:
        return None
    if _is_strict_reupload_stem(stem) and stem in zip_photos:
        return zip_photos.get(stem)
    if REUPLOAD_ALLOW_LEGACY_FALLBACK and _is_fallback_reupload_stem(stem):
        return zip_photos.get(stem)
    return None


@require_http_methods(["POST"])
@api_require_permission('perm_idcard_bulk_upload')
def api_idcard_bulk_upload(request, table_id):
    """API endpoint to bulk upload ID Cards from XLSX/CSV file with fuzzy matching and optional ZIP photo upload.
    
    Uses disk-based image storage for large ZIPs to prevent OOM.
    For effective Super Mode users, synchronous ZIP ingestion prefers RAM-only
    processing with a bounded memory budget for lower I/O latency.
    Row processing is unified across XLSX and CSV via BulkUploadService.
    """
    _tbl, err = _check_client_scope_by_table(request.user, table_id)
    if err: return err
    folder_access_err = _ensure_folder_upload_allowed(request)
    if folder_access_err:
        return folder_access_err
    # Double-click guard: prevent duplicate uploads from rapid form submissions
    lock_key = f'bulk_upload_lock:{request.user.id}:{table_id}'
    if not django_cache.add(lock_key, 1, 300):
        return JsonResponse({'success': False, 'message': 'Upload already in progress. Please wait.'}, status=429)
    
    # Import the disk-backed image store and helpers
    from ..services.bulk_upload_service import (
        DiskBackedImageStore, extract_zip_to_store, process_data_rows,
        MAX_BULK_ROWS, BULK_BATCH_SIZE,
    )
    
    # Track all image stores for cleanup on exit
    _all_stores = []
    super_mode_sync_ram_only = False
    effective_super_ram_mb = 0
    generated_folder_zip_paths = []

    try:
        super_mode_sync_ram_only = False
        if super_mode_sync_ram_only:
            effective_super_ram_mb = 0
    except Exception:
        logger.exception("Failed resolving Super Mode RAM-only state for sync bulk upload")
        super_mode_sync_ram_only = False
        effective_super_ram_mb = 0

    # Configure upload handlers before first access to request.FILES.
    if super_mode_sync_ram_only:
        try:
            request.upload_handlers = [_SuperModeMemoryUploadHandler(request)]
        except Exception:
            logger.exception("Failed to apply Super Mode in-memory upload handler")
    
    try:
        import openpyxl
        from io import BytesIO
        import re
        import zipfile
        import os
        import shutil
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile

        # Pre-flight disk space check: require at least 500 MB free.
        # Skip this guard for Super Mode RAM-only sync ingestion.
        if not super_mode_sync_ram_only:
            try:
                disk = shutil.disk_usage(settings.MEDIA_ROOT)
                if disk.free < 500 * 1024 * 1024:  # 500 MB
                    return JsonResponse({
                        'success': False,
                        'message': 'Insufficient disk space. Please contact your administrator.'
                    }, status=507)
            except Exception:
                pass  # Non-critical — proceed if check fails
        
        table = get_object_or_404(Table.objects.select_related('group__client'), id=table_id)
        
        if 'file' not in request.FILES:
            return JsonResponse({'success': False, 'message': 'No file uploaded!'}, status=400)
        
        uploaded_file = request.FILES['file']
        file_name = uploaded_file.name.lower()
        file_size = uploaded_file.size
        
        # Get image field names from table using BaseService
        image_field_names = BaseService.get_image_field_names(table.fields)
        
        # ── Extract ZIP images into disk-backed stores ──
        # Each image field gets its own DiskBackedImageStore
        zip_photos_by_field = {}  # { field_name: DiskBackedImageStore }
        
        # Check for multiple ZIP files - one per image field
        zip_field_names_str = request.POST.get('zip_field_names', '[]')
        try:
            zip_field_names = json.loads(zip_field_names_str)
        except (json.JSONDecodeError, TypeError):
            zip_field_names = []

        try:
            unified_zip_count = min(int(request.POST.get('unified_zip_count', 0)), 20)
        except (ValueError, TypeError):
            unified_zip_count = 0

        store_kwargs = {}
        if super_mode_sync_ram_only:
            mib = 1024 * 1024
            # Keep headroom for Python, DB work, and request processing.
            total_ram_budget = int(max(64 * mib, min(512 * mib, effective_super_ram_mb * mib * 0.60)))

            uploaded_field_zip_count = sum(
                1 for field_name in zip_field_names if f'photos_zip_{field_name}' in request.FILES
            )
            uploaded_unified_zip_count = sum(
                1 for i in range(unified_zip_count) if f'unified_zip_{i}' in request.FILES
            )
            planned_store_count = uploaded_field_zip_count + (1 if uploaded_unified_zip_count > 0 else 0)
            if planned_store_count <= 0 and 'photos_zip' in request.FILES:
                planned_store_count = 1
            planned_store_count = max(1, planned_store_count)

            per_store_budget = max(32 * mib, int(total_ram_budget / planned_store_count))
            per_image_budget = min(20 * mib, max(512 * 1024, int(per_store_budget / 8)))

            store_kwargs = {
                'ram_threshold_bytes': per_store_budget,
                'ram_threshold_per_image': per_image_budget,
                'force_ram_only': True,
            }
        
        logger.debug("zip_field_names = %s", zip_field_names)
        
        # Process per-field ZIP files
        for field_name in zip_field_names:
            zip_key = f'photos_zip_{field_name}'
            if zip_key in request.FILES:
                photos_zip_file = request.FILES[zip_key]
                store = DiskBackedImageStore(**store_kwargs)
                _all_stores.append(store)
                try:
                    count = extract_zip_to_store(photos_zip_file, store)
                except MemoryError:
                    return JsonResponse({
                        'success': False,
                        'message': (
                            'Super Mode RAM-only upload limit reached. '
                            'Reduce ZIP size/count (or disable Super Mode to allow disk-assisted upload).'
                        ),
                    }, status=413)
                if count > 0:
                    zip_photos_by_field[field_name] = store
                    logger.debug("Field '%s' extracted %d images", field_name, count)
        
        # Legacy: single photos_zip (backward compatibility)
        if not zip_photos_by_field and 'photos_zip' in request.FILES:
            photos_zip_file = request.FILES['photos_zip']
            first_image_field = image_field_names[0] if image_field_names else 'PHOTO'
            store = DiskBackedImageStore(**store_kwargs)
            _all_stores.append(store)
            try:
                count = extract_zip_to_store(photos_zip_file, store)
            except MemoryError:
                return JsonResponse({
                    'success': False,
                    'message': (
                        'Super Mode RAM-only upload limit reached. '
                        'Reduce ZIP size/count (or disable Super Mode to allow disk-assisted upload).'
                    ),
                }, status=413)
            if count > 0:
                zip_photos_by_field[first_image_field] = store
        
        # Unified ZIP files (images auto-matched to all columns)
        unified_zip_photos = DiskBackedImageStore(**store_kwargs)
        _all_stores.append(unified_zip_photos)
        
        for i in range(unified_zip_count):
            zip_key = f'unified_zip_{i}'
            if zip_key in request.FILES:
                try:
                    extract_zip_to_store(request.FILES[zip_key], unified_zip_photos)
                except MemoryError:
                    return JsonResponse({
                        'success': False,
                        'message': (
                            'Super Mode RAM-only upload limit reached. '
                            'Reduce ZIP size/count (or disable Super Mode to allow disk-assisted upload).'
                        ),
                    }, status=413)

        # Optional: folder-selected image files (browser folder upload)
        folder_upload_files = request.FILES.getlist('photos_folder_files')
        if folder_upload_files:
            folder_zip_path, _folder_image_count, folder_err = build_zip_from_uploaded_folder_files(folder_upload_files)
            if folder_err:
                return JsonResponse({'success': False, 'message': folder_err}, status=400)
            generated_folder_zip_paths.append(folder_zip_path)
            try:
                extract_zip_to_store(os.path.join(settings.MEDIA_ROOT, folder_zip_path), unified_zip_photos)
            except MemoryError:
                return JsonResponse({
                    'success': False,
                    'message': (
                        'Super Mode RAM-only upload limit reached. '
                        'Reduce folder image size/count (or disable Super Mode to allow disk-assisted upload).'
                    ),
                }, status=413)

        # Optional: pasted server-side folder path
        folder_path = str(request.POST.get('photos_folder_path', '') or '').strip()
        if folder_path:
            folder_zip_path, _folder_image_count, folder_err = build_zip_from_folder_path(folder_path)
            if folder_err:
                return JsonResponse({'success': False, 'message': folder_err}, status=400)
            generated_folder_zip_paths.append(folder_zip_path)
            try:
                extract_zip_to_store(os.path.join(settings.MEDIA_ROOT, folder_zip_path), unified_zip_photos)
            except MemoryError:
                return JsonResponse({
                    'success': False,
                    'message': (
                        'Super Mode RAM-only upload limit reached. '
                        'Reduce folder image size/count (or disable Super Mode to allow disk-assisted upload).'
                    ),
                }, status=413)
        
        logger.debug("unified_zip_photos count = %d", len(unified_zip_photos))
        
        # Get client for ImageService operations
        client = table.group.client
        
        # Get all table fields
        all_table_fields = table.fields
        table_fields = [f['name'] for f in all_table_fields if not BaseService.is_image_field(f)]
        image_fields = [f['name'] for f in all_table_fields if BaseService.is_image_field(f)]
        
        matched_field_names = []
        
        # Check if frontend sent a manual field mapping
        frontend_mapping_str = request.POST.get('field_mapping', '')
        frontend_mapping = {}
        if frontend_mapping_str:
            try:
                frontend_mapping = json.loads(frontend_mapping_str)
                if not isinstance(frontend_mapping, dict):
                    frontend_mapping = {}
            except (json.JSONDecodeError, TypeError):
                frontend_mapping = {}
        
        # ── Parse file (XLSX/XLS/CSV) ──
        if file_name.endswith('.xlsx') or file_name.endswith('.xls'):
            rows_data, headers, header_to_field, image_ref_columns, matched_field_names, parse_error = \
                _parse_excel_file(uploaded_file, file_name, table_fields, image_fields,
                                  frontend_mapping, all_table_fields)
            if parse_error:
                return parse_error
            is_csv = False
        elif file_name.endswith('.csv'):
            rows_data, headers, header_to_field, image_ref_columns, matched_field_names, parse_error = \
                _parse_csv_file(uploaded_file, table_fields, image_fields,
                                frontend_mapping, all_table_fields)
            if parse_error:
                return parse_error
            is_csv = True
        else:
            return JsonResponse({
                'success': False,
                'message': 'Invalid file format! Please upload .xlsx, .xls, or .csv file.'
            }, status=400)
        
        if not header_to_field:
            return JsonResponse({
                'success': False,
                'message': f'No matching columns found! Expected columns: {", ".join(table_fields)}'
            }, status=400)
        
        if len(rows_data) > MAX_BULK_ROWS:
            return JsonResponse({
                'success': False,
                'message': f'File has {len(rows_data)} rows. Maximum allowed is {MAX_BULK_ROWS}.'
            }, status=400)
        
        # Reverse rows so first Excel row gets highest DB id (preserves order in -id display)
        rows_data = list(reversed(rows_data))
        
        # ── Process rows using unified service ──
        result = process_data_rows(
            rows=rows_data,
            header_to_field=header_to_field,
            image_ref_columns=image_ref_columns,
            image_fields=image_fields,
            all_table_fields=all_table_fields,
            table=table,
            client=client,
            zip_photos_by_field=zip_photos_by_field,
            unified_zip_photos=unified_zip_photos,
            request_user=request.user,
            is_csv=is_csv,
        )
        
        cards_created = result['cards_created']
        total_photos_matched = result['total_photos_matched']
        errors = result['errors']

        if cards_created > 0:
            try:
                CacheVersionService.bump('mob_filter', int(table.id))
                CacheVersionService.bump('class_section', int(table.group.client_id))
                CacheVersionService.bump('global_search', 'all')
            except Exception:
                pass

            # Activity log
            try:
                from core.services.activity_service import ActivityService
                ActivityService.log_bulk_upload(
                    request,
                    cards_created=cards_created,
                    images_matched=total_photos_matched,
                    table=table,
                    file_format='xlsx' if not is_csv else 'csv',
                )
            except Exception:
                logger.exception('Bulk upload activity log failed')
        
        # Return result
        photo_msg = f" with {total_photos_matched} photos matched" if total_photos_matched > 0 else ""
        response = {
            'success': True,
            'message': f'Successfully created {cards_created} ID cards{photo_msg}!',
            'cards_created': cards_created,
            'photos_matched': total_photos_matched,
            'matched_fields': matched_field_names,
        }
        
        if errors:
            response['errors'] = errors[:10]
            response['error_count'] = len(errors)
        
        return JsonResponse(response)
        
    except ImportError:
        return JsonResponse({
            'success': False,
            'message': 'openpyxl library not installed. Run: pip install openpyxl'
        }, status=500)
    except Exception as e:
        return JsonResponse({'success': False, 'message': _safe_error(e)}, status=500)
    finally:
        # Always cleanup disk-backed image stores
        for store in _all_stores:
            try:
                store.cleanup()
            except Exception:
                pass
        from core.services.background_worker import cleanup_temp_file
        for _zip_path in generated_folder_zip_paths:
            cleanup_temp_file(_zip_path)
        django_cache.delete(lock_key)


def _parse_excel_file(uploaded_file, file_name, table_fields, image_fields,
                       frontend_mapping, all_table_fields):
    """Parse Excel file and return (rows_data, headers, header_to_field, image_ref_columns, matched_fields, error_response).
    Returns error_response=None on success, or a JsonResponse on failure."""
    import openpyxl
    from io import BytesIO

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
    
    try:
        file_content = uploaded_file.read()
        if len(file_content) < 4:
            return None, None, None, None, [], JsonResponse({
                'success': False, 'message': 'File is too small or empty.'
            }, status=400)
        
        magic_bytes = file_content[:4]
        is_zip = magic_bytes[:2] == b'PK'
        is_old_xls = (magic_bytes[0] == 0xD0 and magic_bytes[1] == 0xCF)
        
        headers = []
        rows_data = []
        
        if is_zip or file_name.endswith('.xlsx'):
            wb = None
            try:
                # Read-only/data-only keeps memory stable for larger uploads.
                wb = openpyxl.load_workbook(BytesIO(file_content), read_only=True, data_only=True)
                ws = wb.active

                row_iter = ws.iter_rows(values_only=True)
                header_row = next(row_iter, None)
                if header_row is not None:
                    headers = [_clean_header_cell(cell) for cell in header_row]

                for row in row_iter:
                    rows_data.append(row)
            except Exception as xlsx_error:
                if not is_zip:
                    is_old_xls = True
                else:
                    raise xlsx_error
            finally:
                if wb is not None:
                    wb.close()
        
        if is_old_xls or (file_name.endswith('.xls') and not file_name.endswith('.xlsx') and not headers):
            try:
                import xlrd
                wb = xlrd.open_workbook(file_contents=file_content)
                ws = wb.sheet_by_index(0)
                headers = []
                for col_idx in range(ws.ncols):
                    cell_value = ws.cell_value(0, col_idx)
                    headers.append(_clean_header_cell(cell_value))
                rows_data = []
                for row_idx in range(1, ws.nrows):
                    row = []
                    for col_idx in range(ws.ncols):
                        row.append(ws.cell_value(row_idx, col_idx))
                    rows_data.append(tuple(row))
            except ImportError:
                return None, None, None, None, [], JsonResponse({
                    'success': False, 'message': 'xlrd library not installed for .xls files.'
                }, status=400)
            except Exception:
                return None, None, None, None, [], JsonResponse({
                    'success': False, 'message': 'Error reading .xls file. Please check the file format.'
                }, status=400)
        
        if not headers:
            return None, None, None, None, [], JsonResponse({
                'success': False, 'message': 'Could not read headers from Excel file.'
            }, status=400)
    except Exception:
        return None, None, None, None, [], JsonResponse({
            'success': False, 'message': 'Error reading Excel file. Please check the file format.'
        }, status=400)
    
    header_to_field, image_ref_columns, matched_field_names = _map_headers_to_fields(
        headers, table_fields, image_fields, frontend_mapping, all_table_fields, is_csv=False
    )
    
    return rows_data, headers, header_to_field, image_ref_columns, matched_field_names, None


def _parse_csv_file(uploaded_file, table_fields, image_fields,
                     frontend_mapping, all_table_fields):
    """Parse CSV file and return (rows_data, headers, header_to_field, image_ref_columns, matched_fields, error_response)."""
    import csv
    from io import StringIO
    
    try:
        content = uploaded_file.read().decode('utf-8-sig')
        reader = csv.DictReader(StringIO(content))
        csv_headers = reader.fieldnames or []
        rows_data = list(reader)
    except Exception:
        return None, None, None, None, [], JsonResponse({
            'success': False, 'message': 'Error reading CSV file. Please check the file format.'
        }, status=400)
    
    if not csv_headers:
        return None, None, None, None, [], JsonResponse({
            'success': False, 'message': 'Could not read headers from CSV file.'
        }, status=400)
    
    header_to_field, image_ref_columns, matched_field_names = _map_headers_to_fields(
        csv_headers, table_fields, image_fields, frontend_mapping, all_table_fields, is_csv=True
    )
    
    return rows_data, csv_headers, header_to_field, image_ref_columns, matched_field_names, None


def _map_headers_to_fields(headers, table_fields, image_fields, frontend_mapping,
                            all_table_fields, *, is_csv=False):
    """Map file headers to table fields using fuzzy matching or frontend mapping.
    Returns (header_to_field, image_ref_columns, matched_field_names)."""
    header_to_field = {}
    available_fields = table_fields.copy()
    image_ref_columns = {}
    unmatched_image_fields = list(image_fields)
    matched_field_names = []
    
    if frontend_mapping:
        if is_csv:
            for table_field_name, excel_header in frontend_mapping.items():
                if table_field_name in available_fields and excel_header in headers:
                    header_to_field[excel_header] = table_field_name
                    available_fields.remove(table_field_name)
                    matched_field_names.append(table_field_name)
        else:
            header_index = {h: i for i, h in enumerate(headers)}
            for table_field_name, excel_header in frontend_mapping.items():
                if table_field_name in available_fields and excel_header in header_index:
                    idx = header_index[excel_header]
                    header_to_field[idx] = table_field_name
                    available_fields.remove(table_field_name)
                    matched_field_names.append(table_field_name)
        
        # Auto-match image columns
        for idx_or_header in (range(len(headers)) if not is_csv else headers):
            header = headers[idx_or_header] if not is_csv else idx_or_header
            if not header:
                continue
            if not is_csv and idx_or_header in header_to_field:
                continue
            if is_csv and header in header_to_field:
                continue
            matched_img = BaseService.find_best_image_field_match(header, unmatched_image_fields)
            if matched_img:
                image_ref_columns[matched_img] = idx_or_header if not is_csv else header
                unmatched_image_fields.remove(matched_img)
    else:
        # Auto fuzzy matching
        for idx_or_header in (range(len(headers)) if not is_csv else headers):
            header = headers[idx_or_header] if not is_csv else idx_or_header
            if not header:
                continue
            
            matched_img = BaseService.find_best_image_field_match(header, unmatched_image_fields)
            if matched_img:
                image_ref_columns[matched_img] = idx_or_header if not is_csv else header
                unmatched_image_fields.remove(matched_img)
                continue
            
            header_str = header if is_csv else header
            match = BaseService.find_best_field_match(header_str.strip() if is_csv else header, available_fields)
            if match:
                if is_csv:
                    header_to_field[header] = match
                else:
                    header_to_field[idx_or_header] = match
                available_fields.remove(match)
                matched_field_names.append(match)
    
    return header_to_field, image_ref_columns, matched_field_names


@require_http_methods(["POST"])
@api_require_permission('perm_idcard_bulk_reupload')
def api_idcard_reupload_images(request, table_id):
    """
    API endpoint to reupload images from a ZIP file.
    Matches ZIP filenames to card image references (PENDING: or existing paths) and updates them.
    
    Supports:
    - PENDING:reference matching (for cards created without images)
    - Existing image path updates (applies edit naming: original_14 + _HHMMSS)
    - Multiple image fields per card
    - Thumbnail generation for all saved images
    """
    _tbl, err = _check_client_scope_by_table(request.user, table_id)
    if err: return err
    folder_access_err = _ensure_folder_upload_allowed(request)
    if folder_access_err:
        return folder_access_err
    # Client/client_staff cannot reupload images for tables with approved/download/reprint cards
    if request.user.PermissionService.is_client_role(user):
        has_locked = IDCard.objects.filter(
            table_id=table_id, status__in=_CLIENT_READONLY_STATUSES
        ).exists()
        if has_locked:
            return JsonResponse({
                'success': False,
                'message': 'This table contains cards in approved/download status. Client users cannot reupload images.'
            }, status=403)
    # Double-click guard: prevent duplicate reupload from rapid form submissions
    lock_key = f'reupload_lock:{request.user.id}:{table_id}'
    if not django_cache.add(lock_key, 1, 300):
        return JsonResponse({'success': False, 'message': 'Reupload already in progress. Please wait.'}, status=429)
    zip_photos_store = None
    generated_reupload_zip_path = None
    try:
        import zipfile
        from django.db import transaction
        from ..services.bulk_upload_service import DiskBackedImageStore
        
        table = get_object_or_404(Table.objects.select_related('group__client'), id=table_id)
        client = table.group.client
        
        reupload_zip_source = None

        if 'photos_zip' in request.FILES:
            reupload_zip_source = request.FILES['photos_zip']
        else:
            folder_upload_files = request.FILES.getlist('photos_folder_files')
            if folder_upload_files:
                generated_reupload_zip_path, _folder_image_count, folder_err = build_zip_from_uploaded_folder_files(folder_upload_files)
                if folder_err:
                    return JsonResponse({'success': False, 'message': folder_err}, status=400)
                reupload_zip_source = os.path.join(settings.MEDIA_ROOT, generated_reupload_zip_path)

            if not reupload_zip_source:
                folder_path = str(request.POST.get('photos_folder_path', '') or '').strip()
                if folder_path:
                    generated_reupload_zip_path, _folder_image_count, folder_err = build_zip_from_folder_path(folder_path)
                    if folder_err:
                        return JsonResponse({'success': False, 'message': folder_err}, status=400)
                    reupload_zip_source = os.path.join(settings.MEDIA_ROOT, generated_reupload_zip_path)

        if not reupload_zip_source:
            return JsonResponse({'success': False, 'message': 'Provide a ZIP, select a folder, or paste a folder path.'}, status=400)
        
        # Get image field names from table
        image_field_names = BaseService.get_image_field_names(table.fields)
        if not image_field_names:
            return JsonResponse({'success': False, 'message': 'No image fields defined in table!'}, status=400)
        
        # Optional single-field mode via target_field; default is all image fields.
        target_field = str(request.POST.get('target_field', '') or '').strip()
        if target_field and target_field in image_field_names:
            image_fields_to_process = [target_field]
        else:
            image_fields_to_process = list(image_field_names)
        
        # Extract photos from ZIP — use temp file if available (avoids OOM on large uploads)
        # Uses strict canonical stem keys for exact matching consistency.
        zip_photos_store = DiskBackedImageStore()  # { exact_key -> bytes on disk/RAM }
        duplicate_name_keys = 0
        seen_stems = set()
        
        try:
            zip_file = reupload_zip_source

            # ZIP size guard
            if hasattr(zip_file, 'size') and zip_file.size > 600 * 1024 * 1024:
                return JsonResponse({'success': False, 'message': 'ZIP file exceeds 600 MB limit.'}, status=400)
            
            # ZIP bomb / nested archive check
            zok, zerr = validate_zip_safety(zip_file)
            if not zok:
                return JsonResponse({'success': False, 'message': zerr}, status=400)

            # Open ZIP directly from file handle (Django spills >10MB to /tmp)
            if isinstance(zip_file, str):
                zf = zipfile.ZipFile(zip_file, 'r')
            elif hasattr(zip_file, 'temporary_file_path'):
                zf = zipfile.ZipFile(zip_file.temporary_file_path(), 'r')
            else:
                zip_file.seek(0)
                zf = zipfile.ZipFile(zip_file, 'r')

            with zf:
                for zip_info in zf.infolist():
                    if zip_info.is_dir():
                        continue

                    # Match async reupload constraints.
                    if zip_info.file_size > 20 * 1024 * 1024:  # 20MB
                        continue
                    
                    file_in_zip = zip_info.filename
                    base_name = os.path.basename(file_in_zip)
                    name_without_ext = os.path.splitext(base_name)[0]
                    ext = os.path.splitext(base_name)[1].lower()
                    
                    if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                        try:
                            image_bytes = zf.read(zip_info.filename)
                            is_valid, error_msg = validate_image_bytes(image_bytes)
                            if is_valid:
                                exact_key = _extract_reupload_stem(name_without_ext)
                                if not exact_key or not _is_supported_reupload_stem(exact_key):
                                    continue

                                if exact_key in seen_stems:
                                    duplicate_name_keys += 1
                                    continue

                                seen_stems.add(exact_key)
                                zip_photos_store.add(
                                    exact_key,
                                    image_bytes,
                                    ext,
                                    base_name,
                                )
                        except Exception:
                            continue
        except Exception as zip_error:
            logger.exception('Error reading ZIP file: %s', zip_error)
            return JsonResponse({'success': False, 'message': 'Error reading ZIP file. Please check the file and try again.'}, status=400)

        if duplicate_name_keys > 0:
            logger.warning(
                "Reupload ZIP has %d duplicate image names; they will be skipped. Processing remaining unique files.",
                duplicate_name_keys,
            )
        
        if not zip_photos_store or len(zip_photos_store) == 0:
            return JsonResponse({'success': False, 'message': 'No valid images found in ZIP file!'}, status=400)
        
        logger.debug(
            "Reupload: %d images extracted from ZIP, keys: %s",
            len(zip_photos_store),
            list(zip_photos_store.keys())[:10],
        )
        
        # Get cards — scoped to selected IDs if provided, else all in table for current status
        card_ids = []
        if 'card_ids' in request.POST:
            try:
                card_ids = json.loads(request.POST.get('card_ids', '[]'))
            except (json.JSONDecodeError, TypeError):
                card_ids = []
        
        # Filter out empty/falsy values
        card_ids = [int(cid) for cid in card_ids if cid and str(cid).strip().isdigit()] if card_ids else []
        
        if card_ids:
            cards_qs = IDCard.objects.filter(table=table, id__in=card_ids).order_by('id')
        else:
            # No specific IDs — reupload to ALL cards in this table (filtered by status if provided)
            status_filter = request.POST.get('status', '')
            if status_filter and status_filter in BaseService.VALID_STATUSES:
                cards_qs = IDCard.objects.filter(table=table, status=status_filter).order_by('id')
            else:
                cards_qs = IDCard.objects.filter(table=table).order_by('id')
        
        updated_count = 0
        matched_count = 0
        errors = []
        
        # Process cards in batches to avoid long-running transactions
        # (SQLite locks the entire DB during a transaction; smaller batches
        # reduce lock duration and prevent "database is locked" errors)
        REUPLOAD_BATCH_SIZE = 50
        all_card_ids = list(cards_qs.values_list('id', flat=True))
        batch_counter = 0
        
        for batch_start in range(0, len(all_card_ids), REUPLOAD_BATCH_SIZE):
            batch_ids = all_card_ids[batch_start:batch_start + REUPLOAD_BATCH_SIZE]
            batch_new_paths = []

            try:
                with transaction.atomic():
                    batch_cards = IDCard.objects.filter(id__in=batch_ids).order_by('id')

                    for card in batch_cards:
                        field_data = card.field_data or {}
                        card_updated = False

                        for img_field in image_fields_to_process:
                            current_value = field_data.get(img_field, '')

                            # Determine what to match against
                            match_key = None
                            existing_path = None

                            if current_value.startswith('PENDING:'):
                                # Extract the reference from PENDING:reference
                                match_key = _extract_reupload_stem(current_value[8:])
                            elif current_value and current_value not in ('NOT_FOUND', ''):
                                # Has existing image - extract filename for matching
                                existing_path = current_value
                                match_key = _extract_reupload_stem(current_value)
                            else:
                                # No current value - skip unless we want to match by card data
                                # Could extend to match by NAME or other field values
                                continue

                            if not match_key:
                                continue

                            # Try strict-first matching with optional legacy fallback.
                            photo_info = _resolve_reupload_photo(match_key, zip_photos_store)
                            if photo_info:
                                matched_count += 1

                                try:
                                    batch_counter += 1

                                    # Use single-authority entry point
                                    if existing_path:
                                        result = ImageService.replace_image(
                                            image_bytes=photo_info['bytes'],
                                            client=client,
                                            field_name=img_field,
                                            existing_path=existing_path,
                                            card=card,
                                            batch_counter=batch_counter,
                                            original_ext=photo_info['ext'],
                                            delete_old_after_save=True,
                                            uploaded_by=request.user if request.user.is_authenticated else None,
                                        )
                                    else:
                                        result = ImageService.save_new_image(
                                            image_bytes=photo_info['bytes'],
                                            client=client,
                                            field_name=img_field,
                                            card=card,
                                            batch_counter=batch_counter,
                                            original_ext=photo_info['ext'],
                                            uploaded_by=request.user if request.user.is_authenticated else None,
                                        )

                                    if result.success and result.data.get('final_value'):
                                        saved_path = result.data['final_value']
                                        field_data[img_field] = saved_path
                                        card_updated = True
                                        batch_new_paths.append(saved_path)
                                        logger.debug("Reupload: Card %s field %s updated to %s",
                                                   card.pk, img_field, saved_path)
                                    else:
                                        errors.append(f"Card {card.pk}: Failed to save {img_field} - {result.message}")
                                except Exception as save_err:
                                    errors.append(f"Card {card.pk}: Error saving {img_field} - {str(save_err)}")

                        if card_updated:
                            card.field_data = field_data
                            card.save()
                            updated_count += 1
            except Exception:
                # Transaction failed: remove newly saved files from this batch.
                for new_path in set(batch_new_paths):
                    try:
                        ImageService.delete_image(new_path)
                    except Exception:
                        pass
                raise

        # Build response
        result_msg = f"Updated {updated_count} cards with {matched_count} images matched"
        # Activity log
        try:
            from core.services.activity_service import ActivityService
            ActivityService.log_image_reupload(
                request,
                updated_count=updated_count,
                matched_count=matched_count,
                table=table,
                target_field=target_field if target_field else '',
            )
        except Exception:
            logger.exception('Image reupload activity log failed')

        response = {
            'success': True,
            'message': result_msg,
            'updated_count': updated_count,
            'matched_count': matched_count,
            'zip_images_count': len(zip_photos_store),
            'duplicates_skipped': duplicate_name_keys,
        }
        
        if errors:
            response['errors'] = errors[:10]
            response['error_count'] = len(errors)
        
        return JsonResponse(response)
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': _safe_error(e)}, status=500)
    finally:
        try:
            if zip_photos_store is not None:
                zip_photos_store.cleanup()
        except Exception:
            pass
        if generated_reupload_zip_path:
            from core.services.background_worker import cleanup_temp_file
            cleanup_temp_file(generated_reupload_zip_path)
        django_cache.delete(lock_key)


# ==================== MODALS HTML (Lazy Load) ====================

@require_http_methods(["GET"])
@api_require_any_authenticated
def api_idcard_modals_html(request, table_id):
    """Return rendered modals.html partial for lazy-loading.
    Used by modal-loader.js to inject modals on first user interaction
    instead of pre-rendering them on every page load.
    """
    from django.template.loader import render_to_string
    from django.http import HttpResponse

    table, err = _check_client_scope_by_table(request.user, table_id)
    if err:
        return err

    html = render_to_string('partials/idcard/modals.html', {'table': table}, request=request)
    return HttpResponse(html, content_type='text/html; charset=utf-8')
