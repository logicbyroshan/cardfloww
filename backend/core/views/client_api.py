"""
Client API Views
Contains: All client-related API endpoints (CRUD, toggle status, get staff)
"""
import json
import logging
import os
from datetime import timedelta
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import OperationalError, ProgrammingError
from organisation.models import Organisation
from assistants.services import AssistantService
from ..services import ClientService
from ..services.activity_service import ActivityService
from ..services.cache_version_service import CacheVersionService
from ..services.notification_service import NotificationService
from ..services.permission_service import (
    PermissionService,
    api_require_any_admin,
    api_require_super_admin,
)
from ..models import ClientMessage, Notification, User
from accounts.rate_limit import rate_limit
from mediafiles.utils import normalize_uploaded_image

logger = logging.getLogger(__name__)


CLIENT_STAFF_ALLOWED_PERMISSION_FIELDS = list(AssistantService.ASSISTANT_PERMISSION_FIELDS)


TEMP_MESSAGE_DURATIONS = {
    '6h': timedelta(hours=6),
    '12h': timedelta(hours=12),
    '24h': timedelta(hours=24),
    '2d': timedelta(days=2),
    '3d': timedelta(days=3),
    '7d': timedelta(days=7),
}


MAX_IMAGE_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_UPLOAD_MIMES = {
    'image/jpeg', 'image/png', 'image/webp',
    'image/heic', 'image/heif', 'image/heic-sequence', 'image/heif-sequence',
    'application/octet-stream', 'image/octet-stream',
}
ALLOWED_IMAGE_UPLOAD_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.hei'}


def _validate_optional_image_upload(uploaded):
    """Validate optional client/staff photo uploads without changing response schema."""
    if not uploaded:
        return None, None

    normalized_upload, error_message = normalize_uploaded_image(
        uploaded,
        max_bytes=MAX_IMAGE_UPLOAD_BYTES,
        allowed_extensions=ALLOWED_IMAGE_UPLOAD_EXTS,
        allowed_mime_types=ALLOWED_IMAGE_UPLOAD_MIMES,
    )
    if error_message:
        return None, JsonResponse({'success': False, 'message': error_message}, status=400)
    return normalized_upload, None


def _check_admin_staff_client_access(user, client_id):
    """Check if user has access to a specific client.

    Admin staff access is always scoped to assigned clients.
    """
    return PermissionService.can_access_client(user, client_id)


def _has_manage_client_page_permission(user):
    """Return True when user can use full Manage Clients operations."""
    return PermissionService.is_super_admin(user) or PermissionService.has(user, 'perm_idcard_client_list')


def _has_manage_client_staff_page_permission(user):
    """(Deprecated) Admin Manage Assistant permission checker removed.
    Admin-side Manage Assistant functionality has been removed — client-side assistant
    features remain unaffected.
    """
    return False


def _manage_client_permission_denied_response():
    """Standard deny payload for missing Manage Client permission."""
    return JsonResponse({'success': False, 'message': 'Manage Client permission required'}, status=403)



def _parse_client_id(raw_client_id):
    try:
        client_id = int(raw_client_id)
    except (TypeError, ValueError):
        return None
    return client_id if client_id > 0 else None


def _get_admin_manageable_client_staff(user, staff_id):
    staff_obj = (
        Staff.objects
        .filter(id=staff_id, staff_type='assistant')
        .select_related('user', 'client')
        .first()
    )
    if not staff_obj:
        return None, JsonResponse({'success': False, 'message': 'Staff not found'}, status=404)
    if not _check_admin_staff_client_access(user, staff_obj.client_id):
        return None, JsonResponse({'success': False, 'message': 'Access denied. You are not assigned to this client.'}, status=403)
    return staff_obj, None


def _serialize_client_message(item):
    sent_by_user = item.sent_by
    if sent_by_user:
        sender_name = sent_by_user.get_full_name() or sent_by_user.username
    else:
        sender_name = 'System'

    return {
        'id': item.id,
        'message': item.message,
        'scope': item.scope,
        'scope_display': item.get_scope_display(),
        'visibility': item.visibility,
        'visibility_display': item.get_visibility_display(),
        'expires_at': item.expires_at.isoformat() if item.expires_at else None,
        'expires_at_display': timezone.localtime(item.expires_at).strftime('%d-%m-%Y %H:%M') if item.expires_at else None,
        'is_expired': item.is_expired,
        'notification_active': bool(getattr(item, 'notification', None) and item.notification.is_active),
        'recipient_count': item.recipient_count,
        'sent_by_name': sender_name,
        'created_at': item.created_at.isoformat(),
        'created_at_display': timezone.localtime(item.created_at).strftime('%d-%m-%Y %H:%M'),
    }


def _parse_message_visibility(payload):
    visibility = (payload.get('visibility') or 'permanent').strip().lower()
    if visibility not in ('permanent', 'temporary'):
        return None, None, 'Invalid message type'

    if visibility == 'permanent':
        return visibility, None, None

    duration_code = (payload.get('temporary_duration') or '').strip().lower()
    duration = TEMP_MESSAGE_DURATIONS.get(duration_code)
    if not duration:
        return None, None, 'Please select a valid temporary duration'

    return visibility, timezone.now() + duration, None


def _resolve_client_message_recipients(client_obj, scope):
    recipient_users = []
    if client_obj.user_id and client_obj.user.is_active:
        recipient_users.append(client_obj.user)

    if scope == 'client_and_staff':
        staff_users = list(
            User.objects.filter(
                assistant_profile__client_id=client_obj.id,
                is_active=True,
            ).only('id')
        )
        recipient_users.extend(staff_users)

    return sorted({u.id for u in recipient_users if u and u.id})


def _is_missing_client_message_table_error(exc):
    error_text = str(exc or '').lower()
    return (
        'core_clientmessage' in error_text
        and ('no such table' in error_text or 'does not exist' in error_text or 'undefined table' in error_text)
    )


def _client_message_table_unavailable_response():
    return JsonResponse(
        {
            'success': False,
            'message': 'Client message storage is not initialized yet. Please run migrations.',
        },
        status=503,
    )


@require_http_methods(["POST"])
@api_require_any_admin
@rate_limit(max_requests=10, window_seconds=60, key_prefix='client_create')
def api_client_create(request):
    """API endpoint to create a new client"""
    if not _has_manage_client_page_permission(request.user):
        return _manage_client_permission_denied_response()
    try:
        data = json.loads(request.body)
        result = ClientService.create(data, request=request)

        if result.success and PermissionService.is_operator(request.user):
            try:
                created_client_id = ((result.data or {}).get('client') or {}).get('id')
                if created_client_id:
                    from organisation.models import Organisation
                    created_client = Organisation.objects.filter(id=created_client_id).first()
                    staff = getattr(request.user, 'operator_profile', None)
                    if created_client and staff:
                        staff.assigned_organisations.add(created_client)
            except Exception:
                logger.warning('Could not auto-assign newly created client to admin_staff user=%s', request.user.pk)
        
        if result.success:
            client_name = data.get('name', data.get('school_name', 'client'))
            client_id_val = result.data.get('client_id') or result.data.get('id')
            ActivityService.log_client_create(request, type('Obj', (), {'name': client_name, 'pk': client_id_val})())
        
        response_data = result.to_response_dict()
        # Add email_sent at top level for JS compatibility
        if result.success and 'email_sent' in result.data:
            response_data['email_sent'] = result.data['email_sent']
        
        return JsonResponse(response_data, status=200 if result.success else 400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.exception("Client API error (create): %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)


@require_http_methods(["GET"])
@api_require_any_admin
@rate_limit(max_requests=60, window_seconds=60, key_prefix='client_get')
def api_client_get(request, client_id):
    """API endpoint to get a client's details"""
    if not _check_admin_staff_client_access(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied. You are not assigned to this client.'}, status=403)
    result = ClientService.get(client_id, include_permissions=True)
    return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)


@require_http_methods(["PUT", "POST"])
@api_require_any_admin
def api_client_update(request, client_id):
    """API endpoint to update a client"""
    if not _has_manage_client_page_permission(request.user):
        return _manage_client_permission_denied_response()
    if not _check_admin_staff_client_access(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied. You are not assigned to this client.'}, status=403)
    try:
        data = json.loads(request.body)
        result = ClientService.update(client_id, data)
        if result.success:
            client_name = data.get('name', data.get('school_name', ''))
            if client_name:
                ActivityService.log_client_update(request, type('Obj', (), {'name': client_name, 'pk': client_id})())
        return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.exception("Client API error (update): %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)


@require_http_methods(["DELETE", "POST"])
@api_require_any_admin
@rate_limit(max_requests=5, window_seconds=60, key_prefix='client_delete')
def api_client_delete(request, client_id):
    """API endpoint to delete a client."""
    if not _has_manage_client_page_permission(request.user):
        return _manage_client_permission_denied_response()
    
    if PermissionService.is_operator(request.user):
        return JsonResponse({'success': False, 'message': 'Only super admin can delete clients'}, status=403)
        
    if not _check_admin_staff_client_access(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied. You are not assigned to this client.'}, status=403)
        
    # Get client object with card count annotation
    from django.db.models import Count
    from organisation.models import Organisation
    
    try:
        client_obj = Organisation.objects.annotate(
            card_count=Count('tables__id_cards', distinct=True)
        ).get(pk=client_id)
        
        client_name = client_obj.name
        
        # Enforce no-cards rule
        if client_obj.card_count > 0:
            return JsonResponse({
                'success': False, 
                'message': f'Cannot delete client "{client_name}" because it has {client_obj.card_count} active ID cards. Please delete all cards belonging to this client first.'
            }, status=400)
            
    except Client.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Client not found'}, status=404)
        
    try:
        last_active_str = ActivityService._format_last_active(client_obj.user)
    except Exception:
        last_active_str = 'never active'

    result = ClientService.delete(client_id)
    if result.success:
        ActivityService.log_client_delete(request, client_name, last_active_str, client_id)
    return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)



@require_http_methods(["POST"])
@api_require_any_admin
def api_client_toggle_status(request, client_id):
    """API endpoint to toggle client active/inactive status"""
    if not _has_manage_client_page_permission(request.user):
        return _manage_client_permission_denied_response()
    if not _check_admin_staff_client_access(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied. You are not assigned to this client.'}, status=403)

    try:
        client_obj = Organisation.objects.select_related('user').get(pk=client_id)
    except Client.DoesNotExist:
        client_obj = None

    result = ClientService.toggle_status(client_id)
    if result.success:
        new_status = result.data.get('new_status', result.data.get('status', ''))
        ActivityService.log_client_status(
            request,
            client_obj,
            new_status,
        )
    return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)


@require_http_methods(["GET"])
@api_require_any_admin
@rate_limit(max_requests=60, window_seconds=60, key_prefix='client_staff_get')
def api_client_staff(request, client_id):
    """API endpoint to get all staff members for a specific client"""
    if not _has_manage_client_page_permission(request.user):
        return _manage_client_permission_denied_response()
    if not _check_admin_staff_client_access(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied. You are not assigned to this client.'}, status=403)
    result = ClientService.get_staff(client_id)
    return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)


@require_http_methods(["POST"])
@api_require_any_admin
def api_client_staff_toggle_status(request, client_id, staff_id):
    """
    API endpoint to toggle client staff active/inactive status.
    Validates that the staff belongs to the specified client.
    """
    if not _has_manage_client_page_permission(request.user):
        return _manage_client_permission_denied_response()
    if not _check_admin_staff_client_access(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied. You are not assigned to this client.'}, status=403)
    result = ClientService.toggle_client_staff_status(client_id, staff_id)
    return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)


@require_http_methods(["PUT", "POST"])
@api_require_super_admin
@rate_limit(max_requests=10, window_seconds=60, key_prefix='staff_perm')
def api_client_staff_permissions(request, client_id, staff_id):
    """
    API endpoint for Super Admin to update client staff permissions.
    Super Admin can override any permission as long as it doesn't exceed client's permissions.
    """
    try:
        data = json.loads(request.body)
        result = ClientService.update_client_staff_permissions(client_id, staff_id, data)
        return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)


@require_http_methods(["POST"])
@api_require_any_admin
@rate_limit(max_requests=5, window_seconds=60, key_prefix='client_temp_pw')
def api_client_set_temp_password(request, client_id):
    """API endpoint to set a temporary password for a client."""
    if not _has_manage_client_page_permission(request.user):
        return _manage_client_permission_denied_response()
    if not _check_admin_staff_client_access(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied. You are not assigned to this client.'}, status=403)
    try:
        data = json.loads(request.body)
        new_password = data.get('password', '').strip()
        if not new_password:
            return JsonResponse({'success': False, 'message': 'Password is required'}, status=400)
        if len(new_password) < 8:
            return JsonResponse({'success': False, 'message': 'Password must be at least 8 characters'}, status=400)

        # Validate against Django password validators
        from django.contrib.auth.password_validation import validate_password
        try:
            validate_password(new_password)
        except Exception as validation_error:
            return JsonResponse({'success': False, 'message': '; '.join(validation_error.messages)}, status=400)

        result = ClientService.set_temp_password(client_id, new_password, request=request)
        return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.exception("Client temp password error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)


@require_http_methods(["GET"])
@api_require_any_admin
@rate_limit(max_requests=60, window_seconds=60, key_prefix='admin_client_staff_clients')
def api_admin_client_staff_clients(request):
    # Admin client-staff listing removed: admin Manage Assistant feature deprecated.
    return JsonResponse({'success': False, 'message': 'Admin Manage Assistant feature removed'}, status=404)


@require_http_methods(["GET"])
@api_require_any_admin
@rate_limit(max_requests=60, window_seconds=60, key_prefix='admin_client_staff_get')
def api_admin_client_staff_get(request, staff_id):
    # Admin endpoint removed
    return JsonResponse({'success': False, 'message': 'Admin Manage Assistant feature removed'}, status=404)


@require_http_methods(["POST"])
@api_require_any_admin
@rate_limit(max_requests=10, window_seconds=60, key_prefix='admin_client_staff_create')
def api_admin_client_staff_create(request):
    return JsonResponse({'success': False, 'message': 'Admin Manage Assistant feature removed'}, status=404)


@require_http_methods(["POST", "PUT"])
@api_require_any_admin
@rate_limit(max_requests=15, window_seconds=60, key_prefix='admin_client_staff_update')
def api_admin_client_staff_update(request, staff_id):
    return JsonResponse({'success': False, 'message': 'Admin Manage Assistant feature removed'}, status=404)


@require_http_methods(["POST", "DELETE"])
@api_require_any_admin
@rate_limit(max_requests=10, window_seconds=60, key_prefix='admin_client_staff_delete')
def api_admin_client_staff_delete(request, staff_id):
    return JsonResponse({'success': False, 'message': 'Admin Manage Assistant feature removed'}, status=404)


@require_http_methods(["POST"])
@api_require_any_admin
@rate_limit(max_requests=20, window_seconds=60, key_prefix='admin_client_staff_toggle')
def api_admin_client_staff_toggle_status(request, staff_id):
    return JsonResponse({'success': False, 'message': 'Admin Manage Assistant feature removed'}, status=404)


@require_http_methods(["POST"])
@api_require_any_admin
@rate_limit(max_requests=5, window_seconds=60, key_prefix='admin_client_staff_temp_pw')
def api_admin_client_staff_set_temp_password(request, staff_id):
    return JsonResponse({'success': False, 'message': 'Admin Manage Assistant feature removed'}, status=404)


@require_http_methods(["GET"])
@api_require_any_admin
def api_admin_client_class_section_options(request, client_id):
    return JsonResponse({'success': False, 'message': 'Admin Manage Assistant feature removed'}, status=404)


@require_http_methods(["GET"])
@api_require_any_admin
def api_admin_client_groups_list(request, client_id):
    return JsonResponse({'success': False, 'message': 'Admin Manage Assistant feature removed'}, status=404)


@require_http_methods(["GET"])
@api_require_any_admin
@rate_limit(max_requests=60, window_seconds=60, key_prefix='client_msg_list')
def api_client_messages(request, client_id):
    """API endpoint to fetch admin-sent message history for a client."""
    if not _has_manage_client_page_permission(request.user):
        return _manage_client_permission_denied_response()
    if not _check_admin_staff_client_access(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied. You are not assigned to this client.'}, status=403)

    from organisation.models import Organisation

    client = Organisation.objects.filter(id=client_id).select_related('user').first()
    if not client:
        return JsonResponse({'success': False, 'message': 'Client not found'}, status=404)

    try:
        rows = (
            ClientMessage.objects
            .filter(client_id=client_id)
            .select_related('sent_by', 'notification')
            .order_by('-created_at')[:80]
        )
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_client_message_table_error(exc):
            logger.warning('ClientMessage table unavailable while listing history: %s', exc)
            return _client_message_table_unavailable_response()
        raise

    return JsonResponse({
        'success': True,
        'client': {
            'id': Organisation.id,
            'name': Organisation.name,
        },
        'messages': [_serialize_client_message(item) for item in rows],
    })


def _bump_client_message_cache_versions(client_id, recipient_user_ids=None):
    """Invalidate client message drawer caches for affected client/users."""
    try:
        client_id = int(client_id)
    except (TypeError, ValueError):
        return

    CacheVersionService.bump('client_messages_drawer_client', f'client:{client_id}')

    for raw_uid in (recipient_user_ids or []):
        try:
            uid = int(raw_uid)
        except (TypeError, ValueError):
            continue
        if uid > 0:
            CacheVersionService.bump('client_messages_drawer_user', f'user:{uid}')


@require_http_methods(["POST"])
@api_require_any_admin
@rate_limit(max_requests=20, window_seconds=60, key_prefix='client_msg_send')
def api_client_message_send(request, client_id):
    """API endpoint to send one-way messages to client/client staff users."""
    if not _has_manage_client_page_permission(request.user):
        return _manage_client_permission_denied_response()
    if not _check_admin_staff_client_access(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied. You are not assigned to this client.'}, status=403)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)

    message_text = (payload.get('message') or '').strip()
    scope = (payload.get('scope') or 'client_only').strip()

    if not message_text:
        return JsonResponse({'success': False, 'message': 'Message is required'}, status=400)
    if len(message_text) > 2000:
        return JsonResponse({'success': False, 'message': 'Message is too long (max 2000 characters)'}, status=400)
    if scope not in ('client_only', 'client_and_staff'):
        return JsonResponse({'success': False, 'message': 'Invalid recipient scope'}, status=400)

    visibility, expires_at, visibility_error = _parse_message_visibility(payload)
    if visibility_error:
        return JsonResponse({'success': False, 'message': visibility_error}, status=400)

    from organisation.models import Organisation

    client = Organisation.objects.filter(id=client_id).select_related('user').first()
    if not client:
        return JsonResponse({'success': False, 'message': 'Client not found'}, status=404)

    try:
        ClientMessage.objects.only('id').first()
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_client_message_table_error(exc):
            logger.warning('ClientMessage table unavailable while sending message: %s', exc)
            return _client_message_table_unavailable_response()
        raise

    recipient_ids = _resolve_client_message_recipients(client, scope)
    if not recipient_ids:
        return JsonResponse({'success': False, 'message': 'No active recipients found for this client'}, status=400)

    sender_name = request.user.get_full_name() or request.user.username
    notif_result = NotificationService.create_notification(
        title=f'Client Message - {client.name}',
        message=message_text,
        priority='normal',
        category='announcement',
        target='selected',
        target_user_ids=recipient_ids,
        created_by=request.user,
        send_email=False,
    )
    if not notif_result.success:
        return JsonResponse(notif_result.to_response_dict(), status=400)

    notif_id = ((notif_result.data or {}).get('notification') or {}).get('id')
    try:
        message_row = ClientMessage.objects.create(
            client=client,
            sent_by=request.user,
            message=message_text,
            scope=scope,
            visibility=visibility,
            expires_at=expires_at,
            notification_id=notif_id,
            recipient_count=len(recipient_ids),
        )
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_client_message_table_error(exc):
            logger.warning('ClientMessage table unavailable while creating message row: %s', exc)
            if notif_id:
                Notification.objects.filter(id=notif_id).update(is_active=False)
            return _client_message_table_unavailable_response()
        raise

    _bump_client_message_cache_versions(client.id, recipient_ids)

    ActivityService.log_client_message_send(
        request,
        client_name=client.name,
        scope=scope,
        recipient_count=len(recipient_ids),
    )

    return JsonResponse({
        'success': True,
        'message': f'Message sent to {len(recipient_ids)} user(s)',
        'client_message': _serialize_client_message(message_row),
        'sender_name': sender_name,
    })


@require_http_methods(["GET"])
@api_require_any_admin
@rate_limit(max_requests=60, window_seconds=60, key_prefix='client_msg_targets')
def api_client_message_targets(request):
    """Return client options for group message targeting."""
    if not _has_manage_client_page_permission(request.user):
        return _manage_client_permission_denied_response()

    from organisation.models import Organisation

    query = (request.GET.get('q') or '').strip()
    try:
        limit = max(20, min(int(request.GET.get('limit', 400)), 1000))
    except (TypeError, ValueError):
        limit = 400

    qs = Organisation.objects.select_related('user').order_by('name')
    if query:
        qs = qs.filter(name__icontains=query)

    rows = list(qs[:limit])
    return JsonResponse({
        'success': True,
        'clients': [
            {
                'id': item.id,
                'name': item.name,
                'status': item.status,
                'is_user_active': bool(item.user and item.user.is_active),
                'logo_url': '',
                'photo_url': '',
                'website_logo_url': '',
                'icon': item.icon,
            }
            for item in rows
        ],
    })


@require_http_methods(["POST"])
@api_require_any_admin
@rate_limit(max_requests=10, window_seconds=60, key_prefix='client_msg_group_send')
def api_client_messages_group_send(request):
    """Send one-way client messages to selected clients or all clients."""
    if not _has_manage_client_page_permission(request.user):
        return _manage_client_permission_denied_response()

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)

    message_text = (payload.get('message') or '').strip()
    scope = (payload.get('scope') or 'client_only').strip()
    target_mode = (payload.get('target_mode') or 'selected').strip()

    if not message_text:
        return JsonResponse({'success': False, 'message': 'Message is required'}, status=400)
    if len(message_text) > 2000:
        return JsonResponse({'success': False, 'message': 'Message is too long (max 2000 characters)'}, status=400)
    if scope not in ('client_only', 'client_and_staff'):
        return JsonResponse({'success': False, 'message': 'Invalid recipient scope'}, status=400)
    if target_mode not in ('selected', 'all'):
        return JsonResponse({'success': False, 'message': 'Invalid target mode'}, status=400)

    visibility, expires_at, visibility_error = _parse_message_visibility(payload)
    if visibility_error:
        return JsonResponse({'success': False, 'message': visibility_error}, status=400)

    selected_ids = []
    raw_client_ids = payload.get('client_ids') or []
    if target_mode == 'selected':
        if not isinstance(raw_client_ids, list):
            return JsonResponse({'success': False, 'message': 'client_ids must be a list'}, status=400)
        for raw_id in raw_client_ids:
            try:
                selected_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        selected_ids = sorted(set(selected_ids))
        if not selected_ids:
            return JsonResponse({'success': False, 'message': 'Select at least one client'}, status=400)

    from organisation.models import Organisation

    clients_qs = Organisation.objects.select_related('user').order_by('name')
    if target_mode == 'selected':
        clients_qs = clients_qs.filter(id__in=selected_ids)

    clients = list(clients_qs)
    if not clients:
        return JsonResponse({'success': False, 'message': 'No clients found for this request'}, status=400)

    try:
        ClientMessage.objects.only('id').first()
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_client_message_table_error(exc):
            logger.warning('ClientMessage table unavailable while group sending message: %s', exc)
            return _client_message_table_unavailable_response()
        raise

    sent_items = []
    skipped_clients = []
    failed_clients = []
    total_recipients = 0

    for client in clients:
        recipient_ids = _resolve_client_message_recipients(client, scope)
        if not recipient_ids:
            skipped_clients.append({'id': Organisation.id, 'name': Organisation.name})
            continue

        notif_result = NotificationService.create_notification(
            title=f'Client Message - {client.name}',
            message=message_text,
            priority='normal',
            category='announcement',
            target='selected',
            target_user_ids=recipient_ids,
            created_by=request.user,
            send_email=False,
        )
        if not notif_result.success:
            failed_clients.append({'id': Organisation.id, 'name': Organisation.name})
            continue

        notif_id = ((notif_result.data or {}).get('notification') or {}).get('id')
        try:
            row = ClientMessage.objects.create(
                client=client,
                sent_by=request.user,
                message=message_text,
                scope=scope,
                visibility=visibility,
                expires_at=expires_at,
                notification_id=notif_id,
                recipient_count=len(recipient_ids),
            )
        except (OperationalError, ProgrammingError) as exc:
            if _is_missing_client_message_table_error(exc):
                logger.warning('ClientMessage table unavailable while creating group message row: %s', exc)
                if notif_id:
                    Notification.objects.filter(id=notif_id).update(is_active=False)
                return _client_message_table_unavailable_response()
            raise
        _bump_client_message_cache_versions(client.id, recipient_ids)
        sent_items.append({'id': row.id, 'client_id': Organisation.id, 'client_name': Organisation.name})
        total_recipients += len(recipient_ids)

    if not sent_items:
        return JsonResponse({
            'success': False,
            'message': 'No messages were sent. Check selected clients and recipients.',
            'skipped_clients': skipped_clients,
            'failed_clients': failed_clients,
        }, status=400)

    ActivityService.log_client_message_send(
        request,
        client_name='',
        scope=scope,
        recipient_count=total_recipients,
        is_group=True,
        group_client_count=len(sent_items),
    )

    return JsonResponse({
        'success': True,
        'message': f'Message sent to {len(sent_items)} Organisation(s)',
        'sent_count': len(sent_items),
        'recipient_count': total_recipients,
        'skipped_count': len(skipped_clients),
        'failed_count': len(failed_clients),
    })


@require_http_methods(["POST"])
@api_require_any_admin
@rate_limit(max_requests=20, window_seconds=60, key_prefix='client_msg_delete')
def api_client_message_delete(request, client_id, message_id):
    """Hide a sent message from client-side surfaces while preserving sender history."""
    if not _has_manage_client_page_permission(request.user):
        return _manage_client_permission_denied_response()
    if not _check_admin_staff_client_access(request.user, client_id):
        return JsonResponse({'success': False, 'message': 'Access denied. You are not assigned to this client.'}, status=403)

    try:
        row = (
            ClientMessage.objects
            .filter(id=message_id, client_id=client_id)
            .select_related('notification', 'client')
            .first()
        )
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_client_message_table_error(exc):
            logger.warning('ClientMessage table unavailable while deleting message: %s', exc)
            return _client_message_table_unavailable_response()
        raise
    if not row:
        return JsonResponse({'success': False, 'message': 'Message not found'}, status=404)

    recipient_user_ids = []
    if row.notification_id and row.notification is not None:
        recipient_user_ids = list(row.notification.target_users.values_list('id', flat=True))

    if row.notification_id:
        Notification.objects.filter(id=row.notification_id).update(is_active=False)

    _bump_client_message_cache_versions(client_id, recipient_user_ids)

    ActivityService.log(
        'notification_update',
        f'Client message manually removed from recipients for {row.client.name}',
        request=request,
        target_model='ClientMessage',
        target_id=row.id,
        target_name=row.client.name,
    )

    return JsonResponse({'success': True, 'message': 'Message removed from client inbox'})