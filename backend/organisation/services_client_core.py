"""
Client Service Module
Contains: Organisation CRUD operations, serialization
"""
import secrets
from typing import Dict, Any, Optional, List

from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils.timezone import localtime

from core.models import User, EmailLog
from organisation.models import Organisation
from assistants.models import Assistant
from core.utils import send_welcome_email
from core.services.base import BaseService, ServiceResult
from core.services.cache_version_service import CacheVersionService
from accounts.services import normalize_password_input

import logging
logger = logging.getLogger(__name__)


class OrganisationService(BaseService):
    """
    Service for Client CRUD operations.
    
    Usage:
        # Create
        result = ClientService.create(data, request)
        if result.success:
            client_dict = result.data['client']
        
        # Get
        result = ClientService.get(client_id)
        
        # Update
        result = ClientService.update(client_id, data)
        
        # Delete
        result = ClientService.delete(client_id)
    """
    
    # All permission field names for Client model
    PERMISSION_FIELDS = [
        # ID Card Client List
        'perm_idcard_client_list',
        # ID Card Setting Permissions
        'perm_idcard_setting_list', 'perm_idcard_setting_add', 
        'perm_idcard_setting_edit', 'perm_idcard_setting_delete', 
        'perm_idcard_setting_status',
        # ID Card List Permissions
        'perm_idcard_pending_list', 'perm_idcard_verified_list', 
        'perm_idcard_pool_list', 'perm_idcard_approved_list', 
        'perm_idcard_download_list', 'perm_reprint_request_list',
        'perm_confirmed_list',
        # ID Card Action Permissions (work in Pending and Verified lists only)
        'perm_idcard_add', 'perm_idcard_edit', 'perm_idcard_delete',
        'perm_idcard_info', 'perm_idcard_approve', 'perm_idcard_verify',
        'perm_idcard_reprint_list',
        'perm_idcard_updated_at',
        'perm_idcard_delete_from_pool',
        'perm_idcard_retrieve',
        # ID Card Bulk Action Permissions (work across all lists)
        'perm_idcard_bulk_upload', 'perm_idcard_bulk_download',
        'perm_idcard_download_image_rename_mode', 'perm_idcard_download_image_generate_mode',
        'perm_delete_all_idcard',
        'perm_idcard_upgrade_all',
        # Mobile App
        'perm_mobile_app',
        # Account Security
        'perm_set_temp_password',
    ]
    
    @classmethod
    def serialize(cls, client: Organisation, include_permissions: bool = True) -> Dict[str, Any]:
        """Serialize Client/Organisation instance to dict"""
        prime_manager_name = (client.user.get_full_name() or client.user.username) if client.user else ''
        data = {
            'id': client.id,
            'organisation_id': client.id,
            'name': client.name,
            'organisation_name': client.name,
            'prime_manager': prime_manager_name,
            'prime_manager_id': client.user_id if client.user_id else None,
            'role_title': 'Guest Prime Manager' if client.is_guest else 'Prime Manager',
            'is_guest': bool(getattr(client, 'is_guest', False)),
            'email': cls._public_email(client.user.email) if client.user else '',
            'phone': (client.user.phone or '') if client.user else '',
            'city': client.city or '',
            'state': client.state or '',
            'pincode': client.pincode or '',
            'status': client.status,
            # Keep photo_url/logo_url keys as empty strings for backward compatibility.
            'photo_url': '',
            'logo_url': '',
            'icon': client.icon or '',
            'created_at': localtime(client.created_at).strftime('%d-%m-%Y %H:%M'),
            'updated_at': localtime(client.updated_at).strftime('%d-%m-%Y %H:%M'),
        }
        
        if include_permissions:
            for perm in cls.PERMISSION_FIELDS:
                data[perm] = getattr(client, perm, False)
        
        return data

    @staticmethod
    def _public_email(email: str) -> str:
        """Hide internal placeholder emails from API payloads."""
        value = (email or '').strip()
        return '' if value.endswith('@noemail.local') else value

    @staticmethod
    def _has_real_email(email: str) -> bool:
        """Return True when the address is usable for outbound SMTP delivery."""
        value = (email or '').strip().lower()
        return bool(value and '@' in value and not value.endswith('@noemail.local'))

    @staticmethod
    def _unexpected_error_result(action: str, exc: Exception) -> ServiceResult:
        """Return a safe error response while retaining full server-side diagnostics."""
        logger.exception('ClientService.%s failed: %s', action, exc)
        return ServiceResult(success=False, message='An unexpected error occurred. Please try again.')

    @staticmethod
    def _bump_client_cache_versions(client_id: int) -> None:
        try:
            cid = int(client_id)
        except (TypeError, ValueError):
            return

        CacheVersionService.bump('dash_rcu', 'global')
        CacheVersionService.bump('dash_team_overview', 'global')
        CacheVersionService.bump('client_dash_counts', f'client:{cid}')
        CacheVersionService.bump('client_staff', f'client:{cid}')
        CacheVersionService.bump('client_messages_drawer_client', f'client:{cid}')
    
    @classmethod
    def create(cls, data: Dict[str, Any], request=None) -> ServiceResult:
        """
        Create a new client with associated user account.
        
        Args:
          data: Dict with client data (name, email, phone, address, etc.)
          request: HTTP request (for email context)
        
        Returns:
          ServiceResult with client data
        """
        try:
            name = str(data.get('name') or '').strip()
            if not name:
                return ServiceResult(success=False, message='Name is required')

            role = str(data.get('role', 'client') or 'client').strip().lower()
            if role not in {'client', 'guest_prime_manager'}:
                role = 'prime_manager'

            username_input = str(data.get('username') or '').strip()
            raw_email = str(data.get('email') or '').strip().lower()
            email_was_provided = bool(raw_email)
            if not raw_email:
                if role != 'guest_prime_manager':
                    return ServiceResult(success=False, message='Email is required')
                username_seed = username_input or name or 'guest'
                safe_username = ''.join(ch if ch.isalnum() or ch in ('-', '_', '.') else '_' for ch in username_seed.lower()).strip('._-') or 'guest'
                raw_email = f'guest.{safe_username}.{secrets.token_hex(4)}@noemail.local'

            if email_was_provided and User.objects.filter(email__iexact=raw_email).exists():
                return ServiceResult(
                    success=False,
                    message='A user with this email already exists'
                )

            email = raw_email

            if role == 'guest_prime_manager' and username_input:
                username = username_input.lower().replace('.', '_')
            else:
                username = email.split('@')[0].lower().replace('.', '_')

            if not username:
                username = f'client_{secrets.token_hex(4)}'

            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            name_parts = name.split() if name else []
            
            # Password policy:
            # - if custom password is provided, use it
            # - otherwise phone number is required and used as password
            phone = str(data.get('phone') or '').strip()
            password = str(data.get('password') or '').strip()
            if not password:
                if phone:
                    # Universal password normalization (phone formats -> digits)
                    password = normalize_password_input(phone)
                    if not password:
                        return ServiceResult(success=False, message='Phone number must contain digits to be used as a password')
                else:
                    return ServiceResult(
                        success=False,
                        message='Phone number is required when custom password is not provided'
                    )
            else:
                # Normalize custom password input
                password = normalize_password_input(password)
            
            if not email:
                return ServiceResult(success=False, message='Email is required')

            # Guest users should come up active by default so they can sign in immediately.
            create_as_active = cls.parse_bool(data.get('is_active', role == 'guest_prime_manager'))
            
            with transaction.atomic():

                # Create user — honour admin's active/inactive choice
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=name_parts[0] if name_parts else '',
                    last_name=' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
                    phone=data.get('phone', ''),
                    role=role,
                    is_active=create_as_active,
                )

                # Build client kwargs
                client_kwargs = {
                    'user': user,
                    'name': name,
                    'is_guest': role == 'guest_prime_manager',
                    'city': data.get('city', ''),
                    'state': data.get('state', ''),
                    'pincode': data.get('pincode', ''),
                    'icon': data.get('icon', 'fa-solid fa-building'),
                    'status': 'active' if create_as_active else 'inactive',
                }

                # Default permissions set to Auto-ON for new clients
                DEFAULT_ACTIVE_PERMISSIONS = {
                    'perm_idcard_pending_list', 'perm_idcard_verified_list', 'perm_idcard_approved_list',
                    'perm_idcard_download_list', 'perm_idcard_pool_list', 'perm_idcard_add', 'perm_idcard_edit',
                    'perm_idcard_info', 'perm_idcard_delete', 'perm_idcard_approve', 'perm_idcard_verify',
                    'perm_idcard_updated_at', 'perm_idcard_retrieve', 'perm_idcard_bulk_download',
                    'perm_idcard_client_list', 'perm_set_temp_password'
                }

                # Add permissions
                for perm in cls.PERMISSION_FIELDS:
                    if perm in data:
                        client_kwargs[perm] = cls.parse_bool(data[perm])
                    else:
                        client_kwargs[perm] = (perm in DEFAULT_ACTIVE_PERMISSIONS)

                client = Organisation.objects.create(**client_kwargs)

                # Queue welcome email only when it is actually needed:
                # - active now, a real email exists, and this is not a guest sandbox
                if create_as_active and email_was_provided and role != 'guest_prime_manager':
                    EmailLog.objects.create(
                        recipient_name=name or 'Client',
                        recipient_email=email,
                        subject='Welcome to Adarsh Admin - Your Account is Ready!',
                        email_type=EmailLog.EMAIL_TYPE_WELCOME,
                        status=EmailLog.STATUS_ON_HOLD,
                    )

            # Send welcome email in background thread if created as active.
            # This prevents the API response from being blocked by SMTP.
            if create_as_active and email_was_provided and role != 'guest_prime_manager':
                _user_pk = user.pk
                _email = email
                _name = name
                _full_name = user.get_full_name()
                _phone = phone

                def _on_email_success():
                    User.objects.filter(pk=_user_pk).update(welcome_email_sent=True)
                    EmailLog.objects.filter(
                        recipient_email=_email,
                        email_type=EmailLog.EMAIL_TYPE_WELCOME,
                        status=EmailLog.STATUS_ON_HOLD,
                    ).update(status=EmailLog.STATUS_SENT)

                def _on_email_failure(err_msg):
                    EmailLog.objects.filter(
                        recipient_email=_email,
                        email_type=EmailLog.EMAIL_TYPE_WELCOME,
                        status=EmailLog.STATUS_ON_HOLD,
                    ).update(status=EmailLog.STATUS_FAILED, error_message=err_msg)

                try:
                    send_welcome_email(
                        name=_name or _full_name,
                        email=_email,
                        password=password,
                        role=role,
                        phone=_phone,
                        on_success=_on_email_success,
                        on_failure=_on_email_failure,
                    )
                except Exception as email_err:
                    logger.warning('Welcome email scheduling failed for new active client %s: %s', _email, email_err)
                    _on_email_failure(str(email_err))

            message = 'Client created successfully!'
            if create_as_active:
                if email_was_provided:
                    if role != 'guest_prime_manager':
                        message += ' Welcome email queued for delivery.'
                else:
                    message += ' No email provided, so welcome email was skipped.'
            else:
                message += ' Account is inactive; activate it to allow login with the configured password.'

            return ServiceResult(
                success=True,
                message=message,
                data={
                    'client': cls.serialize(client, include_permissions=False),
                    'email_sent': create_as_active and email_was_provided and role != 'guest_prime_manager',
                }
            )

        except Exception as e:
            return cls._unexpected_error_result('create', e)

    @classmethod
    def create_guest_from_client(cls, client_id: int, request=None) -> ServiceResult:
        """Convert an existing client into a guest sandbox client."""
        try:
            client = get_object_or_404(Organisation.objects.select_related('user'), id=client_id)
            user = client.user

            if client.is_guest or user.role == 'guest_prime_manager':
                return ServiceResult(success=False, message='This account is already a guest user.')

            with transaction.atomic():
                client.is_guest = True
                client.status = 'active'
                user.role = 'guest_prime_manager'
                user.is_active = True
                user.save(update_fields=['role', 'is_active'])
                client.save(update_fields=['is_guest', 'status', 'updated_at'])

            cls._bump_client_cache_versions(client.id)
            return ServiceResult(
                success=True,
                message=f'Client "{client.name}" converted to guest user successfully!',
                data={'client': cls.serialize(client, include_permissions=False)},
            )
        except Exception as e:
            return cls._unexpected_error_result('create_guest_from_client', e)

    @classmethod
    def restore_client_from_guest(cls, client_id: int, request=None) -> ServiceResult:
        """Convert a guest sandbox client back into a normal client."""
        try:
            client = get_object_or_404(Organisation.objects.select_related('user'), id=client_id)
            user = client.user

            if not client.is_guest and user.role != 'guest_prime_manager':
                return ServiceResult(success=False, message='This account is already a normal client.')

            with transaction.atomic():
                client.is_guest = False
                client.status = 'active'
                user.role = 'prime_manager'
                user.is_active = True
                user.save(update_fields=['role', 'is_active'])
                client.save(update_fields=['is_guest', 'status', 'updated_at'])

            cls._bump_client_cache_versions(client.id)
            return ServiceResult(
                success=True,
                message=f'Guest "{client.name}" restored to client successfully!',
                data={'client': cls.serialize(client, include_permissions=False)},
            )
        except Exception as e:
            return cls._unexpected_error_result('restore_client_from_guest', e)
    
    @classmethod
    def get(cls, client_id: int, include_permissions: bool = True) -> ServiceResult:
        """Get a client by ID"""
        try:
            client = get_object_or_404(Organisation.objects.select_related('user'), id=client_id)
            return ServiceResult(
                success=True,
                data={'client': cls.serialize(client, include_permissions)}
            )
        except Exception as e:
            return cls._unexpected_error_result('get', e)
    
    @classmethod
    def update(cls, client_id: int, data: Dict[str, Any]) -> ServiceResult:
        """Update a client"""
        try:
            client = get_object_or_404(Organisation.objects.select_related('user'), id=client_id)
            user = client.user
            
            with transaction.atomic():
                # Update user fields
                if data.get('email'):
                    new_email = str(data['email'] or '').strip().lower()
                    if new_email != user.email.lower():
                        if User.objects.filter(email__iexact=new_email).exclude(id=user.id).exists():
                            return ServiceResult(success=False, message='A user with this email already exists')
                        user.email = new_email
                if data.get('phone'):
                    user.phone = data['phone']
                if data.get('name'):
                    name_parts = data['name'].split()
                    user.first_name = name_parts[0] if name_parts else ''
                    user.last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                user.save()
                
                # Update client fields
                if data.get('name'):
                    client.name = data['name']
                for field in ['city', 'state', 'pincode', 'icon']:
                    if field in data:
                        setattr(client, field, data[field])
                
                # Handle is_active / status change via edit form
                if 'is_active' in data:
                    new_active = cls.parse_bool(data['is_active'])
                    if new_active != user.is_active:
                        user.is_active = new_active
                        client.status = 'active' if new_active else 'inactive'
                        user.save(update_fields=['is_active'])
                        # Cascade deactivation to all client staff
                        if not new_active:
                            cls._cascade_deactivate_staff(client)
                
                # Track revoked permissions for cascade to staff
                revoked_permissions = []
                
                # Update permissions — when ANY perm key is present, set ALL perms
                # (missing keys default to False to prevent stale ON states)
                has_any_perm = any(perm in data for perm in cls.PERMISSION_FIELDS)
                if has_any_perm:
                    for perm in cls.PERMISSION_FIELDS:
                        new_value = cls.parse_bool(data[perm]) if perm in data else False
                        old_value = getattr(client, perm, False)
                        
                        # Track if permission is being revoked
                        if old_value and not new_value:
                            revoked_permissions.append(perm)
                        
                        setattr(client, perm, new_value)
                
                client.save()
                
                # CRITICAL: Cascade revoked permissions to all staff members
                # Client Staff Permission ⊆ Client Permission
                if revoked_permissions:
                    cls._cascade_revoked_permissions(client, revoked_permissions)
            
            # Refresh from DB to return authoritative state
            client.refresh_from_db()
            
            return ServiceResult(
                success=True,
                message='Client updated successfully!',
                data={'client': cls.serialize(client, include_permissions=False)}
            )
            
        except Exception as e:
            return cls._unexpected_error_result('update', e)
    
    @classmethod
    def _cascade_revoked_permissions(cls, client: Organisation, revoked_permissions: List[str]) -> None:
        """
        Cascade revoked permissions to all assistants.
        Enforces: Assistant Permission ⊆ Client Permission
        
        When a client permission is revoked, all assistants must also
        have that permission revoked.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Get all assistants for this client
        client_staff = Assistant.objects.filter(
            organisation=client
        )
        
        if not client_staff.exists():
            return
        
        # Update each assistant
        updated_count = 0
        for staff in client_staff:
            staff_changed = False
            for perm in revoked_permissions:
                # Only update if assistant actually has the permission
                if hasattr(staff, perm) and getattr(staff, perm, False):
                    setattr(staff, perm, False)
                    staff_changed = True
            
            if staff_changed:
                staff.save()
                updated_count += 1
        
        if updated_count > 0:
            logger.info(
                "Permission cascade: Revoked permissions %s from %d assistants of client '%s' (ID: %d)",
                revoked_permissions, updated_count, client.name, client.id
            )
    
    @classmethod
    def delete(cls, client_id: int) -> ServiceResult:
        """Delete a client and associated user (including assistants users)"""
        try:
            client = get_object_or_404(Client, id=client_id)
            user = client.user
            client_name = client.name
            
            # Phase 1: Photo and profile_image fields removed - using avatar placeholder
            
            # Collect assistant User IDs before cascade deletes their Assistant records
            from assistants.models import Assistant as AssistantModel
            staff_user_ids = list(
                AssistantModel.objects.filter(
                    client=client
                ).values_list('user_id', flat=True)
            )

            archived_user_ids = []

            def _retire_user_account(user_obj):
                """Fallback for accounts protected by historical FK records.
                We keep the row but deactivate and anonymize it so client deletion can continue.
                """
                token = secrets.token_hex(3)
                user_obj.is_active = False
                user_obj.username = f'deleted_client_{user_obj.pk}_{token}'
                user_obj.email = f'deleted.client.{user_obj.pk}.{token}@noemail.local'
                user_obj.phone = ''
                user_obj.first_name = 'Deleted'
                user_obj.last_name = 'Client'
                user_obj.save(update_fields=['is_active', 'username', 'email', 'phone', 'first_name', 'last_name'])
                archived_user_ids.append(user_obj.pk)
            
            with transaction.atomic():
                client.delete()   # Cascades Assistant records
                try:
                    user.delete()     # Delete client's own User
                except ProtectedError:
                    _retire_user_account(user)
                # Clean up orphaned assistant User records
                if staff_user_ids:
                    from django.contrib.auth import get_user_model
                    staff_users = get_user_model().objects.filter(id__in=staff_user_ids)
                    for staff_user in staff_users:
                        try:
                            staff_user.delete()
                        except ProtectedError:
                            _retire_user_account(staff_user)

            cls._bump_client_cache_versions(client_id)

            if archived_user_ids:
                logger.warning(
                    'ClientService.delete: Organisation %s deleted but archived protected user accounts: %s',
                    client_id,
                    archived_user_ids,
                )

            return ServiceResult(
                success=True,
                message=f'Client "{client_name}" deleted successfully!'
            )
        except Exception as e:
            return cls._unexpected_error_result('delete', e)
    
    @classmethod
    def toggle_status(cls, client_id: int) -> ServiceResult:
        """Toggle client active/inactive status (atomic to prevent lost toggles).
        On every activation, attempts to send credentials to the client's email.
        """
        try:
            # Collect state needed for email (must be outside atomic for clean email send)
            send_welcome = False
            welcome_email_info = {}
            welcome_user_id = None
            welcome_email_log_id = None
            welcome_email_failed_reason = ''
            welcome_skipped_reason = ''

            with transaction.atomic():
                client = Organisation.objects.select_related('user').select_for_update().get(id=client_id)
                user = client.user
                real_email_available = cls._has_real_email(user.email)
                is_activating = (client.status != 'active')

                if client.status == 'active':
                    # Deactivate
                    client.status = 'inactive'
                    user.is_active = False
                    status_display = 'Inactive'
                    deactivated_staff_count = cls._cascade_deactivate_staff(client)
                    client.save(update_fields=['status', 'updated_at'])
                    user.save(update_fields=['is_active'])
                else:
                    # Activate
                    client.status = 'active'
                    user.is_active = True
                    status_display = 'Active'
                    deactivated_staff_count = 0

                    if is_activating and real_email_available:
                        phone_value = (user.phone or '').strip()
                        has_usable_password = bool(user.has_usable_password())
                        # Universal normalization for checking/setting phone passwords
                        normalized_phone_pw = normalize_password_input(phone_value)
                        
                        can_reuse_phone_password = (
                            has_usable_password and bool(phone_value) and (
                                user.check_password(phone_value) or 
                                user.check_password(normalized_phone_pw)
                            )
                        )
                        email_variant = 'welcome'
                        credential_password = ''

                        if can_reuse_phone_password:
                            # Standardize to normalized format
                            credential_password = normalized_phone_pw
                            if not user.check_password(credential_password):
                                user.set_password(credential_password)
                            user.save(update_fields=['is_active', 'password'])
                        elif has_usable_password:
                            # Preserve any existing custom password configured during client creation.
                            # Do not rotate to a temp password during activation.
                            credential_password = 'Use the password configured by your administrator.'
                            user.save(update_fields=['is_active'])
                        elif normalized_phone_pw:
                            # Legacy recovery: if password became unusable, recover from phone.
                            user.set_password(normalized_phone_pw)
                            credential_password = normalized_phone_pw
                            user.save(update_fields=['is_active', 'password'])
                        else:
                            return ServiceResult(
                                success=False,
                                message='Cannot activate client without a configured password. Set a password first.'
                            )

                        subject = (
                            'Your Temporary Password — Adarsh Admin'
                            if email_variant == 'temp_password'
                            else 'Welcome to Adarsh Admin - Your Account is Ready!'
                        )
                        log = EmailLog.objects.create(
                            recipient_name=client.name or user.get_full_name() or user.username,
                            recipient_email=user.email,
                            subject=subject,
                            email_type=(
                                EmailLog.EMAIL_TYPE_TEMP_PASSWORD
                                if email_variant == 'temp_password'
                                else EmailLog.EMAIL_TYPE_WELCOME
                            ),
                            status=EmailLog.STATUS_ON_HOLD,
                        )

                        send_welcome = True
                        welcome_user_id = user.pk
                        welcome_email_log_id = log.pk
                        welcome_email_info = {
                            'name': Organisation.name or user.get_full_name(),
                            'email': user.email,
                            'password': credential_password,
                            'phone': user.phone or '',
                            'email_variant': email_variant,
                        }
                    else:
                        if is_activating and not real_email_available:
                            welcome_skipped_reason = 'No valid email found for this client, so activation email was skipped.'
                        user.save(update_fields=['is_active'])

                    client.save(update_fields=['status', 'updated_at'])

            # Send welcome email asynchronously after the transaction commits
            if send_welcome:
                _user_pk = welcome_user_id
                _email = welcome_email_info['email']
                _log_id = welcome_email_log_id

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
                        name=welcome_email_info['name'],
                        email=welcome_email_info['email'],
                        password=welcome_email_info['password'],
                        role='client',
                        phone=welcome_email_info['phone'],
                        email_variant=welcome_email_info['email_variant'],
                        on_success=_on_email_success,
                        on_failure=_on_email_failure,
                    )
                except Exception as email_err:
                    queued = False
                    queue_message = str(email_err)

                if not queued:
                    welcome_email_failed_reason = queue_message or 'Failed to queue activation email.'
                    _on_email_failure(welcome_email_failed_reason)

            message = f'Client status changed to {status_display}!'
            if send_welcome:
                if welcome_email_failed_reason:
                    message += f' Activation email could not be sent: {welcome_email_failed_reason}'
                else:
                    message += ' Activation email queued for delivery.'
            elif welcome_skipped_reason:
                message += f' {welcome_skipped_reason}'
            if deactivated_staff_count > 0:
                message += f' ({deactivated_staff_count} staff members also deactivated)'
                logger.info(
                    'Client deactivation cascade: Deactivated %d staff members of client \'%s\' (ID: %d)',
                    deactivated_staff_count, client.name, client.id
                )

            return ServiceResult(
                success=True,
                message=message,
                data={
                    'status': Organisation.status,
                    'status_display': status_display,
                    'staff_deactivated': deactivated_staff_count
                }
            )
        except Exception as e:
            return cls._unexpected_error_result('toggle_status', e)
    
    @classmethod
    def _cascade_deactivate_staff(cls, client: Organisation) -> int:
        """
        Deactivate all assistants when client is deactivated.
        Returns the count of assistants deactivated.
        """
        # Get all active assistants for this client
        active_staff = Assistant.objects.filter(
            organisation=client,
            user__is_active=True
        ).select_related('user')
        
        count = 0
        for staff in active_staff:
            staff.user.is_active = False
            staff.user.save()
            count += 1
        
        return count
    
    @classmethod
    def list_all(cls, include_inactive: bool = False) -> ServiceResult:
        """List all clients"""
        try:
            queryset = Organisation.objects.select_related('user').all()
            if not include_inactive:
                queryset = queryset.filter(status='active')
            
            clients = [cls.serialize(c, include_permissions=False) for c in queryset]
            return ServiceResult(
                success=True,
                data={'clients': clients, 'total': len(clients)}
            )
        except Exception as e:
            return cls._unexpected_error_result('list_all', e)
    
    @classmethod
    def get_staff(cls, client_id: int) -> ServiceResult:
        """Get all assistants for a client"""
        try:
            client = get_object_or_404(Organisation, id=client_id)
            staff_members = Assistant.objects.filter(
                organisation=client
            ).select_related('user')
            
            staff_list = []
            active_count = 0
            inactive_count = 0
            
            for staff in staff_members:
                is_active = staff.user.is_active
                if is_active:
                    active_count += 1
                else:
                    inactive_count += 1

                # Include all permission booleans so UI can render current assistant grants.
                staff_permissions = {
                    field.name: bool(getattr(staff, field.name, False))
                    for field in staff._meta.fields
                    if field.name.startswith('perm_')
                }
                
                staff_list.append({
                    'id': staff.id,
                    'name': staff.user.get_full_name() or staff.user.username,
                    'email': staff.user.email or '',
                    'phone': staff.user.phone or '',
                    'department': staff.department or '',
                    'designation': staff.designation or '',
                    'is_active': is_active,
                    'status': 'active' if is_active else 'inactive',
                    'status_display': 'Active' if is_active else 'Inactive',
                    'created_at': staff.created_at.strftime('%d-%m-%Y'),
                    **staff_permissions,
                })
            
            return ServiceResult(
                success=True,
                data={
                    'client_name': client.name,
                    'staff': staff_list,
                    'total': len(staff_list),
                    'active': active_count,
                    'inactive': inactive_count
                }
            )
        except Exception as e:
            return cls._unexpected_error_result('get_staff', e)

    @classmethod
    def toggle_client_staff_status(cls, client_id: int, staff_id: int) -> ServiceResult:
        """Toggle an assistant member's active/inactive status (atomic, Super Admin only)"""
        try:
            client = get_object_or_404(Organisation, id=client_id)
            with transaction.atomic():
                staff = Assistant.objects.select_for_update().select_related('user').filter(
                    id=staff_id,
                    organisation=client
                ).first()
                
                if not staff:
                    return ServiceResult(
                        success=False,
                        message='Assistant member not found or does not belong to this client'
                    )
                
                user = staff.user
                user.is_active = not user.is_active
                user.save(update_fields=['is_active'])
            
            is_active = user.is_active
            return ServiceResult(
                success=True,
                message=f'Assistant {"activated" if is_active else "deactivated"} successfully',
                data={
                    'staff_id': staff_id,
                    'is_active': is_active,
                    'status': 'active' if is_active else 'inactive',
                    'status_display': 'Active' if is_active else 'Inactive'
                }
            )
        except Exception as e:
            return cls._unexpected_error_result('toggle_client_staff_status', e)
    
    @classmethod
    def update_client_staff_permissions(cls, client_id: int, staff_id: int, permissions: dict) -> ServiceResult:
        """
        Update an assistant's permissions (Super Admin only).
        Enforces that assistant permissions cannot exceed client permissions.
        """
        try:
            client = get_object_or_404(Organisation, id=client_id)
            staff = Assistant.objects.filter(
                id=staff_id,
                organisation=client
            ).first()
            
            if not staff:
                return ServiceResult(
                    success=False,
                    message='Assistant member not found or does not belong to this client'
                )
            
            # Permission mapping: staff perm -> Organisation perm
            STAFF_TO_CLIENT_PERMS = {
                'perm_idcard_client_list': 'perm_idcard_client_list',
                'perm_idcard_setting_list': 'perm_idcard_setting_list',
                'perm_idcard_setting_add': 'perm_idcard_setting_add',
                'perm_idcard_setting_edit': 'perm_idcard_setting_edit',
                'perm_idcard_setting_delete': 'perm_idcard_setting_delete',
                'perm_idcard_setting_status': 'perm_idcard_setting_status',
            }
            
            updated_perms = []
            rejected_perms = []
            
            with transaction.atomic():
                # Re-fetch with row lock to prevent concurrent permission updates
                staff = Assistant.objects.select_for_update().get(pk=staff.pk)
                
                for perm_name, value in permissions.items():
                    if perm_name not in STAFF_TO_CLIENT_PERMS:
                        continue  # Ignore unknown permissions
                    
                    client_perm = STAFF_TO_CLIENT_PERMS.get(perm_name)
                    
                    # If trying to grant a permission, verify client has it
                    if value and client_perm:
                        client_has_perm = getattr(client, client_perm, False)
                        if not client_has_perm:
                            rejected_perms.append(perm_name)
                            continue  # Skip - client doesn't have this permission
                    
                    # Update assistant permission
                    setattr(staff, perm_name, bool(value))
                    updated_perms.append(perm_name)
                
                staff.save()
            
            # Refresh to confirm persistence
            staff.refresh_from_db()
            
            message = f'Updated {len(updated_perms)} permission(s)'
            if rejected_perms:
                message += f'. {len(rejected_perms)} permission(s) rejected (client lacks permission)'
            
            return ServiceResult(
                success=True,
                message=message,
                data={
                    'staff_id': staff_id,
                    'updated_permissions': updated_perms,
                    'rejected_permissions': rejected_perms
                }
            )
        except Exception as e:
            return cls._unexpected_error_result('update_client_staff_permissions', e)

    @classmethod
    def set_temp_password(cls, client_id: int, new_password: str, request=None) -> ServiceResult:
        """
        Set a temporary password for a client user.
        Sends a welcome email with the new credentials so the user knows their password.
        """
        try:
            client = get_object_or_404(Organisation.objects.select_related('user'), id=client_id)
            user = client.user

            if not new_password or not new_password.strip():
                return ServiceResult(success=False, message='Password cannot be empty')

            # Universal password normalization (phone formats -> digits, text -> intact)
            normalized_password = normalize_password_input(new_password)

            user.set_password(normalized_password)
            user.save(update_fields=['password'])

            # Send welcome email with the new temporary password
            email_sent = False
            try:
                email_sent, _ = send_welcome_email(
                    name=client.name or user.get_full_name(),
                    email=user.email,
                    password=new_password,
                    role='client',
                    phone=user.phone or '',
                    request=request,
                    email_variant='temp_password',
                )
                EmailLog.objects.create(
                    recipient_name=client.name or user.get_full_name(),
                    recipient_email=user.email,
                    subject='Your Temporary Password — Adarsh Admin',
                    email_type=EmailLog.EMAIL_TYPE_TEMP_PASSWORD,
                    status=EmailLog.STATUS_SENT if email_sent else EmailLog.STATUS_FAILED,
                )
            except Exception as e:
                logger.warning('Temp password email failed for %s: %s', user.email, e)

            return ServiceResult(
                success=True,
                message=f'Temporary password set for "{client.name}"',
                data={'email_sent': email_sent}
            )
        except Exception as e:
            return cls._unexpected_error_result('set_temp_password', e)
