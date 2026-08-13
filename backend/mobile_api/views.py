"""
PWA Mobile App Views â€” real backend integration.

All views enforce:
  1. Login required
  2. Valid role (super_admin, admin_staff, client, client_staff)
  3. Mobile device user-agent (desktop gets block page)

No new backend logic â€” delegates entirely to existing services.
"""
import json
import re
import logging
import time
APP_BOOT_TS = time.time()
import hashlib
from datetime import timedelta
from functools import wraps
import logging

logger = logging.getLogger(__name__)

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.timezone import make_aware, is_naive, localtime
from django.utils import timezone

from django.db import transaction
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.utils.timesince import timesince
from django.db.models import Q, Count, Max, Min, F, Sum, Avg, CharField
from django.db.models.functions import Cast, Coalesce
from django.db.models.fields.json import KeyTextTransform
from django.core.cache import cache
from urllib.parse import urlencode
from operators.models import Operator
from assistants.models import Assistant
from core.models import Photographer
from mediafiles.utils import get_card_photo_url
from tables.models import IDCard, Table
from organisation.models import Organisation

from staff.models import Staff


MAX_REPRINT_ACTION_IDS = 200

from organisation.services import (
    OrganisationAccessService,
    OrganisationDashboardService,
    OrganisationCardService,
    OrganisationImageService,
    OrganisationStaffService,
)
from core.services.permission_service import PermissionService
from tables.models import Table, IDCard
from reprintcard.models import ReprintRequest
from mediafiles.utils import get_card_photo_url, normalize_uploaded_image
from accounts.rate_limit import rate_limit, _get_client_ip
from accounts.services import AuthService
from mediafiles.services import ImageService, ThumbnailService
from core.services.activity_service import ActivityService
from core.services.cache_version_service import CacheVersionService
from core.services import StaffService, IDCardService, ClientService
from core.utils.field_utils import (
    normalize_class_value,
    normalize_compact_text_value,
    CLASS_ORDER,
    CLASS_ORDER_UNKNOWN,
)

MAX_SEARCH_QUERY_LEN = 100
MAX_GLOBAL_SEARCH_DB_SCAN = 100
MOBILE_CLIENT_EDIT_LOCK_STATUSES = frozenset({'pool', 'deleted'})
MOBILE_INSTALLATION_ID_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._:-]{7,79}$')
MOBILE_SORT_MODES = frozenset({'sr-asc', 'name-asc', 'name-desc'})


def _normalize_mobile_sort_mode(value):
    normalized = str(value or '').strip().lower()
    if normalized in MOBILE_SORT_MODES:
        return normalized
    return 'sr-asc'


def _mobile_field_token(field_name):
    # simplified token generation (direct regex)
    name = str(field_name or '').lower()
    # replace non-alphanum/underscore with underscores, collapse multiple underscores, strip edges
    name = re.sub(r'[^a-z0-9_]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name


def _has_meaningful_field_value(value):
    if not value:
        return False
    val_str = str(value).strip()
    if val_str.upper() in ('', 'NULL', 'NONE', 'N/A', 'NA', 'N.A.', '-'):
        return False
    if val_str.startswith('PENDING:'):
        return False
    return True


def _get_field_value_case_insensitive(field_data, field_name):
    return OrganisationCardService._get_field_value_case_insensitive(field_data, field_name)


def _rel_photo_slot_for_name(name):
    name_lower = str(name or '').lower()
    if 'father' in name_lower:
        return 'father'
    if 'mother' in name_lower:
        return 'mother'
    if 'student' in name_lower or 'photo' in name_lower or 'image' in name_lower:
        return 'student'
    return None


def _rel_photo_aliases_for_slot(slot):
    if slot == 'father':
        return ['father_photo', 'father photo', 'father image', 'father_image', 'father']
    if slot == 'mother':
        return ['mother_photo', 'mother photo', 'mother image', 'mother_image', 'mother']
    if slot == 'student':
        return ['photo', 'student_photo', 'student photo', 'student_image', 'student image', 'image']
    return []
def _safe_file_url(file_field, request=None):
    """Safely get URL from an ImageField/FileField and prefer absolute URLs for external clients."""
    if not file_field:
        return ''
    try:
        url = file_field.url
    except ValueError:
        return ''

    if not url:
        return ''

    # Prefer absolute URLs for external clients if a base is configured.
    base = str(getattr(settings, 'WEBSITE_URL', '') or getattr(settings, 'SITE_URL', '') or '').strip().rstrip('/')
    if base and not url.startswith(('http://', 'https://')):
        if not url.startswith('/'):
            url = f'/{url}'
        return f'{base}{url}'

    return url


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def is_mobile(request):
    """Check if request comes from a mobile device or native app."""
    ua = request.META.get('HTTP_USER_AGENT', '')
    # Expanded regex to include 'Adarsh' (custom) and 'okhttp' (standard Android networking)
    return bool(re.search(
        r'Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Adarsh|okhttp',
        ua, re.I,
    ))

def _truthy(value):
    """Convert value to boolean, handling strings like 'true', '1', 'yes'."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'y', 't')
    return bool(value)


def require_mobile_client(view_func=None, allow_public=False):
    """
    Decorator for mobile-aware views.
    - If allow_public=True: Only ensures valid Mobile UA (in production).
    - If allow_public=False: Also ensures user is authenticated & mobile-auth-ok.
    Returns 401/403 JSON for API requests; redirects to PWA login for others.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(request, *args, **kwargs):
            is_api_request = (request.path or '').startswith('/api/mobile/')
            ua = request.META.get('HTTP_USER_AGENT', '')

            # 1. Enforce mobile user-agent in production
            if not getattr(settings, 'DEBUG', False) and not is_mobile(request):
                if is_api_request:
                    return JsonResponse({'success': False, 'message': 'Invalid client source.'}, status=403)
                return redirect('/app/no-access/?reason=invalid-source')

            if allow_public:
                return f(request, *args, **kwargs)

            # 2. Enforce Authentication
            if not request.user.is_authenticated:
                session_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
                if session_key:
                    from django.core.cache import cache
                    if cache.get(f'concurrent_logout:{session_key}'):
                        if is_api_request:
                            return JsonResponse({
                                'success': False,
                                'logged_in_elsewhere': True,
                                'message': 'logged_in_elsewhere'
                            }, status=401)
                        return redirect('/app/login/?reason=logged_in_elsewhere')

                if is_api_request:
                    return JsonResponse({'success': False, 'authenticated': False, 'message': 'Authentication required'}, status=401)
                return redirect('/app/login/')

            # 3. Enforce Mobile Auth OK (Session flag)
            if not request.session.get('mobile_auth_ok'):
                if is_api_request:
                    return JsonResponse({'success': False, 'mobile_auth_required': True, 'message': 'Session checkpoint required'}, status=401)
                return redirect('/app/login/')

            # 4. Enforce valid roles
            user = request.user
            valid_roles = ('pro_user', 'super_admin', 'operator', 'prime_manager', 'manager', 'guest_prime_manager', 'assistant', 'photographer')
            if not hasattr(user, 'role') or user.role not in valid_roles:
                if is_api_request:
                    return JsonResponse({'success': False, 'message': 'Invalid account role.'}, status=403)
                return redirect('/app/login/')

            return f(request, *args, **kwargs)
        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator



def _get_notification_count(user):
    """Return unread notification count for the mobile bell badge (capped at 99)."""
    try:
        _, unread_count = _get_system_notifications(
            user,
            limit=100,
            mark_visible_as_read=False,
        )
        return min(unread_count, 99)
    except Exception:
        return 0


def _is_mobile_client_edit_locked(user, card_status):
    """Client/client_staff cannot edit cards in specific locked statuses on mobile."""
    return getattr(user, 'role', '') in ('prime_manager', 'manager') and card_status in MOBILE_CLIENT_EDIT_LOCK_STATUSES


def _mobile_client_edit_locked_response():
    """Standard 403 payload for mobile edit lock violations."""
    return JsonResponse(
        {'success': False, 'message': 'Cards in pool status cannot be edited by client users.'},
        status=403,
    )


def _can_access_card_with_row_scope(user, card):
    """Enforce card ownership plus client_staff row-level scope restrictions."""
    if not OrganisationAccessService.can_access_card(user, card):
        return False

    if not PermissionService.is_client_staff(user):
        return True

    scoped = OrganisationCardService._apply_client_staff_row_scope(
        user,
        card.table,
        IDCard.objects.filter(id=card.id, table_id=card.table_id),
    )
    return scoped.exists()


def _mobile_search_allowed_statuses(user):
    """Return card statuses visible to the user in mobile list/search surfaces."""
    status_perm_map = getattr(PermissionService, 'STATUS_LIST_PERM_MAP', {}) or {}
    allowed = []
    for status, perm_key in status_perm_map.items():
        if not perm_key or PermissionService.has(user, perm_key):
            allowed.append(status)
    return allowed


def _apply_mobile_search_status_scope(user, qs):
    """Limit search queryset to statuses the user can actually open on mobile."""
    if PermissionService.is_super_admin(user):
        return qs

    allowed_statuses = _mobile_search_allowed_statuses(user)
    if not allowed_statuses:
        return qs.none()
    return qs.filter(status__in=allowed_statuses)


def _filter_cards_for_client_staff_row_scope(user, cards):
    """Batch-filter search cards by client_staff row scope table-by-table."""
    cards_list = list(cards or [])
    if not PermissionService.is_client_staff(user):
        return cards_list
    if not cards_list:
        return cards_list

    grouped_by_table = {}
    for card in cards_list:
        table_id = getattr(card, 'table_id', None)
        card_id = getattr(card, 'id', None)
        table_obj = getattr(card, 'table', None)
        if not table_id or not card_id or table_obj is None:
            continue

        table_key = int(table_id)
        bucket = grouped_by_table.setdefault(table_key, {'table': table_obj, 'card_ids': []})
        bucket['card_ids'].append(int(card_id))

    allowed_ids = set()
    for table_id, payload in grouped_by_table.items():
        scoped_qs = OrganisationCardService._apply_client_staff_row_scope(
            user,
            payload['table'],
            IDCard.objects.filter(table_id=table_id, id__in=payload['card_ids']),
        )
        allowed_ids.update(scoped_qs.values_list('id', flat=True))

    return [card for card in cards_list if int(getattr(card, 'id', 0) or 0) in allowed_ids]


def _get_system_notifications(user, limit=20, mark_visible_as_read=False):
    """Return system notifications for a user with consistent unread tracking."""
    from core.models import Notification, NotificationRead
    from django.db.models import Q as _Q
    from django.utils import timezone as _tz

    role = getattr(user, 'role', 'all') or 'all'
    safe_limit = max(1, min(int(limit or 20), 100))
    now = _tz.now()

    notifications = list(
        Notification.objects
        .filter(is_active=True, client_message__isnull=True)
        .filter(_Q(expires_at__isnull=True) | _Q(expires_at__gt=now))
        .filter(_Q(target='all') | _Q(target=role) | _Q(target='selected', target_users=user))
        .distinct()
        .order_by('-created_at')[:safe_limit]
    )

    if not notifications:
        return [], 0

    notif_ids = [n.id for n in notifications]
    read_ids = set(
        NotificationRead.objects
        .filter(user=user, notification_id__in=notif_ids)
        .values_list('notification_id', flat=True)
    )

    if mark_visible_as_read:
        unread_ids = [nid for nid in notif_ids if nid not in read_ids]
        if unread_ids:
            NotificationRead.objects.bulk_create(
                [NotificationRead(user=user, notification_id=nid) for nid in unread_ids],
                ignore_conflicts=True,
            )
            read_ids.update(unread_ids)
            cache.delete(f'mobile:notif_count:{user.pk}')

    items = [
        {
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'priority': n.priority,
            'priority_color': n.priority_color,
            'category': n.get_category_display(),
            'icon_class': n.icon_class,
            'created_at': n.created_at.strftime('%d %b %Y'),
            'is_read': n.id in read_ids,
        }
        for n in notifications
    ]

    unread_count = sum(1 for n in items if not n['is_read'])
    return items, unread_count


def _map_role_compat(role_str):
    """Translate operator/assistant to admin_staff/client_staff for mobile app compatibility."""
    from core.services.compat_service import CompatibilityService
    return CompatibilityService.map_role_to_legacy(role_str)


def _client_ctx(user):
    """Return (client, permissions_dict) for the current user.
    For admin roles (super_admin/admin_staff) that have no client profile,
    returns a scoped fallback client so PWA views can function.
    """
    client = OrganisationAccessService.get_organisation_for_user(user)
    if client is None and PermissionService.is_super_admin(user):
        # Super admin can access all clients â€” pick the first active one
        from organisation.models import Organisation
        client = Organisation.objects.filter(status='active').first()
    elif client is None and (PermissionService.is_admin_staff(user) or PermissionService.is_photographer(user)):
        # Admin staff/photographer fallback must stay within assigned-client scope
        from organisation.models import Organisation
        accessible_ids = PermissionService.get_accessible_client_ids(user)
        if accessible_ids:
            client = Organisation.objects.filter(id__in=accessible_ids, status='active').first()
    perms = PermissionService.get_permission_context(user)
    return client, perms


def _mobile_no_client_redirect():
    """Single redirect target when mobile session has no client context."""
    return redirect('/app/no-access/?reason=no-client-context')


def _can_manage_clients_surface(user):
    """Return True when user can use Manage Client actions."""
    if PermissionService.is_super_admin(user):
        return True
    if PermissionService.is_admin_staff(user):
        return PermissionService.has(user, 'perm_idcard_client_list')
    return PermissionService.has(user, 'perm_idcard_client_list')


def _can_manage_client_staff_surface(user):
    """Return True when user can manage client staff."""
    if PermissionService.is_super_admin(user):
        return True
    if PermissionService.is_admin_staff(user):
        return PermissionService.has(user, 'perm_manage_assistant') or PermissionService.has(user, 'perm_idcard_client_list')
    # Clients can manage their own staff only if they have the manage_client_staff permission
    if PermissionService.is_client(user):
        return PermissionService.has(user, 'perm_manage_assistant') or PermissionService.has(user, 'perm_idcard_client_list')
    return False


_AACI_SENTINEL = object()  # sentinel for _admin_accessible_client_ids cache


def _admin_accessible_client_ids(user):
    """Return admin-scoped client IDs, or None for super_admin (all clients).

    Performance: caches the result on the user object so repeated calls
    within the same request don't trigger additional M2M queries.
    """
    _cache_attr = '_cached_accessible_client_ids'
    cached = getattr(user, _cache_attr, _AACI_SENTINEL)
    if cached is not _AACI_SENTINEL:
        return cached

    if PermissionService.is_super_admin(user):
        result = None
    elif PermissionService.is_admin_staff(user) or PermissionService.is_photographer(user):
        result = PermissionService.get_accessible_client_ids(user)
        # Defensive fallback: if cached scope is empty but staff has assignments,
        # read directly from assignments to avoid temporary stale-zero dashboards.
        if not result:
            staff = getattr(user, 'staff_profile', None)
            if staff is not None:
                if PermissionService.is_photographer(user):
                    from django.utils import timezone
                    from django.db.models import Q
                    now = timezone.now()
                    result = list(
                        staff.photographer_assignments.filter(
                            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
                        ).values_list('client_id', flat=True)
                    )
                else:
                    result = list(staff.assigned_organisations.values_list('id', flat=True))
    else:
        result = []

    setattr(user, _cache_attr, result)
    return result


def _image_path_basename(value):
    """Return a normalized basename from a stored media path-like value."""
    raw = str(value or '').strip()
    if not raw or raw == 'NOT_FOUND' or raw.startswith('PENDING:'):
        return ''
    cleaned = raw.replace('\\', '/').split('?', 1)[0].split('#', 1)[0]
    return cleaned.rsplit('/', 1)[-1]


def _search_cards_for_global_results(base_qs, query, limit=50, filter_type='all'):
    """Desktop-parity card matching for mobile global search.

    Uses a broad DB prefilter and then validates matches field-by-field so
    mobile search behaves like desktop global search for dynamic table fields.
    """
    if not query or len(query) < 2:
        return []

    query_upper = query.upper()
    active_filter = str(filter_type or 'all').strip().lower()
    if active_filter not in ('all', 'name', 'address', 'mobile'):
        active_filter = 'all'
    image_field_types = {'photo', 'rel_photo', 'mother_photo', 'father_photo', 'image', 'signature'}
    non_searchable_field_types = {'file', 'barcode', 'qr_code'}
    non_searchable_name_tokens = ('BARCODE', 'QR', 'FILE')

    cards = base_qs.filter(field_data__icontains=query)[:MAX_GLOBAL_SEARCH_DB_SCAN]
    matched_cards = []

    for card in cards:
        field_data = card.field_data or {}
        if not isinstance(field_data, dict):
            continue

        field_type_by_name = {}
        table_fields = getattr(card.table, 'fields', None)
        if isinstance(table_fields, list):
            for field in table_fields:
                if not isinstance(field, dict):
                    continue
                field_name = str(field.get('name', '')).strip().upper()
                if not field_name:
                    continue
                field_type_by_name[field_name] = str(field.get('type', 'text')).strip().lower()

        matched = False
        for field_name, field_value in field_data.items():
            if field_value in (None, ''):
                continue

            field_name_upper = str(field_name).upper()
            field_type = field_type_by_name.get(field_name_upper, '')

            is_image_field = (
                field_type in image_field_types
                or ((not field_type) and ('PHOTO' in field_name_upper or 'IMAGE' in field_name_upper or 'SIGN' in field_name_upper))
            )
            if is_image_field:
                if active_filter != 'all':
                    continue
                image_basename = _image_path_basename(field_value)
                if image_basename and query_upper in image_basename.upper():
                    matched = True
                    break
                continue

            if field_type in non_searchable_field_types:
                continue
            if (not field_type) and any(token in field_name_upper for token in non_searchable_name_tokens):
                continue

            if active_filter != 'all':
                if active_filter == 'name' and 'NAME' not in field_name_upper:
                    continue
                if active_filter == 'address' and 'ADDRESS' not in field_name_upper:
                    continue
                if active_filter == 'mobile' and ('MOBILE' not in field_name_upper and 'PHONE' not in field_name_upper and 'MOB' not in field_name_upper):
                    continue

            if query_upper in str(field_value).upper():
                matched = True
                break

        if not matched:
            continue

        matched_cards.append(card)
        if len(matched_cards) >= limit:
            break

    return matched_cards


def _card_display_name(card, field_data):
    """Return user-facing card name with table-aware fallback."""
    for key in ('NAME', 'name', 'Name'):
        value = (field_data or {}).get(key)
        if value:
            return str(value)

    table_fields = getattr(card.table, 'fields', None)
    if isinstance(table_fields, list):
        for field in table_fields:
            if not isinstance(field, dict):
                continue
            if str(field.get('type', 'text')).strip().lower() not in ('text', 'textarea'):
                continue
            fname = field.get('name')
            if not fname:
                continue
            value = (field_data or {}).get(fname)
            if value:
                return str(value)

    return f'Card #{card.id}'


def _sanitize_search_query(value, max_len=MAX_SEARCH_QUERY_LEN):
    """Trim and cap user-provided search strings to keep scans bounded."""
    return str(value or '').strip()[:max_len]


def _normalize_positive_int_ids(values):
    """Normalize mixed input to unique positive integer IDs."""
    if not isinstance(values, list):
        return []

    normalized = []
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
        normalized.append(number)
    return normalized


def _dedupe_scope_values(values):
    """Normalize filter values preserving first-seen order."""
    out = []
    seen = set()
    for value in values or []:
        text = str(value).strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(text)
    return out



def _get_table_filter_metadata(table, table_fields, user=None):
    """Build class/section filter metadata for list page."""
    class_field_name = None
    section_field_name = None
    for _f in table_fields:
        _fname = str(_f.get('name', '')).strip()
        _ftype = str(_f.get('type', '')).strip().lower()
        if not _fname:
            continue
        if class_field_name is None and (_ftype == 'class' or _fname.lower() == 'class'):
            class_field_name = _fname
        if section_field_name is None and (_ftype == 'section' or _fname.lower() == 'section'):
            section_field_name = _fname

    options_qs = IDCard.objects.filter(table=table)
    
    # Apply client_staff row-level scope if applicable
    if user and PermissionService.is_client_staff(user):
        options_qs = OrganisationCardService._apply_client_staff_row_scope(
            user, table, options_qs, ignore_pool_bypass=True
        )

    all_classes = []
    if class_field_name:
        all_classes = sorted(
            [
                str(v) for v in options_qs
                .annotate(_cv=Cast(KeyTextTransform(class_field_name, 'field_data'), CharField()))
                .exclude(_cv__isnull=True)
                .exclude(_cv='')
                .order_by()
                .values_list('_cv', flat=True)
                .distinct()
                if v is not None
            ],
        )

    all_sections = []
    if section_field_name:
        all_sections = sorted(
            [
                str(v) for v in options_qs
                .annotate(_sv=Cast(KeyTextTransform(section_field_name, 'field_data'), CharField()))
                .exclude(_sv__isnull=True)
                .exclude(_sv='')
                .order_by()
                .values_list('_sv', flat=True)
                .distinct()
                if v is not None
            ],
        )

    fallback_classes = set(all_classes)
    fallback_sections = set(all_sections)
    class_to_sections = {}

    for _card in options_qs.only('field_data').iterator(chunk_size=500):
        _fd = _card.field_data or {}

        _cls = ''
        _sec = ''
        if class_field_name:
            _cls = str(_fd.get(class_field_name, '') or '').strip()
        if section_field_name:
            _sec = str(_fd.get(section_field_name, '') or '').strip()

        if not _cls:
            _cls = str(_fd.get('CLASS') or _fd.get('class') or _fd.get('DESIGNATION') or '').strip()
        if not _sec:
            _sec = str(_fd.get('SECTION') or _fd.get('section') or '').strip()

        if not all_classes and _cls:
            fallback_classes.add(_cls)
        if not all_sections and _sec:
            fallback_sections.add(_sec)

        if _cls:
            if _cls not in class_to_sections:
                class_to_sections[_cls] = set()
            if _sec:
                class_to_sections[_cls].add(_sec)

    if not all_classes:
        all_classes = sorted(fallback_classes)
    if not all_sections:
        all_sections = sorted(fallback_sections)

    payload = {
        'all_classes': all_classes,
        'all_sections': all_sections,
        'class_to_sections': {
            _cls: sorted(list(_sections))
            for _cls, _sections in class_to_sections.items()
        },
    }
    return payload


def _build_filter_metadata_from_queryset(cards_qs, class_field_name=None, section_field_name=None):
    """Build class/section filter metadata from an already filtered queryset."""
    all_classes = []
    if class_field_name:
        all_classes = sorted(
            [
                str(v) for v in cards_qs
                .annotate(_cv=Cast(KeyTextTransform(class_field_name, 'field_data'), CharField()))
                .exclude(_cv__isnull=True)
                .exclude(_cv='')
                .order_by()
                .values_list('_cv', flat=True)
                .distinct()
                if v is not None
            ],
        )

    all_sections = []
    if section_field_name:
        all_sections = sorted(
            [
                str(v) for v in cards_qs
                .annotate(_sv=Cast(KeyTextTransform(section_field_name, 'field_data'), CharField()))
                .exclude(_sv__isnull=True)
                .exclude(_sv='')
                .order_by()
                .values_list('_sv', flat=True)
                .distinct()
                if v is not None
            ],
        )

    fallback_classes = set(all_classes)
    fallback_sections = set(all_sections)
    class_to_sections = {}

    for _card in cards_qs.only('field_data').iterator(chunk_size=500):
        _fd = _card.field_data or {}

        _cls = ''
        _sec = ''
        if class_field_name:
            _cls = str(_fd.get(class_field_name, '') or '').strip()
        if section_field_name:
            _sec = str(_fd.get(section_field_name, '') or '').strip()

        if not _cls:
            _cls = str(_fd.get('CLASS') or _fd.get('class') or _fd.get('DESIGNATION') or '').strip()
        if not _sec:
            _sec = str(_fd.get('SECTION') or _fd.get('section') or '').strip()

        if not all_classes and _cls:
            fallback_classes.add(_cls)
        if not all_sections and _sec:
            fallback_sections.add(_sec)

        if _cls:
            if _cls not in class_to_sections:
                class_to_sections[_cls] = set()
            if _sec:
                class_to_sections[_cls].add(_sec)

    if not all_classes:
        all_classes = sorted(fallback_classes)
    if not all_sections:
        all_sections = sorted(fallback_sections)

    return {
        'all_classes': all_classes,
        'all_sections': all_sections,
        'class_to_sections': {
            _cls: sorted(list(_sections))
            for _cls, _sections in class_to_sections.items()
        },
    }


# â”€â”€ Image upload validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_ALLOWED_IMAGE_TYPES = frozenset({
    'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif',
    'image/heic', 'image/heif', 'image/heic-sequence', 'image/heif-sequence',
    'image/bmp', 'application/octet-stream', 'image/octet-stream',  # Android camera can send these
})
_ALLOWED_IMAGE_EXTS  = frozenset({'.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic', '.heif', '.hei', '.bmp'})
_MAX_IMAGE_SIZE = 40 * 1024 * 1024  # 40 MB raw input; normalized output is compressed JPEG

def _validate_image(photo):
    """Return (ok, message, normalized_upload) for an uploaded file.

    Prefer the implementation in `mobile_app.views` when available so tests
    that patch `mobile_app.views._validate_image` affect this code path.
    """
    try:
        from importlib import import_module
        ma_views = import_module('mobile_app.views')
        func = getattr(ma_views, '_validate_image', None)
        if func:
            return func(photo)
    except Exception:
        pass

    normalized_upload, error_message = normalize_uploaded_image(
        photo,
        max_bytes=_MAX_IMAGE_SIZE,
        allowed_extensions=_ALLOWED_IMAGE_EXTS,
        allowed_mime_types=_ALLOWED_IMAGE_TYPES,
    )
    if error_message:
        return False, error_message, None
    return True, '', normalized_upload


def _unpack_validate_image_result(result, original_photo):
    try:
        from importlib import import_module
        ma_views = import_module('mobile_app.views')
        func = getattr(ma_views, '_unpack_validate_image_result', None)
        if func:
            return func(result, original_photo)
    except Exception:
        pass
    if isinstance(result, tuple):
        if len(result) == 3:
            return result
        if len(result) == 2:
            ok, err = result
            return ok, err, original_photo if ok else None
    return False, 'Invalid image validation response', None


def _serialize_mobile_admin_staff(staff):
    """Serialize admin_staff rows with full permission flags for mobile edit forms."""
    row = {
        'id': staff.id,
        'user_id': staff.user.id,
        'name': staff.user.get_full_name() or staff.user.username,
        'email': staff.user.email,
        'phone': getattr(staff.user, 'phone', '') or '',
        'department': staff.department or '',
        'designation': staff.designation or '',
        'is_active': staff.user.is_active,
        'staff_type': staff.get_staff_type_display(),
        'created_at': staff.created_at.strftime('%d %b %Y'),
        'assigned_client_ids': [client.id for client in staff.assigned_organisations.all()],
        'assigned_client_names': [client.name for client in staff.assigned_organisations.all()],
    }
    for perm in StaffService.PERMISSION_FIELDS:
        row[perm] = bool(getattr(staff, perm, False))
    return row


def _list_mobile_admin_staff(limit=200):
    """Return admin_staff records for mobile list/details, including permission booleans."""
    queryset = (
        Staff.objects
        .filter(staff_type='operator')
        .select_related('user')
        .prefetch_related('assigned_organisations')
        .order_by('-created_at')[:limit]
    )
    return [_serialize_mobile_admin_staff(staff) for staff in queryset]


# ---------------------------------------------------------------------------
# PAGE VIEWS
# ---------------------------------------------------------------------------



@csrf_exempt
@require_http_methods(["POST"])
@rate_limit(max_requests=6, window_seconds=60, key_prefix='mob_login')
def api_mobile_login(request):
    """Mobile-only login: authenticate + enforce perm_mobile_app before session login."""
    identifier = None
    try:
        data = json.loads(request.body or '{}')
        identifier = (data.get('email') or '').strip()
        password = data.get('password', '')
        force_logout_other = _truthy(data.get('force_logout_other'))
        client_ip = _get_client_ip(request)

        if not identifier or not password:
            return JsonResponse({'success': False, 'message': 'Email and password are required.'}, status=400)

        result = AuthService.authenticate_user(identifier, password)
        if not result.get('success'):
            return JsonResponse({'success': False, 'message': result.get('message', 'Invalid credentials.')}, status=400)

        user = result.get('user')
        valid_roles = ('pro_user', 'super_admin', 'operator', 'prime_manager', 'manager', 'guest_prime_manager', 'assistant', 'photographer')
        if not user or getattr(user, 'role', '') not in valid_roles:
            return JsonResponse({'success': False, 'message': 'This account cannot access the mobile app.'}, status=403)

        if not PermissionService.has(user, 'perm_mobile_app'):
            return JsonResponse({
                'success': False,
                'no_mobile_access': True,
                'message': 'Mobile app access is disabled for your account. Please contact admin/owner.',
            }, status=403)

        browser_fingerprint = AuthService.browser_fingerprint_from_request(request)
        current_session_key = ''
        if request.user.is_authenticated and getattr(request.user, 'pk', None) == user.pk:
            current_session_key = request.session.session_key or ''

        # Check for existing sessions (for logging purposes)
        session_inspection = AuthService.inspect_active_sessions_for_user(
            user.id,
            browser_fingerprint=browser_fingerprint,
            exclude_session_key=current_session_key,
        )
        surface_counts = session_inspection.get('surface_counts') or {}
        active_mobile_sessions = int(surface_counts.get('mobile', 0) or 0)

        try:
            auth_login(request, user)
            if not request.session.session_key:
                request.session.save()
            new_session_key = request.session.session_key or ''

            # Guest users are allowed up to 20 concurrent mobile sessions.
            # Keep the legacy handoff behavior for other roles only.
            if getattr(user, 'role', '') != 'guest_prime_manager':
                AuthService.revoke_active_sessions_for_user(
                    user.id,
                    surface='mobile',
                    exclude_session_key=new_session_key
                )
        except Exception as e:
            logger.error("api_mobile_login: auth_login failed: %s", str(e), exc_info=True)
            return JsonResponse({'success': False, 'message': 'Authentication failed during session creation.'}, status=500)

        # Seed session fingerprint immediately so the very next
        # request doesn't see a mismatch and force-logout the user.
        try:
            from core.middleware import PermissionValidationMiddleware
            PermissionValidationMiddleware.seed_session_fingerprint(request)
        except Exception as e:
            logger.warning("api_mobile_login: seed_session_fingerprint failed: %s", str(e))

        # Reset the absolute max-age clock for a fresh session lifetime.
        import time as _time
        request.session['_session_created'] = _time.time()
        request.session['_last_activity'] = _time.time()

        request.session['selected_role'] = getattr(user, 'role', '')
        # Mark session as mobile-authenticated so require_mobile_client passes.
        request.session['mobile_auth_ok'] = True
        
        try:
            AuthService.apply_session_auth_context(
                request,
                surface='mobile',
                ip_address=client_ip,
            )
        except Exception as e:
            logger.warning("api_mobile_login: apply_session_auth_context failed: %s", str(e))

        try:
            ActivityService.log_login(request, user)
        except Exception as e:
            logger.warning("api_mobile_login: log_login failed: %s", str(e))

        client, perms = _client_ctx(user)
        
        return JsonResponse({
            'success': True,
            'redirect_url': '/app/',
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'email': user.email,
                'full_name': user.get_full_name(),
                'role': _map_role_compat(user.role),
                'client_id': getattr(client, 'id', None) if client else None,
                'client_name': getattr(client, 'name', None) if client else None,
            },
            'permissions': perms or {},
            'pwa_enabled': (perms or {}).get('perm_mobile_app', False),
            'can_manage_clients': _can_manage_clients_surface(user),
            'can_manage_staff': _can_manage_client_staff_surface(user),
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error("api_mobile_login critical error: %s", str(e), exc_info=True)
        return JsonResponse({'success': False, 'message': 'An unexpected error occurred. Please try again.'}, status=500)


def pwa_manifest(request):
    """Serve the PWA Web App Manifest at /app/manifest.json.
    This is required for Chrome/Android to show the 'Add to Home Screen' prompt.
    """
    manifest = {
        'name': 'Adarsh ID Cards',
        'short_name': 'Adarsh IDs',
        'id': '/app/',
        'description': 'Manage ID cards on the go â€” fast, secure, and mobile-first.',
        'start_url': '/app/',
        'scope': '/app/',
        'display': 'standalone',
        'display_override': ['standalone', 'minimal-ui', 'browser'],
        'orientation': 'portrait',
        'background_color': '#eaf2ff',
        'theme_color': '#2f80ed',
        'lang': 'en',
        'prefer_related_applications': False,
        'icons': [
            {
                'src': '/static/mobile/images/icon-192.png',
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': '/static/mobile/images/icon-192.png',
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'maskable',
            },
            {
                'src': '/static/mobile/images/icon-512.png',
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': '/static/mobile/images/icon-512.png',
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'maskable',
            },
        ],
        'categories': ['business', 'productivity'],
    }
    response = JsonResponse(manifest)
    response['Content-Type'] = 'application/manifest+json'
    response['Cache-Control'] = 'public, max-age=3600'
    return response


def pwa_service_worker(request):
    """Serve the PWA service worker at /app/sw.js.
    The Service-Worker-Allowed header extends scope to the full /app/ path.
    A service worker is required by Chrome/Android to enable the PWA install prompt.
    """
    from django.http import HttpResponse
    app_version = str(getattr(settings, 'APP_VERSION', 'v0.00.00') or 'v0.00.00')
    version_seed = app_version.strip() or 'v0.00.00'
    normalized_version = re.sub(r'[^a-zA-Z0-9._-]+', '-', version_seed).strip('-').lower() or 'v0.00.00'

    try:
        cache_generation = max(1, int(getattr(settings, 'MOBILE_PWA_CACHE_GENERATION', 1) or 1))
    except (TypeError, ValueError):
        cache_generation = 1

    try:
        rollback_window = max(1, int(getattr(settings, 'MOBILE_PWA_CACHE_ROLLBACK_WINDOW', 2) or 2))
    except (TypeError, ValueError):
        rollback_window = 2

    cache_namespace = f'g{cache_generation}-{normalized_version}'
    asset_version = f'{normalized_version}.g{cache_generation}'
    cache_group = 'adarsh-mobile'

    shell_routes = [
        '/app/login/',
        '/app/no-access/',
        '/app/desktop-required/',
        '/app/manifest.json',
    ]
    static_assets = [
        f'/static/css/tailwind.css?v={asset_version}',
        '/static/css/vendor/fontawesome/all.min.css?v=3',
        '/static/css/vendor/webfonts/fa-solid-900.woff2',
        '/static/css/vendor/webfonts/fa-solid-900.ttf',
        '/static/css/vendor/webfonts/fa-regular-400.woff2',
        '/static/css/vendor/webfonts/fa-regular-400.ttf',
        '/static/css/vendor/webfonts/fa-brands-400.woff2',
        '/static/css/vendor/webfonts/fa-brands-400.ttf',
        f'/static/mobile/css/mobile.css?v={asset_version}',
        f'/static/css/dropdown-unified.css?v={asset_version}',
        f'/static/mobile/js/environment-gate.js?v={asset_version}',
        f'/static/mobile/js/device-bridge.js?v={asset_version}',
        f'/static/mobile/js/app.js?v={asset_version}',
    ]
    read_only_cacheable_paths = [
        '/app/login/',
        '/app/no-access/',
        '/app/desktop-required/',
        '/app/manifest.json',
    ]
    online_required_prefixes = [
        '/app/api/',
        '/app/camera/',
        '/app/table/',
        '/app/reprint/',
        '/app/clients/',
        '/app/website/',
        '/app/staff/',
        '/app/groups/',
        '/app/profile/',
        '/app/settings/',
        '/app/notifications/',
        '/app/search/',
    ]

    # Exclude login and CSRF from caching (Step 10)
    online_required_prefixes.extend([
        '/panel/auth/login/',
        '/panel/auth/csrf/',
        '/auth/login/',
        '/csrf/',
    ])

    sw_template = """\
/* Adarsh ID Cards â€” PWA Service Worker (Phase 5) */
const CACHE_GROUP = '__CACHE_GROUP__';
const CACHE_NAMESPACE = '__CACHE_NAMESPACE__';
const CACHE_GENERATION = __CACHE_GENERATION__;
const ROLLBACK_WINDOW = __ROLLBACK_WINDOW__;
const APP_CACHE = CACHE_GROUP + '-app-' + CACHE_NAMESPACE;
const STATIC_CACHE = CACHE_GROUP + '-static-' + CACHE_NAMESPACE;
const SHELL = __SHELL_JSON__;
const STATIC_ASSETS = __STATIC_ASSETS_JSON__;
const READ_ONLY_CACHEABLE_PATHS = __READ_ONLY_PATHS_JSON__;
const ONLINE_REQUIRED_PREFIXES = __ONLINE_REQUIRED_PREFIXES_JSON__;
const OFFLINE_HTML = [
    '<!doctype html>',
    '<html lang="en">',
    '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
    '<title>Offline - Adarsh IDs</title>',
    '<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:24px;background:#eaf2ff;color:#1f2937;} .card{max-width:420px;margin:8vh auto;background:#fff;border:1px solid #d6e7f8;border-radius:14px;padding:18px 16px;box-shadow:0 8px 20px rgba(15,23,42,.08);} h1{font-size:20px;margin:0 0 8px;} p{font-size:14px;line-height:1.45;color:#4b5563;margin:0;} a{display:inline-block;margin-top:12px;font-size:13px;text-decoration:none;color:#2f80ed;font-weight:600;}</style>',
    '</head><body><div class="card"><h1>Offline Mode</h1><p>This page requires internet right now. Reconnect and try again.</p><a href="/app/login/">Open Login</a></div></body></html>'
].join('');

function shouldCacheResponse(response) {
    return !!response && response.status === 200;
}

function parseGeneration(cacheName) {
    if (!cacheName) return null;
    var match = cacheName.match(/-g(\d+)-/);
    if (!match) return null;
    var parsed = parseInt(match[1], 10);
    return Number.isFinite(parsed) ? parsed : null;
}

function isLegacyCache(cacheName) {
    return /^adarsh-(app|static)-v\d+$/.test(cacheName || '');
}

function shouldDeleteStaleCache(cacheName, activeCaches) {
    if (activeCaches.indexOf(cacheName) !== -1) return false;
    if (isLegacyCache(cacheName)) return true;
    if ((cacheName || '').indexOf(CACHE_GROUP + '-') !== 0) return false;
    var generation = parseGeneration(cacheName);
    if (generation === null) return true;
    return generation < (CACHE_GENERATION - ROLLBACK_WINDOW);
}

function isOnlineRequiredPath(pathname) {
    if (!pathname) return false;
    return ONLINE_REQUIRED_PREFIXES.some(function(prefix) {
        return pathname.indexOf(prefix) === 0;
    });
}

function isReadOnlyCacheablePath(pathname) {
    return READ_ONLY_CACHEABLE_PATHS.indexOf(pathname) !== -1;
}

function offlineJsonResponse() {
    return new Response(JSON.stringify({ success: false, offline: true, message: 'Network connection required.' }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
    });
}

function offlineHtmlResponse() {
    return new Response(OFFLINE_HTML, {
        status: 503,
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
}

self.addEventListener('install', function(event) {
    event.waitUntil(
        Promise.all([
            caches.open(APP_CACHE).then(async function(cache) {
                await Promise.allSettled(
                    SHELL.map(function(url) {
                        return cache.add(url);
                    })
                );
            }),
            caches.open(STATIC_CACHE).then(async function(cache) {
                await Promise.allSettled(
                    STATIC_ASSETS.map(function(url) {
                        return cache.add(url);
                    })
                );
            }),
        ])
    );
    self.skipWaiting();
});

self.addEventListener('activate', function(event) {
    var activeCaches = [APP_CACHE, STATIC_CACHE];
    event.waitUntil(
        caches.keys().then(function(cacheNames) {
            return Promise.all(
                cacheNames
                    .filter(function(cacheName) {
                        return shouldDeleteStaleCache(cacheName, activeCaches);
                    })
                    .map(function(cacheName) {
                        return caches.delete(cacheName);
                    })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('message', function(event) {
    if (event && event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

self.addEventListener('fetch', function(event) {
    if (event.request.method !== 'GET') return;

    var url = new URL(event.request.url);
    if (url.origin !== self.location.origin) return;

    if (url.pathname.indexOf('/static/') === 0) {
        event.respondWith(
            caches.open(STATIC_CACHE).then(function(cache) {
                var isIconAsset = url.pathname.indexOf('/static/css/vendor/fontawesome/') === 0 ||
                    url.pathname.indexOf('/static/css/vendor/webfonts/') === 0;

                if (isIconAsset) {
                    return fetch(event.request)
                        .then(function(response) {
                            if (shouldCacheResponse(response)) {
                                cache.put(event.request, response.clone());
                            }
                            return response;
                        })
                        .catch(function() {
                            return cache.match(event.request).then(function(cached) {
                                return cached || Response.error();
                            });
                        });
                }

                return cache.match(event.request).then(function(cached) {
                    var networkFetch = fetch(event.request)
                        .then(function(response) {
                            if (shouldCacheResponse(response)) {
                                cache.put(event.request, response.clone());
                            }
                            return response;
                        })
                        .catch(function() {
                            return cached || Response.error();
                        });

                    return cached || networkFetch;
                });
            })
        );
        return;
    }

    if (url.pathname.indexOf('/app/api/') === 0) {
        event.respondWith(
            fetch(event.request).catch(function() {
                return offlineJsonResponse();
            })
        );
        return;
    }

    if (isOnlineRequiredPath(url.pathname)) {
        event.respondWith(
            fetch(event.request).catch(function() {
                return offlineHtmlResponse();
            })
        );
        return;
    }

    if (!url.pathname.startsWith('/app/')) return;

    if (isReadOnlyCacheablePath(url.pathname)) {
        event.respondWith(
            caches.open(APP_CACHE).then(function(cache) {
                return fetch(event.request)
                    .then(function(response) {
                        if (shouldCacheResponse(response)) {
                            cache.put(event.request, response.clone());
                        }
                        return response;
                    })
                    .catch(function() {
                        return cache.match(event.request).then(function(cached) {
                            return cached || cache.match('/app/login/');
                        });
                    });
            })
        );
        return;
    }

    event.respondWith(
        fetch(event.request).catch(function() {
            return offlineHtmlResponse();
        })
    );
});
"""

    sw_content = (
        sw_template
        .replace('__CACHE_GROUP__', cache_group)
        .replace('__CACHE_NAMESPACE__', cache_namespace)
        .replace('__CACHE_GENERATION__', json.dumps(cache_generation))
        .replace('__ROLLBACK_WINDOW__', json.dumps(rollback_window))
        .replace('__SHELL_JSON__', json.dumps(shell_routes))
        .replace('__STATIC_ASSETS_JSON__', json.dumps(static_assets))
        .replace('__READ_ONLY_PATHS_JSON__', json.dumps(read_only_cacheable_paths))
        .replace('__ONLINE_REQUIRED_PREFIXES_JSON__', json.dumps(online_required_prefixes))
    )
    response = HttpResponse(sw_content, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/app/'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


# ---------------------------------------------------------------------------
# API VIEWS — thin proxies to existing services
# ---------------------------------------------------------------------------

@require_mobile_client
@require_http_methods(["POST"])
def api_card_status(request, card_id):
    """Change single card status."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    new_status = data.get('status', '')
    apply_class_change = _truthy(data.get('apply_class_change'))
    updated_class = data.get('updated_class', '')

    result = OrganisationCardService.change_card_status(
        request.user, card_id, new_status, request=request,
        apply_class_change=apply_class_change, updated_class=updated_class
    )
    if result.success:
        return JsonResponse({'success': True, 'message': result.message, **(result.data or {})})

    if result.data and result.data.get('requires_class_change'):
        return JsonResponse({'success': False, 'message': result.message, **(result.data or {})}, status=409)

    return JsonResponse({'success': False, 'message': result.message}, status=400)


@require_mobile_client
@require_http_methods(["POST"])
@rate_limit(max_requests=30, window_seconds=60, key_prefix='mab_bulk')
def api_bulk_status(request, table_id):
    """Bulk status change."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    card_ids_raw = data.get('card_ids', [])
    new_status = data.get('status', '')
    if not isinstance(card_ids_raw, list):
        return JsonResponse({'success': False, 'message': 'card_ids must be a list'}, status=400)
    if len(card_ids_raw) > 500:
        return JsonResponse({'success': False, 'message': 'Maximum 500 cards per batch'}, status=400)

    card_ids = _normalize_positive_int_ids(card_ids_raw)
    if not card_ids:
        return JsonResponse({'success': False, 'message': 'No valid card IDs provided'}, status=400)

    apply_class_change = _truthy(data.get('apply_class_change'))
    pool_retrieve_class_updates = data.get('pool_retrieve_class_updates') or {}

    result = OrganisationCardService.bulk_change_status(
        request.user, table_id, card_ids, new_status, request=request,
        apply_class_change=apply_class_change,
        pool_retrieve_class_updates=pool_retrieve_class_updates
    )
    if result.success:
        return JsonResponse({'success': True, 'message': result.message, **(result.data or {})})

    if result.data and result.data.get('requires_class_change'):
        return JsonResponse({'success': False, 'message': result.message, **(result.data or {})}, status=409)

    return JsonResponse({'success': False, 'message': result.message}, status=400)


@require_mobile_client
@require_http_methods(["POST"])
@rate_limit(max_requests=20, window_seconds=60, key_prefix='mab_upload')
def api_upload_photo(request, table_id):
    """Upload photo for a card."""
    card_id = request.POST.get('card_id')
    photo = request.FILES.get('photo')
    if not photo or not card_id:
        return JsonResponse({'success': False, 'message': 'photo and card_id required'}, status=400)

    try:
        card_id_int = int(str(card_id).strip())
        card = IDCard.objects.select_related('table__group').get(id=card_id_int, table_id=table_id)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Invalid card_id'}, status=400)
    except IDCard.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Card not found'}, status=404)

    is_assistant_pool_retrieve = (
        PermissionService.is_client_staff(request.user)
        and card.status == 'pool'
        and PermissionService.has(request.user, 'perm_idcard_retrieve')
    )

    if not PermissionService.has(request.user, 'perm_idcard_edit') and not is_assistant_pool_retrieve:
        return JsonResponse({'success': False, 'message': 'No permission to edit cards'}, status=403)

    _ok, _err, photo = _unpack_validate_image_result(_validate_image(photo), photo)
    if not _ok:
        return JsonResponse({'success': False, 'message': _err}, status=400)

    try:
        if not is_assistant_pool_retrieve and not _can_access_card_with_row_scope(request.user, card):
            return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
        if _is_mobile_client_edit_locked(request.user, card.status) and not is_assistant_pool_retrieve:
            return _mobile_client_edit_locked_response()

        # Keep mobile + desktop lists in sync by writing through the same
        # field_data/CardMedia image pipeline used by idcard-actions tables.
        image_field_names = ImageService.get_image_field_names(card.table.fields or [])
        requested_field_name = str(request.POST.get('field_name') or '').strip()
        preferred_field_name = None

        if requested_field_name:
            requested_token = _mobile_field_token(requested_field_name)
            for field_name in image_field_names:
                if _mobile_field_token(field_name) == requested_token:
                    preferred_field_name = field_name
                    break

        if not preferred_field_name:
            image_names_by_token = {
                _mobile_field_token(field_name): field_name
                for field_name in image_field_names
            }
            relation_name_tokens = ('father', 'mother', 'guardian', 'rel')
            for field_def in (card.table.fields or []):
                field_name = str(field_def.get('name', '')).strip()
                if not field_name:
                    continue

                try:
                    from importlib import import_module
                    ma_views = import_module('mobile_app.views')
                    token = _mobile_field_token(field_name)
                except Exception:
                    token = None
                matched_name = image_names_by_token.get(token)
                if not matched_name:
                    continue

                field_type = str(field_def.get('type', '')).strip().lower()
                field_name_lower = field_name.lower()
                is_relation_like = (
                    field_type in {'rel_photo', 'mother_photo', 'father_photo'}
                    or any(tok in field_name_lower for tok in relation_name_tokens)
                )
                if field_type == 'photo' and not is_relation_like:
                    preferred_field_name = matched_name
                    break

        if not preferred_field_name:
            for field_name in image_field_names:
                field_name_lower = str(field_name or '').lower()
                if 'photo' not in field_name_lower:
                    continue
                if any(tok in field_name_lower for tok in ('rel', 'father', 'mother', 'guardian')):
                    continue
                preferred_field_name = field_name
                break

        if not preferred_field_name and image_field_names:
            preferred_field_name = image_field_names[0]

        if preferred_field_name:
            field_data = card.field_data or {}
            field_data_upper = {k.upper(): v for k, v in field_data.items()}
            existing_value = field_data.get(preferred_field_name, '') or field_data_upper.get(preferred_field_name.upper(), '')

            media_result = ImageService.process_image_field(
                field_name=preferred_field_name,
                new_value=None,
                existing_value=existing_value,
                client=card.table.group.client,
                card=card,
                uploaded_file=photo,
                batch_counter=1,
                uploaded_by=request.user,
            )
            if not media_result.success:
                return JsonResponse({'success': False, 'message': media_result.message or 'Upload failed'}, status=400)

            final_value = (media_result.data or {}).get('final_value', existing_value)
            field_data[preferred_field_name] = final_value
            card.field_data = field_data
            card.modified_by = getattr(request.user, 'username', '') or card.modified_by

            # Legacy compatibility: keep ImageField pointer aligned with latest path.
            if final_value:
                card.photo = final_value
                # Extra safety: ensure thumbnail exists even if initial creation failed.
                ThumbnailService.ensure_thumbnail_exists(final_value)

            card.save(update_fields=['field_data', 'modified_by', 'photo'])
            photo_url = get_card_photo_url(card, field_data)
            return JsonResponse({
                'success': True,
                'message': 'Photo uploaded',
                'photo_url': photo_url,
                'field_name': preferred_field_name,
            })

        # Fallback for tables with no configured image fields:
        # still route through ImageService so filenames follow timestamp policy.
        field_data = card.field_data or {}
        existing_value = ''
        try:
            existing_value = card.photo.name or ''
        except Exception:
            existing_value = ''

        media_result = ImageService.process_image_field(
            field_name='PHOTO',
            new_value=None,
            existing_value=existing_value,
            client=card.table.group.client,
            card=card,
            uploaded_file=photo,
            batch_counter=1,
            uploaded_by=request.user,
        )
        if not media_result.success:
            return JsonResponse({'success': False, 'message': media_result.message or 'Upload failed'}, status=400)

        final_value = (media_result.data or {}).get('final_value', existing_value)
        if final_value:
            field_data['PHOTO'] = final_value
            card.field_data = field_data
            card.photo = final_value
            # Extra safety: ensure thumbnail exists even if initial creation failed.
            ThumbnailService.ensure_thumbnail_exists(final_value)

        card.modified_by = getattr(request.user, 'username', '') or card.modified_by
        update_fields = ['modified_by']
        if final_value:
            update_fields.extend(['field_data', 'photo'])
        card.save(update_fields=update_fields)

        return JsonResponse({
            'success': True,
            'message': 'Photo uploaded',
            'photo_url': get_card_photo_url(card, field_data),
            'field_name': 'PHOTO',
        })
    except IDCard.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Card not found'}, status=404)
    except Exception:
        import logging as _log
        _log.getLogger(__name__).exception('Photo upload error')
        return JsonResponse({'success': False, 'message': 'An error occurred during upload.'}, status=500)


@require_mobile_client
@require_http_methods(["GET"])
def api_card_detail(request, card_id):
    """Get card detail JSON."""
    result = OrganisationCardService.get_card_detail(request.user, card_id)
    if result.success:
        return JsonResponse({'success': True, 'data': result.data})
    msg = (result.message or '').lower()
    if 'permission' in msg or 'access denied' in msg or 'access' in msg:
        status_code = 403
    else:
        status_code = 404
    return JsonResponse({'success': False, 'message': result.message}, status=status_code)


@require_mobile_client
@require_http_methods(["GET"])
def api_cards(request, table_id):
    """Get cards for a table (paginated)."""
    status_filter = str(request.GET.get('status', '') or '').strip().lower()
    if not status_filter:
        return JsonResponse({'success': False, 'message': 'status is required'}, status=400)

    valid_statuses = {'pending', 'verified', 'approved', 'download', 'pool', 'reprint', 'captured', 'uncaptured'}
    if status_filter not in valid_statuses:
        return JsonResponse({'success': False, 'message': 'Invalid status'}, status=400)

    search = _sanitize_search_query(request.GET.get('search', ''))
    from_date = (request.GET.get('from') or '').strip()
    to_date = (request.GET.get('to') or '').strip()
    photo_filter = str(request.GET.get('photo', '') or '').strip().lower()
    if photo_filter not in ('complete', 'pending', 'incomplete', 'with', 'without'):
        photo_filter = ''
    image_column = str(request.GET.get('image_column', '') or '').strip()
    sort_mode = _normalize_mobile_sort_mode(request.GET.get('sort', 'sr-asc'))
    class_filter = (request.GET.get('class') or '').strip()
    section_filter = (request.GET.get('section') or '').strip()
    course_filter = (request.GET.get('course') or '').strip()
    branch_filter = (request.GET.get('branch') or '').strip()
    try:
        page = max(int(request.GET.get('page', 1)), 1)
        per_page = max(1, min(int(request.GET.get('per_page', 50)), 200))
    except (ValueError, TypeError):
        page, per_page = 1, 50

    offset = (page - 1) * per_page

    try:
        result = OrganisationCardService.get_cards(
            request.user, table_id,
            status_filter, offset, per_page,
            search or None,
            from_date=from_date,
            to_date=to_date,
            class_filter=class_filter or None,
            section_filter=section_filter or None,
            course_filter=course_filter or None,
            branch_filter=branch_filter or None,
            photo_filter=photo_filter or None,
            sort_order=sort_mode,
            image_column=image_column or None,
        )
        if result.success:
            return JsonResponse({'success': True, 'data': result.data})
        return JsonResponse({'success': False, 'message': result.message}, status=400)
    except Exception:
        logger.exception('api_cards error')
        return JsonResponse({'success': False, 'message': 'Unable to load cards.'}, status=500)


@require_mobile_client
@require_http_methods(["GET"])
def api_all_card_ids(request, table_id):
    """Return all matching card IDs for mobile Select All (full dataset, filter-aware)."""
    status_filter = str(request.GET.get('status', '') or '').strip().lower()
    if not status_filter:
        return JsonResponse({'success': False, 'message': 'status is required'}, status=400)

    valid_statuses = {'pending', 'verified', 'approved', 'download', 'pool', 'reprint', 'captured', 'uncaptured'}
    if status_filter not in valid_statuses:
        return JsonResponse({'success': False, 'message': 'Invalid status'}, status=400)

    table = get_object_or_404(Table, id=table_id)
    if not OrganisationAccessService.can_access_table(request.user, table):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)

    perm_map = {
        'pending': 'perm_idcard_pending_list',
        'verified': 'perm_idcard_verified_list',
        'pool': 'perm_idcard_pool_list',
        'reprint': 'perm_idcard_reprint_list',
        'captured': 'perm_idcard_pending_list',
        'uncaptured': 'perm_idcard_pending_list',
    }
    needed_perm = perm_map.get(status_filter)
    if needed_perm and not PermissionService.has(request.user, needed_perm):
        return JsonResponse({'success': False, 'message': 'No permission to view this list'}, status=403)

    search = _sanitize_search_query(request.GET.get('search', ''))
    from_date = (request.GET.get('from') or '').strip()
    to_date = (request.GET.get('to') or '').strip()
    selected_class = (request.GET.get('class') or '').strip()
    selected_section = (request.GET.get('section') or '').strip()
    selected_course = (request.GET.get('course') or '').strip()
    selected_branch = (request.GET.get('branch') or '').strip()
    photo_filter = str(request.GET.get('photo', '') or '').strip().lower()
    if photo_filter not in ('complete', 'pending', 'incomplete', 'with', 'without'):
        photo_filter = ''
    image_column = str(request.GET.get('image_column', '') or '').strip()
    
    if status_filter in ('captured', 'uncaptured'):
        cards_qs = IDCard.objects.filter(table=table, status__in=['pending', 'verified']).order_by('-created_at', '-id')
        if not photo_filter:
            photo_filter = 'complete' if status_filter == 'captured' else 'incomplete'
    elif status_filter == 'download':
        cards_qs = IDCard.objects.filter(table=table, status=status_filter).order_by('-downloaded_at', '-id')
    elif status_filter == 'pool':
        cards_qs = IDCard.objects.filter(table=table, status=status_filter).order_by('-deleted_at', '-id')
    elif status_filter in ('verified', 'approved'):
        cards_qs = IDCard.objects.filter(table=table, status=status_filter).order_by('-status_changed_at', '-id')
    else:
        cards_qs = IDCard.objects.filter(table=table, status=status_filter).order_by('-created_at', '-id')

    cards_qs = OrganisationCardService._apply_client_staff_row_scope(request.user, table, cards_qs)

    if search:
        cards_qs = IDCardService._apply_search_filter(cards_qs, search, table=table)

    if status_filter == 'download':
        if from_date:
            parsed_from_dt = parse_datetime(from_date)
            if parsed_from_dt is not None:
                if is_naive(parsed_from_dt):
                    parsed_from_dt = make_aware(parsed_from_dt)
                cards_qs = cards_qs.filter(downloaded_at__gte=parsed_from_dt)
            else:
                parsed_from_d = parse_date(from_date)
                if parsed_from_d is not None:
                    cards_qs = cards_qs.filter(downloaded_at__date__gte=parsed_from_d)

        if to_date:
            parsed_to_dt = parse_datetime(to_date)
            if parsed_to_dt is not None:
                if is_naive(parsed_to_dt):
                    parsed_to_dt = make_aware(parsed_to_dt)
                cards_qs = cards_qs.filter(downloaded_at__lte=parsed_to_dt)
            else:
                parsed_to_d = parse_date(to_date)
                if parsed_to_d is not None:
                    cards_qs = cards_qs.filter(downloaded_at__date__lte=parsed_to_d)

    class_field_name, section_field_name, course_field_name, branch_field_name = (
        IDCardService._get_class_section_course_branch_field_names(table)
    )

    if selected_class:
        selected_class_norm = normalize_class_value(selected_class)
        if not class_field_name or not selected_class_norm:
            cards_qs = cards_qs.none()
        else:
            cards_qs = cards_qs.annotate(_filter_cls=Cast(KeyTextTransform(class_field_name, 'field_data'), CharField()))
            raw_classes = list(
                cards_qs
                .exclude(_filter_cls__isnull=True)
                .exclude(_filter_cls='')
                .values_list('_filter_cls', flat=True)
                .distinct()
            )
            matching_classes = [
                raw_value for raw_value in raw_classes
                if normalize_class_value(raw_value) == selected_class_norm
            ]
            if not matching_classes:
                cards_qs = cards_qs.none()
            else:
                cards_qs = cards_qs.filter(_filter_cls__in=matching_classes)

    if selected_section:
        if not section_field_name:
            cards_qs = cards_qs.none()
        else:
            cards_qs = cards_qs.annotate(_filter_sec=Cast(KeyTextTransform(section_field_name, 'field_data'), CharField()))
            target_section = selected_section.strip().lower()
            raw_sections = list(
                cards_qs
                .exclude(_filter_sec__isnull=True)
                .exclude(_filter_sec='')
                .values_list('_filter_sec', flat=True)
                .distinct()
            )
            matching_sections = [
                raw_value for raw_value in raw_sections
                if str(raw_value).strip().lower() == target_section
            ]
            if not matching_sections:
                cards_qs = cards_qs.none()
            else:
                cards_qs = cards_qs.filter(_filter_sec__in=matching_sections)

    if selected_course and course_field_name:
        cards_qs = IDCardService._apply_compact_text_filter(
            cards_qs,
            selected_course,
            course_field_name,
            table_id=table_id,
            alias='_course_cmp',
        )

    if selected_branch and branch_field_name:
        cards_qs = IDCardService._apply_compact_text_filter(
            cards_qs,
            selected_branch,
            branch_field_name,
            table_id=table_id,
            alias='_branch_cmp',
        )

    if photo_filter:
        matching_photo_ids = []
        target_col = image_column or 'photo'
        for _card in cards_qs.only('id', 'photo', 'field_data').iterator(chunk_size=500):
            fd = _card.field_data or {}
            
            if target_col:
                val = fd.get(target_col)
                if val is None:
                    for k, v in fd.items():
                        if str(k).strip().upper() == target_col.upper():
                            val = v
                            break
                has_valid_photo = bool(val and isinstance(val, str) and not val.startswith('PENDING:') and val not in ('NOT_FOUND', ''))
                is_pending_placeholder = bool(val and isinstance(val, str) and val.startswith('PENDING:'))
            else:
                has_valid_photo = bool(get_card_photo_url(_card, fd))
                is_pending_placeholder = False
                for val in fd.values():
                    if isinstance(val, str) and val.startswith('PENDING:'):
                        is_pending_placeholder = True
                        break

            matched = False
            if photo_filter in ('complete', 'with'):
                matched = has_valid_photo
            elif photo_filter == 'pending':
                matched = is_pending_placeholder
            elif photo_filter in ('incomplete', 'without'):
                matched = not has_valid_photo and not is_pending_placeholder

            if matched:
                matching_photo_ids.append(_card.id)

        if not matching_photo_ids:
            cards_qs = cards_qs.none()
        else:
            cards_qs = cards_qs.filter(id__in=matching_photo_ids)

    card_ids = list(cards_qs.values_list('id', flat=True))
    return JsonResponse({
        'success': True,
        'card_ids': card_ids,
        'total_count': len(card_ids),
    })


@require_mobile_client
@require_http_methods(["GET"])
def api_filter_options(request, table_id):
    """Return distinct class/section/course/branch values for filter dropdowns on mobile."""
    status_filter = str(request.GET.get('status', '') or '').strip().lower()
    if not status_filter:
        return JsonResponse({'success': False, 'message': 'status is required'}, status=400)

    valid_statuses = {'pending', 'verified', 'approved', 'download', 'pool', 'reprint', 'captured', 'uncaptured'}
    if status_filter not in valid_statuses:
        return JsonResponse({'success': False, 'message': 'Invalid status'}, status=400)

    table = get_object_or_404(Table, id=table_id)
    if not OrganisationAccessService.can_access_table(request.user, table):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)

    perm_map = {
        'pending': 'perm_idcard_pending_list',
        'verified': 'perm_idcard_verified_list',
        'pool': 'perm_idcard_pool_list',
        'reprint': 'perm_idcard_reprint_list',
        'captured': 'perm_idcard_pending_list',
        'uncaptured': 'perm_idcard_pending_list',
    }
    needed_perm = perm_map.get(status_filter)
    if needed_perm and not PermissionService.has(request.user, needed_perm):
        return JsonResponse({'success': False, 'message': 'No permission to view this list'}, status=403)

    cards_qs = IDCard.objects.filter(table=table)
    if status_filter in ('captured', 'uncaptured'):
        cards_qs = cards_qs.filter(status__in=['pending', 'verified'])
        
        # Apply photo presence filter
        matching_photo_ids = []
        target_col = 'photo'
        for _card in cards_qs.only('id', 'photo', 'field_data').iterator(chunk_size=500):
            fd = _card.field_data or {}
            val = fd.get(target_col)
            if val is None:
                for k, v in fd.items():
                    if str(k).strip().upper() == target_col.upper():
                        val = v
                        break
            has_photo = bool(val and isinstance(val, str) and not val.startswith('PENDING:') and val not in ('NOT_FOUND', ''))
            
            matched = False
            if status_filter == 'captured':
                matched = has_photo
            else:
                matched = not has_photo
                
            if matched:
                matching_photo_ids.append(_card.id)
                
        cards_qs = cards_qs.filter(id__in=matching_photo_ids)
    elif status_filter:
        cards_qs = cards_qs.filter(status=status_filter)

    if status_filter != 'pool' and PermissionService.is_client_staff(request.user):
        cards_qs = OrganisationCardService._apply_client_staff_row_scope(request.user, table, cards_qs, status_filter=status_filter, ignore_pool_bypass=True)
    else:
        cards_qs = OrganisationCardService._apply_client_staff_row_scope(request.user, table, cards_qs, status_filter=status_filter)

    class_field_name, section_field_name, course_field_name, branch_field_name = (
        IDCardService._get_class_section_course_branch_field_names(table)
    )

    from collections import defaultdict
    class_values = []
    section_values = []
    course_values = []
    branch_values = []
    course_display_map = {}
    branch_display_map = {}
    class_to_sections = {}
    course_to_branches = {}

    if class_field_name:
        # Get distinct raw values WITH counts
        raw_with_counts = (
            cards_qs.annotate(_cv=Cast(KeyTextTransform(class_field_name, 'field_data'), CharField()))
            .exclude(_cv__isnull=True).exclude(_cv='')
            .order_by()
            .values('_cv')
            .annotate(cnt=Count('id'))
        )

        # Group by canonical form → pick most common raw as display
        groups = defaultdict(list)  # canonical → [(raw, count)]
        for entry in raw_with_counts:
            raw = entry['_cv'].strip()
            canonical = normalize_class_value(raw)
            groups[canonical].append((raw, entry['cnt']))

        for canonical, variants in groups.items():
            best_display = max(variants, key=lambda x: x[1])[0]
            total_count = sum(v[1] for v in variants)
            class_values.append({
                'value': canonical,
                'display': best_display,
                'count': total_count,
            })

        # Sort by class order
        class_values.sort(
            key=lambda x: (CLASS_ORDER.get(x['value'], CLASS_ORDER_UNKNOWN), x['value'])
        )

    if section_field_name:
        section_values = sorted(
            [
                str(v) for v in
                cards_qs.annotate(_sv=Cast(KeyTextTransform(section_field_name, 'field_data'), CharField()))
                .exclude(_sv__isnull=True).exclude(_sv='')
                .order_by()
                .values_list('_sv', flat=True).distinct()
                if v is not None
            ],
        )

    if course_field_name:
        raw_with_counts = (
            cards_qs.annotate(_coursev=Cast(KeyTextTransform(course_field_name, 'field_data'), CharField()))
            .exclude(_coursev__isnull=True).exclude(_coursev='')
            .order_by()
            .values('_coursev')
            .annotate(cnt=Count('id'))
        )

        grouped = {}
        for entry in raw_with_counts:
            raw = str(entry['_coursev']).strip()
            normalized = normalize_compact_text_value(raw)
            if not normalized:
                continue
            prev = grouped.get(normalized)
            if prev is None or entry['cnt'] > prev[1]:
                grouped[normalized] = (raw, entry['cnt'])

        course_display_map = {normalized: data[0] for normalized, data in grouped.items()}
        course_values = sorted(course_display_map.values(), key=lambda x: x.lower())

    if branch_field_name:
        raw_with_counts = (
            cards_qs.annotate(_branchv=Cast(KeyTextTransform(branch_field_name, 'field_data'), CharField()))
            .exclude(_branchv__isnull=True).exclude(_branchv='')
            .order_by()
            .values('_branchv')
            .annotate(cnt=Count('id'))
        )

        grouped = {}
        for entry in raw_with_counts:
            raw = str(entry['_branchv']).strip()
            normalized = normalize_compact_text_value(raw)
            if not normalized:
                continue
            prev = grouped.get(normalized)
            if prev is None or entry['cnt'] > prev[1]:
                grouped[normalized] = (raw, entry['cnt'])

        branch_display_map = {normalized: data[0] for normalized, data in grouped.items()}
        branch_values = sorted(branch_display_map.values(), key=lambda x: x.lower())

    if class_field_name and section_field_name:
        pair_rows = (
            cards_qs.annotate(
                _cv=Cast(KeyTextTransform(class_field_name, 'field_data'), CharField()),
                _sv=Cast(KeyTextTransform(section_field_name, 'field_data'), CharField()),
            )
            .exclude(_cv__isnull=True).exclude(_cv='')
            .exclude(_sv__isnull=True).exclude(_sv='')
            .order_by()
            .values_list('_cv', '_sv')
            .distinct()
        )

        class_section_sets = defaultdict(set)
        for raw_class, raw_section in pair_rows:
            canonical_class = normalize_class_value(str(raw_class).strip())
            section_text = str(raw_section).strip()
            if not canonical_class or not section_text:
                continue
            class_section_sets[canonical_class].add(section_text)

        # Build canonical → display mapping so class_to_sections keys match what classes list returns
        canonical_to_display = {c['value']: c['display'] for c in class_values}

        class_to_sections = {
            canonical_to_display.get(cls, cls): sorted(list(sections))
            for cls, sections in class_section_sets.items()
        }

    if course_field_name and branch_field_name:
        pair_rows = (
            cards_qs.annotate(
                _coursev=Cast(KeyTextTransform(course_field_name, 'field_data'), CharField()),
                _branchv=Cast(KeyTextTransform(branch_field_name, 'field_data'), CharField()),
            )
            .exclude(_coursev__isnull=True).exclude(_coursev='')
            .exclude(_branchv__isnull=True).exclude(_branchv='')
            .order_by()
            .values_list('_coursev', '_branchv')
            .distinct()
        )

        course_branch_sets = defaultdict(set)
        for raw_course, raw_branch in pair_rows:
            course_text = str(raw_course).strip()
            branch_text = str(raw_branch).strip()
            course_norm = normalize_compact_text_value(course_text)
            branch_norm = normalize_compact_text_value(branch_text)
            if not course_norm or not branch_norm:
                continue
            if course_norm not in course_display_map:
                course_display_map[course_norm] = course_text
            if branch_norm not in branch_display_map:
                branch_display_map[branch_norm] = branch_text

            course_branch_sets[course_norm].add(branch_norm)

        course_to_branches = {
            course_display_map.get(course, course): sorted(
                [branch_display_map.get(branch, branch) for branch in branches],
                key=lambda x: x.lower(),
            )
            for course, branches in course_branch_sets.items()
        }

    return JsonResponse({
        'success': True,
        'data': {
            'fields': table.fields,
            'classes': [c['display'] for c in class_values] if class_values else [],
            'sections': list(section_values),
            'courses': list(course_values),
            'branches': list(branch_values),
            'class_to_sections': class_to_sections,
            'course_to_branches': course_to_branches,
            'total': cards_qs.count(),
        },
    })


@require_mobile_client
@require_http_methods(["POST"])
@rate_limit(max_requests=20, window_seconds=60, key_prefix='mab_add')
def api_card_add(request, table_id):
    """Add a new card to a table."""
    try:
        table = get_object_or_404(Table, id=table_id, is_active=True)
        if not OrganisationAccessService.can_access_table(request.user, table):
            return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
        if not PermissionService.has(request.user, 'perm_idcard_add'):
            return JsonResponse({'success': False, 'message': 'No permission to add cards'}, status=403)

        field_data_raw = request.POST.get('field_data', '{}')
        try:
            field_data = json.loads(field_data_raw)
        except json.JSONDecodeError:
            field_data = {}
        if not isinstance(field_data, dict):
            field_data = {}

        from core.services import IDCardService
        if hasattr(table, 'fields'):
            field_data = IDCardService.uppercase_field_data_selective(field_data, table.fields)

        legacy_photo = request.FILES.get('photo')
        image_files = {}
        for file_key in request.FILES:
            uploaded = request.FILES.get(file_key)
            if not uploaded:
                continue

            key_l = str(file_key).strip().lower()
            if key_l == 'photo' or key_l.startswith('image_'):
                _ok, _err, validated_file = _unpack_validate_image_result(_validate_image(uploaded), uploaded)
                if not _ok:
                    return JsonResponse({'success': False, 'message': _err}, status=400)

                if key_l == 'photo':
                    legacy_photo = validated_file
                elif key_l.startswith('image_'):
                    image_files[file_key] = validated_file


        with transaction.atomic():
            card = IDCard.objects.create(table=table, field_data=field_data, status='pending')

            if image_files or legacy_photo:
                update_result = IDCardService.update_card(
                    card_id=card.id,
                    field_data={},
                    image_files=image_files,
                    uploaded_by=request.user,
                    legacy_photo_file=legacy_photo,
                    modified_by=getattr(request.user, 'username', '') or None,
                )
                if not update_result.success:
                    raise ValueError(update_result.message or 'Image upload failed')

        try:
            CacheVersionService.bump('mob_filter', int(table.id))
            CacheVersionService.bump('class_section', int(table.group.client_id))
            CacheVersionService.bump('client_dash_counts', f'client:{table.group.client_id}')
            CacheVersionService.bump('global_search', 'all')
        except Exception:
            pass

        return JsonResponse({'success': True, 'message': 'Card added successfully', 'card_id': card.id})
    except ValueError as err:
        return JsonResponse({'success': False, 'message': str(err)}, status=400)
    except Exception:
        import logging as _log
        _log.getLogger(__name__).exception('Card add error')
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=500)


@require_mobile_client
@require_http_methods(["GET"])
def api_table_download_pdf(request, table_id):
    """Download PDF for all cards in a specific table/status (Mobile Wrapper)."""
    user = request.user
    table = get_object_or_404(Table, id=table_id)
    if not OrganisationAccessService.can_access_table(user, table):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
    
    status = request.GET.get('status', 'pending')
    selected_ids_raw = request.GET.get('selected_ids', '')
    search_q = (request.GET.get('search') or '').strip()
    class_f = (request.GET.get('class') or '').strip()
    section_f = (request.GET.get('section') or '').strip()
    photo_f = (request.GET.get('photo') or '').strip().lower()
    
    try:
        from exports.services import ExportService
        service = ExportService(user)
        
        # Fetch base queryset
        qs = IDCard.objects.filter(table=table, status=status)
        
        # Apply filters
        if search_q:
            qs = _search_cards_for_global_results(qs, search_q, limit=None)
        if class_f:
            qs = qs.filter(field_data__CLASS=class_f) # Adjust based on actual JSON field naming
        if section_f:
            qs = qs.filter(field_data__SECTION=section_f)
        if photo_f == 'complete':
            qs = qs.exclude(photo__in=['', 'NOT_FOUND']).exclude(photo__startswith='PENDING:')
        elif photo_f == 'pending':
            qs = qs.filter(photo__startswith='PENDING:')
            
        if selected_ids_raw:
            try:
                selected_ids = [int(i.strip()) for i in selected_ids_raw.split(',') if i.strip()]
                if selected_ids:
                    qs = qs.filter(id__in=selected_ids)
            except (ValueError, TypeError):
                pass

        # Apply row-level scoping
        from core.views.idcard_helpers import _apply_client_staff_row_scope
        qs = _apply_client_staff_row_scope(qs, user, table)
        
        card_ids = list(qs.values_list('id', flat=True))
        
        if not card_ids:
            return JsonResponse({'success': False, 'message': f'No {status} cards to download'}, status=404)
        
        # Trigger PDF generation
        result = service.export_pdf(table_id, card_ids, status=status)
        
        if not result.success:
            return JsonResponse({'success': False, 'message': result.message}, status=400)
            
        return result.response
    except Exception as e:
        logger.exception('Mobile PDF download error')
        return JsonResponse({'success': False, 'message': 'Export failed'}, status=500)


@require_mobile_client
@require_http_methods(["POST"])
def api_card_update(request, table_id, card_id):
    """Update an existing card."""
    from core.services import IDCardService
    try:
        card = get_object_or_404(IDCard.objects.select_related('table__group'), id=card_id, table_id=table_id)
        is_assistant_pool_retrieve = (
            PermissionService.is_client_staff(request.user)
            and card.status == 'pool'
            and PermissionService.has(request.user, 'perm_idcard_retrieve')
        )
        if not is_assistant_pool_retrieve and not _can_access_card_with_row_scope(request.user, card):
            return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
        if not PermissionService.has(request.user, 'perm_idcard_edit') and not is_assistant_pool_retrieve:
            return JsonResponse({'success': False, 'message': 'No permission to edit cards'}, status=403)
        if _is_mobile_client_edit_locked(request.user, card.status) and not is_assistant_pool_retrieve:
            return _mobile_client_edit_locked_response()

        field_data_raw = request.POST.get('field_data', '{}')
        try:
            field_data = json.loads(field_data_raw)
        except json.JSONDecodeError:
            field_data = {}
        if not isinstance(field_data, dict):
            field_data = {}

        from core.services import IDCardService
        if hasattr(card.table, 'fields'):
            field_data = IDCardService.uppercase_field_data_selective(field_data, card.table.fields)

        legacy_photo = request.FILES.get('photo')
        image_files = {}
        for file_key in request.FILES:
            uploaded = request.FILES.get(file_key)
            if not uploaded:
                continue

            key_l = str(file_key).strip().lower()
            if key_l == 'photo' or key_l.startswith('image_'):
                _ok, _err, validated_file = _unpack_validate_image_result(_validate_image(uploaded), uploaded)
                if not _ok:
                    return JsonResponse({'success': False, 'message': _err}, status=400)

                if key_l == 'photo':
                    legacy_photo = validated_file
                elif key_l.startswith('image_'):
                    image_files[file_key] = validated_file

        update_result = IDCardService.update_card(
            card_id=card.id,
            field_data=field_data,
            image_files=image_files,
            uploaded_by=request.user,
            legacy_photo_file=legacy_photo,
            modified_by=getattr(request.user, 'username', '') or None,
        )
        if not update_result.success:
            return JsonResponse({'success': False, 'message': update_result.message or 'Update failed'}, status=400)

        # Construct exact same card serialization as returned in get_cards
        from django.utils.timezone import localtime
        from mediafiles.utils import get_card_photo_url

        card.refresh_from_db()
        fd = card.field_data or {}
        detected_name_field = IDCardService._get_name_field(card.table)
        name = None
        if detected_name_field:
            name = fd.get(detected_name_field)
            if not name:
                for k, v in fd.items():
                    if k.upper() == detected_name_field.upper():
                        name = v
                        break
        name = name or fd.get('NAME') or fd.get('name') or fd.get('Name') or f'Card #{card.id}'
        id_number = (
            fd.get('ID') or 
            fd.get('id') or 
            fd.get('ID_NUMBER') or 
            fd.get('id_number') or
            fd.get('ROLL_NO') or
            fd.get('roll_no') or
            ''
        )
        class_designation = (
            fd.get('CLASS') or 
            fd.get('class') or 
            fd.get('DESIGNATION') or 
            fd.get('designation') or
            ''
        )
        sanitized_field_data = {}
        for key, val in fd.items():
            is_image_field = False
            for field in (card.table.fields or []):
                if not isinstance(field, dict):
                    continue
                fname = field.get('name')
                if fname is None:
                    continue
                fname_str = str(fname).strip()
                if fname_str == key or fname_str.upper() == key.upper():
                    is_image_field = field.get('type') in ['photo', 'image', 'rel_photo', 'mother_photo', 'father_photo', 'barcode', 'qr_code', 'signature', 'image']
                    break
            if not is_image_field and val and isinstance(val, str) and val.startswith('PENDING:'):
                sanitized_field_data[key] = ''
            else:
                sanitized_field_data[key] = val
        card_data = {
            'id': card.id,
            'sr_no': 1,
            'name': name,
            'id_number': id_number,
            'class_designation': class_designation,
            'photo_url': get_card_photo_url(card, fd),
            'field_data': sanitized_field_data,
            'status': card.status,
            'status_display': card.get_status_display(),
            'downloaded_date': localtime(card.downloaded_at).strftime('%Y-%m-%d') if card.downloaded_at else '',
            'created_at': localtime(card.created_at).strftime('%d %b %Y, %H:%M'),
            'updated_at': localtime(card.updated_at).strftime('%d %b %Y, %H:%M'),
        }

        return JsonResponse({
            'success': True,
            'message': 'Card updated successfully',
            'card': card_data
        })
    except Exception:
        logger.exception('Card update error')
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=500)


@require_mobile_client
@require_http_methods(["GET"])
def api_client_groups_detail(request, client_id):
    """Return groups with their tables and card counts for a client (admin only)."""
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    if not PermissionService.can_access_client(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
    from organisation.models import Organisation
    from tables.models import Table
    get_object_or_404(Client, id=client_id)
    groups = Table.objects.filter(client_id=client_id).order_by('name')
    tables_qs = (
        Table.objects
        .filter(group__client_id=client_id, is_active=True)
        .select_related('group')
        .annotate(
            pending_count=Count('id_cards', filter=Q(id_cards__status='pending')),
            verified_count=Count('id_cards', filter=Q(id_cards__status='verified')),
            approved_count=Count('id_cards', filter=Q(id_cards__status='approved')),
            download_count=Count('id_cards', filter=Q(id_cards__status='download')),
            pool_count=Count('id_cards', filter=Q(id_cards__status='pool')),
            total_count=Count('id_cards'),
        )
        .order_by('name')
    )

    is_photographer = PermissionService.is_photographer(request.user)
    uncaptured_counts = {}
    captured_counts = {}
    if is_photographer:
        for t in tables_qs:
            uncaptured_counts[t.id] = 0
            captured_counts[t.id] = 0

        assigned_cards_qs = IDCard.objects.filter(
            table__group__client_id=client_id,
            status__in=['pending', 'verified']
        ).only('id', 'table_id', 'photo', 'field_data')

        for card in assigned_cards_qs.iterator(chunk_size=500):
            has_photo = bool(get_card_photo_url(card))
            t_id = card.table_id
            if t_id in uncaptured_counts:
                if has_photo:
                    captured_counts[t_id] += 1
                else:
                    uncaptured_counts[t_id] += 1

    tables_by_group = {}
    for t in tables_qs:
        gid = t.group_id
        if gid not in tables_by_group:
            tables_by_group[gid] = []
        tables_by_group[gid].append({
            'id': t.id,
            'name': t.name,
            'group_id': t.group_id,
            'fields': t.fields if isinstance(t.fields, list) else [],
            'is_active': t.is_active,
            'pending_count': t.pending_count,
            'verified_count': t.verified_count,
            'approved_count': t.approved_count,
            'download_count': t.download_count,
            'pool_count': t.pool_count,
            'uncaptured_count': uncaptured_counts.get(t.id, 0) if is_photographer else 0,
            'captured_count': captured_counts.get(t.id, 0) if is_photographer else 0,
            'total_count': t.total_count,
        })
    groups_data = []
    for g in groups:
        g_tables = tables_by_group.get(g.id, [])
        groups_data.append({
            'id': g.id,
            'name': g.name,
            'table_count': len(g_tables),
            'total_cards': sum(t['total_count'] for t in g_tables),
            'tables': g_tables,
        })
    return JsonResponse({'success': True, 'groups': groups_data})


@require_mobile_client
@require_http_methods(["POST"])
def api_group_create(request, client_id):
    """Create a new Table for a client."""
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    if not PermissionService.can_access_client(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
    if not PermissionService.has(request.user, 'perm_idcard_setting_add'):
        return JsonResponse({'success': False, 'message': 'Settings add permission required'}, status=403)
    from organisation.models import Organisation
    from tables.models import Table
    target_client = get_object_or_404(Client, id=client_id)
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    name = str(data.get('name', '') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'Group name is required'}, status=400)
    if Table.objects.filter(client=target_client, name__iexact=name).exists():
        return JsonResponse({'success': False, 'message': f'A group named "{name}" already exists'}, status=400)
    group = Table.objects.create(client=target_client, name=name)
    ActivityService.log('group_create', f'Group "{name}" created', request=request, target_model='Table', target_id=group.pk, target_name=name)
    return JsonResponse({'success': True, 'message': f'Group "{name}" created', 'group': {'id': group.id, 'name': group.name, 'table_count': 0, 'total_cards': 0, 'tables': []}})


@require_mobile_client
@require_http_methods(["POST"])
def api_group_update(request, group_id):
    """Rename an Table."""
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    if not PermissionService.has(request.user, 'perm_idcard_setting_edit'):
        return JsonResponse({'success': False, 'message': 'Settings edit permission required'}, status=403)
    from tables.models import Table
    group = get_object_or_404(Table, id=group_id)
    if not PermissionService.can_access_client(request.user, group.client_id):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    name = str(data.get('name', '') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'Group name is required'}, status=400)
    if Table.objects.filter(client_id=group.client_id, name__iexact=name).exclude(id=group_id).exists():
        return JsonResponse({'success': False, 'message': f'A group named "{name}" already exists'}, status=400)
    old_name = group.name
    group.name = name
    group.save(update_fields=['name'])
    ActivityService.log('group_update', f'Group "{old_name}" renamed to "{name}"', request=request, target_model='Table', target_id=group.pk, target_name=name)
    return JsonResponse({'success': True, 'message': f'Group renamed to "{name}"', 'group': {'id': group.id, 'name': group.name}})


@require_mobile_client
@require_http_methods(["POST"])
def api_group_delete(request, group_id):
    """Delete an Table — only if it has no active tables."""
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    if not PermissionService.has(request.user, 'perm_idcard_setting_delete'):
        return JsonResponse({'success': False, 'message': 'Settings delete permission required'}, status=403)
    from tables.models import Table
    group = get_object_or_404(Table, id=group_id)
    if not PermissionService.can_access_client(request.user, group.client_id):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
    active_table_count = Table.objects.filter(group=group, is_active=True).count()
    if active_table_count > 0:
        return JsonResponse({'success': False, 'message': f'Cannot delete group with {active_table_count} active table(s). Delete or move all tables first.'}, status=400)
    name = group.name
    group.delete()
    ActivityService.log('group_delete', f'Group "{name}" deleted', request=request, target_model='Table', target_name=name)
    return JsonResponse({'success': True, 'message': f'Group "{name}" deleted'})


@require_mobile_client
@require_http_methods(["POST"])
def api_table_create(request, group_id):
    """Create a new Table under a group."""
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    if not PermissionService.has(request.user, 'perm_idcard_setting_add'):
        return JsonResponse({'success': False, 'message': 'Settings add permission required'}, status=403)
    from tables.models import Table
    group = get_object_or_404(Table, id=group_id)
    if not PermissionService.can_access_client(request.user, group.client_id):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    name = str(data.get('name', '') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'Table name is required'}, status=400)
    if Table.objects.filter(group=group, name__iexact=name, is_active=True).exists():
        return JsonResponse({'success': False, 'message': f'A table named "{name}" already exists in this group'}, status=400)
    table = Table.objects.create(group=group, name=name, fields=[])
    ActivityService.log('table_create', f'Table "{name}" created in group "{group.name}"', request=request, target_model='Table', target_id=table.pk, target_name=name)
    return JsonResponse({
        'success': True, 'message': f'Table "{name}" created',
        'table': {
            'id': table.id, 'name': table.name, 'group_id': group.id,
            'fields': [], 'is_active': True,
            'pending_count': 0, 'verified_count': 0, 'approved_count': 0,
            'download_count': 0, 'pool_count': 0, 'total_count': 0,
        }
    })


@require_mobile_client
@require_http_methods(["POST"])
def api_table_rename(request, table_id):
    """Rename an Table."""
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    if not PermissionService.has(request.user, 'perm_idcard_setting_edit'):
        return JsonResponse({'success': False, 'message': 'Settings edit permission required'}, status=403)
    table = get_object_or_404(Table, id=table_id)
    if not OrganisationAccessService.can_access_table(request.user, table):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    name = str(data.get('name', '') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'Table name is required'}, status=400)
    if Table.objects.filter(group=table.group, name__iexact=name, is_active=True).exclude(id=table_id).exists():
        return JsonResponse({'success': False, 'message': f'A table named "{name}" already exists in this group'}, status=400)
    old_name = table.name
    table.name = name
    table.save(update_fields=['name'])
    ActivityService.log('table_update', f'Table "{old_name}" renamed to "{name}"', request=request, target_model='Table', target_id=table.pk, target_name=name)
    return JsonResponse({'success': True, 'message': f'Table renamed to "{name}"', 'table': {'id': table.id, 'name': table.name}})


@require_mobile_client
@require_http_methods(["POST"])
def api_table_delete(request, table_id):
    """Soft-delete (deactivate) an Table, or permanently delete if empty."""
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    if not PermissionService.has(request.user, 'perm_idcard_setting_delete'):
        return JsonResponse({'success': False, 'message': 'Settings delete permission required'}, status=403)
    table = get_object_or_404(Table, id=table_id)
    if not OrganisationAccessService.can_access_table(request.user, table):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
    card_count = IDCard.objects.filter(table=table).count()
    if card_count > 0:
        return JsonResponse({'success': False, 'message': f'Cannot delete table with {card_count} card(s). Ensure all cards are removed first.'}, status=400)
    name = table.name
    group_name = table.group.name if table.group else ''
    table.delete()
    ActivityService.log('table_delete', f'Table "{name}" deleted from group "{group_name}"', request=request, target_model='Table', target_name=name)
    return JsonResponse({'success': True, 'message': f'Table "{name}" deleted'})


@require_mobile_client
@require_http_methods(["GET"])
def api_table_fields_get(request, table_id):
    """Return field definitions for a table."""
    table = get_object_or_404(Table, id=table_id)
    if not OrganisationAccessService.can_access_table(request.user, table):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
    return JsonResponse({
        'success': True,
        'table': {
            'id': table.id,
            'name': table.name,
            'fields': table.fields if isinstance(table.fields, list) else [],
        }
    })


@require_mobile_client
@require_http_methods(["POST"])
def api_table_update_fields(request, table_id):
    """Update the column definitions (fields) of an Table.
    Accepts JSON body: { "fields": [{"name": "NAME", "type": "text", "order": 0, "mandatory": false}, ...] }
    """
    try:
        table = get_object_or_404(Table, id=table_id)
        if not OrganisationAccessService.can_access_table(request.user, table):
            return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
        # Table schema changes must follow settings permission, not card-value edit permission.
        if not PermissionService.has(request.user, 'perm_idcard_setting_edit'):
            return JsonResponse({'success': False, 'message': 'Settings edit permission required'}, status=403)

        body = json.loads(request.body or '{}')
        raw_fields = body.get('fields', [])

        if not isinstance(raw_fields, list):
            return JsonResponse({'success': False, 'message': 'fields must be a list'}, status=400)

        VALID_FIELD_TYPES = {
            'text', 'number', 'date', 'select', 'photo', 'signature', 'qr_code',
            'barcode', 'class_section', 'rel_photo', 'email', 'class', 'section',
            'image', 'textarea',
            # Legacy aliases accepted and normalized to rel_photo.
            'mother_photo', 'father_photo',
        }
        MAX_FIELDS = 30

        if len(raw_fields) > MAX_FIELDS:
            return JsonResponse({'success': False, 'message': f'Maximum {MAX_FIELDS} fields allowed'}, status=400)

        old_fields = table.fields if isinstance(table.fields, list) else []
        old_fields_map = {
            str(of.get('name', '')).strip().upper(): of
            for of in old_fields if isinstance(of, dict) and of.get('name')
        }

        validated = []
        for idx, f in enumerate(raw_fields):
            if not isinstance(f, dict):
                continue
            name = str(f.get('name', '')).strip().upper()
            if not name:
                continue
            ftype = f.get('type', 'text')
            if ftype not in VALID_FIELD_TYPES:
                ftype = 'text'
            elif ftype in ('mother_photo', 'father_photo'):
                ftype = 'rel_photo'

            if 'mandatory' in f and f['mandatory'] is not None:
                is_mandatory = bool(f['mandatory'])
            elif name in old_fields_map:
                is_mandatory = bool(old_fields_map[name].get('mandatory', False))
            else:
                is_mandatory = False

            if 'show_path' in f and f['show_path'] is not None:
                is_show_path = bool(f['show_path'])
            elif name in old_fields_map:
                is_show_path = bool(old_fields_map[name].get('show_path', False))
            else:
                is_show_path = False

            field_item = {
                'name': name,
                'type': ftype,
                'order': idx,
                'mandatory': is_mandatory,
            }
            if is_show_path:
                field_item['show_path'] = True

            validated.append(field_item)

        try:
            from importlib import import_module
            ma_views = import_module('mobile_app.views')
            build_fn = getattr(ma_views, '_build_field_rename_pairs', None)
            rename_pairs = build_fn(old_fields, validated) if callable(build_fn) else []
        except Exception:
            # Fallback: no rename pairs
            rename_pairs = []

        with transaction.atomic():
            table.fields = validated
            table.save(update_fields=['fields'])
            try:
                try:
                    from importlib import import_module
                    ma_views = import_module('mobile_app.views')
                except ImportError:
                    ma_views = None
                migrate_cards = getattr(ma_views, '_migrate_table_field_data_for_renames', None) if ma_views else None
                migrate_media = getattr(ma_views, '_migrate_cardmedia_field_names_for_renames', None) if ma_views else None
                cards_updated = migrate_cards(table.id, rename_pairs) if callable(migrate_cards) else 0
                media_updated = migrate_media(table.id, rename_pairs) if callable(migrate_media) else 0
            except Exception:
                cards_updated = 0
                media_updated = 0

        try:
            CacheVersionService.bump('mob_filter', int(table.id))
            CacheVersionService.bump('class_section', int(table.group.client_id))
            CacheVersionService.bump('global_search', 'all')
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'message': 'Column order saved successfully',
            'migrated_card_rows': cards_updated,
            'migrated_media_rows': media_updated,
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    except Exception:
        logger.exception('Table update fields error')
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=500)


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# NEW API VIEWS
# ---------------------------------------------------------------------------

@require_mobile_client
@require_http_methods(["POST"])
def api_card_delete(request, card_id):
    """Delete a single card (move to pool or permanently delete)."""
    try:
        card = get_object_or_404(IDCard.objects.select_related('table__group'), id=card_id)
        user = request.user
        if not _can_access_card_with_row_scope(user, card):
            return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
        data = json.loads(request.body) if request.body else {}
        permanent = data.get('permanent', False)

        if permanent:
            if not PermissionService.has(user, 'perm_idcard_delete_from_pool'):
                return JsonResponse({'success': False, 'message': 'No permanent delete permission'}, status=403)

            if card.status != 'pool':
                return JsonResponse({
                    'success': False,
                    'message': 'Only cards in pool can be permanently deleted',
                }, status=400)

            card_id_for_log = card.id
            table_id_for_cache = card.table_id
            client_id_for_cache = getattr(getattr(card.table, 'group', None), 'client_id', None)
            table_name = card.table.name if card.table_id else ''
            card.delete()
            try:
                CacheVersionService.bump('mob_filter', int(table_id_for_cache))
                if client_id_for_cache:
                    CacheVersionService.bump('class_section', int(client_id_for_cache))
                CacheVersionService.bump('global_search', 'all')
            except Exception:
                pass
            try:
                suffix = f' in table "{table_name}"' if table_name else ''
                ActivityService.log(
                    'bulk_delete',
                    f'1 card deleted via mobile{suffix}',
                    request=request,
                    target_model='IDCard',
                    target_id=card_id_for_log,
                    target_name=f'Card #{card_id_for_log}',
                )
            except Exception:
                logger.exception('Mobile card-delete activity logging failed')
            return JsonResponse({'success': True, 'message': 'Card permanently deleted'})
        else:
            if not PermissionService.has(user, 'perm_idcard_delete'):
                return JsonResponse({'success': False, 'message': 'No delete permission'}, status=403)

            card.status = 'pool'
            card.save(update_fields=['status'])
            try:
                CacheVersionService.bump('global_search', 'all')
                client_id_for_cache = getattr(getattr(card.table, 'group', None), 'client_id', None)
                if client_id_for_cache:
                    CacheVersionService.bump('client_dash_counts', f'client:{client_id_for_cache}')
            except Exception:
                pass
            return JsonResponse({'success': True, 'message': 'Card moved to pool'})
    except Exception:
        logger.exception('Card delete error')
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=500)


@require_mobile_client
@require_http_methods(["GET"])
def api_staff_list(request):
    """List staff for the client.
    
    Authorized for 'client' role and 'operator' with manage permission.
    """
    user = request.user
    
    # Check if user has surface-level permission
    if not _can_manage_client_staff_surface(user):
        return JsonResponse({'success': False, 'message': 'Manage Staff permission required'}, status=403)

    if PermissionService.is_client(user) or PermissionService.is_admin_staff(user):
        # admin_staff managing client staff must be in a client context
        result = OrganisationStaffService.list_staff(user)
        if result.success:
            return JsonResponse({'success': True, 'data': result.data})
        return JsonResponse({'success': False, 'message': result.message}, status=400)
    
    elif PermissionService.is_super_admin(user):
        role = request.GET.get('role', 'operator')
        from core.services.compat_service import CompatibilityService
        role = CompatibilityService.map_role_to_legacy(role)
        if role in ('assistant'):
            # List all client staff system-wide
            # from accounts.models import Staff (removed)
            queryset = Staff.objects.filter(staff_type='assistant').select_related('user', 'client').order_by('-created_at')[:200]
            staff_data = []
            for s in queryset:
                staff_data.append({
                    'id': s.id,
                    'name': s.user.get_full_name() or s.user.username,
                    'email': s.user.email,
                    'phone': getattr(s.user, 'phone', ''),
                    'is_active': s.user.is_active,
                    'client_name': s.client.name if s.client else 'System',
                    'created_at': s.created_at.strftime('%d %b %Y'),
                })
            return JsonResponse({'success': True, 'data': {'staff': staff_data}})
        else:
            # Super admin sees all admin_staff (system-wide)
            staff_data = _list_mobile_admin_staff(limit=200)
            return JsonResponse({'success': True, 'data': {'staff': staff_data}})
        
    return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)


@require_mobile_client
@require_http_methods(["POST"])
def api_staff_create(request):
    """Create a new staff member."""
    user = request.user
    if not _can_manage_client_staff_surface(user):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    if PermissionService.is_super_admin(user):
        payload = dict(data)
        role_requested = str(payload.get('role', '') or '').strip().lower()
        from core.services.compat_service import CompatibilityService
        role_requested = CompatibilityService.map_role_to_legacy(role_requested)

        if role_requested in ('assistant'):
            # Super Admin creating an Assistant (client_staff) for a specific client
            client_id = payload.get('client_id')
            if not client_id:
                return JsonResponse({'success': False, 'message': 'client_id is required to create an assistant'}, status=400)
            try:
                from organisation.models import Organisation
                target_client = Organisation.objects.get(id=int(client_id))
            except Exception:
                return JsonResponse({'success': False, 'message': 'Client not found'}, status=404)
            # Build a minimal fake admin user context scoped to the target client
            # Use OrganisationStaffService with a proxy-like call under the target client
            # Build data dict the service expects (same as client self-creating staff)
            staff_data = dict(payload)
            staff_data.pop('role', None)
            staff_data.pop('client_id', None)
            first_name = str(staff_data.pop('first_name', '') or '').strip()
            last_name = str(staff_data.pop('last_name', '') or '').strip()
            full_name = f'{first_name} {last_name}'.strip() or str(staff_data.get('name', '') or '').strip()
            if not full_name:
                return JsonResponse({'success': False, 'message': 'First name is required'}, status=400)
            staff_data['name'] = full_name
            # StaffService.create accepts client= as a keyword argument (Client instance)
            result = StaffService.create(staff_data, staff_type='assistant', client=target_client, request=request)
        else:
            # Super Admin creating an Operator (admin_staff)
            first_name = str(payload.pop('first_name', '') or '').strip()
            last_name = str(payload.pop('last_name', '') or '').strip()
            full_name = f'{first_name} {last_name}'.strip() or str(payload.get('name', '') or '').strip()
            if not full_name:
                return JsonResponse({'success': False, 'message': 'First name is required'}, status=400)
            payload['name'] = full_name
            result = StaffService.create(payload, staff_type='operator', request=request)
    else:
        result = OrganisationStaffService.create_staff(user, data)

    if result.success:
        return JsonResponse({'success': True, 'message': result.message, **(result.data or {})})
    return JsonResponse({'success': False, 'message': result.message}, status=400)


@require_mobile_client
@require_http_methods(["POST"])
def api_staff_update(request, staff_id):
    """Update a staff member."""
    user = request.user
    if not _can_manage_client_staff_surface(user):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    # Handle temporary password if provided
    temp_pw = data.get('temp_password', '').strip()
    if temp_pw:
        if len(temp_pw) < 8:
            return JsonResponse({'success': False, 'message': 'Password must be at least 8 characters'}, status=400)
        from django.contrib.auth.password_validation import validate_password
        try:
            validate_password(temp_pw)
        except Exception as validation_error:
            return JsonResponse({'success': False, 'message': '; '.join(validation_error.messages)}, status=400)

        if PermissionService.is_super_admin(user):
            pw_result = StaffService.set_temp_password(staff_id, temp_pw, request=request)
        else:
            pw_result = OrganisationStaffService.set_temp_password(user, staff_id, temp_pw, request=request)

        if not pw_result.success:
            return JsonResponse({'success': False, 'message': pw_result.message or 'Failed to set password'}, status=400)

    if PermissionService.is_super_admin(user):
        if not Staff.objects.filter(id=staff_id, staff_type='operator').exists():
            return JsonResponse({'success': False, 'message': 'Staff not found'}, status=404)

        payload = dict(data)
        has_name_parts = ('first_name' in payload) or ('last_name' in payload)
        first_name = str(payload.pop('first_name', '') or '').strip()
        last_name = str(payload.pop('last_name', '') or '').strip()
        if has_name_parts:
            full_name = f'{first_name} {last_name}'.strip()
            if full_name:
                payload['name'] = full_name
            elif not str(payload.get('name', '') or '').strip():
                return JsonResponse({'success': False, 'message': 'First name is required'}, status=400)

        result = StaffService.update(staff_id, payload)
    else:
        result = OrganisationStaffService.update_staff(user, staff_id, data)

    if result.success:
        return JsonResponse({'success': True, 'message': result.message})
    return JsonResponse({'success': False, 'message': result.message}, status=400)


@require_mobile_client
@require_http_methods(["POST"])
def api_staff_toggle(request, staff_id):
    """Toggle staff active/inactive."""
    user = request.user
    if not _can_manage_client_staff_surface(user):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

    if PermissionService.is_client(user) or PermissionService.is_admin_staff(user):
        result = OrganisationStaffService.toggle_staff_status(user, staff_id)
        if result.success:
            return JsonResponse({'success': True, 'message': result.message, **(result.data or {})})
        return JsonResponse({'success': False, 'message': result.message}, status=400)
    else:
        # Admin toggle â€” directly update the Staff user's is_active
        try:
            staff = Staff.objects.select_related('user').get(id=staff_id, staff_type='operator')
            staff.user.is_active = not staff.user.is_active
            staff.user.save(update_fields=['is_active'])
            new_state = 'activated' if staff.user.is_active else 'deactivated'
            return JsonResponse({'success': True, 'message': f'{staff.user.get_full_name() or staff.user.username} {new_state}', 'is_active': staff.user.is_active})
        except Staff.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Staff not found'}, status=404)
        except Exception as exc:
            logger.exception('Admin staff toggle error')
            return JsonResponse({'success': False, 'message': 'An error occurred. Please try again.'}, status=500)


@require_mobile_client
@require_http_methods(["POST"])
def api_staff_delete(request, staff_id):
    """Delete a staff member."""
    user = request.user
    if not _can_manage_client_staff_surface(user):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

    if PermissionService.is_client(user) or PermissionService.is_admin_staff(user):
        # admin_staff can delete client staff if they have permission
        result = OrganisationStaffService.delete_staff(user, staff_id)
        if result.success:
            return JsonResponse({'success': True, 'message': result.message})
        return JsonResponse({'success': False, 'message': result.message}, status=400)
    else:
        try:
            staff = Staff.objects.select_related('user').get(id=staff_id, staff_type='operator')
            staff_id_for_log = staff.id
            name = staff.user.get_full_name() or staff.user.username
            last_active_str = ActivityService._format_last_active(staff.user)
            staff.user.delete()  # cascade deletes staff profile
            try:
                ActivityService.log_staff_delete(request, name, last_active_str, staff_id_for_log)
            except Exception:
                logger.exception('Mobile staff-delete activity logging failed')
            return JsonResponse({'success': True, 'message': f'{name} deleted'})
        except Staff.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Staff not found'}, status=404)
        except Exception as exc:
            logger.exception('Admin staff delete error')
            return JsonResponse({'success': False, 'message': 'An error occurred. Please try again.'}, status=500)


@require_mobile_client
@require_http_methods(["GET"])
def api_staff_assignable_items(request, staff_id):
    """Return groups and tables assignable to a staff member."""
    user = request.user
    if not _can_manage_client_staff_surface(user):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

    try:
        staff = get_object_or_404(Staff, id=staff_id)
        # For client staff, we need their client context
        if staff.staff_type == 'operator':
            # Operator: return all active clients
            from organisation.models import Organisation
            clients = Organisation.objects.filter(status='active').values('id', 'name').order_by('name')
            return JsonResponse({'success': True, 'clients': list(clients)})

        client_id = staff.client_id

        if not PermissionService.can_access_client(user, client_id):
            return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)

        groups = Table.objects.filter(client_id=client_id).values('id', 'name').order_by('name')
        tables = Table.objects.filter(group__client_id=client_id, is_active=True).values('id', 'name', 'group_id').order_by('group__name', 'name')

        return JsonResponse({
            'success': True,
            'groups': list(groups),
            'tables': list(tables)
        })
    except Exception:
        logger.exception('api_staff_assignable_items error')
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=500)


@require_mobile_client
@require_http_methods(["POST"])
def api_staff_assign(request, staff_id):
    """Save assignments for a staff member."""
    user = request.user
    if not _can_manage_client_staff_surface(user):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
        if PermissionService.is_client(user) or PermissionService.is_admin_staff(user):
            target_client = None
            if PermissionService.is_admin_staff(user):
                staff = get_object_or_404(Staff, id=staff_id)
                target_client = staff.client
            # Use update_staff which handles assigned_groups and assigned_table_ids
            result = OrganisationStaffService.update_staff(user, staff_id, data, target_client=target_client)
            if result.success:
                return JsonResponse({'success': True, 'message': 'Assignments updated successfully'})
            return JsonResponse({'success': False, 'message': result.message}, status=400)
        elif PermissionService.is_super_admin(user):
            # Super admin managing admin_staff
            result = StaffService.update(staff_id, data)
            if result.success:
                return JsonResponse({'success': True, 'message': 'Assignments updated successfully'})
            return JsonResponse({'success': False, 'message': result.message}, status=400)
            
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    except Exception:
        logger.exception('api_staff_assign error')
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=500)


@require_mobile_client
@require_http_methods(["GET"])
def api_mobile_staff_assignment(request, staff_id):
    """GET current assignments and scope options for a staff member."""
    user = request.user
    if not _can_manage_client_staff_surface(user):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

    try:
        staff = get_object_or_404(Staff, id=staff_id)
        
        # operator mode (admin_staff / photographer)
        is_operator_mode = staff.staff_type in ('operator', 'photographer')
        
        if is_operator_mode:
            # Operator: return all active clients
            from organisation.models import Organisation
            clients = Organisation.objects.filter(status='active').order_by('name')
            clients_list = [{'id': c.id, 'name': c.name} for c in clients]
            if staff.staff_type == 'photographer':
                from django.utils import timezone
                from django.db.models import Q
                now = timezone.now()
                assigned_clients = list(
                    staff.photographer_assignments.filter(
                        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
                    ).values_list('client_id', flat=True)
                )
            else:
                assigned_clients = list(staff.assigned_organisations.values_list('id', flat=True))
            
            return JsonResponse({
                'success': True,
                'data': {
                    'clients': clients_list,
                    'assigned_organisations': assigned_clients,
                    'groups': [],
                    'tables': [],
                    'assigned_groups': [],
                    'assigned_tables': [],
                    'assignment_scopes': []
                }
            })
            
        # assistant mode (client_staff)
        client_id = staff.client_id
        if not PermissionService.can_access_client(user, client_id):
            return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)

        # Load client's groups and tables
        groups = Table.objects.filter(client_id=client_id).values('id', 'name').order_by('name')
        tables = Table.objects.filter(group__client_id=client_id, deleted_by_client=False).values('id', 'name', 'group_id').order_by('group__name', 'name')
        
        assigned_groups = list(staff.assigned_groups.values_list('id', flat=True))
        assigned_tables = [
            int(v) for v in (staff.assigned_table_ids or [])
            if str(v).strip().isdigit() and int(v) > 0
        ]
        
        # Aggregate distinct classes, sections, branches from this client's card database
        # We build options per group, per table, and globally.
        from tables.models import IDCard
        tables_data = list(Table.objects.filter(group__client_id=client_id, deleted_by_client=False).values('id', 'group_id', 'fields'))
        
        table_fields_meta = {}
        for t in tables_data:
            tid = t['id']
            class_f = None
            section_f = None
            branch_f = None
            for f in (t.get('fields') or []):
                ft = f.get('type', '').lower()
                fn = f.get('name', '')
                fn_lower = fn.lower()
                if ft == 'class' or fn_lower == 'class':
                    class_f = fn
                elif ft == 'section' or fn_lower == 'section':
                    section_f = fn
                elif ft == 'branch' or fn_lower == 'branch' or fn_lower == 'stream' or fn_lower == 'course' or 'branch' in fn_lower or 'stream' in fn_lower or 'course' in fn_lower:
                    branch_f = fn
            table_fields_meta[tid] = (class_f, section_f, branch_f)
            
        cards = IDCard.objects.filter(table__group__client_id=client_id).values('table_id', 'field_data')
        
        group_options = {}
        table_options = {}
        global_sections = set()
        
        group_class_counts = {}
        table_class_counts = {}
        global_class_counts = {}
        
        group_branch_counts = {}
        table_branch_counts = {}
        global_branch_counts = {}
        
        group_class_sections = {}
        table_class_sections = {}
        global_class_sections = {}
        
        # Build maps
        for card in cards:
            tid = card['table_id']
            fd = card['field_data']
            if not fd:
                continue
            
            class_f, section_f, branch_f = table_fields_meta.get(tid, (None, None, None))
            class_val = ''
            section_val = ''
            branch_val = ''
            
            if class_f:
                val = fd.get(class_f) or fd.get(class_f.upper()) or fd.get(class_f.lower())
                if val: class_val = str(val).strip()
            if section_f:
                val = fd.get(section_f) or fd.get(section_f.upper()) or fd.get(section_f.lower())
                if val: section_val = str(val).strip()
            if branch_f:
                val = fd.get(branch_f) or fd.get(branch_f.upper()) or fd.get(branch_f.lower())
                if val: branch_val = str(val).strip()
                
            gid = next((t['group_id'] for t in tables_data if t['id'] == tid), None)
            
            if gid:
                group_options.setdefault(gid, {'sections': set()})
                if section_val: group_options[gid]['sections'].add(section_val)
                
                if class_val:
                    group_class_counts.setdefault(gid, {}).setdefault(class_val, 0)
                    group_class_counts[gid][class_val] += 1
                    group_class_sections.setdefault(gid, {}).setdefault(class_val, set())
                    if section_val: group_class_sections[gid][class_val].add(section_val)
                    
                if branch_val:
                    group_branch_counts.setdefault(gid, {}).setdefault(branch_val, 0)
                    group_branch_counts[gid][branch_val] += 1
                
            table_options.setdefault(tid, {'sections': set()})
            if section_val: table_options[tid]['sections'].add(section_val)
            
            if class_val:
                table_class_counts.setdefault(tid, {}).setdefault(class_val, 0)
                table_class_counts[tid][class_val] += 1
                table_class_sections.setdefault(tid, {}).setdefault(class_val, set())
                if section_val: table_class_sections[tid][class_val].add(section_val)
                
            if branch_val:
                table_branch_counts.setdefault(tid, {}).setdefault(branch_val, 0)
                table_branch_counts[tid][branch_val] += 1
            
            if section_val: global_sections.add(section_val)
            
            if class_val:
                global_class_counts.setdefault(class_val, 0)
                global_class_counts[class_val] += 1
                global_class_sections.setdefault(class_val, set())
                if section_val: global_class_sections[class_val].add(section_val)
                
            if branch_val:
                global_branch_counts.setdefault(branch_val, 0)
                global_branch_counts[branch_val] += 1
                
        from core.utils.field_utils import normalize_class_value, normalize_compact_text_value, CLASS_ORDER, CLASS_ORDER_UNKNOWN
        from collections import defaultdict

        def resolve_normalized_options(counts_dict, normalizer):
            groups = defaultdict(list)
            for raw, count in counts_dict.items():
                canonical = normalizer(raw)
                if canonical:
                    groups[canonical].append((raw, count))
            
            raw_to_best = {}
            best_options = []
            for canonical, variants in groups.items():
                best_raw = max(variants, key=lambda x: x[1])[0]
                best_options.append(best_raw)
                for raw, _ in variants:
                    raw_to_best[raw] = best_raw
            return raw_to_best, best_options

        def sort_classes(classes_list):
            return sorted(classes_list, key=lambda x: (CLASS_ORDER.get(normalize_class_value(x), CLASS_ORDER_UNKNOWN), normalize_class_value(x)))

        group_options_json = {}
        for gid, opt in group_options.items():
            c_raw_to_best, c_best = resolve_normalized_options(group_class_counts.get(gid, {}), normalize_class_value)
            b_raw_to_best, b_best = resolve_normalized_options(group_branch_counts.get(gid, {}), normalize_compact_text_value)
            
            cls_secs = defaultdict(set)
            for c_raw, s_set in group_class_sections.get(gid, {}).items():
                best_cls = c_raw_to_best.get(c_raw, c_raw)
                cls_secs[best_cls].update(s_set)
                
            group_options_json[str(gid)] = {
                'classes': sort_classes(c_best),
                'sections': sorted(opt['sections']),
                'branches': sorted(b_best),
                'class_sections': {k: sorted(list(v)) for k, v in cls_secs.items()}
            }
            
        table_options_json = {}
        for tid, opt in table_options.items():
            c_raw_to_best, c_best = resolve_normalized_options(table_class_counts.get(tid, {}), normalize_class_value)
            b_raw_to_best, b_best = resolve_normalized_options(table_branch_counts.get(tid, {}), normalize_compact_text_value)
            
            cls_secs = defaultdict(set)
            for c_raw, s_set in table_class_sections.get(tid, {}).items():
                best_cls = c_raw_to_best.get(c_raw, c_raw)
                cls_secs[best_cls].update(s_set)
                
            table_options_json[str(tid)] = {
                'classes': sort_classes(c_best),
                'sections': sorted(opt['sections']),
                'branches': sorted(b_best),
                'class_sections': {k: sorted(list(v)) for k, v in cls_secs.items()}
            }
            
        glb_c_raw_to_best, glb_c_best = resolve_normalized_options(global_class_counts, normalize_class_value)
        glb_b_raw_to_best, glb_b_best = resolve_normalized_options(global_branch_counts, normalize_compact_text_value)
        
        glb_cls_secs = defaultdict(set)
        for c_raw, s_set in global_class_sections.items():
            best_cls = glb_c_raw_to_best.get(c_raw, c_raw)
            glb_cls_secs[best_cls].update(s_set)
            
        global_options = {
            'classes': sort_classes(glb_c_best),
            'sections': sorted(global_sections),
            'branches': sorted(glb_b_best),
            'class_sections': {k: sorted(list(v)) for k, v in glb_cls_secs.items()}
        }
        
        # Fallback assignment modes
        from organisation.models import Organisation
        target_client = Organisation.objects.filter(id=client_id).first()
        group_count = len(groups)
        inferred_id_source = 'table' if group_count <= 1 else 'group'
        assignment_id_source = 'table' if target_client and getattr(target_client, 'assignment_id_source', '') == 'table' else inferred_id_source
        
        return JsonResponse({
            'success': True,
            'data': {
                'groups': list(groups),
                'tables': list(tables),
                'assigned_groups': assigned_groups,
                'assigned_tables': assigned_tables,
                'assignment_scopes': staff.assignment_scopes or [],
                'assignment_id_source': assignment_id_source,
                'id_source': assignment_id_source,
                'class_section_options': global_options,
                'group_options': group_options_json,
                'table_options': table_options_json
            }
        })
    except Exception:
        logger.exception('api_mobile_staff_assignment error')
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=500)


@require_mobile_client
@require_http_methods(["POST"])
def api_mobile_staff_assignment_update(request, staff_id):
    """POST to save assignments for a staff member (compatible with React Native)."""
    user = request.user
    if not _can_manage_client_staff_surface(user):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
        
        # React Native sends { group_ids, table_ids, client_ids, assignment_scopes }
        # We need to translate them to the payload shape expected by OrganisationStaffService or StaffService
        payload = {
            'assigned_groups': data.get('group_ids', []),
            'assigned_tables': data.get('table_ids', []),
            'assigned_organisations': data.get('client_ids', []),
            'assignment_scopes': data.get('assignment_scopes', [])
        }
        
        staff = get_object_or_404(Staff, id=staff_id)
        if staff.staff_type == 'operator':
            # Operator mode
            if not PermissionService.is_super_admin(user):
                return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
            # StaffService.update takes client_ids key
            operator_payload = {
                'client_ids': payload['assigned_organisations']
            }
            result = StaffService.update(staff_id, operator_payload)
        else:
            # Client staff assistant mode
            client_id = staff.client_id
            from organisation.models import Organisation
            target_client = Organisation.objects.filter(id=client_id).first()
            
            req_id_source = data.get('assignment_id_source', '').lower()
            if req_id_source in ('group', 'table'):
                id_source = req_id_source
            else:
                group_count = Table.objects.filter(client_id=client_id).count()
                id_source = 'table' if group_count <= 1 else 'group'
                if target_client and getattr(target_client, 'assignment_id_source', '') == 'table':
                    id_source = 'table'
                
            client_staff_payload = {
                'assigned_groups': payload['assigned_tables'] if id_source == 'table' else payload['assigned_groups'],
                'assignment_id_source': id_source,
                'assignment_scopes': payload['assignment_scopes']
            }
            result = OrganisationStaffService.update_staff(user, staff_id, client_staff_payload, target_client=target_client)

        if result.success:
            return JsonResponse({'success': True, 'message': 'Assignments updated successfully'})
        return JsonResponse({'success': False, 'message': result.message}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    except Exception:
        logger.exception('api_mobile_staff_assignment_update error')
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=500)


# ─── Native App JSON APIs (for React Native) ───

@require_mobile_client
@require_http_methods(["GET"])
def api_profile_data(request):
    """Return current user profile data as JSON for native app."""
    try:
        user = request.user
        client, perms = _client_ctx(user)
        return JsonResponse({
            'success': True,
            'data': {
                'name': user.get_full_name() or user.username,
                'email': user.email or '',
                'phone': getattr(user, 'phone', '') or '',
                'role': _map_role_compat(getattr(user, 'role', '')),
                'client_id': getattr(client, 'id', None) if client else None,
                'client_name': getattr(client, 'name', '') if client else '',
                'is_super_admin': PermissionService.is_super_admin(user),
                'is_client': PermissionService.is_client(user),
                'is_admin_staff': PermissionService.is_admin_staff(user),
                'can_manage_clients': _can_manage_clients_surface(user),
                'can_manage_staff': _can_manage_client_staff_surface(user),
                'permissions': perms,
            }
        })
    except Exception:
        logger.exception('api_profile_data error')
        return JsonResponse({'success': False, 'message': 'Unable to load profile.'}, status=500)


@require_mobile_client
@require_http_methods(["GET"])
def api_notifications_list(request):
    """Return notification list as JSON for native app."""
    try:
        # Use the comprehensive notification helper
        notifs, _ = _get_system_notifications(request.user, limit=50, mark_visible_as_read=True)

        priority_to_color = {
            'low': 'blue',
            'normal': 'purple',
            'high': 'orange',
            'urgent': 'red'
        }

        items = []
        for n in notifs:
            items.append({
                'id': n['id'],
                'title': n['title'] or '',
                'message': n['message'] or '',
                'icon': n['icon_class'] or 'bell',
                'color': priority_to_color.get(n['priority'], 'blue'),
                'read': n['is_read'],
                'time': n['created_at'],
            })
        return JsonResponse({'success': True, 'data': items})
    except Exception:
        logger.exception('api_notifications_list error')
        return JsonResponse({'success': False, 'message': 'Unable to load notifications.'}, status=500)



@require_mobile_client
@require_http_methods(["GET"])
def api_messages_list(request):
    """Return client messages sent by admin."""
    try:
        from core.models import ClientMessage, NotificationRead
        from django.db.models import Exists, OuterRef, Q as _Q
        
        user = request.user
        client = OrganisationAccessService.get_organisation_for_user(user)
        if not client:
            return JsonResponse({'success': True, 'data': []})

        now = timezone.now()
        base_qs = (
            ClientMessage.objects
            .filter(
                client_id=client.id,
                notification__is_active=True,
                notification__target='selected',
                notification__target_users=user,
            )
            .filter(_Q(visibility='permanent') | _Q(expires_at__gt=now))
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
            )[:50]
        )

        items = []
        unread_notif_ids = []
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
                'created_at': row.created_at.strftime('%d %b %Y'),
                'sent_by_name': sender_name,
                'read': bool(getattr(row, 'is_read', False)),
            })
            if not getattr(row, 'is_read', False) and row.notification_id:
                unread_notif_ids.append(row.notification_id)

        # Automatically mark unread messages as read upon retrieval
        if unread_notif_ids:
            NotificationRead.objects.bulk_create(
                [NotificationRead(user=user, notification_id=nid) for nid in unread_notif_ids],
                ignore_conflicts=True,
            )
            cache.delete(f'mobile:notif_count:{user.pk}')

        return JsonResponse({'success': True, 'data': items})
    except Exception:
        logger.exception('api_messages_list error')
        return JsonResponse({'success': False, 'message': 'Unable to load messages.'}, status=500)



@require_mobile_client
@require_http_methods(["GET"])
def api_tables_list(request):
    """Return list of accessible tables for mobile picker screen."""
    try:
        user = request.user
        status = (request.GET.get('status') or '').strip().lower()
        
        # 1. Get accessible tables
        from tables.models import Table
        tables_qs = Table.objects.filter(is_active=True, deleted_by_client=False)
        
        if not PermissionService.is_super_admin(user):
            # For non-superadmins, we must restrict by client or assigned IDs
            if PermissionService.is_admin_staff(user):
                accessible_client_ids = PermissionService.get_accessible_client_ids(user)
                if accessible_client_ids:
                    tables_qs = tables_qs.filter(group__client_id__in=accessible_client_ids)
                else:
                    return JsonResponse({'success': True, 'data': [], 'tables': [], 'count': 0})
            else:
                # Regular client/client_staff
                client, _ = _client_ctx(user)
                if not client:
                    return JsonResponse({'success': False, 'message': 'No client context'}, status=400)
                tables_qs = tables_qs.filter(group__client=client)

        if PermissionService.is_client_staff(user):
            tables_qs = OrganisationAccessService.get_scoped_tables_qs(user, client, tables_qs)
            if not tables_qs.exists():
                return JsonResponse({'success': True, 'data': [], 'tables': [], 'count': 0})

        items = []
        is_staff = PermissionService.is_client_staff(user)
        
        # 2. Annotate with status count if status is provided
        # 'total' is a virtual status from the native app — treat like 'all'
        if not is_staff:
            if status and status not in ('all', 'total'):
                tables_qs = tables_qs.annotate(
                    status_count=Count('id_cards', filter=Q(id_cards__status=status))
                ).filter(status_count__gt=0)
            else:
                tables_qs = tables_qs.annotate(status_count=Count('id_cards'))

        tables_list = list(tables_qs.select_related('group', 'group__client').order_by('name'))
        for t in tables_list:
            if is_staff:
                card_qs = OrganisationCardService._apply_client_staff_row_scope(user, t, IDCard.objects.filter(table_id=t.id))
                if status and status not in ('all', 'total'):
                    t_status_count = card_qs.filter(status=status).count()
                    if t_status_count == 0:
                        continue
                    t.status_count = t_status_count
                else:
                    t.status_count = card_qs.count()

            items.append({
                'id': t.id,
                'name': t.name,
                'group_name': t.group.name if t.group else '',
                'client_name': t.group.client.name if t.group and t.group.client else '',
                'status_count': getattr(t, 'status_count', 0),
            })

        return JsonResponse({'success': True, 'data': items})
    except Exception:
        logger.exception('api_tables_list error')
        return JsonResponse({'success': False, 'message': 'Unable to load tables.'}, status=500)


@require_mobile_client
@require_http_methods(["GET"])
def api_groups_list(request):
    """Return groups with tables + status counts as JSON for native groups screen."""
    try:
        user = request.user
        # 1. Get accessible tables
        from tables.models import Table
        tables_qs = Table.objects.filter(is_active=True, deleted_by_client=False)
        
        if not PermissionService.is_super_admin(user):
            # For non-superadmins, we must restrict by client or assigned IDs
            if PermissionService.is_admin_staff(user):
                accessible_client_ids = PermissionService.get_accessible_client_ids(user)
                if accessible_client_ids:
                    tables_qs = tables_qs.filter(group__client_id__in=accessible_client_ids)
                else:
                    return JsonResponse({'success': True, 'data': {'groups': [], 'tables': []}})
            else:
                # Regular client/client_staff
                client, _ = _client_ctx(user)
                if not client:
                    return JsonResponse({'success': False, 'message': 'No client context'}, status=400)
                tables_qs = tables_qs.filter(group__client=client)

        if PermissionService.is_client_staff(user):
            tables_qs = OrganisationAccessService.get_scoped_tables_qs(user, client, tables_qs)
            if not tables_qs.exists():
                return JsonResponse({'success': True, 'data': {'groups': [], 'tables': []}})

        if PermissionService.is_client_staff(user):
            # Compute scoped counts table-by-table for assistant
            tables_list = list(tables_qs.order_by('name'))
            
            # Bulk fetch pool counts for all tables to avoid N+1 queries
            table_ids = [t.id for t in tables_list]
            pool_counts = {}
            if table_ids:
                for row in IDCard.objects.filter(table_id__in=table_ids, status='pool').values('table_id').annotate(n=Count('id')):
                    pool_counts[row['table_id']] = row['n']
                    
            tables_annotated = []
            for t in tables_list:
                table_cards_qs = OrganisationCardService._apply_client_staff_row_scope(
                    user,
                    t,
                    IDCard.objects.filter(table_id=t.id)
                )
                
                # Get scoped status counts (excluding pool)
                t_counts = {'pending': 0, 'verified': 0, 'approved': 0, 'download': 0, 'reprint': 0}
                for row in table_cards_qs.exclude(status='pool').values('status').annotate(n=Count('id')):
                    status_val = row['status']
                    if status_val in t_counts:
                        t_counts[status_val] = row['n']
                
                # Pool cards count is the full table pool count (unfiltered)
                t_counts['pool'] = pool_counts.get(t.id, 0)
                
                # total_cards excludes pool to match desktop
                t.total_cards = t_counts['pending'] + t_counts['verified'] + t_counts['approved'] + t_counts['download']
                t.pending_cards = t_counts['pending']
                t.verified_cards = t_counts['verified']
                t.approved_cards = t_counts['approved']
                t.download_cards = t_counts['download']
                t.pool_cards = t_counts['pool']
                t.reprint_cards = t_counts['reprint']
                
                tables_annotated.append(t)
        else:
            tables_annotated = list(tables_qs.annotate(
                pending_cards=Count('id_cards', filter=Q(id_cards__status='pending')),
                verified_cards=Count('id_cards', filter=Q(id_cards__status='verified')),
                approved_cards=Count('id_cards', filter=Q(id_cards__status='approved')),
                download_cards=Count('id_cards', filter=Q(id_cards__status='download')),
                pool_cards=Count('id_cards', filter=Q(id_cards__status='pool')),
                reprint_cards=Count('id_cards', filter=Q(id_cards__status='reprint')),
            ).order_by('name'))
            for t in tables_annotated:
                t.total_cards = t.pending_cards + t.verified_cards + t.approved_cards + t.download_cards

        # 2. Get groups that contain at least one accessible table
        accessible_group_ids = {t.group_id for t in tables_annotated}
        groups = Table.objects.filter(id__in=accessible_group_ids).order_by('name')

        groups_data = []
        for g in groups:
            g_tables = [t for t in tables_annotated if t.group_id == g.id]
            groups_data.append({
                'id': g.id,
                'name': g.name,
                'table_count': len(g_tables),
                'total_cards': sum(t.total_cards for t in g_tables),
                'pending_cards': sum(t.pending_cards for t in g_tables),
                'verified_cards': sum(t.verified_cards for t in g_tables),
                'approved_cards': sum(t.approved_cards for t in g_tables),
                'download_cards': sum(t.download_cards for t in g_tables),
                'pool_cards': sum(t.pool_cards for t in g_tables),
                'reprint_cards': sum(t.reprint_cards for t in g_tables),
            })

        tables_data = [{
            'id': t.id,
            'name': t.name,
            'group_id': t.group_id,
            'total_cards': t.total_cards,
            'pending_cards': t.pending_cards,
            'verified_cards': t.verified_cards,
            'approved_cards': t.approved_cards,
            'download_cards': t.download_cards,
            'pool_cards': t.pool_cards,
            'reprint_cards': t.reprint_cards
        } for t in tables_annotated]

        return JsonResponse({'success': True, 'data': {'groups': groups_data, 'tables': tables_data}})
    except Exception:
        logger.exception('api_groups_list error')
        return JsonResponse({'success': False, 'message': 'Unable to load groups.'}, status=500)


@require_mobile_client
@require_http_methods(["GET"])
def api_settings_data(request):
    """Return settings page data as JSON for native settings screen."""
    try:
        user = request.user
        client, perms = _client_ctx(user)
        if not client:
            return JsonResponse({'success': False, 'message': 'No client context'}, status=400)

        d = {}
        d['table_count'] = Table.objects.filter(group__client=client, is_active=True).count()
        d['group_count'] = Table.objects.filter(client=client).count()
        d['total_cards'] = IDCard.objects.filter(table__group__client=client).count()

        if PermissionService.is_any_admin(user):
            from organisation.models import Organisation as _Client
            accessible_ids = _admin_accessible_client_ids(user)
            _c = _Client.objects.filter(status='active')
            _t = Table.objects.filter(is_active=True)
            _cd = IDCard.objects.all()
            _st = Staff.objects.all()
            if accessible_ids is not None:
                _c = _c.filter(id__in=accessible_ids)
                _t = _t.filter(group__client_id__in=accessible_ids)
                _cd = _cd.filter(table__group__client_id__in=accessible_ids)
                _st = _st.filter(
                    Q(client_id__in=accessible_ids) | 
                    Q(staff_type='operator', assigned_clients__id__in=accessible_ids) |
                    Q(staff_type='photographer', photographer_assignments__client_id__in=accessible_ids)
                ).distinct()
            d['admin_client_count'] = _c.count()
            d['admin_staff_count'] = _st.count()
            d['admin_table_count'] = _t.count()
            d['admin_total_cards'] = _cd.count()

        # Recent logs
        from django.utils.timesince import timesince as _timesince
        from django.utils import timezone as _tz
        _now = _tz.now()
        _cards = list(IDCard.objects.filter(table__group__client=client).select_related('table', 'table__group').order_by('-updated_at')[:15])
        d['log_activities'] = [{'name': (c.field_data or {}).get('NAME') or (c.field_data or {}).get('name') or f'Card #{c.id}', 'status': c.status, 'status_display': c.status.replace('_', ' ').title(), 'updated_at': _timesince(c.updated_at, _now) if c.updated_at else 'â€”', 'table_name': c.table.name if c.table else '', 'group_name': c.table.group.name if c.table and c.table.group else ''} for c in _cards]

        # System info
        import django as _dj, sys as _sy, os as _o
        try:
            with open(_o.path.join(settings.BASE_DIR, 'VERSION.txt')) as _vf:
                d['app_version'] = _vf.read().strip()
        except Exception:
            d['app_version'] = str(getattr(settings, 'APP_VERSION', 'v0.00.00') or 'v0.00.00')
        d['django_version'] = _dj.__version__
        d['python_version'] = f'{_sy.version_info.major}.{_sy.version_info.minor}.{_sy.version_info.micro}'
        d['debug_mode'] = settings.DEBUG

        return JsonResponse({'success': True, 'data': d})
    except Exception:
        logger.exception('api_settings_data error')
        return JsonResponse({'success': False, 'message': 'Unable to load settings.'}, status=500)


@require_mobile_client
@require_http_methods(["GET"])
def api_dashboard_data(request):
    """Return dashboard status counts as JSON for native home screen.
    
    For admin/operator: Returns clients list with nested tables.
    For client/assistant: Returns single client with tables.
    """
    try:
        user = request.user
        from django.core.cache import cache
        from core.services.cache_version_service import CacheVersionService
        from core.services.activity_service import ActivityService
        from organisation.models import Organisation
        from core.models import User
        from django.db.models import Max

        
        is_admin = PermissionService.is_super_admin(user) or PermissionService.is_admin_staff(user)
        is_photographer = PermissionService.is_photographer(user)
        is_staff = PermissionService.is_client_staff(user)
        
        # Recent Activity (Always included for all roles)
        recent_activity = ActivityService.get_recent(limit=100, user=user)
        
        # Enrich activity entries with table_id for IDCard entries (for mobile navigation)
        idcard_activity_ids = [
            a['target_id'] for a in recent_activity
            if str(a.get('target_model', '')).lower() == 'idcard' and a.get('target_id')
        ]
        if idcard_activity_ids:
            idcard_table_map = dict(
                IDCard.objects.filter(id__in=idcard_activity_ids).values_list('id', 'table_id')
            )
            for a in recent_activity:
                if str(a.get('target_model', '')).lower() == 'idcard' and a.get('target_id'):
                    a['table_id'] = idcard_table_map.get(a['target_id'])
        
        if is_admin or is_photographer:
            # ADMIN/OPERATOR/PHOTOGRAPHER: Return clients with nested tables
            cache_version = CacheVersionService.get('admin_dash_counts', 'global')
            if is_photographer:
                cache_key = f"mob_dash_photo_{user.id}_v{cache_version}"
            else:
                cache_key = f"mob_dash_admin_{user.id}_v{cache_version}"
            cached_data = cache.get(cache_key)
            if cached_data:
                cached_data['recent_activity'] = recent_activity
                return JsonResponse({'success': True, 'data': cached_data})
            
            # Get accessible clients
            if PermissionService.is_super_admin(user):
                # Super admins see EVERYTHING (active or not) to match system-wide data visibility
                clients_qs = Organisation.objects.all()
            else:  # admin_staff or photographer
                accessible_ids = PermissionService.get_accessible_client_ids(user) or []
                clients_qs = Organisation.objects.filter(id__in=accessible_ids)

            if is_photographer:
                # Fetch active tables for assigned clients
                tables_qs = (
                    Table.objects
                    .filter(group__client_id__in=accessible_ids, deleted_by_client=False, is_active=True)
                    .select_related('group')
                )
                
                table_to_client_map = {}
                for t in tables_qs:
                    client_id = getattr(t.group, 'client_id', None)
                    if client_id is not None:
                        table_to_client_map[t.id] = client_id
                
                # Initialize count dictionaries
                table_counts = {t.id: {'captured': 0, 'uncaptured': 0} for t in tables_qs}
                client_counts = {cid: {'captured': 0, 'uncaptured': 0} for cid in accessible_ids}
                
                global_captured = 0
                global_uncaptured = 0
                
                # Fetch pending & verified cards for these clients
                assigned_cards_qs = IDCard.objects.filter(
                    table__group__client_id__in=accessible_ids,
                    status__in=['pending', 'verified']
                ).only('id', 'table_id', 'photo', 'field_data')
                
                for card in assigned_cards_qs.iterator(chunk_size=500):
                    has_photo = bool(get_card_photo_url(card))
                    t_id = card.table_id
                    cid = table_to_client_map.get(t_id)
                    
                    if has_photo:
                        global_captured += 1
                        if t_id in table_counts:
                            table_counts[t_id]['captured'] += 1
                        if cid in client_counts:
                            client_counts[cid]['captured'] += 1
                    else:
                        global_uncaptured += 1
                        if t_id in table_counts:
                            table_counts[t_id]['uncaptured'] += 1
                        if cid in client_counts:
                            client_counts[cid]['uncaptured'] += 1
                
                global_counts = {
                    'captured': global_captured,
                    'uncaptured': global_uncaptured,
                    'client_count': len(accessible_ids),
                    'operator_count': User.objects.filter(role__in=('operator'), is_active=True).count(),
                    'assistant_count': User.objects.filter(role__in=('assistant', 'prime_manager', 'manager'), is_active=True).count(),
                }
                
                ordered_clients = list(clients_qs.annotate(
                    latest_approved=Max(
                        'id_card_groups__tables__id_cards__updated_at',
                        filter=Q(id_card_groups__tables__id_cards__status='approved')
                    )
                ).order_by(
                    F('latest_approved').desc(nulls_last=True),
                    F('created_at').desc(nulls_last=True),
                    F('id').desc(),
                )[:100])
                
                from collections import defaultdict
                tables_by_client = defaultdict(list)
                for t in tables_qs:
                    client_id = getattr(t.group, 'client_id', None)
                    if client_id is not None:
                        tables_by_client[client_id].append(t)
                
                clients_data = []
                for client in ordered_clients:
                    c_counts = client_counts.get(client.id, {'captured': 0, 'uncaptured': 0})
                    
                    tables_data = []
                    tables_for_client = tables_by_client.get(client.id, [])
                    for t in tables_for_client[:20]:
                        t_counts = table_counts.get(t.id, {'captured': 0, 'uncaptured': 0})
                        tables_data.append({
                            'id': t.id,
                            'name': t.name,
                            'group': t.group.name if t.group else '',
                            'captured': t_counts['captured'],
                            'uncaptured': t_counts['uncaptured'],
                        })
                    
                    clients_data.append({
                        'id': Organisation.id,
                        'name': getattr(client, 'business_name', client.name),
                        'captured': c_counts['captured'],
                        'uncaptured': c_counts['uncaptured'],
                        'tables': tables_data,
                    })
                
                counts = {
                    **global_counts,
                    'recent_clients': clients_data,
                    'recent_activity': recent_activity,
                    'recent_reprints': [],
                    'is_photographer': True,
                    'is_admin': False
                }
                
                cache.set(cache_key, counts, timeout=600)
                return JsonResponse({'success': True, 'data': counts})
            
            # --- Efficient Global Counts ---
            card_qs = IDCard.objects.all()
            if not PermissionService.is_super_admin(user):
                card_qs = card_qs.filter(table__group__client_id__in=accessible_ids)
            
            global_counts_agg = card_qs.aggregate(
                total=Count('id', filter=Q(status__in=['pending', 'verified', 'approved', 'download'])),
                pending=Count('id', filter=Q(status='pending')),
                verified=Count('id', filter=Q(status='verified')),
                approved=Count('id', filter=Q(status='approved')),
                download=Count('id', filter=Q(status='download')),
                pool=Count('id', filter=Q(status='pool')),
            )
            global_counts = {
                'pending': global_counts_agg.get('pending', 0),
                'verified': global_counts_agg.get('verified', 0),
                'approved': global_counts_agg.get('approved', 0),
                'download': global_counts_agg.get('download', 0),
                'pool': global_counts_agg.get('pool', 0),
                'total': global_counts_agg.get('total', 0),
                'client_count': clients_qs.count(),
                'operator_count': User.objects.filter(role__in=('operator'), is_active=True).count(),
                'assistant_count': User.objects.filter(role__in=('assistant', 'prime_manager', 'manager'), is_active=True).count(),
            }
            
            clients_data = []
 
            # Order clients identically to the dashboard: latest approved cards first, then latest created.
            ordered_clients = list(clients_qs.annotate(
                latest_approved=Max(
                    'id_card_groups__tables__id_cards__updated_at',
                    filter=Q(id_card_groups__tables__id_cards__status='approved')
                )
            ).order_by(
                F('latest_approved').desc(nulls_last=True),
                F('created_at').desc(nulls_last=True),
                F('id').desc(),
            )[:100])
 
            # Batch-fetch tables and card counts to avoid N+1 queries per client
            client_ids = [c.id for c in ordered_clients]
 
            # Tables with per-table counts
            tables_qs = (
                Table.objects
                .filter(group__client_id__in=client_ids, deleted_by_client=False)
                .annotate(
                    cnt_p=Count('id_cards', filter=Q(id_cards__status='pending')),
                    cnt_v=Count('id_cards', filter=Q(id_cards__status='verified')),
                    cnt_a=Count('id_cards', filter=Q(id_cards__status='approved')),
                    cnt_d=Count('id_cards', filter=Q(id_cards__status='download')),
                    cnt_po=Count('id_cards', filter=Q(id_cards__status='pool')),
                )
                .select_related('group')
            )
            if not PermissionService.is_super_admin(user):
                tables_qs = tables_qs.filter(is_active=True)
 
            from collections import defaultdict
            tables_by_client = defaultdict(list)
            for t in tables_qs:
                # group__client_id should be present via select_related on group
                client_id = getattr(t.group, 'client_id', None) if getattr(t, 'group', None) else None
                if client_id is None:
                    # Fallback: try group__client_id via attribute access
                    client_id = getattr(t, 'group_id', None)
                tables_by_client[client_id].append(t)
 
            # Aggregate card status counts per client in one query
            status_rows = IDCard.objects.filter(table__group__client_id__in=client_ids).values('table__group__client_id', 'status').annotate(n=Count('id'))
            client_counts_map = {cid: {'pending': 0, 'verified': 0, 'approved': 0, 'download': 0, 'pool': 0} for cid in client_ids}
            for row in status_rows:
                cid = row.get('table__group__client_id')
                st = row.get('status')
                if cid in client_counts_map and st in client_counts_map[cid]:
                    client_counts_map[cid][st] = row.get('n', 0)
 
            for client in ordered_clients:
                client_counts = client_counts_map.get(client.id, {'pending': 0, 'verified': 0, 'approved': 0, 'download': 0, 'pool': 0})
 
                tables_data = []
                tables_for_client = tables_by_client.get(client.id, [])
                # Limit to 20 as before; tables_qs is already filtered by is_active when needed
                for t in tables_for_client[:20]:
                    tables_data.append({
                        'id': t.id,
                        'name': t.name,
                        'group': t.group.name if t.group else '',
                        'p': getattr(t, 'cnt_p', 0),
                        'v': getattr(t, 'cnt_v', 0),
                        'a': getattr(t, 'cnt_a', 0),
                        'd': getattr(t, 'cnt_d', 0),
                        'po': getattr(t, 'cnt_po', 0),
                    })
 
                clients_data.append({
                    'id': Organisation.id,
                    'name': getattr(client, 'business_name', client.name),
                    'pending': client_counts.get('pending', 0),
                    'verified': client_counts.get('verified', 0),
                    'approved': client_counts.get('approved', 0),
                    'download': client_counts.get('download', 0),
                    'pool': client_counts.get('pool', 0),
                    'tables': tables_data,
                })
            
            recent_reprints = []
            if is_admin:
                from reprintcard.models import ReprintRequest
                reprints_qs = ReprintRequest.objects.filter(status__in=['requested', 'confirmed']).select_related('card', 'table', 'requested_by', 'table__group__client').order_by('-created_at')
                if not PermissionService.is_super_admin(user):
                    reprints_qs = reprints_qs.filter(table__group__client_id__in=accessible_ids)
                
                for r in reprints_qs[:1000]:
                    recent_reprints.append({
                        'id': r.id,
                        'card_id': r.card_id,
                        'client_id': r.table.group.client_id if r.table and r.table.group else 0,
                        'client_name': getattr(r.table.group.client, 'business_name', r.table.group.client.name) if r.table and r.table.group and r.table.group.client else 'Unknown',
                        'table_id': r.table_id,
                        'table_name': r.table.name if r.table else 'Unknown Table',
                        'group_name': r.table.group.name if r.table and r.table.group else 'Unknown Group',
                        'status': r.status,
                        'reason': r.reason,
                        'requested_by': r.requested_by.get_full_name() if r.requested_by else 'Unknown',
                        'time_ago': timesince(r.created_at, timezone.now()) + ' ago',
                        'created_at': r.created_at.isoformat(),
                    })
 
            counts = {
                **global_counts,
                'recent_clients': clients_data,
                'recent_activity': recent_activity,
                'recent_reprints': recent_reprints,
                'is_admin': True
            }
            
            cache.set(cache_key, counts, timeout=600) # shorter timeout for admin
            return JsonResponse({'success': True, 'data': counts})
        
        else:
            # CLIENT/ASSISTANT: Return single client with tables
            client, _ = _client_ctx(user)
            if not client:
                return JsonResponse({'success': False, 'message': 'No client context'}, status=400)
            
            # For assistant, explicitly compute access FIRST to avoid stale cache overriding security.
            is_staff_empty = False
            if is_staff:
                scoped_qs = OrganisationAccessService.get_scoped_tables_qs(user, client)
                if not scoped_qs.exists():
                    # STRICT BYPASS: Assistant has no assignments, return empty immediately
                    cached_data = {
                        'client_id': Organisation.id,
                        'client_name': getattr(client, 'business_name', client.name),
                        'pending': 0, 'verified': 0, 'approved': 0,
                        'download': 0, 'pool': 0, 'total': 0,
                        'tables': [],
                        'recent_activity': recent_activity
                    }
                    return JsonResponse({'success': True, 'data': cached_data})
            
            cache_key = f"mob_dash_{client.id}_{user.id}" if is_staff else f"mob_dash_{client.id}"
            cache_version = CacheVersionService.get('client_dash_counts', f'client:{client.id}')
            full_cache_key = f"{cache_key}_v{cache_version}"
            
            cached_data = cache.get(full_cache_key)
            if cached_data:
                cached_data['recent_activity'] = recent_activity
                return JsonResponse({'success': True, 'data': cached_data})
            
            # Get accessible tables
            tables_qs = Table.objects.filter(group__client=client, is_active=True, deleted_by_client=False)
            if is_staff:
                tables_qs = OrganisationAccessService.get_scoped_tables_qs(user, client, tables_qs)
            
            scoped_table_ids = list(tables_qs.values_list('id', flat=True))
            
            counts = {
                'client_id': Organisation.id,
                'client_name': getattr(client, 'business_name', client.name),
                'pending': 0, 'verified': 0, 'approved': 0, 'download': 0, 'pool': 0, 'total': 0
            }

            tables_data = []
            if is_staff:
                # Bulk fetch pool counts for all tables to avoid N+1 queries
                tables_list = list(tables_qs.order_by('name'))
                table_ids = [t.id for t in tables_list]
                pool_counts = {}
                if table_ids:
                    for row in IDCard.objects.filter(table_id__in=table_ids, status='pool').values('table_id').annotate(n=Count('id')):
                        pool_counts[row['table_id']] = row['n']
                        
                # Scoped counts table-by-table for assistant (except pool)
                for t in tables_list:
                    table_cards_qs = OrganisationCardService._apply_client_staff_row_scope(
                        user,
                        t,
                        IDCard.objects.filter(table_id=t.id)
                    )
                    
                    t_counts = {'pending': 0, 'verified': 0, 'approved': 0, 'download': 0, 'pool': 0}
                    # We exclude pool cards from the scoped counts loop,
                    # because we want to use the full client/table pool count instead!
                    for row in table_cards_qs.exclude(status='pool').values('status').annotate(n=Count('id')):
                        status_val = row['status']
                        if status_val in t_counts:
                            t_counts[status_val] = row['n']
                            counts[status_val] += row['n']
                            
                    # Pool count in tables is the full table pool count (unfiltered)
                    t_counts['pool'] = pool_counts.get(t.id, 0)
                    
                    tables_data.append({
                        'id': t.id,
                        'name': t.name,
                        'p': t_counts['pending'],
                        'v': t_counts['verified'],
                        'a': t_counts['approved'],
                        'd': t_counts['download'],
                        'po': t_counts['pool'],
                    })
                
                # Fetch pool count scoped to the assistant's assigned tables
                counts['pool'] = IDCard.objects.filter(table_id__in=scoped_table_ids, status='pool').count()
            else:
                # Regular client: standard query
                cards_qs = IDCard.objects.filter(table_id__in=scoped_table_ids)
                for row in cards_qs.values('status').annotate(n=Count('id')):
                    status_val = row['status']
                    if status_val in counts:
                        counts[status_val] = row['n']
                
                tables_annotated = tables_qs.annotate(
                    cnt_p=Count('id_cards', filter=Q(id_cards__status='pending')),
                    cnt_v=Count('id_cards', filter=Q(id_cards__status='verified')),
                    cnt_a=Count('id_cards', filter=Q(id_cards__status='approved')),
                    cnt_d=Count('id_cards', filter=Q(id_cards__status='download')),
                    cnt_po=Count('id_cards', filter=Q(id_cards__status='pool')),
                ).order_by('name')
                
                for t in tables_annotated:
                    tables_data.append({
                        'id': t.id,
                        'name': t.name,
                        'p': t.cnt_p,
                        'v': t.cnt_v,
                        'a': t.cnt_a,
                        'd': t.cnt_d,
                        'po': t.cnt_po,
                    })

            # TOTAL definition (match website): Excludes pool
            counts['total'] = counts['pending'] + counts['verified'] + counts['approved'] + counts['download']
            counts['tables'] = tables_data
            counts['recent_activity'] = recent_activity
            
            # Save to cache
            cache.set(full_cache_key, counts, timeout=3600)
            return JsonResponse({'success': True, 'data': counts})
            
    except Exception:
        logger.exception('api_dashboard_data error')
        return JsonResponse({'success': False, 'message': 'Unable to load dashboard.'}, status=500)




@ensure_csrf_cookie
@require_mobile_client
@require_http_methods(["GET"])
def api_server_info(request):
    """Return lightweight server diagnostics for authenticated mobile admins only."""
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({'success': False, 'authenticated': False, 'message': 'Authentication required'}, status=401)

    # Only super admins may view sensitive diagnostics
    if not PermissionService.is_super_admin(user):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)

    import os
    import platform
    import socket
    process_uptime_seconds = max(0, int(time.time() - APP_BOOT_TS))

    # Disk usage info
    try:
        import shutil
        total, used, free = shutil.disk_usage(os.getcwd())
        disk = {
            'total': total,
            'used': used,
            'free': free,
            'percent': round(used / total * 100, 1) if total else None,
        }
    except Exception:
        disk = None

    data = {
        'hostname': socket.gethostname(),
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'django_version': __import__('django').get_version(),
        'environment': 'Development' if settings.DEBUG else 'Production',
        'uptime': process_uptime_seconds,
        'disk': disk,
    }
    return JsonResponse({'success': True, 'data': data})


@require_mobile_client
@require_http_methods(["GET"])
def api_reprint_data(request, client_id):
    """Return reprint request/confirmed counts per table as JSON.
    If client_id is 0 and user is admin, returns global data.
    """
    try:
        user = request.user
        is_admin = PermissionService.is_any_admin(user)
        
        if client_id == 0:
            if not is_admin:
                return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
            # Global view for admin
            tables_qs = Table.objects.filter(is_active=True).select_related('group', 'group__client').order_by('group__name', 'name')
            if PermissionService.is_admin_staff(user):
                accessible_ids = PermissionService.get_accessible_client_ids(user)
                if accessible_ids:
                    tables_qs = tables_qs.filter(group__client_id__in=accessible_ids)
                else:
                    return JsonResponse({'success': True, 'data': {'tables': [], 'request_total': 0, 'confirmed_total': 0, 'download_total': 0}})
        else:
            if not PermissionService.can_access_client(user, client_id):
                return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
            tables_qs = Table.objects.filter(group__client_id=client_id, is_active=True).select_related('group', 'group__client').order_by('group__name', 'name')

        if PermissionService.is_client_staff(user):
            client_ctx = OrganisationAccessService.get_organisation_for_user(user)
            tables_qs = OrganisationAccessService.get_scoped_tables_qs(user, client_ctx, tables_qs)

        tables = list(tables_qs)
        table_ids = [t.id for t in tables]

        reprint_map = {}
        if table_ids:
            for row in ReprintRequest.objects.filter(table_id__in=table_ids, status__in=['requested', 'confirmed']).values('table_id', 'status').annotate(n=Count('id'), latest_request=Max('created_at')):
                if row['table_id'] not in reprint_map:
                    reprint_map[row['table_id']] = {'requested': 0, 'confirmed': 0, 'latest_request': None}
                reprint_map[row['table_id']][row['status']] = row['n']
                if row['latest_request']:
                    cur = reprint_map[row['table_id']]['latest_request']
                    if not cur or row['latest_request'] > cur:
                        reprint_map[row['table_id']]['latest_request'] = row['latest_request']

        download_map = {}
        if table_ids:
            for row in IDCard.objects.filter(table_id__in=table_ids, status='download').values('table_id').annotate(n=Count('id')):
                download_map[row['table_id']] = row['n']

        request_total = 0
        confirmed_total = 0
        download_total = 0
        items = []
        for t in tables:
            sm = reprint_map.get(t.id, {})
            requested = int(sm.get('requested', 0) or 0)
            confirmed = int(sm.get('confirmed', 0) or 0)
            request_total += requested
            confirmed_total += confirmed
            dl_count = int(download_map.get(t.id, 0) or 0)
            reprint_count = max(0, dl_count - requested)
            download_total += dl_count
            items.append({
                'id': t.id,
                'name': t.name,
                'group_name': t.group.name,
                'client_name': t.group.client.name if t.group and t.group.client else '',
                'client_id': t.group.client_id if t.group else 0,
                'requested': requested,
                'confirmed': confirmed,
                'reprint_count': reprint_count,
                'download': dl_count,
                'latest_request': sm.get('latest_request').isoformat() if sm.get('latest_request') else None
            })

        return JsonResponse({'success': True, 'data': {'tables': items, 'request_total': request_total, 'confirmed_total': confirmed_total, 'download_total': download_total}})
    except Exception:
        logger.exception('api_reprint_data error')
        return JsonResponse({'success': False, 'message': 'Unable to load reprint data.'}, status=500)


@require_mobile_client
@require_http_methods(["POST"])
def api_profile_update(request):
    """Update current user's profile."""
    user = request.user
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    try:
        if 'first_name' in data:
            user.first_name = data['first_name'].strip()
        if 'last_name' in data:
            user.last_name = data['last_name'].strip()
        if 'phone' in data and hasattr(user, 'phone'):
            user.phone = data['phone'].strip()

        # Handle combined name field
        name = data.get('name', '').strip()
        if name and 'first_name' not in data:
            parts = name.split()
            user.first_name = parts[0] if parts else ''
            user.last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''

        user.save()
        return JsonResponse({
            'success': True,
            'message': 'Profile updated successfully',
            'name': user.get_full_name() or user.username,
        })
    except Exception:
        logger.exception('Profile update error')
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=500)


@require_mobile_client
@require_http_methods(["POST"])
def api_profile_change_password(request):
    """Change current user's password."""
    user = request.user
    try:
        data = json.loads(request.body)
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return JsonResponse({'success': False, 'message': 'Both current and new passwords are required'}, status=400)
            
        if not user.check_password(current_password):
            return JsonResponse({'success': False, 'message': 'Current password is incorrect'}, status=400)
            
        user.set_password(new_password)
        user.save()
        
        # Update session to prevent logout
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, user)
        
        return JsonResponse({'success': True, 'message': 'Password updated successfully'})
    except Exception:
        logger.exception('Password change error')
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=500)


@require_mobile_client
@require_http_methods(["POST"])
def api_profile_delete_request(request):
    """Submit a data deletion request for the current user.

    Google Play Store requires apps that collect user data to provide a visible
    mechanism for requesting data deletion. This endpoint records the request
    and notifies the admin team.
    """
    user = request.user
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = {}

    if not data.get('confirm'):
        return JsonResponse({
            'success': False,
            'message': 'Please confirm your deletion request.',
        }, status=400)

    user_email = getattr(user, 'email', '') or ''
    user_name = user.get_full_name() or getattr(user, 'username', '')
    user_role = getattr(user, 'role', 'unknown')

    # Log the request for audit trail
    logger.info(
        'Data deletion requested â€” user_id=%s name=%s email=%s role=%s',
        user.pk, user_name, user_email, user_role,
    )

    # Record activity if the service is available
    try:
        ActivityService.log(
            'other',
            f'User {user_name} ({user_email}) requested account and data deletion via mobile app.',
            user=user,
        )
    except Exception:
        pass  # Activity logging is best-effort

    # Send notification email to admin
    admin_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or getattr(settings, 'ADMIN_EMAIL', '')
    if admin_email:
        try:
            from django.core.mail import send_mail as _send_mail
            _send_mail(
                subject=f'[Adarsh Admin] Data Deletion Request â€” {user_name}',
                message=(
                    f'A data deletion request has been submitted.\n\n'
                    f'User ID: {user.pk}\n'
                    f'Name: {user_name}\n'
                    f'Email: {user_email}\n'
                    f'Role: {user_role}\n\n'
                    f'Please process this request within 7 business days per our privacy policy.'
                ),
                from_email=admin_email,
                recipient_list=[admin_email],
                fail_silently=True,
            )
        except Exception:
            logger.warning('Failed to send data deletion notification email for user_id=%s', user.pk)

    return JsonResponse({
        'success': True,
        'message': 'Your data deletion request has been submitted. An administrator will process it within 7 business days.',
    })


@require_mobile_client
@require_http_methods(["GET"])
def api_search(request):
    """Global search API across all client cards."""
    user = request.user
    
    query = _sanitize_search_query(request.GET.get('q', ''))
    filter_type = str(request.GET.get('filter', 'all') or 'all').strip().lower()
    if filter_type not in ('all', 'name', 'address', 'mobile'):
        return JsonResponse({'success': False, 'message': 'Invalid search filter.'}, status=400)
    raw_table_id = (request.GET.get('table_id') or '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'success': True, 'data': {'results': [], 'count': 0}})

    # Super admin searches all cards; admin_staff is assignment-scoped.
    if PermissionService.is_super_admin(user):
        base_qs = IDCard.objects.select_related(
            'table', 'table__group', 'table__group__client'
        ).order_by('-updated_at')
    elif PermissionService.is_admin_staff(user):
        accessible_ids = PermissionService.get_accessible_client_ids(user)
        if accessible_ids:
            base_qs = IDCard.objects.filter(
                table__group__client_id__in=accessible_ids,
            ).select_related('table', 'table__group', 'table__group__client').order_by('-updated_at')
        else:
            return JsonResponse({'success': True, 'data': {'results': [], 'count': 0}})
    else:
        client, _ = _client_ctx(user)
        if not client:
            return JsonResponse({'success': False, 'message': 'No client'}, status=400)
        base_qs = IDCard.objects.filter(
            table__group__client=client,
        ).select_related('table', 'table__group').order_by('-updated_at')

    base_qs = _apply_mobile_search_status_scope(user, base_qs)

    if raw_table_id:
        if not raw_table_id.isdigit():
            return JsonResponse({'success': False, 'message': 'Invalid table scope.'}, status=400)

        scoped_table_id = int(raw_table_id)
        if scoped_table_id <= 0:
            return JsonResponse({'success': False, 'message': 'Invalid table scope.'}, status=400)

        scoped_table = Table.objects.select_related('group').filter(id=scoped_table_id).first()
        if not scoped_table:
            return JsonResponse({'success': False, 'message': 'Table not found.'}, status=404)

        if not PermissionService.can_access_client(user, scoped_table.group.client_id):
            return JsonResponse({'success': False, 'message': 'Access denied.'}, status=403)

        if user.role in ('prime_manager', 'manager') and not OrganisationAccessService.can_access_table(user, scoped_table):
            return JsonResponse({'success': False, 'message': 'Access denied.'}, status=403)

        base_qs = base_qs.filter(table_id=scoped_table_id)

    cards_qs = _search_cards_for_global_results(base_qs, query, limit=30, filter_type=filter_type)
    cards_qs = _filter_cards_for_client_staff_row_scope(user, cards_qs)

    results = []
    for card in cards_qs:
        fd = card.field_data or {}
        name = _card_display_name(card, fd)
        roll_no = fd.get('ROLL NO') or fd.get('ROLL_NO') or fd.get('roll_no') or ''
        photo_url = get_card_photo_url(card, fd)
        
        # Sanitize field_data: strip PENDING: prefix from text fields
        sanitized_field_data = {}
        for key, val in fd.items():
            is_image_field = False
            for field in (card.table.fields or []):
                if not isinstance(field, dict):
                    continue
                fname = field.get('name')
                if fname is None:
                    continue
                fname_str = str(fname).strip()
                if fname_str == key or fname_str.upper() == key.upper():
                    is_image_field = field.get('type') in ['photo', 'image', 'rel_photo', 'mother_photo', 'father_photo', 'barcode', 'qr_code', 'signature', 'image']
                    break
            if not is_image_field and val and isinstance(val, str) and val.startswith('PENDING:'):
                sanitized_field_data[key] = ''
            else:
                sanitized_field_data[key] = val

        ordered_fields = []
        for field in (card.table.fields or []):
            if not isinstance(field, dict):
                continue
            field_name = field.get('name')
            field_name_str = str(field_name).strip() if field_name is not None else ''
            ordered_fields.append({
                'name': field_name_str,
                'type': field.get('type', 'text'),
                'label': field.get('label') or field_name_str,
                'value': sanitized_field_data.get(field_name_str, '')
            })

        results.append({
            'id': card.id,
            'name': name,
            'roll_no': roll_no,
            'status': card.status,
            'table_name': card.table.name,
            'group_name': getattr(card.table.group, 'name', ''),
            'client_name': getattr(getattr(card.table.group, 'client', None), 'name', ''),
            'photo_url': photo_url,
            'table_id': card.table.id,
            'field_data': sanitized_field_data,
            'ordered_fields': ordered_fields,
        })

    return JsonResponse({'success': True, 'data': {'results': results, 'count': len(results)}})




@require_mobile_client
@require_http_methods(["GET"])
def api_impersonate_users(request):
    """Return pro-user impersonation targets filtered to mobile-eligible users."""
    from accounts.services_impersonate import ImpersonateService
    from django.contrib.auth import get_user_model

    if not ImpersonateService.can_impersonate(request.user):
        return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

    users = ImpersonateService.get_impersonation_targets(request)
    if not users:
        return JsonResponse({'success': True, 'users': []})

    user_ids = [int(item.get('id')) for item in users if str(item.get('id', '')).isdigit()]
    
    # Super Admins and Admin Staff should see ALL clients, regardless of mobile perm.
    # Pro Users (Clients) trying to impersonate their own staff might need filtering, but 
    # ImpersonateService.get_impersonation_targets already filters valid targets.
    # To maintain desktop parity, we remove the strict `perm_mobile_app` restriction.
    mobile_allowed_ids = set(user_ids)

    from tables.models import IDCard
    from django.db.models import Count, Max

    # Bulk fetch counts for all mobile-allowed IDs in one query
    counts_map = {}
    stats = (
        IDCard.objects.filter(table__group__client_id__in=mobile_allowed_ids)
        .values('table__group__client_id', 'status')
        .annotate(count=Count('id'))
    )
    for s in stats:
        cid = s['table__group__client_id']
        status = s['status']
        count = s['count']
        if cid not in counts_map:
            counts_map[cid] = {'total': 0, 'pending': 0, 'verified': 0, 'approved': 0, 'download': 0, 'pool': 0}
        counts_map[cid]['total'] += count
        if status in counts_map[cid]:
            counts_map[cid][status] = count

    filtered = []
    for item in users:
        try:
            item_id = int(item.get('id') or 0)
        except (TypeError, ValueError):
            continue
            
        if item_id in mobile_allowed_ids:
            item['counts'] = counts_map.get(item_id, {'total': 0, 'pending': 0, 'verified': 0, 'approved': 0, 'download': 0, 'pool': 0})
            filtered.append(item)
    return JsonResponse({'success': True, 'users': filtered})


@require_mobile_client
@require_http_methods(["GET"])
def api_clients_list(request):
    """Admin-only: Return all clients with full status counts for management."""
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

    from organisation.models import Organisation
    
    # Fetch all clients based on permissions
    if PermissionService.is_super_admin(request.user):
        clients_qs = Organisation.objects.select_related('user').all().order_by('name')
    else:  # admin_staff (operators) or photographer
        accessible_ids = PermissionService.get_accessible_client_ids(request.user) or []
        clients_qs = Organisation.objects.filter(id__in=accessible_ids).select_related('user').order_by('name')
    
    client_ids = list(clients_qs.values_list('id', flat=True))

    from tables.models import IDCard
    from django.db.models import Count

    is_photographer = PermissionService.is_photographer(request.user)

    # Bulk fetch counts
    counts_map = {}
    if is_photographer:
        # Initialize captured/uncaptured counts map
        for cid in client_ids:
            counts_map[cid] = {'captured': 0, 'uncaptured': 0}
        
        # Fetch active tables for client_ids to build mapping
        from tables.models import Table
        tables_qs = Table.objects.filter(group__client_id__in=client_ids).values('id', 'group__client_id')
        table_to_client_map = {t['id']: t['group__client_id'] for t in tables_qs}

        assigned_cards_qs = IDCard.objects.filter(
            table__group__client_id__in=client_ids,
            status__in=['pending', 'verified']
        ).only('id', 'table_id', 'photo', 'field_data')

        for card in assigned_cards_qs.iterator(chunk_size=500):
            has_photo = bool(get_card_photo_url(card))
            cid = table_to_client_map.get(card.table_id)
            if cid in counts_map:
                if has_photo:
                    counts_map[cid]['captured'] += 1
                else:
                    counts_map[cid]['uncaptured'] += 1
    else:
        stats = (
            IDCard.objects.filter(table__group__client_id__in=client_ids)
            .values('table__group__client_id', 'status')
            .annotate(count=Count('id'))
        )
        for s in stats:
            cid = s['table__group__client_id']
            status = s['status']
            count = s['count']
            if cid not in counts_map:
                counts_map[cid] = {'total': 0, 'pending': 0, 'verified': 0, 'approved': 0, 'download': 0, 'pool': 0}
            counts_map[cid]['total'] += count
            if status in counts_map[cid]:
                counts_map[cid][status] = count

    users_list = []
    for c in clients_qs:
        try:
            u = c.user
            if not u:
                continue
        except Exception:
            continue
        logo_url = ''
            
        users_list.append({
            'id': c.id,       # Client model ID — used by toggle/delete/update endpoints
            'user_id': u.id,  # User model ID — used by impersonation endpoint
            'name': c.name,
            'email': u.email,
            'phone': getattr(u, 'phone', '') or '',
            'is_active': u.is_active,
            'logo_url': logo_url,
            'counts': counts_map.get(c.id, {'captured': 0, 'uncaptured': 0} if is_photographer else {'total': 0, 'pending': 0, 'verified': 0, 'approved': 0, 'download': 0, 'pool': 0})
        })

    return JsonResponse({'success': True, 'users': users_list})


@require_mobile_client
@require_http_methods(["POST"])
def api_impersonate_start(request):
    """Start impersonation from mobile and keep the session on the mobile surface."""
    from accounts.services_impersonate import ImpersonateService
    from django.contrib.auth import get_user_model

    if not ImpersonateService.can_impersonate(request.user):
        return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)

    raw_user_id = payload.get('user_id')
    try:
        target_user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'user_id is required'}, status=400)

    UserModel = get_user_model()
    target = UserModel.objects.filter(pk=target_user_id).first()
    if not target:
        return JsonResponse({'success': False, 'message': 'User not found.'}, status=404)

    valid_mobile_roles = {'pro_user', 'super_admin', 'operator', 'prime_manager', 'manager', 'guest_prime_manager', 'assistant', 'photographer'}
    if getattr(target, 'role', '') not in valid_mobile_roles:
        return JsonResponse({'success': False, 'message': 'Target user cannot access the mobile app.'}, status=400)

    if not PermissionService.has(target, 'perm_mobile_app'):
        return JsonResponse({'success': False, 'message': 'Target user has no mobile app access.'}, status=400)

    result = ImpersonateService.start(request, target_user_id)
    if not result.get('success'):
        return JsonResponse(result, status=403)

    request.session['mobile_auth_ok'] = True
    request.session['_auth_login_surface'] = 'mobile'
    request.session['_auth_browser_fp'] = AuthService.browser_fingerprint_from_request(request)
    request.session['selected_role'] = getattr(target, 'role', '')
    result['redirect_url'] = '/app/'
    return JsonResponse(result)


@require_mobile_client
@require_http_methods(["POST"])
def api_impersonate_stop(request):
    """Stop impersonation from mobile and return to pro user on mobile surface."""
    from accounts.services_impersonate import ImpersonateService

    next_url = ''
    try:
        data = json.loads(request.body)
        next_url = str(data.get('next', '') or '').strip()
    except (json.JSONDecodeError, TypeError):
        pass

    result = ImpersonateService.stop(request, next_url=next_url)
    if not result.get('success'):
        return JsonResponse(result, status=400)

    request.session['mobile_auth_ok'] = True
    request.session['_auth_login_surface'] = 'mobile'
    request.session['_auth_browser_fp'] = AuthService.browser_fingerprint_from_request(request)
    request.session['selected_role'] = getattr(request.user, 'role', '')
    # Only override to /app/ if we didn't get a specific next_url via stop()
    if not result.get('redirect_url') or result['redirect_url'] == '/panel/':
        result['redirect_url'] = '/app/'
    return JsonResponse(result)


# â”€â”€â”€ Client Management APIs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@require_mobile_client
@require_http_methods(['POST'])
def api_client_toggle(request, client_id):
    """Toggle a client between active / inactive."""
    from organisation.models import Organisation
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    if not _can_manage_clients_surface(request.user):
        return JsonResponse({'success': False, 'message': 'Manage Client permission required'}, status=403)
    if PermissionService.is_admin_staff(request.user) and not PermissionService.can_access_client(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
    try:
        client = get_object_or_404(Client, id=client_id)
        if client.status == 'active':
            client.status = 'inactive'
            label = 'deactivated'
        else:
            client.status = 'active'
            label = 'activated'
        client.save(update_fields=['status'])
        return JsonResponse({'success': True, 'message': f'{client.name} {label}', 'new_status': Organisation.status})
    except Exception as exc:
        logger.exception('api_client_toggle error: %s', exc)
        return JsonResponse({'success': False, 'message': 'An error occurred. Please try again.'}, status=500)


@require_mobile_client
@require_http_methods(['POST'])
def api_client_delete(request, client_id):
    """Permanently delete a client (super_admin only)."""
    from organisation.models import Organisation
    if not PermissionService.is_super_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Only super admin can delete clients'}, status=403)
    try:
        client = get_object_or_404(Client, id=client_id)
        client_name = client.name
        last_active_str = ActivityService._format_last_active(getattr(client, 'user', None))
        result = ClientService.delete(client_id)
        if result.success:
            try:
                ActivityService.log_client_delete(request, client_name, last_active_str, client_id)
            except Exception:
                logger.exception('Mobile client-delete activity logging failed')
        return JsonResponse(
            {'success': result.success, 'message': result.message},
            status=200 if result.success else 400,
        )
    except Exception as exc:
        logger.exception('api_client_delete error: %s', exc)
        return JsonResponse({'success': False, 'message': 'An error occurred. Please try again.'}, status=500)


@require_mobile_client
@require_http_methods(["GET"])
def api_client_tables(request, client_id):
    """Return active tables with pending/verified counts for a client (admin only, lazy-loaded)."""
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
    if not PermissionService.can_access_client(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
    from organisation.models import Organisation
    get_object_or_404(Client, id=client_id)
    tables_qs = (
        Table.objects
        .filter(group__client_id=client_id, is_active=True)
        .select_related('group')
        .annotate(
            pending_count=Count('id_cards', filter=Q(id_cards__status='pending')),
            verified_count=Count('id_cards', filter=Q(id_cards__status='verified')),
            approved_count=Count('id_cards', filter=Q(id_cards__status='approved')),
            download_count=Count('id_cards', filter=Q(id_cards__status='download')),
            pool_count=Count('id_cards', filter=Q(id_cards__status='pool')),
        )
        .order_by('group__name', 'name')
    )
    tables = [
        {
            'id': t.id,
            'name': t.name,
            'group_name': t.group.name,
            'pending_count': t.pending_count,
            'verified_count': t.verified_count,
            'approved_count': t.approved_count,
            'download_count': t.download_count,
            'pool_count': t.pool_count,
            'total_cards': t.pending_count + t.verified_count + t.approved_count + t.download_count + t.pool_count
        }
        for t in tables_qs
    ]
    return JsonResponse({'success': True, 'tables': tables})


@require_mobile_client
@require_http_methods(['GET'])
def api_client_detail(request, client_id):
    """Fetch client details for edit form (super_admin/pro_user or scoped admin_staff manager)."""
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    if not _can_manage_clients_surface(request.user):
        return JsonResponse({'success': False, 'message': 'Manage Client permission required'}, status=403)
    if PermissionService.is_admin_staff(request.user) and not PermissionService.can_access_client(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)

    result = ClientService.get(client_id, include_permissions=True)
    if not result.success:
        return JsonResponse({'success': False, 'message': result.message or 'Client not found'}, status=404)
    return JsonResponse({'success': True, 'client': result.data.get('client', {})})


@require_mobile_client
@require_http_methods(['POST'])
def api_client_create(request):
    """Create a client from mobile app for users with Manage Client access."""
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    if not _can_manage_clients_surface(request.user):
        return JsonResponse({'success': False, 'message': 'Manage Client permission required'}, status=403)
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    # Inject default Power User permissions for mobile-created clients
    default_perms = {
        'perm_mobile_app': True,
        'perm_idcard_info': True,
        'perm_idcard_verify': True,
        'perm_idcard_approve': True,
        'perm_idcard_client_list': True,
        'perm_idcard_pending_list': True,
        'perm_idcard_verified_list': True,
        'perm_idcard_pool_list': True,
        'perm_idcard_approved_list': True,
    }
    for perm_key, perm_val in default_perms.items():
        if perm_key not in data:
            data[perm_key] = perm_val

    result = ClientService.create(data, request=request)
    if not result.success:
        return JsonResponse({'success': False, 'message': result.message or 'Failed to create client'}, status=400)

    if PermissionService.is_operator(request.user) or PermissionService.is_admin_staff(request.user):
        try:
            created_client_id = ((result.data or {}).get('client') or {}).get('id') or (result.data or {}).get('id')
            if created_client_id:
                from organisation.models import Organisation
                created_client = Organisation.objects.filter(id=created_client_id).first()
                operator_profile = getattr(request.user, 'operator_profile', None)
                if created_client and operator_profile:
                    operator_profile.assigned_organisations.add(created_client)
        except Exception:
            logger.warning('Could not auto-assign newly created client to operator user=%s', request.user.pk)

    client_payload = result.data.get('client', {}) if result.data else {}
    return JsonResponse({
        'success': True,
        'message': result.message or 'Client created successfully',
        'client': client_payload,
    })


@require_mobile_client
@require_http_methods(['POST'])
def api_mobile_logout(request):
    """Logout mobile user and clear session."""
    from django.contrib.auth import logout
    logout(request)
    return JsonResponse({'success': True, 'message': 'Logged out successfully'})


@require_mobile_client
@require_http_methods(['POST'])
def api_client_update(request, client_id):
    """Update a client from mobile app for users with Manage Client access."""
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    if not _can_manage_clients_surface(request.user):
        return JsonResponse({'success': False, 'message': 'Manage Client permission required'}, status=403)
    if PermissionService.is_admin_staff(request.user) and not PermissionService.can_access_client(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied'}, status=403)
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    # Handle temporary password if provided
    temp_pw = data.get('temp_password', '').strip()
    if temp_pw:
        if len(temp_pw) < 8:
            return JsonResponse({'success': False, 'message': 'Password must be at least 8 characters'}, status=400)
        from django.contrib.auth.password_validation import validate_password
        try:
            validate_password(temp_pw)
        except Exception as validation_error:
            return JsonResponse({'success': False, 'message': '; '.join(validation_error.messages)}, status=400)
            
        from organisation.services_client_core import OrganisationService as ClientService
        pw_result = ClientService.set_temp_password(client_id, temp_pw, request=request)
        if not pw_result.success:
            return JsonResponse({'success': False, 'message': pw_result.message or 'Failed to set password'}, status=400)

    result = ClientService.update(client_id, data)
    if not result.success:
        return JsonResponse({'success': False, 'message': result.message or 'Failed to update client'}, status=400)

    client_payload = result.data.get('client', {}) if result.data else {}
    return JsonResponse({
        'success': True,
        'message': result.message or 'Client updated successfully',
        'client': client_payload,
    })


@require_mobile_client
@require_http_methods(["POST"])
def api_client_update_permissions(request, client_user_id):
    """Admin-only: Update permissions for a specific client account."""
    user = request.user
    if not PermissionService.is_super_admin(user) and not PermissionService.is_admin_staff(user):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

    try:
        from core.models import User
        client_user = get_object_or_404(User, id=client_user_id)
        profile = getattr(client_user, 'client_profile', None)
        if not profile:
            return JsonResponse({'success': False, 'message': 'Client profile not found'}, status=404)

        data = json.loads(request.body)
        updates = data.get('permissions', {})
        
        # Whitelist of permissions that can be toggled via mobile
        ALLOWED_TOGGLES = {
            'perm_idcard_info', 'perm_idcard_verify', 'perm_idcard_approve', 
            'perm_idcard_download'
        }

        for key, value in updates.items():
            if key in ALLOWED_TOGGLES and hasattr(profile, key):
                setattr(profile, key, bool(value))
        
        profile.save()
        
        # Invalidate permission cache for this user
        cache_key = PermissionService._permission_context_cache_key(client_user)
        from django.core.cache import cache
        cache.delete(cache_key)

        return JsonResponse({'success': True, 'message': 'Permissions updated'})
    except Exception:
        logger.exception('api_client_update_permissions error')
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=500)


@require_mobile_client
@require_http_methods(["GET"])
def api_client_permissions(request, client_user_id):
    """Admin-only: Get current permissions for a specific client account."""
    user = request.user
    if not PermissionService.is_super_admin(user) and not PermissionService.is_admin_staff(user):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

    from core.models import User
    client_user = get_object_or_404(User, id=client_user_id)
    perms = PermissionService.get_permission_context(client_user)
    return JsonResponse({'success': True, 'data': perms.get('user_permissions', {})})

@require_mobile_client(allow_public=True)
@require_http_methods(['GET'])
def api_app_version(request):
    """
    Returns the latest mobile app version from settings or dynamically reads it from
    android_app/app.json, and redirect/installation URLs.
    """
    import os
    import json
    import logging
    
    logger = logging.getLogger(__name__)
    latest_version = getattr(settings, 'LATEST_MOBILE_VERSION', None)
    
    if not latest_version:
        try:
            app_json_path = os.path.join(settings.BASE_DIR, 'android_app', 'app.json')
            if os.path.exists(app_json_path):
                with open(app_json_path, 'r', encoding='utf-8') as f:
                    app_data = json.load(f)
                    latest_version = app_data.get('expo', {}).get('version')
        except Exception as e:
            logger.warning("Failed to parse app.json dynamically: %s", e)

    if not latest_version:
        latest_version = '1.0.82'

    return JsonResponse({
        'success': True,
        'latest_version': latest_version,
        'play_store_url': 'https://play.google.com/store/apps/details?id=com.adarshid.app',
        'market_url': 'market://details?id=com.adarshid.app'
    })


@require_mobile_client(allow_public=True)
@require_http_methods(['GET'])
def api_website_landing_data(request):
    """
    Public endpoint for mobile app landing screen.
    Priority:
      1. Django ORM (works on production where website app is co-installed)
      2. SQLite direct query (works locally where apps are separate)
    """
    import os
    import sqlite3

    # 1. Determine website media base URL
    proto = "https" if request.is_secure() else "http"
    ip_or_domain = request.get_host().split(':')[0]
    if 'panel.adarshbhopal.in' in ip_or_domain:
        website_base_url = "https://www.adarshbhopal.in"
    else:
        env_url = os.getenv('LANDING_WEBSITE_URL', '').rstrip('/')
        website_base_url = env_url if env_url else f"{proto}://{ip_or_domain}:8001"

    def make_absolute(path):
        if not path:
            return ''
        if path.startswith(('http://', 'https://')):
            return path
        rel = path.lstrip('/')
        return f"{website_base_url}/{rel}" if rel.startswith('media/') else f"{website_base_url}/media/{rel}"

    categories = []
    clients = []
    business = {
        'site_name': 'Adarsh ID Cards',
        'tagline': 'Excellence in Identification',
        'address': 'Bhopal, MP, India',
        'phone': '+91-XXXXXXXXXX',
        'email': 'info@adarshbhopal.in',
        'whatsapp': '91XXXXXXXXXX',
    }
    data_loaded = False

    # ------------------------------------------------------------------
    # STRATEGY 1: Django ORM — works on production (co-deployed apps)
    # ------------------------------------------------------------------
    try:
        from website.models import PortfolioCategory, PortfolioItem, WebsiteClientLogo

        try:
            from website.models import BusinessDetails
            biz = BusinessDetails.objects.filter(is_active=True).first()
            if biz:
                ph = getattr(biz, 'phone1', '') or getattr(biz, 'phone2', '') or ''
                business.update({
                    'site_name': biz.site_name or business['site_name'],
                    'address': biz.address or business['address'],
                    'phone': ph or business['phone'],
                    'email': biz.email or business['email'],
                    'whatsapp': ''.join(c for c in ph if c.isdigit()) or business['whatsapp'],
                })
        except Exception:
            pass

        for cat in PortfolioCategory.objects.filter(is_active=True).order_by('order', 'name'):
            icon_name = (getattr(cat, 'icon', '') or 'folder').replace('fas fa-', '').replace('fa-', '')
            products_list = []
            for item in cat.items.filter(is_active=True).order_by('order', '-created_at'):
                img_path = str(item.image) if item.image else ''
                vf_path = str(item.video_file) if item.video_file else ''
                if item.item_type in ('video', 'reel'):
                    media_url = make_absolute(img_path) if img_path else make_absolute(vf_path)
                else:
                    media_url = make_absolute(img_path)
                products_list.append({
                    'id': item.id, 'title': item.title, 'slug': item.slug,
                    'description': item.description or '',
                    'item_type': item.item_type or 'image',
                    'orientation': getattr(item, 'orientation', '') or '',
                    'media_url': media_url,
                    'video_url': item.video_url or '',
                    'video_fallback_url': make_absolute(vf_path),
                    'video_stream_url': '',
                    'video_thumbnail_url': make_absolute(img_path),
                    'is_featured': bool(item.is_featured),
                    'order': item.order,
                    'created_at': item.created_at.isoformat(),
                })
            categories.append({
                'id': cat.id, 'name': cat.name, 'slug': cat.slug, 'icon': icon_name,
                'description': cat.description or '', 'is_bento': bool(cat.is_bento),
                'bento_size': cat.bento_size or 'normal', 'order': cat.order, 'products': products_list,
            })

        for cl in WebsiteClientLogo.objects.filter(website_is_visible=True).order_by('website_display_order', '-created_at'):
            clients.append({
                'id': cl.id, 'name': cl.name,
                'logo': make_absolute(str(cl.logo)) if cl.logo else '',
                'total_records': cl.total_records or 0,
            })

        data_loaded = True
        logger.info("landing_data: loaded via Django ORM (%d categories)", len(categories))

    except ImportError:
        logger.info("landing_data: website ORM not available, trying SQLite")
    except Exception as orm_err:
        logger.error("landing_data: ORM error: %s", orm_err)

    # ------------------------------------------------------------------
    # STRATEGY 2: SQLite — works locally when apps are in separate dirs
    # ------------------------------------------------------------------
    if not data_loaded:
        db_path = os.getenv('WEBSITE_DATABASE_PATH')
        if not db_path:
            candidates = [
                r'E:\E\Adarsh Website New\db.sqlite3',
                os.path.abspath(os.path.join(settings.BASE_DIR, '..', 'Adarsh Website New', 'db.sqlite3')),
                os.path.abspath(os.path.join(settings.BASE_DIR, '..', 'Adarsh-Website-New', 'db.sqlite3')),
            ]
            db_path = next((p for p in candidates if os.path.exists(p)), None)

        if db_path:
            conn = None
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                try:
                    row = cur.execute('SELECT site_name,address,phone1,phone2,email FROM website_businessdetails WHERE is_active=1 LIMIT 1').fetchone()
                    if row:
                        r = dict(row)
                        ph = r.get('phone1') or r.get('phone2') or ''
                        business.update({'site_name': r.get('site_name') or business['site_name'],
                                         'address': r.get('address') or business['address'],
                                         'phone': ph or business['phone'],
                                         'email': r.get('email') or business['email'],
                                         'whatsapp': ''.join(c for c in ph if c.isdigit()) or business['whatsapp']})
                except Exception:
                    pass

                for cat_row in cur.execute(
                    'SELECT id,name,slug,icon,description,is_bento,bento_size,"order" FROM website_portfoliocategory WHERE is_active=1 ORDER BY "order",name'
                ).fetchall():
                    cat = dict(cat_row)
                    icon_name = (cat.get('icon') or 'folder').replace('fas fa-', '').replace('fa-', '')
                    products_list = []
                    for pr in cur.execute(
                        'SELECT id,title,slug,description,image,orientation,item_type,video_url,video_file,is_featured,"order",created_at '
                        'FROM website_portfolioitem WHERE is_active=1 AND category_id=? ORDER BY "order",created_at DESC',
                        (cat['id'],)
                    ).fetchall():
                        p = dict(pr)
                        img = p.get('image') or ''
                        vf = p.get('video_file') or ''
                        if p.get('item_type') in ('video', 'reel'):
                            media_url = make_absolute(img) if img else make_absolute(vf)
                        else:
                            media_url = make_absolute(img)
                        products_list.append({
                            'id': p['id'], 'title': p['title'], 'slug': p['slug'],
                            'description': p['description'] or '',
                            'item_type': p['item_type'] or 'image', 'orientation': p['orientation'] or '',
                            'media_url': media_url, 'video_url': p['video_url'] or '',
                            'video_fallback_url': make_absolute(vf), 'video_stream_url': '',
                            'video_thumbnail_url': make_absolute(img),
                            'is_featured': bool(p['is_featured']), 'order': p['order'], 'created_at': p['created_at'],
                        })
                    categories.append({
                        'id': cat['id'], 'name': cat['name'], 'slug': cat['slug'], 'icon': icon_name,
                        'description': cat['description'] or '', 'is_bento': bool(cat['is_bento']),
                        'bento_size': cat['bento_size'] or 'normal', 'order': cat['order'], 'products': products_list,
                    })

                for cr in cur.execute(
                    'SELECT id,name,logo,website_display_order,total_records FROM website_websiteclientlogo WHERE website_is_visible=1 ORDER BY website_display_order,created_at DESC'
                ).fetchall():
                    c = dict(cr)
                    clients.append({'id': c['id'], 'name': c['name'], 'logo': make_absolute(c['logo']), 'total_records': c['total_records'] or 0})

                data_loaded = True
                logger.info("landing_data: loaded via SQLite (%d categories)", len(categories))
            except Exception as sq_err:
                logger.error("landing_data: SQLite error: %s", sq_err)
            finally:
                if conn:
                    conn.close()

    # Build hero slider
    all_prods = [p for cat in categories for p in cat.get('products', [])]
    featured = [p for p in all_prods if p.get('is_featured')][:3] or all_prods[:3]
    hero_images = [
        {'id': p['id'], 'image': p.get('media_url') or '', 'title': p['title'],
          'subtitle': (p['description'][:60] + '...') if p.get('description') else 'Premium PVC ID cards and accessories'}
        for p in featured
    ] or [
        {'id': 1, 'image': 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop',
          'title': 'Premium ID Cards', 'subtitle': 'High-quality PVC printing for all institutions'},
        {'id': 2, 'image': 'https://images.unsplash.com/photo-1557804506-669a67965ba0?w=800&auto=format&fit=crop',
          'title': 'Secure & Fast', 'subtitle': 'Trusted by 1000+ organizations across India'},
    ]

    return JsonResponse({'success': True, 'data': {
        'hero_images': hero_images, 'categories': categories, 'clients': clients, 'business': business,
    }})


@require_mobile_client(allow_public=True)
@csrf_exempt
@require_http_methods(['POST'])
def api_website_contact_submit(request):
    """
    Handles submission of contact/enquiry form.
    Proxies the request to the landing website's secure API.
    """
    import json
    import requests
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST

        name = str(data.get('name', '')).strip()
        email = str(data.get('email', '')).strip()
        phone = str(data.get('phone', '')).strip()
        message = str(data.get('message', '')).strip()
        subject = str(data.get('subject', 'Mobile App Contact Submission')).strip()

        if not all([name, email, message]):
            return JsonResponse({'success': False, 'message': 'Required fields missing'}, status=400)

        # Forward the submission to the landing website API securely
        landing_website_url = os.getenv('LANDING_WEBSITE_URL', 'https://www.adarshbhopal.in').strip()
        api_url = f"{landing_website_url}/api/web-share/contact/"
        api_key = getattr(settings, 'WEB_APP_API_KEY', 'adarsh_secure_fallback_key_2026_web_app')

        payload = {
            'name': name,
            'email': email,
            'phone': phone,
            'subject': subject,
            'message': message
        }
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-API-KEY': api_key
        }

        try:
            response = requests.post(api_url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                res_data = response.json()
                if res_data.get('success'):
                    return JsonResponse({'success': True, 'message': res_data.get('message', 'Message sent successfully!')})
                else:
                    return JsonResponse({'success': False, 'message': res_data.get('message', 'Failed to submit.')}, status=400)
            else:
                logger.error("Landing site contact API returned status %s: %s", response.status_code, response.text)
        except Exception as proxy_err:
            logger.error("Enquiry proxy forwarding failed: %s", proxy_err)

        # Fallback to local log if the website endpoint fails or is unreachable
        logger.info('Mobile contact enquiry received (local fallback): %s <%s>', name, email)
        return JsonResponse({'success': True, 'message': 'Thank you! We have logged your message.'})

    except Exception as e:
        logger.error('Mobile contact submit failed: %s', e)
        return JsonResponse({'success': False, 'message': 'Internal server error'}, status=500)


@require_mobile_client
@csrf_exempt
@require_http_methods(['POST'])
def api_website_portfolio_upload(request):
    """Compatibility endpoint for mobile website portfolio uploads."""
    if PortfolioCategory is None or PortfolioItemService is None:
        return JsonResponse({'success': False, 'message': 'Website portfolio features are unavailable in this build.'}, status=410)

    user = request.user
    if not (PermissionService.is_super_admin(user) or PermissionService.has(user, 'perm_website_edit')):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

    category_id = request.POST.get('category_id') or request.GET.get('category_id')
    category = None
    if category_id:
        try:
            category = PortfolioCategory.objects.filter(id=int(category_id)).first()
        except (TypeError, ValueError):
            category = None

    files = request.FILES.getlist('images') or request.FILES.getlist('files') or []
    if not files:
        return JsonResponse({'success': False, 'message': 'No files uploaded', 'failed_count': 0, 'failed': []}, status=400)

    created = []
    failed = []

    for upload in files:
        try:
            item = PortfolioItemService.create(
                category=category,
                upload=upload,
                user=user,
            )
            created.append(item)
        except Exception as exc:
            failed.append({'name': getattr(upload, 'name', 'upload'), 'error': str(exc)})

    status_code = 200 if created and not failed else 207 if created and failed else 400
    payload = {
        'success': bool(created),
        'count': len(created),
        'failed_count': len(failed),
        'failed': failed,
    }
    return JsonResponse(payload, status=status_code)


@require_mobile_client(allow_public=True)
@require_http_methods(['GET'])
def api_website_portfolio_category_items(request, category_id):
    """Compatibility endpoint for website portfolio category item listing."""
    if PortfolioCategory is None:
        return JsonResponse({'success': False, 'message': 'Website portfolio features are unavailable in this build.'}, status=410)

    if not (PermissionService.is_super_admin(request.user) or PermissionService.has(request.user, 'perm_website_view')):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

    category = get_object_or_404(PortfolioCategory, id=category_id)
    items = list(category.items.filter(is_active=True).values('id', 'title', 'item_type', 'video_url', 'order'))
    return JsonResponse({'success': True, 'items': items, 'count': len(items)})


@require_mobile_client
@csrf_exempt
@require_http_methods(['POST'])
def api_register_device_token(request):
    """
    Registers or updates an Expo push token for the authenticated user.
    """
    try:
        data = json.loads(request.body)
        token = data.get('push_token') or data.get('token')
        if not token:
            return JsonResponse({'success': False, 'message': 'Push token is required'}, status=400)
            
        from mobile_api.models import MobileDeviceToken
        
        # Save or update the token. A token is bound to one user.
        device_token, created = MobileDeviceToken.objects.update_or_create(
            push_token=token,
            defaults={'user': request.user}
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Token registered successfully',
            'created': created
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to register device token")
        return JsonResponse({'success': False, 'message': 'Internal error'}, status=500)

@require_mobile_client
@require_http_methods(['GET'])
def api_photographer_sync(request):
    """
    Returns all assigned clients, tables, and pending/verified cards for the photographer.
    This data is cached locally by the mobile app for offline capture.
    """
    user = request.user
    if not PermissionService.is_photographer(user):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    accessible_ids = PermissionService.get_accessible_client_ids(user) or []
    if not accessible_ids:
        return JsonResponse({'success': True, 'clients': []})
        
    clients = Organisation.objects.filter(id__in=accessible_ids)
    
    tables_qs = (
        Table.objects
        .filter(group__client_id__in=accessible_ids, deleted_by_client=False, is_active=True)
        .select_related('group')
    )
    
    cards_qs = IDCard.objects.filter(
        table__in=tables_qs,
        status__in=['pending', 'verified']
    ).select_related('table')
    
    # Organize data hierarchically
    import collections
    
    cards_by_table = collections.defaultdict(list)
    for card in cards_qs.iterator(chunk_size=1000):
        # We need a slim serialization for offline mode
        has_photo = bool(get_card_photo_url(card))
        cards_by_table[card.table_id].append({
            'id': card.id,
            'table_id': card.table_id,
            'field_data': card.field_data or {},
            'status': card.status,
            'has_photo': has_photo,
        })
        
    tables_by_client = collections.defaultdict(list)
    for t in tables_qs:
        client_id = getattr(t.group, 'client_id', None)
        if client_id:
            tables_by_client[client_id].append({
                'id': t.id,
                'name': t.name,
                'group': t.group.name if t.group else '',
                'cards': cards_by_table.get(t.id, [])
            })
            
    clients_data = []
    for c in clients:
        clients_data.append({
            'id': c.id,
            'name': getattr(c, 'business_name', c.name),
            'tables': tables_by_client.get(c.id, [])
        })
        
    return JsonResponse({'success': True, 'clients': clients_data})

@require_mobile_client
@csrf_exempt
@require_http_methods(['POST'])
def api_photographer_upload_offline(request):
    """
    Accepts bulk offline uploaded photos.
    Expects FormData where each file is keyed by the card_id.
    """
    user = request.user
    if not PermissionService.is_photographer(user):
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
        
    uploaded = 0
    failed = 0
    
    from core.services.idcard_service import IDCardService
    
    for key, file in request.FILES.items():
        try:
            # key should be the card_id
            card_id = int(key)
            card = IDCard.objects.get(id=card_id)
            
            # Verify permission
            if card.table.group.client_id not in (PermissionService.get_accessible_client_ids(user) or []):
                failed += 1
                continue
                
            res = IDCardService.upload_photo(card, file, user)
            if res.success:
                uploaded += 1
            else:
                failed += 1
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"Failed offline upload for card {key}")
            failed += 1
            
    return JsonResponse({
        'success': True, 
        'message': f'Uploaded {uploaded} photos. Failed: {failed}.',
        'uploaded': uploaded,
        'failed': failed
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_validate_photo(request):
    """
    Validate a captured photo for face presence, open eyes, sunglasses, and glasses.
    """
    photo = request.FILES.get('photo')
    if not photo:
        return JsonResponse({'success': False, 'message': 'No photo uploaded'}, status=400)
        
    try:
        try:
            import numpy as np
            import cv2
            file_bytes = np.asarray(bytearray(photo.read()), dtype=np.uint8)
            img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        except Exception:
            img = None

        if img is None:
            # Fallback to PIL to check if valid image
            try:
                from PIL import Image
                photo.seek(0)
                pil_img = Image.open(photo)
                pil_img.verify()
                return JsonResponse({
                    'success': True,
                    'face_detected': False,
                    'eyes_open': False,
                    'wearing_sunglasses': False,
                    'wearing_glasses': False,
                    'message': 'No Person Detected'
                })
            except Exception:
                return JsonResponse({'success': False, 'message': 'Invalid image file'}, status=400)
            
        h, w, _ = img.shape
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        if len(faces) == 0:
            return JsonResponse({
                'success': True,
                'face_detected': False,
                'eyes_open': False,
                'wearing_sunglasses': False,
                'wearing_glasses': False,
                'message': 'No Person Detected'
            })
            
        # Get the largest face
        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        fx, fy, fw, fh = faces[0]
        
        face_gray = gray[fy:fy+fh, fx:fx+fw]
        
        # Upper area of face for eyes
        eye_region_y_start = int(fh * 0.2)
        eye_region_y_end = int(fh * 0.55)
        eye_roi_gray = face_gray[eye_region_y_start:eye_region_y_end, :]
        
        eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
        eye_glasses_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye_tree_eyeglasses.xml')
        
        eyes = eye_cascade.detectMultiScale(eye_roi_gray, 1.15, 3)
        eyes_glasses = eye_glasses_cascade.detectMultiScale(eye_roi_gray, 1.15, 3)
        
        # Sunglasses check: Check if eye band region is extremely dark
        eye_band = face_gray[int(fh*0.35):int(fh*0.5), int(fw*0.15):int(fw*0.85)]
        forehead_band = face_gray[int(fh*0.05):int(fh*0.2), int(fw*0.2):int(fw*0.8)]
        
        avg_eye_brightness = np.mean(eye_band) if eye_band.size > 0 else 128
        avg_forehead_brightness = np.mean(forehead_band) if forehead_band.size > 0 else 128
        
        sunglasses_ratio = avg_eye_brightness / max(1.0, avg_forehead_brightness)
        wearing_sunglasses = (sunglasses_ratio < 0.48) or (avg_eye_brightness < 50)
        
        # Optical Glasses check: Edge density on the nose bridge region
        nose_x_start = int(fw * 0.4)
        nose_x_end = int(fw * 0.6)
        nose_y_start = int(fh * 0.3)
        nose_y_end = int(fh * 0.45)
        
        nose_roi = face_gray[nose_y_start:nose_y_end, nose_x_start:nose_x_end]
        wearing_glasses = False
        if nose_roi.size > 0:
            edges = cv2.Canny(nose_roi, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            wearing_glasses = edge_density > 0.08
            
        # Eyes open check: if not wearing sunglasses, check detected eye count
        eyes_open = True
        if not wearing_sunglasses:
            detected_eye_count = max(len(eyes), len(eyes_glasses))
            if detected_eye_count < 2:
                eyes_open = False
                
        return JsonResponse({
            'success': True,
            'face_detected': True,
            'eyes_open': bool(eyes_open),
            'wearing_sunglasses': bool(wearing_sunglasses),
            'wearing_glasses': bool(wearing_glasses),
            'message': 'Success'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Server processing error: {str(e)}'
        }, status=500)


