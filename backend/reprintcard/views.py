"""
Reprint Card Views
==================
Page views + API endpoints for the Reprint Cards workflow:
    Reprint List (download source) → Request List → Confirmed List

ARCHITECTURE RULES:
- Views are ULTRA-THIN: parse request → call service → return JsonResponse.
- All mutations delegate to ReprintWorkflowService (in this app).
"""
import json
import logging
import re
from urllib.parse import urlparse

from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q
from django.utils.timezone import localtime
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from tables.models import IDCard, Table
from core.services import IDCardService
from core.services.base import BaseService
from core.services.permission_service import PermissionService, api_require_permission, api_require_any_authenticated
from core.services.activity_service import ActivityService
from core.views.base import get_user_role
from core.views.idcard_helpers import _get_class_section_field_names, _build_class_filter_q

from .models import ReprintRequest
from .services import ReprintWorkflowService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _reprint_access_denied():
    return JsonResponse(
        {'status': 'error', 'message': 'Access denied. You are not assigned to this client.'},
        status=403,
    )


def _check_reprint_table_scope(user, table_id):
    """Check user has access to the client owning this table."""
    table = get_object_or_404(Table, id=table_id)
    if not PermissionService.is_super_admin(user):
        operator_profile = getattr(user, 'operator_profile', None)
        if operator_profile:
            if not operator_profile.assigned_organisations.filter(id=table.organisation_id).exists():
                return None, _reprint_access_denied()
        elif PermissionService.is_client_role(user):
            from organisation.services import OrganisationAccessService
            if not OrganisationAccessService.can_access_table(user, table):
                return None, _reprint_access_denied()
    return table, None


def _build_ordered_fields(card, table):
    """Build ordered field list from card field_data with CardMedia fallback for images."""
    fd = card.field_data or {}
    fd_upper = {k.upper(): v for k, v in fd.items()}
    fd_norm = {}

    def _is_missing_image_value(value):
        v = str(value or '').strip()
        if not v:
            return True
        if v == 'NOT_FOUND':
            return True
        if v.startswith('PENDING:'):
            return True
        return False

    def _normalize_image_value(value):
        """Normalize image path values to media-relative form when possible."""
        raw = str(value or '').strip()
        if not raw:
            return ''
        if raw == 'NOT_FOUND' or raw.startswith('PENDING:'):
            return raw

        normalized = raw.replace('\\', '/').strip()
        while '//' in normalized:
            normalized = normalized.replace('//', '/')

        # URL input: use the path section only.
        if normalized.lower().startswith('http://') or normalized.lower().startswith('https://'):
            try:
                normalized = (urlparse(normalized).path or normalized).strip()
            except Exception:
                pass

        # Handle absolute paths by extracting the part after media root markers.
        lower = normalized.lower()
        mediafiles_marker = '/mediafiles/'
        media_marker = '/media/'
        mediafiles_idx = lower.find(mediafiles_marker)
        if mediafiles_idx >= 0:
            normalized = 'mediafiles/' + normalized[mediafiles_idx + len(mediafiles_marker):]
        else:
            media_idx = lower.find(media_marker)
            if media_idx >= 0:
                normalized = 'media/' + normalized[media_idx + len(media_marker):]

        normalized = normalized.lstrip('/').strip()
        while '//' in normalized:
            normalized = normalized.replace('//', '/')

        return normalized

    def _norm_key(value):
        return ''.join(ch for ch in str(value or '').upper() if ch.isalnum())

    for key, value in fd.items():
        nk = _norm_key(key)
        if nk and nk not in fd_norm:
            fd_norm[nk] = value

    def _is_image_field(ftype, fname):
        t = str(ftype or '').lower()
        n = str(fname or '').lower()
        if t in ('image', 'photo', 'file'):
            return True
        if 'designation' in n:
            return False
        return (
            ('image' in t) or ('photo' in t) or ('file' in t) or ('upload' in t) or
            ('photo' in n) or ('image' in n) or ('picture' in n) or ('pic' in n) or ('img' in n) or
            ('signature' in n) or ('barcode' in n) or ('qr' in n)
        )

    def _infer_media_type(fname):
        n = str(fname or '').lower()
        if (('father' in n or 'mother' in n) and ('photo' in n or 'image' in n or 'pic' in n)):
            return 'rel_photo'
        if re.search(r'\b(?:rel(?:ation)?)\s*[_-]?\s*(?:1|one|2|two)\b', n):
            return 'rel_photo'
        if 'signature' in n or n.strip() == 'sign':
            return 'signature'
        if 'barcode' in n:
            return 'barcode'
        if 'qr' in n:
            return 'qr_code'
        if 'photo' in n or 'image' in n or 'picture' in n or 'pic' in n or n.strip() == 'img':
            return 'photo'
        return ''

    # Build a per-card media lookup once (prefetched relation when available).
    media_by_field = getattr(card, '_reprint_media_by_field', None)
    if media_by_field is None:
        media_by_field = {}
        media_by_type = {}
        media_items = []
        try:
            media_items = list(card.media_files.all())
        except Exception:
            media_items = []

        for media in media_items:
            path = ''
            try:
                path = media.file.name or ''
            except Exception:
                path = ''
            if not path:
                continue

            mf = _norm_key(getattr(media, 'field_name', '') or '')
            if mf and mf not in media_by_field:
                media_by_field[mf] = path

            mt = str(getattr(media, 'media_type', '') or '').lower().strip()
            if mt and mt not in media_by_type:
                media_by_type[mt] = path

        card._reprint_media_by_field = media_by_field
        card._reprint_media_by_type = media_by_type
    else:
        media_by_type = getattr(card, '_reprint_media_by_type', {}) or {}

    ordered_fields = []
    for field in table.fields:
        fname = field['name']
        ftype = field.get('type', 'text')
        fval = fd.get(fname, '') or fd_upper.get(fname.upper(), '') or fd_norm.get(_norm_key(fname), '')

        # Image fallback: if field_data is empty/stale but CardMedia exists, use that path.
        if _is_image_field(ftype, fname) and _is_missing_image_value(fval):
            norm_name = _norm_key(fname)
            fval = media_by_field.get(norm_name, '')
            if not fval:
                inferred = _infer_media_type(fname)
                if inferred:
                    if inferred == 'rel_photo':
                        fval = (
                            media_by_type.get('rel_photo', '')
                            or media_by_type.get('father_photo', '')
                            or media_by_type.get('mother_photo', '')
                        )
                    else:
                        fval = media_by_type.get(inferred, '')

            # Final legacy fallback for PHOTO from deprecated ImageField
            if not fval and norm_name == 'PHOTO' and getattr(card, 'photo', None):
                try:
                    fval = card.photo.name or card.photo.url
                except Exception:
                    pass

        if _is_image_field(ftype, fname):
            fval = _normalize_image_value(fval)

        ordered_fields.append({'name': fname, 'type': ftype, 'value': fval})

        if _is_image_field(ftype, fname) and field.get('type') in ('photo', 'rel_photo', 'mother_photo', 'father_photo') and BaseService.is_show_path_enabled(field):
            display_val = BaseService.extract_photo_path_display_value(card, fname, fval)
            ordered_fields.append({'name': fname + ' Path', 'type': 'text', 'value': display_val})
    return ordered_fields


def _require_admin_role(user):
    """Return a 403 JsonResponse if user is not super_admin or admin_staff, else None."""
    if PermissionService.is_any_admin(user):
        return None
    return JsonResponse(
        {'status': 'error', 'message': 'Admin access required for this action.'},
        status=403,
    )


def _can_use_reprint_cards(user) -> bool:
    """Permission for opening reprint picker and creating reprint requests."""
    if PermissionService.has(user, 'perm_idcard_reprint_list'):
        return True
    if PermissionService.is_client_role(user):
        return PermissionService.has(user, 'perm_reprint_request_list')
    return False


def _can_view_reprint_request_list(user) -> bool:
    """Permission for opening the Reprint Request List page/tab."""
    if PermissionService.has(user, 'perm_reprint_request_list'):
        return True
    if PermissionService.is_client_role(user):
        return PermissionService.has(user, 'perm_idcard_reprint_list') or PermissionService.has(user, 'perm_reprint_request_list')
    return False


def _can_view_reprint_confirmed_list(user) -> bool:
    """Permission for opening the Reprint Confirmed List page/tab."""
    return PermissionService.has(user, 'perm_confirmed_list')


def _reprint_permission_denied_response():
    return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)


def _require_reprint_scope(user, scope: str):
    """Role-aware reprint permission gate used by reprint endpoints."""
    if PermissionService.is_super_admin(user):
        return None

    if scope == 'cards':
        allowed = _can_use_reprint_cards(user)
    elif scope == 'request':
        allowed = _can_view_reprint_request_list(user)
    elif scope == 'confirmed':
        allowed = _can_view_reprint_confirmed_list(user)
    elif scope == 'request_or_confirmed':
        allowed = _can_view_reprint_request_list(user) or _can_view_reprint_confirmed_list(user)
    elif scope == 'any_reprint':
        allowed = (
            _can_use_reprint_cards(user)
            or _can_view_reprint_request_list(user)
            or _can_view_reprint_confirmed_list(user)
        )
    else:
        allowed = False

    if allowed:
        return None
    return _reprint_permission_denied_response()


def _parse_offset_limit(request, *, default_limit=100, max_limit=200):
    """Parse and clamp offset/limit query params for list endpoints."""
    try:
        offset = int(request.GET.get('offset', 0))
    except (ValueError, TypeError):
        offset = 0
    try:
        limit = int(request.GET.get('limit', default_limit))
    except (ValueError, TypeError):
        limit = default_limit

    offset = max(offset, 0)
    limit = min(max(limit, 1), max_limit)
    return offset, limit


def _parse_local_datetime_filter(value):
    """Parse datetime-local input safely into an aware datetime."""
    if not value:
        return None
    dt = parse_datetime(value)
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _parse_json_body_dict(request):
    """Parse JSON body and ensure object payloads for mutation endpoints."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None, JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    if not isinstance(body, dict):
        return None, JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    return body, None


def _apply_inline_reprint_edit(table, user, card_ids, inline_field_data):
    """Apply optional inline field edits before creating a reprint request."""
    if inline_field_data is None:
        return None

    if not isinstance(inline_field_data, dict):
        return JsonResponse({'status': 'error', 'message': 'inline_field_data must be an object'}, status=400)

    if not inline_field_data:
        return None

    # Reprint inline edit is for text/meta corrections only.
    # Image mutations are handled by dedicated upload/remove endpoints and
    # should never be rewritten by request-create payloads.
    safe_inline_field_data = {}
    for key, value in inline_field_data.items():
        key_name = str(key or '').strip()
        if not key_name:
            continue
        if IDCardService.is_image_field_name_for_table(key_name, table.fields or []):
            continue
        safe_inline_field_data[key_name] = value

    if not safe_inline_field_data:
        return None

    normalized_ids = ReprintWorkflowService._normalize_positive_int_ids(card_ids)
    if len(normalized_ids) != 1:
        return JsonResponse(
            {'status': 'error', 'message': 'Inline edits are only allowed when exactly one card is selected'},
            status=400,
        )

    target_id = normalized_ids[0]
    card = IDCard.objects.filter(table=table, id=target_id, status='download').only('id').first()
    if not card:
        return JsonResponse(
            {'status': 'error', 'message': 'Inline edits are only allowed for cards in download status'},
            status=400,
        )

    update_result = IDCardService.update_card(
        card_id=card.id,
        field_data=safe_inline_field_data,
        uploaded_by=user if getattr(user, 'is_authenticated', False) else None,
        modified_by=user.username if getattr(user, 'is_authenticated', False) else '',
    )
    if not update_result.success:
        return JsonResponse(
            {'status': 'error', 'message': update_result.message or 'Could not save inline edits'},
            status=400,
        )

    try:
        ActivityService.log(
            'card_update',
            'ID card updated before reprint request',
            user=user,
            target_model='IDCard',
            target_id=card.id,
            target_name=f'Card #{card.id}',
        )
    except Exception:
        pass

    return None


def _get_reprint_step_counts(table):
    """Return download/request/confirmed counts for the reprint workflow."""
    source_cards_count = IDCard.objects.filter(table=table, status='download').count()
    status_counts = ReprintRequest.objects.filter(
        table=table,
        card__status='download',
    ).aggregate(
        request_count=Count('id', filter=Q(status='requested')),
        confirmed_count=Count('id', filter=Q(status='confirmed')),
    )

    request_count = int(status_counts.get('request_count') or 0)
    confirmed_count = int(status_counts.get('confirmed_count') or 0)

    return {
        'download_list': int(source_cards_count),
        'reprint_list': max(0, source_cards_count - request_count),
        'request_list': request_count,
        'confirmed': confirmed_count,
    }




# ---------------------------------------------------------------------------
# API VIEWS
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
@api_require_any_authenticated
def api_reprint_step_counts(request, table_id):
    """Return step counts for the reprint workflow tabs."""
    perm_err = _require_reprint_scope(request.user, 'any_reprint')
    if perm_err:
        return perm_err

    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    step_counts = _get_reprint_step_counts(table)
    return JsonResponse({'status': 'ok', **step_counts})


@require_http_methods(["GET"])
@api_require_any_authenticated
def api_reprint_list(request, table_id):
    """List source IDCards (Download only) for Reprint List step."""
    perm_err = _require_reprint_scope(request.user, 'cards')
    if perm_err:
        return perm_err

    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    query = request.GET.get('q', '').strip()
    available_only = request.GET.get('available_only', '').strip().lower() in ('1', 'true', 'yes')
    offset, limit = _parse_offset_limit(request, default_limit=100, max_limit=200)

    card_qs = IDCard.objects.filter(
        table=table,
        status='download',
    ).prefetch_related('media_files').order_by('-updated_at')

    if available_only:
        busy_card_ids = ReprintRequest.objects.filter(
            table=table,
            status__in=['requested'],
        ).values_list('card_id', flat=True)
        card_qs = card_qs.exclude(id__in=busy_card_ids)

    if query:
        search_q = Q(field_data__icontains=query)
        if query.isdigit():
            search_q |= Q(id=int(query))
        card_qs = card_qs.filter(search_q)

    total = card_qs.count()
    batch = list(card_qs[offset:offset + limit + 1])
    has_more = len(batch) > limit
    if has_more:
        batch = batch[:limit]

    items = []
    for idx, card in enumerate(batch):
        items.append({
            'card_id': card.id,
            'sr_no': offset + idx + 1,
            'status': card.status,
            'status_display': card.get_status_display(),
            'ordered_fields': _build_ordered_fields(card, table),
            'updated_at': localtime(card.updated_at).strftime('%d-%b-%Y %H:%M'),
        })

    return JsonResponse({
        'status': 'ok',
        'items': items,
        'total': total,
        'has_more': has_more,
        'offset': offset,
        'limit': limit,
    })


@require_http_methods(["POST"])
@api_require_any_authenticated
def api_reprint_request_create(request, table_id):
    """Create reprint requests for card IDs (goes to request list).
    Body: { "card_ids": [1, 2, 3], "reason": "optional" }
    """
    perm_err = _require_reprint_scope(request.user, 'cards')
    if perm_err:
        return perm_err

    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    body, json_err = _parse_json_body_dict(request)
    if json_err:
        return json_err

    card_ids = body.get('card_ids', [])
    reason = body.get('reason', '')
    inline_field_data = body.get('inline_field_data')

    inline_err = _apply_inline_reprint_edit(
        table=table,
        user=request.user,
        card_ids=card_ids,
        inline_field_data=inline_field_data,
    )
    if inline_err:
        return inline_err

    result = ReprintWorkflowService.create_requests(
        table=table,
        card_ids=card_ids,
        reason=reason,
        requested_by=request.user,
    )

    if result.success:
        return JsonResponse({
            'status': 'ok',
            'message': result.message,
            'created_count': result.data['created_count'],
            'skipped_count': result.data['skipped_count'],
        })
    return JsonResponse({'status': 'error', 'message': result.message}, status=400)


@require_http_methods(["POST"])
@api_require_any_authenticated
def api_reprint_confirm(request, table_id):
    """Confirm reprint requests: requested → confirmed.
    Body: { "rr_ids": [1, 2, 3] }
    """
    perm_err = _require_reprint_scope(request.user, 'request')
    if perm_err:
        return perm_err

    admin_err = _require_admin_role(request.user)
    if admin_err:
        return admin_err
    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    body, json_err = _parse_json_body_dict(request)
    if json_err:
        return json_err

    rr_ids = body.get('rr_ids', [])
    if not rr_ids:
        return JsonResponse({'status': 'error', 'message': 'No reprint IDs provided'}, status=400)

    result = ReprintWorkflowService.bulk_transition(table, rr_ids, 'confirmed', user=request.user)

    if result.success:
        return JsonResponse({
            'status': 'ok',
            'message': result.message,
            'confirmed_count': result.data.get('updated_count', 0),
        })
    return JsonResponse({'status': 'error', 'message': result.message}, status=400)


@require_http_methods(["POST"])
@api_require_any_authenticated
def api_reprint_retrieve(request, table_id):
    """Move confirmed reprint requests back to requested status.
    Body: { "rr_ids": [1, 2, 3] }
    """
    perm_err = _require_reprint_scope(request.user, 'confirmed')
    if perm_err:
        return perm_err

    admin_err = _require_admin_role(request.user)
    if admin_err:
        return admin_err
    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    body, json_err = _parse_json_body_dict(request)
    if json_err:
        return json_err

    rr_ids = body.get('rr_ids', [])
    if not rr_ids:
        return JsonResponse({'status': 'error', 'message': 'No reprint IDs provided'}, status=400)

    result = ReprintWorkflowService.bulk_transition(table, rr_ids, 'requested', user=request.user)

    if result.success:
        return JsonResponse({
            'status': 'ok',
            'message': result.message,
            'requested_count': result.data.get('updated_count', 0),
            'moved_ids': result.data.get('updated_ids', rr_ids),
        })
    return JsonResponse({'status': 'error', 'message': result.message}, status=400)


@require_http_methods(["GET"])
@api_require_any_authenticated
def api_request_list(request, table_id):
    """List requested reprint requests (status='requested')."""
    perm_err = _require_reprint_scope(request.user, 'request')
    if perm_err:
        return perm_err

    from django.db.models.functions import Cast
    from django.db.models import CharField
    from django.db.models.fields.json import KeyTextTransform

    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    query = request.GET.get('q', '').strip()
    class_filter = request.GET.get('class', '').strip()
    section_filter = request.GET.get('section', '').strip()
    offset, limit = _parse_offset_limit(request, default_limit=100, max_limit=200)

    rr_qs = ReprintRequest.objects.filter(
        table=table,
        status='requested',
        card__status='download',
    ).select_related('card', 'requested_by').prefetch_related('card__media_files').order_by('-created_at')

    from_dt = _parse_local_datetime_filter(request.GET.get('from'))
    to_dt = _parse_local_datetime_filter(request.GET.get('to'))

    class_field_name, section_field_name = _get_class_section_field_names(table)
    if class_filter or section_filter:
        card_scope = IDCard.objects.filter(table=table, status='download')
        if class_filter and class_field_name:
            card_scope = _build_class_filter_q(card_scope, class_filter, class_field_name)
        if section_filter and section_field_name:
            card_scope = card_scope.annotate(
                _reprint_section=Cast(KeyTextTransform(section_field_name, 'field_data'), CharField()),
            ).filter(_reprint_section=section_filter)
        rr_qs = rr_qs.filter(card_id__in=card_scope.values('id'))

    if from_dt:
        rr_qs = rr_qs.filter(created_at__gte=from_dt)
    if to_dt:
        rr_qs = rr_qs.filter(created_at__lte=to_dt)

    if query:
        query_filter = Q(card__field_data__icontains=query)
        if query.isdigit():
            query_filter |= Q(card_id=int(query))
        rr_qs = rr_qs.filter(query_filter)

    total = rr_qs.count()
    batch = list(rr_qs[offset:offset + limit + 1])
    has_more = len(batch) > limit
    if has_more:
        batch = batch[:limit]

    items = []
    for idx, rr in enumerate(batch):
        req_by = rr.requested_by
        items.append({
            'rr_id': rr.id,
            'card_id': rr.card_id,
            'sr_no': offset + idx + 1,
            'requested_by_name': (req_by.get_full_name() or req_by.username) if req_by else 'System',
            'requested_at': localtime(rr.created_at).strftime('%d-%b-%Y %H:%M'),
            'ordered_fields': _build_ordered_fields(rr.card, table),
        })

    return JsonResponse({
        'status': 'ok',
        'items': items,
        'total': total,
        'has_more': has_more,
        'offset': offset,
        'limit': limit,
    })


@require_http_methods(["POST"])
@api_require_any_authenticated
def api_reprint_reject(request, table_id):
    """Reject (delete) reprint requests in 'requested' or 'confirmed' status.
    Body: { "rr_ids": [1, 2, 3] }
    """
    perm_err = _require_reprint_scope(request.user, 'request_or_confirmed')
    if perm_err:
        return perm_err

    admin_err = _require_admin_role(request.user)
    if admin_err:
        return admin_err
    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    body, json_err = _parse_json_body_dict(request)
    if json_err:
        return json_err

    rr_ids = body.get('rr_ids', [])

    result = ReprintWorkflowService.reject_requests(table=table, rr_ids=rr_ids, user=request.user)

    if result.success:
        return JsonResponse({
            'status': 'ok',
            'message': result.message,
            'rejected_count': result.data['rejected_count'],
            'rejected_ids': result.data.get('rejected_ids', []),
        })
    return JsonResponse({'status': 'error', 'message': result.message}, status=400)


@require_http_methods(["GET"])
@api_require_any_authenticated
def api_confirmed_list(request, table_id):
    """List confirmed reprint requests (status='confirmed')."""
    perm_err = _require_reprint_scope(request.user, 'confirmed')
    if perm_err:
        return perm_err

    from django.db.models.functions import Cast
    from django.db.models import CharField
    from django.db.models.fields.json import KeyTextTransform

    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    query = request.GET.get('q', '').strip()
    class_filter = request.GET.get('class', '').strip()
    section_filter = request.GET.get('section', '').strip()
    offset, limit = _parse_offset_limit(request, default_limit=100, max_limit=200)

    rr_qs = ReprintRequest.objects.filter(
        table=table,
        status='confirmed',
        card__status='download',
    ).select_related('card', 'requested_by').prefetch_related('card__media_files').order_by('-updated_at')

    from_dt = _parse_local_datetime_filter(request.GET.get('from'))
    to_dt = _parse_local_datetime_filter(request.GET.get('to'))

    class_field_name, section_field_name = _get_class_section_field_names(table)
    if class_filter or section_filter:
        card_scope = IDCard.objects.filter(table=table, status='download')
        if class_filter and class_field_name:
            card_scope = _build_class_filter_q(card_scope, class_filter, class_field_name)
        if section_filter and section_field_name:
            card_scope = card_scope.annotate(
                _reprint_section=Cast(KeyTextTransform(section_field_name, 'field_data'), CharField()),
            ).filter(_reprint_section=section_filter)
        rr_qs = rr_qs.filter(card_id__in=card_scope.values('id'))

    if from_dt:
        rr_qs = rr_qs.filter(updated_at__gte=from_dt)
    if to_dt:
        rr_qs = rr_qs.filter(updated_at__lte=to_dt)

    if query:
        query_filter = Q(card__field_data__icontains=query)
        if query.isdigit():
            query_filter |= Q(card_id=int(query))
        rr_qs = rr_qs.filter(query_filter)

    total = rr_qs.count()
    batch = list(rr_qs[offset:offset + limit + 1])
    has_more = len(batch) > limit
    if has_more:
        batch = batch[:limit]

    items = []
    for idx, rr in enumerate(batch):
        req_by = rr.requested_by
        items.append({
            'rr_id': rr.id,
            'card_id': rr.card_id,
            'sr_no': offset + idx + 1,
            'requested_by_name': (req_by.get_full_name() or req_by.username) if req_by else 'System',
            'confirmed_at': localtime(rr.updated_at).strftime('%d-%b-%Y %H:%M'),
            'ordered_fields': _build_ordered_fields(rr.card, table),
        })

    return JsonResponse({
        'status': 'ok',
        'items': items,
        'total': total,
        'has_more': has_more,
        'offset': offset,
        'limit': limit,
    })


@require_http_methods(["POST"])
@api_require_any_authenticated
def api_reprint_mark_downloaded(request, table_id):
    """Mark confirmed reprints as downloaded: confirmed → downloaded.
    Body: { "rr_ids": [1, 2, 3] }
    """
    perm_err = _require_reprint_scope(request.user, 'confirmed')
    if perm_err:
        return perm_err

    admin_err = _require_admin_role(request.user)
    if admin_err:
        return admin_err
    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    body, json_err = _parse_json_body_dict(request)
    if json_err:
        return json_err

    rr_ids = body.get('rr_ids', [])
    if not rr_ids:
        return JsonResponse({'status': 'error', 'message': 'No reprint IDs provided'}, status=400)

    result = ReprintWorkflowService.bulk_transition(table, rr_ids, 'downloaded', user=request.user)

    if result.success:
        return JsonResponse({
            'status': 'ok',
            'message': result.message,
            'downloaded_count': result.data.get('updated_count', 0),
        })
    return JsonResponse({'status': 'error', 'message': result.message}, status=400)


@require_http_methods(["GET"])
@api_require_any_authenticated
def api_download_list(request, table_id):
    """List downloaded reprint requests (status='downloaded')."""
    perm_err = _require_reprint_scope(request.user, 'confirmed')
    if perm_err:
        return perm_err

    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    query = request.GET.get('q', '').strip()
    offset, limit = _parse_offset_limit(request, default_limit=100, max_limit=200)

    rr_qs = ReprintRequest.objects.filter(
        table=table, status='downloaded',
    ).select_related('card', 'requested_by').prefetch_related('card__media_files').order_by('-updated_at')

    if query:
        query_filter = Q(card__field_data__icontains=query) | Q(reason__icontains=query)
        if query.isdigit():
            query_filter |= Q(card_id=int(query))
        rr_qs = rr_qs.filter(query_filter)

    total = rr_qs.count()
    batch = list(rr_qs[offset:offset + limit + 1])
    has_more = len(batch) > limit
    if has_more:
        batch = batch[:limit]

    items = []
    for idx, rr in enumerate(batch):
        req_by = rr.requested_by
        items.append({
            'rr_id': rr.id,
            'card_id': rr.card_id,
            'sr_no': offset + idx + 1,
            'status': rr.card.status,
            'status_display': rr.card.get_status_display(),
            'reason': rr.reason,
            'requested_by_name': (req_by.get_full_name() or req_by.username) if req_by else 'System',
            'downloaded_at': localtime(rr.updated_at).strftime('%d-%b-%Y %H:%M'),
            'ordered_fields': _build_ordered_fields(rr.card, table),
        })

    return JsonResponse({
        'status': 'ok',
        'items': items,
        'total': total,
        'has_more': has_more,
        'offset': offset,
        'limit': limit,
    })


# ---------------------------------------------------------------------------
# SEND TO PRINT (confirmed -> cardprint generate list)
# ---------------------------------------------------------------------------

@require_http_methods(["POST"])
@api_require_any_authenticated
def api_reprint_send_to_print(request, table_id):
    """Send requested reprint items to the cardprint Generate List.

    Body: { "rr_ids": [1, 2, 3] }
    Extracts card IDs from requested reprint requests and creates
    PrintRequest entries in the cardprint app.
    """
    perm_err = _require_reprint_scope(request.user, 'request')
    if perm_err:
        return perm_err

    admin_err = _require_admin_role(request.user)
    if admin_err:
        return admin_err
    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    data, json_err = _parse_json_body_dict(request)
    if json_err:
        return json_err

    rr_ids = data.get('rr_ids', [])
    if not rr_ids:
        return JsonResponse({'status': 'error', 'message': 'No items selected'}, status=400)

    # Only allow requested reprint requests
    requested_qs = ReprintRequest.objects.filter(
        id__in=rr_ids,
        table=table,
        status='requested',
        card__status='download',
    )

    requested_rows = list(requested_qs.values_list('id', 'card_id'))
    eligible_rr_ids = [rr_id for rr_id, _ in requested_rows]
    card_ids = [card_id for _, card_id in requested_rows]
    if not card_ids:
        return JsonResponse(
            {'status': 'error', 'message': 'No requested reprint items found'},
            status=400,
        )

    # Cardprint integration removed: move eligible requested rows to
    # confirmed locally without creating PrintRequest entries.
    moved_rows = list(ReprintRequest.objects.filter(
        id__in=eligible_rr_ids,
        table=table,
        status='requested',
        card__status='download',
    ).values_list('id', 'card_id'))

    moved_ids = [r[0] for r in moved_rows]
    moved_card_ids = [r[1] for r in moved_rows]

    if moved_ids:
        ReprintRequest.objects.filter(id__in=moved_ids).update(status='confirmed')
        for card_id in moved_card_ids:
            ActivityService.log(
                'reprint_status',
                'Reprint moved to confirmed (print disabled)',
                user=request.user,
                target_model='IDCard',
                target_id=card_id,
                target_name=f'Card #{card_id}',
            )

    return JsonResponse({
        'status': 'ok',
        'message': f"{len(moved_ids)} request(s) moved to Confirmed List",
        'created': 0,
        'skipped': 0,
        'moved': len(moved_ids),
        'moved_ids': moved_ids,
    })
