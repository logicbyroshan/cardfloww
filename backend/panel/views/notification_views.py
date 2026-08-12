"""
Notification views  (panel app)
================================
User-facing + admin notification API endpoints.
Logic moved from core/views/notification_api.py.
"""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from core.models import Notification, NotificationRead, ClientMessage
from core.services.activity_service import ActivityService
from core.services.notification_service import NotificationService
from core.services.permission_service import (
    api_require_super_admin,
    api_require_any_authenticated,
)

logger = logging.getLogger(__name__)


# ── User-facing endpoints (any authenticated user) ──────────────────────

@login_required
@api_require_any_authenticated
@require_http_methods(["GET"])
def api_notifications_list(request):
    """Get notifications for the current user (with read/unread status)."""
    try:
        limit = min(int(request.GET.get('limit', 20)), 50)
        offset = max(int(request.GET.get('offset', 0)), 0)
    except (ValueError, TypeError):
        limit, offset = 20, 0
    unread_only = request.GET.get('unread_only', '').lower() == 'true'
    include_expired = request.GET.get('include_expired', '').lower() == 'true'
    if unread_only:
        include_expired = False

    data = NotificationService.get_notifications_for_user(
        user=request.user,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
        include_expired=include_expired,
    )
    return JsonResponse({'success': True, **data})


@login_required
@api_require_any_authenticated
@require_http_methods(["GET"])
def api_notifications_unread_count(request):
    """Fast endpoint for notification badge count."""
    count = NotificationService.get_unread_count(request.user)
    return JsonResponse({'success': True, 'unread_count': count})


@login_required
@api_require_any_authenticated
@require_http_methods(["POST"])
def api_notification_mark_read(request, notification_id):
    """Mark a single notification as read."""
    result = NotificationService.mark_as_read(request.user, notification_id)
    return JsonResponse(result.to_response_dict())


@login_required
@api_require_any_authenticated
@require_http_methods(["POST"])
def api_notifications_mark_all_read(request):
    """Mark all notifications as read for the current user."""
    result = NotificationService.mark_all_as_read(request.user)
    return JsonResponse(result.to_response_dict())


@login_required
@api_require_any_authenticated
@require_http_methods(["GET"])
def api_client_message_strip(request):
    """Return unread client-message notifications for cross-page strip rendering."""
    limit_raw = request.GET.get('limit', '5')
    try:
        limit = max(1, min(int(limit_raw), 10))
    except (TypeError, ValueError):
        limit = 5

    now = timezone.now()
    unread_qs = (
        ClientMessage.objects
        .filter(
            notification__is_active=True,
            notification__target='selected',
            notification__target_users=request.user,
            notification__title__startswith='Client Message - ',
        )
        .filter(Q(visibility='permanent') | Q(expires_at__gt=now))
        .annotate(
            is_read=Exists(
                NotificationRead.objects.filter(
                    notification_id=OuterRef('notification_id'),
                    user=request.user,
                )
            )
        )
        .filter(is_read=False)
        .select_related('client', 'sent_by', 'notification')
        .order_by('-created_at')[:limit]
    )

    items = []
    for item in unread_qs:
        sender_name = 'System'
        if item.sent_by:
            sender_name = item.sent_by.get_full_name() or item.sent_by.username
        items.append({
            'id': item.id,
            'notification_id': item.notification_id,
            'client_id': item.client_id,
            'client_name': item.client.name,
            'message': item.message,
            'scope': item.scope,
            'scope_display': item.get_scope_display(),
            'visibility': item.visibility,
            'expires_at': item.expires_at.isoformat() if item.expires_at else None,
            'sent_by_name': sender_name,
            'created_at': item.created_at.isoformat(),
        })

    return JsonResponse({'success': True, 'items': items})


# ── Admin endpoints (super admin only) ──────────────────────────────────

@login_required
@api_require_super_admin
@require_http_methods(["GET"])
def api_panel_notifications_list(request):
    """List all notifications for admin panel management."""
    try:
        limit = min(int(request.GET.get('limit', 50)), 100)
        offset = max(int(request.GET.get('offset', 0)), 0)
    except (ValueError, TypeError):
        limit, offset = 50, 0
    search = request.GET.get('search', '')

    data = NotificationService.list_all_notifications(
        limit=limit, offset=offset, search=search
    )
    return JsonResponse({'success': True, **data})


@login_required
@api_require_super_admin
@require_http_methods(["POST"])
def api_panel_notification_create(request):
    """Create and broadcast a notification."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Invalid JSON.'}, status=400)

    result = NotificationService.create_notification(
        title=body.get('title', ''),
        message=body.get('message', ''),
        priority=body.get('priority', 'normal'),
        category=body.get('category', 'general'),
        target=body.get('target', 'all'),
        target_user_ids=body.get('target_user_ids'),
        created_by=request.user,
        send_email=body.get('send_email', False),
        visibility_hours=body.get('visibility_hours', 24),
    )
    if result.success:
        notif_data = (result.data or {}).get('notification') or {}
        notif_id = notif_data.get('id')
        title = notif_data.get('title') or (body.get('title') or '').strip()
        target = (body.get('target') or 'all').strip()
        ActivityService.log(
            'notification_create',
            f'Notification "{title or "untitled"}" created (target: {target})',
            request=request,
            target_model='Notification',
            target_id=notif_id,
            target_name=title,
        )
    status = 200 if result.success else 400
    return JsonResponse(result.to_response_dict(), status=status)


@login_required
@api_require_super_admin
@require_http_methods(["DELETE"])
def api_panel_notification_delete(request, notification_id):
    """Hide (deactivate) a notification."""
    notif_title = ''
    try:
        notif = Notification.objects.filter(id=notification_id).only('title').first()
        if notif:
            notif_title = notif.title or ''
    except Exception as exc:
        logger.debug('Notification title lookup failed before delete for id=%s: %s', notification_id, exc)
        notif_title = ''

    result = NotificationService.delete_notification(notification_id)
    if result.success:
        ActivityService.log(
            'notification_delete',
            f'Notification "{notif_title or notification_id}" hidden',
            request=request,
            target_model='Notification',
            target_id=notification_id,
            target_name=notif_title,
        )
    status = 200 if result.success else 404
    return JsonResponse(result.to_response_dict(), status=status)


@login_required
@api_require_super_admin
@require_http_methods(["GET"])
def api_panel_target_users(request):
    """Get users grouped by role for the target user picker."""
    grouped = NotificationService.get_target_user_options()
    return JsonResponse({'success': True, 'users': grouped})
