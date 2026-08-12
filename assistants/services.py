"""
Assistant Service — CRUD operations for client-managed assistants (formerly client staff).
"""
from typing import Dict, Any, Optional, List, Tuple
import logging
import secrets

from django.db import transaction
from django.db.models import Prefetch
from django.utils.timezone import localtime

from core.models import User, EmailLog
from organisation.models import Organisation
from assistants.models import Assistant
from tables.models import Table
from core.services.base import BaseService, ServiceResult
from core.services.cache_version_service import CacheVersionService
from core.services.permission_service import PermissionService
from core.utils import send_welcome_email
from organisation.services_access import OrganisationAccessService
from accounts.services import normalize_password_input

logger = logging.getLogger(__name__)


class AssistantService(BaseService):
    """
    Service for assistant management.
    Only Client Admin (role='client') can manage assistants.
    """
    
    # All permission fields that clients can delegate to their assistants.
    # Must match the Client model fields AND exist on the Assistant model.
    # Groups: ID Card List Tabs | Card Actions | Bulk Actions | App
    ASSISTANT_PERMISSION_FIELDS = [
        # ── ID Card List Tabs ────────────────────────────────────────
        'perm_idcard_pending_list', 'perm_idcard_verified_list',
        'perm_idcard_approved_list', 'perm_idcard_download_list',
        'perm_idcard_pool_list',
        
        # ── Export / Download ───────────────────────────────────────
        'perm_idcard_bulk_download',
        # ── Card Actions ──────────────────────────────────────────────
        'perm_idcard_add', 'perm_idcard_edit', 'perm_idcard_delete',
        'perm_idcard_info', 'perm_idcard_verify', 'perm_idcard_approve',
        'perm_idcard_updated_at', 'perm_idcard_delete_from_pool',
        'perm_idcard_retrieve',
        # ── App & Access ───────────────────────────────────────────
        'perm_mobile_app',
    ]

    NON_DELEGABLE_ASSISTANT_PERMS = []

    @staticmethod
    def _public_email(email: str) -> str:
        """Hide internal placeholder emails from API payloads."""
        value = (email or '').strip()
        return '' if value.endswith('@noemail.local') else value

    @staticmethod
    def _has_real_email(email: str) -> bool:
        """Return True when the address is suitable for SMTP delivery."""
        value = (email or '').strip().lower()
        return bool(value and '@' in value and not value.endswith('@noemail.local'))

    @staticmethod
    def _unexpected_error_result(action: str, exc: Exception) -> ServiceResult:
        logger.exception('AssistantService.%s failed: %s', action, exc)
        return ServiceResult(success=False, message='An unexpected error occurred. Please try again.')

    @staticmethod
    def _bump_dashboard_cache_versions(client_id: int) -> None:
        try:
            cid = int(client_id)
        except (TypeError, ValueError):
            return
        CacheVersionService.bump('dash_team_overview', 'global')
        CacheVersionService.bump('client_staff', f'client:{cid}')
        CacheVersionService.bump('client_dash_counts', f'client:{cid}')

    @staticmethod
    def _resolve_assignment_scope_ids(
        client: Organisation,
        raw_ids: Any,
        id_source: str = 'auto',
    ) -> Tuple[List[int], List[int]]:
        """Normalize assignment IDs into valid group IDs and table IDs."""
        if not isinstance(raw_ids, list):
            return [], []

        normalized_ids = sorted({
            int(v) for v in raw_ids
            if not isinstance(v, bool) and str(v).strip().isdigit() and int(v) > 0
        })
        if not normalized_ids:
            return [], []

        source = str(id_source or '').strip().lower()
        if source not in ('group', 'table', 'auto'):
            source = 'auto'

        if source == 'auto':
            group_count = Table.objects.filter(client=client).count()
            source = 'table' if group_count <= 1 else 'group'

        valid_group_ids = set(
            Table.objects.filter(client=client, id__in=normalized_ids)
            .values_list('id', flat=True)
        )

        if source == 'group':
            return sorted(valid_group_ids), []

        valid_table_ids = set(
            Table.objects.filter(
                group__client=client,
                deleted_by_client=False,
                id__in=normalized_ids,
            ).values_list('id', flat=True)
        )

        if valid_table_ids:
            table_group_ids = Table.objects.filter(
                id__in=valid_table_ids,
            ).values_list('group_id', flat=True)
            valid_group_ids.update(table_group_ids)
            return sorted(valid_group_ids), sorted(valid_table_ids)

        return sorted(valid_group_ids), []

    @staticmethod
    def _normalize_scope_value_list(raw_values: Any) -> List[str]:
        """Normalize class/section/branch lists into unique non-empty strings."""
        if not isinstance(raw_values, list):
            return []

        out: List[str] = []
        seen = set()
        for value in raw_values:
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            out.append(text)
        return out

    @staticmethod
    def _normalize_class_section_map(raw_map: Any) -> Dict[str, List[str]]:
        """Normalize per-class section selections into a string-to-list map."""
        if not isinstance(raw_map, dict):
            return {}

        out: Dict[str, List[str]] = {}
        for cls_name, raw_sections in raw_map.items():
            cls_text = str(cls_name).strip()
            if not cls_text:
                continue
            out[cls_text] = AssistantService._normalize_scope_value_list(raw_sections)
        return out

    @classmethod
    def _normalize_assignment_scopes(cls, client: Organisation, raw_scopes: Any) -> List[Dict[str, Any]]:
        """Validate and normalize per-scope filters sent by assignment chips."""
        if not isinstance(raw_scopes, list):
            return []

        pending_scopes: List[Dict[str, Any]] = []
        requested_group_ids = set()
        requested_table_ids = set()

        for item in raw_scopes:
            if not isinstance(item, dict):
                continue

            scope_type = str(item.get('scope_type', '') or '').strip().lower()
            if scope_type not in ('group', 'table'):
                continue

            raw_scope_id = item.get('scope_id')
            if isinstance(raw_scope_id, bool):
                continue
            try:
                scope_id = int(str(raw_scope_id).strip())
            except (TypeError, ValueError):
                continue
            if scope_id <= 0:
                continue

            if scope_type == 'group':
                requested_group_ids.add(scope_id)
            else:
                requested_table_ids.add(scope_id)

            pending_scopes.append({
                'scope_type': scope_type,
                'scope_id': scope_id,
                'classes': cls._normalize_scope_value_list(item.get('classes', [])),
                'sections': cls._normalize_scope_value_list(item.get('sections', [])),
                'branches': cls._normalize_scope_value_list(item.get('branches', [])),
                'class_sections': cls._normalize_class_section_map(item.get('class_sections', {})),
            })

        valid_group_ids = set(
            Table.objects.filter(
                client=client,
                id__in=list(requested_group_ids),
            ).values_list('id', flat=True)
        )

        valid_table_rows = list(
            Table.objects.filter(
                group__client=client,
                deleted_by_client=False,
                id__in=list(requested_table_ids),
            ).values_list('id', 'group_id')
        )
        valid_table_map = {int(tid): int(gid) for tid, gid in valid_table_rows}

        normalized_by_key: Dict[str, Dict[str, Any]] = {}
        for scope in pending_scopes:
            scope_type = scope['scope_type']
            scope_id = int(scope['scope_id'])

            if scope_type == 'group':
                if scope_id not in valid_group_ids:
                    continue
                group_id = scope_id
            else:
                group_id = valid_table_map.get(scope_id)
                if not group_id:
                    continue

            key = f'{scope_type}:{scope_id}'
            normalized_by_key[key] = {
                'scope_type': scope_type,
                'scope_id': scope_id,
                'group_id': int(group_id),
                'classes': scope['classes'],
                'sections': scope['sections'],
                'branches': scope['branches'],
                'class_sections': scope['class_sections'],
            }

        return sorted(
            normalized_by_key.values(),
            key=lambda s: (s['scope_type'], int(s['group_id']), int(s['scope_id'])),
        )

    @staticmethod
    def _scope_value_union(scopes: List[Dict[str, Any]]) -> Tuple[List[str], List[str], List[str]]:
        """Build legacy union lists from normalized scopes for compatibility."""
        classes, sections, branches = [], [], []
        seen_cls, seen_sec, seen_bra = set(), set(), set()

        for scope in scopes:
            class_sections = scope.get('class_sections') or {}
            if isinstance(class_sections, dict):
                for cls_name, raw_sections in class_sections.items():
                    key = str(cls_name).strip().lower()
                    if key and key not in seen_cls:
                        seen_cls.add(key)
                        classes.append(str(cls_name).strip())
                    for value in (raw_sections or []):
                        sec_key = str(value).strip().lower()
                        if sec_key and sec_key not in seen_sec:
                            seen_sec.add(sec_key)
                            sections.append(str(value).strip())

            for value in (scope.get('classes') or []):
                key = str(value).strip().lower()
                if key and key not in seen_cls:
                    seen_cls.add(key)
                    classes.append(str(value).strip())
            for value in (scope.get('sections') or []):
                key = str(value).strip().lower()
                if key and key not in seen_sec:
                    seen_sec.add(key)
                    sections.append(str(value).strip())
            for value in (scope.get('branches') or []):
                key = str(value).strip().lower()
                if key and key not in seen_bra:
                    seen_bra.add(key)
                    branches.append(str(value).strip())

        return classes, sections, branches
    
    @classmethod
    def _has_staff_management_access(cls, user) -> bool:
        """Check if user has staff management permissions (either client list perm or manage client staff)."""
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if PermissionService.has(user, 'perm_idcard_client_list'):
            return True
        if PermissionService.is_client(user) and PermissionService.has(user, 'perm_manage_assistant'):
            return True
        return False

    @classmethod
    def can_manage_assistants(cls, user) -> bool:
        """Check if user can manage assistants."""
        return cls._has_staff_management_access(user)
    
    @classmethod
    def list_assistants(cls, user, target_client=None) -> ServiceResult:
        """List all assistants for the client."""
        try:
            if target_client:
                client = target_client
            elif user.is_superuser:
                client = None
            else:
                client = OrganisationAccessService.get_organisation_for_user(user)
                if not client:
                    return ServiceResult(success=False, message='Client profile not found')
            
            if not cls._has_staff_management_access(user):
                return ServiceResult(success=False, message='Permission denied')

            assistant_only_fields = [
                'id',
                'user',
                'client',
                'created_at',
                'department',
                'designation',
                'assigned_table_ids',
                'allowed_classes',
                'allowed_sections',
                'assignment_scopes',
                'user__first_name',
                'user__last_name',
                'user__username',
                'user__email',
                'user__phone',
                'user__is_active',
            ] + list(cls.ASSISTANT_PERMISSION_FIELDS)
            
            assistant_filters = {}
            if client:
                assistant_filters['client'] = client

            assistant_list = Assistant.objects.filter(
                **assistant_filters
            ).select_related('user').only(*assistant_only_fields).prefetch_related(
                Prefetch('assigned_groups', queryset=Table.objects.only('id'))
            )
            
            assistant_data = []
            for assistant in assistant_list:
                assigned_group_ids = [group.id for group in assistant.assigned_groups.all()]
                item = {
                    'id': assistant.id,
                    'user_id': assistant.user.id,
                    'client_id': assistant.client_id,
                    'organisation_id': assistant.client_id,
                    'client_name': assistant.client.name if assistant.client else '-',
                    'organisation_name': assistant.client.name if assistant.client else '-',
                    'name': assistant.user.get_full_name() or assistant.user.username,
                    'role_title': 'Manager',
                    'email': cls._public_email(assistant.user.email),
                    'phone': assistant.user.phone or '',
                    'department': assistant.department or '',
                    'designation': assistant.designation or '',
                    'is_active': assistant.user.is_active,
                    'created_at': assistant.created_at.strftime('%d %b %Y'),
                    'assigned_group_ids': assigned_group_ids,
                    'assigned_table_ids': [
                        int(v) for v in (assistant.assigned_table_ids or [])
                        if str(v).strip().isdigit() and int(v) > 0
                    ],
                    'allowed_classes': assistant.allowed_classes or [],
                    'allowed_sections': assistant.allowed_sections or [],
                    'assignment_scopes': assistant.assignment_scopes or [],
                }
                for perm in cls.ASSISTANT_PERMISSION_FIELDS:
                    item[perm] = getattr(assistant, perm, False)
                assistant_data.append(item)
            
            if client:
                client_permissions = {
                    perm: getattr(client, perm, False)
                    for perm in cls.ASSISTANT_PERMISSION_FIELDS
                }
            else:
                client_permissions = {
                    perm: True
                    for perm in cls.ASSISTANT_PERMISSION_FIELDS
                }
            
            return ServiceResult(success=True, data={
                'managers': assistant_data,
                'assistants': assistant_data,
                'staff': assistant_data,  # Keep key for backward compatibility
                'client_permissions': client_permissions,
                'organisation_permissions': client_permissions,
            })
            
        except Exception as e:
            return cls._unexpected_error_result('list_assistants', e)
    
    @classmethod
    def get_assistant_detail(cls, user, assistant_id: int) -> ServiceResult:
        """Get details of a specific assistant."""
        try:
            try:
                assistant = Assistant.objects.select_related('user', 'client').prefetch_related(
                    Prefetch('assigned_groups', queryset=Table.objects.only('id'))
                ).get(id=assistant_id)
            except Assistant.DoesNotExist:
                return ServiceResult(success=False, message='Assistant not found')

            if user is not None and not user.is_superuser:
                client = OrganisationAccessService.get_organisation_for_user(user)
                if not client or assistant.client_id != client.id:
                    return ServiceResult(success=False, message='Access denied')
                if not cls._has_staff_management_access(user):
                    return ServiceResult(success=False, message='Permission denied')
            
            client = assistant.client
            assigned_group_ids = [group.id for group in assistant.assigned_groups.all()]
            
            client_permissions = {
                perm: getattr(client, perm, False)
                for perm in cls.ASSISTANT_PERMISSION_FIELDS
            }
            
            detail = {
                'id': assistant.id,
                'client_id': assistant.client_id,
                'client_name': assistant.client.name if assistant.client else '-',
                'first_name': assistant.user.first_name,
                'last_name': assistant.user.last_name,
                'name': assistant.user.get_full_name() or assistant.user.username,
                'email': cls._public_email(assistant.user.email),
                'phone': assistant.user.phone or '',
                'department': assistant.department or '',
                'designation': assistant.designation or '',
                'is_active': assistant.user.is_active,
                'status': 'active' if assistant.user.is_active else 'inactive',
                'created_at': assistant.created_at.strftime('%Y-%m-%dT%H:%M:%S'),
                'profile_image_url': None,
                'assigned_group_ids': assigned_group_ids,
                'assigned_table_ids': [
                    int(v) for v in (assistant.assigned_table_ids or [])
                    if str(v).strip().isdigit() and int(v) > 0
                ],
                'allowed_classes': assistant.allowed_classes or [],
                'allowed_sections': assistant.allowed_sections or [],
                'allowed_branches': assistant.allowed_branches or [],
                'assignment_scopes': assistant.assignment_scopes or [],
                'client_permissions': client_permissions,
            }

            if not detail['assignment_scopes']:
                legacy_classes = list(assistant.allowed_classes or [])
                legacy_sections = list(assistant.allowed_sections or [])
                group_ids = list(assistant.assigned_groups.values_list('id', flat=True))
                table_ids = [
                    int(v) for v in (assistant.assigned_table_ids or [])
                    if str(v).strip().isdigit() and int(v) > 0
                ]

                if legacy_classes:
                    scope_type = 'group'
                    scope_id = group_ids[0] if len(group_ids) >= 1 else None
                    if scope_id is None and len(table_ids) >= 1:
                        scope_type = 'table'
                        scope_id = table_ids[0]

                    if scope_id is not None:
                        # Build class_sections map for the classes
                        class_sections = {}
                        for cls_name in legacy_classes:
                            class_sections[cls_name] = legacy_sections

                        detail['assignment_scopes'] = [{
                            'scope_type': scope_type,
                            'scope_id': scope_id,
                            'group_id': group_ids[0] if group_ids else scope_id,
                            'classes': legacy_classes,
                            'sections': legacy_sections,
                            'branches': list(assistant.allowed_branches or []),
                            'class_sections': class_sections,
                        }]

            for perm in cls.ASSISTANT_PERMISSION_FIELDS:
                detail[perm] = getattr(assistant, perm, False)
            
            return ServiceResult(success=True, data=detail)
            
        except Exception as e:
            return cls._unexpected_error_result('get_assistant_detail', e)
    
    @classmethod
    def create_assistant(cls, user, data: Dict[str, Any], target_client=None) -> ServiceResult:
        """Create a new assistant."""
        try:
            send_welcome = False
            welcome_info = {}
            welcome_user_id = None
            welcome_email_log_id = None
            welcome_email_failed_reason = ''

            if target_client:
                client = target_client
            elif user.is_superuser:
                client_id = data.get('client_id')
                if not client_id:
                    return ServiceResult(success=False, message='Client is required to create an assistant.')
                from organisation.models import Organisation
                client = Organisation.objects.filter(id=client_id).first()
                if not client:
                    return ServiceResult(success=False, message='Client not found.')
            else:
                client = OrganisationAccessService.get_organisation_for_user(user)
                if not client:
                    return ServiceResult(success=False, message='Client profile not found')
                if not cls._has_staff_management_access(user):
                    return ServiceResult(success=False, message='Permission denied')

            first_name = str(data.get('first_name') or '').strip()
            last_name = str(data.get('last_name') or '').strip()
            if not first_name:
                name = str(data.get('name') or '').strip()
                name_parts = name.split() if name else []
                first_name = name_parts[0] if name_parts else ''
                last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

            display_name = f'{first_name} {last_name}'.strip()
            if not display_name:
                return ServiceResult(success=False, message='Name is required')

            raw_email = str(data.get('email') or '').strip().lower()
            if not raw_email:
                return ServiceResult(success=False, message='Email is required')

            if User.objects.filter(email__iexact=raw_email).exists():
                return ServiceResult(
                    success=False,
                    message='A user with this email already exists'
                )
            email = raw_email

            username = email.split('@')[0].lower().replace('.', '_')
            if not username:
                username = f'assistant_{secrets.token_hex(4)}'
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            
            phone = str(data.get('phone') or '').strip()
            password = str(data.get('password') or '').strip()
            used_phone_as_password = False
            if not password:
                if phone:
                    password = phone
                    used_phone_as_password = True
                else:
                    return ServiceResult(
                        success=False,
                        message='Phone number is required when custom password is not provided'
                    )
            
            if not used_phone_as_password:
                from django.contrib.auth.password_validation import validate_password
                try:
                    validate_password(password)
                except Exception as pw_err:
                    return ServiceResult(success=False, message=str(pw_err))
            
            with transaction.atomic():
                is_active = cls.parse_bool(data.get('is_active', True))
                assistant_user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                    role='assistant',
                    is_active=is_active,
                )
                
                assistant_kwargs = {
                    'user': assistant_user,
                    'client': Organisation,
                    'department': data.get('department', ''),
                    'designation': data.get('designation', ''),
                    'allowed_classes': [
                        str(v).strip() for v in (data.get('allowed_classes') or [])
                        if isinstance(v, str) and str(v).strip()
                    ] if isinstance(data.get('allowed_classes', []), list) else [],
                    'allowed_sections': [
                        str(v).strip() for v in (data.get('allowed_sections') or [])
                        if isinstance(v, str) and str(v).strip()
                    ] if isinstance(data.get('allowed_sections', []), list) else [],
                    'allowed_branches': [
                        str(v).strip() for v in (data.get('allowed_branches') or [])
                        if isinstance(v, str) and str(v).strip()
                    ] if isinstance(data.get('allowed_branches', []), list) else [],
                }
                
                for perm in cls.ASSISTANT_PERMISSION_FIELDS:
                    if perm in data:
                        if getattr(client, perm, False):
                            assistant_kwargs[perm] = cls.parse_bool(data[perm])
                        else:
                            assistant_kwargs[perm] = False
                    else:
                        if getattr(client, perm, False):
                            assistant_kwargs[perm] = True
                        else:
                            assistant_kwargs[perm] = False

                for perm in cls.NON_DELEGABLE_ASSISTANT_PERMS:
                    assistant_kwargs[perm] = False
                
                assistant = Assistant.objects.create(**assistant_kwargs)

                normalized_assignment_scopes = None
                if 'assignment_scopes' in data:
                    normalized_assignment_scopes = cls._normalize_assignment_scopes(
                        client,
                        data.get('assignment_scopes', []),
                    )

                scope_group_ids = sorted({
                    int(scope.get('group_id', 0) or 0)
                    for scope in (normalized_assignment_scopes or [])
                    if int(scope.get('group_id', 0) or 0) > 0
                })
                scope_table_ids = sorted({
                    int(scope.get('scope_id', 0) or 0)
                    for scope in (normalized_assignment_scopes or [])
                    if str(scope.get('scope_type', '')).lower() == 'table' and int(scope.get('scope_id', 0) or 0) > 0
                })

                assigned_groups = data.get('assigned_groups', [])
                if (not assigned_groups) and normalized_assignment_scopes:
                    assigned_groups = scope_group_ids

                resolved_group_ids = []
                resolved_table_ids = []
                if assigned_groups:
                    resolved_group_ids, resolved_table_ids = cls._resolve_assignment_scope_ids(
                        client,
                        assigned_groups,
                        data.get('assignment_id_source', 'auto'),
                    )

                if normalized_assignment_scopes:
                    resolved_group_ids = sorted(set(resolved_group_ids) | set(scope_group_ids))
                    resolved_table_ids = sorted(set(resolved_table_ids) | set(scope_table_ids))

                if assigned_groups or normalized_assignment_scopes is not None:
                    valid_groups = Table.objects.filter(
                        id__in=resolved_group_ids,
                        client=client,
                    )
                    assistant.assigned_groups.set(valid_groups)
                    assistant.assigned_table_ids = resolved_table_ids
                    assistant.save(update_fields=['assigned_table_ids'])

                if normalized_assignment_scopes is not None:
                    valid_group_set = set(resolved_group_ids)
                    valid_table_set = set(resolved_table_ids)
                    filtered_scopes = []
                    for scope in normalized_assignment_scopes:
                        stype = scope.get('scope_type')
                        sid = int(scope.get('scope_id', 0) or 0)
                        if stype == 'group' and sid in valid_group_set:
                            filtered_scopes.append(scope)
                        elif stype == 'table' and sid in valid_table_set:
                            filtered_scopes.append(scope)

                    classes_u, sections_u, branches_u = cls._scope_value_union(filtered_scopes)
                    assistant.assignment_scopes = filtered_scopes
                    assistant.allowed_classes = classes_u
                    assistant.allowed_sections = sections_u
                    assistant.allowed_branches = branches_u
                    assistant.save(update_fields=['assignment_scopes', 'allowed_classes', 'allowed_sections', 'allowed_branches'])

                if cls._has_real_email(email):
                    log = EmailLog.objects.create(
                        recipient_name=display_name or assistant_user.get_full_name() or assistant_user.username,
                        recipient_email=email,
                        subject='Welcome to Adarsh Admin - Your Account is Ready!',
                        email_type=EmailLog.EMAIL_TYPE_WELCOME,
                        status=EmailLog.STATUS_ON_HOLD,
                    )
                    welcome_email_log_id = log.pk

                    if is_active:
                        send_welcome = True
                        welcome_user_id = assistant_user.pk
                        welcome_info = {
                            'name': display_name or assistant_user.get_full_name() or assistant_user.username,
                            'email': email,
                            'password': password,
                            'phone': phone,
                            'role': 'assistant',
                        }

                transaction.on_commit(lambda cid=client.id: cls._bump_dashboard_cache_versions(cid))

            if send_welcome:
                _user_pk = welcome_user_id
                _log_id = welcome_email_log_id
                _email = welcome_info['email']

                def _on_email_success():
                    try:
                        User.objects.filter(pk=_user_pk).update(welcome_email_sent=True)
                        EmailLog.objects.filter(pk=_log_id).update(
                            status=EmailLog.STATUS_SENT,
                            sent_at=localtime(),
                            error_message='',
                        )
                    except Exception as cb_err:
                        logger.warning('Email success callback failed for %s: %s', _email, cb_err)

                def _on_email_failure(err_msg):
                    try:
                        EmailLog.objects.filter(pk=_log_id).update(
                            status=EmailLog.STATUS_FAILED,
                            error_message=str(err_msg),
                        )
                    except Exception as cb_err:
                        logger.warning('Email failure callback failed for %s: %s', _email, cb_err)

                try:
                    queued, queue_message = send_welcome_email(
                        name=welcome_info['name'],
                        email=welcome_info['email'],
                        password=welcome_info['password'],
                        role=welcome_info['role'],
                        phone=welcome_info['phone'],
                        request=None,
                        on_success=_on_email_success,
                        on_failure=_on_email_failure,
                    )
                except Exception as email_err:
                    queued = False
                    queue_message = str(email_err)

                if not queued:
                    welcome_email_failed_reason = queue_message or 'Failed to queue welcome email.'
                    _on_email_failure(welcome_email_failed_reason)

            email_sent = bool(send_welcome and not welcome_email_failed_reason)
            message = f'Assistant "{display_name}" created successfully!'
            if email_sent:
                message += ' Welcome email queued for delivery.'
            elif send_welcome and welcome_email_failed_reason:
                message += f' Welcome email could not be sent right now: {welcome_email_failed_reason}'
            elif not send_welcome and cls._has_real_email(email):
                message += ' Account is inactive; welcome email will be sent after activation.'
            
            return ServiceResult(
                success=True,
                message=message,
                data={'staff_id': assistant.id, 'email_sent': email_sent}
            )
            
        except Exception as e:
            return cls._unexpected_error_result('create_assistant', e)
    
    @classmethod
    def update_assistant(cls, user, assistant_id: int, data: Dict[str, Any], target_client=None) -> ServiceResult:
        """Update an assistant."""
        try:
            if user.is_superuser:
                try:
                    assistant = Assistant.objects.select_related('user', 'client').get(id=assistant_id)
                    client = assistant.client
                except Assistant.DoesNotExist:
                    return ServiceResult(success=False, message='Assistant not found')
            else:
                client = target_client or OrganisationAccessService.get_organisation_for_user(user)
                if not client:
                    return ServiceResult(success=False, message='Client profile not found')
                if not cls._has_staff_management_access(user):
                    return ServiceResult(success=False, message='Permission denied')

            with transaction.atomic():
                if not user.is_superuser:
                    try:
                        assistant = (
                            Assistant.objects
                            .select_for_update()
                            .select_related('user')
                            .get(id=assistant_id, client=client)
                        )
                    except Assistant.DoesNotExist:
                        return ServiceResult(success=False, message='Assistant not found')
                else:
                    # For superuser, lock the record we already found
                    assistant = Assistant.objects.select_for_update().select_related('user').get(id=assistant_id)

                normalized_assignment_scopes = None
                if 'assignment_scopes' in data:
                    normalized_assignment_scopes = cls._normalize_assignment_scopes(
                        client,
                        data.get('assignment_scopes', []),
                    )

                scope_group_ids = sorted({
                    int(scope.get('group_id', 0) or 0)
                    for scope in (normalized_assignment_scopes or [])
                    if int(scope.get('group_id', 0) or 0) > 0
                })
                scope_table_ids = sorted({
                    int(scope.get('scope_id', 0) or 0)
                    for scope in (normalized_assignment_scopes or [])
                    if str(scope.get('scope_type', '')).lower() == 'table' and int(scope.get('scope_id', 0) or 0) > 0
                })

                assistant_user = assistant.user

                if 'first_name' in data:
                    assistant_user.first_name = str(data['first_name'] or '').strip()
                if 'last_name' in data:
                    assistant_user.last_name = str(data['last_name'] or '').strip()

                name = str(data.get('name') or '').strip()
                if name and 'first_name' not in data:
                    name_parts = name.split()
                    assistant_user.first_name = name_parts[0] if name_parts else ''
                    assistant_user.last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

                if 'phone' in data:
                    assistant_user.phone = data['phone']

                if 'is_active' in data:
                    assistant_user.is_active = cls.parse_bool(data['is_active'])

                assistant_user.save()

                if 'department' in data:
                    assistant.department = data['department']
                if 'designation' in data:
                    assistant.designation = data['designation']

                for perm in cls.ASSISTANT_PERMISSION_FIELDS:
                    if perm in data:
                        if getattr(client, perm, False):
                            setattr(assistant, perm, cls.parse_bool(data[perm]))
                        else:
                            setattr(assistant, perm, False)

                for perm in cls.NON_DELEGABLE_ASSISTANT_PERMS:
                    setattr(assistant, perm, False)

                if 'allowed_classes' in data:
                    allowed_classes = data['allowed_classes']
                    if isinstance(allowed_classes, list):
                        assistant.allowed_classes = [str(v).strip() for v in allowed_classes if isinstance(v, str)]
                if 'allowed_sections' in data:
                    allowed_sections = data['allowed_sections']
                    if isinstance(allowed_sections, list):
                        assistant.allowed_sections = [str(v).strip() for v in allowed_sections if isinstance(v, str)]
                if 'allowed_branches' in data:
                    allowed_branches = data['allowed_branches']
                    if isinstance(allowed_branches, list):
                        assistant.allowed_branches = [str(v).strip() for v in allowed_branches if isinstance(v, str)]

                assistant.save()

                resolved_group_ids = list(assistant.assigned_groups.values_list('id', flat=True))
                resolved_table_ids = [
                    int(v) for v in (assistant.assigned_table_ids or [])
                    if str(v).strip().isdigit() and int(v) > 0
                ]

                if ('assigned_groups' in data) or ('assignment_scopes' in data):
                    explicit_assignment_payload = 'assigned_groups' in data
                    explicit_scopes_payload = 'assignment_scopes' in data
                    
                    if explicit_assignment_payload:
                        assignment_ids = data.get('assigned_groups', [])
                        if (not assignment_ids) and normalized_assignment_scopes:
                            assignment_ids = scope_group_ids

                        if assignment_ids:
                            resolved_group_ids, resolved_table_ids = cls._resolve_assignment_scope_ids(
                                client,
                                assignment_ids,
                                data.get('assignment_id_source', 'auto'),
                            )
                        else:
                            resolved_group_ids, resolved_table_ids = [], []
                    elif explicit_scopes_payload:
                        resolved_group_ids, resolved_table_ids = [], []

                    if explicit_scopes_payload and normalized_assignment_scopes:
                        resolved_group_ids = sorted(set(resolved_group_ids) | set(scope_group_ids))
                        resolved_table_ids = sorted(set(resolved_table_ids) | set(scope_table_ids))

                    valid_groups = Table.objects.filter(
                        id__in=resolved_group_ids,
                        client=client,
                    )
                    assistant.assigned_groups.set(valid_groups)
                    assistant.assigned_table_ids = resolved_table_ids
                    assistant.save(update_fields=['assigned_table_ids'])

                if 'assignment_scopes' in data:
                    valid_group_set = set(int(v) for v in (resolved_group_ids or []))
                    valid_table_set = set(int(v) for v in (resolved_table_ids or []))
                    filtered_scopes = []
                    for scope in normalized_assignment_scopes:
                        stype = scope.get('scope_type')
                        sid = int(scope.get('scope_id', 0) or 0)
                        if stype == 'group' and sid in valid_group_set:
                            filtered_scopes.append(scope)
                        elif stype == 'table' and sid in valid_table_set:
                            filtered_scopes.append(scope)

                    classes_u, sections_u, branches_u = cls._scope_value_union(filtered_scopes)
                    assistant.assignment_scopes = filtered_scopes
                    assistant.allowed_classes = classes_u
                    assistant.allowed_sections = sections_u
                    assistant.allowed_branches = branches_u
                    assistant.save(update_fields=['assignment_scopes', 'allowed_classes', 'allowed_sections', 'allowed_branches'])

                transaction.on_commit(lambda cid=client.id: cls._bump_dashboard_cache_versions(cid))
            
            return ServiceResult(
                success=True,
                message='Assistant updated successfully!'
            )
            
        except Exception as e:
            return cls._unexpected_error_result('update_assistant', e)
    
    @classmethod
    def toggle_assistant_status(cls, user, assistant_id: int) -> ServiceResult:
        """Toggle assistant active/inactive status."""
        try:
            # First fetch without locking to do permission checks cheaply
            try:
                assistant = Assistant.objects.select_related('user', 'client').get(id=assistant_id)
            except Assistant.DoesNotExist:
                return ServiceResult(success=False, message='Assistant not found')

            if user is not None and not user.is_superuser:
                client = OrganisationAccessService.get_organisation_for_user(user)
                if not client or assistant.client_id != client.id:
                    return ServiceResult(success=False, message='Access denied')
                if not cls._has_staff_management_access(user):
                    return ServiceResult(success=False, message='Permission denied')

            client = assistant.client
            with transaction.atomic():
                # Re-query inside atomic transaction with select_for_update
                assistant_locked = Assistant.objects.select_for_update().select_related('user').get(id=assistant_id)
                assistant_user = assistant_locked.user
                assistant_user.is_active = not assistant_user.is_active
                assistant_user.save(update_fields=['is_active'])

                transaction.on_commit(lambda cid=client.id: cls._bump_dashboard_cache_versions(cid))

            status = 'active' if assistant_user.is_active else 'inactive'

            return ServiceResult(
                success=True,
                message=f'Assistant status changed to {status}!',
                data={'is_active': assistant_user.is_active}
            )

        except Exception as e:
            return cls._unexpected_error_result('toggle_assistant_status', e)
    
    @classmethod
    def delete_assistant(cls, user, assistant_id: int) -> ServiceResult:
        """Delete an assistant."""
        try:
            try:
                assistant = Assistant.objects.select_related('user', 'client').get(id=assistant_id)
            except Assistant.DoesNotExist:
                return ServiceResult(success=False, message='Assistant not found')

            if user is not None and not user.is_superuser:
                client = OrganisationAccessService.get_organisation_for_user(user)
                if not client or assistant.client_id != client.id:
                    return ServiceResult(success=False, message='Access denied')
                if not cls._has_staff_management_access(user):
                    return ServiceResult(success=False, message='Permission denied')
            
            client = assistant.client
            assistant_name = assistant.user.get_full_name() or assistant.user.username
            assistant_user = assistant.user
            
            with transaction.atomic():
                # Fetch specifically to delete
                to_delete = Assistant.objects.get(id=assistant_id)
                to_delete.delete()
                assistant_user.delete()

            cls._bump_dashboard_cache_versions(client.id)
            
            return ServiceResult(
                success=True,
                message=f'Assistant "{assistant_name}" deleted successfully!'
            )
            
        except Exception as e:
            return cls._unexpected_error_result('delete_assistant', e)

    @classmethod
    def set_temp_password(cls, user, assistant_id: int, new_password: str, request=None) -> ServiceResult:
        """Set temporary password for an assistant account."""
        try:
            assistant = Assistant.objects.select_related('client').filter(id=assistant_id).first()
            if not assistant:
                return ServiceResult(success=False, message='Assistant not found')

            if user is not None and not user.is_superuser:
                client = OrganisationAccessService.get_organisation_for_user(user)
                if not client or assistant.client_id != client.id:
                    return ServiceResult(success=False, message='Access denied')
                if not PermissionService.has(user, 'perm_set_temp_password'):
                    return ServiceResult(success=False, message='Permission denied')

            from operators.services import OperatorCreationService
            res_dict = OperatorCreationService.set_temp_password(assistant.id, new_password, is_assistant=True, request=request)
            if res_dict.get('success'):
                return ServiceResult(
                    success=True,
                    message=res_dict.get('message', ''),
                    data={'email_sent': res_dict.get('email_sent', False)}
                )
            else:
                return ServiceResult(
                    success=False,
                    message=res_dict.get('error', res_dict.get('message', 'Failed to set password'))
                )

        except Exception as e:
            return cls._unexpected_error_result('set_temp_password', e)

    @classmethod
    def bulk_create_from_excel(cls, user, target_client, file_obj) -> ServiceResult:
        """Create multiple assistants from an uploaded Excel file."""
        import pandas as pd
        from django.contrib.auth.models import User
        from django.db import transaction

        try:
            # Read the Excel file
            df = pd.read_excel(file_obj)
            # Normalize column names for matching
            df.columns = [str(c).strip().lower() for c in df.columns]

            # Find matching column names
            name_col = next((c for c in df.columns if c in ('name', 'full name', 'fullname')), None)
            email_col = next((c for c in df.columns if c in ('email', 'email address')), None)
            password_col = next((c for c in df.columns if c in ('password',)), None)
            phone_col = next((c for c in df.columns if c in ('phone', 'phone number', 'mobile')), None)

            if not name_col or not email_col or not password_col:
                return ServiceResult(
                    success=False, 
                    message="Excel file must contain 'Name', 'Email', and 'Password' columns."
                )

            created_count = 0
            skipped_count = 0
            skipped_reasons = []

            # Pre-fetch existing emails and usernames to avoid IntegrityError
            existing_emails = set(User.objects.values_list('email', flat=True))
            existing_usernames = set(User.objects.values_list('username', flat=True))

            for index, row in df.iterrows():
                name = str(row.get(name_col, '')).strip()
                email = str(row.get(email_col, '')).strip().lower()
                password = str(row.get(password_col, '')).strip()
                phone = str(row.get(phone_col, '')).strip() if phone_col else ''
                if phone.lower() == 'nan':
                    phone = ''

                # Skip invalid or empty rows
                if not name or not email or not password or name.lower() == 'nan' or email.lower() == 'nan' or password.lower() == 'nan':
                    skipped_count += 1
                    skipped_reasons.append(f"Row {index + 2}: Missing required fields.")
                    continue

                if email in existing_emails or email in existing_usernames:
                    skipped_count += 1
                    skipped_reasons.append(f"Row {index + 2}: Email '{email}' already exists.")
                    continue

                try:
                    with transaction.atomic():
                        new_user = User.objects.create(
                            username=email,
                            email=email,
                            is_active=False  # Inactive by default per requirements
                        )
                        name_parts = name.split(' ', 1)
                        new_user.first_name = name_parts[0]
                        if len(name_parts) > 1:
                            new_user.last_name = name_parts[1]
                        new_user.set_password(password)
                        new_user.save()

                        Assistant.objects.create(
                            user=new_user,
                            client=target_client,
                            phone=phone
                        )
                        created_count += 1
                        existing_emails.add(email)
                        existing_usernames.add(email)
                except Exception as e:
                    skipped_count += 1
                    skipped_reasons.append(f"Row {index + 2}: Error - {str(e)}")

            if created_count == 0 and skipped_count > 0:
                return ServiceResult(
                    success=False, 
                    message=f"No assistants were created. Skipped {skipped_count} rows.", 
                    data={'reasons': skipped_reasons}
                )

            message = f"Successfully created {created_count} assistant{'s' if created_count != 1 else ''}."
            if skipped_count > 0:
                message += f" Skipped {skipped_count} row{'s' if skipped_count != 1 else ''}."

            return ServiceResult(
                success=True, 
                message=message, 
                data={'created': created_count, 'skipped': skipped_count, 'reasons': skipped_reasons}
            )

        except Exception as e:
            return cls._unexpected_error_result('bulk_create_from_excel', e)

    @classmethod
    def get_client_class_sections(cls, client, group=None, table=None):
        """Returns a dict of class names to a list of their section names for a client.
        
        Filtering priority:
          - table  → only cards from that specific table
          - group  → all tables inside that group
          - neither → all tables for the client
        """
        from tables.models import Table, IDCard
        tables = Table.objects.filter(group__client=client, deleted_by_client=False)
        if table:
            tables = tables.filter(id=table.id)
        elif group:
            tables = tables.filter(group=group)
        table_field_map = {}
        for t in tables:
            class_field, section_field = None, None
            for field in (t.fields or []):
                ft = field.get('type', '').lower()
                fn = field.get('name', '')
                fn_lower = fn.lower()
                if ft == 'class' or fn_lower == 'class':
                    class_field = fn
                elif ft == 'section' or fn_lower == 'section':
                    section_field = fn
            if class_field or section_field:
                table_field_map[t.id] = {'class_field': class_field, 'section_field': section_field}

        class_sections = {}
        if not table_field_map:
            return class_sections

        qs = IDCard.objects.filter(table_id__in=table_field_map.keys(), deleted_at__isnull=True)
        cards = qs.values('table_id', 'field_data')

        for card in cards:
            t_id = card['table_id']
            data = card.get('field_data') or {}
            c_f = table_field_map[t_id].get('class_field')
            s_f = table_field_map[t_id].get('section_field')

            c_val = str(data.get(c_f, '')).strip() if c_f else ''
            s_val = str(data.get(s_f, '')).strip() if s_f else ''

            if c_val:
                if c_val not in class_sections:
                    class_sections[c_val] = set()
                if s_val:
                    class_sections[c_val].add(s_val)

        # Convert sets to sorted lists
        return {k: sorted(list(v)) for k, v in class_sections.items()}

    @classmethod
    def auto_create_assistants(cls, user, target_client, acronym, mode, auto_assign=True, group=None, table=None) -> ServiceResult:
        """Auto create assistants based on client classes/sections and return an Excel file buffer.
        
        When 'table' is provided (single-list selection), classes/sections are read
        only from that table and assignments are scoped to that table.
        When only 'group' is provided, all tables in the group are used.
        """
        import openpyxl
        import io
        import re
        import random
        from django.contrib.auth import get_user_model
        User = get_user_model()
        from django.db import transaction

        acronym = str(acronym).strip()
        if not acronym:
            return ServiceResult(success=False, message="Acronym is required")
        
        mode = str(mode).strip().lower()
        if mode not in ('class', 'section'):
            return ServiceResult(success=False, message="Mode must be 'class' or 'section'")

        class_sections = cls.get_client_class_sections(target_client, group=group, table=table)
        is_fallback_mode = False
        if not class_sections:
            is_fallback_mode = True
            if table:
                class_sections = {table.name: []}
            elif group:
                class_sections = {group.name: []}
            else:
                scope_desc = 'list/table' if table else 'client/group'
                return ServiceResult(success=False, message=f"No classes found for this {scope_desc}")

        def clean_for_email(text):
            # Remove all non-alphanumeric characters and lowercase
            return re.sub(r'[^a-zA-Z0-9]', '', str(text)).lower()

        existing_emails = set(User.objects.values_list('email', flat=True))
        existing_usernames = set(User.objects.values_list('username', flat=True))

        created_assistants = []

        try:
            with transaction.atomic():
                for cls_name, sections in class_sections.items():
                    if mode == 'class':
                        # Create one per class
                        name = f"{acronym} {cls_name}"
                        email_prefix = clean_for_email(cls_name)
                        email = f"{email_prefix}@assistant.{clean_for_email(acronym)}"
                        
                        # Handle duplicate emails
                        counter = 2
                        while email in existing_emails or email in existing_usernames:
                            email = f"{email_prefix}{counter}@assistant.{clean_for_email(acronym)}"
                            counter += 1
                            
                        password = f"{acronym}@{random.randint(1000, 9999)}"

                        new_user = User.objects.create(
                            username=email,
                            email=email,
                            role='assistant',
                            is_active=True
                        )
                        name_parts = name.split(' ', 1)
                        new_user.first_name = name_parts[0]
                        if len(name_parts) > 1:
                            new_user.last_name = name_parts[1]
                        new_user.set_password(password)
                        new_user.save()

                        allowed_classes = [] if is_fallback_mode else ([cls_name] if auto_assign else [])
                        assistant_kwargs = {
                            'user': new_user,
                            'client': target_client,
                            'allowed_classes': allowed_classes
                        }
                        for perm in cls.ASSISTANT_PERMISSION_FIELDS:
                            if getattr(target_client, perm, False):
                                assistant_kwargs[perm] = True
                            else:
                                assistant_kwargs[perm] = False
                        assistant = Assistant.objects.create(**assistant_kwargs)
                        if group:
                            assistant.assigned_groups.add(group)
                            if auto_assign:
                                _cs = {} if is_fallback_mode else ({cls_name: []} if allowed_classes else {})
                                if table:
                                    # Scoped to a specific table
                                    assistant.assignment_scopes = [{
                                        'scope_type': 'table',
                                        'scope_id': table.id,
                                        'group_id': group.id,
                                        'table_id': table.id,
                                        'classes': allowed_classes,
                                        'sections': [],
                                        'branches': [],
                                        'class_sections': _cs,
                                    }]
                                else:
                                    # Scoped to the whole group
                                    assistant.assignment_scopes = [{
                                        'scope_type': 'group',
                                        'scope_id': group.id,
                                        'group_id': group.id,
                                        'classes': allowed_classes,
                                        'sections': [],
                                        'branches': [],
                                        'class_sections': _cs,
                                    }]
                                assistant.save(update_fields=['assignment_scopes'])
                        existing_emails.add(email)
                        existing_usernames.add(email)
                        created_assistants.append({'Name': name, 'Email': email, 'Password': password})

                    elif mode == 'section':
                        # Create one per section (or just class if it has no sections)
                        if not sections:
                            sections = [''] # Force at least one iteration if class has no sections

                        for sec_name in sections:
                            if sec_name:
                                name = f"{acronym} {cls_name}-{sec_name}"
                                email_prefix = clean_for_email(cls_name) + clean_for_email(sec_name)
                            else:
                                name = f"{acronym} {cls_name}"
                                email_prefix = clean_for_email(cls_name)

                            email = f"{email_prefix}@assistant.{clean_for_email(acronym)}"
                            
                            counter = 2
                            while email in existing_emails or email in existing_usernames:
                                email = f"{email_prefix}{counter}@assistant.{clean_for_email(acronym)}"
                                counter += 1

                            password = f"{acronym}@{random.randint(1000, 9999)}"

                            new_user = User.objects.create(
                                username=email,
                                email=email,
                                role='assistant',
                                is_active=True
                            )
                            name_parts = name.split(' ', 1)
                            new_user.first_name = name_parts[0]
                            if len(name_parts) > 1:
                                new_user.last_name = name_parts[1]
                            new_user.set_password(password)
                            new_user.save()

                            allowed_classes = [] if is_fallback_mode else ([cls_name] if auto_assign else [])
                            allowed_sections = [] if is_fallback_mode else ([sec_name] if (auto_assign and sec_name) else [])
                            assistant_kwargs = {
                                'user': new_user,
                                'client': target_client,
                                'allowed_classes': allowed_classes,
                                'allowed_sections': allowed_sections
                            }
                            for perm in cls.ASSISTANT_PERMISSION_FIELDS:
                                if getattr(target_client, perm, False):
                                    assistant_kwargs[perm] = True
                                else:
                                    assistant_kwargs[perm] = False
                            assistant = Assistant.objects.create(**assistant_kwargs)
                            if group:
                                assistant.assigned_groups.add(group)
                                if auto_assign:
                                    _cs = {} if is_fallback_mode else ({cls_name: allowed_sections} if allowed_classes else {})
                                    if table:
                                        # Scoped to a specific table
                                        assistant.assignment_scopes = [{
                                            'scope_type': 'table',
                                            'scope_id': table.id,
                                            'group_id': group.id,
                                            'table_id': table.id,
                                            'classes': allowed_classes,
                                            'sections': allowed_sections,
                                            'branches': [],
                                            'class_sections': _cs,
                                        }]
                                    else:
                                        # Scoped to the whole group
                                        assistant.assignment_scopes = [{
                                            'scope_type': 'group',
                                            'scope_id': group.id,
                                            'group_id': group.id,
                                            'classes': allowed_classes,
                                            'sections': allowed_sections,
                                            'branches': [],
                                            'class_sections': _cs,
                                        }]
                                    assistant.save(update_fields=['assignment_scopes'])
                            existing_emails.add(email)
                            existing_usernames.add(email)
                            created_assistants.append({'Name': name, 'Email': email, 'Password': password})

            if not created_assistants:
                return ServiceResult(success=False, message="No assistants were generated.")

            # Generate Excel using openpyxl directly
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Assistants"
            ws.append(["Name", "Email", "Password"])
            for assistant in created_assistants:
                ws.append([assistant["Name"], assistant["Email"], assistant["Password"]])
            buffer = io.BytesIO()
            wb.save(buffer)
            buffer.seek(0)

            return ServiceResult(success=True, data={'buffer': buffer, 'count': len(created_assistants)})
        except Exception as e:
            return cls._unexpected_error_result('auto_create_assistants', e)
