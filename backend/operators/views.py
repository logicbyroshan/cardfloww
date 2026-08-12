"""
Operators Views Module

Views for Operator management by Super Admin.
All views enforce Super Admin access at the view level.
"""
import json
import logging

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from organisation.models import Organisation
from operators.models import Operator
from core.services.activity_service import ActivityService

from .services import (
    OperatorCreationService,
    OperatorPermissionService,
    OperatorClientScopingService,
    check_client_access,
    check_permission,
    OPERATOR_PERMISSIONS,
)
from core.services.permission_service import (
    require_super_admin,
    require_any_admin,
    api_require_super_admin,
    api_require_any_admin,
)


logger = logging.getLogger(__name__)


def _parse_json_object(request):
    """Parse request JSON and require a dict payload for mutation endpoints."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None, JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    if not isinstance(data, dict):
        return None, JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    return data, None


# =============================================================================
# PAGE VIEWS
# =============================================================================

@login_required
@require_super_admin
def operators_management_page(request):
    """
    Operator management page for Super Admin.
    Handles both full page load and HTMX partial refresh.
    """
    # Heal missing operator profiles
    from core.models import User as CoreUser
    users_without_profile = CoreUser.objects.filter(role='operator', operator_profile__isnull=True)
    if users_without_profile.exists():
        for u in users_without_profile:
            Operator.objects.get_or_create(user=u)

    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()

    qs = Operator.objects.select_related('user').order_by('-created_at')

    if search_query:
        from django.db.models import Q as _Q
        qs = qs.filter(
            _Q(user__first_name__icontains=search_query) |
            _Q(user__last_name__icontains=search_query) |
            _Q(user__email__icontains=search_query) |
            _Q(user__phone__icontains=search_query)
        )

    if status_filter == 'active':
        qs = qs.filter(user__is_active=True)
    elif status_filter == 'inactive':
        qs = qs.filter(user__is_active=False)

    staff_list = list(qs)

    context = {
        'page_title': 'Manage Operators',
        'active_page': 'manage_staff',
        'staff_list': staff_list,
        'search_query': search_query,
        'status_filter': status_filter,
        'page_obj': None,
        'per_page': len(staff_list),
    }

    if request.headers.get('HX-Request'):
        return render(request, 'index.html', context)

    return render(request, 'index.html', context)


# =============================================================================
# OPERATOR CRUD API
# =============================================================================

@api_require_super_admin
@require_http_methods(['GET', 'POST'])
def api_operator_list_create(request):
    """
    GET: List all operators
    POST: Create new operator
    """
    if request.method == 'GET':
        result = OperatorCreationService.list_operators(request.user)
        return JsonResponse(result)
    
    # POST - Create new operator
    data, json_err = _parse_json_object(request)
    if json_err:
        return json_err
    
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    if not first_name and data.get('name'):
        name_val = data.get('name', '').strip()
        parts = name_val.split()
        first_name = parts[0] if parts else ''
        last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''

    result = OperatorCreationService.create_operator(
        created_by=request.user,
        first_name=first_name,
        last_name=last_name,
        email=data.get('email', ''),
        phone=data.get('phone', ''),
        designation=data.get('designation', 'Operator'),
        department=data.get('department', ''),
        assigned_client_ids=data.get('assigned_organisations', []),
        permission_codenames=data.get('permissions', []),
        password=data.get('password', ''),
    )
    
    if result.get('success'):
        name = f"{first_name} {last_name}".strip() or 'operator'
        ActivityService.log(
            'staff_create',  # Keep internal log keys consistent
            f'New operator "{name}" added',
            request=request,
            target_model='Operator',
            target_name=name,
        )
    
    status = 201 if result.get('success') else 400
    return JsonResponse(result, status=status)


@api_require_super_admin
@require_http_methods(['GET', 'PUT', 'POST', 'DELETE'])
def api_operator_detail(request, operator_id):
    """
    GET: Get operator detail
    POST/PUT: Update operator
    DELETE: Delete operator
    """
    # Heal missing profile if queried directly
    try:
        from core.models import User as CoreUser
        op = Operator.objects.filter(id=operator_id).first()
        if not op:
            usr = CoreUser.objects.filter(id=operator_id, role='operator').first()
            if usr:
                Operator.objects.get_or_create(user=usr)
    except Exception:
        pass

    if not Operator.objects.filter(id=operator_id).exists():
        return JsonResponse({'success': False, 'error': 'Operator not found'}, status=404)
    if request.method == 'GET':
        result = OperatorCreationService.get_operator_detail(request.user, operator_id)
        status = 200 if result.get('success') else 404
        return JsonResponse(result, status=status)
    
    if request.method in ('PUT', 'POST'):
        data, json_err = _parse_json_object(request)
        if json_err:
            return json_err
        
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        if not first_name and data.get('name'):
            name_val = data.get('name', '').strip()
            parts = name_val.split()
            first_name = parts[0] if parts else ''
            last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''

        result = OperatorCreationService.update_operator(
            updated_by=request.user,
            operator_id=operator_id,
            first_name=first_name,
            last_name=last_name,
            phone=data.get('phone'),
            designation=data.get('designation'),
            department=data.get('department'),
            assigned_client_ids=data.get('assigned_organisations'),
            permission_codenames=data.get('permissions'),
        )
        
        if result.get('success'):
            name = f"{first_name} {last_name}".strip() or 'operator'
            ActivityService.log(
                'staff_update',
                f'Operator "{name}" details updated',
                request=request,
                target_model='Operator',
                target_id=operator_id,
                target_name=name,
            )
        
        status = 200 if result.get('success') else 400
        return JsonResponse(result, status=status)
    
    if request.method == 'DELETE':
        result = OperatorCreationService.delete_operator(request.user, operator_id)
        if result.get('success'):
            name = result.get('data', {}).get('name', 'operator')
            ActivityService.log(
                'staff_delete',
                f'Operator "{name}" removed',
                request=request,
                target_model='Operator',
                target_id=operator_id,
                target_name=name,
            )
        status = 200 if result.get('success') else 400
        return JsonResponse(result, status=status)


@api_require_super_admin
@require_http_methods(['POST'])
def api_operator_toggle_status(request, operator_id):
    """Toggle operator active/inactive status."""
    try:
        if not Operator.objects.filter(id=operator_id).exists():
            return JsonResponse({'success': False, 'error': 'Operator not found'}, status=404)
        result = OperatorCreationService.toggle_status(request.user, operator_id)
        if result.get('success'):
            payload = result.get('data', {})
            new_status = payload.get('is_active')
            if new_status is None:
                new_status = result.get('is_active')
            name = payload.get('name', 'operator')
            label = 'active' if new_status else 'inactive'
            ActivityService.log(
                'staff_status',
                f'Operator "{name}" marked as {label}',
                request=request,
                target_model='Operator',
                target_id=operator_id,
                target_name=name,
            )
        status = 200 if result.get('success') else 400
        return JsonResponse(result, status=status)
    except Exception as e:
        logger.exception("Operator toggle status error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred. Please try again.'}, status=500)


@api_require_super_admin
@require_http_methods(['POST'])
def api_operator_delete(request, operator_id):
    """Delete an operator via POST (used by the JS frontend)."""
    try:
        if not Operator.objects.filter(id=operator_id).exists():
            return JsonResponse({'success': False, 'error': 'Operator not found'}, status=404)
        result = OperatorCreationService.delete_operator(request.user, operator_id)
        if result.get('success'):
            name = result.get('data', {}).get('name', 'operator')
            ActivityService.log(
                'staff_delete',
                f'Operator "{name}" removed',
                request=request,
                target_model='Operator',
                target_id=operator_id,
                target_name=name,
            )
        status = 200 if result.get('success') else 400
        return JsonResponse(result, status=status)
    except Exception as e:
        logger.exception("Operator delete error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred. Please try again.'}, status=500)


@api_require_super_admin
@require_http_methods(['POST'])
def api_operator_reset_password(request, operator_id):
    """Reset operator password and send email."""
    try:
        if not Operator.objects.filter(id=operator_id).exists():
            return JsonResponse({'success': False, 'error': 'Operator not found'}, status=404)
        result = OperatorCreationService.reset_password(request.user, operator_id)
        if result.get('success'):
            target_name = ''
            try:
                op_obj = Operator.objects.select_related('user').filter(id=operator_id).first()
                if op_obj and op_obj.user:
                    target_name = (op_obj.user.get_full_name() or op_obj.user.username or '').strip()
            except Exception:
                target_name = ''

            ActivityService.log(
                'staff_password_reset',
                f'Operator password reset for "{target_name or operator_id}"',
                request=request,
                target_model='Operator',
                target_id=operator_id,
                target_name=target_name,
            )
        status = 200 if result.get('success') else 400
        return JsonResponse(result, status=status)
    except Exception as e:
        logger.exception("Operator reset password error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred. Please try again.'}, status=500)


# =============================================================================
# PERMISSION & CLIENT LISTING API
# =============================================================================

@api_require_super_admin
@require_http_methods(['GET'])
def api_available_permissions(request):
    """Get list of permissions that can be assigned to operators."""
    permissions = OperatorPermissionService.get_assignable_permissions()
    return JsonResponse({
        'success': True,
        'permissions': permissions,
    })


@api_require_super_admin
@require_http_methods(['GET'])
def api_available_clients(request):
    """Get list of all clients for assignment to operators (includes inactive)."""
    clients = Organisation.objects.all().values('id', 'name', 'status')
    return JsonResponse({
        'success': True,
        'clients': list(clients),
    })


# =============================================================================
# OPERATOR SELF-SERVICE API
# =============================================================================

@api_require_any_admin
@require_http_methods(['GET'])
def api_my_permissions(request):
    """Get current user's permissions (for operator dashboard)."""
    permissions = OperatorPermissionService.get_user_permissions(request.user)
    scope = OperatorClientScopingService.get_scope_context(request.user)
    
    return JsonResponse({
        'success': True,
        'user': {
            'id': request.user.id,
            'name': request.user.get_full_name(),
            'email': request.user.email,
            'role': request.user.role,
        },
        'permissions': permissions,
        'scope': scope,
    })


@api_require_any_admin
@require_http_methods(['GET'])
def api_my_clients(request):
    """Get clients accessible to the current operator user."""
    clients = OperatorClientScopingService.get_accessible_clients(request.user)
    
    return JsonResponse({
        'success': True,
        'clients': list(clients.values('id', 'name', 'status')),
    })


# =============================================================================
# CLIENT-SCOPED DATA ACCESS EXAMPLES
# =============================================================================

@api_require_any_admin
@check_permission('can_view_clients')
@require_http_methods(['GET'])
def api_scoped_clients(request):
    """
    Example: Get clients with automatic scoping.
    Operators only see their assigned clients.
    """
    clients = OperatorClientScopingService.get_accessible_clients(request.user)
    
    status = request.GET.get('status')
    if status:
        clients = clients.filter(status=status)
    
    search = request.GET.get('search')
    if search:
        clients = clients.filter(name__icontains=search)
    
    return JsonResponse({
        'success': True,
        'clients': list(clients.values('id', 'name', 'status', 'city')),
    })


@api_require_any_admin
@check_permission('can_view_idcard_data')
@check_client_access('client_id')
@require_http_methods(['GET'])
def api_client_idcard_groups(request, client_id):
    """
    Example: Get ID card groups for a specific client.
    Enforces both permission AND client access checks.
    """
    from tables.models import Table
    
    groups = Table.objects.filter(client_id=client_id)
    
    return JsonResponse({
        'success': True,
        'groups': list(groups.values('id', 'name', 'is_active')),
    })


# =============================================================================
# UTILITY VIEWS
# =============================================================================

@login_required
@require_any_admin
def operator_dashboard(request):
    """
    Operator dashboard with scoped data.
    """
    from django.db.models import Count, Q
    from tables.models import IDCard
    from core.services.permission_service import PermissionService

    scope = OperatorClientScopingService.get_scope_context(request.user)
    permissions = OperatorPermissionService.get_user_permissions(request.user)

    user = request.user
    is_scoped = PermissionService.is_operator(user)
    card_qs = IDCard.objects.all()
    if is_scoped:
        accessible_ids = PermissionService.get_accessible_client_ids(user)
        card_qs = card_qs.filter(table__group__client_id__in=accessible_ids)
    
    card_stats = card_qs.aggregate(
        total=Count('id', filter=Q(status__in=['pending', 'verified', 'approved', 'download'])),
        pending=Count('id', filter=Q(status='pending')),
        verified=Count('id', filter=Q(status='verified')),
        approved=Count('id', filter=Q(status='approved')),
        downloaded=Count('id', filter=Q(status='download')),
    )

    recent_activities = ActivityService.get_recent(limit=15, user=user)

    context = {
        'page_title': 'Operator Dashboard',
        'active_page': 'dashboard',
        'scope': scope,
        'permissions': permissions,
        'total_id_cards': card_stats['total'],
        'pending_cards': card_stats['pending'],
        'verified_cards': card_stats['verified'],
        'approved_cards': card_stats['approved'],
        'downloaded_cards': card_stats['downloaded'],
        'recent_activities': recent_activities,
    }

    return render(request, 'index.html', context)
