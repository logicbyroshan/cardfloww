import json
import logging
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils.timezone import localtime

from core.models import User, Photographer, PhotographerAssignment
from client.models import Client
from ..services.permission_service import require_super_admin, api_require_super_admin, PermissionService
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from core.services.photographer_service import PhotographerService
from core.views.base_helpers import get_user_role, get_page_range
from accounts.rate_limit import rate_limit
from functools import wraps
from core.services.activity_service import ActivityService

def api_require_photographer_manager(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Authentication required'}, status=401)
        if not (PermissionService.is_super_admin(request.user) or PermissionService.has(request.user, 'perm_manage_photographer_staff')):
            return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper

logger = logging.getLogger(__name__)


def _apply_drawer_embed_frame_headers(request, response):
    if request.GET.get('embed') == 'drawer':
        response['X-Frame-Options'] = 'SAMEORIGIN'
    return response


def _parse_json_object(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None, JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    if not isinstance(data, dict):
        return None, JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    return data, None


def _photographer_assignment_snapshot(photographer_obj):
    if not photographer_obj:
        return {'client_ids': []}
    return {
        'client_ids': list(photographer_obj.photographer_assignments.values_list('client_id', flat=True))
    }


@login_required
def manage_photographers(request):
    """View to manage photographers — supports HTMX partial responses."""
    DEFAULT_PER_PAGE = 25
    PER_PAGE_OPTIONS = [5, 10, 25, 50, 100]

    try:
        per_page = int(request.GET.get('per_page', DEFAULT_PER_PAGE))
        if per_page not in PER_PAGE_OPTIONS:
            per_page = DEFAULT_PER_PAGE
    except (ValueError, TypeError):
        per_page = DEFAULT_PER_PAGE

    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()

    user = request.user
    can_manage = PermissionService.is_super_admin(user) or PermissionService.has(user, 'perm_manage_photographer_staff')
    if not can_manage:
        return HttpResponseForbidden("Access Denied")

    staff_qs = Photographer.objects.select_related('user').prefetch_related('photographer_assignments__client').order_by('-id')

    # active_clients used for assignment dropdown
    active_clients = Client.objects.filter(status='active', is_guest=False)
    
    if not PermissionService.is_super_admin(user):
        operator = getattr(user, 'operator_profile', None)
        if operator:
            active_clients = operator.assigned_clients.filter(status='active', is_guest=False)
        else:
            active_clients = Client.objects.none()
            
    active_clients = active_clients.order_by('name').values('id', 'name')

    if search_query:
        staff_qs = staff_qs.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__phone__icontains=search_query) |
            Q(user__username__icontains=search_query)
        )

    if status_filter == 'active':
        staff_qs = staff_qs.filter(user__is_active=True)
    elif status_filter == 'inactive':
        staff_qs = staff_qs.filter(user__is_active=False)

    paginator = Paginator(staff_qs, per_page)
    page_obj = paginator.get_page(request.GET.get('page', 1))


    # Detect if request is HTMX
    is_htmx = request.headers.get('HX-Request') == 'true'

    context = {
        'active_page': 'manage_photographers',
        'user_role': get_user_role(request.user),
        'staff_list': page_obj.object_list,
        'page_obj': page_obj,
        'page_range': get_page_range(page_obj),
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTIONS,
        'search_query': search_query,
        'status_filter': status_filter,
        'active_clients': list(active_clients),
    }

    if is_htmx:
        response = render(request, 'index.html', context)
        return _apply_drawer_embed_frame_headers(request, response)

    response = render(request, 'index.html', context)
    return _apply_drawer_embed_frame_headers(request, response)


@require_http_methods(["POST"])
@api_require_photographer_manager
@rate_limit(max_requests=10, window_seconds=60, key_prefix='photographer_create')
def api_photographer_create(request):
    """API endpoint to create a new photographer"""
    try:
        data, json_err = _parse_json_object(request)
        if json_err:
            return json_err

        result = PhotographerService.create(data, request=request)
        if result.success:
            try:
                photographer_id = result.data.get('staff', {}).get('id')
                photographer = Photographer.objects.select_related('user').filter(id=photographer_id).first()
                if photographer:
                    ActivityService.log_staff_create(request, photographer)
                    ActivityService.log_staff_assignment_change(
                        request,
                        photographer,
                        before_snapshot={},
                        after_snapshot=_photographer_assignment_snapshot(photographer),
                        reason='created',
                    )
            except Exception:
                logger.exception("Failed to log photographer create activity")
        return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)
    except Exception as e:
        logger.exception("Photographer API create error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)


@require_http_methods(["GET"])
@api_require_photographer_manager
@rate_limit(max_requests=60, window_seconds=60, key_prefix='photographer_get')
def api_photographer_get(request, staff_id):
    """API endpoint to get photographer details"""
    result = PhotographerService.get(staff_id)
    return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)


@require_http_methods(["PUT", "POST"])
@api_require_photographer_manager
def api_photographer_update(request, staff_id):
    """API endpoint to update photographer details"""
    try:
        data, json_err = _parse_json_object(request)
        if json_err:
            return json_err

        try:
            photographer = Photographer.objects.select_related('user').filter(id=staff_id).first()
            before_snapshot = _photographer_assignment_snapshot(photographer) if photographer else None
        except Exception:
            before_snapshot = None
            photographer = None

        result = PhotographerService.update(staff_id, data)
        if result.success and photographer:
            try:
                photographer.refresh_from_db()
                ActivityService.log_staff_update(request, photographer)
                after_snapshot = _photographer_assignment_snapshot(photographer)
                ActivityService.log_staff_assignment_change(
                    request,
                    photographer,
                    before_snapshot=before_snapshot,
                    after_snapshot=after_snapshot,
                    reason='updated',
                )
            except Exception:
                logger.exception("Failed to log photographer update activity")
        return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)
    except Exception as e:
        logger.exception("Photographer API update error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)


@require_http_methods(["DELETE", "POST"])
@api_require_photographer_manager
@rate_limit(max_requests=5, window_seconds=60, key_prefix='photographer_delete')
def api_photographer_delete(request, staff_id):
    """API endpoint to delete a photographer"""
    try:
        photographer = Photographer.objects.select_related('user').filter(id=staff_id).first()
        if photographer:
            name = photographer.user.get_full_name() or photographer.user.username
            last_active_str = ActivityService._format_last_active(photographer.user)
        else:
            name = f'Photographer #{staff_id}'
            last_active_str = 'never active'
    except Exception:
        name = f'Photographer #{staff_id}'
        last_active_str = 'never active'

    result = PhotographerService.delete(staff_id)
    if result.success:
        try:
            ActivityService.log_staff_delete(request, name, last_active_str, staff_id, user_type='Photographer')
        except Exception:
            logger.exception("Failed to log photographer delete activity")
    return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)


@require_http_methods(["POST"])
@api_require_photographer_manager
def api_photographer_toggle_status(request, staff_id):
    """API endpoint to toggle photographer active/inactive status"""
    try:
        photographer = Photographer.objects.select_related('user').filter(id=staff_id).first()
    except Exception:
        photographer = None

    result = PhotographerService.toggle_status(staff_id)
    if result.success and photographer:
        try:
            ActivityService.log_staff_status(request, photographer, result.data.get('is_active', False))
        except Exception:
            logger.exception("Failed to log photographer status activity")
    return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)


@require_http_methods(["POST"])
@api_require_photographer_manager
def api_photographer_assign_clients(request, staff_id):
    """API endpoint to update ONLY the client assignments for a photographer (no profile fields needed)"""
    try:
        data, json_err = _parse_json_object(request)
        if json_err:
            return json_err

        from django.utils.dateparse import parse_datetime
        from core.models import PhotographerAssignment
        from django.db import transaction

        try:
            staff = Photographer.objects.select_related('user').get(id=staff_id)
        except Photographer.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Photographer not found'}, status=404)

        before_snapshot = _photographer_assignment_snapshot(staff)

        assigned_clients = data.get('assigned_clients', [])
        if isinstance(assigned_clients, str):
            try:
                import json as _json
                assigned_clients = _json.loads(assigned_clients)
            except Exception:
                assigned_clients = []

        if not PermissionService.is_super_admin(request.user):
            operator = getattr(request.user, 'operator_profile', None)
            if operator:
                allowed_client_ids = set(operator.assigned_clients.values_list('id', flat=True))
            else:
                return JsonResponse({'success': False, 'message': 'Not authorized to manage assignments'}, status=403)
        else:
            allowed_client_ids = None

        with transaction.atomic():
            existing = {a.client_id: a for a in staff.photographer_assignments.all()}
            keep_client_ids = set()

            for item in assigned_clients:
                try:
                    client_id = int(item.get('client_id'))
                    if allowed_client_ids is not None and client_id not in allowed_client_ids:
                        continue # Operator can only assign their own clients
                        
                    expires_at_str = item.get('expires_at')
                    expires_at = parse_datetime(expires_at_str) if expires_at_str else None

                    if client_id in existing:
                        assignment = existing[client_id]
                        assignment.expires_at = expires_at
                        raw_table_ids = item.get('allowed_table_ids', [])
                        assignment.allowed_table_ids = [int(t) for t in raw_table_ids if str(t).isdigit()] if raw_table_ids else []
                        assignment.save()
                    else:
                        raw_table_ids = item.get('allowed_table_ids', [])
                        allowed_table_ids = [int(t) for t in raw_table_ids if str(t).isdigit()] if raw_table_ids else []
                        PhotographerAssignment.objects.create(
                            photographer=staff,
                            client_id=client_id,
                            expires_at=expires_at,
                            allowed_table_ids=allowed_table_ids,
                        )
                    keep_client_ids.add(client_id)
                except (ValueError, TypeError):
                    pass

            if allowed_client_ids is not None:
                # Operator: only delete assignments they have access to
                staff.photographer_assignments.filter(client_id__in=allowed_client_ids).exclude(client_id__in=keep_client_ids).delete()
            else:
                # Super Admin: delete all missing
                staff.photographer_assignments.exclude(client_id__in=keep_client_ids).delete()

        try:
            ActivityService.log_staff_assignment_change(
                request,
                staff,
                before_snapshot=before_snapshot,
                after_snapshot=_photographer_assignment_snapshot(staff),
                reason='updated',
            )
        except Exception:
            logger.exception("Failed to log photographer assignment change")

        return JsonResponse({'success': True, 'message': 'Client assignments saved successfully'})
    except Exception as e:
        logger.exception("Photographer assign clients error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)


@require_http_methods(["GET"])
@api_require_photographer_manager
def api_photographer_client_tables(request, client_id):
    """Return all groups and their tables for a client — used by assignment drawer."""
    try:
        from idcards.models import IDCardGroup, IDCardTable, IDCard
        from mediafiles.utils import get_card_photo_url

        groups = IDCardGroup.objects.filter(client_id=client_id, is_active=True).order_by('name')
        
        # Calculate captured/uncaptured counts per table for this client
        assigned_cards_qs = IDCard.objects.filter(
            table__group__client_id=client_id,
            status__in=['pending', 'verified']
        ).only('id', 'table_id', 'photo', 'field_data')

        uncaptured_counts = {}
        captured_counts = {}

        for card in assigned_cards_qs.iterator(chunk_size=500):
            has_photo = bool(get_card_photo_url(card))
            t_id = card.table_id
            if has_photo:
                captured_counts[t_id] = captured_counts.get(t_id, 0) + 1
            else:
                uncaptured_counts[t_id] = uncaptured_counts.get(t_id, 0) + 1

        result = []
        for group in groups:
            tables = IDCardTable.objects.filter(
                group=group, deleted_by_client=False
            ).order_by('name').values('id', 'name', 'is_active')
            
            tables_data = []
            for t in tables:
                t_id = t['id']
                tables_data.append({
                    'id': t_id,
                    'name': t['name'],
                    'is_active': t['is_active'],
                    'captured_count': captured_counts.get(t_id, 0),
                    'uncaptured_count': uncaptured_counts.get(t_id, 0)
                })

            result.append({
                'group_id': group.id,
                'group_name': group.name,
                'tables': tables_data,
            })
        return JsonResponse({'success': True, 'groups': result})
    except Exception as e:
        logger.exception("Photographer client tables error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)


@require_http_methods(["POST"])
@api_require_photographer_manager
def api_photographer_set_temp_password(request, staff_id):
    """API endpoint to set a temporary password for a photographer"""
    try:
        data, json_err = _parse_json_object(request)
        if json_err:
            return json_err
        new_password = data.get('password', '').strip()
        if not new_password:
            return JsonResponse({'success': False, 'message': 'Password is required'}, status=400)
        if len(new_password) < 8:
            return JsonResponse({'success': False, 'message': 'Password must be at least 8 characters'}, status=400)

        # Validate against Django password validators
        from django.contrib.auth.password_validation import validate_password
        try:
            validate_password(new_password)
        except Exception as validation_error:
            return JsonResponse({'success': False, 'message': '; '.join(validation_error.messages)}, status=400)

        result = PhotographerService.set_temp_password(staff_id, new_password, request=request)
        return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)
    except Exception as e:
        logger.exception("Photographer temp password error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)
