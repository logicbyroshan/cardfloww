"""
Client Views — API endpoints.

JSON API views for the client panel: dashboard data, staff CRUD,
card listing/status changes, image uploads, and group/class helpers.
"""
import json
import logging

from django.core.cache import cache
from django.db.models import Count, Exists, OuterRef, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from accounts.rate_limit import rate_limit
from assistants.models import Assistant
from assistants.services import AssistantService
from .services_staff import OrganisationStaffService

from core.models import ClientMessage, NotificationRead
from core.services.permission_service import PermissionService
from core.services.activity_service import ActivityService
from core.services.cache_version_service import CacheVersionService
from core.services.session_revalidation import get_user_revalidation_marker

from .views_decorators import require_client_user, require_client_admin, require_client_staff_manager
from .services import (
    OrganisationAccessService,
    OrganisationDashboardService,
    OrganisationCardService,
    OrganisationImageService,
)


logger = logging.getLogger(__name__)


def _normalize_positive_int_ids(values, max_items: int = 500):
    """Normalize mixed payload IDs to unique positive integers with a cap."""
    if not isinstance(values, list):
        return []

    out = []
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
        if len(out) >= max_items:
            break
    return out


def _normalize_assignment_scopes(values, max_items: int = 500):
    """Keep assignment scopes as a bounded list of dicts."""
    if not isinstance(values, list):
        return []

    out = []
    for item in values:
        if not isinstance(item, dict):
            continue
        out.append(item)
        if len(out) >= max_items:
            break
    return out


def _normalize_staff_assignment_payload(data):
    """Normalize and cap assignment-related payload fields for stability."""
    if not isinstance(data, dict):
        return data

    if 'assigned_groups' in data:
        data['assigned_groups'] = _normalize_positive_int_ids(data.get('assigned_groups'), max_items=500)

    if 'assignment_scopes' in data:
        data['assignment_scopes'] = _normalize_assignment_scopes(data.get('assignment_scopes'), max_items=500)

    return data


def _result_error_status(message: str, fallback: int = 400) -> int:
    """Map service error messages to HTTP status without case-sensitive checks."""
    text = str(message or '').strip().lower()
    if 'permission' in text or 'access denied' in text or 'access' in text:
        return 403
    return fallback


def _client_staff_assignment_snapshot(staff_obj):
    """Return normalized assignment state used for timeline diff logging."""
    if not staff_obj:
        return {
            'client_ids': [],
            'group_ids': [],
            'table_ids': [],
            'classes': [],
            'sections': [],
            'branches': [],
            'scope_count': 0,
        }

    table_ids = []
    for value in (staff_obj.assigned_table_ids or []):
        try:
            num = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if num > 0:
            table_ids.append(num)

    return {
        'client_ids': [int(staff_obj.client_id)] if getattr(staff_obj, 'client_id', None) else [],
        'group_ids': list(staff_obj.assigned_groups.values_list('id', flat=True)),
        'table_ids': table_ids,
        'classes': list(staff_obj.allowed_classes or []),
        'sections': list(staff_obj.allowed_sections or []),
        'branches': list(staff_obj.allowed_branches or []),
        'scope_count': len(staff_obj.assignment_scopes or []),
    }


# =============================================================================
# API VIEWS - Dashboard
# =============================================================================

@require_client_user
@require_http_methods(["GET"])
def api_dashboard_data(request):
    """
    API: Get dashboard summary data.
    """
    result = OrganisationDashboardService.get_dashboard_data(request.user)
    
    if result.success:
        return JsonResponse({
            'success': True,
            'data': result.data
        })
    
    return JsonResponse({
        'success': False,
        'message': result.message
    }, status=400)


@require_client_user
@require_http_methods(["GET"])
def api_reprint_history(request):
    """
    API: Return reprint history for the client dashboard.

    This wraps OrganisationDashboardService.get_reprint_history so templates
    and client-side code can fetch a single consolidated endpoint.
    """
    if not PermissionService.has_permission(request.user, 'perm_reprint_request_list'):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

    try:
        result = OrganisationDashboardService.get_reprint_history(request.user)
        if result.success:
            return JsonResponse({'success': True, 'data': result.data})
        return JsonResponse({'success': False, 'message': result.message}, status=400)
    except Exception as e:
        logger.exception('api_reprint_history failed: %s', e)
        return JsonResponse({'success': False, 'message': 'An unexpected error occurred.'}, status=500)





@require_client_user
@require_http_methods(["GET"])
def api_groups_list(request):
    """
    API: Get list of groups with card counts.
    """
    # Check permission (matches the page view gate)
    if not PermissionService.has_permission(request.user, 'perm_idcard_setting_list'):
        return JsonResponse({
            'success': False,
            'message': 'Permission denied'
        }, status=403)

    result = OrganisationDashboardService.get_groups_with_counts(request.user)

    if result.success:
        return JsonResponse({
            'success': True,
            'data': {'groups': result.data.get('groups', [])}
        })
    
    return JsonResponse({
        'success': False,
        'error': result.message
    }, status=400)


@require_client_user
@require_http_methods(["GET"])
def api_messages_drawer(request):
    """API: Return client message history payload for the right-side drawer."""
    user = request.user
    client = OrganisationAccessService.get_organisation_for_user(user)
    if not client:
        return JsonResponse({'success': False, 'message': 'Client not found.'}, status=403)

    try:
        limit = max(10, min(int(request.GET.get('limit', 40)), 100))
    except (TypeError, ValueError):
        limit = 40

    marker = str(get_user_revalidation_marker(getattr(user, 'pk', None)) or '')
    user_cache_version = CacheVersionService.get('client_messages_drawer_user', f'user:{user.id}')
    client_cache_version = CacheVersionService.get('client_messages_drawer_client', f'client:{client.id}')
    cache_key = (
        f'client:messages_drawer:v3:{user.id}:{client.id}:{limit}:{marker}:'
        f'{user_cache_version}:{client_cache_version}'
    )
    cached_payload = cache.get(cache_key)
    if cached_payload is not None:
        return JsonResponse(cached_payload)

    now = timezone.now()
    base_qs = (
        ClientMessage.objects
        .filter(
            client_id=client.id,
            notification__is_active=True,
            notification__target='selected',
            notification__target_users=user,
        )
        .filter(Q(visibility='permanent') | Q(expires_at__gt=now))
        .annotate(
            is_read=Exists(
                NotificationRead.objects.filter(
                    notification_id=OuterRef('notification_id'),
                    user=user,
                )
            )
        )
        .order_by('-created_at')
    )

    counts = base_qs.aggregate(
        total_count=Count('id'),
        unread_count=Count('id', filter=Q(is_read=False)),
    )
    total_count = int(counts.get('total_count') or 0)
    unread_count = int(counts.get('unread_count') or 0)
    rows = list(
        base_qs
        .select_related('sent_by')
        .only(
            'id',
            'notification_id',
            'message',
            'scope',
            'visibility',
            'expires_at',
            'created_at',
            'sent_by__first_name',
            'sent_by__last_name',
            'sent_by__username',
        )[:limit]
    )
    client_name = client.name

    items = []
    for row in rows:
        sender_name = 'Admin'
        if row.sent_by:
            sender_name = row.sent_by.get_full_name() or row.sent_by.username
        items.append({
            'id': row.id,
            'notification_id': row.notification_id,
            'message': row.message,
            'scope': row.scope,
            'scope_display': row.get_scope_display(),
            'visibility': row.visibility,
            'expires_at': row.expires_at.isoformat() if row.expires_at else None,
            'created_at': row.created_at.isoformat(),
            'sent_by_name': sender_name,
            'client_name': client_name,
            'is_read': bool(getattr(row, 'is_read', False)),
        })

    payload = {
        'success': True,
        'items': items,
        'total_count': total_count,
        'unread_count': unread_count,
    }
    cache.set(cache_key, payload, 90)
    return JsonResponse(payload)


# =============================================================================
# API VIEWS - Staff Management


@require_client_staff_manager
@require_http_methods(["GET", "POST"])
def api_staff_list_create(request):
    """
    API: List client staff (GET) or Create new staff (POST).
    """
    if request.method == 'GET':
        result = OrganisationStaffService.list_staff(request.user)
        if result.success:
            return JsonResponse({
                'success': True,
                'data': {'staff': result.data.get('staff', [])}
            })

        return JsonResponse({
            'success': False,
            'error': result.message
        }, status=400 if 'Permission' not in result.message else 403)

    # POST - Create new staff
    content_type = request.content_type or ''
    if 'multipart/form-data' in content_type:
        data = request.POST.dict()
        # Parse JSON fields sent as strings
        if 'assigned_groups' in data:
            try:
                data['assigned_groups'] = json.loads(data['assigned_groups'])
            except (json.JSONDecodeError, TypeError):
                data['assigned_groups'] = []
        if 'assignment_scopes' in data:
            try:
                data['assignment_scopes'] = json.loads(data['assignment_scopes'])
            except (json.JSONDecodeError, TypeError):
                data['assignment_scopes'] = []
        # Parse boolean strings
        for key in list(data.keys()):
            if data[key] in ('true', 'True'):
                data[key] = True
            elif data[key] in ('false', 'False'):
                data[key] = False
    else:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data'
            }, status=400)
    
    data = _normalize_staff_assignment_payload(data)
    result = OrganisationStaffService.create_staff(request.user, data)
    
    if result.success:
        staff_id = (result.data or {}).get('staff_id')
        if staff_id:
            raw_id = staff_id - 200000 if staff_id >= 200000 else staff_id
            try:
                staff = (
                    Assistant.objects
                    .select_related('user')
                    .prefetch_related('assigned_groups')
                    .filter(id=raw_id)
                    .first()
                )
                if staff:
                    ActivityService.log_staff_create(request, staff)
                    ActivityService.log_staff_assignment_change(
                        request,
                        staff,
                        before_snapshot={},
                        after_snapshot=_client_staff_assignment_snapshot(staff),
                        reason='created',
                    )
            except Exception:
                logger.exception('Failed to log staff create activity for staff_id=%s', staff_id)
        
        return JsonResponse({
            'success': True,
            'message': result.message,
            'data': {'staff_id': staff_id}
        })

    status_code = _result_error_status(result.message, fallback=400)
    return JsonResponse({
        'success': False,
        'error': result.message
    }, status=status_code)


@require_client_staff_manager
@require_http_methods(["GET", "PUT", "DELETE"])
@rate_limit(max_requests=90, window_seconds=60, key_prefix='client_staff_detail')
def api_staff_detail(request, staff_id):
    """
    API: Get, Update, or Delete a specific staff member.
    """
    raw_id = staff_id % 100000 if staff_id >= 100000 else staff_id
    if request.method == 'GET':
        result = OrganisationStaffService.get_staff_detail(request.user, staff_id)
        
        if result.success:
            return JsonResponse({
                'success': True,
                'data': result.data
            })
        
        return JsonResponse({
            'success': False,
            'error': result.message
        }, status=404 if 'found' in result.message.lower() else 403)
    
    if request.method == 'PUT':
        before_staff = (
            Assistant.objects
            .select_related('user')
            .prefetch_related('assigned_groups')
            .filter(id=raw_id)
            .first()
        )
        if not before_staff:
            return JsonResponse({
                'success': False,
                'error': 'Assistant not found'
            }, status=404)
        before_assignment_snapshot = _client_staff_assignment_snapshot(before_staff)

        content_type = request.content_type or ''
        if 'multipart/form-data' in content_type:
            # Django doesn't parse PUT multipart by default
            from django.http.multipartparser import MultiPartParser
            try:
                parser = MultiPartParser(request.META, request, request.upload_handlers)
                post_data, files = parser.parse()
            except Exception:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid multipart form data'
                }, status=400)
            data = post_data.dict()
            # Parse JSON fields sent as strings
            if 'assigned_groups' in data:
                try:
                    data['assigned_groups'] = json.loads(data['assigned_groups'])
                except (json.JSONDecodeError, TypeError):
                    data['assigned_groups'] = []
            if 'assignment_scopes' in data:
                try:
                    data['assignment_scopes'] = json.loads(data['assignment_scopes'])
                except (json.JSONDecodeError, TypeError):
                    data['assignment_scopes'] = []
            # Parse boolean strings
            for key in list(data.keys()):
                if data[key] in ('true', 'True'):
                    data[key] = True
                elif data[key] in ('false', 'False'):
                    data[key] = False
        else:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid JSON data'
                }, status=400)
        # Debug: log incoming assignment_scopes payload before normalization
        try:
            logger.info('Incoming staff update payload for staff_id=%s: %s', raw_id, json.dumps({k: v for k, v in data.items() if k in ('assignment_scopes', 'assigned_groups')}, ensure_ascii=False))
        except Exception:
            logger.exception('Failed to log incoming staff update payload for staff_id=%s', raw_id)
        data = _normalize_staff_assignment_payload(data)
        
        result = OrganisationStaffService.update_staff(request.user, staff_id, data)
        
        if result.success:
            try:
                staff = (
                    Assistant.objects
                    .select_related('user')
                    .prefetch_related('assigned_groups')
                    .filter(id=raw_id)
                    .first()
                )
                if staff:
                    ActivityService.log_staff_update(request, staff)
                    ActivityService.log_staff_assignment_change(
                        request,
                        staff,
                        before_snapshot=before_assignment_snapshot,
                        after_snapshot=_client_staff_assignment_snapshot(staff),
                        reason='updated',
                    )
            except Exception:
                logger.exception('Failed to log staff update activity for staff_id=%s', raw_id)
            return JsonResponse({
                'success': True,
                'message': result.message
            })
        
        status_code = _result_error_status(result.message, fallback=400)
        return JsonResponse({
            'success': False,
            'error': result.message
        }, status=status_code)
    
    # DELETE
    staff_name = f'Staff #{raw_id}'
    last_active_str = 'never active'
    try:
        existing_staff = Assistant.objects.select_related('user').filter(id=raw_id).first()
        if existing_staff:
            staff_name = existing_staff.user.get_full_name() or existing_staff.user.username
            last_active_str = ActivityService._format_last_active(existing_staff.user)
    except Exception:
        logger.exception('Failed to resolve staff name before delete for staff_id=%s', raw_id)

    result = OrganisationStaffService.delete_staff(request.user, staff_id)
    
    if result.success:
        try:
            ActivityService.log_staff_delete(request, staff_name, last_active_str, raw_id, user_type='Assistant')
        except Exception:
            logger.exception('Failed to log staff delete activity for staff_id=%s', raw_id)
        return JsonResponse({
            'success': True,
            'message': result.message
        })
    
    status_code = _result_error_status(result.message, fallback=400)
    return JsonResponse({
        'success': False,
        'error': result.message
    }, status=status_code)


@require_client_staff_manager
@require_http_methods(["POST"])
def api_staff_toggle_status(request, staff_id):
    """
    API: Toggle staff member active/inactive status.
    """
    raw_id = staff_id % 100000 if staff_id >= 100000 else staff_id
    try:
        result = OrganisationStaffService.toggle_staff_status(request.user, staff_id)
        
        if result.success:
            is_active = result.data.get('is_active', False)
            try:
                staff = Assistant.objects.select_related('user').filter(id=raw_id).first()
                if staff:
                    ActivityService.log_staff_status(request, staff, is_active)
                else:
                    ActivityService.log(
                        'staff_status',
                        f'Staff "#{raw_id}" marked as {"active" if is_active else "inactive"}',
                        request=request,
                        target_model='Staff',
                        target_id=raw_id,
                        target_name=f'Staff #{raw_id}',
                    )
            except Exception:
                logger.exception('Failed to log staff status activity for staff_id=%s', raw_id)
            return JsonResponse({
                'success': True,
                'message': result.message,
                'status': 'active' if is_active else 'inactive',
                'status_display': 'Active' if is_active else 'Inactive',
            })
        
        status_code = _result_error_status(result.message, fallback=400)
        return JsonResponse({
            'success': False,
            'message': result.message
        }, status=status_code)
    except Exception:
        logger.exception('Staff toggle status error')
        return JsonResponse({'success': False, 'message': 'An error occurred. Please try again.'}, status=500)


@require_client_staff_manager
@require_http_methods(["POST"])
@rate_limit(max_requests=5, window_seconds=60, key_prefix='client_staff_temp_pw')
def api_staff_set_temp_password(request, staff_id):
    """API: Set temporary password for a client-owned staff member."""
    raw_id = staff_id % 100000 if staff_id >= 100000 else staff_id
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)

    new_password = (data.get('password') or '').strip()
    if not new_password:
        return JsonResponse({'success': False, 'message': 'Password is required'}, status=400)
    if len(new_password) < 8:
        return JsonResponse({'success': False, 'message': 'Password must be at least 8 characters'}, status=400)

    from django.contrib.auth.password_validation import validate_password
    try:
        validate_password(new_password)
    except Exception as validation_error:
        return JsonResponse({'success': False, 'message': '; '.join(validation_error.messages)}, status=400)

    result = OrganisationStaffService.set_temp_password(
        request.user,
        staff_id,
        new_password,
        request=request,
    )

    if result.success:
        try:
            staff = Assistant.objects.select_related('user').filter(id=raw_id).first()
            staff_name = f'Staff #{raw_id}'
            if staff:
                staff_name = staff.user.get_full_name() or staff.user.username
            ActivityService.log(
                'staff_password_reset',
                f'Temporary password reset for client staff "{staff_name}"',
                request=request,
                target_model='Staff',
                target_id=raw_id,
                target_name=staff_name,
            )
        except Exception:
            logger.exception('Failed to log staff temp-password activity for staff_id=%s', raw_id)
        return JsonResponse(result.to_response_dict(), status=200)

    msg = (result.message or '').lower()
    if 'permission' in msg:
        status_code = 403
    elif 'not found' in msg:
        status_code = 404
    else:
        status_code = 400
    return JsonResponse(result.to_response_dict(), status=status_code)


@require_client_staff_manager
@require_http_methods(["GET"])
def api_client_groups_list(request):
    """
    API: Get list of assignable containers for current client staff.

    Normal behavior: return ID card groups.
    Fallback behavior: when a client effectively operates under a single
    default group with multiple tables, return table entries so the UI can
    present meaningful assignment choices.
    """
    from tables.models import Table  # local import: group listing
    from tables.models import Table
    
    user = request.user
    client = OrganisationAccessService.get_organisation_for_user(user)
    if not client:
        return JsonResponse({'success': False, 'message': 'Client not found'}, status=400)
    
    groups_qs = Table.objects.filter(organisation=client).order_by('name')
    group_count = groups_qs.count()
    for_auto_create = request.GET.get('for_auto_create') == 'true'

    if group_count <= 1 and not for_auto_create:
        tables_qs = Table.objects.filter(
            organisation=client,
            deleted_by_manager=False,
        ).order_by('name').values('id', 'name')
        groups_data = [
            {
                'id': t['id'],
                'name': t['name'],
                'group_id': t['id'],
                'source': 'table',
            }
            for t in tables_qs
        ]
    else:
        groups_data = [
            {
                'id': g.id,
                'name': g.name,
                'group_id': g.id,
                'source': 'group',
            }
            for g in groups_qs
        ]
    
    return JsonResponse({
        'success': True,
        'groups': groups_data
    })


@require_client_staff_manager
@require_http_methods(["GET"])
def api_class_section_options(request):
    """
    API: Get distinct class and section values from all cards of this client.
    Used in staff drawer for class/section filter assignment.
    """
    from tables.models import IDCard, Table

    user = request.user
    client = OrganisationAccessService.get_organisation_for_user(user)
    if not client:
        return JsonResponse({'success': False, 'message': 'Client not found'}, status=400)

    raw_group_ids = request.GET.get('group_ids', '').strip()
    id_source = (request.GET.get('id_source', '') or '').strip().lower()
    if id_source not in ('group', 'table'):
        id_source = 'auto'

    resolved_id_source = id_source
    if resolved_id_source == 'auto':
        group_count = Table.objects.filter(organisation=client).count()
        resolved_id_source = 'table' if group_count <= 1 else 'group'

    group_ids = []
    if raw_group_ids:
        try:
            group_ids = sorted({int(x) for x in raw_group_ids.split(',') if str(x).strip().isdigit()})
        except Exception:
            group_ids = []

    # Resolve effective tables.
    # Accepts either:
    # - group IDs (legacy behavior), or
    # - table IDs (client fallback assignment mode).
    tables_qs = Table.objects.filter(organisation=client, deleted_by_manager=False)

    if group_ids:
        valid_group_ids = set(
            Table.objects.filter(organisation=client, id__in=group_ids).values_list('id', flat=True)
        )
        valid_table_ids = set(
            Table.objects.filter(organisation=client, id__in=group_ids).values_list('id', flat=True)
        )

        if resolved_id_source == 'table':
            if valid_table_ids:
                tables_qs = tables_qs.filter(id__in=list(valid_table_ids))
            elif valid_group_ids:
                # Backward-compatible fallback for legacy group-id payloads.
                tables_qs = tables_qs.filter(id__in=list(valid_group_ids))
            else:
                tables_qs = tables_qs.none()
        elif resolved_id_source == 'group':
            if valid_group_ids:
                tables_qs = tables_qs.filter(id__in=list(valid_group_ids))
            elif valid_table_ids:
                # Graceful fallback for stale clients accidentally sending table IDs.
                tables_qs = tables_qs.filter(id__in=list(valid_table_ids))
            else:
                tables_qs = tables_qs.none()

    tables = list(tables_qs.values('id', 'fields'))

    classes = set()
    sections = set()
    branches = set()
    class_sections = {}
    class_counts = {}
    section_counts = {}
    class_section_counts = {}
    table_field_map = {}
    has_class_field = False
    has_section_field = False
    has_branch_field = False

    for table in tables:
        # Determine which field names are class/section/branch type
        class_field = None
        section_field = None
        branch_field = None
        for field in (table.get('fields') or []):
            ft = field.get('type', '').lower()
            fn = field.get('name', '')
            fn_lower = fn.lower()
            if ft == 'class' or fn.lower() == 'class':
                class_field = fn
            elif ft == 'section' or fn.lower() == 'section':
                section_field = fn
            elif (
                ft == 'branch'
                or fn_lower == 'branch'
                or fn_lower == 'stream'
                or fn_lower == 'course'
                or 'branch' in fn_lower
                or 'stream' in fn_lower
                or 'course' in fn_lower
            ):
                branch_field = fn

        if class_field:
            has_class_field = True
        if section_field:
            has_section_field = True
        if branch_field:
            has_branch_field = True

        if class_field or section_field or branch_field:
            table_field_map[table['id']] = (class_field, section_field, branch_field)

    table_ids = list(table_field_map.keys())
    if table_ids:
        cards = IDCard.objects.filter(table_id__in=table_ids).values_list('table_id', 'field_data').iterator(chunk_size=1000)
    else:
        cards = []

    for table_id, fd in cards:
        if not fd:
            continue

        class_field, section_field, branch_field = table_field_map.get(table_id, (None, None, None))
        class_val = ''
        section_val = ''
        if class_field:
            val = fd.get(class_field, '') or fd.get(class_field.upper(), '') or fd.get(class_field.lower(), '')
            if val:
                class_val = str(val).strip()
                if class_val:
                    classes.add(class_val)
        if section_field:
            val = fd.get(section_field, '') or fd.get(section_field.upper(), '') or fd.get(section_field.lower(), '')
            if val:
                section_val = str(val).strip()
                if section_val:
                    sections.add(section_val)
        if branch_field:
            val = fd.get(branch_field, '') or fd.get(branch_field.upper(), '') or fd.get(branch_field.lower(), '')
            if val:
                branch_val = str(val).strip()
                if branch_val:
                    branches.add(branch_val)

        # Build class -> sections mapping from actual card rows.
        if class_val:
            if class_val not in class_sections:
                class_sections[class_val] = set()
            if section_val:
                class_sections[class_val].add(section_val)

            class_counts[class_val] = class_counts.get(class_val, 0) + 1

        if section_val:
            section_counts[section_val] = section_counts.get(section_val, 0) + 1

        if class_val and section_val:
            class_section_counts.setdefault(class_val, {})
            class_section_counts[class_val][section_val] = (
                class_section_counts[class_val].get(section_val, 0) + 1
            )

    # ── Normalize class values ──
    from core.utils.field_utils import normalize_class_value, CLASS_ORDER, CLASS_ORDER_UNKNOWN
    from collections import defaultdict

    class_groups = defaultdict(list)
    for raw_cls, count in class_counts.items():
        canonical = normalize_class_value(raw_cls)
        if canonical:
            class_groups[canonical].append((raw_cls, count))

    raw_class_to_best = {}
    best_classes = set()
    best_class_counts = {}
    best_class_sections = {}
    best_class_section_counts = {}

    for canonical, variants in class_groups.items():
        best_raw = max(variants, key=lambda x: x[1])[0]
        best_classes.add(best_raw)
        for raw_cls, _ in variants:
            raw_class_to_best[raw_cls] = best_raw

    for raw_cls, count in class_counts.items():
        best_cls = raw_class_to_best.get(raw_cls, raw_cls)
        best_class_counts[best_cls] = best_class_counts.get(best_cls, 0) + count

    for raw_cls, secs in class_sections.items():
        best_cls = raw_class_to_best.get(raw_cls, raw_cls)
        if best_cls not in best_class_sections:
            best_class_sections[best_cls] = set()
        best_class_sections[best_cls].update(secs)

    for raw_cls, sec_cnts in class_section_counts.items():
        best_cls = raw_class_to_best.get(raw_cls, raw_cls)
        if best_cls not in best_class_section_counts:
            best_class_section_counts[best_cls] = {}
        for sec, count in sec_cnts.items():
            best_class_section_counts[best_cls][sec] = (
                best_class_section_counts[best_cls].get(sec, 0) + count
            )

    classes = best_classes
    class_counts = best_class_counts
    class_sections = best_class_sections
    class_section_counts = best_class_section_counts

    payload = {
        'success': True,
        'resolved_id_source': resolved_id_source,
        'classes': sorted(
            classes,
            key=lambda x: (CLASS_ORDER.get(normalize_class_value(x), CLASS_ORDER_UNKNOWN), normalize_class_value(x))
        ),
        'sections': sorted(sections),
        'branches': sorted(branches),
        'has_class_field': has_class_field,
        'has_section_field': has_section_field,
        'has_branch_field': has_branch_field,
        'class_sections': {
            cls_name: sorted(sec_values)
            for cls_name, sec_values in sorted(class_sections.items(), key=lambda x: (CLASS_ORDER.get(normalize_class_value(x[0]), CLASS_ORDER_UNKNOWN), normalize_class_value(x[0])))
        },
        'class_counts': {
            cls_name: int(count)
            for cls_name, count in sorted(class_counts.items(), key=lambda x: (CLASS_ORDER.get(normalize_class_value(x[0]), CLASS_ORDER_UNKNOWN), normalize_class_value(x[0])))
        },
        'section_counts': {
            sec_name: int(count)
            for sec_name, count in sorted(section_counts.items(), key=lambda x: x[0])
        },
        'class_section_counts': {
            cls_name: {
                sec_name: int(sec_count)
                for sec_name, sec_count in sorted(sec_counts.items(), key=lambda x: x[0])
            }
            for cls_name, sec_counts in sorted(class_section_counts.items(), key=lambda x: (CLASS_ORDER.get(normalize_class_value(x[0]), CLASS_ORDER_UNKNOWN), normalize_class_value(x[0])))
        },
    }
    return JsonResponse(payload)


# =============================================================================
# API VIEWS - Card Data
# =============================================================================

@require_client_user
@require_http_methods(["GET"])
def api_tables_list(request):
    """
    API: Get list of tables with card counts.
    """
    # For client owner, require perm_idcard_setting_list.
    # For client staff, require perm_idcard_setting_list or any card list perm.
    if PermissionService.is_client(request.user) and not PermissionService.is_client_staff(request.user):
        if not PermissionService.has(request.user, 'perm_idcard_setting_list'):
            return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    else:
        has_access = (
            PermissionService.has(request.user, 'perm_idcard_setting_list') or
            PermissionService.has(request.user, 'perm_idcard_pending_list') or
            PermissionService.has(request.user, 'perm_idcard_verified_list') or
            PermissionService.has(request.user, 'perm_idcard_approved_list') or
            PermissionService.has(request.user, 'perm_idcard_download_list') or
            PermissionService.has(request.user, 'perm_idcard_pool_list')
        )
        if not has_access:
            return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

    result = OrganisationCardService.get_tables_for_client(request.user)
    
    if result.success:
        return JsonResponse({
            'success': True,
            'tables': result.data.get('tables', [])
        })
    
    return JsonResponse({
        'success': False,
        'message': result.message
    }, status=400)


@require_client_user
@require_http_methods(["GET"])
def api_cards_list(request, table_id):
    """
    API: Get cards for a specific table.
    """
    status_filter = (request.GET.get('status', '') or '').strip().lower()
    search = (request.GET.get('search', '') or '').strip()[:120]
    class_filter = (request.GET.get('class', '') or '').strip()
    section_filter = (request.GET.get('section', '') or '').strip()
    course_filter = (request.GET.get('course', '') or '').strip()
    branch_filter = (request.GET.get('branch', '') or '').strip()
    sort_order = (request.GET.get('sort', '') or 'sr-asc').strip().lower()
    photo_filter = (request.GET.get('photo', '') or request.GET.get('image_condition', '') or '').strip().lower()
    image_column = (request.GET.get('image_column', '') or '').strip()
    from_date = (request.GET.get('from', '') or '').strip()
    to_date = (request.GET.get('to', '') or '').strip()
    try:
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
    except (ValueError, TypeError):
        page, per_page = 1, 20
    page = max(page, 1)
    per_page = max(1, min(per_page, 200))
    offset = (page - 1) * per_page
    
    result = OrganisationCardService.get_cards(
        request.user,
        table_id,
        status_filter if status_filter else None,
        offset,
        per_page,
        search if search else None,
        from_date=from_date or None,
        to_date=to_date or None,
        class_filter=class_filter or None,
        section_filter=section_filter or None,
        course_filter=course_filter or None,
        branch_filter=branch_filter or None,
        photo_filter=photo_filter or None,
        sort_order=sort_order or 'sr-asc',
        image_column=image_column or None,
    )
    
    if result.success:
        # Calculate pagination info
        total = result.data.get('total', 0)
        total_pages = (total + per_page - 1) // per_page if total else 1
        
        return JsonResponse({
            'success': True,
            'data': {
                'cards': result.data.get('cards', []),
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'total_pages': total_pages
                }
            }
        })
    
    status_code = _result_error_status(result.message, fallback=400)
    return JsonResponse({
        'success': False,
        'error': result.message
    }, status=status_code)


@require_client_user
@require_http_methods(["GET"])
@rate_limit(max_requests=90, window_seconds=60, key_prefix='client_card_detail')
def api_card_detail(request, card_id):
    """
    API: Get details of a specific card.
    """
    result = OrganisationCardService.get_card_detail(request.user, card_id)
    
    if result.success:
        return JsonResponse({
            'success': True,
            'data': result.data
        })
    
    status_code = _result_error_status(result.message, fallback=404)
    return JsonResponse({
        'success': False,
        'error': result.message
    }, status=status_code)


@require_client_user
@require_http_methods(["POST"])
def api_card_change_status(request, card_id):
    """
    API: Change a card's status.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)
    
    new_status = data.get('status', '')
    
    result = OrganisationCardService.change_card_status(request.user, card_id, new_status, request=request)
    
    if result.success:
        return JsonResponse({
            'success': True,
            'message': result.message,
            **result.data
        })
    
    status_code = _result_error_status(result.message, fallback=400)
    # 409 Conflict indicates a scope mismatch (requires class change)
    if 'outside your assigned' in result.message:
        status_code = 409
    
    return JsonResponse({
        'success': False,
        'message': result.message,
        **(result.data or {})
    }, status=status_code)


@require_client_user
@require_http_methods(["POST"])
def api_cards_bulk_status(request, table_id):
    """
    API: Change status for multiple cards.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)
    
    card_ids = _normalize_positive_int_ids(data.get('card_ids', []), max_items=500)
    new_status = data.get('status', '')

    if not card_ids:
        return JsonResponse({
            'success': False,
            'message': 'No valid card IDs provided'
        }, status=400)
    
    result = OrganisationCardService.bulk_change_status(
        request.user,
        table_id,
        card_ids,
        new_status,
        request=request,
    )
    
    if result.success:
        return JsonResponse({
            'success': True,
            'message': result.message,
            **result.data
        })
    
    status_code = _result_error_status(result.message, fallback=400)
    # 409 Conflict indicates a scope mismatch (requires class change)
    if 'outside your assigned' in result.message:
        status_code = 409
        
    return JsonResponse({
        'success': False,
        'message': result.message,
        **(result.data or {})
    }, status=status_code)


# =============================================================================
# API VIEWS - Image Upload
# =============================================================================

@require_client_user
@require_http_methods(["POST"])
def api_upload_images(request, table_id):
    """
    API: Upload images and link to cards.
    """
    images = request.FILES.getlist('images')
    
    if not images:
        return JsonResponse({
            'success': False,
            'message': 'No images provided'
        }, status=400)
    
    try:
        result = OrganisationImageService.upload_images(request.user, table_id, images)
        
        if result.success:
            return JsonResponse({
                'success': True,
                'message': result.message,
                **result.data
            })
        
        status_code = _result_error_status(result.message, fallback=400)
        return JsonResponse({
            'success': False,
            'message': result.message
        }, status=status_code)
    except Exception:
        import logging as _logging
        _logging.getLogger(__name__).exception("Image upload error")
        return JsonResponse({'success': False, 'message': 'An error occurred. Please try again.'}, status=500)


@require_client_admin
@require_http_methods(["POST"])
def client_api_create_table_from_xlsx(request):
    """
    Client wrapper for the Create-from-XLSX API.
    Auto-detects the client's default group, then delegates to the core view.
    """
    user = request.user
    client = _get_client_for_request(user)
    if not client:
        return JsonResponse({'success': False, 'message': 'Client not found.'}, status=403)

    if not PermissionService.has_permission(user, 'perm_idcard_setting_add'):
        return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

    from core.services.idcard_service import IDCardService
    group = IDCardService.ensure_default_group(client)
    from core.views.idcard_api import api_create_table_from_xlsx
    return api_create_table_from_xlsx(request, group.id)
