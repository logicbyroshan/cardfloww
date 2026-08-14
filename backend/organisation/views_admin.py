"""
Organisation admin views — manage clients page.

This provides a server-side rendered view of the organisations list,
scoped to the current user's permissions (super_admin sees all,
operators see only assigned organisations).
"""
import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q

from organisation.models import Organisation
from core.services.permission_service import PermissionService

logger = logging.getLogger(__name__)

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 200


def _get_per_page(request):
    try:
        per_page = int(request.GET.get('per_page', DEFAULT_PER_PAGE))
    except (TypeError, ValueError):
        per_page = DEFAULT_PER_PAGE
    return max(1, min(per_page, MAX_PER_PAGE))


@login_required
def manage_clients(request):
    """
    Manage Clients view — lists all organisations the user can access.

    Super admins see all organisations.
    Operators see only their assigned organisations.
    Client/client-staff users are redirected to login (access denied).
    """
    user = request.user

    # Only admin-type users may access this page
    if not PermissionService.is_any_admin(user):
        from django.conf import settings
        return redirect(getattr(settings, 'LOGIN_URL', '/auth/login/'))

    # Determine if the user can perform management operations
    can_manage_clients = (
        PermissionService.is_super_admin(user)
        or PermissionService.has(user, 'perm_idcard_client_list')
    )

    # Build base queryset — scoped to assigned orgs for operators
    if PermissionService.is_super_admin(user):
        qs = Organisation.objects.all().order_by('-created_at')
    else:
        # Operators: scope to assigned organisations
        try:
            from staff.models import Staff
            staff_profile = Staff.objects.filter(user=user).first()
            if staff_profile and staff_profile.assigned_organisations.exists():
                qs = staff_profile.assigned_organisations.all().order_by('-created_at')
            else:
                qs = Organisation.objects.none()
        except Exception:
            qs = Organisation.objects.none()

    # Search
    search = request.GET.get('search', '').strip()
    search_field = request.GET.get('search_field', '').strip()
    if search:
        if search_field == 'email':
            qs = qs.filter(user__email__icontains=search)
        elif search_field == 'name':
            qs = qs.filter(name__icontains=search)
        else:
            qs = qs.filter(
                Q(name__icontains=search) | Q(user__email__icontains=search)
            )

    per_page = _get_per_page(request)
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.get_page(page_number)
    except Exception:
        page_obj = paginator.get_page(1)

    clients = list(page_obj.object_list)

    context = {
        'clients': clients,
        'page_obj': page_obj,
        'can_manage_clients': can_manage_clients,
        'search': search,
        'search_field': search_field,
        'per_page': per_page,
    }

    return render(request, 'manage_clients.html', context)
