"""
Staff Service — Shim wrapper around AssistantService, OperatorCreationService and PhotographerService.
For backward compatibility with mobile API and old calls.
"""
from typing import Dict, Any, Optional, List
import logging

from django.shortcuts import get_object_or_404
from core.services.base import BaseService, ServiceResult
from assistants.services import AssistantService
from operators.services import OperatorCreationService
from core.services.photographer_service import PhotographerService
from operators.models import Operator
from assistants.models import Assistant
from core.models import Photographer

logger = logging.getLogger(__name__)


class StaffService(BaseService):
    PERMISSION_FIELDS = [
        'perm_idcard_client_list',
        'perm_manage_assistant',
        'perm_idcard_setting_list', 'perm_idcard_setting_add', 
        'perm_idcard_setting_edit', 'perm_idcard_setting_delete', 
        'perm_idcard_setting_status',
        'perm_idcard_pending_list', 'perm_idcard_verified_list',
        'perm_idcard_pool_list', 'perm_idcard_approved_list',
        'perm_idcard_download_list', 'perm_idcard_reprint_list',
        'perm_reprint_request_list', 'perm_confirmed_list',
        'perm_idcard_add', 'perm_idcard_edit', 'perm_idcard_delete',
        'perm_idcard_info', 'perm_idcard_approve', 'perm_idcard_verify',
        'perm_idcard_updated_at',
        'perm_idcard_delete_from_pool',
        'perm_idcard_clear_pending_path',
        'perm_idcard_retrieve',
        'perm_idcard_bulk_upload', 'perm_idcard_bulk_download',
        'perm_idcard_download_image_rename_mode', 'perm_idcard_download_image_generate_mode',
        'perm_idcard_bulk_reupload',
        'perm_idcard_upgrade_all',
        'perm_mobile_app',
        'perm_manage_panel_backup', 'perm_manage_panel_email',
    ]

    @classmethod
    def create(cls, data: Dict[str, Any], staff_type: str = 'operator', client=None, request=None, **kwargs) -> ServiceResult:
        if staff_type == 'photographer':
            return PhotographerService.create(data, request=request)
        elif staff_type == 'assistant':
            return AssistantService.create_assistant(user=request.user if request else None, data=data)
        else:
            name = str(data.get('name') or '').strip()
            name_parts = name.split() if name else []
            first_name = name_parts[0] if name_parts else ''
            last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
            
            # Check phone and password requirements (test requirement)
            phone = str(data.get('phone') or '').strip()
            password = str(data.get('password') or '').strip()
            if not phone and not password:
                return ServiceResult(success=False, message="Phone number is required to generate a temporary password.")

            # Fallback email generation
            email = str(data.get('email') or '').strip()
            if not email:
                import uuid
                email = f"staff_{uuid.uuid4().hex[:8]}@noemail.local"

            assigned_client_ids = data.get('assigned_organisations', [])
            if isinstance(assigned_client_ids, str):
                import json
                try:
                    assigned_client_ids = json.loads(assigned_client_ids)
                except Exception:
                    assigned_client_ids = []
            
            from core.views.staff_api import _map_perm_fields_to_codenames
            permission_codenames = _map_perm_fields_to_codenames(data)

            raw_res = OperatorCreationService.create_operator(
                created_by=request.user if request else None,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                designation=data.get('designation', 'Operator'),
                department=data.get('department', ''),
                assigned_client_ids=assigned_client_ids,
                permission_codenames=permission_codenames,
                password=password,
                is_active=bool(data.get('is_active', False)),
            )
            if raw_res.get('success'):
                op_data = raw_res.get('operator')
                if isinstance(op_data, dict) and 'id' in op_data:
                    op_data['id'] = op_data['id'] + 100000
                return ServiceResult(success=True, data={'staff': op_data, 'email_sent': raw_res.get('email_sent')})
            else:
                return ServiceResult(success=False, message=raw_res.get('error', 'Failed to create operator'))

    @classmethod
    def _decode_staff_id(cls, staff_id: int):
        try:
            val = int(staff_id)
        except (TypeError, ValueError):
            return 'unknown', 0
        if 100000 <= val < 200000:
            return 'operator', val - 100000
        elif 200000 <= val < 300000:
            return 'client_staff', val - 200000
        elif 300000 <= val < 400000:
            return 'photographer', val - 300000
        else:
            if Photographer.objects.filter(id=val).exists():
                return 'photographer', val
            if Assistant.objects.filter(id=val).exists():
                return 'client_staff', val
            if Operator.objects.filter(id=val).exists():
                return 'operator', val
            return 'unknown', val

    @classmethod
    def update(cls, staff_id: int, data: Dict[str, Any]) -> ServiceResult:
        staff_type, real_id = cls._decode_staff_id(staff_id)
        if staff_type == 'photographer':
            return PhotographerService.update(real_id, data)
        elif staff_type == 'operator':
            operator = Operator.objects.filter(id=real_id).first()
            if operator:
                name = str(data.get('name') or '').strip()
                name_parts = name.split() if name else []
                first_name = name_parts[0] if name_parts else ''
                last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                
                assigned_client_ids = data.get('assigned_organisations', [])
                if isinstance(assigned_client_ids, str):
                    import json
                    try:
                        assigned_client_ids = json.loads(assigned_client_ids)
                    except Exception:
                        assigned_client_ids = []

                from core.views.staff_api import _map_perm_fields_to_codenames
                permission_codenames = _map_perm_fields_to_codenames(data)

                raw_res = OperatorCreationService.update_operator(
                    updated_by=None,
                    operator_id=real_id,
                    first_name=first_name,
                    last_name=last_name,
                    email=data.get('email', operator.user.email),
                    phone=data.get('phone', operator.user.phone),
                    designation=data.get('designation', operator.designation),
                    department=data.get('department', operator.department),
                    assigned_client_ids=assigned_client_ids,
                    permission_codenames=permission_codenames,
                )
                if raw_res.get('success'):
                    from staff.models import Staff
                    staff = Staff.objects.filter(id=staff_id).first()
                    return ServiceResult(success=True, data={'staff': cls.serialize(staff) if staff else raw_res.get('operator')})
                else:
                    return ServiceResult(success=False, message=raw_res.get('error', 'Failed to update operator'))
            return ServiceResult(success=False, message='Admin staff not found')
        else:
            return ServiceResult(success=False, message='Access denied/Not admin staff')

    @classmethod
    def set_temp_password(cls, staff_id: int, new_password: str, request=None) -> ServiceResult:
        staff_type, real_id = cls._decode_staff_id(staff_id)
        if staff_type == 'photographer':
            photographer = Photographer.objects.filter(id=real_id).first()
            if photographer:
                photographer.user.set_password(new_password)
                photographer.user.save()
                return ServiceResult(success=True, message='Password updated successfully')
        elif staff_type == 'operator':
            raw_res = OperatorCreationService.set_temp_password(profile_id=real_id, new_password=new_password, is_assistant=False, request=request)
            if raw_res.get('success'):
                return ServiceResult(success=True, message='Password updated successfully')
            else:
                return ServiceResult(success=False, message=raw_res.get('error', 'Failed to set password'))
        return ServiceResult(success=False, message='Staff member not found')

    @classmethod
    def get(cls, staff_id: int, include_permissions: bool = True) -> ServiceResult:
        staff_type, real_id = cls._decode_staff_id(staff_id)
        if staff_type == 'photographer':
            return PhotographerService.get(real_id)
        elif staff_type == 'operator':
            operator = Operator.objects.filter(id=real_id).first()
            if operator:
                from staff.models import Staff
                staff = Staff.objects.filter(id=staff_id).first()
                if staff:
                    return ServiceResult(success=True, data={'staff': cls.serialize(staff, include_permissions)})
            return ServiceResult(success=False, message='Admin staff not found')
        else:
            return ServiceResult(success=False, message='Access denied/Not admin staff')

    @classmethod
    def delete(cls, staff_id: int) -> ServiceResult:
        staff_type, real_id = cls._decode_staff_id(staff_id)
        if staff_type == 'photographer':
            return PhotographerService.delete(real_id)
        elif staff_type == 'operator':
            raw_res = OperatorCreationService.delete_operator(deleted_by=None, operator_id=real_id)
            if raw_res.get('success'):
                return ServiceResult(success=True, message=raw_res.get('message', 'Operator deleted successfully'))
            else:
                return ServiceResult(success=False, message=raw_res.get('error', 'Failed to delete operator'))
        else:
            return ServiceResult(success=False, message='Access denied/Not admin staff')

    @classmethod
    def toggle_status(cls, staff_id: int) -> ServiceResult:
        staff_type, real_id = cls._decode_staff_id(staff_id)
        if staff_type == 'photographer':
            return PhotographerService.toggle_status(real_id)
        elif staff_type == 'operator':
            raw_res = OperatorCreationService.toggle_status(toggled_by=None, operator_id=real_id)
            if raw_res.get('success'):
                return ServiceResult(
                    success=True,
                    message=raw_res.get('message', ''),
                    data={
                        'is_active': raw_res.get('is_active'),
                        'status': raw_res.get('status'),
                        'status_display': raw_res.get('status_display'),
                    }
                )
            else:
                return ServiceResult(success=False, message=raw_res.get('error', 'Failed to toggle status'))
        else:
            return ServiceResult(success=False, message='Access denied/Not admin staff')

    @classmethod
    def serialize(cls, staff, include_permissions: bool = True) -> Dict[str, Any]:
        """Serialize Staff instance to dict"""
        user = staff.user
        from django.utils.timezone import localtime
        data = {
            'id': staff.id,
            'name': user.get_full_name(),
            'email': cls._public_email(user.email),
            'phone': user.phone or '',
            'address': '',
            'department': staff.department or '',
            'designation': staff.designation or '',
            'staff_type': staff.staff_type,
            'status': 'active' if user.is_active else 'inactive',
            'profile_image_url': None,
            'created_at': localtime(staff.created_at).strftime('%d-%m-%Y %H:%M') if getattr(staff, 'created_at', None) else '',
            'updated_at': localtime(staff.updated_at).strftime('%d-%m-%Y %H:%M') if getattr(staff, 'updated_at', None) else '',
        }
        
        if include_permissions:
            for perm in cls.PERMISSION_FIELDS:
                data[perm] = getattr(staff, perm, False)
        
        # Include assigned client IDs
        data['assigned_client_ids'] = list(
            staff.assigned_organisations.values_list('id', flat=True)
        )
        
        return data

    @staticmethod
    def _public_email(email: str) -> str:
        """Hide internal placeholder emails from API payloads."""
        value = (email or '').strip()
        return '' if value.endswith('@noemail.local') else value

    @classmethod
    def list_admin_staff(cls) -> ServiceResult:
        """List all admin staff"""
        try:
            from staff.models import Staff
            staff_list = Staff.objects.filter(staff_type='operator')
            serialized = [cls.serialize(s) for s in staff_list]
            return ServiceResult(
                success=True,
                data={'staff_list': serialized}
            )
        except Exception as e:
            logger.exception("Error in list_admin_staff: %s", e)
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def list_client_staff(cls, client_id: int) -> ServiceResult:
        """List all staff for a specific client"""
        try:
            from staff.models import Staff
            staff_list = Staff.objects.filter(staff_type='assistant', client_id=client_id)
            serialized = [cls.serialize(s) for s in staff_list]
            return ServiceResult(
                success=True,
                data={'staff_list': serialized}
            )
        except Exception as e:
            logger.exception("Error in list_client_staff: %s", e)
            return ServiceResult(success=False, message=str(e))
