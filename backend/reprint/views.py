"""
Reprint Views
=============
API endpoints and page views for the 3-step Reprint workflow:
  1. Reprint List (source downloaded cards) -> 2. Requested List -> 3. Confirmed List
"""
import json
import logging
from urllib.parse import urlparse

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q
from django.utils.timezone import localtime
from django.utils.dateparse import parse_datetime

from tables.models import IDCard, Table
from core.services.permission_service import (
    PermissionService,
    api_require_any_authenticated,
)
from core.views.base import get_user_role
from core.views.idcard_helpers import (
    _get_class_section_field_names,
    _build_class_filter_q,
)

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


def _require_admin_role(user):
    """Verify that the user is an admin or operator."""
    if PermissionService.is_super_admin(user):
        return None
    role = get_user_role(user)
    if role in ('super_admin', 'pro_user', 'operator', 'prime_manager', 'super_manager', 'admin_staff'):
        return None
    return JsonResponse(
        {'status': 'error', 'message': 'Admin privileges required for this action.'},
        status=403,
    )


def _parse_json_body_dict(request):
    try:
        data = json.loads(request.body or '{}')
        return data, None
    except Exception as exc:
        return None, JsonResponse({'status': 'error', 'message': f'Invalid JSON: {exc}'}, status=400)


def _parse_offset_limit(request, default_limit=100, max_limit=200):
    try:
        offset = max(0, int(request.GET.get('offset', 0)))
    except (ValueError, TypeError):
        offset = 0
    try:
        limit = min(max_limit, max(1, int(request.GET.get('limit', default_limit))))
    except (ValueError, TypeError):
        limit = default_limit
    return offset, limit


def _build_ordered_fields(card, table, staged_changes=None):
    """Build ordered field list from card field_data, merging any staged changes."""
    fd = dict(card.field_data or {})
    if staged_changes and isinstance(staged_changes, dict):
        fd.update(staged_changes)

    fields_config = table.fields or []
    ordered = []
    seen = set()

    for col in fields_config:
        col_name = col.get('name') or col.get('field_name') or ''
        if not col_name:
            continue
        val = fd.get(col_name, '')
        seen.add(col_name)
        ordered.append({
            'name': col_name,
            'label': col.get('label') or col_name,
            'type': col.get('type') or 'text',
            'value': val,
            'is_edited': bool(staged_changes and col_name in staged_changes),
        })

    # Include any remaining fields not in fields_config
    for k, v in fd.items():
        if k not in seen:
            ordered.append({
                'name': k,
                'label': k,
                'type': 'text',
                'value': v,
                'is_edited': bool(staged_changes and k in staged_changes),
            })

    return ordered


# ---------------------------------------------------------------------------
# API VIEWS
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
@api_require_any_authenticated
def api_reprint_step_counts(request, table_id):
    """Return step counts for the 3-step reprint workflow tabs."""
    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    source_cards_count = IDCard.objects.filter(table=table, status='download').count()
    request_count = ReprintRequest.objects.filter(table=table, status='requested').count()
    confirmed_count = ReprintRequest.objects.filter(table=table, status='confirmed').count()
    downloaded_count = ReprintRequest.objects.filter(table=table, status='downloaded').count()

    return JsonResponse({
        'status': 'ok',
        'reprint_list': source_cards_count,
        'request_list': request_count,
        'confirmed': confirmed_count,
        'download_list': downloaded_count,
    })


@require_http_methods(["GET"])
@api_require_any_authenticated
def api_reprint_list(request, table_id):
    """
    Step 1: Reprint List (Source Downloaded Cards).
    Shows all downloaded cards for this table uniquely.
    Includes active request status and lifetime reprint counts.
    """
    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    query = request.GET.get('q', '').strip()
    class_filter = request.GET.get('class', '').strip()
    section_filter = request.GET.get('section', '').strip()
    offset, limit = _parse_offset_limit(request, default_limit=100, max_limit=200)

    card_qs = IDCard.objects.filter(
        table=table,
        status='download',
    ).prefetch_related('media_files').order_by('-updated_at')

    # Class & section filtering
    class_field_name, section_field_name = _get_class_section_field_names(table)
    if class_filter and class_field_name:
        card_qs = _build_class_filter_q(card_qs, class_filter, class_field_name)

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

    # Pre-fetch pending request IDs and confirmed counts for this batch
    batch_card_ids = [c.id for c in batch]
    active_requests = dict(
        ReprintRequest.objects.filter(
            table=table,
            card_id__in=batch_card_ids,
            status='requested',
        ).values_list('card_id', 'id')
    )

    confirmed_counts = dict(
        ReprintRequest.objects.filter(
            table=table,
            card_id__in=batch_card_ids,
            status__in=['confirmed', 'downloaded'],
        ).values('card_id').annotate(n=Count('id')).values_list('card_id', 'n')
    )

    items = []
    for idx, card in enumerate(batch):
        cid = card.id
        is_requested = cid in active_requests
        items.append({
            'card_id': cid,
            'sr_no': offset + idx + 1,
            'status': card.status,
            'status_display': card.get_status_display(),
            'is_in_request_queue': is_requested,
            'active_request_id': active_requests.get(cid),
            'reprint_count': confirmed_counts.get(cid, 0),
            'field_data': card.field_data or {},
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
    """
    Create reprint requests from Reprint List.
    Accepts:
      {
        "card_ids": [1, 2],
        "reason": "Lost card / spelling fix",
        "changes": { "1": { "NAME": "New Name" } }
      }
    """
    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    body, json_err = _parse_json_body_dict(request)
    if json_err:
        return json_err

    card_ids = body.get('card_ids', [])
    reason = body.get('reason', '')
    changes_by_card = body.get('changes') or {}

    # Support single card inline edit payload format
    if not changes_by_card and body.get('inline_field_data') and len(card_ids) == 1:
        changes_by_card = {str(card_ids[0]): body.get('inline_field_data')}

    result = ReprintWorkflowService.create_requests(
        table=table,
        card_ids=card_ids,
        reason=reason,
        changes_by_card=changes_by_card,
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


@require_http_methods(["GET"])
@api_require_any_authenticated
def api_request_list(request, table_id):
    """
    Step 2: Requested List (Pending Admin Confirmation).
    Shows cards currently requested for reprint with reason and staged changes diff.
    """
    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    query = request.GET.get('q', '').strip()
    offset, limit = _parse_offset_limit(request, default_limit=100, max_limit=200)

    rr_qs = ReprintRequest.objects.filter(
        table=table,
        status='requested',
    ).select_related('card', 'requested_by').prefetch_related('card__media_files').order_by('-created_at')

    if query:
        query_filter = Q(card__field_data__icontains=query) | Q(reason__icontains=query)
        if query.isdigit():
            query_filter |= Q(card_id=int(query)) | Q(id=int(query))
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
            'reason': rr.reason or 'Reprint Request',
            'reprint_number': rr.reprint_number,
            'changes': rr.changes or {},
            'has_changes': rr.has_changes,
            'requested_by_name': (req_by.get_full_name() or req_by.username) if req_by else 'Staff',
            'requested_at': localtime(rr.created_at).strftime('%d-%b-%Y %H:%M'),
            'field_data': rr.card.field_data or {},
            'ordered_fields': _build_ordered_fields(rr.card, table, staged_changes=rr.changes),
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
def api_reprint_confirm(request, table_id):
    """
    Step 2 -> Step 3: Confirm reprint requests.
    Applies any staged changes in-place to original IDCard and moves status to 'confirmed'.
    """
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

    result = ReprintWorkflowService.confirm_requests(table=table, rr_ids=rr_ids, user=request.user)

    if result.success:
        return JsonResponse({
            'status': 'ok',
            'message': result.message,
            'confirmed_count': result.data.get('confirmed_count', 0),
            'confirmed_ids': result.data.get('confirmed_ids', []),
        })
    return JsonResponse({'status': 'error', 'message': result.message}, status=400)


@require_http_methods(["POST"])
@api_require_any_authenticated
def api_reprint_reject(request, table_id):
    """
    Reject / Cancel reprint requests.
    Cancels request and returns card back to normal in Reprint List.
    """
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
    reason = body.get('reason', '')
    move_to_deleted = bool(body.get('move_to_deleted', False))

    result = ReprintWorkflowService.reject_requests(
        table=table,
        rr_ids=rr_ids,
        reason=reason,
        move_card_to_deleted=move_to_deleted,
        user=request.user,
    )

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
    """
    Step 3: Confirmed List.
    Shows confirmed reprints with their reprint sequence count (Reprint #1, #2, etc.).
    """
    table, err = _check_reprint_table_scope(request.user, table_id)
    if err:
        return err

    query = request.GET.get('q', '').strip()
    offset, limit = _parse_offset_limit(request, default_limit=100, max_limit=200)

    rr_qs = ReprintRequest.objects.filter(
        table=table,
        status='confirmed',
    ).select_related('card', 'requested_by', 'confirmed_by').prefetch_related('card__media_files').order_by('-confirmed_at', '-created_at')

    if query:
        query_filter = Q(card__field_data__icontains=query) | Q(reason__icontains=query)
        if query.isdigit():
            query_filter |= Q(card_id=int(query)) | Q(id=int(query))
        rr_qs = rr_qs.filter(query_filter)

    total = rr_qs.count()
    batch = list(rr_qs[offset:offset + limit + 1])
    has_more = len(batch) > limit
    if has_more:
        batch = batch[:limit]

    items = []
    for idx, rr in enumerate(batch):
        req_by = rr.requested_by
        conf_by = rr.confirmed_by
        items.append({
            'rr_id': rr.id,
            'card_id': rr.card_id,
            'sr_no': offset + idx + 1,
            'reprint_number': rr.reprint_number,
            'reason': rr.reason or 'Confirmed Reprint',
            'changes': rr.changes or {},
            'has_changes': rr.has_changes,
            'requested_by_name': (req_by.get_full_name() or req_by.username) if req_by else 'Staff',
            'confirmed_by_name': (conf_by.get_full_name() or conf_by.username) if conf_by else 'Admin',
            'confirmed_at': localtime(rr.confirmed_at).strftime('%d-%b-%Y %H:%M') if rr.confirmed_at else '—',
            'field_data': rr.card.field_data or {},
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
def api_reprint_retrieve(request, table_id):
    """Move confirmed reprint requests back to requested status."""
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
    result = ReprintWorkflowService.bulk_transition(table, rr_ids, 'requested', user=request.user)

    if result.success:
        return JsonResponse({
            'status': 'ok',
            'message': result.message,
            'requested_count': result.data.get('updated_count', 0),
        })
    return JsonResponse({'status': 'error', 'message': result.message}, status=400)


@require_http_methods(["POST"])
@api_require_any_authenticated
def api_reprint_mark_downloaded(request, table_id):
    """Mark confirmed reprint requests as downloaded."""
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
def api_reprint_card_history(request, card_id):
    """Return full chronological reprint lifecycle history for a specific ID card."""
    card = get_object_or_404(IDCard, id=card_id)
    table, err = _check_reprint_table_scope(request.user, card.table_id)
    if err:
        return err

    history = ReprintWorkflowService.get_card_reprint_history(card_id)
    return JsonResponse({
        'status': 'ok',
        'card_id': card_id,
        'history': history,
        'total_reprints': len(history),
    })
