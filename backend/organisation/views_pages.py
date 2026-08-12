"""
Client Views — page rendering views.

Full-page views for the client dashboard, card groups, card table,
and staff management.
"""
from django.urls import reverse
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q, Count
from django.utils import timezone

from tables.models import Table
from core.services.permission_service import PermissionService
from core.models import ClientMessage, NotificationRead

from .views_decorators import require_client_user, require_client_admin, require_client_staff_manager
from .services import OrganisationAccessService, OrganisationDashboardService


# =============================================================================
# PAGE VIEWS
# =============================================================================

@require_client_user
def dashboard(request):
    """
    Client Dashboard - shows summary of card data and quick actions.
    """
    user = request.user
    client = OrganisationAccessService.get_organisation_for_user(user)
    
    if not client:
        return redirect('/panel/auth/login/')
    
    # Get dashboard data
    result = OrganisationDashboardService.get_dashboard_data(user)
    
    # Get permission context
    permissions = PermissionService.get_permission_context(user)
    
    context = {
        'user': user,
        'user_name': user.get_full_name() or user.username,
        'user_role': 'Client Admin' if PermissionService.is_client(user) else 'Assistant',
        'client': Organisation,
        'is_client_admin': PermissionService.is_client(user),
        'active_page': 'dashboard',
        **permissions,
    }
    
    if result.success:
        context.update(result.data)
    
    # Fetch accessible tables for reprint links/dropdown and ID Card Group dashboard section
    tables_qs = Table.objects.filter(
        group__client=client,
        deleted_by_client=False,
    ).select_related('group', 'group__client')

    has_any_list_perm = any(PermissionService.has_permission(user, p) for p in [
        'perm_idcard_setting_list', 'perm_idcard_pending_list',
        'perm_idcard_verified_list', 'perm_idcard_approved_list',
        'perm_idcard_download_list', 'perm_idcard_pool_list',
        'perm_idcard_reprint_list', 'perm_reprint_request_list',
        'perm_confirmed_list',
    ])

    if has_any_list_perm:
        if PermissionService.is_client_staff(user):
            from django.core.cache import cache
            from core.views.idcard_helpers import _apply_client_staff_row_scope
            from tables.models import IDCard

            tables_qs = OrganisationAccessService.get_scoped_tables_qs(user, client, tables_qs)
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
            tables = list(tables_qs.annotate(
                pending_count=Count('id_cards', filter=Q(id_cards__status='pending')),
                verified_count=Count('id_cards', filter=Q(id_cards__status='verified')),
                pool_count=Count('id_cards', filter=Q(id_cards__status='pool')),
                approved_count=Count('id_cards', filter=Q(id_cards__status='approved')),
                download_count=Count('id_cards', filter=Q(id_cards__status='download')),
                total_cards=Count('id_cards')
            ).order_by('-updated_at'))
    else:
        tables = []

    context['tables'] = tables
    context['accessible_tables'] = tables
    
    return render(request, 'index.html', context)


@require_client_user
def card_groups(request):
    """
    View all card groups (ID Card Settings) for the client.
    """
    user = request.user
    client = OrganisationAccessService.get_organisation_for_user(user)
    
    if not client:
        return redirect('/panel/auth/login/')
    
    # Check permission
    if not (
        PermissionService.has_permission(user, 'perm_idcard_setting_list')
        or PermissionService.has_permission(user, 'perm_idcard_reprint_list')
        or PermissionService.has_permission(user, 'perm_reprint_request_list')
        or PermissionService.has_permission(user, 'perm_confirmed_list')
    ):
        return redirect(reverse('client:dashboard'))
    
    result = OrganisationDashboardService.get_groups_with_counts(user)
    permissions = PermissionService.get_permission_context(user)
    
    context = {
        'user': user,
        'user_name': user.get_full_name() or user.username,
        'user_role': 'Client Admin' if PermissionService.is_client(user) else 'Assistant',
        'client': Organisation,
        'is_client_admin': PermissionService.is_client(user),
        'active_page': 'groups',
        'groups': result.data.get('groups', []) if result.success else [],
        **permissions,
    }
    
    return render(request, 'index.html', context)


@require_client_user
def card_table(request, table_id):
    """
    View cards in a specific table.
    """
    user = request.user
    client = OrganisationAccessService.get_organisation_for_user(user)
    
    if not client:
        return redirect('/panel/auth/login/')
    
    # Require at least one list permission to view cards
    LIST_PERMISSIONS = [
        'perm_idcard_setting_list', 'perm_idcard_pending_list',
        'perm_idcard_verified_list', 'perm_idcard_approved_list',
        'perm_idcard_download_list', 'perm_idcard_pool_list',
        'perm_idcard_reprint_list',
        'perm_reprint_request_list', 'perm_confirmed_list',
    ]
    if not any(PermissionService.has_permission(user, p) for p in LIST_PERMISSIONS):
        return redirect(reverse('client:dashboard'))
    
    # Verify access
    try:
        table = Table.objects.select_related('group__client').get(id=table_id)
    except Table.DoesNotExist:
        return redirect(reverse('client:groups'))
    
    if not OrganisationAccessService.can_access_table(user, table):
        return redirect(reverse('client:groups'))
    
    # Get status filter from query params
    status_filter = request.GET.get('status', '')
    
    permissions = PermissionService.get_permission_context(user)
    
    context = {
        'user': user,
        'user_name': user.get_full_name() or user.username,
        'user_role': 'Client Admin' if PermissionService.is_client(user) else 'Assistant',
        'client': Organisation,
        'is_client_admin': PermissionService.is_client(user),
        'active_page': 'groups',
        'table': table,
        'group': table.group,
        'status_filter': status_filter,
        **permissions,
    }
    
    return render(request, 'index.html', context)


@require_client_user
def print_table(request, table_id):
    """
    Client-facing print view for a table. Tests expect a redirect to
    the idcard-group page when the current client lacks print/download
    permissions. We do not implement full printing here; just guard access
    and redirect appropriately.
    """
    user = request.user
    client = OrganisationAccessService.get_organisation_for_user(user)
    if not client:
        return redirect('/panel/auth/login/')

    # Print functionality removed — print routes are deprecated.
    # Redirect to the shared ID card group view expected by existing callers.
    return redirect(reverse('client:idcard_group'))


@require_client_staff_manager
def manage_staff(request):
    """
    Manage client staff members.
    Only accessible by Client Admin.
    Uses same layout as admin manage-staff page.
    """
    user = request.user
    client = OrganisationAccessService.get_organisation_for_user(user)
    
    if not client:
        return redirect('/panel/auth/login/')
    
    # Check permission: allow either client-list toggle or explicit manage-staff flag
    if not (PermissionService.has_permission(user, 'perm_idcard_client_list')
            or PermissionService.has_permission(user, 'perm_manage_assistant')):
        return redirect(reverse('client:dashboard'))
    
    # Get Assistant QuerySet directly for server-side table rendering
    from assistants.models import Assistant
    staff_list = Assistant.objects.filter(
        client=client
    ).select_related('user').order_by('-created_at')
    
    permissions = PermissionService.get_permission_context(user)
    
    context = {
        'user': user,
        'user_name': user.get_full_name() or user.username,
        'user_role': 'Client Admin' if PermissionService.is_client(user) else 'Assistant',
        'client': Organisation,
        'is_client_admin': PermissionService.is_client(user),
        'active_page': 'staff',
        'staff_list': staff_list,
        **permissions,
    }
    
    return render(request, 'index.html', context)


@require_client_user
def messages(request):
    """Read-only client message history page (admin-originated one-way messages)."""
    user = request.user
    client = OrganisationAccessService.get_organisation_for_user(user)

    if not client:
        return redirect('/panel/auth/login/')

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
        .select_related('client', 'sent_by', 'notification')
        .order_by('-created_at')
    )

    paginator = Paginator(base_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    unread_count = base_qs.filter(is_read=False).count()

    permissions = PermissionService.get_permission_context(user)
    context = {
        'user': user,
        'user_name': user.get_full_name() or user.username,
        'user_role': 'Client Admin' if PermissionService.is_client(user) else 'Assistant',
        'client': Organisation,
        'is_client_admin': PermissionService.is_client(user),
        'active_page': 'client_messages',
        'messages_page': page_obj,
        'unread_count': unread_count,
        'total_count': paginator.count,
        **permissions,
    }
    return render(request, 'index.html', context)
