"""Guest user management API endpoints for Pro User / Super Admin."""

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from client.models import Client
from client.services_client_core import ClientService
from core.models import User
from core.services.permission_service import PermissionService

logger = logging.getLogger(__name__)


def _require_pro_user(request):
    user = getattr(request, 'user', None)
    if not PermissionService.can_manage_pro_features(user):
        return JsonResponse({'success': False, 'message': 'Pro User or Super Admin access required.'}, status=403)
    return None


def _parse_json_body(request):
    if not getattr(request, 'body', b''):
        return {}
    try:
        return json.loads(request.body.decode('utf-8'))
    except (TypeError, ValueError, UnicodeDecodeError):
        return None


def _serialize_guest(client: Client) -> dict:
    payload = ClientService.serialize(client, include_permissions=False)
    payload['role'] = client.user.role
    payload['role_display'] = client.user.get_role_display() if hasattr(client.user, 'get_role_display') else client.user.role
    payload['username'] = client.user.username
    payload['is_active'] = bool(client.user.is_active)
    payload['guest_status'] = 'sandbox' if getattr(client, 'is_guest', False) else 'client'
    return payload


@login_required
@require_http_methods(['GET'])
def api_pro_user_guest_users(request):
    """List all guest sandbox users."""
    guard = _require_pro_user(request)
    if guard is not None:
        return guard

    guests = (
        Client.objects
        .select_related('user')
        .filter(is_guest=True)
        .order_by('-updated_at', '-id')
    )

    return JsonResponse({
        'success': True,
        'guests': [_serialize_guest(client) for client in guests],
        'total': guests.count(),
    })


@login_required
@require_http_methods(['GET'])
def api_pro_user_guest_source_clients(request):
    """List active non-guest clients that can be converted into guest sandboxes."""
    guard = _require_pro_user(request)
    if guard is not None:
        return guard

    current_client_id = getattr(getattr(request.user, 'client_profile', None), 'id', None)

    clients = (
        Client.objects
        .select_related('user')
        .filter(status='active', is_guest=False)
        .order_by('name', 'id')
    )
    if current_client_id:
        clients = clients.exclude(id=current_client_id)

    return JsonResponse({
        'success': True,
        'clients': [
            {
                'id': client.id,
                'name': client.name,
                'username': client.user.username,
                'email': client.user.email,
                'role': client.user.role,
            }
            for client in clients
        ],
    })


@login_required
@require_http_methods(['POST'])
def api_pro_user_guest_user_create(request):
    """Create a new guest sandbox user."""
    guard = _require_pro_user(request)
    if guard is not None:
        return guard

    body = _parse_json_body(request)
    if body is None:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    payload = {
        'name': str(body.get('name') or '').strip(),
        'username': str(body.get('username') or '').strip(),
        'email': str(body.get('email') or '').strip(),
        'phone': str(body.get('phone') or '').strip(),
        'password': str(body.get('password') or '').strip(),
        'address': str(body.get('address') or '').strip(),
        'city': str(body.get('city') or '').strip(),
        'state': str(body.get('state') or '').strip(),
        'pincode': str(body.get('pincode') or '').strip(),
        'status': 'active',
        'role': 'guest_prime_manager',
        'is_active': True,
    }

    if not payload['name']:
        return JsonResponse({'success': False, 'message': 'Guest name is required.'}, status=400)
    if not payload['username']:
        return JsonResponse({'success': False, 'message': 'Guest username is required.'}, status=400)
    if not payload['password']:
        return JsonResponse({'success': False, 'message': 'Guest password is required.'}, status=400)

    result = ClientService.create(payload, request=request)
    return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)


@login_required
@require_http_methods(['POST'])
def api_pro_user_guest_user_convert(request):
    """Convert an existing client into a guest sandbox account."""
    guard = _require_pro_user(request)
    if guard is not None:
        return guard

    body = _parse_json_body(request)
    if body is None:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    client_id = body.get('client_id')
    try:
        client_id = int(str(client_id).strip())
    except (TypeError, ValueError):
        client_id = 0

    if client_id <= 0:
        return JsonResponse({'success': False, 'message': 'A valid client_id is required.'}, status=400)

    client = get_object_or_404(Client.objects.select_related('user'), id=client_id)
    if getattr(client, 'is_guest', False) or getattr(client.user, 'role', '') == 'guest_prime_manager':
        return JsonResponse({'success': False, 'message': 'This user is already a guest.'}, status=400)

    try:
        result = ClientService.create_guest_from_client(client_id, request=request)
    except Exception as exc:
        logger.exception('Guest convert failed for client_id=%s: %s', client_id, exc)
        return JsonResponse({'success': False, 'message': 'Failed to convert client to guest user.'}, status=500)

    return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)


@login_required
@require_http_methods(['POST'])
def api_pro_user_guest_user_restore(request):
    """Restore a guest sandbox account back to a normal client."""
    guard = _require_pro_user(request)
    if guard is not None:
        return guard

    body = _parse_json_body(request)
    if body is None:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    client_id = body.get('client_id')
    try:
        client_id = int(str(client_id).strip())
    except (TypeError, ValueError):
        client_id = 0

    if client_id <= 0:
        return JsonResponse({'success': False, 'message': 'A valid client_id is required.'}, status=400)

    client = get_object_or_404(Client.objects.select_related('user'), id=client_id)
    if not getattr(client, 'is_guest', False) and getattr(client.user, 'role', '') != 'guest_prime_manager':
        return JsonResponse({'success': False, 'message': 'This user is not a guest.'}, status=400)

    try:
        result = ClientService.restore_client_from_guest(client_id, request=request)
    except Exception as exc:
        logger.exception('Guest restore failed for client_id=%s: %s', client_id, exc)
        return JsonResponse({'success': False, 'message': 'Failed to restore guest to client.'}, status=500)

    return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)