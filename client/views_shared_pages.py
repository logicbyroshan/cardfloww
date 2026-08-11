"""
Client Views — shared admin-template pages.

Page views that render the same templates used by the admin panel
but scoped to the current client's data and permissions.
"""
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.core.cache import cache
from django.db.models import Count, Q
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.utils.timezone import localtime

from idcards.models import IDCard, IDCardTable
from core.services import IDCardService
from core.services.permission_service import PermissionService
from core.utils.htmx import is_htmx
from core.views.idcard_helpers import _apply_client_staff_row_scope

from .views_decorators import require_client_user, require_client_admin, _get_client_for_request
from .services import ClientAccessService


# =============================================================================
# SHARED PAGES — Render admin templates with client context
# =============================================================================

@require_client_user
def client_idcard_group(request):
    """
    ID Card Group page for clients — same template as admin idcard-group.html.
    Auto-detects client from user profile.
    """
    user = request.user
    client = _get_client_for_request(user)
    if not client:
        return redirect(reverse('client:dashboard'))
    
    # Check if user has any list permission (affects what content is shown)
    LIST_PERMISSIONS = [
        'perm_idcard_setting_list', 'perm_idcard_pending_list',
        'perm_idcard_verified_list', 'perm_idcard_approved_list',
        'perm_idcard_download_list', 'perm_idcard_pool_list',
        'perm_idcard_reprint_list', 'perm_reprint_request_list',
        'perm_confirmed_list',
    ]
    has_any_list_perm = any(PermissionService.has_permission(user, p) for p in LIST_PERMISSIONS)
    
    # Always render the page — show empty if no permissions
    if has_any_list_perm:
        tables_qs = IDCardTable.objects.filter(
            group__client=client,
            deleted_by_client=False,   # hide client-soft-deleted tables
        ).select_related('group', 'group__client')

        # For client_staff with assigned groups: restrict to those groups only
        if PermissionService.is_client_staff(user):
            tables_qs = ClientAccessService.get_scoped_tables_qs(user, client, tables_qs)

            ordered_tables = list(tables_qs.order_by('-updated_at'))
            table_ids = [table.id for table in ordered_tables]
            pool_counts = {
                row['table_id']: row['count']
                for row in (
                    IDCard.objects
                    .filter(table_id__in=table_ids, status='pool')
                    .values('table_id')
                    .annotate(count=Count('id'))
                )
            } if table_ids else {}

            try:
                from core.services.session_revalidation import get_user_revalidation_marker

                marker = str(get_user_revalidation_marker(getattr(user, 'pk', None)) or '')
            except Exception:
                marker = ''

            scoped_tables = []
            for table in ordered_tables:
                counts_cache_key = (
                    f'client:idcard_group:staff_counts:v1:'
                    f'user:{user.id}:table:{table.id}:m:{marker}'
                )
                counts_by_status = cache.get(counts_cache_key)
                if not isinstance(counts_by_status, dict):
                    scoped_cards = _apply_client_staff_row_scope(
                        IDCard.objects.filter(table=table),
                        user,
                        table,
                    )
                    counts_by_status = {
                        row['status']: row['count']
                        for row in scoped_cards.values('status').annotate(count=Count('id'))
                    }
                    cache.set(counts_cache_key, counts_by_status, 10)

                table.pending_count = counts_by_status.get('pending', 0)
                table.verified_count = counts_by_status.get('verified', 0)
                table.pool_count = pool_counts.get(table.id, 0)
                table.approved_count = counts_by_status.get('approved', 0)
                table.download_count = counts_by_status.get('download', 0)

                table.total_cards = (
                    table.pending_count
                    + table.verified_count
                    + table.pool_count
                    + table.approved_count
                    + table.download_count
                )
                scoped_tables.append(table)

            tables = scoped_tables
        else:
            tables = tables_qs.annotate(
                pending_count=Count('id_cards', filter=Q(id_cards__status='pending')),
                verified_count=Count('id_cards', filter=Q(id_cards__status='verified')),
                pool_count=Count('id_cards', filter=Q(id_cards__status='pool')),
                approved_count=Count('id_cards', filter=Q(id_cards__status='approved')),
                download_count=Count('id_cards', filter=Q(id_cards__status='download')),
                total_cards=Count('id_cards')
            ).order_by('-updated_at')
    else:
        tables = IDCardTable.objects.none()

    # Get default group for Create with XLSX button
    group = IDCardService.ensure_default_group(client)
    
    context = {
        'active_page': 'idcard_group',
        'user_role': user.get_role_display(),
        'client': client,
        'group': group,
        'tables': tables,
    }
    return render(request, 'index.html', context)


@require_client_user
def client_idcard_actions(request, table_id):
    """
    ID Card Actions page for clients — same template as admin idcard-actions.html.
    Uses shared build_idcard_actions_context() helper for queryset + context.
    """
    user = request.user
    client = _get_client_for_request(user)
    if not client:
        return redirect(reverse('client:dashboard'))
    
    # Require at least one list permission or table scope for assistant
    LIST_PERMISSIONS = [
        'perm_idcard_pending_list', 'perm_idcard_verified_list',
        'perm_idcard_approved_list', 'perm_idcard_download_list',
        'perm_idcard_pool_list', 'perm_idcard_reprint_list',
        'perm_reprint_request_list', 'perm_confirmed_list',
    ]
    table = get_object_or_404(IDCardTable.objects.select_related('group__client'), id=table_id)
    
    # Verify table access (client owner or assigned assistant)
    if not ClientAccessService.can_access_table(user, table):
        return redirect(reverse('client:idcard_group'))
    
    has_list_perm = any(PermissionService.has_permission(user, p) for p in LIST_PERMISSIONS)
    if not has_list_perm and not PermissionService.is_client_staff(user):
        return redirect(reverse('client:dashboard'))
    
    status_filter = request.GET.get('status', None)
    if status_filter:
        from core.views.base import _STATUS_LIST_PERM
        required_perm = _STATUS_LIST_PERM.get(status_filter)
        if required_perm and not PermissionService.has_permission(user, required_perm):
            accessible_statuses = [
                st for st, perm in _STATUS_LIST_PERM.items()
                if PermissionService.has_permission(user, perm)
            ]
            if accessible_statuses:
                return redirect(f"{reverse('client:idcard_actions', args=[table.id])}?status={accessible_statuses[0]}")
            elif PermissionService.is_client_staff(user):
                status_filter = None
            else:
                return redirect(reverse('client:idcard_group'))
    
    from core.views.base import build_idcard_actions_context
    context = build_idcard_actions_context(
        request, table,
        default_per_page=50,
        per_page_options=[50, 100, 150, 200],
        active_page='idcard_group',
        user_role=user.get_role_display(),
    )
    
    # React SPA handles all card data fetching via REST API.
    context['actions_base_url'] = reverse('client:idcard_actions', args=[table.id])
    return render(request, 'index.html', context)


@require_client_admin
def client_group_settings(request):
    """
    Group Settings page for client admins only — not available to client_staff.
    Same template as admin group-setting.html, scoped to the current client.

    Supports:
    - HTMX partial responses (table-container only)
    - Search by table name
    - Pagination (matching admin defaults: 10 per page)
    - Excludes tables soft-deleted by this client (deleted_by_client=True)
    """
    from django.core.paginator import Paginator
    from core.views.base_helpers import get_page_range

    user = request.user
    client = _get_client_for_request(user)
    if not client:
        return redirect(reverse('client:dashboard'))

    # Always render — show empty if no permissions
    has_perm = PermissionService.has_permission(user, 'perm_idcard_setting_list')

    search_query = request.GET.get('search', '').strip()

    if has_perm:
        group = IDCardService.ensure_default_group(client)
        tables_qs = IDCardTable.objects.filter(
            group=group,
            deleted_by_client=False,   # hide client-soft-deleted tables
        ).annotate(total_cards=Count('id_cards')).order_by('-updated_at')

        if search_query:
            tables_qs = tables_qs.filter(name__icontains=search_query)
    else:
        group = None
        tables_qs = IDCardTable.objects.none()

    DEFAULT_PER_PAGE = 10
    PER_PAGE_OPTIONS = [5, 10, 25, 50]
    try:
        per_page = int(request.GET.get('per_page', DEFAULT_PER_PAGE))
        if per_page not in PER_PAGE_OPTIONS:
            per_page = DEFAULT_PER_PAGE
    except (ValueError, TypeError):
        per_page = DEFAULT_PER_PAGE

    paginator = Paginator(tables_qs, per_page)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'active_page': 'group_settings',
        'user_role': user.get_role_display(),
        'client': client,
        'group': group,
        'tables': page_obj.object_list,
        'page_obj': page_obj,
        'page_range': get_page_range(page_obj),
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTIONS,
        'search_query': search_query,
    }

    if is_htmx(request):
        return render(request, 'index.html', context)

    return render(request, 'index.html', context)



# =============================================================================
# CREATE TABLE FROM XLSX (client side)
# =============================================================================

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

    group = IDCardService.ensure_default_group(client)
    from core.views.idcard_api import api_create_table_from_xlsx
    return api_create_table_from_xlsx(request, group.id)
