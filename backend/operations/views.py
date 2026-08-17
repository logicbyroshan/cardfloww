"""
CardFlow — Reversible Operations, Bulk Transactions & Audit History API Views

Endpoints:
  - POST /api/operations/undo/
  - POST /api/operations/redo/
  - GET  /api/operations/stack/
  - GET  /api/operations/history/
  - GET  /api/operations/audit/cards/<card_id>/timeline/
  - GET  /api/operations/audit/tables/<table_id>/activity/
  - GET  /api/operations/audit/transactions/
  - GET  /api/operations/audit/transactions/<transaction_id>/
  - POST /api/operations/audit/transactions/<transaction_id>/reverse/
  - GET  /api/operations/audit/export/
"""
import csv
import json
import logging
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator

from organisation.models import Organisation
from tables.models import Table, IDCard
from .services import OperationEngine, AuditService, AuditVisibilityService

logger = logging.getLogger(__name__)


def _get_request_org(request, table_id=None):
    """Resolve organisation from request user or table_id with fallback."""
    user = getattr(request, 'user', None)
    if user and getattr(user, 'is_authenticated', False):
        org = (
            getattr(user, 'organisation_profile', None)
            or getattr(user, 'organisation', None)
            or getattr(user, 'client', None)
        )
        if org:
            return org

    if table_id:
        try:
            t = Table.objects.select_related('organisation').get(id=table_id)
            if t.organisation:
                return t.organisation
        except Table.DoesNotExist:
            pass

    # Global fallback for single-tenant local or super-admin setups
    return Organisation.objects.first()


# ══════════════════════════════════════════════════════════════════════════
# 1. UNDO / REDO REST ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

@csrf_exempt
@require_http_methods(['POST'])
def undo_view(request):
    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        data = {}

    table_id = data.get('table_id') or request.GET.get('table_id')
    operation_id = data.get('operation_id')
    session_id = data.get('session_id', '')
    org = _get_request_org(request, table_id)

    res = OperationEngine.undo_operation(
        operation_id=int(operation_id) if operation_id else None,
        organisation=org,
        user=request.user if request.user.is_authenticated else None,
        table_id=int(table_id) if table_id else None,
        session_id=session_id,
        admin_override=getattr(request.user, 'is_superuser', False),
    )

    stack = OperationEngine.get_stack_status(
        organisation=org,
        user=request.user if request.user.is_authenticated else None,
        table_id=int(table_id) if table_id else None,
        session_id=session_id,
    )

    return JsonResponse({
        **res.to_dict(),
        'stack_status': stack,
    }, status=200 if res.success else 400)


@csrf_exempt
@require_http_methods(['POST'])
def redo_view(request):
    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        data = {}

    table_id = data.get('table_id') or request.GET.get('table_id')
    operation_id = data.get('operation_id')
    session_id = data.get('session_id', '')
    org = _get_request_org(request, table_id)

    res = OperationEngine.redo_operation(
        operation_id=int(operation_id) if operation_id else None,
        organisation=org,
        user=request.user if request.user.is_authenticated else None,
        table_id=int(table_id) if table_id else None,
        session_id=session_id,
    )

    stack = OperationEngine.get_stack_status(
        organisation=org,
        user=request.user if request.user.is_authenticated else None,
        table_id=int(table_id) if table_id else None,
        session_id=session_id,
    )

    return JsonResponse({
        **res.to_dict(),
        'stack_status': stack,
    }, status=200 if res.success else 400)


@require_http_methods(['GET'])
def stack_status_view(request):
    table_id = request.GET.get('table_id')
    session_id = request.GET.get('session_id', '')
    org = _get_request_org(request, table_id)

    stack = OperationEngine.get_stack_status(
        organisation=org,
        user=request.user if request.user.is_authenticated else None,
        table_id=int(table_id) if table_id else None,
        session_id=session_id,
    )
    return JsonResponse({'success': True, **stack})


@require_http_methods(['GET'])
def history_view(request):
    table_id = request.GET.get('table_id')
    limit = min(int(request.GET.get('limit', 50)), 200)
    offset = max(int(request.GET.get('offset', 0)), 0)
    org = _get_request_org(request, table_id)

    res = OperationEngine.get_history(
        organisation=org,
        user=request.user if request.user.is_authenticated else None,
        table_id=int(table_id) if table_id else None,
        limit=limit,
        offset=offset,
    )
    return JsonResponse({'success': True, **res})


# ══════════════════════════════════════════════════════════════════════════
# 2. AUDIT HISTORY & CARD TIMELINE REST ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

@require_http_methods(['GET'])
def card_timeline_view(request, card_id):
    """Return chronological audit timeline for a specific card."""
    limit = min(int(request.GET.get('limit', 50)), 200)
    offset = max(int(request.GET.get('offset', 0)), 0)

    res = AuditService.get_card_timeline(
        card_id=int(card_id),
        user=request.user if request.user.is_authenticated else None,
        limit=limit,
        offset=offset,
    )
    return JsonResponse(res, status=200 if res.get('success') else 404)


@require_http_methods(['GET'])
def table_activity_view(request, table_id):
    """Return high-level activity feed for a table."""
    limit = min(int(request.GET.get('limit', 50)), 200)
    offset = max(int(request.GET.get('offset', 0)), 0)

    res = AuditService.get_table_activity(
        table_id=int(table_id),
        user=request.user if request.user.is_authenticated else None,
        limit=limit,
        offset=offset,
    )
    return JsonResponse(res, status=200 if res.get('success') else 404)


@require_http_methods(['GET'])
def bulk_transactions_list_view(request):
    """Return list of bulk transactions with filters."""
    table_id = request.GET.get('table_id')
    action = request.GET.get('action')
    status = request.GET.get('status')
    limit = min(int(request.GET.get('limit', 50)), 200)
    offset = max(int(request.GET.get('offset', 0)), 0)
    org = _get_request_org(request, table_id)

    res = AuditService.get_bulk_transactions(
        table_id=int(table_id) if table_id else None,
        organisation=org,
        user=request.user if request.user.is_authenticated else None,
        action=action,
        status=status,
        limit=limit,
        offset=offset,
    )
    return JsonResponse(res)


@require_http_methods(['GET'])
def bulk_transaction_detail_view(request, transaction_id):
    """Return detailed metadata and affected card list for a bulk transaction."""
    search = request.GET.get('search', '').strip()
    limit = min(int(request.GET.get('limit', 100)), 500)
    offset = max(int(request.GET.get('offset', 0)), 0)

    res = AuditService.get_transaction_detail(
        transaction_id=int(transaction_id),
        user=request.user if request.user.is_authenticated else None,
        search=search,
        limit=limit,
        offset=offset,
    )
    return JsonResponse(res, status=200 if res.get('success') else 404)


@csrf_exempt
@require_http_methods(['POST'])
def reverse_bulk_transaction_view(request, transaction_id):
    """Safely reverse a historical bulk transaction with conflict checking."""
    res = AuditService.reverse_bulk_transaction(
        transaction_id=int(transaction_id),
        user=request.user if request.user.is_authenticated else None,
    )
    return JsonResponse(res, status=200 if res.get('success') else 400)


@require_http_methods(['GET'])
def export_audit_view(request):
    """Export authorized audit history to CSV."""
    table_id = request.GET.get('table_id')
    org = _get_request_org(request, table_id)
    user = request.user if request.user.is_authenticated else None

    from .models import AuditEvent
    base_qs = AuditEvent.objects.all().select_related('target_table', 'actor', 'bulk_transaction')
    visible_qs = AuditVisibilityService.filter_events(
        base_qs, user, organisation=org, table_id=int(table_id) if table_id else None
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="audit_export_{table_id or "all"}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Event ID', 'Event Type', 'Target Type', 'Target ID', 'Target Name', 'Actor', 'Role', 'Date & Time', 'Bulk Transaction Code'])

    for ev in visible_qs.order_by('-created_at')[:2000]:
        writer.writerow([
            ev.event_id,
            ev.event_type,
            ev.target_type,
            ev.target_id,
            ev.target_name_snapshot,
            ev.actor_name_snapshot or (ev.actor.username if ev.actor else 'System'),
            ev.actor_role_snapshot,
            ev.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            ev.bulk_transaction.tx_code if ev.bulk_transaction else '',
        ])

    # Record an audit event for the export action itself (Invariant 51 & 73)
    if org:
        try:
            AuditService.record_event(
                organisation=org,
                actor=user,
                event_type='export_data',
                target_type='table' if table_id else 'organisation',
                target_id=int(table_id) if table_id else org.id,
                target_name=f"Audit Export ({visible_qs.count()} events)",
                visibility_scope='INTERNAL_ADMIN',
            )
        except Exception:
            pass

    return response
