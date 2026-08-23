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

from organisation.models import Organisation
from operators.models import Operator
from staff.models import Staff
from accounts.services import AuthService
from tables.models import Table, IDCard
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
        "email id: Organisation.demo@example.com",
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



@login_required
@require_any_admin
@require_http_methods(['GET'])
def api_client_login_history(request, client_id):
    """Return login/logout timeline for a single client in Manage Clients drawers."""
    client = get_object_or_404(Organisation.objects.select_related('user'), id=client_id)

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
            'id': Organisation.id,
            'name': Organisation.name,
            'status': Organisation.status,
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
        or PermissionService.has(request.user, 'perm_manage_assistant')
    )
    if PermissionService.is_admin_staff(request.user) and not can_manage_client_staff:
        return JsonResponse({'success': False, 'message': 'Manage Assistent permission required'}, status=403)

    staff = get_object_or_404(
        Staff.objects.select_related('user', 'client'),
        id=staff_id,
        staff_type='assistant',
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
        or PermissionService.has(request.user, 'perm_manage_assistant')
    )
    if PermissionService.is_admin_staff(request.user) and not can_manage_client_staff:
        return JsonResponse({'success': False, 'message': 'Manage Assistent permission required'}, status=403)

    staff = get_object_or_404(
        Staff.objects.select_related('user', 'client'),
        id=staff_id,
        staff_type='assistant',
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
        staff_type='operator',
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
        staff_type='operator',
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


from panel.views.manage_panel_views import (  # noqa: F401
    api_email_logs,
    api_email_resend,
    api_email_retry_single,
    api_email_retry_all_failed,
    api_email_send_new,
    api_email_compose_defaults,
)


def _resolve_tutorial_scope(user):
    """Return the tutorial content scope key for the logged-in user role."""
    role = str(getattr(user, 'role', '') or '').strip().lower()
    if role == 'assistant':
        return 'client_staff'
    if role == 'operator':
        return 'operator'
    if role in ('super_admin', 'pro_user'):
        return 'admin'
    return 'client'


def _resolve_tutorial_video_url(scope):
    """Resolve role-specific tutorial video URL with client URL fallback."""
    client_url = getattr(django_settings, 'CLIENT_TUTORIAL_VIDEO_URL', 'https://www.youtube.com/')
    if scope == 'assistant':
        return getattr(django_settings, 'CLIENT_STAFF_TUTORIAL_VIDEO_URL', client_url)
    if scope == 'operator':
        return getattr(django_settings, 'ADMIN_STAFF_TUTORIAL_VIDEO_URL', client_url)
    if scope == 'admin':
        return getattr(django_settings, 'ADMIN_TUTORIAL_VIDEO_URL', client_url)
    return client_url


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
