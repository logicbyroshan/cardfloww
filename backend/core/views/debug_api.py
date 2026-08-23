"""
Debug, health, and activity log API views.
Split from base.py for maintainability.
"""
import logging
from django.conf import settings as django_settings
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q

from tables.models import IDCard, Table
from ..models import User, ActivityLog
from ..services.permission_service import (
    PermissionService,
    require_any_admin,
)

logger = logging.getLogger(__name__)


# =============================================================================
# HEALTH / VERSION ENDPOINT (auth-protected)
# =============================================================================

@login_required
@require_any_admin
@require_http_methods(["GET"])
def api_health(request):
    """Auth-protected health & version endpoint."""
    return JsonResponse({
        'status': 'ok',
        'version': getattr(django_settings, 'APP_VERSION', 'unknown'),
    })


# =============================================================================
# PERMISSION DEBUG ENDPOINT (super_admin only)
# =============================================================================

@login_required
@require_http_methods(["GET"])
def api_debug_permissions(request):
    """
    Self-check endpoint: returns the effective permissions for the requesting
    user (or for a target_user_id if the requester is super_admin).

    GET /panel/api/debug/permissions/
    GET /panel/api/debug/permissions/?user_id=42
    """
    from ..services.permission_service import PermissionService, api_require_super_admin
    if not PermissionService.is_super_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Super admin access required'}, status=403)

    target_user = request.user
    user_id = request.GET.get('user_id')
    if user_id:
        try:
            target_user = User.objects.get(pk=int(user_id))
        except (User.DoesNotExist, ValueError):
            return JsonResponse({'success': False, 'message': 'User not found'}, status=404)

    info = PermissionService.debug_permissions(target_user)
    return JsonResponse({'success': True, 'data': info})


# =============================================================================
# WORKFLOW DEBUG ENDPOINT (super_admin only)
# =============================================================================

@login_required
@require_http_methods(["GET"])
def api_debug_workflow(request):
    """
    Workflow self-check endpoint.

    GET /panel/api/debug/workflow-check/?card_id=123
        Returns: current status, allowed transitions (all + user-filtered),
                 mandatory-field status, image-field status.

    GET /panel/api/debug/workflow-check/
        Returns: global transition matrix + reprint matrix.
    """
    from ..services.permission_service import PermissionService
    from tables.services_workflow import WorkflowService
    from reprint.services import ReprintWorkflowService

    if not PermissionService.is_super_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Super admin access required'}, status=403)

    card_id = request.GET.get('card_id')
    if card_id:
        try:
            data = WorkflowService.debug_workflow(int(card_id), user=request.user)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'message': 'Invalid card_id'}, status=400)
        return JsonResponse({'success': True, 'data': data})

    # Global matrix view
    return JsonResponse({
        'success': True,
        'data': {
            'idcard_transitions': WorkflowService.ALLOWED_TRANSITIONS,
            'idcard_initial_status': WorkflowService.INITIAL_STATUS,
            'idcard_perm_map': WorkflowService.TRANSITION_PERM_MAP,
            'reprint_transitions': ReprintWorkflowService.ALLOWED_TRANSITIONS,
            'reprint_initial_status': ReprintWorkflowService.INITIAL_STATUS,
        }
    })


# =============================================================================
# ALLOWED TRANSITIONS API (any authenticated user)
# =============================================================================

from ..services.permission_service import (
    PermissionService,
    api_require_any_authenticated,
)


@require_http_methods(["GET"])
@api_require_any_authenticated
def api_card_allowed_transitions(request, card_id):

    """
    Return the transitions allowed for a specific card for the requesting user.

    GET /panel/api/card/<card_id>/allowed-transitions/
    Response: { "success": true, "allowed_transitions": ["verified", "pool"] }
    """
    from tables.services_workflow import WorkflowService

    try:
        card = get_object_or_404(IDCard.objects.select_related('table__organisation'), id=card_id)
    except Exception:
        return JsonResponse({'success': False, 'message': 'Card not found'}, status=404)

    # IDOR protection: scope card to requesting user's client
    client_id = card.table.organisation_id
    if not PermissionService.can_access_client(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Card not found'}, status=404)

    allowed = WorkflowService.get_allowed_transitions(card, user=request.user)
    return JsonResponse({
        'success': True,
        'current_status': card.status,
        'allowed_transitions': allowed,
    })


# =============================================================================
# IMAGE INTEGRITY DEBUG ENDPOINT (super_admin only)
# =============================================================================

@login_required
@require_http_methods(["GET"])
def api_debug_image_integrity(request):
    """
    Image integrity self-check endpoint.

    GET /panel/api/debug/image-integrity/?card_id=123
        Returns per-card: each image field's stored value, file-on-disk status,
        thumbnail status, CardMedia record status.

    GET /panel/api/debug/image-integrity/?table_id=45
        Returns aggregate: total cards, missing images count, missing thumbnails
        count, orphan CardMedia count.
    """
    from ..services.permission_service import PermissionService
    from mediafiles.services import ImageService
    from ..services.base import BaseService
    from mediafiles.models import CardMedia
    from mediafiles.services import ThumbnailService
    from django.core.files.storage import default_storage

    if not PermissionService.is_super_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Super admin access required'}, status=403)

    card_id = request.GET.get('card_id')
    table_id = request.GET.get('table_id')

    if card_id:
        try:
            card = get_object_or_404(IDCard.objects.select_related('table'), id=int(card_id))
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'message': 'Invalid card_id'}, status=400)

        table = card.table
        image_field_names = BaseService.get_image_field_names(table.fields)
        field_data = card.field_data or {}
        fields_report = []

        for fname in image_field_names:
            value = field_data.get(fname, '')
            file_exists = False
            thumb_exists = False
            thumb_path = None
            cm_exists = False

            if value and value not in ('NOT_FOUND', '') and not value.startswith('PENDING:'):
                try:
                    file_exists = default_storage.exists(value)
                except Exception:
                    pass
                thumb_path = ThumbnailService.get_thumbnail_path(value)
                if thumb_path:
                    try:
                        thumb_exists = default_storage.exists(thumb_path)
                    except Exception:
                        pass

            cm_exists = CardMedia.objects.filter(card=card, field_name=fname).exists()

            fields_report.append({
                'field_name': fname,
                'stored_value': value,
                'is_pending': value.startswith('PENDING:') if value else False,
                'is_empty': not value or value in ('', 'NOT_FOUND'),
                'file_on_disk': file_exists,
                'thumbnail_path': thumb_path,
                'thumbnail_on_disk': thumb_exists,
                'card_media_exists': cm_exists,
            })

        return JsonResponse({
            'success': True,
            'data': {
                'card_id': card.pk,
                'status': card.status,
                'fields': fields_report,
            }
        })

    if table_id:
        try:
            table = get_object_or_404(Table, id=int(table_id))
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'message': 'Invalid table_id'}, status=400)

        image_field_names = BaseService.get_image_field_names(table.fields)
        cards = IDCard.objects.filter(table=table)
        total = cards.count()
        missing_files = 0
        missing_thumbs = 0
        pending_count = 0
        empty_count = 0

        # Sample up to 500 cards for performance
        sample = cards.order_by('id')[:500]

        for card in sample:
            fd = card.field_data or {}
            for fname in image_field_names:
                val = fd.get(fname, '')
                if not val or val in ('', 'NOT_FOUND'):
                    empty_count += 1
                elif val.startswith('PENDING:'):
                    pending_count += 1
                else:
                    try:
                        if not default_storage.exists(val):
                            missing_files += 1
                    except Exception:
                        missing_files += 1
                    tp = ThumbnailService.get_thumbnail_path(val)
                    if tp:
                        try:
                            if not default_storage.exists(tp):
                                missing_thumbs += 1
                        except Exception:
                            missing_thumbs += 1

        # Orphan CardMedia count (records pointing to non-existent cards)
        orphan_cm = CardMedia.objects.filter(
            card__table=table,
        ).exclude(
            card__in=cards,
        ).count()

        return JsonResponse({
            'success': True,
            'data': {
                'table_id': table.pk,
                'table_name': table.name,
                'total_cards': total,
                'sampled_cards': sample.count(),
                'image_fields': image_field_names,
                'missing_files': missing_files,
                'missing_thumbnails': missing_thumbs,
                'pending_images': pending_count,
                'empty_images': empty_count,
                'orphan_card_media': orphan_cm,
            }
        })

    return JsonResponse({
        'success': True,
        'data': {
            'usage': 'Pass ?card_id=N for per-card check, or ?table_id=N for aggregate.',
            'entry_points': [
                'ImageService.save_new_image()',
                'ImageService.replace_image()',
                'ImageService.mark_pending()',
                'ImageService.remove_image()',
                'ImageService.process_image_field()',
            ],
        }
    })


# =========================================================================
# ACTIVITY LOGS API (for Manage Panel → Log History tab)
# =========================================================================

@login_required
@require_any_admin
@require_http_methods(['GET'])
def api_activity_logs(request):
    """GET /api/activity-logs/ — paginated activity log for manage panel."""
    from django.utils.timesince import timesince as django_timesince
    from django.utils import timezone as tz

    try:
        limit = int(request.GET.get('limit', 30))
    except (ValueError, TypeError):
        limit = 30
    limit = min(max(limit, 1), 100)

    try:
        offset = int(request.GET.get('offset', 0))
    except (ValueError, TypeError):
        offset = 0
    offset = max(offset, 0)
    search = request.GET.get('search', '').strip()
    action_filter   = request.GET.get('action', '').strip()
    user_role_filter = request.GET.get('user_role', '').strip()

    qs = ActivityLog.objects.select_related('user').order_by('-created_at')

    if action_filter:
        qs = qs.filter(action=action_filter)
    if user_role_filter:
        qs = qs.filter(user__role=user_role_filter)
    if search:
        from django.db.models import Q
        qs = qs.filter(
            Q(description__icontains=search) |
            Q(target_name__icontains=search) |
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__username__icontains=search)
        )

    total = qs.count()
    entries = qs[offset:offset + limit]
    now = tz.now()

    # Build action display labels
    action_dict = dict(ActivityLog.ACTION_CHOICES)

    logs = []
    for entry in entries:
        user_name = ''
        if entry.user:
            user_name = entry.user.get_full_name() or entry.user.username
        logs.append({
            'id': entry.pk,
            'user_name': user_name,
            'action': entry.action,
            'action_display': action_dict.get(entry.action, entry.action),
            'description': entry.description,
            'target_name': entry.target_name or '',
            'ip_address': entry.ip_address or '',
            'icon_class': entry.icon_class,
            'icon_color': entry.icon_color,
            'time_ago': django_timesince(entry.created_at, now),
            'created_at': entry.created_at.isoformat(),
        })

    return JsonResponse({'success': True, 'logs': logs, 'total': total})
