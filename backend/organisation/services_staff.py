"""
Client Staff Service — Shim wrapper around AssistantService for backward compatibility.
All calls are delegated to AssistantService in assistants app.
"""
from typing import Dict, Any, Optional, List
import logging

from core.services.base import BaseService, ServiceResult
from assistants.services import AssistantService
from core.utils import send_welcome_email

logger = logging.getLogger(__name__)


class OrganisationStaffService(BaseService):
    """
    Shim OrganisationStaffService class that wraps AssistantService.
    """
    STAFF_PERMISSION_FIELDS = AssistantService.ASSISTANT_PERMISSION_FIELDS
    NON_DELEGABLE_CLIENT_STAFF_PERMS = AssistantService.NON_DELEGABLE_ASSISTANT_PERMS

    @classmethod
    def _resolve_assignment_scope_ids(cls, *args, **kwargs):
        return AssistantService._resolve_assignment_scope_ids(*args, **kwargs)

    @classmethod
    def _normalize_scope_value_list(cls, *args, **kwargs):
        return AssistantService._normalize_scope_value_list(*args, **kwargs)

    @classmethod
    def _normalize_class_section_map(cls, *args, **kwargs):
        return AssistantService._normalize_class_section_map(*args, **kwargs)

    @classmethod
    def _normalize_assignment_scopes(cls, *args, **kwargs):
        return AssistantService._normalize_assignment_scopes(*args, **kwargs)

    @classmethod
    def _scope_value_union(cls, *args, **kwargs):
        return AssistantService._scope_value_union(*args, **kwargs)

    @classmethod
    def can_manage_staff(cls, user) -> bool:
        return AssistantService.can_manage_assistants(user)

    @classmethod
    def list_staff(cls, user) -> ServiceResult:
        res = AssistantService.list_assistants(user)
        if res.success and res.data and 'staff' in res.data:
            for item in res.data['staff']:
                if 'id' in item:
                    item['id'] = item['id'] + 200000
        return res

    @classmethod
    def get_staff_detail(cls, user, staff_id: int) -> ServiceResult:
        raw_id = staff_id % 100000 if staff_id >= 100000 else staff_id
        res = AssistantService.get_assistant_detail(user, raw_id)
        if res.success and res.data and 'id' in res.data:
            res.data['id'] = res.data['id'] + 200000
        return res

    @classmethod
    def create_staff(cls, user, data: Dict[str, Any]) -> ServiceResult:
        import sys
        import assistants.services
        old_send = getattr(assistants.services, 'send_welcome_email', None)
        current_module = sys.modules.get('organisation.services_staff')
        if current_module and hasattr(current_module, 'send_welcome_email'):
            assistants.services.send_welcome_email = current_module.send_welcome_email
        try:
            res = AssistantService.create_assistant(user, data)
        finally:
            if old_send is not None:
                assistants.services.send_welcome_email = old_send

        if res.success and res.data and 'staff_id' in res.data:
            res.data['staff_id'] = res.data['staff_id'] + 200000
        return res

    @classmethod
    def update_staff(cls, user, staff_id: int, data: Dict[str, Any], target_client=None) -> ServiceResult:
        raw_id = staff_id % 100000 if staff_id >= 100000 else staff_id
        return AssistantService.update_assistant(user, raw_id, data, target_client=target_client)

    @classmethod
    def toggle_staff_status(cls, user, staff_id: int) -> ServiceResult:
        raw_id = staff_id % 100000 if staff_id >= 100000 else staff_id
        return AssistantService.toggle_assistant_status(user, raw_id)

    @classmethod
    def delete_staff(cls, user, staff_id: int) -> ServiceResult:
        raw_id = staff_id % 100000 if staff_id >= 100000 else staff_id
        return AssistantService.delete_assistant(user, raw_id)

    @classmethod
    def set_temp_password(cls, user, staff_id: int, new_password: str, request=None) -> ServiceResult:
        raw_id = staff_id % 100000 if staff_id >= 100000 else staff_id
        return AssistantService.set_temp_password(user, raw_id, new_password, request=request)
