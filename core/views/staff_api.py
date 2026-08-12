"""
Staff API Views (Adapter for Operator/Assistant separation)
Contains: All staff-related API endpoints (CRUD, toggle status, active clients list)
"""
import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from ..services.permission_service import api_require_super_admin
from operators.services import OperatorCreationService
from ..services.activity_service import ActivityService
from organisation.models import Organisation
from operators.models import Operator
from accounts.rate_limit import rate_limit
from mediafiles.utils import normalize_uploaded_image

logger = logging.getLogger(__name__)

MAX_IMAGE_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_UPLOAD_MIMES = {
    'image/jpeg', 'image/png', 'image/webp',
    'image/heic', 'image/heif', 'image/heic-sequence', 'image/heif-sequence',
}
ALLOWED_IMAGE_UPLOAD_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.hei'}


class DictServiceResult:
    def __init__(self, d):
        self.success = d.get('success', False)
        self.message = d.get('message') or d.get('error', '')
        # Map operator key to staff key for compatibility
        if 'operator' in d:
            d['staff'] = d['operator']
        self.data = d
        
    def to_response_dict(self):
        return {
            'success': self.success,
            'message': self.message,
            'data': self.data
        }


def _parse_json_object(request):
    """Parse request JSON and require an object payload."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None, JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)

    if not isinstance(data, dict):
        return None, JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)

    return data, None


def _validate_optional_image_upload(uploaded):
    """Validate optional profile image upload."""
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


def _admin_staff_assignment_snapshot(staff_obj):
    if not staff_obj:
        return {
            'client_ids': [],
            'group_ids': [],
            'table_ids': [],
            'classes': [],
            'sections': [],
            'branches': [],
            'scope_count': 0,
        }
    return {
        'client_ids': list(staff_obj.assigned_organisations.values_list('id', flat=True)),
        'group_ids': [],
        'table_ids': [],
        'classes': [],
        'sections': [],
        'branches': [],
        'scope_count': 0,
    }


def _map_perm_fields_to_codenames(data):
    codenames = set()
    mapping = {
        'perm_idcard_client_list': ['can_view_clients'],
        'perm_manage_assistant': ['can_view_clients'],
        'perm_idcard_setting_list': ['can_view_idcard_settings'],
        'perm_idcard_setting_add': ['can_add_idcard_settings'],
        'perm_idcard_setting_edit': ['can_edit_idcard_settings'],
        'perm_idcard_setting_delete': ['can_delete_idcard_settings'],
        'perm_idcard_setting_status': ['can_edit_idcard_settings'],
        'perm_idcard_pending_list': ['can_view_idcard_data'],
        'perm_idcard_verified_list': ['can_view_idcard_data'],
        'perm_idcard_pool_list': ['can_view_idcard_data'],
        'perm_idcard_approved_list': ['can_view_approved_list'],
        'perm_idcard_download_list': ['can_view_download_list'],
        'perm_idcard_reprint_list': ['can_view_idcard_data'],
        'perm_reprint_request_list': ['can_view_idcard_data'],
        'perm_confirmed_list': ['can_view_approved_list'],
        'perm_idcard_add': ['can_add_idcard_data'],
        'perm_idcard_edit': ['can_edit_idcard_data'],
        'perm_idcard_delete': ['can_delete_idcard_data'],
        'perm_idcard_info': ['can_view_idcard_data'],
        'perm_idcard_approve': ['can_approve_idcard'],
        'perm_idcard_verify': ['can_verify_idcard'],
        'perm_idcard_updated_at': ['can_edit_idcard_data'],
        'perm_idcard_delete_from_pool': ['can_delete_idcard_data'],
        'perm_idcard_clear_pending_path': ['can_edit_idcard_data'],
        'perm_reupload_idcard_image': ['can_upload_images', 'can_reupload_images'],
        'perm_idcard_retrieve': ['can_view_idcard_data'],
        'perm_idcard_bulk_upload': ['can_bulk_upload'],
        'perm_idcard_bulk_download': ['can_bulk_download'],
        'perm_idcard_download_image_rename_mode': ['can_bulk_download'],
        'perm_idcard_download_image_generate_mode': ['can_bulk_download'],
        'perm_idcard_bulk_reupload': ['can_bulk_upload'],
        'perm_idcard_upgrade_all': ['can_edit_idcard_data'],
        'perm_mobile_app': ['can_view_idcard_data'],
        'perm_manage_panel_backup': ['can_view_workflow'],
        'perm_manage_panel_email': ['can_view_workflow'],
    }
    for k, v in data.items():
        if k.startswith('perm_') and v:
            is_truthy = False
            if isinstance(v, bool):
                is_truthy = v
            elif isinstance(v, str):
                is_truthy = v.lower() in ('true', '1', 'yes')
            elif isinstance(v, (int, float)):
                is_truthy = bool(v)
            
            if is_truthy and k in mapping:
                for codename in mapping[k]:
                    codenames.add(codename)
                    
    raw_perms = data.get('permissions') or data.get('permission_codenames')
    if isinstance(raw_perms, list):
        for p in raw_perms:
            if isinstance(p, str):
                codenames.add(p)
            elif isinstance(p, dict) and 'codename' in p:
                codenames.add(p['codename'])
                
    return list(codenames)


def serialize_operator_compat(operator: Operator, include_permissions: bool = True) -> dict:
    from core.services.compat_service import CompatibilityService
    user = operator.user
    data = {
        'id': CompatibilityService.encode_id(operator.id, 'operator'),
        'name': user.get_full_name(),
        'email': user.email if not user.email.endswith('@noemail.local') else '',
        'phone': user.phone or '',
        'address': '',
        'department': operator.department or '',
        'designation': operator.designation or '',
        'staff_type': 'operator',
        'status': 'active' if user.is_active else 'inactive',
        'profile_image_url': None,
        'created_at': operator.created_at.strftime('%d-%m-%Y %H:%M') if operator.created_at else '',
        'updated_at': operator.updated_at.strftime('%d-%m-%Y %H:%M') if operator.updated_at else '',
    }
    
    if include_permissions:
        from core.services.permission_service import PermissionService
        for perm in PermissionService.ALL_PERMISSION_KEYS:
            data[perm] = getattr(operator, perm, False)
            
    data['assigned_client_ids'] = list(
        operator.assigned_organisations.values_list('id', flat=True)
    )
    return data


@require_http_methods(["POST"])
@api_require_super_admin
def api_staff_create(request):
    """API endpoint to create an admin staff member (Operator)"""
    try:
        # Check if it's a multipart form (file upload) or JSON
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = dict(request.POST)
            data = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in data.items()}
            profile_image = request.FILES.get('profile_image')
        else:
            data, json_err = _parse_json_object(request)
            if json_err:
                return json_err
            profile_image = None

        profile_image, file_error = _validate_optional_image_upload(profile_image)
        if file_error:
            return file_error

        name = str(data.get('name') or '').strip()
        name_parts = name.split() if name else []
        first_name = name_parts[0] if name_parts else ''
        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

        assigned_clients = data.get('assigned_organisations', [])
        assigned_client_ids = []
        for c in assigned_clients:
            if isinstance(c, dict) and 'id' in c:
                assigned_client_ids.append(int(c['id']))
            elif isinstance(c, (int, str)):
                assigned_client_ids.append(int(c))
                
        permission_codenames = _map_perm_fields_to_codenames(data)

        perm_keys = []
        for k, v in data.items():
            if k.startswith('perm_'):
                is_truthy = False
                if isinstance(v, bool):
                    is_truthy = v
                elif isinstance(v, str):
                    is_truthy = v.lower() in ('true', '1', 'yes')
                elif isinstance(v, (int, float)):
                    is_truthy = bool(v)
                
                if is_truthy:
                    perm_keys.append(k)

        raw_result = OperatorCreationService.create_operator(
            created_by=request.user,
            first_name=first_name,
            last_name=last_name,
            email=data.get('email', ''),
            phone=data.get('phone', ''),
            designation=data.get('designation', 'Operator'),
            department=data.get('department', ''),
            assigned_client_ids=assigned_client_ids,
            permission_codenames=permission_codenames,
            password=data.get('password', ''),
            perm_keys=perm_keys,
        )
        result = DictServiceResult(raw_result)
        
        response_data = result.to_response_dict()
        if result.success and 'email_sent' in result.data:
            response_data['email_sent'] = result.data['email_sent']

        if result.success:
            created_staff_id = ((result.data or {}).get('staff') or {}).get('id')
            if created_staff_id:
                try:
                    created_staff = (
                        Operator.objects
                        .filter(id=created_staff_id)
                        .select_related('user')
                        .prefetch_related('assigned_organisations')
                        .first()
                    )
                    if created_staff:
                        ActivityService.log_staff_create(request, created_staff)
                        ActivityService.log_staff_assignment_change(
                            request,
                            created_staff,
                            before_snapshot={},
                            after_snapshot=_admin_staff_assignment_snapshot(created_staff),
                            reason='created',
                        )
                except Exception:
                    logger.exception('Failed to log admin staff create timeline for staff_id=%s', created_staff_id)
        
        return JsonResponse(response_data, status=200 if result.success else 400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.exception("Staff API error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)


@require_http_methods(["GET"])
@api_require_super_admin
@rate_limit(max_requests=60, window_seconds=60, key_prefix='staff_get')
def api_staff_get(request, staff_id):
    """API endpoint to get a staff's details"""
    try:
        from core.services.compat_service import CompatibilityService
        _, real_id = CompatibilityService.decode_id(staff_id)
        operator = Operator.objects.filter(id=real_id).first()
        if not operator:
            return JsonResponse({'success': False, 'message': 'Staff not found'}, status=404)
        
        operator_data = serialize_operator_compat(operator, include_permissions=True)
        return JsonResponse({
            'success': True,
            'message': '',
            'data': operator_data
        }, status=200)
    except Exception as e:
        logger.exception("Staff API get error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)


@require_http_methods(["PUT", "POST"])
@api_require_super_admin
def api_staff_update(request, staff_id):
    """API endpoint to update a staff"""
    try:
        from core.services.compat_service import CompatibilityService
        _, real_id = CompatibilityService.decode_id(staff_id)
        before_staff = (
            Operator.objects
            .filter(id=real_id)
            .select_related('user')
            .prefetch_related('assigned_organisations')
            .first()
        )
        if not before_staff:
            return JsonResponse({'success': False, 'message': 'Staff not found'}, status=404)
        before_assignment_snapshot = _admin_staff_assignment_snapshot(before_staff)

        # Check if it's a multipart form (file upload) or JSON
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = dict(request.POST)
            data = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in data.items()}
            profile_image = request.FILES.get('profile_image')
        else:
            data, json_err = _parse_json_object(request)
            if json_err:
                return json_err
            profile_image = None

        profile_image, file_error = _validate_optional_image_upload(profile_image)
        if file_error:
            return file_error
        
        name = str(data.get('name') or '').strip()
        name_parts = name.split() if name else []
        first_name = name_parts[0] if name_parts else ''
        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

        assigned_clients = data.get('assigned_organisations', [])
        assigned_client_ids = []
        for c in assigned_clients:
            if isinstance(c, dict) and 'id' in c:
                assigned_client_ids.append(int(c['id']))
            elif isinstance(c, (int, str)):
                assigned_client_ids.append(int(c))
                
        permission_codenames = _map_perm_fields_to_codenames(data)

        # Update active status if changed
        user = before_staff.user
        is_active = data.get('is_active')
        if is_active is not None:
            is_active_bool = is_active if isinstance(is_active, bool) else (str(is_active).lower() in ('true', '1'))
            if user.is_active != is_active_bool:
                user.is_active = is_active_bool
                user.save()

        perm_keys = []
        for k, v in data.items():
            if k.startswith('perm_'):
                is_truthy = False
                if isinstance(v, bool):
                    is_truthy = v
                elif isinstance(v, str):
                    is_truthy = v.lower() in ('true', '1', 'yes')
                elif isinstance(v, (int, float)):
                    is_truthy = bool(v)
                
                if is_truthy:
                    perm_keys.append(k)

        raw_result = OperatorCreationService.update_operator(
            updated_by=request.user,
            operator_id=real_id,
            first_name=first_name,
            last_name=last_name,
            phone=data.get('phone'),
            designation=data.get('designation'),
            department=data.get('department'),
            assigned_client_ids=assigned_client_ids,
            permission_codenames=permission_codenames,
            perm_keys=perm_keys,
        )
        result = DictServiceResult(raw_result)

        if result.success:
            try:
                refreshed = (
                    Operator.objects
                    .filter(id=real_id)
                    .select_related('user')
                    .prefetch_related('assigned_organisations')
                    .first()
                )
                if refreshed:
                    ActivityService.log_staff_update(request, refreshed)
                    ActivityService.log_staff_assignment_change(
                        request,
                        refreshed,
                        before_snapshot=before_assignment_snapshot,
                        after_snapshot=_admin_staff_assignment_snapshot(refreshed),
                        reason='updated',
                    )
            except Exception:
                logger.exception('Failed to log admin staff update timeline for staff_id=%s', staff_id)

        return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.exception("Staff API error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)


@require_http_methods(["DELETE", "POST"])
@api_require_super_admin
@rate_limit(max_requests=5, window_seconds=60, key_prefix='staff_delete')
def api_staff_delete(request, staff_id):
    """API endpoint to delete a staff"""
    try:
        from core.services.compat_service import CompatibilityService
        _, real_id = CompatibilityService.decode_id(staff_id)
        operator = Operator.objects.filter(id=real_id).first()
        if not operator:
            return JsonResponse({'success': False, 'message': 'Staff not found'}, status=404)
        
        name = operator.user.get_full_name() or operator.user.username
        last_active_str = ActivityService._format_last_active(operator.user)
        raw_result = OperatorCreationService.delete_operator(deleted_by=request.user, operator_id=real_id)
        result = DictServiceResult(raw_result)
        
        if result.success:
            ActivityService.log_staff_delete(request, name, last_active_str, real_id, user_type='Operator')
            
        return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)
    except Exception as e:
        logger.exception("Staff API delete error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)


@require_http_methods(["POST"])
@api_require_super_admin
def api_staff_toggle_status(request, staff_id):
    """API endpoint to toggle staff active/inactive status"""
    try:
        from core.services.compat_service import CompatibilityService
        _, real_id = CompatibilityService.decode_id(staff_id)
        operator = Operator.objects.filter(id=real_id).first()
        if not operator:
            return JsonResponse({'success': False, 'message': 'Staff not found'}, status=404)
            
        raw_result = OperatorCreationService.toggle_status(toggled_by=request.user, operator_id=real_id)
        result = DictServiceResult(raw_result)
        
        if result.success:
            try:
                ActivityService.log_staff_status(request, operator, result.data.get('is_active', False))
            except Exception:
                logger.exception("Failed to log status toggle for operator_id=%s", staff_id)
                
        return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)
    except Exception as e:
        logger.exception("Staff API toggle status error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)


@require_http_methods(["GET"])
@api_require_super_admin
def api_active_clients_list(request):
    """API endpoint to get list of active clients for staff assignment dropdown"""
    clients = Organisation.objects.filter(status='active', is_guest=False).order_by('name').values('id', 'name')
    return JsonResponse({
        'success': True,
        'clients': list(clients)
    })


@require_http_methods(["GET"])
@api_require_super_admin
def api_all_clients_for_assignment(request):
    """API endpoint to get ALL clients (active + inactive) for staff assignment dropdown."""
    clients = Organisation.objects.filter(is_guest=False).order_by('status', 'name').values('id', 'name', 'status')
    return JsonResponse({
        'success': True,
        'clients': list(clients)
    })


@require_http_methods(["POST"])
@api_require_super_admin
@rate_limit(max_requests=5, window_seconds=60, key_prefix='staff_temp_pw')
def api_staff_set_temp_password(request, staff_id):
    """API endpoint to set a temporary password for a staff member (Super Admin only)"""
    try:
        from core.services.compat_service import CompatibilityService
        _, real_id = CompatibilityService.decode_id(staff_id)
        operator = Operator.objects.filter(id=real_id).first()
        if not operator:
            return JsonResponse({'success': False, 'message': 'Staff not found'}, status=404)

        data, json_err = _parse_json_object(request)
        if json_err:
            return json_err
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

        raw_result = OperatorCreationService.set_temp_password(profile_id=real_id, new_password=new_password, is_assistant=False, request=request)
        result = DictServiceResult(raw_result)
        return JsonResponse(result.to_response_dict(), status=200 if result.success else 400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.exception("Staff temp password error: %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'}, status=400)