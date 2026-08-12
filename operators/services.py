"""
Operators Services Module — SINGLE AUTHORITY for operator mutations.

Handles:
- Operator creation by Super Admin
- Permission assignment using Django Groups & Permissions
- Client assignment (many-to-many)
- Client scoping for data access
- Access control enforcement
"""
import logging
from functools import wraps
from typing import Dict, Any, Optional, List

from accounts.services import normalize_password_input
logger = logging.getLogger(__name__)


def _unexpected_error_response(action: str, exc: Exception) -> Dict[str, Any]:
    """Return safe error payload while logging full details server-side."""
    logger.exception('%s failed: %s', action, exc)
    return {'success': False, 'error': 'An unexpected error occurred. Please try again.'}

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import QuerySet, Count, Q

from core.models import User
from client.models import Client
from operators.models import Operator
from core.services.permission_service import PermissionService
from core.utils.email_utils import generate_secure_password, send_welcome_email
from core.models import EmailLog


# =============================================================================
# OPERATOR PERMISSION DEFINITIONS
# =============================================================================

# Permissions that can be assigned to Operators (maps to Django permission codenames)
OPERATOR_PERMISSIONS = {
    # Client Management
    'can_view_clients': 'Can access Clients page',
    'can_add_clients': 'Can create new Client',
    'can_edit_clients': 'Can modify Client details',
    'can_delete_clients': 'Can remove Client',
    'can_toggle_client_status': 'Can toggle Client active status',
    
    # ID Card Data Management
    'can_view_idcard_data': 'Can access Card data',
    'can_add_idcard_data': 'Can add new Card entry',
    'can_edit_idcard_data': 'Can edit Card data',
    'can_delete_idcard_data': 'Can delete Card entry',
    'can_verify_idcard': 'Can verify Card data',
    'can_approve_idcard': 'Can approve Card status',
    'can_view_approved_list': 'Can view Approved List',
    'can_view_download_list': 'Can view Download List',
    
    # ID Card Settings
    'can_view_idcard_settings': 'Can view Template list',
    'can_add_idcard_settings': 'Can create new Template',
    'can_edit_idcard_settings': 'Can modify Template settings',
    'can_delete_idcard_settings': 'Can remove Template',
    
    # Image Management
    'can_upload_images': 'Can upload Card photos',
    'can_reupload_images': 'Can replace Card photos',
    
    # Bulk Operations
    'can_bulk_upload': 'Can use Excel / ZIP bulk upload',
    'can_bulk_download': 'Can download Cards as ZIP',
    
    # Exports
    'can_export_data': 'Can export data (Excel / Word / PDF)',
    'can_download_cards': 'Can download rendered Card images',
    
    # Workflow
    'can_view_workflow': 'Can view workflow dashboard',
    'can_manage_workflow': 'Can manage workflow settings',
}

# Operator Django Group name
OPERATOR_GROUP = 'operator_group'

# Map Django permission codenames to Operator perm_ fields
CODENAME_TO_OPERATOR_PERMS = {
    'can_view_clients': ['perm_idcard_client_list', 'perm_manage_client_staff'],
    'can_view_idcard_settings': ['perm_idcard_setting_list'],
    'can_add_idcard_settings': ['perm_idcard_setting_add'],
    'can_edit_idcard_settings': ['perm_idcard_setting_edit', 'perm_idcard_setting_status'],
    'can_delete_idcard_settings': ['perm_idcard_setting_delete'],
    'can_view_idcard_data': [
        'perm_idcard_pending_list', 'perm_idcard_verified_list', 'perm_idcard_pool_list',
        'perm_idcard_reprint_list', 'perm_reprint_request_list', 'perm_idcard_info',
        'perm_idcard_retrieve', 'perm_mobile_app'
    ],
    'can_view_approved_list': ['perm_idcard_approved_list', 'perm_confirmed_list'],
    'can_view_download_list': ['perm_idcard_download_list'],
    'can_add_idcard_data': ['perm_idcard_add'],
    'can_edit_idcard_data': ['perm_idcard_edit', 'perm_idcard_updated_at', 'perm_idcard_clear_pending_path', 'perm_idcard_upgrade_all'],
    'can_delete_idcard_data': ['perm_idcard_delete', 'perm_idcard_delete_from_pool'],
    'can_approve_idcard': ['perm_idcard_approve'],
    'can_verify_idcard': ['perm_idcard_verify'],
    'can_upload_images': ['perm_reupload_idcard_image'],
    'can_reupload_images': ['perm_reupload_idcard_image'],
    'can_bulk_upload': ['perm_idcard_bulk_upload', 'perm_idcard_bulk_reupload'],
    'can_bulk_download': [
        'perm_idcard_bulk_download', 'perm_idcard_download_image_rename_mode',
        'perm_idcard_download_image_generate_mode'
    ],
    'can_view_workflow': ['perm_manage_panel_backup', 'perm_manage_panel_email'],
}



# =============================================================================
# OPERATOR PERMISSION SERVICE
# =============================================================================

class OperatorPermissionService:
    """
    Service for managing Django Groups & Permissions for Operators.
    """
    
    @classmethod
    def ensure_permissions_exist(cls) -> None:
        """
        Ensure all operator permissions exist in the database.
        Creates them if they don't exist.
        """
        content_type = ContentType.objects.get_for_model(User)
        
        for codename, name in OPERATOR_PERMISSIONS.items():
            Permission.objects.get_or_create(
                codename=codename,
                content_type=content_type,
                defaults={'name': name}
            )
    
    @classmethod
    def get_or_create_operator_group(cls) -> Group:
        """
        Get or create the Operator Django Group.
        """
        cls.ensure_permissions_exist()
        group, _created = Group.objects.get_or_create(name=OPERATOR_GROUP)
        return group
    
    @classmethod
    def get_assignable_permissions(cls) -> List[Dict[str, Any]]:
        """
        Get list of permissions that can be assigned to operators.
        """
        cls.ensure_permissions_exist()
        
        content_type = ContentType.objects.get_for_model(User)
        permissions = Permission.objects.filter(
            codename__in=OPERATOR_PERMISSIONS.keys(),
            content_type=content_type
        )
        
        return [
            {
                'id': p.pk,
                'codename': p.codename,
                'name': p.name,
                'description': OPERATOR_PERMISSIONS.get(p.codename, ''),
            }
            for p in permissions
        ]
    
    @classmethod
    def assign_permissions_to_operator(
        cls,
        operator_user: User,
        permission_codenames: List[str],
        perm_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Assign specific permissions to an operator user.
        """
        try:
            cls.ensure_permissions_exist()
            
            # Validate codenames
            valid_codenames = set(OPERATOR_PERMISSIONS.keys())
            requested = set(permission_codenames)
            invalid = requested - valid_codenames
            
            if invalid:
                return {
                    'success': False,
                    'error': f"Invalid permissions: {', '.join(invalid)}"
                }
            
            content_type = ContentType.objects.get_for_model(User)

            # Clear only this user's direct User-content_type permissions.
            existing_user_perms = list(
                operator_user.user_permissions.filter(content_type=content_type)
            )
            if existing_user_perms:
                operator_user.user_permissions.remove(*existing_user_perms)
            
            # Add new permissions
            permissions = list(Permission.objects.filter(
                codename__in=permission_codenames,
                content_type=content_type
            ))
            if permissions:
                operator_user.user_permissions.add(*permissions)
            
            # Update BooleanFields on Operator profile
            profile = getattr(operator_user, 'operator_profile', None)
            if profile:
                operator_fields = [f.name for f in Operator._meta.fields if f.name.startswith('perm_')]
                for field_name in operator_fields:
                    if perm_keys is not None:
                        setattr(profile, field_name, field_name in perm_keys)
                    else:
                        is_granted = False
                        for codename in permission_codenames:
                            if field_name in CODENAME_TO_OPERATOR_PERMS.get(codename, []):
                                is_granted = True
                                break
                        setattr(profile, field_name, is_granted)
                profile.save()
            
            return {
                'success': True,
                'assigned_count': len(permissions)
            }
            
        except Exception as e:
            return _unexpected_error_response('OperatorPermissionService.assign_permissions_to_operator', e)
    
    @classmethod
    def get_user_permissions(cls, user: User) -> List[str]:
        """
        Get all permission codenames for an operator user.
        """
        if not user.is_authenticated:
            return []
        
        # Get permissions that match our defined ones
        user_perms = user.get_all_permissions()
        operator_perms = []
        
        for perm in user_perms:
            if '.' in perm:
                codename = perm.split('.')[-1]
            else:
                codename = perm
            
            if codename in OPERATOR_PERMISSIONS:
                operator_perms.append(codename)
        
        return operator_perms


# =============================================================================
# OPERATOR CREATION SERVICE
# =============================================================================

class OperatorCreationService:
    """
    Service for creating and managing Operator members.
    Only accessible by Super Admin (super_admin/superuser).
    """
    
    @classmethod
    def create_operator(
        cls,
        created_by: User,
        first_name: str,
        last_name: str,
        email: str,
        phone: str = '',
        designation: str = 'Operator',
        department: str = '',
        assigned_client_ids: Optional[List[int]] = None,
        permission_codenames: Optional[List[str]] = None,
        password: str = '',
        perm_keys: Optional[List[str]] = None,
        is_active: bool = False,
    ) -> Dict[str, Any]:
        """
        Create a new operator member.
        """
        try:
            normalized_email = (email or '').strip().lower()

            if not normalized_email:
                return {
                    'success': False,
                    'error': 'Email is required'
                }

            # Verify creator is super admin
            if created_by is not None and not PermissionService.is_super_admin(created_by):
                return {
                    'success': False,
                    'error': 'Only Super Admin can create operators'
                }
            
            # Check if email already exists
            if User.objects.filter(email__iexact=normalized_email).exists():
                return {
                    'success': False,
                    'error': 'A user with this email already exists'
                }
            
            with transaction.atomic():
                # Universal password normalization
                if password and password.strip():
                    final_password = normalize_password_input(password)
                elif phone:
                    final_password = normalize_password_input(phone)
                else:
                    final_password = generate_secure_password()
                
                # Create User
                user = User.objects.create_user(
                    username=normalized_email,
                    email=normalized_email,
                    password=final_password,
                    first_name=first_name,
                    last_name=last_name,
                    role='operator',
                    phone=phone,
                    is_active=is_active,
                )
                
                # Build profile kwargs
                profile_kwargs = {
                    'user': user,
                    'designation': designation,
                    'department': department,
                }
                
                # Add permissions
                operator_fields = [f.name for f in Operator._meta.fields if f.name.startswith('perm_')]
                for field_name in operator_fields:
                    if perm_keys is not None:
                        profile_kwargs[field_name] = field_name in perm_keys
                    else:
                        is_granted = False
                        if permission_codenames:
                            for codename in permission_codenames:
                                if field_name in CODENAME_TO_OPERATOR_PERMS.get(codename, []):
                                    is_granted = True
                                    break
                        profile_kwargs[field_name] = is_granted
                
                operator = Operator.objects.create(**profile_kwargs)
                
                # Assign clients
                if assigned_client_ids:
                    clients = Client.objects.filter(id__in=assigned_client_ids)
                    operator.assigned_clients.set(clients)
                
                # Add to operator group
                group = OperatorPermissionService.get_or_create_operator_group()
                user.groups.add(group)
                
                # Assign permissions
                if permission_codenames is not None or perm_keys is not None:
                    perm_result = OperatorPermissionService.assign_permissions_to_operator(
                        user,
                        permission_codenames or [],
                        perm_keys=perm_keys,
                    )
                    if not perm_result['success']:
                        raise ValueError(perm_result['error'])
                
                # Log email as on_hold
                full_name = f"{first_name} {last_name}".strip()
                email_log = EmailLog.objects.create(
                    recipient_name=full_name,
                    recipient_email=normalized_email,
                    subject='Welcome to Adarsh Admin - Your Account is Ready!',
                    email_type=EmailLog.EMAIL_TYPE_WELCOME,
                    status=EmailLog.STATUS_ON_HOLD,
                )
                
                email_sent = False
                if is_active:
                    _user_pk = user.pk
                    _email = normalized_email
                    def _on_email_success():
                        try:
                            User.objects.filter(pk=_user_pk).update(welcome_email_sent=True)
                            EmailLog.objects.filter(pk=email_log.pk).update(status=EmailLog.STATUS_SENT)
                        except Exception as cb_err:
                            logger.warning('Email success callback failed for %s: %s', _email, cb_err)

                    def _on_email_failure(err_msg):
                        try:
                            EmailLog.objects.filter(pk=email_log.pk).update(status=EmailLog.STATUS_FAILED, error_message=str(err_msg))
                        except Exception as cb_err:
                            logger.warning('Email failure callback failed for %s: %s', _email, cb_err)

                    send_welcome_email(
                        email=normalized_email,
                        name=full_name,
                        password=password or phone or final_password,
                        role='operator',
                        phone=phone,
                        on_success=_on_email_success,
                        on_failure=_on_email_failure,
                    )
                    email_sent = True

                extra = " Welcome email sent." if email_sent else " Welcome email will be sent on first activation."
                return {
                    'success': True,
                    'message': f'Operator "{full_name}" created successfully.' + extra,
                    'operator': {
                        'id': operator.pk,
                        'user_id': operator.user.pk,
                        'name': full_name,
                        'email': normalized_email,
                    },
                    'email_sent': email_sent,
                }
                
        except ValueError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            return _unexpected_error_response('OperatorCreationService.create_operator', e)
    
    @classmethod
    def update_operator(
        cls,
        updated_by: User,
        operator_id: int,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        phone: Optional[str] = None,
        designation: Optional[str] = None,
        department: Optional[str] = None,
        assigned_client_ids: Optional[List[int]] = None,
        permission_codenames: Optional[List[str]] = None,
        perm_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Update an existing operator member.
        """
        try:
            if updated_by is not None and not PermissionService.is_super_admin(updated_by):
                return {
                    'success': False,
                    'error': 'Only Super Admin can update operators'
                }

            with transaction.atomic():
                operator = Operator.objects.select_for_update().filter(
                    id=operator_id
                ).select_related('user').first()

                if not operator:
                    return {'success': False, 'error': 'Operator not found'}

                user = operator.user
                
                # Update user fields
                if first_name is not None:
                    user.first_name = first_name
                if last_name is not None:
                    user.last_name = last_name
                if phone is not None:
                    user.phone = phone
                user.save()
                
                # Update operator fields
                if designation is not None:
                    operator.designation = designation
                if department is not None:
                    operator.department = department
                operator.save()
                
                # Update assigned clients
                if assigned_client_ids is not None:
                    clients = Client.objects.filter(id__in=assigned_client_ids)
                    operator.assigned_clients.set(clients)
                
                # Update permissions
                if permission_codenames is not None or perm_keys is not None:
                    perm_result = OperatorPermissionService.assign_permissions_to_operator(
                        user,
                        permission_codenames or [],
                        perm_keys=perm_keys,
                    )
                    if not perm_result.get('success'):
                        raise ValueError(perm_result.get('error', 'Failed to assign permissions'))
                
                return {
                    'success': True,
                    'message': f'Operator "{user.get_full_name()}" updated successfully',
                }
                
        except ValueError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            return _unexpected_error_response('OperatorCreationService.update_operator', e)
    
    @classmethod
    def delete_operator(cls, deleted_by: User, operator_id: int) -> Dict[str, Any]:
        """
        Delete an operator member.
        """
        try:
            if deleted_by is not None and not PermissionService.is_super_admin(deleted_by):
                return {
                    'success': False,
                    'error': 'Only Super Admin can delete operators'
                }
            
            operator = Operator.objects.filter(
                id=operator_id
            ).select_related('user').first()
            
            if not operator:
                return {'success': False, 'error': 'Operator not found'}
            
            name = operator.user.get_full_name()
            user = operator.user
            
            # Delete operator profile and user atomically
            with transaction.atomic():
                operator.delete()
                user.delete()
            
            return {
                'success': True,
                'message': f'Operator "{name}" deleted successfully',
                'data': {'name': name},
            }
            
        except Exception as e:
            return _unexpected_error_response('OperatorCreationService.delete_operator', e)
    
    @classmethod
    def toggle_status(cls, toggled_by: User, operator_id: int) -> Dict[str, Any]:
        """
        Toggle operator active/inactive status.
        """
        try:
            if toggled_by is not None and not PermissionService.is_super_admin(toggled_by):
                return {
                    'success': False,
                    'error': 'Only Super Admin can toggle operator status'
                }

            send_welcome = False
            welcome_info = {}
            welcome_user_id = None

            with transaction.atomic():
                operator = Operator.objects.select_for_update().select_related('user').filter(
                    id=operator_id
                ).first()

                if not operator:
                    return {'success': False, 'error': 'Operator not found'}

                user = operator.user
                is_first_activation = not user.is_active and not user.welcome_email_sent
                user.is_active = not user.is_active

                if user.is_active and is_first_activation:
                    phone_value = (user.phone or '').strip()
                    has_usable_password = bool(user.has_usable_password())
                    normalized_phone_pw = normalize_password_input(phone_value)
                    
                    can_reuse_phone_password = (
                        has_usable_password and bool(phone_value) and (
                            user.check_password(phone_value) or 
                            user.check_password(normalized_phone_pw)
                        )
                    )

                    credential_password = ''
                    if can_reuse_phone_password:
                        credential_password = normalized_phone_pw
                        if not user.check_password(credential_password):
                            user.set_password(credential_password)
                    elif has_usable_password:
                        credential_password = '[Preserved Custom Password]'
                    elif normalized_phone_pw:
                        user.set_password(normalized_phone_pw)
                        credential_password = normalized_phone_pw
                    else:
                        credential_password = generate_secure_password()
                        user.set_password(credential_password)

                    user.save(update_fields=['is_active', 'password'])
                    send_welcome = True
                    welcome_user_id = user.pk
                    welcome_info = {
                        'full_name': user.get_full_name(),
                        'email': user.email,
                        'password': credential_password,
                        'phone': user.phone or '',
                    }
                else:
                    user.save(update_fields=['is_active'])

            if send_welcome:
                _user_pk = welcome_user_id
                _email = welcome_info['email']

                def _on_email_success():
                    try:
                        User.objects.filter(pk=_user_pk).update(welcome_email_sent=True)
                        EmailLog.objects.filter(
                            recipient_email=_email,
                            email_type=EmailLog.EMAIL_TYPE_WELCOME,
                            status=EmailLog.STATUS_ON_HOLD,
                        ).update(status=EmailLog.STATUS_SENT)
                    except Exception as cb_err:
                        logger.warning('Email success callback failed for %s: %s', _email, cb_err)

                def _on_email_failure(err_msg):
                    try:
                        EmailLog.objects.filter(
                            recipient_email=_email,
                            email_type=EmailLog.EMAIL_TYPE_WELCOME,
                            status=EmailLog.STATUS_ON_HOLD,
                        ).update(status=EmailLog.STATUS_FAILED, error_message=str(err_msg))
                    except Exception as cb_err:
                        logger.warning('Email failure callback failed for %s: %s', _email, cb_err)

                send_welcome_email(
                    email=welcome_info['email'],
                    name=welcome_info['full_name'],
                    password=welcome_info['password'],
                    role='operator',
                    phone=welcome_info['phone'],
                    on_success=_on_email_success,
                    on_failure=_on_email_failure,
                )

            status_word = 'activated' if user.is_active else 'deactivated'
            extra = ' Welcome email queued for delivery.' if send_welcome else ''
            return {
                'success': True,
                'message': f'Operator "{user.get_full_name()}" {status_word}.{extra}',
                'is_active': user.is_active,
                'status': 'active' if user.is_active else 'inactive',
                'status_display': 'Active' if user.is_active else 'Inactive',
                'data': {
                    'is_active': user.is_active,
                    'status': 'active' if user.is_active else 'inactive',
                    'status_display': 'Active' if user.is_active else 'Inactive',
                    'name': user.get_full_name() or user.username,
                },
            }

        except Exception as e:
            return _unexpected_error_response('OperatorCreationService.toggle_status', e)
    
    @classmethod
    def reset_password(cls, reset_by: User, operator_id: int) -> Dict[str, Any]:
        """
        Reset operator password and send email.
        """
        try:
            if reset_by is not None and not PermissionService.is_super_admin(reset_by):
                return {
                    'success': False,
                    'error': 'Only Super Admin can reset operator password'
                }
            
            operator = Operator.objects.filter(
                id=operator_id
            ).select_related('user').first()
            
            if not operator:
                return {'success': False, 'error': 'Operator not found'}
            
            user = operator.user
            new_password = generate_secure_password()
            user.set_password(new_password)
            user.save()
            
            # Send email with new password
            success, msg = send_welcome_email(
                email=user.email,
                name=user.get_full_name(),
                password=new_password,
                role='operator',
                phone=getattr(user, 'phone', ''),
                email_variant='temp_password',
            )

            # Log password reset
            try:
                from core.services.activity_service import ActivityService
                last_active_str = ActivityService._format_last_active(user)
                ActivityService.log(
                    'staff_password_reset',
                    f'Password reset for Operator "{user.get_full_name()}" by admin ({last_active_str})',
                    target_model='Operator',
                    target_id=operator.pk,
                    target_name=user.get_full_name(),
                    user=reset_by,
                )
            except Exception:
                logger.exception('Failed to log operator password reset')

            return {
                'success': True,
                'message': f'Password reset for "{user.get_full_name()}"',
                'email_sent': success,
            }
            
        except Exception as e:
            return _unexpected_error_response('OperatorCreationService.reset_password', e)

    @classmethod
    def set_temp_password(cls, profile_id: int, new_password: str, is_assistant: bool = False, request=None) -> Dict[str, Any]:
        """
        Set a temporary password for an operator or assistant user.
        Sends a welcome email with the new credentials so the user knows their password.
        """
        try:
            if is_assistant:
                from assistants.models import Assistant
                profile = Assistant.objects.filter(id=profile_id).select_related('user').first()
                role_label = 'assistant'
            else:
                profile = Operator.objects.filter(id=profile_id).select_related('user').first()
                role_label = 'operator'

            if not profile:
                return {'success': False, 'error': f"{role_label.capitalize()} not found"}

            user = profile.user

            if not new_password or not new_password.strip():
                return {'success': False, 'error': 'Password cannot be empty'}

            # Universal password normalization (phone formats -> digits, text -> intact)
            normalized_password = normalize_password_input(new_password)

            user.set_password(normalized_password)
            user.save(update_fields=['password'])

            # Send welcome email with the new temporary password
            email_sent = False
            try:
                email_sent, _ = send_welcome_email(
                    name=user.get_full_name(),
                    email=user.email,
                    password=new_password,
                    role=role_label,
                    phone=user.phone or '',
                    request=request,
                    email_variant='temp_password',
                )
                EmailLog.objects.create(
                    recipient_name=user.get_full_name(),
                    recipient_email=user.email,
                    subject='Temporary password update',
                    email_type=EmailLog.EMAIL_TYPE_WELCOME,
                    status=EmailLog.STATUS_SENT if email_sent else EmailLog.STATUS_FAILED,
                )
            except Exception as e:
                logger.warning('Failed to send temp password email: %s', e)

            # Log password reset
            try:
                from core.services.activity_service import ActivityService
                last_active_str = ActivityService._format_last_active(user)
                ActivityService.log(
                    'staff_password_reset',
                    f'Temporary password set for {role_label.capitalize()} "{user.get_full_name()}" ({last_active_str})',
                    request=request,
                    target_model=role_label.capitalize(),
                    target_id=profile.pk,
                    target_name=user.get_full_name(),
                )
            except Exception:
                logger.exception('Failed to log staff temp password reset')

            return {
                'success': True,
                'message': f'Temporary password updated successfully for {role_label} "{user.get_full_name()}".',
                'email_sent': email_sent
            }
        except Exception as e:
            return _unexpected_error_response('OperatorCreationService.set_temp_password', e)
    
    @classmethod
    def list_operators(cls, user: User) -> Dict[str, Any]:
        """
        List all operators.
        """
        try:
            if user is not None and not PermissionService.is_super_admin(user):
                return {
                    'success': False,
                    'error': 'Only Super Admin can view operators list'
                }
            
            operator_list = list(Operator.objects.all().select_related('user').prefetch_related('assigned_clients'))

            user_ids = [o.user_id for o in operator_list]
            perm_counts_by_user = {}
            if user_ids:
                content_type = ContentType.objects.get_for_model(User)
                perm_counts_by_user = dict(
                    User.objects.filter(id__in=user_ids)
                    .annotate(
                        operator_perm_count=Count(
                            'user_permissions',
                            filter=Q(
                                user_permissions__content_type=content_type,
                                user_permissions__codename__in=OPERATOR_PERMISSIONS.keys(),
                            ),
                            distinct=True,
                        )
                    )
                    .values_list('id', 'operator_perm_count')
                )
            
            data = []
            for operator in operator_list:
                assigned = list(operator.assigned_clients.all())
                data.append({
                    'id': operator.pk,
                    'user_id': operator.user.pk,
                    'name': operator.user.get_full_name(),
                    'email': operator.user.email,
                    'phone': operator.user.phone or '',
                    'designation': operator.designation or '',
                    'department': operator.department or '',
                    'role_title': 'Operator',
                    'assigned_organisations': [
                        {'id': c.id, 'name': c.name, 'organisation_id': c.id, 'organisation_name': c.name}
                        for c in assigned
                    ],
                    'assigned_clients': [
                        {'id': c.id, 'name': c.name, 'organisation_id': c.id, 'organisation_name': c.name}
                        for c in assigned
                    ],
                    'assigned_organisations_count': len(assigned),
                    'assigned_clients_count': len(assigned),
                    'permissions_count': perm_counts_by_user.get(operator.user_id, 0),
                    'created_at': operator.created_at.isoformat(),
                })
            
            return {
                'success': True,
                'operators': data,
                'count': len(data),
            }
            
        except Exception as e:
            return _unexpected_error_response('OperatorCreationService.list_operators', e)
    
    @classmethod
    def get_operator_detail(cls, user: User, operator_id: int) -> Dict[str, Any]:
        """
        Get detailed info for a single operator.
        """
        try:
            if user is not None and not PermissionService.is_super_admin(user):
                return {
                    'success': False,
                    'error': 'Only Super Admin can view operator details'
                }
            
            operator = Operator.objects.filter(
                id=operator_id
            ).select_related('user').prefetch_related('assigned_clients').first()
            
            if not operator:
                return {'success': False, 'error': 'Operator not found'}
            
            permissions = OperatorPermissionService.get_user_permissions(operator.user)
            
            return {
                'success': True,
                'operator': {
                    'id': operator.pk,
                    'user_id': operator.user.pk,
                    'name': operator.user.get_full_name() or operator.user.username,
                    'first_name': operator.user.first_name,
                    'last_name': operator.user.last_name,
                    'email': operator.user.email,
                    'phone': operator.user.phone or '',
                    'designation': operator.designation or '',
                    'department': operator.department or '',
                    'is_active': operator.user.is_active,
                    'status': 'active' if operator.user.is_active else 'inactive',
                    'assigned_clients': [
                        {'id': c.id, 'name': c.name}
                        for c in operator.assigned_clients.all()
                    ],
                    'assigned_client_ids': [c.id for c in operator.assigned_clients.all()],
                    'permissions': permissions,
                    'created_at': operator.created_at.isoformat(),
                    'updated_at': operator.updated_at.isoformat(),
                }
            }
            
        except Exception as e:
            return _unexpected_error_response('OperatorCreationService.get_operator_detail', e)


# =============================================================================
# OPERATOR CLIENT SCOPING SERVICE
# =============================================================================

class OperatorClientScopingService:
    """
    Service for enforcing client-based data scoping for operators.
    """
    
    @classmethod
    def get_accessible_clients(cls, user: User) -> QuerySet:
        """Get QuerySet of clients accessible to the user."""
        if not user.is_authenticated:
            return Client.objects.none()
        if PermissionService.is_super_admin(user):
            return Client.objects.all()
        if PermissionService.is_operator(user):
            operator = getattr(user, 'operator_profile', None)
            if operator:
                return operator.assigned_clients.all()
        return Client.objects.none()
    
    @classmethod
    def get_accessible_client_ids(cls, user: User) -> List[int]:
        """Get list of accessible client IDs for the user."""
        return PermissionService.get_accessible_client_ids(user)
    
    @classmethod
    def can_access_client(cls, user: User, client_id: int) -> bool:
        """Check if user can access a specific client."""
        return PermissionService.can_access_client(user, client_id)
    
    @classmethod
    def filter_by_accessible_clients(cls, user: User, queryset: QuerySet, client_field: str = 'client') -> QuerySet:
        """Filter queryset to only include records for accessible clients."""
        if not user.is_authenticated:
            return queryset.none()
        if PermissionService.is_super_admin(user):
            return queryset
        if PermissionService.is_operator(user):
            accessible_ids = PermissionService.get_accessible_client_ids(user)
            filter_kwargs = {f'{client_field}__id__in': accessible_ids}
            return queryset.filter(**filter_kwargs)
        return queryset.none()
    
    @classmethod
    def get_scope_context(cls, user: User) -> Dict[str, Any]:
        """Get client scoping context for templates/views."""
        accessible = cls.get_accessible_clients(user)
        return {
            'is_shop_owner': PermissionService.is_super_admin(user),
            'is_operator': PermissionService.is_operator(user),
            'accessible_clients': list(accessible.values('id', 'name')),
            'accessible_client_ids': list(accessible.values_list('id', flat=True)),
            'has_client_access': accessible.exists(),
        }


# =============================================================================
# PERMISSION CHECK DECORATORS
# =============================================================================

def check_client_access(client_id_param: str = 'client_id'):
    """
    Decorator to check if user can access a specific client.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            client_id = kwargs.get(client_id_param) or request.GET.get(client_id_param) or request.POST.get(client_id_param)
            
            if client_id:
                try:
                    client_id = int(client_id)
                except (TypeError, ValueError):
                    return JsonResponse({'success': False, 'error': 'Invalid client ID'}, status=400)
                
                if not PermissionService.can_access_client(request.user, client_id):
                    return JsonResponse({
                        'success': False,
                        'error': 'You do not have access to this client'
                    }, status=403)
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def check_permission(codename: str):
    """
    Decorator to check if user has a specific Django permission.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            
            if not user.is_authenticated:
                return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)
            
            if PermissionService.is_super_admin(user):
                return view_func(request, *args, **kwargs)
            
            if not user.has_perm(f'core.{codename}'):
                return JsonResponse({
                    'success': False,
                    'error': f'Permission denied: {codename}'
                }, status=403)
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator
