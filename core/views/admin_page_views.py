"""
Admin page views — staff, client, ID card management pages.
Split from base.py for maintainability.
"""
import logging
from django.conf import settings as django_settings
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q, Case, When, Value, BooleanField
from django.utils import timezone
from django.utils.timesince import timesince as django_timesince

from client.models import Client
from operators.models import Operator
from staff.models import Staff
from accounts.services import AuthService
from idcards.models import IDCardGroup, IDCard, IDCardTable
from mediafiles.models import CardMedia
from mediafiles.services.image_thumbnail import ThumbnailService
from django.core.files.storage import default_storage
from ..models import User, Notification, EmailLog, ActivityLog
from ..services import IDCardService
from ..utils.htmx import is_htmx
from ..services.permission_service import (
    PermissionService,
    require_any_admin,
    require_super_admin,
)
from .base_helpers import (
    get_user_role,
    get_page_range,
    _STATUS_LIST_PERM,
    _VALID_STATUSES,
)
from .idcard_helpers import (
    _apply_client_staff_row_scope,
    _build_class_filter_q,
    _get_class_section_course_branch_field_names,
)

logger = logging.getLogger(__name__)



def _apply_drawer_embed_frame_headers(request, response):
    """Allow same-origin iframe embedding only for dashboard drawer embed mode."""
    if request.GET.get('embed') == 'drawer':
        response['X-Frame-Options'] = 'SAMEORIGIN'
    return response


def _normalize_device_surface(value):
    normalized = str(value or '').strip().lower()
    if normalized in {'desktop', 'mobile'}:
        return normalized
    return 'unknown'


def _infer_device_surface(action, description):
    text = f"{action or ''} {description or ''}".lower()
    mobile_tokens = ('mobile app', 'android', 'iphone', 'ipad', 'ipod', ' ios ', 'mobile')
    desktop_tokens = ('desktop web', 'desktop', 'browser', 'windows', 'mac', 'linux', 'web app', 'web')

    if any(token in text for token in mobile_tokens):
        return 'mobile'
    if any(token in text for token in desktop_tokens):
        return 'desktop'
    return 'unknown'


def _device_surface_meta(surface):
    normalized = _normalize_device_surface(surface)
    if normalized == 'mobile':
        return {
            'device_surface': 'mobile',
            'device_surface_label': 'Mobile',
            'device_surface_icon': 'fa-mobile-screen-button',
        }
    if normalized == 'desktop':
        return {
            'device_surface': 'desktop',
            'device_surface_label': 'Desktop',
            'device_surface_icon': 'fa-desktop',
        }
    return {
        'device_surface': 'unknown',
        'device_surface_label': 'Unknown',
        'device_surface_icon': 'fa-circle-question',
    }


def _active_device_snapshot(user_id):
    if not user_id:
        return {
            'fingerprints': [],
            'surface_counts': {'desktop': 0, 'mobile': 0},
            'devices': [],
        }

    ids = {str(user_id)}
    fingerprints = set()
    surface_counts = {'desktop': 0, 'mobile': 0}
    devices = []

    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator(chunk_size=200):
        try:
            data = session.get_decoded()
        except Exception:
            continue

        user_id_str = str(data.get('_auth_user_id') or '')
        if user_id_str not in ids:
            continue

        surface = _normalize_device_surface(data.get('_auth_login_surface'))
        if surface in surface_counts:
            surface_counts[surface] += 1

        fingerprint = str(data.get('_auth_browser_fp') or '').strip() or f'session:{session.session_key}'
        fingerprints.add(fingerprint)

        session_info = AuthService.session_device_info(data, session_key=session.session_key)
        if session_info.get('surface') == 'desktop' and surface == 'mobile':
            session_info['surface'] = 'mobile'
        devices.append(session_info)

    devices.sort(key=lambda item: int(item.get('login_ts') or 0), reverse=True)

    return {
        'fingerprints': sorted(fingerprints),
        'surface_counts': surface_counts,
        'devices': devices,
    }


def _serialize_login_history_event(entry, action_display_map, now):
    meta = _device_surface_meta(_infer_device_surface(entry.action, entry.description))
    event = {
        'id': entry.pk,
        'action': entry.action,
        'action_display': action_display_map.get(entry.action, entry.action),
        'description': entry.description or '',
        'ip_address': entry.ip_address or '',
        'icon_class': entry.icon_class,
        'icon_color': entry.icon_color,
        'created_at': timezone.localtime(entry.created_at).strftime('%d-%m-%Y %H:%M'),
        'time_ago': django_timesince(entry.created_at, now) + ' ago',
    }
    event.update(meta)
    return event


def _serialize_assignment_history_event(entry, action_display_map, now):
    actor_name = 'System'
    if entry.user_id:
        actor_name = entry.user.get_full_name() or entry.user.username or 'System'

    return {
        'id': entry.pk,
        'action': entry.action,
        'action_display': action_display_map.get(entry.action, entry.action),
        'description': entry.description or '',
        'actor_name': actor_name,
        'icon_class': entry.icon_class,
        'icon_color': entry.icon_color,
        'created_at': timezone.localtime(entry.created_at).strftime('%d-%m-%Y %H:%M'),
        'time_ago': django_timesince(entry.created_at, now) + ' ago',
    }


def _build_personal_guide_text(share_url):
    """Build the downloadable plain-text personal guide content."""
    lines = [
        "ADARSH ID CARDS - PERSONAL GUIDE (CLIENT OPERATIONS)",
        "=" * 62,
        "",
        "Student Data Check, Corrections ya New Add karne ke liye is panel se login kare:",
        "https://panel.adarshbhopal.in/",
        "",
        "Client section me login kare:",
        "email id: client.demo@example.com",
        "pw: Demo@1234",
        "(ye sirf example credentials hain; login ke baad apna password zarur change kare)",
        "",
        "Share Link (Admin/Superadmin clients ko bhejne ke liye):",
        share_url,
        "",
        "NAYE CLIENT FEATURES (DETAIL):",
        "1) Kisi bhi class ya section ka PDF me data download kiya ja sakta hai.",
        "2) Search + filter se class, section, naam, ID ke hisab se records instantly mil jate hain.",
        "3) Checkbox se bulk verify aur bulk approve dono actions ek saath kiye ja sakte hain.",
        "4) Aap admin hain: kisi bhi class/section ko particular teacher ko checking ke liye assign kar sakte hain.",
        "5) Teacher ke liye nayi user ID bana kar use sub-staff role diya ja sakta hai.",
        "6) Role-based permission se har user ko sirf zaruri access diya ja sakta hai.",
        "7) Pool List se galat approve/verified record ko Retrieve karke wapas Pending me bheja ja sakta hai.",

        "9) Export/download flow me final files ko standard naam se archive kar sakte hain.",
        "10) Notifications aur activity tracking se team handover clear rehta hai.",
        "11) Google Chrome par panel login ke baad app install option bhi available hota hai.",
        "12) Table-level workflow se Pending -> Verified -> Approved process clean aur auditable rehta hai.",
        "",
        "FEATURES KO KAAM ME KAISE USE KARE:",
        "A) Daily start: filters lagao, pending backlog nikalo, high-priority classes pe kaam karo.",
        "B) Mid process: correction complete karke Verify karo; bulk action me checkbox use karo.",
        "C) Final stage: Verified list se final check karke Approve karo aur export nikalo.",
        "D) Exception stage: koi galti mile to Pool List + Retrieve se record wapas Pending me lao.",
        "",
        "INSTRUCTIONS (STEP BY STEP):",
        "A) Client section me login karne ke baad Pending List me sabhi data hota hai.",
        "   - Yahi se data correction kiya jata hai aur new data add kiya ja sakta hai.",
        "   - Photo change/new upload: photo column me photo ke niche Edit option par click kare,",
        "     fir Upload Photo par click karke photo upload kare.",
        "",
        "B) Pending List me har field me Verify button diya hota hai.",
        "   - Data correction complete karke Verify kare.",
        "   - Verify hone ke baad data Verified List me chala jata hai.",
        "",
        "C) Verified List me final review karke har record ko Approve kare.",
        "   - Approve button se record final hota hai.",
        "   - Bulk action ke liye checkbox se multiple records ek saath approve kar sakte hain.",
        "",
        "D) Important Rule:",
        "   - Data approve hone ke baad normal flow me usme correction nahi kiya ja sakta.",
        "",
        "E) Pool List Workflow:",
        "   - Agar kisi record ko dobara correction ke liye bhejna ho,",
        "     to Pool List me record select karke Retrieve par click kare.",
        "   - Record wapas Pending List me shift ho jayega.",
        "",
        "F) Daily Best Practice (Recommended):",
        "   - Day start me Pending backlog clear kare.",
        "   - Verify aur approve ke beech ek quick final check zarur kare.",
        "   - Data export/download se pehle class/section filter double-check kare.",
        "   - Team accounts alag rakhe; ek hi login ko multiple users me share na kare.",
        "",
        "G) Support:",
        "   - Koi bhi doubt ho to 9301199730 par call kijiyega.",
        "",
        "Note: Kuch options aapke role/permissions ke hisab se dikhte hain.",
    ]
    return "\n".join(lines)


# Staff Management
@require_super_admin
def manage_staff(request):
    """View to manage admin staff — supports HTMX partial responses."""
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
    
    staff_qs = Operator.objects.select_related('user').order_by('-id')
    
    # Server-side search
    if search_query:
        staff_qs = staff_qs.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__phone__icontains=search_query) |
            Q(user__username__icontains=search_query)
        )
    
    # Server-side status filter
    if status_filter == 'active':
        staff_qs = staff_qs.filter(user__is_active=True)
    elif status_filter == 'inactive':
        staff_qs = staff_qs.filter(user__is_active=False)
    
    # This page already uses client-side pagination/search over rendered rows.
    # Keep server pagination as a single page with the full filtered queryset
    # to avoid "10 of 10" mismatches when more rows exist.
    paginator = Paginator(staff_qs, per_page)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    
    context = {
        'active_page': 'manage_staff',
        'user_role': get_user_role(request.user),
        'staff_list': page_obj.object_list,
        'page_obj': page_obj,
        'page_range': get_page_range(page_obj),
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTIONS,
        'search_query': search_query,
        'status_filter': status_filter,
    }
    
    if is_htmx(request):
        response = render(request, 'index.html', context)
        return _apply_drawer_embed_frame_headers(request, response)

    response = render(request, 'index.html', context)
    return _apply_drawer_embed_frame_headers(request, response)


# Client Staff Management
@login_required
@require_any_admin
def manage_client_staff(request):
    """Deprecated: admin Manage Assistant UI removed. Redirecting to Manage Staff."""
    return redirect(reverse('manage_staff'))


# Client Management
@login_required
@require_any_admin
def manage_clients(request):
    """View to manage all clients — supports HTMX partial responses."""
    user = request.user
    can_manage_clients = PermissionService.is_super_admin(user) or PermissionService.has(user, 'perm_idcard_client_list')

    DEFAULT_PER_PAGE = 25
    PER_PAGE_OPTIONS = [5, 10, 25, 50, 100]
    
    try:
        per_page = int(request.GET.get('per_page', DEFAULT_PER_PAGE))
        if per_page not in PER_PAGE_OPTIONS:
            per_page = DEFAULT_PER_PAGE
    except (ValueError, TypeError):
        per_page = DEFAULT_PER_PAGE
    
    search_query = request.GET.get('search', '').strip()
    search_field = request.GET.get('search_field', 'all').strip().lower()
    status_filter = request.GET.get('status', '').strip().lower()

    if search_field not in ('all', 'name', 'email', 'mobile'):
        search_field = 'all'

    if status_filter not in ('all', 'active', 'inactive', 'suspended'):
        status_filter = 'all'
    
    # Admin staff can always open this page, but the result set remains
    # scoped to their assigned clients.
    clients_qs = (
        Client.objects
        .all()
        .select_related('user')
        .annotate(
            table_count=Count('id_card_groups__tables', distinct=True),
            has_media=Exists(CardMedia.objects.filter(client_id=OuterRef('pk'))),
        )
        .annotate(
            has_data=Case(
                When(Q(table_count__gt=0) | Q(has_media=True), then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )
        .order_by('-id')
    )
    clients_qs = PermissionService.get_accessible_clients(user, base_qs=clients_qs)
    
    if search_query:
        if search_field == 'name':
            clients_qs = clients_qs.filter(name__icontains=search_query)
        elif search_field == 'email':
            clients_qs = clients_qs.filter(user__email__icontains=search_query)
        elif search_field == 'mobile':
            clients_qs = clients_qs.filter(user__phone__icontains=search_query)
        else:
            clients_qs = clients_qs.filter(
                Q(name__icontains=search_query) |
                Q(user__email__icontains=search_query) |
                Q(user__phone__icontains=search_query)
            )
    if status_filter in ('active', 'inactive', 'suspended'):
        clients_qs = clients_qs.filter(status=status_filter)
    
    paginator = Paginator(clients_qs, per_page)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    
    context = {
        'active_page': 'manage_clients',
        'user_role': get_user_role(request.user),
        'clients': page_obj.object_list,
        'page_obj': page_obj,
        'page_range': get_page_range(page_obj),
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTIONS,
        'search_query': search_query,
        'search_field': search_field,
        'status_filter': status_filter,
        'can_manage_clients': can_manage_clients,
    }
    
    if is_htmx(request):
        response = render(request, 'index.html', context)
        return _apply_drawer_embed_frame_headers(request, response)

    response = render(request, 'index.html', context)
    return _apply_drawer_embed_frame_headers(request, response)


@login_required
@require_any_admin
def active_clients(request):
    """Legacy Active Clients URL kept for backlink compatibility.

    Redirects to Manage Clients while preserving supported query params.
    """
    allowed_search_fields = {'all', 'name', 'email', 'mobile'}
    allowed_status_filters = {'all', 'active', 'inactive', 'suspended'}

    query = request.GET.copy()
    search_field = (query.get('search_field') or '').strip().lower()
    status_filter = (query.get('status') or '').strip().lower()

    if search_field and search_field not in allowed_search_fields:
        query.pop('search_field', None)
    if status_filter and status_filter not in allowed_status_filters:
        query.pop('status', None)

    target_url = reverse('manage_clients')
    query_string = query.urlencode()
    if query_string:
        target_url = f"{target_url}?{query_string}"
    return redirect(target_url)


@login_required
@require_any_admin
@require_http_methods(['GET'])
def active_client_status_redirect(request, client_id, status):
    """Legacy deep-link for Active Clients status cards.

    Old links now land on Manage Clients with the selected client highlighted.
    """
    if not PermissionService.can_access_client(request.user, client_id):
        return redirect('manage_clients')

    query = request.GET.copy()
    query['highlight'] = str(client_id)

    normalized_status = (status or '').strip().lower()
    if normalized_status in ('active', 'inactive', 'suspended'):
        query['status'] = normalized_status

    target_url = reverse('manage_clients')
    query_string = query.urlencode()
    if query_string:
        target_url = f"{target_url}?{query_string}"
    return redirect(target_url)

@login_required
@require_any_admin
@require_http_methods(['GET'])
def api_client_login_history(request, client_id):
    """Return login/logout timeline for a single client in Manage Clients drawers."""
    client = get_object_or_404(Client.objects.select_related('user'), id=client_id)

    if not PermissionService.can_access_client(request.user, client.id):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)

    try:
        limit = int(request.GET.get('limit', 80))
    except (TypeError, ValueError):
        limit = 80
    limit = min(max(limit, 10), 200)

    logs_qs = (
        ActivityLog.objects
        .filter(user=client.user, action__in=['login', 'logout'])
        .order_by('-created_at')[:limit]
    )

    now = timezone.now()
    action_display_map = dict(ActivityLog.ACTION_CHOICES)
    device_snapshot = _active_device_snapshot(client.user_id)
    device_fingerprints = device_snapshot.get('fingerprints') or []

    events = [_serialize_login_history_event(entry, action_display_map, now) for entry in logs_qs]

    return JsonResponse({
        'success': True,
        'client': {
            'id': client.id,
            'name': client.name,
            'status': client.status,
        },
        'active_devices': len(device_fingerprints),
        'active_surface_counts': device_snapshot.get('surface_counts') or {'desktop': 0, 'mobile': 0},
        'device_fingerprints': device_fingerprints,
        'active_devices_info': device_snapshot.get('devices') or [],
        'events': events,
    })

@login_required
@require_any_admin
@require_http_methods(['GET'])
def api_client_staff_login_history(request, staff_id):
    """Return login/logout timeline for a single client staff user."""
    can_manage_client_staff = (
        PermissionService.is_super_admin(request.user)
        or PermissionService.has(request.user, 'perm_idcard_client_list')
        or PermissionService.has(request.user, 'perm_manage_client_staff')
    )
    if PermissionService.is_admin_staff(request.user) and not can_manage_client_staff:
        return JsonResponse({'success': False, 'message': 'Manage Assistent permission required'}, status=403)

    staff = get_object_or_404(
        Staff.objects.select_related('user', 'client'),
        id=staff_id,
        staff_type='client_staff',
    )

    if staff.client_id and not PermissionService.can_access_client(request.user, staff.client_id):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)

    try:
        limit = int(request.GET.get('limit', 80))
    except (TypeError, ValueError):
        limit = 80
    limit = min(max(limit, 10), 200)

    logs_qs = (
        ActivityLog.objects
        .filter(user=staff.user, action__in=['login', 'logout'])
        .order_by('-created_at')[:limit]
    )

    now = timezone.now()
    action_display_map = dict(ActivityLog.ACTION_CHOICES)
    device_snapshot = _active_device_snapshot(staff.user_id)
    device_fingerprints = device_snapshot.get('fingerprints') or []

    events = [_serialize_login_history_event(entry, action_display_map, now) for entry in logs_qs]

    staff_name = staff.user.get_full_name() or staff.user.username
    return JsonResponse({
        'success': True,
        'staff': {
            'id': staff.id,
            'name': staff_name,
            'status': 'active' if staff.user.is_active else 'inactive',
            'client_name': staff.client.name if staff.client_id else '',
        },
        'active_devices': len(device_fingerprints),
        'active_surface_counts': device_snapshot.get('surface_counts') or {'desktop': 0, 'mobile': 0},
        'device_fingerprints': device_fingerprints,
        'active_devices_info': device_snapshot.get('devices') or [],
        'events': events,
    })


@login_required
@require_any_admin
@require_http_methods(['GET'])
def api_client_staff_assignment_timeline(request, staff_id):
    """Return assignment-change timeline for a single client staff member."""
    can_manage_client_staff = (
        PermissionService.is_super_admin(request.user)
        or PermissionService.has(request.user, 'perm_idcard_client_list')
        or PermissionService.has(request.user, 'perm_manage_client_staff')
    )
    if PermissionService.is_admin_staff(request.user) and not can_manage_client_staff:
        return JsonResponse({'success': False, 'message': 'Manage Assistent permission required'}, status=403)

    staff = get_object_or_404(
        Staff.objects.select_related('user', 'client'),
        id=staff_id,
        staff_type='client_staff',
    )

    if staff.client_id and not PermissionService.can_access_client(request.user, staff.client_id):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)

    try:
        limit = int(request.GET.get('limit', 80))
    except (TypeError, ValueError):
        limit = 80
    limit = min(max(limit, 10), 200)

    from core.services.compat_service import CompatibilityService
    _, real_target_id = CompatibilityService.decode_id(staff.id)
    logs_qs = (
        ActivityLog.objects
        .filter(target_model='Staff', target_id__in=(staff.id, real_target_id))
        .filter(Q(action='staff_assignment') | Q(action='staff_update', description__icontains='assignment'))
        .select_related('user')
        .order_by('-created_at')[:limit]
    )

    now = timezone.now()
    action_display_map = dict(ActivityLog.ACTION_CHOICES)
    events = [_serialize_assignment_history_event(entry, action_display_map, now) for entry in logs_qs]

    staff_name = staff.user.get_full_name() or staff.user.username
    return JsonResponse({
        'success': True,
        'staff': {
            'id': staff.id,
            'name': staff_name,
            'status': 'active' if staff.user.is_active else 'inactive',
            'client_name': staff.client.name if staff.client_id else '',
        },
        'events': events,
    })


@require_super_admin
@require_http_methods(['GET'])
def api_staff_login_history(request, staff_id):
    """Return login/logout timeline for a single admin staff (operator)."""
    staff = get_object_or_404(
        Staff.objects.select_related('user'),
        id=staff_id,
        staff_type='admin_staff',
    )

    try:
        limit = int(request.GET.get('limit', 80))
    except (TypeError, ValueError):
        limit = 80
    limit = min(max(limit, 10), 200)

    logs_qs = (
        ActivityLog.objects
        .filter(user=staff.user, action__in=['login', 'logout'])
        .order_by('-created_at')[:limit]
    )

    now = timezone.now()
    action_display_map = dict(ActivityLog.ACTION_CHOICES)
    device_snapshot = _active_device_snapshot(staff.user_id)
    device_fingerprints = device_snapshot.get('fingerprints') or []

    events = [_serialize_login_history_event(entry, action_display_map, now) for entry in logs_qs]

    staff_name = staff.user.get_full_name() or staff.user.username
    return JsonResponse({
        'success': True,
        'staff': {
            'id': staff.id,
            'name': staff_name,
            'status': 'active' if staff.user.is_active else 'inactive',
        },
        'active_devices': len(device_fingerprints),
        'active_surface_counts': device_snapshot.get('surface_counts') or {'desktop': 0, 'mobile': 0},
        'device_fingerprints': device_fingerprints,
        'active_devices_info': device_snapshot.get('devices') or [],
        'events': events,
    })


@require_super_admin
@require_http_methods(['GET'])
def api_staff_assignment_timeline(request, staff_id):
    """Return assignment-change timeline for a single admin staff (operator)."""
    staff = get_object_or_404(
        Staff.objects.select_related('user'),
        id=staff_id,
        staff_type='admin_staff',
    )

    try:
        limit = int(request.GET.get('limit', 80))
    except (TypeError, ValueError):
        limit = 80
    limit = min(max(limit, 10), 200)

    from core.services.compat_service import CompatibilityService
    _, real_target_id = CompatibilityService.decode_id(staff.id)
    logs_qs = (
        ActivityLog.objects
        .filter(target_model='Staff', target_id__in=(staff.id, real_target_id))
        .filter(Q(action='staff_assignment') | Q(action='staff_update', description__icontains='assignment'))
        .select_related('user')
        .order_by('-created_at')[:limit]
    )

    now = timezone.now()
    action_display_map = dict(ActivityLog.ACTION_CHOICES)
    events = [_serialize_assignment_history_event(entry, action_display_map, now) for entry in logs_qs]

    staff_name = staff.user.get_full_name() or staff.user.username
    return JsonResponse({
        'success': True,
        'staff': {
            'id': staff.id,
            'name': staff_name,
            'status': 'active' if staff.user.is_active else 'inactive',
        },
        'events': events,
    })


# ID Card Group
@login_required
@require_any_admin
def idcard_group(request, client_id):
    """View ID card groups/tables for a specific client with status counts"""
    client = get_object_or_404(Client, id=client_id)
    
    # Check if user has access to this client
    user = request.user
    if not PermissionService.can_access_client(user, client_id):
        return redirect('manage_clients')
    
    # Get all tables for this client's groups with status counts
    tables = IDCardTable.objects.filter(group__client=client).select_related('group', 'group__client').annotate(
        pending_count=Count('id_cards', filter=Q(id_cards__status='pending')),
        verified_count=Count('id_cards', filter=Q(id_cards__status='verified')),
        pool_count=Count('id_cards', filter=Q(id_cards__status='pool')),
        approved_count=Count('id_cards', filter=Q(id_cards__status='approved')),
        download_count=Count('id_cards', filter=Q(id_cards__status='download')),

        total_cards=Count('id_cards')
    ).order_by('-updated_at')

    # Get default group for Create with XLSX button
    group = IDCardService.ensure_default_group(client)
    
    can_manage_clients = PermissionService.is_super_admin(user) or PermissionService.has(user, 'perm_idcard_client_list')
    context = {
        'active_page': 'manage_clients',
        'user_role': get_user_role(request.user),
        'client': client,
        'group': group,
        'tables': tables,
        'can_manage_clients': can_manage_clients,
    }
    return render(request, 'index.html', context)


# ────────────────────────────────────────────────────────────
# Shared helper: builds queryset + context for idcard-actions
# Used by admin idcard_actions() and client client_idcard_actions()
# ────────────────────────────────────────────────────────────
def build_idcard_actions_context(request, table, *, default_per_page=100,
                                  per_page_options=None, active_page='manage_clients',
                                  user_role=None):
    """Build the queryset, counts, and template context for idcard-actions.

    Returns a dict ready to be passed to ``render()``.  Caller is still
    responsible for access checks and redirect logic.
    """
    if per_page_options is None:
        per_page_options = [100, 200, 300, 400, 500]

    status_filter = request.GET.get('status', None)

    # ── Pagination params ──
    try:
        per_page = int(request.GET.get('per_page', default_per_page))
        if per_page not in per_page_options:
            per_page = default_per_page
    except (ValueError, TypeError):
        per_page = default_per_page

    search_query = request.GET.get('search', '').strip()
    class_filter = request.GET.get('class', '').strip()
    section_filter = request.GET.get('section', '').strip()
    course_filter = request.GET.get('course', '').strip()
    branch_filter = request.GET.get('branch', '').strip()

    # ── Base queryset — newest action first in each status list ──
    # Pending/Verified/Approved/Reprint are sorted by last status movement,
    # with created_at fallback for legacy rows where status_changed_at is null.
    from django.db.models.functions import Coalesce
    if status_filter == 'download':
        id_cards_query = IDCard.objects.filter(table=table).order_by('-downloaded_at', '-id')
    elif status_filter == 'pool':
        id_cards_query = IDCard.objects.filter(table=table).order_by('-deleted_at', '-id')
    else:
        id_cards_query = (
            IDCard.objects
            .filter(table=table)
            .annotate(_status_sort_at=Coalesce('status_changed_at', 'created_at'))
            .order_by('-_status_sort_at', '-id')
        )
    if status_filter and status_filter in _VALID_STATUSES:
        id_cards_query = id_cards_query.filter(status=status_filter)

    # Enforce client_staff data partitioning by group/class/section/branch.
    # Pool list is intentionally unscoped for class/section/branch visibility.
    id_cards_query = _apply_client_staff_row_scope(
        id_cards_query,
        request.user,
        table,
        status_filter=status_filter,
    )

    # ── Search ──
    if search_query:
        id_cards_query = IDCardService._apply_search_filter(id_cards_query, search_query, table=table)

    # ── Class/section/course/branch filters ──
    if class_filter or section_filter or course_filter or branch_filter:
        from django.db.models.fields.json import KeyTextTransform
        class_field_name, section_field_name, course_field_name, branch_field_name = (
            _get_class_section_course_branch_field_names(table)
        )
        if class_filter and class_field_name:
            id_cards_query = _build_class_filter_q(id_cards_query, class_filter, class_field_name)
        if section_filter and section_field_name:
            id_cards_query = id_cards_query.annotate(
                _sec=KeyTextTransform(section_field_name, 'field_data')
            ).filter(_sec__iexact=section_filter)
        if course_filter and course_field_name:
            id_cards_query = id_cards_query.annotate(
                _course=KeyTextTransform(course_field_name, 'field_data')
            ).filter(_course__iexact=course_filter)
        if branch_filter and branch_field_name:
            id_cards_query = id_cards_query.annotate(
                _branch=KeyTextTransform(branch_field_name, 'field_data')
            ).filter(_branch__iexact=branch_filter)

    # ── Date range (download only) ──
    from_date = request.GET.get('from', '').strip()
    to_date = request.GET.get('to', '').strip()
    if status_filter == 'download':
        from datetime import datetime as dt
        if from_date:
            try:
                from_dt = dt.fromisoformat(from_date)
                from_dt = timezone.make_aware(from_dt) if timezone.is_naive(from_dt) else from_dt
                id_cards_query = id_cards_query.filter(downloaded_at__gte=from_dt)
            except (ValueError, TypeError):
                pass
        if to_date:
            try:
                to_dt = dt.fromisoformat(to_date)
                to_dt = timezone.make_aware(to_dt) if timezone.is_naive(to_dt) else to_dt
                id_cards_query = id_cards_query.filter(downloaded_at__lte=to_dt)
            except (ValueError, TypeError):
                pass

    total_count = id_cards_query.count()
    # Default counts for all non-client-staff roles.
    # Client staff get a scoped count set below so the tabs match their row scope.
    status_counts = IDCardService.get_status_counts(table)

    if PermissionService.is_client_staff(request.user):
        scoped_cards_qs = _apply_client_staff_row_scope(
            IDCard.objects.filter(table=table),
            request.user,
            table,
        )
        status_counts = {
            'pending': 0,
            'verified': 0,
            'pool': 0,
            'approved': 0,
            'download': 0,
            'total': 0,
        }
        for row in scoped_cards_qs.values('status').annotate(count=Count('id')):
            st = row.get('status')
            ct = row.get('count', 0)
            if st in status_counts:
                status_counts[st] = ct
                status_counts['total'] += ct

        status_counts['pool'] = IDCard.objects.filter(table=table, status='pool').count()
        status_counts['total'] = (
            status_counts.get('pending', 0)
            + status_counts.get('verified', 0)
            + status_counts.get('pool', 0)
            + status_counts.get('approved', 0)
            + status_counts.get('download', 0)
        )


    return {
        'active_page': active_page,
        'user_role': user_role or get_user_role(request.user),
        'table': table,
        'group': table.group,
        'client': table.group.client,
        'id_cards': [],
        'current_status': status_filter,
        'status_counts': status_counts,

        'total_count': total_count,
        'has_more': True,
        'initial_load_limit': per_page,
        'page_obj': None,
        'page_range': [],
        'per_page': per_page,
        'per_page_options': per_page_options,
        'search_query': search_query,
        'class_filter': class_filter,
        'section_filter': section_filter,
        'course_filter': course_filter,
        'branch_filter': branch_filter,
        'from_date': from_date,
        'to_date': to_date,
    }


# ID Card Actions
@login_required
@require_any_admin
def idcard_actions(request, table_id):
    """View and manage ID cards in a table — returns React SPA shell.

    The React SPA (IDCardActionsView.jsx) fetches all card data via REST API.
    Query params (status, page, per_page, search, class, section, etc.) are
    handled entirely on the frontend.
    """
    table = get_object_or_404(IDCardTable.objects.select_related('group__client'), id=table_id)
    user = request.user
    if not PermissionService.can_access_client(user, table.group.client_id):
        return redirect('manage_clients')

    context = {
        'active_page': 'manage_clients',
        'user_role': get_user_role(user),
        'table_id': table.id,
    }
    return render(request, 'index.html', context)


# Group Settings
@login_required
@require_any_admin
def group_settings(request, client_id):
    """Settings for a specific client — manage their groups and tables."""
    client = get_object_or_404(Client, id=client_id)
    user = request.user
    if not PermissionService.can_access_client(user, client_id):
        return redirect('manage_clients')

    search_query = request.GET.get('search', '').strip()

    group = IDCardService.ensure_default_group(client)
    tables_qs = IDCardTable.objects.filter(group=group).select_related('group').annotate(
        total_cards=Count('id_cards')
    ).order_by('-created_at')

    if search_query:
        tables_qs = tables_qs.filter(name__icontains=search_query)

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

    can_manage_clients = PermissionService.is_super_admin(user) or PermissionService.has(user, 'perm_idcard_client_list')
    context = {
        'active_page': 'manage_clients',
        'user_role': get_user_role(request.user),
        'client': client,
        'group': group,
        'tables': page_obj.object_list,
        'page_obj': page_obj,
        'page_range': get_page_range(page_obj),
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTIONS,
        'search_query': search_query,
        'can_manage_clients': can_manage_clients,
    }

    if is_htmx(request):
        return render(request, 'index.html', context)

    return render(request, 'index.html', context)


from panel.views.manage_panel_views import (  # noqa: F401
    notifications_page,
    manage_panel,
    api_email_logs,
    api_email_resend,
    api_email_send_new,
    api_email_compose_defaults,
)


@login_required
def settings(request):
    """User settings/profile view - accessible by all user types"""
    context = {
        'active_page': 'settings',
        'user_role': get_user_role(request.user),
    }
    return render(request, 'index.html', context)


def _resolve_tutorial_scope(user):
    """Return the tutorial content scope key for the logged-in user role."""
    role = str(getattr(user, 'role', '') or '').strip().lower()
    if role == 'client_staff':
        return 'client_staff'
    if role == 'admin_staff':
        return 'admin_staff'
    if role in ('super_admin', 'pro_user'):
        return 'admin'
    return 'client'


def _resolve_tutorial_video_url(scope):
    """Resolve role-specific tutorial video URL with client URL fallback."""
    client_url = getattr(django_settings, 'CLIENT_TUTORIAL_VIDEO_URL', 'https://www.youtube.com/')
    if scope == 'client_staff':
        return getattr(django_settings, 'CLIENT_STAFF_TUTORIAL_VIDEO_URL', client_url)
    if scope == 'admin_staff':
        return getattr(django_settings, 'ADMIN_STAFF_TUTORIAL_VIDEO_URL', client_url)
    if scope == 'admin':
        return getattr(django_settings, 'ADMIN_TUTORIAL_VIDEO_URL', client_url)
    return client_url


@login_required
def tutorial(request):
    """Role-aware tutorial and usage guide page."""
    tutorial_lang = str(request.GET.get('lang', 'en')).strip().lower()
    if tutorial_lang not in ('en', 'hi'):
        tutorial_lang = 'en'
    tutorial_scope = _resolve_tutorial_scope(request.user)

    context = {
        'active_page': 'tutorial',
        'user_role': get_user_role(request.user),
        'tutorial_scope': tutorial_scope,
        'tutorial_video_url': _resolve_tutorial_video_url(tutorial_scope),
        'tutorial_lang': tutorial_lang,
    }
    return render(request, 'index.html', context)


@login_required
def tutorial_personal_guide(request):
    """Formatted personal guide page for client operations and sharing."""
    tutorial_lang = str(request.GET.get('lang', 'hi')).strip().lower()
    if tutorial_lang not in ('en', 'hi'):
        tutorial_lang = 'hi'

    tutorial_scope = _resolve_tutorial_scope(request.user)
    personal_guide_share_url = request.build_absolute_uri(reverse('tutorial_personal_guide'))

    context = {
        'active_page': 'tutorial',
        'user_role': get_user_role(request.user),
        'tutorial_scope': tutorial_scope,
        'tutorial_lang': tutorial_lang,
        'personal_guide_share_url': personal_guide_share_url,
        'personal_guide_download_url': reverse('tutorial_personal_guide_download'),
        'can_share_personal_guide': tutorial_scope == 'admin',
    }
    return render(request, 'index.html', context)


@login_required
def tutorial_personal_guide_download(request):
    """Download Personal Guide as plain text for admin/client sharing."""
    personal_guide_share_url = request.build_absolute_uri(reverse('tutorial_personal_guide'))
    response = HttpResponse(
        _build_personal_guide_text(personal_guide_share_url),
        content_type='text/plain; charset=utf-8',
    )
    response['Content-Disposition'] = 'attachment; filename="adarsh-personal-guide.txt"'
    return response
