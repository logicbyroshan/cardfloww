import json
import logging
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from organisation.models import Organisation
from tables.models import Table
from .services import OperationEngine

logger = logging.getLogger(__name__)


def _parse_body(request):
    """Safely parse JSON request body."""
    if not getattr(request, 'body', None):
        return {}
    try:
        raw = request.body.decode('utf-8') if isinstance(request.body, bytes) else str(request.body)
        return json.loads(raw or '{}')
    except Exception:
        return {}


def _get_user_org(request):
    """Resolve current organisation for request."""
    user = request.user
    if not user or not user.is_authenticated:
        return None
    # Check organisation profile
    if hasattr(user, 'organisation_profile') and user.organisation_profile:
        return user.organisation_profile
    # Check client/org on user
    org = getattr(user, 'organisation', None) or getattr(user, 'client', None)
    if org:
        return org
    # Fallback to first active organisation if superuser
    if user.is_superuser:
        return Organisation.objects.filter(status='active').first()
    return None


@method_decorator(csrf_exempt, name='dispatch')
class UndoView(View):
    """
    POST /api/operations/undo/
    Body: { operation_id?: int, table_id?: int }
    """
    def post(self, request):
        user = request.user if request.user.is_authenticated else None
        org = _get_user_org(request)
        data = _parse_body(request)

        operation_id = data.get('operation_id')
        table_id = data.get('table_id')
        session_id = data.get('session_id') or request.session.session_key or ''

        # If table_id is provided, resolve organisation from table
        if table_id and not org:
            table = Table.objects.filter(id=table_id).first()
            if table:
                org = table.organisation

        if not org:
            return JsonResponse({'success': False, 'message': 'Organisation context required.'}, status=400)

        result = OperationEngine.undo_operation(
            operation_id=operation_id,
            organisation=org,
            user=user,
            table_id=table_id,
            session_id=session_id,
        )

        response_data = result.to_dict()
        response_data['stack_status'] = OperationEngine.get_stack_status(
            organisation=org, user=user, table_id=table_id, session_id=session_id
        )

        status_code = 200 if result.success else 400
        return JsonResponse(response_data, status=status_code)


@method_decorator(csrf_exempt, name='dispatch')
class RedoView(View):
    """
    POST /api/operations/redo/
    Body: { operation_id?: int, table_id?: int }
    """
    def post(self, request):
        user = request.user if request.user.is_authenticated else None
        org = _get_user_org(request)
        data = _parse_body(request)

        operation_id = data.get('operation_id')
        table_id = data.get('table_id')
        session_id = data.get('session_id') or request.session.session_key or ''

        if table_id and not org:
            table = Table.objects.filter(id=table_id).first()
            if table:
                org = table.organisation

        if not org:
            return JsonResponse({'success': False, 'message': 'Organisation context required.'}, status=400)

        result = OperationEngine.redo_operation(
            operation_id=operation_id,
            organisation=org,
            user=user,
            table_id=table_id,
            session_id=session_id,
        )

        response_data = result.to_dict()
        response_data['stack_status'] = OperationEngine.get_stack_status(
            organisation=org, user=user, table_id=table_id, session_id=session_id
        )

        status_code = 200 if result.success else 400
        return JsonResponse(response_data, status=status_code)


class StackStatusView(View):
    """
    GET /api/operations/stack/?table_id=123
    """
    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        org = _get_user_org(request)
        table_id = request.GET.get('table_id')
        session_id = request.GET.get('session_id') or request.session.session_key or ''

        if table_id:
            try:
                table_id = int(table_id)
                if not org:
                    table = Table.objects.filter(id=table_id).first()
                    if table:
                        org = table.organisation
            except (ValueError, TypeError):
                table_id = None

        stack_status = OperationEngine.get_stack_status(
            organisation=org, user=user, table_id=table_id, session_id=session_id
        )

        return JsonResponse({'success': True, **stack_status})


class OperationHistoryView(View):
    """
    GET /api/operations/history/?table_id=123&limit=50&offset=0
    """
    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        org = _get_user_org(request)
        table_id = request.GET.get('table_id')
        limit = min(int(request.GET.get('limit', 50)), 100)
        offset = int(request.GET.get('offset', 0))

        if table_id:
            try:
                table_id = int(table_id)
                if not org:
                    table = Table.objects.filter(id=table_id).first()
                    if table:
                        org = table.organisation
            except (ValueError, TypeError):
                table_id = None

        history = OperationEngine.get_history(
            organisation=org, user=user, table_id=table_id, limit=limit, offset=offset
        )

        return JsonResponse({'success': True, **history})
