"""
Export Views Module

API views for export operations.
All views are READ-ONLY - they never mutate data.

Features:
- Permission checking
- Client scoping
- Proper error responses
"""
import json
import base64
import logging
import os
from typing import List, Optional, Dict, Any

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from tables.models import Table
from core.services.permission_service import PermissionService, api_require_any_authenticated
from accounts.rate_limit import rate_limit

from django.core.cache import cache as django_cache

from .services import ExportService
from .excel import ExcelExporter
from .zip import ZipExporter, zip_result_to_dict
from .export_throttle import acquire_global_export_slot, release_global_export_slot

logger = logging.getLogger(__name__)

# None means no ID-count cap at request parsing stage.
MAX_EXPORT_CARD_IDS: Optional[int] = None
MAX_EXPORT_JSON_BODY_BYTES = int(os.getenv('MAX_EXPORT_JSON_BODY_BYTES', '5242880'))  # 5 MB

_VALID_STATUSES = {'pending', 'verified', 'approved', 'download', 'pool'}

# Cards above this threshold are routed to async background export.
# Small exports stay sync for instant response; large ones go to BackgroundWorker.
_ASYNC_EXPORT_THRESHOLD = int(os.getenv('ASYNC_EXPORT_THRESHOLD', '200'))

_GLOBAL_THROTTLE_MSG = (
    'Server is busy processing other exports. '
    'Please try again in 30 seconds.'
)


def _is_json_request(request) -> bool:
    return 'application/json' in str(getattr(request, 'content_type', '') or '').lower()


def _get_json_body(request) -> Optional[Dict[str, Any]]:
    """Parse and cache JSON request body once with a defensive size limit."""
    if not _is_json_request(request):
        return None

    if getattr(request, '_exports_json_body_cache_set', False):
        return getattr(request, '_exports_json_body_cache', None)

    body_bytes = request.body or b''
    if MAX_EXPORT_JSON_BODY_BYTES > 0 and len(body_bytes) > MAX_EXPORT_JSON_BODY_BYTES:
        logger.warning(
            'Export JSON body too large: size=%s limit=%s user=%s path=%s',
            len(body_bytes),
            MAX_EXPORT_JSON_BODY_BYTES,
            getattr(getattr(request, 'user', None), 'id', None),
            getattr(request, 'path', ''),
        )
        request._exports_json_body_cache = None
        request._exports_json_body_cache_set = True
        return None

    try:
        parsed = json.loads(body_bytes)
    except (json.JSONDecodeError, ValueError, TypeError):
        request._exports_json_body_cache = None
        request._exports_json_body_cache_set = True
        return None

    if isinstance(parsed, dict):
        request._exports_json_body_cache = parsed
        request._exports_json_body_cache_set = True
        return parsed

    request._exports_json_body_cache = None
    request._exports_json_body_cache_set = True
    return None


def _get_status_from_request(request) -> str:
    """Extract status label from POST body (JSON or form data)."""
    status = ''
    if _is_json_request(request):
        data = _get_json_body(request) or {}
        status = data.get('status', '')
    if not status:
        status = request.POST.get('status', '')
    return status if status in _VALID_STATUSES else ''


def _normalize_positive_int_ids(values, max_items: Optional[int] = MAX_EXPORT_CARD_IDS) -> List[int]:
    """Normalize mixed payload IDs to unique positive integers with a hard cap."""
    if not isinstance(values, list):
        return []

    out: List[int] = []
    seen = set()
    for value in values:
        if isinstance(value, bool):
            continue
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if number <= 0 or number in seen:
            continue
        seen.add(number)
        out.append(number)
        if max_items is not None and len(out) >= max_items:
            break
    return out


def _get_card_ids_from_request(request, table_id: int = None) -> Optional[List[int]]:
    """
    Extract card IDs from POST request body.
    
    Handles both form data and JSON body.
    When no explicit card_ids are provided but table_id is given,
    falls back to ALL card IDs for the requested status from the database.
    
    Args:
        request: Django HttpRequest
        table_id: Optional table ID to fall back to full status query
        
    Returns:
        List of card IDs or None if no valid IDs found
    """
    card_ids = None
    user = getattr(request, 'user', None)
    is_super_admin = bool(user and getattr(user, 'is_authenticated', False) and PermissionService.is_super_admin(user))
    
    # Try JSON body first
    if _is_json_request(request):
        data = _get_json_body(request) or {}
        card_ids = data.get('card_ids', [])
    
    # Fall back to POST data
    if not card_ids:
        card_ids_str = request.POST.get('card_ids', '')
        if card_ids_str:
            try:
                card_ids = json.loads(card_ids_str)
            except (json.JSONDecodeError, ValueError):
                # Try comma-separated
                card_ids = [int(x.strip()) for x in card_ids_str.split(',') if x.strip().isdigit()]
    
    # Validate and filter
    if card_ids:
        max_items = None if is_super_admin else MAX_EXPORT_CARD_IDS
        card_ids = _normalize_positive_int_ids(card_ids, max_items=max_items)
    
    # Fallback: if no card_ids provided but table_id is available,
    # fetch ALL card IDs for the requested status from the database,
    # respecting any active search/class/section filters.
    if not card_ids and table_id:
        from tables.models import IDCard, Table
        from core.services import IDCardService
        status = _get_status_from_request(request)
        # Extract optional filters from JSON body
        search_q = ''
        class_f = ''
        section_f = ''
        course_f = ''
        branch_f = ''
        image_column = ''
        image_condition = ''
        from_date = ''
        to_date = ''
        if _is_json_request(request):
            body = _get_json_body(request) or {}
            search_q = (body.get('search') or '').strip()
            class_f = (body.get('class') or body.get('class_filter') or '').strip()
            section_f = (body.get('section') or body.get('section_filter') or '').strip()
            course_f = (body.get('course') or body.get('course_filter') or '').strip()
            branch_f = (body.get('branch') or body.get('branch_filter') or '').strip()
            image_column = (body.get('image_column') or '').strip()
            image_condition = (body.get('image_condition') or '').strip()
            from_date = (body.get('from') or '').strip()
            to_date = (body.get('to') or '').strip()
        try:
            from django.db.models import Q, CharField
            from django.db.models.fields.json import KeyTextTransform
            from django.db.models.functions import Cast
            from core.views.idcard_helpers import (
                _apply_client_staff_row_scope,
                _build_class_filter_q,
                _get_class_section_course_branch_field_names,
            )

            table = Table.objects.select_related('organisation').filter(id=table_id).first()
            if not table:
                return None

            user = getattr(request, 'user', None)
            if not user or not getattr(user, 'is_authenticated', False):
                logger.warning("Export fallback blocked for unauthenticated request on table %s", table_id)
                return None
            table_org_id = getattr(table, 'organisation_id', None) or getattr(getattr(table, 'group', None), 'client_id', None) or getattr(table, 'client_id', None)
            if table_org_id and not PermissionService.can_access_organisation(user, table_org_id):
                logger.warning("Export fallback blocked for unauthorized user %s on table %s", getattr(user, 'id', None), table_id)
                return None

            qs = IDCard.objects.filter(table=table)
            qs = _apply_client_staff_row_scope(qs, user, table)
            if status:
                qs = qs.filter(status=status)
            if search_q:
                qs = IDCardService._apply_search_filter(qs, search_q, table=table)
            # Keep export fallback filtering consistent with the listing API.
            if class_f or section_f or course_f or branch_f:
                class_field_name, section_field_name, course_field_name, branch_field_name = (
                    _get_class_section_course_branch_field_names(table)
                )
                if class_f and class_field_name:
                    qs = _build_class_filter_q(qs, class_f, class_field_name)
                if section_f and section_field_name:
                    qs = qs.annotate(_sec=KeyTextTransform(section_field_name, 'field_data')).filter(_sec__iexact=section_f)
                if course_f and course_field_name:
                    qs = qs.annotate(_course=KeyTextTransform(course_field_name, 'field_data')).filter(_course__iexact=course_f)
                if branch_f and branch_field_name:
                    qs = qs.annotate(_branch=KeyTextTransform(branch_field_name, 'field_data')).filter(_branch__iexact=branch_f)
            if image_column and image_condition in ('complete', 'pending', 'incomplete'):
                qs = qs.annotate(_img=Cast(KeyTextTransform(image_column, 'field_data'), CharField()))
                if image_condition == 'complete':
                    qs = qs.exclude(_img__isnull=True).exclude(_img='').exclude(_img='NOT_FOUND')
                    qs = qs.exclude(_img__startswith='PENDING:')
                elif image_condition == 'pending':
                    qs = qs.filter(_img__startswith='PENDING:')
                elif image_condition == 'incomplete':
                    qs = qs.filter(Q(_img__isnull=True) | Q(_img='') | Q(_img='NOT_FOUND'))
            # DateTime range filter applies only to download status.
            if status == 'download':
                if from_date:
                    try:
                        from django.utils.dateparse import parse_datetime
                        dt = parse_datetime(from_date)
                        if dt:
                            qs = qs.filter(downloaded_at__gte=dt)
                    except (ValueError, TypeError):
                        pass
                if to_date:
                    try:
                        from django.utils.dateparse import parse_datetime
                        dt = parse_datetime(to_date)
                        if dt:
                            qs = qs.filter(downloaded_at__lte=dt)
                    except (ValueError, TypeError):
                        pass
            max_items = None if is_super_admin else MAX_EXPORT_CARD_IDS
            if max_items is None:
                card_ids = list(qs.order_by('id').values_list('id', flat=True))
            else:
                card_ids = list(qs.order_by('id').values_list('id', flat=True)[:max_items])
        except Exception as e:
            logger.warning("Export card_ids fallback query failed for table %s: %s", table_id, e)
    
    return card_ids if card_ids else None


def _get_image_rename_options_from_request(request) -> Optional[Dict[str, Any]]:
    """
    Extract optional image rename settings from JSON body.

    Expected shape:
        {
            "rename_options": {
                "enabled": true,
                "mode": "rename" | "generate",
                "output_format": "zip" | "pdf_zip",
                "selected_image_field": "PHOTO",
                "image_name_fields": {
                    "PHOTO": "Student Name" | ["Student Name", "Class", "Section"],
                    "FATHER_PHOTO": "Father Name" | ["Student Name", "Father Name"],
                    "MOTHER_PHOTO": "Mother Name" | ["Student Name", "Mother Name"]
                },
                "generate_options": {
                    "enabled": true,
                    "name_field": "Student Name",
                    "detail_fields": ["Class", "Section"],
                    "max_detail_lines": 2,
                    "compress_enabled": true,
                    "target_size_kb": 40,
                    "maintain_dimensions": true
                }
            }
        }
    """
    if not _is_json_request(request):
        return None

    data = _get_json_body(request)
    if not data:
        return None

    rename_options = data.get('rename_options')
    if not isinstance(rename_options, dict):
        return None
    if rename_options.get('enabled') is not True:
        return None

    raw_map = rename_options.get('image_name_fields')
    if not isinstance(raw_map, dict):
        return None

    cleaned_map: Dict[str, Any] = {}
    for key, value in raw_map.items():
        k = str(key or '').strip().upper()
        if not k:
            continue
        if len(k) > 60:
            continue

        if isinstance(value, (list, tuple)):
            values = []
            seen = set()
            for item in value:
                v = str(item or '').strip()
                if not v or len(v) > 120:
                    continue
                v_norm = v.lower()
                if v_norm in seen:
                    continue
                seen.add(v_norm)
                values.append(v)
            if values:
                cleaned_map[k] = values
            continue

        v = str(value or '').strip()
        if not v or len(v) > 120:
            continue
        cleaned_map[k] = v

    if not cleaned_map:
        return None

    selected_image_field = str(rename_options.get('selected_image_field') or '').strip()
    if len(selected_image_field) > 120:
        selected_image_field = ''

    raw_output_format = str(rename_options.get('output_format', 'zip') or 'zip').strip().lower()
    output_format = 'pdf_zip' if raw_output_format == 'pdf_zip' else 'zip'

    raw_mode = str(rename_options.get('mode', 'rename') or 'rename').strip().lower()
    mode = 'generate' if raw_mode == 'generate' else 'rename'

    cleaned_options = {
        'enabled': True,
        'image_name_fields': cleaned_map,
        'output_format': output_format,
        'mode': mode,
    }

    if selected_image_field:
        cleaned_options['selected_image_field'] = selected_image_field

    if mode == 'generate':
        raw_generate_options = rename_options.get('generate_options')
        if not isinstance(raw_generate_options, dict):
            raw_generate_options = {}

        name_field = str(raw_generate_options.get('name_field') or '').strip()
        if len(name_field) > 120:
            name_field = ''

        raw_detail_fields = raw_generate_options.get('detail_fields')
        if not isinstance(raw_detail_fields, (list, tuple)):
            raw_detail_fields = []

        detail_fields = []
        seen_details = set()
        for item in raw_detail_fields:
            value = str(item or '').strip()
            if not value or len(value) > 120:
                continue
            key = value.lower()
            if key in seen_details:
                continue
            seen_details.add(key)
            detail_fields.append(value)

        # Fallback: derive name/details from image_name_fields mapping when
        # explicit generate_options are not provided.
        if not name_field:
            mapping_values = []
            for mapped in cleaned_map.values():
                if isinstance(mapped, list):
                    mapping_values = mapped
                    break
                if isinstance(mapped, str):
                    mapping_values = [mapped]
                    break
            if mapping_values:
                name_field = mapping_values[0]
                if not detail_fields:
                    detail_fields = mapping_values[1:]

        class_field = str(raw_generate_options.get('class_field') or '').strip()
        if len(class_field) > 120:
            class_field = ''

        section_field = str(raw_generate_options.get('section_field') or '').strip()
        if len(section_field) > 120:
            section_field = ''

        custom_date = str(raw_generate_options.get('custom_date') or '').strip()
        if len(custom_date) > 40:
            custom_date = custom_date[:40]

        raw_size_preset = str(raw_generate_options.get('size_preset', 'size_23x34') or 'size_23x34').strip().lower()
        size_preset = 'size_37x53' if raw_size_preset in ('size_37x53', '37x53', 'large') else 'size_23x34'

        if not class_field and detail_fields:
            class_field = detail_fields[0]
        if not section_field and len(detail_fields) > 1:
            section_field = detail_fields[1]

        raw_detail_mode = str(raw_generate_options.get('detail_mode') or '').strip().lower()
        if raw_detail_mode not in ('class_only', 'class_section', 'custom_date'):
            if custom_date:
                raw_detail_mode = 'custom_date'
            elif class_field and section_field:
                raw_detail_mode = 'class_section'
            else:
                raw_detail_mode = 'class_only'
        detail_mode = raw_detail_mode

        resolved_detail_fields = []
        if detail_mode == 'class_section':
            if class_field:
                resolved_detail_fields.append(class_field)
            if section_field and section_field.lower() != str(class_field or '').lower():
                resolved_detail_fields.append(section_field)
        elif detail_mode == 'class_only':
            if class_field:
                resolved_detail_fields.append(class_field)

        max_detail_lines = 1

        compress_enabled = raw_generate_options.get('compress_enabled') is True

        raw_target_kb = raw_generate_options.get('target_size_kb', 40)
        try:
            target_size_kb = int(raw_target_kb)
        except (TypeError, ValueError):
            target_size_kb = 40
        target_size_kb = max(10, min(200, target_size_kb))

        cleaned_options['generate_options'] = {
            'enabled': True,
            'name_field': name_field,
            'detail_fields': resolved_detail_fields,
            'max_detail_lines': max_detail_lines,
            'detail_mode': detail_mode,
            'class_field': class_field,
            'section_field': section_field,
            'custom_date': custom_date,
            'size_preset': size_preset,
            'compress_enabled': compress_enabled,
            'target_size_kb': target_size_kb,
            'maintain_dimensions': True,
        }

    return cleaned_options


def _check_export_permission(request, skip_status_check=False):
    """
    Check if user has export permission.
    
    Clients/client_staff are blocked from exporting approved/download status
    cards and from the download-all endpoint (unless skip_status_check=True,
    used for PDF exports which clients are allowed on all statuses).
    
    Returns:
        None if permitted, JsonResponse with error if not
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'message': 'Authentication required'
        }, status=401)
    
    if not PermissionService.can_bulk_download(request.user):
        return JsonResponse({
            'success': False,
            'message': 'Permission denied: You do not have bulk download access'
        }, status=403)

    # Keep export access aligned with status list permissions.
    status = _get_status_from_request(request)
    if status:
        is_client_role = PermissionService.is_client_role(request.user) or getattr(request.user, 'role', '') == 'guest_prime_manager'
        if not (skip_status_check and is_client_role):
            required_perm = PermissionService.STATUS_LIST_PERM_MAP.get(status)
            if required_perm and not PermissionService.has(request.user, required_perm):
                return JsonResponse({
                    'success': False,
                    'message': 'Permission denied: You do not have access to this list'
                }, status=403)
    
    # Block client/client_staff from exporting approved or download status cards
    # (skipped for PDF exports — clients can download PDF on all statuses)
    if not skip_status_check and PermissionService.is_client_role(request.user):
        if status in ('approved', 'download'):
            return JsonResponse({
                'success': False,
                'message': 'Export is not available for this list'
            }, status=403)
    
    return None


def _check_image_export_permission(request):
    """Check if user has permission to export images.

    Allows access if the user has bulk download or image-mode permissions.
    Keeps list-permission and client status restrictions aligned with exports.
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'message': 'Authentication required'
        }, status=401)

    has_bulk = PermissionService.can_bulk_download(request.user)
    has_image_modes = (
        PermissionService.can_use_image_rename_mode(request.user)
        or PermissionService.can_use_image_generate_mode(request.user)
    )
    if not (has_bulk or has_image_modes):
        return JsonResponse({
            'success': False,
            'message': 'Permission denied: You do not have image download access'
        }, status=403)

    status = _get_status_from_request(request)
    if status:
        required_perm = PermissionService.STATUS_LIST_PERM_MAP.get(status)
        if required_perm and not PermissionService.has(request.user, required_perm):
            return JsonResponse({
                'success': False,
                'message': 'Permission denied: You do not have access to this list'
            }, status=403)

    return None


def _check_client_pdf_only(request):
    """
    Block client / client_staff from non-PDF export formats.
    Clients are only allowed PDF downloads; xlsx, docx, images are admin-only.

    Returns:
        None if permitted, JsonResponse with error if blocked.
    """
    if PermissionService.is_client_role(request.user):
        return JsonResponse({
            'success': False,
            'message': 'Only PDF download is available for your account'
        }, status=403)
    return None


def _check_image_mode_permission(request, rename_options):
    """Validate mode-specific permissions for image export advanced flows."""
    if not isinstance(rename_options, dict):
        return None

    mode = str(rename_options.get('mode') or '').strip().lower()
    if mode == 'rename' and not PermissionService.can_use_image_rename_mode(request.user):
        return JsonResponse({
            'success': False,
            'message': 'Permission denied: Rename mode is not enabled for your account'
        }, status=403)

    if mode == 'generate' and not PermissionService.can_use_image_generate_mode(request.user):
        return JsonResponse({
            'success': False,
            'message': 'Permission denied: Generate mode is not enabled for your account'
        }, status=403)

    return None


def _check_export_client_scope(request, table_id):
    """
    Check if user has access to the client owning this table.
    Delegates to PermissionService.can_access_client() (single authority).
    
    Returns:
        None if permitted, JsonResponse with error if not
    """
    from core.views.idcard_helpers import _check_client_scope_by_table

    _, error = _check_client_scope_by_table(request.user, table_id)
    if error:
        return error
    return None


def _log_export_failure(request, export_type, message, table_id=None, table_name=''):
    try:
        from core.services.activity_service import ActivityService

        resolved_table_name = table_name or ''
        resolved_table_id = table_id
        if not resolved_table_name and table_id:
            resolved_table_name = (
                Table.objects.filter(id=table_id)
                .values_list('name', flat=True)
                .first()
            ) or ''

        ActivityService.log_export_failed(
            request=request,
            user=getattr(request, 'user', None),
            export_type=export_type,
            message=message,
            table_id=resolved_table_id,
            table_name=resolved_table_name,
            source='sync',
        )
    except Exception:
        logger.exception('Failed to write export failure activity log')


def _acquire_export_lock(user_id, table_id, export_type='generic', max_concurrent=5, ttl=300, request_user=None):
    """Allow up to max_concurrent concurrent exports per user/table/type.

    Each export type (pdf, xlsx, docx, images, download_all) gets its own
    set of lock slots so that e.g. 3 PDF downloads can run at the same time
    while an XLSX export is also in progress.

    TTL=300s (5 min) safety net — locks are always released in the finally
    block, but TTL handles crashes / timeouts gracefully.

    Returns (acquired: bool, lock_key: str).
    """
    effective_max_concurrent = max(1, int(max_concurrent or 1))
    effective_max_concurrent = max(1, min(effective_max_concurrent, 10))

    for slot in range(effective_max_concurrent):
        lock_key = f'export_lock:{user_id}:{table_id}:{export_type}:{slot}'
        if django_cache.add(lock_key, 1, ttl):
            return True, lock_key
    return False, ''

def _release_export_lock(lock_key):
    """Release export lock."""
    if lock_key:
        django_cache.delete(lock_key)


def _safe_media_download_url(file_path: str) -> str:
    """Build MEDIA_URL for an absolute file path only when it stays under MEDIA_ROOT."""
    raw = str(file_path or '').strip()
    if not raw:
        return ''

    media_root = os.path.abspath(settings.MEDIA_ROOT)
    candidate = os.path.abspath(raw)
    try:
        if os.path.commonpath([media_root, candidate]) != media_root:
            return ''
    except ValueError:
        return ''

    rel_path = os.path.relpath(candidate, media_root).replace('\\', '/')
    return f"{settings.MEDIA_URL.rstrip('/')}/{rel_path}"


def _disk_zip_result_to_payload(disk_result) -> Dict[str, Any]:
    """Convert disk ZIP export result to JSON payload consumed by the frontend."""
    zip_files = []
    for zf in getattr(disk_result, 'zip_files', []) or []:
        download_url = _safe_media_download_url(getattr(zf, 'path', ''))
        if not download_url:
            continue
        zip_files.append({
            'field_name': getattr(zf, 'field_name', 'ALL') or 'ALL',
            'filename': getattr(zf, 'filename', 'images.zip') or 'images.zip',
            'download_url': download_url,
            'image_count': int(getattr(zf, 'image_count', 0) or 0),
        })

    if not zip_files:
        return {
            'success': False,
            'message': 'Large image export failed. Please try again.',
        }

    payload = {
        'success': True,
        'zip_files': zip_files,
        'total_images': int(getattr(disk_result, 'total_images', 0) or 0),
        'total_zips': len(zip_files),
    }
    if len(zip_files) == 1:
        payload['download_url'] = zip_files[0]['download_url']
        payload['filename'] = zip_files[0]['filename']
    return payload


def _write_http_response_to_file(response, file_path: str) -> int:
    """Persist HttpResponse/StreamingHttpResponse content to disk safely."""
    if response is None:
        return 0

    bytes_written = 0
    with open(file_path, 'wb') as handle:
        if hasattr(response, 'streaming_content'):
            for chunk in response.streaming_content:
                if isinstance(chunk, str):
                    chunk = chunk.encode('utf-8')
                if not chunk:
                    continue
                handle.write(chunk)
                bytes_written += len(chunk)
        elif hasattr(response, 'content'):
            payload = response.content or b''
            if isinstance(payload, str):
                payload = payload.encode('utf-8')
            if payload:
                handle.write(payload)
                bytes_written = len(payload)

    return bytes_written


# =============================================================================
# EXCEL EXPORT
# =============================================================================

@api_require_any_authenticated
@require_POST
@rate_limit(max_requests=10, window_seconds=60, key_prefix='export')
def api_export_xlsx(request, table_id: int) -> HttpResponse:
    """
    Export cards to Excel format.
    
    POST /api/table/<table_id>/export/xlsx/
    POST /api/table/<table_id>/cards/download-xlsx/  (legacy URL in core)
    
    Body:
        {
            "card_ids": [1, 2, 3]
        }
        
    Returns:
        Excel file download or JSON error
    """
    # Check permission
    perm_error = _check_export_permission(request)
    if perm_error:
        return perm_error

    # Client/client_staff can only download PDF for spreadsheet exports.
    pdf_only = _check_client_pdf_only(request)
    if pdf_only:
        return pdf_only
    
    # Check client scope for admin_staff
    scope_error = _check_export_client_scope(request, table_id)
    if scope_error:
        return scope_error
    
    card_ids = _get_card_ids_from_request(request, table_id=table_id)
    if not card_ids:
        return JsonResponse({
            'success': False,
            'message': 'No cards selected for export'
        }, status=400)
    
    # Route large exports to async background worker
    if len(card_ids) > _ASYNC_EXPORT_THRESHOLD:
        from .tasks import BackgroundExportManager
        task_id = BackgroundExportManager.start_xlsx_export(
            user=request.user,
            table_id=table_id,
            card_ids=card_ids,
            status=_get_status_from_request(request),
        )
        try:
            from core.services.activity_service import ActivityService
            ActivityService.log_cards_download(request, card_ids, 'Excel Data (Async Requested)')
        except Exception:
            pass
        logger.info("Export XLSX (async): user=%s table=%d cards=%d task=%s",
                    request.user.id, table_id, len(card_ids), task_id)
        return JsonResponse({
            'success': True,
            'task_id': task_id,
            'async': True,
            'card_count': len(card_ids),
        })

    # Concurrent export guard
    acquired, lock_key = _acquire_export_lock(request.user.id, table_id, 'xlsx', request_user=request.user)
    if not acquired:
        return JsonResponse({'success': False, 'level': 'warning', 'message': 'Too many Excel exports running. Please wait.'}, status=429)
    global_slot = acquire_global_export_slot()
    if global_slot is None:
        _release_export_lock(lock_key)
        return JsonResponse({'success': False, 'level': 'warning', 'message': _GLOBAL_THROTTLE_MSG}, status=429)
    try:
        service = ExportService(request.user)
        result = service.export_excel(table_id, card_ids, status=_get_status_from_request(request))
        
        if not result.success:
            _log_export_failure(request, 'xlsx', result.message, table_id=table_id)
            return JsonResponse({
                'success': False,
                'message': result.message
            }, status=400)
        
        try:
            from core.services.activity_service import ActivityService
            ActivityService.log_cards_download(request, card_ids, 'Excel Data')
        except Exception:
            pass

        logger.info("Export XLSX: user=%s table=%d cards=%d", request.user.id, table_id, len(card_ids))
        return result.response
    except Exception as e:
        logger.exception("Export XLSX failed: %s", e)
        _log_export_failure(request, 'xlsx', str(e), table_id=table_id)
        return JsonResponse({'success': False, 'message': 'Export failed. Please try again or reduce the number of cards.'}, status=500)
    finally:
        release_global_export_slot(global_slot)
        _release_export_lock(lock_key)


# =============================================================================
# WORD EXPORT
# =============================================================================

@api_require_any_authenticated
@require_POST
@rate_limit(max_requests=10, window_seconds=60, key_prefix='export')
def api_export_docx(request, table_id: int) -> HttpResponse:
    """
    Export cards to Word format.
    
    POST /api/table/<table_id>/export/docx/
    POST /api/table/<table_id>/cards/download-docx/  (legacy URL in core)
    
    Body:
        {
            "card_ids": [1, 2, 3],
            "format": "docx"  // or "doc"
        }
        
    Returns:
        Word file download or JSON error
    """
    # Check permission
    perm_error = _check_export_permission(request)
    if perm_error:
        return perm_error
    
    # Client/client_staff can only download PDF
    pdf_only = _check_client_pdf_only(request)
    if pdf_only:
        return pdf_only
    
    # Check client scope for admin_staff
    scope_error = _check_export_client_scope(request, table_id)
    if scope_error:
        return scope_error

    is_super_admin = PermissionService.is_super_admin(request.user)

    # Get format preference, template_id, class filter and custom break options
    doc_format = 'docx'
    template_id = None
    class_filter_enabled = False
    selected_classes = []
    break_enabled = False
    break_pages = 0
    break_mode = 'none'

    if _is_json_request(request):
        data = _get_json_body(request) or {}
        tpl_val = data.get('template_id', '')
        if tpl_val:
            try:
                template_id = int(tpl_val)
            except (ValueError, TypeError):
                pass
        class_filter_enabled = bool(data.get('class_filter_enabled'))
        selected_classes = data.get('selected_classes') or []
        break_enabled = bool(data.get('break_enabled'))
        try:
            break_pages = int(data.get('break_pages') or 0)
        except (ValueError, TypeError):
            break_pages = 0
        requested_break_mode = str(data.get('break_mode') or '').strip().lower()
        if requested_break_mode in ('class_only', 'class_section', 'none'):
            break_mode = requested_break_mode

    card_ids = _get_card_ids_from_request(request, table_id=table_id)
    if not card_ids:
        return JsonResponse({
            'success': False,
            'message': 'No cards selected for export'
        }, status=400)

    # Apply class filter if enabled
    if class_filter_enabled and selected_classes:
        from core.views.idcard_helpers import _get_class_section_course_branch_field_names
        from tables.models import Table, IDCard
        from core.utils.field_utils import normalize_class_value

        try:
            table = Table.objects.get(id=table_id)
            class_field, _, _, _ = _get_class_section_course_branch_field_names(table)
            if class_field:
                cards_qs = IDCard.objects.filter(id__in=card_ids)
                filtered_card_ids = []
                selected_classes_set = {normalize_class_value(str(c).strip()) for c in selected_classes if c}
                for card in cards_qs:
                    val = card.field_data.get(class_field)
                    if val:
                        norm = normalize_class_value(str(val).strip())
                        if norm in selected_classes_set:
                            filtered_card_ids.append(card.id)
                card_ids = filtered_card_ids
        except Table.DoesNotExist:
            pass

    if not card_ids:
        return JsonResponse({
            'success': False,
            'message': 'No cards selected for export after applying class filter'
        }, status=400)
    
    # Route large exports to async background worker
    if len(card_ids) > _ASYNC_EXPORT_THRESHOLD:
        from .tasks import BackgroundExportManager
        task_id = BackgroundExportManager.start_docx_export(
            user=request.user,
            table_id=table_id,
            card_ids=card_ids,
            status=_get_status_from_request(request),
            doc_format=doc_format,
            template_id=template_id,
            break_enabled=break_enabled,
            break_pages=break_pages,
            break_mode=break_mode,
        )
        try:
            from core.services.activity_service import ActivityService
            ActivityService.log_cards_download(request, card_ids, f'Word Document ({doc_format.upper()}, Async Requested)')
        except Exception:
            pass
        logger.info("Export %s (async): user=%s table=%d cards=%d task=%s",
                    doc_format.upper(), request.user.id, table_id, len(card_ids), task_id)
        return JsonResponse({
            'success': True,
            'task_id': task_id,
            'async': True,
            'card_count': len(card_ids),
        })

    # Concurrent export guard
    acquired, lock_key = _acquire_export_lock(request.user.id, table_id, 'docx', request_user=request.user)
    if not acquired:
        return JsonResponse({'success': False, 'level': 'warning', 'message': 'Too many Word exports running. Please wait.'}, status=429)
    global_slot = acquire_global_export_slot()
    if global_slot is None:
        _release_export_lock(lock_key)
        return JsonResponse({'success': False, 'level': 'warning', 'message': _GLOBAL_THROTTLE_MSG}, status=429)
    try:
        service = ExportService(request.user)
        allow_large_exports = is_super_admin

        result = service.export_word(
            table_id,
            card_ids,
            doc_format=doc_format,
            status=_get_status_from_request(request),
            template_id=template_id,
            allow_large=allow_large_exports,
            break_enabled=break_enabled,
            break_pages=break_pages,
            break_mode=break_mode,
        )
        
        if not result.success:
            _log_export_failure(request, doc_format, result.message, table_id=table_id)
            return JsonResponse({
                'success': False,
                'message': result.message
            }, status=400)
        
        try:
            from core.services.activity_service import ActivityService
            ActivityService.log_cards_download(request, card_ids, f'Word Document ({doc_format.upper()})')
        except Exception:
            pass

        logger.info("Export %s: user=%s table=%d cards=%d", doc_format.upper(), request.user.id, table_id, len(card_ids))
        return result.response
    except Exception as e:
        logger.exception("Export DOCX failed: %s", e)
        _log_export_failure(request, doc_format, str(e), table_id=table_id)
        return JsonResponse({'success': False, 'message': 'Export failed. Please try again or reduce the number of cards.'}, status=500)
    finally:
        release_global_export_slot(global_slot)
        _release_export_lock(lock_key)


# =============================================================================
# PDF EXPORT
# =============================================================================

@api_require_any_authenticated
@require_POST
@rate_limit(max_requests=10, window_seconds=60, key_prefix='export')
def api_export_pdf(request, table_id: int) -> HttpResponse:
    """
    Export cards to PDF format.
    
    POST /api/table/<table_id>/export/pdf/
    POST /api/table/<table_id>/cards/download-pdf/  (legacy URL in core)
    
    Body:
        {
            "card_ids": [1, 2, 3]
        }
        
    Returns:
        PDF file download or JSON error
    """
    perm_error = _check_export_permission(request, skip_status_check=True)
    if perm_error:
        return perm_error
    
    # Check client scope for admin_staff
    scope_error = _check_export_client_scope(request, table_id)
    if scope_error:
        return scope_error

    card_ids = _get_card_ids_from_request(request, table_id=table_id)
    if not card_ids:
        return JsonResponse({
            'success': False,
            'message': 'No cards selected for export'
        }, status=400)
    
    # Extract template_id from request.
    # Font mode is intentionally locked to 'auto' for consistent layout.
    template_id = None
    font_mode = 'auto'
    shorten_titles = False
    break_mode = 'class_section'
    if _is_json_request(request):
        data = _get_json_body(request) or {}
        tpl_val = data.get('template_id', '')
        if tpl_val:
            try:
                template_id = int(tpl_val)
            except (ValueError, TypeError):
                pass
        shorten_titles = bool(data.get('shorten_titles', False))
        requested_break_mode = str(data.get('break_mode') or '').strip().lower()
        if requested_break_mode in ('class_only', 'class_section'):
            break_mode = requested_break_mode
        prefer_sync = bool(data.get('prefer_sync', False))
    else:
        prefer_sync = False
    
    # Route large PDF exports to async path automatically unless the caller
    # explicitly prefers the stable synchronous path.
    if not prefer_sync and len(card_ids) > _ASYNC_EXPORT_THRESHOLD:
        from .tasks import BackgroundExportManager
        task_id = BackgroundExportManager.start_pdf_export(
            user=request.user,
            table_id=table_id,
            card_ids=card_ids,
            status=_get_status_from_request(request),
            template_id=template_id,
            font_mode=font_mode,
            shorten_titles=shorten_titles,
            break_mode=break_mode,
        )
        try:
            from core.services.activity_service import ActivityService
            ActivityService.log_cards_download(request, card_ids, 'PDF Document (Async Auto-Routed)')
        except Exception:
            pass
        logger.info("Export PDF (async auto-routed): user=%s table=%d cards=%d task=%s",
                    request.user.id, table_id, len(card_ids), task_id)
        return JsonResponse({
            'success': True,
            'task_id': task_id,
            'async': True,
            'card_count': len(card_ids),
        })

    # Concurrent export guard
    acquired, lock_key = _acquire_export_lock(request.user.id, table_id, 'pdf', request_user=request.user)
    if not acquired:
        return JsonResponse({'success': False, 'level': 'warning', 'message': 'Too many PDF exports running. Please wait.'}, status=429)
    global_slot = acquire_global_export_slot()
    if global_slot is None:
        _release_export_lock(lock_key)
        return JsonResponse({'success': False, 'level': 'warning', 'message': _GLOBAL_THROTTLE_MSG}, status=429)
    try:
        service = ExportService(request.user)
        result = service.export_pdf(
            table_id,
            card_ids,
            status=_get_status_from_request(request),
            template_id=template_id,
            font_mode=font_mode,
            shorten_titles=shorten_titles,
            break_mode=break_mode,
        )
        
        if not result.success:
            _log_export_failure(request, 'pdf', result.message, table_id=table_id)
            return JsonResponse({
                'success': False,
                'message': result.message
            }, status=400)
        
        try:
            from core.services.activity_service import ActivityService
            ActivityService.log_cards_download(request, card_ids, 'PDF Document')
        except Exception:
            pass

        logger.info("Export PDF: user=%s table=%d cards=%d", request.user.id, table_id, len(card_ids))
        return result.response
    except Exception as e:
        logger.exception("Export PDF failed: %s", e)
        _log_export_failure(request, 'pdf', str(e), table_id=table_id)
        return JsonResponse({'success': False, 'message': 'Export failed. Please try again or reduce the number of cards.'}, status=500)
    finally:
        release_global_export_slot(global_slot)
        _release_export_lock(lock_key)


# =============================================================================
# ASYNC PDF EXPORT (Background generation with polling)
# =============================================================================

# Threshold: exports with more cards than this use background generation
_ASYNC_PDF_THRESHOLD = 500

@api_require_any_authenticated
@require_POST
@rate_limit(max_requests=10, window_seconds=60, key_prefix='export')
def api_export_pdf_async(request, table_id: int) -> JsonResponse:
    """
    Start a background PDF export for large datasets.
    
    Returns a task_id immediately. Client polls api_export_status()
    until state='completed', then downloads the file.
    
    POST /api/table/<table_id>/export/pdf-async/
    
    Body:
        { "card_ids": [1, 2, 3], "template_id": 5 }
    
    Returns:
        { "success": true, "task_id": "abc123", "async": true }
    """
    perm_error = _check_export_permission(request, skip_status_check=True)
    if perm_error:
        return perm_error
    
    scope_error = _check_export_client_scope(request, table_id)
    if scope_error:
        return scope_error

    is_super_admin = PermissionService.is_super_admin(request.user)
    
    card_ids = _get_card_ids_from_request(request, table_id=table_id)
    if not card_ids:
        return JsonResponse({
            'success': False,
            'message': 'No cards selected for export'
        }, status=400)
    
    template_id = None
    font_mode = 'auto'
    shorten_titles = False
    break_mode = 'class_section'
    if _is_json_request(request):
        data = _get_json_body(request) or {}
        tpl_val = data.get('template_id', '')
        if tpl_val:
            try:
                template_id = int(tpl_val)
            except (ValueError, TypeError):
                pass
        shorten_titles = bool(data.get('shorten_titles', False))
        requested_break_mode = str(data.get('break_mode') or '').strip().lower()
        if requested_break_mode in ('class_only', 'class_section'):
            break_mode = requested_break_mode
    
    from .tasks import BackgroundExportManager
    
    task_id = BackgroundExportManager.start_pdf_export(
        user=request.user,
        table_id=table_id,
        card_ids=card_ids,
        status=_get_status_from_request(request),
        template_id=template_id,
        font_mode=font_mode,
        shorten_titles=shorten_titles,
        break_mode=break_mode,
    )
    
    try:
        from core.services.activity_service import ActivityService
        ActivityService.log_cards_download(request, card_ids, 'PDF Document (Async Requested)')
    except Exception:
        pass

    logger.info("Export PDF (async): user=%s table=%d cards=%d task=%s",
                request.user.id, table_id, len(card_ids), task_id)
    
    return JsonResponse({
        'success': True,
        'task_id': task_id,
        'async': True,
        'card_count': len(card_ids),
    })


@api_require_any_authenticated
def api_export_status(request, task_id: str) -> JsonResponse:
    """
    Check the status of a background export task.
    
    GET /api/export/status/<task_id>/
    
    Returns:
        {
            "success": true,
            "state": "processing|completed|failed",
            "progress": 50,
            "message": "Generating PDF for 2000 cards...",
            "download_url": "/media/temp/exports/abc123_file.pdf"  (when completed)
        }
    """
    from .tasks import BackgroundExportManager
    
    status = BackgroundExportManager.get_status(task_id, user=request.user)
    if status is None:
        return JsonResponse({
            'success': False,
            'message': 'Export task not found or expired'
        }, status=404)
    
    return JsonResponse({
        'success': True,
        'state': status['state'],
        'progress': status['progress'],
        'progress_percentage': status.get('progress_percentage', 0),
        'eta_seconds': status.get('eta_seconds'),
        'message': status['message'],
        'download_url': status.get('download_url', ''),
        'filename': status.get('filename', ''),
        'file_size_bytes': status.get('file_size_bytes', 0),
        'file_size_label': status.get('file_size_label', ''),
    })


# =============================================================================
# IMAGE ZIP EXPORT
# =============================================================================

@api_require_any_authenticated
@require_POST
@rate_limit(max_requests=10, window_seconds=60, key_prefix='export')
def api_export_images(request, table_id: int) -> JsonResponse:
    """
    Export images as ZIP files.
    
    POST /api/table/<table_id>/export/images/
    POST /api/table/<table_id>/cards/download-images/  (legacy URL in core)
    
    Body:
        {
            "card_ids": [1, 2, 3]
        }
        
    Returns:
        JSON with base64-encoded ZIP files:
        {
            "success": true,
            "zip_files": [
                {
                    "field_name": "PHOTO",
                    "filename": "TableName_PHOTO_20240101_120000.zip",
                    "data": "base64...",
                    "image_count": 10
                }
            ],
            "total_images": 10,
            "total_zips": 1
        }
    """
    # Check permission
    perm_error = _check_image_export_permission(request)
    if perm_error:
        return perm_error
    
    # Check client scope for admin_staff
    scope_error = _check_export_client_scope(request, table_id)
    if scope_error:
        return scope_error

    is_super_admin = PermissionService.is_super_admin(request.user)
    
    card_ids = _get_card_ids_from_request(request, table_id=table_id)
    if not card_ids:
        return JsonResponse({
            'success': False,
            'message': 'No cards selected for export'
        }, status=400)
    
    export_status = _get_status_from_request(request)

    # Concurrent export guard
    acquired, lock_key = _acquire_export_lock(request.user.id, table_id, 'images', request_user=request.user)
    if not acquired:
        return JsonResponse({'success': False, 'level': 'warning', 'message': 'Too many image exports running. Please wait.'}, status=429)
    try:
        service = ExportService(request.user)
        rename_options = _get_image_rename_options_from_request(request)
        mode_perm_error = _check_image_mode_permission(request, rename_options)
        if mode_perm_error:
            return mode_perm_error
        is_pdf_zip_mode = bool(rename_options and rename_options.get('output_format') == 'pdf_zip')
        allow_large_exports = is_super_admin

        result = service.export_images(
            table_id,
            card_ids,
            status=export_status,
            rename_options=rename_options,
            allow_large_base64=allow_large_exports,
        )

        # Fallback: when inline base64 payload is too large for non-super-admin,
        # generate disk-based ZIP(s) and return direct download URL(s).
        too_large_inline = (
            not is_super_admin
            and not is_pdf_zip_mode
            and not rename_options
            and not result.success
            and (
                'too large for inline' in str(result.message or '').lower()
                or 'inline zip limit' in str(result.message or '').lower()
            )
        )
        if too_large_inline:
            from core.services.background_worker import ensure_exports_directory
            from .zip import export_images_to_disk as _export_images_disk

            table = get_object_or_404(Table.objects.select_related('organisation'), id=table_id)
            cards_qs = service.get_scoped_cards(table, card_ids)
            output_dir = ensure_exports_directory()
            disk_result = _export_images_disk(
                table,
                cards_qs,
                output_dir=output_dir,
                status=export_status,
            )
            disk_payload = _disk_zip_result_to_payload(disk_result)
            if disk_payload.get('success'):
                logger.info(
                    "Export ZIP fallback-to-disk: user=%s table=%d cards=%d zips=%d",
                    request.user.id,
                    table_id,
                    len(card_ids),
                    disk_payload.get('total_zips', 0),
                )
                return JsonResponse(disk_payload)

        response_payload = zip_result_to_dict(result)
        if not response_payload.get('success'):
            _log_export_failure(request, 'images', response_payload.get('message', 'Image export failed'), table_id=table_id)
            return JsonResponse(response_payload)

        try:
            from core.services.activity_service import ActivityService
            ActivityService.log_cards_download(request, card_ids, 'Image Archive (ZIP)')
        except Exception:
            pass

        logger.info("Export ZIP: user=%s table=%d cards=%d", request.user.id, table_id, len(card_ids))
        return JsonResponse(response_payload)
    except Exception as e:
        logger.exception("Export ZIP failed: %s", e)
        _log_export_failure(request, 'images', str(e), table_id=table_id)
        return JsonResponse({'success': False, 'message': 'Export failed. Please try again or reduce the number of cards.'}, status=500)
    finally:
        _release_export_lock(lock_key)


# =============================================================================
# EXPORT PREVIEW
# =============================================================================

@api_require_any_authenticated
def api_export_preview(request, table_id: int) -> JsonResponse:
    """
    Get export preview/capabilities for a table.
    
    GET /api/table/<table_id>/export/preview/
    
    Returns:
        JSON with export capabilities:
        {
            "success": true,
            "table_name": "Student Cards",
            "card_count": 100,
            "text_field_count": 5,
            "image_field_count": 2,
            "available_formats": {
                "xlsx": true,
                "docx": true,
                "doc": true,
                "zip": true
            },
            "can_export": true
        }
    """
    # Check permission
    perm_error = _check_export_permission(request)
    if perm_error:
        return perm_error

    # Check client scope for admin_staff
    scope_error = _check_export_client_scope(request, table_id)
    if scope_error:
        return scope_error

    card_ids = None
    
    # Optional card_ids filter
    card_ids_str = request.GET.get('card_ids', '')
    if card_ids_str:
        try:
            card_ids = _normalize_positive_int_ids(json.loads(card_ids_str))
        except (json.JSONDecodeError, ValueError):
            card_ids = _normalize_positive_int_ids(card_ids_str.split(','))
    
    service = ExportService(request.user)
    result = service.get_export_preview(table_id, card_ids)
    
    return JsonResponse(result)


# =============================================================================
# DOWNLOAD ALL (Bulk Export by Status)
# =============================================================================

# Status lists to export
_DOWNLOAD_ALL_STATUSES = {
    'pending': 'Pending',
    'verified': 'Verified',
    'approved': 'Approved',
    'download': 'Download',
    'pool': 'Pool',
}


@api_require_any_authenticated
@require_POST
@rate_limit(max_requests=3, window_seconds=60, key_prefix='export_all')
def api_download_all_cards(request, table_id: int) -> JsonResponse:
    """
    Download all ID cards for a table, grouped by status list.
    
    For each status (Pending/Verified/Approved/Download/Pool) that has cards,
    generates one XLSX file and one or more ZIP files (one per image field).
    
    Memory-efficient implementation:
    - Writes individual XLSX/ZIP files to a temp directory on disk
    - Streams them into a single combined ZIP file on disk
    - Returns a download URL for the combined ZIP (no base64 in RAM)
    - Temp files auto-cleaned after 1 hour by BackgroundExportManager
    
    Not available to client/client_staff users.
    
    POST /api/table/<table_id>/cards/download-all/
    
    Returns JSON with a download URL (new streaming mode) or base64 files (legacy small exports):
    {
        "success": true,
        "download_url": "/media/temp/exports/abc123_download_all.zip",
        "filename": "Client_Table_AllCards.zip",
        "total_files": 3,
        "total_cards": 500
    }
    """
    
    # Block client/client_staff from download-all (contains approved/download data)
    if request.user.is_authenticated and PermissionService.is_client_role(request.user):
        return JsonResponse({
            'success': False,
            'message': 'This feature is not available for your account'
        }, status=403)
    
    # Check permission
    perm_error = _check_export_permission(request)
    if perm_error:
        return perm_error
    
    # Check client scope for admin_staff
    scope_error = _check_export_client_scope(request, table_id)
    if scope_error:
        return scope_error
    
    try:
        table = get_object_or_404(Table.objects.select_related('organisation'), id=table_id)
    except Exception:
        return JsonResponse({'success': False, 'message': 'Table not found'}, status=404)
    
    # Concurrent export guard — download-all is heavy, keep max_concurrent=1
    acquired, lock_key = _acquire_export_lock(
        request.user.id,
        table_id,
        'download_all',
        max_concurrent=1,
        request_user=request.user,
    )
    if not acquired:
        return JsonResponse({'success': False, 'level': 'warning', 'message': 'A bulk download is already in progress. Please wait.'}, status=429)
    try:
        import uuid as _uuid
        from core.services.background_worker import ensure_exports_directory
        EXPORT_TEMP_DIR = ensure_exports_directory()
        
        service = ExportService(request.user)
        excel_exporter = ExcelExporter()
        zip_exporter = ZipExporter()
        
        # Get client name for filenames
        client_name = ''
        if getattr(table, 'organisation', None):
            client_name = table.organisation.name
        
        from .utils import clean_filename
        clean_client = clean_filename(client_name) if client_name else ''
        clean_table = clean_filename(table.name)
        
        total_cards_processed = 0
        all_downloaded_card_ids = []
        file_entries = []  # list of (filename, disk_path) for combined ZIP
        temp_files = []  # track for cleanup on error
        
        task_id = _uuid.uuid4().hex[:12]
        
        for status_key, status_label in _DOWNLOAD_ALL_STATUSES.items():
            cards_qs = service.get_scoped_cards(table).filter(status=status_key)
            card_count = cards_qs.count()
            if card_count == 0:
                continue

            all_downloaded_card_ids.extend(list(cards_qs.values_list('id', flat=True)))
            cards = cards_qs
            total_cards_processed += card_count
            
            if clean_client:
                base_name = f"{clean_client}_{clean_table}_{status_label}"
            else:
                base_name = f"{clean_table}_{status_label}"
            
            # Write XLSX to disk
            try:
                xlsx_result = excel_exporter.export_cards(table, cards, status=status_key)
                if xlsx_result.success and xlsx_result.response:
                    xlsx_filename = f"{base_name}.xlsx"
                    xlsx_path = os.path.join(EXPORT_TEMP_DIR, f"{task_id}_{xlsx_filename}")
                    written = _write_http_response_to_file(xlsx_result.response, xlsx_path)
                    if written > 0:
                        file_entries.append((xlsx_filename, xlsx_path))
                        temp_files.append(xlsx_path)
                    del xlsx_result
            except Exception as e:
                logger.error("XLSX export failed for status %s: %s", status_key, e)
            
            # Write ZIP(s) for image fields directly to disk (memory-safe, no base64)
            try:
                from .zip import export_images_to_disk as _export_images_disk
                disk_result = _export_images_disk(table, cards, output_dir=EXPORT_TEMP_DIR, status=status_label)
                if disk_result.success and disk_result.zip_files:
                    for dzi in disk_result.zip_files:
                        file_entries.append((dzi.filename, dzi.path))
                        temp_files.append(dzi.path)
                del disk_result
            except Exception as e:
                logger.error("ZIP export failed for status %s: %s", status_key, e)
        
        if not file_entries:
            # Cleanup any temp files
            for tp in temp_files:
                try:
                    os.remove(tp)
                except OSError:
                    pass
            _log_export_failure(request, 'download_all', 'No cards found in any list to export', table_id=table_id)
            return JsonResponse({
                'success': False,
                'message': 'No cards found in any list to export'
            }, status=400)
        
        # Combine all files into a single ZIP on disk (streaming, constant RAM)
        if clean_client:
            combined_name = f"{clean_client}_{clean_table}_AllCards.zip"
        else:
            combined_name = f"{clean_table}_AllCards.zip"
        
        combined_path = os.path.join(EXPORT_TEMP_DIR, f"{task_id}_{combined_name}")
        
        import zipfile as _zf
        # Most members are already compressed (.xlsx/.zip), so storing avoids
        # expensive recompression with negligible size impact.
        with _zf.ZipFile(combined_path, 'w', _zf.ZIP_STORED) as combined_zip:
            for entry_name, entry_path in file_entries:
                combined_zip.write(entry_path, arcname=entry_name)
        
        # Clean up individual temp files (combined ZIP has their data now)
        for tp in temp_files:
            try:
                os.remove(tp)
            except OSError:
                pass
        
        # Build download URL
        rel_path = os.path.relpath(combined_path, settings.MEDIA_ROOT).replace('\\', '/')
        download_url = f'{settings.MEDIA_URL}{rel_path}'
        
        try:
            from core.services.activity_service import ActivityService
            ActivityService.log_cards_download(request, all_downloaded_card_ids, 'Complete Archive (ZIP)')
        except Exception:
            pass

        logger.info("Export DOWNLOAD-ALL: user=%s table=%d files=%d cards=%d url=%s", 
                    request.user.id, table_id, len(file_entries), total_cards_processed, download_url)
        
        return JsonResponse({
            'success': True,
            'download_url': download_url,
            'filename': combined_name,
            'total_files': len(file_entries),
            'total_cards': total_cards_processed,
            'note': None,
        })
    except Exception as e:
        logger.exception("Export DOWNLOAD-ALL failed: %s", e)
        _log_export_failure(request, 'download_all', str(e), table_id=table_id)
        return JsonResponse({'success': False, 'message': 'Export failed. Please try again or reduce the number of cards.'}, status=500)
    finally:
        _release_export_lock(lock_key)
