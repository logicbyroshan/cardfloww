"""
Dashboard views for the panel home and dashboard API endpoints.
Split from base.py for maintainability.
"""
import json
import logging
import re
from collections import defaultdict
from django.conf import settings
from django.core.cache import cache
from django.contrib.sessions.models import Session
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import Count, F, Max, Q, Min
from django.utils import timezone

from client.models import Client
from idcards.models import IDCard, IDCardTable
from ..models import User
from ..services import IDCardService
from ..services.activity_service import ActivityService
from ..services.cache_version_service import CacheVersionService
from ..services.live_presence_service import LiveClientPresenceService
from ..utils.htmx import is_htmx
from ..services.permission_service import (
    PermissionService,
    require_any_admin,
    api_require_any_admin,
    api_require_any_authenticated,
)
from .base_helpers import (
    get_user_role,
    ACTIVITY_FEED_MAX,
    GLOBAL_SEARCH_DB_LIMIT,
    GLOBAL_SEARCH_RESULT_LIMIT,
)

logger = logging.getLogger(__name__)
GLOBAL_SEARCH_CACHE_TTL = 120
_ACTIVITY_STATUS_TO_QUERY = {
    'pending': 'pending',
    'verified': 'verified',
    'approved': 'approved',
    'download': 'download',
    'downloaded': 'download',
    'pool': 'pool',
    'reprint': 'reprint',
}
_ACTIVITY_MOVE_TO_RE = re.compile(r'\bmoved\s+from\s+.+?\s+to\s+([a-zA-Z_\- ]+)', re.IGNORECASE)
_ACTIVITY_CLIENT_SUFFIX_RE = re.compile(r'\bfor\s+"?([^"\n]+?)"?\s*$', re.IGNORECASE)


def _dashboard_live_surface_counts(*, user, is_scoped=False, accessible_ids=None):
    """Return unique logged-in user counts split by desktop/mobile surface and never-active status."""
    now = timezone.now()
    cache_key = f'dashboard_live_surface_counts:{user.pk if is_scoped else "all"}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    allowed_user_ids = None
    if is_scoped:
        scoped_client_ids = list(accessible_ids or [])
        client_user_ids = set(
            Client.objects.filter(id__in=scoped_client_ids).values_list('user_id', flat=True)
        )
        from assistants.models import Assistant
        assistant_user_ids = set(
            Assistant.objects.filter(
                client_id__in=scoped_client_ids,
            ).values_list('user_id', flat=True)
        )
        admin_user_ids = set(
            User.objects.filter(role__in=['super_admin', 'operator', 'pro_user']).values_list('id', flat=True)
        )
        allowed_user_ids = client_user_ids | assistant_user_ids | admin_user_ids
    else:
        allowed_user_ids = set(User.objects.filter(is_active=True).values_list('id', flat=True))

    from accounts.models import UserDeviceSession

    # Fetch device sessions active in the last year (365 days), ordered by last_active descending (most recent first)
    cutoff = now - timezone.timedelta(days=365)
    device_sessions = UserDeviceSession.objects.filter(
        user_id__in=allowed_user_ids,
        last_active__gte=cutoff
    ).order_by('-last_active')

    # Get the latest device surface type for each active user
    user_latest_surface = {}
    for ds in device_sessions:
        if ds.user_id not in user_latest_surface:
            user_latest_surface[ds.user_id] = ds.device_type

    desktop_count = 0
    mobile_count = 0
    never_active_count = 0

    for uid in allowed_user_ids:
        device_type = user_latest_surface.get(uid)
        if device_type == 'web':
            desktop_count += 1
        elif device_type == 'mobile':
            mobile_count += 1
        else:
            never_active_count += 1

    result = {
        'desktop': desktop_count,
        'mobile': mobile_count,
        'never_active': never_active_count,
    }
    cache.set(cache_key, result, 15)
    return result


def _parse_dashboard_limit(raw_limit, *, default=500, max_limit=500):
    """Parse and clamp dashboard limit query params."""
    try:
        limit = int(raw_limit)
    except (ValueError, TypeError):
        limit = default
    return min(max(limit, 1), max_limit)


def _parse_json_body(request):
    raw_body = getattr(request, 'body', b'') or b''
    if not raw_body:
        return {}
    try:
        return json.loads(raw_body.decode('utf-8'))
    except (TypeError, ValueError, UnicodeDecodeError):
        return {}


def _dashboard_recent_activity_cache_key(*, user, limit, surface):
    """Per-user key for short-lived dashboard activity caches."""
    user_id = getattr(user, 'pk', 'anon')
    user_role = getattr(user, 'role', 'anon')
    return f'dash:recent-activity:{surface}:{user_id}:{user_role}:{int(limit)}'


def _get_dashboard_recent_activities(*, user, limit, merge_card_activity=True):
    """Return latest activity entries for the dashboard recent-updates feed."""
    return ActivityService.get_recent(limit=limit, hours=None, user=user, merge_card_activity=merge_card_activity, merge_similar_activity=merge_card_activity)


def _normalize_activity_name(value):
    """Normalize names for case-insensitive matching."""
    return ' '.join(str(value or '').strip().lower().split())


def _extract_activity_client_name(activity):
    """Best-effort client name extraction from activity fields/description."""
    client_context = str(activity.get('client_context') or '').strip()
    if client_context:
        return client_context

    description = str(activity.get('description') or '').strip()
    match = _ACTIVITY_CLIENT_SUFFIX_RE.search(description)
    if match:
        return match.group(1).strip()

    return ''


def _extract_activity_status_query(activity):
    """Map activity text/action to an ID card status query value."""
    action = str(activity.get('action') or '').strip().lower()
    description = str(activity.get('description') or '').strip().lower()

    if action in ('reprint_request', 'reprint_status'):
        return 'reprint'

    move_match = _ACTIVITY_MOVE_TO_RE.search(description)
    if move_match:
        token = move_match.group(1).strip().lower().replace('-', ' ').replace('_', ' ')
        token = ' '.join(token.split())
        if token in _ACTIVITY_STATUS_TO_QUERY:
            return _ACTIVITY_STATUS_TO_QUERY[token]

    for token, mapped in _ACTIVITY_STATUS_TO_QUERY.items():
        if re.search(rf'\b{re.escape(token)}\b', description):
            return mapped

    return ''


def _build_recent_activity_link(activity, *, staff_type_map, card_meta_map, client_id_by_name, first_table_by_client):
    """Return best destination URL for clicking a recent activity chip."""
    action = str(activity.get('action') or '').strip().lower()
    target_model = str(activity.get('target_model') or '').strip().lower()
    target_id = activity.get('target_id')
    actor_role = str(activity.get('actor_role') or '').strip().lower()

    try:
        target_id_int = int(target_id) if target_id is not None else None
    except (TypeError, ValueError):
        target_id_int = None

    if target_model == 'idcard' and target_id_int and target_id_int in card_meta_map:
        card_meta = card_meta_map[target_id_int]
        table_id = card_meta.get('table_id')
        if table_id:
            status = card_meta.get('status') or _extract_activity_status_query(activity)
            status_query = f'?status={status}' if status else ''
            highlight = f'&highlight={target_id_int}' if status_query else f'?highlight={target_id_int}'
            return f'{reverse("idcard_actions", args=[table_id])}{status_query}{highlight}'

    if target_model == 'staff' and target_id_int:
        staff_type = staff_type_map.get(target_id_int)
        if staff_type == 'client_staff':
            return reverse('manage_client_staff')
        if staff_type == 'admin_staff':
            return reverse('manage_staff')

    if target_model == 'client':
        return reverse('manage_clients')

    if action.startswith('client_'):
        return reverse('manage_clients')
    if action.startswith('staff_'):
        return reverse('manage_client_staff') if target_model == 'staff' and target_id_int and staff_type_map.get(target_id_int) == 'client_staff' else reverse('manage_staff')

    if action in ('login', 'logout'):
        if actor_role in ('prime_manager', 'manager', 'guest_prime_manager', 'client'):
            return reverse('manage_clients')
        if actor_role in ('assistant', 'client_staff'):
            return reverse('manage_client_staff')
        if actor_role in ('admin_staff', 'super_admin'):
            return reverse('manage_staff')

    if action.startswith('card_') or action.startswith('reprint_') or action in ('bulk_upgrade', 'bulk_delete', 'image_upload', 'image_reupload'):
        client_name = _extract_activity_client_name(activity)
        client_id = client_id_by_name.get(_normalize_activity_name(client_name)) if client_name else None
        if client_id:
            status = _extract_activity_status_query(activity)
            table_id = first_table_by_client.get(client_id)
            if table_id and status:
                return f'{reverse("idcard_actions", args=[table_id])}?status={status}'
            return reverse('idcard_group', args=[client_id])
        return reverse('manage_clients')

    return ''


def _enrich_recent_activities_for_dashboard(user, activities):
    """Attach click targets + fallback timestamp display for dashboard feed items."""
    if not activities:
        return []

    activity_list = list(activities)

    staff_ids = set()
    card_ids = set()
    client_names = set()

    for activity in activity_list:
        target_model = str(activity.get('target_model') or '').strip().lower()
        target_id = activity.get('target_id')
        try:
            target_id_int = int(target_id) if target_id is not None else None
        except (TypeError, ValueError):
            target_id_int = None

        if target_model == 'staff' and target_id_int:
            staff_ids.add(target_id_int)
        elif target_model == 'idcard' and target_id_int:
            card_ids.add(target_id_int)

        extracted_client_name = _extract_activity_client_name(activity)
        if extracted_client_name:
            client_names.add(_normalize_activity_name(extracted_client_name))

        if target_model == 'client':
            target_name = str(activity.get('target_name') or '').strip()
            if target_name:
                client_names.add(_normalize_activity_name(target_name))

    staff_type_map = {}
    if staff_ids:
        from operators.models import Operator
        from assistants.models import Assistant
        for row in Operator.objects.filter(id__in=staff_ids).values('id'):
            staff_type_map[row['id']] = 'admin_staff'
        for row in Assistant.objects.filter(id__in=staff_ids).values('id'):
            staff_type_map[row['id']] = 'client_staff'

    card_meta_map = {}
    if card_ids:
        card_meta_map = {
            row['id']: {'table_id': row.get('table_id'), 'status': row.get('status')}
            for row in IDCard.objects.filter(id__in=card_ids).values('id', 'table_id', 'status')
        }

    client_id_by_name = {}
    if client_names:
        name_filter = Q()
        for name in client_names:
            if name:
                name_filter |= Q(name__iexact=name)

        if name_filter:
            accessible_clients = (
                PermissionService.get_accessible_clients(user, Client.objects.all())
                .filter(name_filter)
                .only('id', 'name')
            )
            for client in accessible_clients:
                key = _normalize_activity_name(client.name)
                if key in client_names and key not in client_id_by_name:
                    client_id_by_name[key] = client.id

    first_table_by_client = {}
    if client_id_by_name:
        client_ids = list(client_id_by_name.values())
        first_table_rows = (
            IDCardTable.objects
            .filter(group__client_id__in=client_ids)
            .values('group__client_id')
            .annotate(first_table_id=Min('id'))
        )
        first_table_by_client = {
            row['group__client_id']: row['first_table_id']
            for row in first_table_rows
        }

    for activity in activity_list:
        if not activity.get('created_at_display'):
            created_raw = str(activity.get('created_at') or '').strip()
            try:
                created_dt = timezone.datetime.fromisoformat(created_raw.replace('Z', '+00:00')) if created_raw else None
                if created_dt is not None:
                    if timezone.is_naive(created_dt):
                        created_dt = timezone.make_aware(created_dt, timezone.get_current_timezone())
                    activity['created_at_display'] = timezone.localtime(created_dt).strftime('%d-%m-%Y %H:%M')
            except Exception:
                activity['created_at_display'] = ''

        activity['url'] = _build_recent_activity_link(
            activity,
            staff_type_map=staff_type_map,
            card_meta_map=card_meta_map,
            client_id_by_name=client_id_by_name,
            first_table_by_client=first_table_by_client,
        )

    return activity_list


# ── Services ─────────────────────────────────────────────────────────────
@login_required
@require_any_admin

# ── Login As User (Pro User only) ─────────────────────────────────────
@login_required
def login_as_user_page(request):
    """Dedicated page for Pro User impersonation."""
    if not PermissionService.can_use_pro_user_options(request.user):
        return redirect('dashboard')
    context = {
        'active_page': 'impersonate',
        'user_role': get_user_role(request.user),
    }
    return render(request, 'index.html', context)


# ── Pro User Deep History (Pro User only) ─────────────────────────────
@login_required
def pro_user_activity_logs_page(request):
    """Backward-compatible URL for the merged Pro User User Options page."""
    if not PermissionService.can_use_pro_user_options(request.user):
        return redirect('dashboard')
    return redirect('login_as_user')




@login_required
def pro_user_guest_users_page(request):
    """Dedicated page for Pro User guest sandbox account management."""
    if not PermissionService.can_manage_pro_features(request.user):
        return redirect('dashboard')

    current_client = getattr(request.user, 'client_profile', None)

    context = {
        'active_page': 'pro_user_guest_users',
        'user_role': get_user_role(request.user),
        'current_client_id': getattr(current_client, 'id', ''),
    }
    return render(request, 'index.html', context)


@login_required
def pro_user_batch_jobs_page(request):
    """Dedicated page for Pro User batch jobs tracking."""
    if not PermissionService.can_manage_pro_features(request.user):
        return redirect('dashboard')

    context = {
        'active_page': 'pro_user_batch_jobs',
        'pro_tab': 'batch_jobs',
        'user_role': get_user_role(request.user),
    }
    return render(request, 'index.html', context)


@login_required
def pro_user_activity_logs_detail_page(request, user_id):
    """Dedicated detail page for a selected user's deep history (Pro User only)."""
    if not PermissionService.can_use_pro_user_options(request.user):
        return redirect('dashboard')

    target_user = get_object_or_404(User, id=user_id)
    context = {
        'active_page': 'pro_user_activity_logs',
        'user_role': get_user_role(request.user),
        'audit_target': {
            'id': target_user.id,
            'name': (target_user.get_full_name() or target_user.username or target_user.email or f'User {target_user.id}').strip(),
            'email_or_username': target_user.email or target_user.username or '-',
            'role_display': target_user.get_role_display() if hasattr(target_user, 'get_role_display') else (target_user.role or '-'),
        },
    }
    return render(request, 'index.html', context)


# Dashboard
@login_required
@require_any_admin
def dashboard(request):
    """Main dashboard view - Super Admin & Admin Staff"""
    # Scope cache keys per user for admin_staff (they only see assigned clients)
    user = request.user
    is_scoped = PermissionService.is_operator(user)
    cache_suffix = f':{user.pk}' if is_scoped else ''

    # Pre-fetch accessible client IDs ONCE for admin_staff users.
    # This must be computed before any cache block so it's always available
    # when is_scoped=True, regardless of which cache keys hit/miss.
    accessible_ids = PermissionService.get_accessible_client_ids(user) if is_scoped else []

    # Combine card status counts into a single aggregate query.
    # Exclude 'pool' status from total count.
    card_qs = IDCard.objects.all()
    if is_scoped:
        card_qs = card_qs.filter(table__group__client_id__in=accessible_ids)
    card_stats = card_qs.aggregate(
        total=Count('id', filter=Q(status__in=['pending', 'verified', 'approved', 'download'])),
        pending=Count('id', filter=Q(status='pending')),
        verified=Count('id', filter=Q(status='verified')),
        approved=Count('id', filter=Q(status='approved')),
        downloaded=Count('id', filter=Q(status='download')),
        pool=Count('id', filter=Q(status='pool')),
    )

    # Sidebar overview counts (clients/admins/operators/assistents).
    # Show total records, not only active ones.
    overview_cache_key = f'dashboard_overview_stats{cache_suffix}'
    overview_stats = cache.get(overview_cache_key)
    if overview_stats is None:
        clients_qs = Client.objects.all()
        from assistants.models import Assistant
        assistents_qs = Assistant.objects.all()
        if is_scoped:
            clients_qs = clients_qs.filter(id__in=accessible_ids)
            assistents_qs = assistents_qs.filter(client_id__in=accessible_ids)

        overview_stats = {
            'clients': clients_qs.filter(is_guest=False).count(),
            'guest_users': clients_qs.filter(is_guest=True).count(),
            'assistents': assistents_qs.count(),
        }
        cache.set(overview_cache_key, overview_stats, 30)

    live_surface_counts = _dashboard_live_surface_counts(
        user=request.user,
        is_scoped=is_scoped,
        accessible_ids=accessible_ids,
    )

    context = {
        'active_page': 'dashboard',
        'user_role': get_user_role(request.user),
        'total_id_cards': card_stats['total'],
        'pending_cards': card_stats['pending'],
        'verified_cards': card_stats['verified'],
        'approved_cards': card_stats['approved'],
        'downloaded_cards': card_stats['downloaded'],
        'pool_cards': card_stats.get('pool', 0),
        'overview_clients_count': overview_stats.get('clients', 0),
        'overview_guest_users_count': overview_stats.get('guest_users', 0),
        'overview_assistents_count': overview_stats.get('assistents', 0),
        'overview_live_desktop_count': live_surface_counts.get('desktop', 0),
        'overview_live_mobile_count': live_surface_counts.get('mobile', 0),
        'overview_live_never_active_count': live_surface_counts.get('never_active', 0),
    }

    recent_cache_key = _dashboard_recent_activity_cache_key(
        user=request.user,
        limit=ACTIVITY_FEED_MAX,
        surface='page',
    )
    recent_activities = cache.get(recent_cache_key)
    if recent_activities is None:
        recent_activities = _enrich_recent_activities_for_dashboard(
            request.user,
            _get_dashboard_recent_activities(user=request.user, limit=ACTIVITY_FEED_MAX),
        )
        cache.set(recent_cache_key, recent_activities, 15)

    context.update({
        # Dashboard feed always shows latest ACTIVITY_FEED_MAX entries.
        'recent_activities': recent_activities,
    })
    return render(request, 'index.html', context)


@require_http_methods(["GET"])
def api_dashboard_card_stats(request):
    """API endpoint for live dashboard card stats refresh.

    Accessible to authenticated admins — returns empty stats for anonymous
    users so the React frontend doesn't get a 401 error.
    Cached for 10 seconds per user scope to reduce DB pressure from polling.
    """
    try:
        user = request.user
        # Return empty stats for unauthenticated users (React app fallback)
        if not user.is_authenticated:
            return JsonResponse({'success': True, 'stats': {
                'total_id_cards': 0, 'pending': 0, 'verified': 0,
                'approved': 0, 'downloaded': 0, 'pool': 0,
                'total_organizations': 0, 'total_operators': 0,
                'total_assistants': 0, 'total_photographers': 0,
            }})

        is_scoped = PermissionService.is_operator(user)
        cache_suffix = f':{user.pk}' if is_scoped else ''
        cache_key = f'api_dashboard_card_stats{cache_suffix}'

        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse({'success': True, 'stats': cached})

        accessible_ids = PermissionService.get_accessible_client_ids(user) if is_scoped else []

        card_qs = IDCard.objects.all()
        if is_scoped:
            card_qs = card_qs.filter(table__group__client_id__in=accessible_ids)

        agg = card_qs.aggregate(
            total=Count('id', filter=Q(status__in=['pending', 'verified', 'approved', 'download'])),
            pending=Count('id', filter=Q(status='pending')),
            verified=Count('id', filter=Q(status='verified')),
            approved=Count('id', filter=Q(status='approved')),
            downloaded=Count('id', filter=Q(status='download')),
            pool=Count('id', filter=Q(status='pool')),
        )

        # User/org counts — only expose to super admins, scoped for operators
        try:
            from ..models import User as CoreUser
            if is_scoped:
                # Operator sees only their assigned scope
                total_orgs = Client.objects.filter(id__in=accessible_ids).count()
                total_operators = CoreUser.objects.filter(role__in=('operator', 'admin_staff'), is_active=True).count()
                total_assistants = CoreUser.objects.filter(role='assistant', is_active=True).count() if hasattr(CoreUser, 'role') else 0
                total_photographers = CoreUser.objects.filter(role='photographer', is_active=True).count()
            else:
                total_orgs = Client.objects.count()
                total_operators = CoreUser.objects.filter(role__in=('operator', 'admin_staff'), is_active=True).count()
                total_assistants = CoreUser.objects.filter(role='assistant', is_active=True).count() if hasattr(CoreUser, 'role') else 0
                total_photographers = CoreUser.objects.filter(role='photographer', is_active=True).count()
        except Exception:
            total_orgs = 0
            total_operators = 0
            total_assistants = 0
            total_photographers = 0

        stats = {
            'total': agg.get('total', 0),
            'pending': agg.get('pending', 0),
            'verified': agg.get('verified', 0),
            'approved': agg.get('approved', 0),
            'downloaded': agg.get('downloaded', 0),
            'pool': agg.get('pool', 0),
            # Card stat aliases used by StatsGrid
            'total_id_cards': agg.get('total', 0),
            'pending_cards': agg.get('pending', 0),
            'verified_cards': agg.get('verified', 0),
            'approved_cards': agg.get('approved', 0),
            'download_cards': agg.get('downloaded', 0),
            'pool_cards': agg.get('pool', 0),
            # Users Overview counts
            'total_organizations': total_orgs,
            'total_clients': total_orgs,
            'total_operators': total_operators,
            'client_staff_count': total_assistants,
            'total_assistants': total_assistants,
            'total_photographers': total_photographers,
            'guest_users': total_operators,
        }

        cache.set(cache_key, stats, 10)
        return JsonResponse({'success': True, 'stats': stats})
    except Exception as e:
        logger.exception('api_dashboard_card_stats error: %s', e)
        return JsonResponse({'success': False, 'error': 'An error occurred. Please try again.'}, status=500)


@require_http_methods(["GET"])
@api_require_any_admin
def api_recent_client_updates(request):
    """API endpoint to get recent clients with their ID card status counts.

    Client results are cached for 10 seconds; live presence is always fresh.
    """
    try:
        raw_limit = request.GET.get('limit')
        limit = None
        if raw_limit not in (None, '', 'all'):
            limit = _parse_dashboard_limit(raw_limit, default=500, max_limit=500)
        user = request.user

        # Cache the heavy client-results portion (raw SQL aggregation)
        is_scoped = PermissionService.is_operator(user)
        cache_suffix = f':{user.pk}' if is_scoped else ''
        cache_key = f'api_recent_client_updates{cache_suffix}:{"all" if limit is None else limit}'

        # Fast path: return cached results + fresh presence
        cached_results = cache.get(cache_key)
        if cached_results is not None:
            presence_payload = LiveClientPresenceService.get_live_payload_for_user(user)
            return JsonResponse({
                'success': True,
                'clients': cached_results,
                **presence_payload,
            })

        # Get recent clients - scoped by PermissionService
        # Show all accessible clients (including inactive) for dashboard recents.
        # Order by most-recently-approved card data, then newest-created client.
        base_qs = Client.objects.all()
        clients_qs = PermissionService.get_accessible_clients(
            user, base_qs
        ).values('id', 'name', 'status', 'created_at').annotate(
            latest_approved=Max(
                'id_card_groups__tables__id_cards__updated_at',
                filter=Q(id_card_groups__tables__id_cards__status='approved')
            )
        ).order_by(
            F('latest_approved').desc(nulls_last=True),
            F('created_at').desc(nulls_last=True),
            F('id').desc(),
        )
        if limit is not None:
            clients_qs = clients_qs[:limit]

        # Materialize only fields needed by dashboard to keep compatibility with
        # DBs that may not yet have newer optional Client columns.
        clients = list(clients_qs)
        client_ids = [c['id'] for c in clients]

        tables_map = {}
        client_counts_map = {}
        first_table_map = {}

        if client_ids:
            placeholders = ','.join(['%s'] * len(client_ids))
            sql = (
                'SELECT '
                '  t.id AS table_id, '
                '  t.name AS table_name, '
                '  g.client_id AS client_id, '
                '  COALESCE(SUM(CASE WHEN c.status = %s THEN 1 ELSE 0 END), 0) AS pending, '
                '  COALESCE(SUM(CASE WHEN c.status = %s THEN 1 ELSE 0 END), 0) AS verified, '
                '  COALESCE(SUM(CASE WHEN c.status = %s THEN 1 ELSE 0 END), 0) AS approved, '
                '  COALESCE(SUM(CASE WHEN c.status = %s THEN 1 ELSE 0 END), 0) AS downloaded, '
                '  COALESCE(SUM(CASE WHEN c.status = %s THEN 1 ELSE 0 END), 0) AS pool '
                'FROM core_idcardtable t '
                'JOIN core_idcardgroup g ON g.id = t.group_id '
                'LEFT JOIN core_idcard c ON c.table_id = t.id '
                f'WHERE g.client_id IN ({placeholders}) '
                'GROUP BY t.id, t.name, g.client_id '
                'ORDER BY t.id ASC'
            )
            sql_params = ['pending', 'verified', 'approved', 'download', 'pool', *client_ids]

            with connection.cursor() as cursor:
                cursor.execute(sql, sql_params)
                for table_id, table_name, client_id, pending, verified, approved, downloaded, pool in cursor.fetchall():
                    cid = int(client_id)
                    table_payload = {
                        'id': int(table_id),
                        'name': table_name,
                        'pending': int(pending or 0),
                        'verified': int(verified or 0),
                        'approved': int(approved or 0),
                        'downloaded': int(downloaded or 0),
                        'pool': int(pool or 0),
                    }

                    if cid not in tables_map:
                        tables_map[cid] = []
                    tables_map[cid].append(table_payload)

                    if cid not in client_counts_map:
                        client_counts_map[cid] = {
                            'pending': 0,
                            'verified': 0,
                            'approved': 0,
                            'downloaded': 0,
                            'pool': 0,
                        }
                    client_counts_map[cid]['pending'] += table_payload['pending']
                    client_counts_map[cid]['verified'] += table_payload['verified']
                    client_counts_map[cid]['approved'] += table_payload['approved']
                    client_counts_map[cid]['downloaded'] += table_payload['downloaded']
                    client_counts_map[cid]['pool'] += table_payload['pool']

                    current_first = first_table_map.get(cid)
                    if current_first is None or int(table_id) < current_first:
                        first_table_map[cid] = int(table_id)

        results = []
        for client in clients:
            client_id = client['id']
            cc = client_counts_map.get(client_id, {})
            client_name = client.get('name') or ''
            results.append({
                'id': client_id,
                'client_id': client_id,
                'name': client_name,
                'status': client.get('status'),
                'initial': client_name[0].upper() if client_name else 'C',
                'first_table_id': first_table_map.get(client_id),
                'tables': tables_map.get(client_id, []),
                'pending': cc.get('pending', 0),
                'verified': cc.get('verified', 0),
                'approved': cc.get('approved', 0),
                'downloaded': cc.get('downloaded', 0),
                'pool': cc.get('pool', 0),
            })
        cache.set(cache_key, results, 30)

        # Presence is always fresh (already optimized in Task 2)
        presence_payload = LiveClientPresenceService.get_live_payload_for_user(user)
        return JsonResponse({
            'success': True,
            'clients': results,
            **presence_payload,
        })
    except Exception as e:
        logger.exception('api_recent_client_updates error: %s', e)
        return JsonResponse({
            'success': False,
            'error': 'An error occurred. Please try again.'
        }, status=500)


@require_http_methods(["POST"])
@api_require_any_authenticated
def api_presence_track(request):
    """Track explicit client-side presence events (start/heartbeat/stop)."""
    try:
        body = _parse_json_body(request)
        action = str(body.get('action') or request.POST.get('action') or '').strip().lower()
        tab_id = str(body.get('tab_id') or request.POST.get('tab_id') or '').strip()

        if action not in {'start', 'heartbeat', 'stop'}:
            return JsonResponse({'success': False, 'message': 'Invalid presence action.'}, status=400)
        if not tab_id:
            return JsonResponse({'success': False, 'message': 'Missing tab_id.'}, status=400)

        if not request.session.session_key:
            request.session.save()

        result = LiveClientPresenceService.record_event(
            user=request.user,
            session_key=request.session.session_key,
            tab_id=tab_id,
            action=action,
        )
        return JsonResponse({'success': True, 'tracked': bool(result.get('tracked')), 'action': action})
    except Exception as e:
        logger.exception('api_presence_track error: %s', e)
        return JsonResponse({'success': False, 'message': 'Presence tracking failed.'}, status=500)


@require_http_methods(["GET"])
@api_require_any_admin
def api_live_client_presence(request):
    """Return current live working client count + IDs for dashboard updates."""
    try:
        payload = LiveClientPresenceService.get_live_payload_for_user(request.user)
        response = JsonResponse({'success': True, **payload})
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
    except Exception as e:
        logger.exception('api_live_client_presence error: %s', e)
        return JsonResponse({'success': False, 'message': 'Could not load live client presence.'}, status=500)


@require_http_methods(["GET"])
@api_require_any_admin
def api_reprint_overview(request):
    """Dashboard API: per-client counts for Card Reprinting stages."""
    try:
        # from cardprint.models import PrintRequest  # Removed cardprint module
        from reprintcard.models import ReprintRequest

        limit = _parse_dashboard_limit(request.GET.get('limit', 500), default=500, max_limit=500)
        user = request.user

        # Show all accessible clients (including inactive) for both admin roles.
        base_qs = Client.objects.all()
        accessible_clients = PermissionService.get_accessible_clients(user, base_qs)

        # Order reprint clients by latest request-list activity, then newest client.
        reprint_clients_qs = accessible_clients.annotate(
            latest_request_time=Max(
                'id_card_groups__tables__reprint_requests__created_at',
                filter=Q(id_card_groups__tables__reprint_requests__status='requested')
            )
        ).order_by(
            F('latest_request_time').desc(nulls_last=True),
            F('created_at').desc(nulls_last=True),
            F('id').desc(),
        )[:limit]

        reprint_clients_list = list(reprint_clients_qs)
        client_ids = list({c.id for c in reprint_clients_list})

        # ── Reprint source counts per client (Download cards only) ─
        reprint_source_qs = IDCard.objects.filter(
            table__group__client_id__in=client_ids,
            status='download',
        ).values('table__group__client_id').annotate(
            download_list=Count('id')
        )
        reprint_source_map = {r['table__group__client_id']: r for r in reprint_source_qs}

        # ── Reprint request/confirmed counts per client ──────────────
        reprint_counts_qs = ReprintRequest.objects.filter(
            table__group__client_id__in=client_ids,
            card__status='download',
        ).values('table__group__client_id').annotate(
            requested=Count('id', filter=Q(status='requested')),
            confirmed=Count('id', filter=Q(status='confirmed')),
        )
        reprint_map = {r['table__group__client_id']: r for r in reprint_counts_qs}

        # ── Reprint source counts per table ──────────────────────────
        reprint_source_table_qs = IDCard.objects.filter(
            table__group__client_id__in=client_ids,
            status='download',
        ).values('table__id', 'table__name', 'table__group__client_id', 'table__created_at').annotate(
            download_list=Count('id')
        ).order_by('table__id')
        reprint_source_table_map = {}
        for t in reprint_source_table_qs:
            cid = t['table__group__client_id']
            if cid not in reprint_source_table_map:
                reprint_source_table_map[cid] = {}
            reprint_source_table_map[cid][t['table__id']] = {
                'id': t['table__id'],
                'name': t['table__name'],
                'download_list': t['download_list'],
                'requested': 0,
                'confirmed': 0,
                'latest_update': None,
                'table_created_at': t.get('table__created_at'),
            }

        # ── Reprint request/confirmed counts per table ───────────────
        reprint_table_qs = ReprintRequest.objects.filter(
            table__group__client_id__in=client_ids,
            card__status='download',
        ).values('table__id', 'table__name', 'table__group__client_id', 'table__created_at').annotate(
            requested=Count('id', filter=Q(status='requested')),
            confirmed=Count('id', filter=Q(status='confirmed')),
            latest_update=Max('updated_at', filter=Q(status='requested')),
        ).order_by('table__id')

        for t in reprint_table_qs:
            cid = t['table__group__client_id']
            if cid not in reprint_source_table_map:
                reprint_source_table_map[cid] = {}
            if t['table__id'] not in reprint_source_table_map[cid]:
                reprint_source_table_map[cid][t['table__id']] = {
                    'id': t['table__id'],
                    'name': t['table__name'],
                    'download_list': 0,
                    'requested': 0,
                    'confirmed': 0,
                    'latest_update': None,
                    'table_created_at': t.get('table__created_at'),
                }
            reprint_source_table_map[cid][t['table__id']]['requested'] = t['requested']
            reprint_source_table_map[cid][t['table__id']]['confirmed'] = t['confirmed']
            reprint_source_table_map[cid][t['table__id']]['latest_update'] = t['latest_update']
            if not reprint_source_table_map[cid][t['table__id']].get('table_created_at'):
                reprint_source_table_map[cid][t['table__id']]['table_created_at'] = t.get('table__created_at')

        reprint_tables_map = {}
        for cid, t_map in reprint_source_table_map.items():
            tables = list(t_map.values())
            tables.sort(
                key=lambda x: (
                    x.get('latest_update') is not None,
                    x.get('latest_update') or x.get('table_created_at'),
                    x.get('table_created_at'),
                    x.get('id') or 0,
                ),
                reverse=True,
            )
            reprint_tables_map[cid] = tables

        # Total requested should represent all accessible clients, not just the limited list.
        reprint_total_requested = ReprintRequest.objects.filter(
            table__group__client__in=accessible_clients,
            card__status='download',
            status='requested',
        ).count()

        # ── Build per-client results ─────────────────────────────────
        reprint_clients = []

        for c in reprint_clients_list:
            rc = reprint_map.get(c.id, {})
            source = reprint_source_map.get(c.id, {})
            reprint_clients.append({
                'id': c.id,
                'name': c.name,
                'status': c.status,
                'download_list': source.get('download_list', 0),
                'reprint_list': source.get('download_list', 0),
                'requested': rc.get('requested', 0),
                'confirmed': rc.get('confirmed', 0),
                'tables': [
                    {
                        'id': t['id'],
                        'name': t['name'],
                        'download_list': t.get('download_list', 0),
                        'requested': t.get('requested', 0),
                        'confirmed': t.get('confirmed', 0),
                    }
                    for t in reprint_tables_map.get(c.id, [])
                ],
            })

        return JsonResponse({
            'success': True,
            'reprint_clients': reprint_clients,
            'reprint_total_requested': reprint_total_requested,
        })
    except Exception as e:
        logger.exception('api_reprint_overview error: %s', e)
        return JsonResponse({
            'success': False,
            'error': 'An error occurred. Please try again.'
        }, status=500)





@require_http_methods(["GET"])
@api_require_any_admin
def api_recent_activity(request):
    """API endpoint for the Recent Activity feed on the dashboard."""
    try:
        limit = _parse_dashboard_limit(
            request.GET.get('limit', ACTIVITY_FEED_MAX),
            default=ACTIVITY_FEED_MAX,
            max_limit=ACTIVITY_FEED_MAX,
        )
        merge = request.GET.get('merge', '1') != '0'
        activities = _enrich_recent_activities_for_dashboard(
            request.user,
            _get_dashboard_recent_activities(user=request.user, limit=limit, merge_card_activity=merge),
        )
        return JsonResponse({'success': True, 'activities': activities})
    except Exception as e:
        logger.exception('api_recent_activity error: %s', e)
        return JsonResponse({'success': False, 'error': 'An error occurred. Please try again.'}, status=500)


@require_http_methods(["GET"])
@api_require_any_authenticated
def api_global_search(request):
    """API endpoint for global search across all ID cards within clients"""
    try:
        query = request.GET.get('q', '').strip()
        filter_type = str(request.GET.get('filter', 'all') or 'all').strip().lower()
        if filter_type not in ('all', 'name', 'address', 'mobile'):
            filter_type = 'all'
        raw_table_id = (request.GET.get('table_id') or '').strip()

        scoped_table_id = None
        if raw_table_id:
            if not raw_table_id.isdigit():
                return JsonResponse({'success': False, 'message': 'Invalid table scope.'}, status=400)
            scoped_table_id = int(raw_table_id)
            if scoped_table_id <= 0:
                return JsonResponse({'success': False, 'message': 'Invalid table scope.'}, status=400)
        
        if not query or len(query) < 2:
            return JsonResponse({
                'success': True,
                'results': [],
                'message': 'Please enter at least 2 characters to search'
            })

        user = request.user
        scope_sig = f'table:{scoped_table_id}' if scoped_table_id else 'all'
        search_version = CacheVersionService.get('global_search', 'all')
        cache_key = f'global-search:v2:{search_version}:{user.id}:{scope_sig}:{filter_type}:{query.lower()}'
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)
        
        results = []
        query_upper = query.upper()
        image_field_types = {'photo', 'rel_photo', 'mother_photo', 'father_photo', 'image', 'signature'}
        non_searchable_field_types = {'file', 'barcode', 'qr_code'}
        non_searchable_name_tokens = ('BARCODE', 'QR', 'FILE')
        
        # Build base queryset - keep the card payload narrow.
        base_cards = IDCard.objects.only(
            'id', 'table_id', 'field_data', 'status', 'photo'
        ).filter(
            field_data__icontains=query
        )
        
        # Scope by role
        _manager_roles = ('prime_manager', 'manager', 'guest_prime_manager', 'client', 'client_staff', 'assistant')
        is_client_role = user.role in _manager_roles
        if PermissionService.is_super_admin(user):
            pass  # super_admin sees all
        elif PermissionService.is_client_role(user):
            from client.services import ClientAccessService
            client = ClientAccessService.get_client_for_user(user)
            if client:
                base_cards = base_cards.filter(table__organisation=client)
            else:
                base_cards = base_cards.none()
        else:
            # Admin staff sees only assigned organisations — use PermissionService
            accessible_ids = PermissionService.get_accessible_client_ids(user)
            if accessible_ids:
                base_cards = base_cards.filter(table__organisation_id__in=accessible_ids)
            else:
                base_cards = base_cards.none()

        if scoped_table_id:
            scoped_table = IDCardTable.objects.only('id', 'organisation_id').filter(id=scoped_table_id).first()
            if not scoped_table:
                return JsonResponse({'success': False, 'message': 'Table not found.'}, status=404)

            if not PermissionService.can_access_client(user, scoped_table.organisation_id):
                return JsonResponse({'success': False, 'message': 'Access denied.'}, status=403)

            if PermissionService.is_client_role(user):
                from client.services import ClientAccessService
                if not ClientAccessService.can_access_table(user, scoped_table):
                    return JsonResponse({'success': False, 'message': 'Access denied.'}, status=403)

            base_cards = base_cards.filter(table_id=scoped_table_id)
        
        cards = list(base_cards[:GLOBAL_SEARCH_DB_LIMIT])  # Limit at database level for speed
        if not cards:
            payload = {
                'success': True,
                'results': [],
                'count': 0,
                'query': query,
            }
            cache.set(cache_key, payload, GLOBAL_SEARCH_CACHE_TTL)
            return JsonResponse(payload)

        table_ids = sorted({card.table_id for card in cards if card.table_id})
        table_map = {
            table.id: table
            for table in IDCardTable.objects.filter(id__in=table_ids).select_related('group__client').only(
                'id',
                'name',
                'fields',
                'group__client__name',
            )
        }

        field_type_map_by_table = {}
        display_field_by_table = {}
        image_fields_by_table = {}
        for table_id, table in table_map.items():
            field_type_by_name = {}
            display_field_name = ''
            image_field_names = []

            for field in (table.fields or []):
                field_name = str(field.get('name', '')).strip()
                if not field_name:
                    continue

                field_name_upper = field_name.upper()
                field_type = str(field.get('type', 'text')).strip().lower()
                field_type_by_name[field_name_upper] = field_type

                if not display_field_name and field_type in ('text', 'textarea'):
                    display_field_name = field_name

                if field_type in ('photo', 'rel_photo', 'mother_photo', 'father_photo', 'image', 'signature'):
                    image_field_names.append(field_name)

            field_type_map_by_table[table_id] = field_type_by_name
            display_field_by_table[table_id] = display_field_name
            image_fields_by_table[table_id] = image_field_names

        is_client_role = PermissionService.is_client_role(user)
        route_name = 'client:idcard_actions' if is_client_role else 'idcard_actions'
        route_prefix_by_table = {}

        for card in cards:
            table = table_map.get(card.table_id)
            if not table:
                continue

            field_data = card.field_data if isinstance(card.field_data, dict) else {}
            matched_field = ''
            matched_value = ''

            field_type_by_name = field_type_map_by_table.get(card.table_id, {})
            
            # Find which field matched
            for field_name, field_value in field_data.items():
                if not field_value:
                    continue
                    
                field_name_upper = str(field_name).upper()
                field_type = field_type_by_name.get(field_name_upper, '')

                is_image_field = (
                    field_type in image_field_types
                    or ((not field_type) and ('PHOTO' in field_name_upper or 'IMAGE' in field_name_upper or 'SIGN' in field_name_upper))
                )

                if is_image_field:
                    if filter_type != 'all':
                        continue
                    image_basename = IDCardService.image_path_basename(field_value)
                    if image_basename and query_upper in image_basename.upper():
                        matched_field = field_name
                        matched_value = image_basename
                        break
                    continue

                # Ignore image/file-like columns so storage paths do not pollute search.
                if field_type in non_searchable_field_types:
                    continue
                if (not field_type) and any(token in field_name_upper for token in non_searchable_name_tokens):
                    continue

                field_value_str = str(field_value).upper()
                
                # Apply filter
                if filter_type != 'all':
                    if filter_type == 'name' and 'NAME' not in field_name_upper:
                        continue
                    elif filter_type == 'address' and 'ADDRESS' not in field_name_upper:
                        continue
                    elif filter_type == 'mobile' and 'MOBILE' not in field_name_upper and 'PHONE' not in field_name_upper and 'MOB' not in field_name_upper:
                        continue
                
                if query_upper in field_value_str:
                    matched_field = field_name
                    matched_value = str(field_value)
                    break
            
            # Skip cards where no searchable field value actually matched.
            if not matched_field:
                continue
                
            # Get display name from first text field
            display_name = ''
            display_field_name = display_field_by_table.get(card.table_id, '')
            if display_field_name:
                display_name = str(field_data.get(display_field_name) or '').strip()
            if not display_name:
                display_name = str(
                    field_data.get('NAME') or
                    field_data.get('name') or
                    field_data.get('Name') or
                    ''
                ).strip()

            client_name = table.group.client.name if table.group_id and table.group and table.group.client else 'Unknown'
            table_name = table.name or 'Unknown'
            
            # Find first valid photo from image fields
            photo_url = None
            for field_name in image_fields_by_table.get(card.table_id, []):
                val = field_data.get(field_name, '')
                if val and not str(val).startswith('PENDING:') and val != 'NOT_FOUND':
                    photo_url = f'/media/{val}' if not str(val).startswith('/') else val
                    break
            # Fallback to legacy photo field
            if not photo_url and card.photo:
                try:
                    photo_url = card.photo.url
                except Exception:
                    pass

            if card.table_id not in route_prefix_by_table:
                route_prefix_by_table[card.table_id] = reverse(route_name, args=[card.table_id])

            detail_url = f'{route_prefix_by_table[card.table_id]}?status={card.status}&highlight={card.id}'
            
            results.append({
                'type': 'idcard',
                'id': card.id,
                'title': display_name or f'Card #{card.id}',
                'subtitle': f'{client_name} • {table_name} • {card.get_status_display()}',
                'table_id': card.table_id,
                'table_name': table_name,
                'matched_field': matched_field or 'Field',
                'matched_value': matched_value or query,
                'url': detail_url,
                'icon': 'fa-id-card',
                'status': card.status,
                'status_display': card.get_status_display(),
                'photo': photo_url,
            })
            
            # Stop after limit for speed
            if len(results) >= GLOBAL_SEARCH_RESULT_LIMIT:
                break
        
        # Sort by title
        results.sort(key=lambda x: x['title'])
        
        payload = {
            'success': True,
            'results': results,
            'count': len(results),
            'query': query
        }
        cache.set(cache_key, payload, GLOBAL_SEARCH_CACHE_TTL)
        return JsonResponse(payload)
    except Exception as e:
        logger.exception('api_global_search error: %s', e)
        return JsonResponse({'success': False, 'message': 'An error occurred. Please try again.'}, status=500)
