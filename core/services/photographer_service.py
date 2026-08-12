"""
Photographer Service Module
Contains: Photographer CRUD operations, serialization using core.models Photographer/PhotographerAssignment
"""
import json
import logging
import secrets
from typing import Dict, Any

from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils.timezone import localtime

from core.models import User, EmailLog, Photographer, PhotographerAssignment
from organisation.models import Organisation
from core.utils import send_welcome_email
from core.utils.email_utils import generate_secure_password
from core.services.base import BaseService, ServiceResult

from accounts.services import normalize_password_input

logger = logging.getLogger(__name__)


class PhotographerService(BaseService):
    """
    Service for Photographer CRUD operations.
    """

    PHOTOGRAPHER_PERMISSION_FIELDS = [
        'perm_idcard_pending_list',
        'perm_idcard_verified_list',
        'perm_idcard_add',
        'perm_idcard_info',
        'perm_mobile_app',
        'perm_idcard_bulk_download',
    ]

    @classmethod
    def parse_bool(cls, val) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ('true', '1', 'yes')
        return bool(val)

    @classmethod
    def _public_email(cls, email: str) -> str:
        if not email:
            return ''
        if email.endswith('@noemail.local'):
            return ''
        return email

    @classmethod
    def _has_real_email(cls, email: str) -> bool:
        return bool(email and not email.endswith('@noemail.local'))

    @classmethod
    def serialize(cls, photographer: Photographer) -> Dict[str, Any]:
        """Serialize Photographer instance to dict"""
        user = photographer.user
        data = {
            'id': photographer.id,
            'name': user.get_full_name(),
            'email': cls._public_email(user.email),
            'phone': user.phone or '',
            'address': '',
            'staff_type': 'photographer',
            'status': 'active' if user.is_active else 'inactive',
            'created_at': localtime(photographer.created_at).strftime('%d-%m-%Y %H:%M'),
            'updated_at': localtime(photographer.updated_at).strftime('%d-%m-%Y %H:%M'),
        }

        # Include photographer permissions so the edit drawer shows correct toggle states
        for perm in cls.PHOTOGRAPHER_PERMISSION_FIELDS:
            data[perm] = bool(getattr(photographer, perm, False))

        # Include photographer assignments
        assignments = []
        for ass in photographer.photographer_assignments.select_related('client').all():
            assignments.append({
                'client_id': ass.client_id,
                'client_name': ass.client.name,
                'expires_at': localtime(ass.expires_at).strftime('%Y-%m-%dT%H:%M') if ass.expires_at else '',
                'expires_at_display': localtime(ass.expires_at).strftime('%d-%m-%Y %H:%M') if ass.expires_at else 'No Expiration',
                'allowed_table_ids': list(ass.allowed_table_ids or []),
            })
        data['assigned_organisations'] = assignments
        # Also simple list of ids for UI drawer compatibility
        data['assigned_client_ids'] = [a['client_id'] for a in assignments]
        return data

    @classmethod
    def get(cls, staff_id: int) -> ServiceResult:
        """Fetch photographer details"""
        try:
            photographer = Photographer.objects.select_related('user').prefetch_related('photographer_assignments__client').get(id=staff_id)
            return ServiceResult(success=True, data={'staff': cls.serialize(photographer)})
        except Photographer.DoesNotExist:
            return ServiceResult(success=False, message='Photographer not found')

    @classmethod
    def create(cls, data: Dict[str, Any], request=None) -> ServiceResult:
        """Create a new photographer"""
        try:
            send_welcome = False
            welcome_info = {}
            welcome_user_id = None
            welcome_email_log_id = None

            name = str(data.get('name') or '').strip()
            if not name:
                return ServiceResult(success=False, message='Name is required')

            raw_email = str(data.get('email') or '').strip().lower()
            email_was_provided = bool(raw_email)

            if raw_email:
                if User.objects.filter(email__iexact=raw_email).exists():
                    return ServiceResult(success=False, message='A user with this email already exists')
                email = raw_email
            else:
                slug = name.lower().replace(' ', '_')[:24] or 'photographer'
                email = f'photographer.{slug}.{secrets.token_hex(4)}@noemail.local'
                while User.objects.filter(email__iexact=email).exists():
                    email = f'photographer.{slug}.{secrets.token_hex(4)}@noemail.local'
            
            # Generate unique username
            username = email.split('@')[0].lower().replace('.', '_')
            if not username:
                username = f'photographer_{secrets.token_hex(4)}'
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            name_parts = name.split() if name else []
            
            phone = str(data.get('phone') or '').strip()
            password = str(data.get('password') or '').strip()
            used_phone_as_password = False
            if not password:
                if phone:
                    password = normalize_password_input(phone)
                    if not password:
                        return ServiceResult(success=False, message='Phone number must contain digits to be used as a password')
                    used_phone_as_password = True
                else:
                    return ServiceResult(success=False, message='Phone number is required when custom password is not provided')
            
            if not used_phone_as_password:
                from django.contrib.auth.password_validation import validate_password
                try:
                    validate_password(password)
                except Exception as pw_err:
                    return ServiceResult(success=False, message=str(pw_err))
            
            role = 'photographer'
            
            with transaction.atomic():
                is_active = cls.parse_bool(data.get('is_active', False))
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=name_parts[0] if name_parts else '',
                    last_name=' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
                    phone=data.get('phone', ''),
                    role=role,
                    is_active=is_active,
                )
                user.set_password(password)
                user.save()
                
                photographer_kwargs = {
                    'user': user,
                }
                for perm in cls.PHOTOGRAPHER_PERMISSION_FIELDS:
                    if perm in data:
                        photographer_kwargs[perm] = cls.parse_bool(data[perm])
                    else:
                        photographer_kwargs[perm] = True
                
                photographer = Photographer.objects.create(**photographer_kwargs)
                
                # Assign clients with optional expirations
                assigned_clients = data.get('assigned_organisations', [])
                if isinstance(assigned_clients, str):
                    try:
                        assigned_clients = json.loads(assigned_clients)
                    except json.JSONDecodeError:
                        assigned_clients = []
                
                from django.utils.dateparse import parse_datetime
                for item in assigned_clients:
                    try:
                        client_id = int(item.get('client_id'))
                        expires_at_str = item.get('expires_at')
                        expires_at = parse_datetime(expires_at_str) if expires_at_str else None
                        raw_table_ids = item.get('allowed_table_ids', [])
                        allowed_table_ids = [int(t) for t in raw_table_ids if str(t).isdigit()] if raw_table_ids else []
                        PhotographerAssignment.objects.create(
                            photographer=photographer,
                            client_id=client_id,
                            expires_at=expires_at,
                            allowed_table_ids=allowed_table_ids,
                        )
                    except (ValueError, TypeError):
                        pass

                if email_was_provided and cls._has_real_email(email):
                    log = EmailLog.objects.create(
                        recipient_name=name or user.get_full_name(),
                        recipient_email=email,
                        subject='Welcome to Adarsh Admin - Your Photographer Account is Ready!',
                        email_type=EmailLog.EMAIL_TYPE_WELCOME,
                        status=EmailLog.STATUS_ON_HOLD,
                    )
                    welcome_email_log_id = log.pk

                    if is_active:
                        send_welcome = True
                        welcome_user_id = user.pk
                        welcome_info = {
                            'name': name or user.get_full_name(),
                            'email': email,
                            'password': password,
                            'phone': user.phone or '',
                            'role': role,
                        }

            if send_welcome:
                _user_pk = welcome_user_id
                _log_id = welcome_email_log_id

                try:
                    email_sent, error_msg = send_welcome_email(
                        name=welcome_info['name'],
                        email=welcome_info['email'],
                        password=welcome_info['password'],
                        role='Photographer',
                        phone=welcome_info['phone'],
                        request=request,
                        email_variant='welcome',
                    )
                except Exception as email_exc:
                    email_sent = False
                    error_msg = str(email_exc)
                    logger.warning('Photographer welcome email failed for %s: %s', welcome_info.get('email', ''), email_exc)

                if email_sent:
                    User.objects.filter(pk=_user_pk).update(welcome_email_sent=True)
                    EmailLog.objects.filter(pk=_log_id).update(
                        status=EmailLog.STATUS_SENT,
                        sent_at=localtime(),
                        error_message='',
                    )
                else:
                    EmailLog.objects.filter(pk=_log_id).update(
                        status=EmailLog.STATUS_FAILED,
                        error_message=error_msg or 'Failed to send welcome email',
                    )

            return ServiceResult(success=True, message='Photographer created successfully', data={'staff': cls.serialize(photographer)})
        except Exception as e:
            return cls._unexpected_error_result('create_photographer', e)

    @classmethod
    @transaction.atomic
    def update(cls, staff_id: int, data: Dict[str, Any]) -> ServiceResult:
        """Update photographer profile and client assignments"""
        try:
            photographer = get_object_or_404(Photographer, id=staff_id)
            user = photographer.user

            name = str(data.get('name') or '').strip()
            if not name:
                return ServiceResult(success=False, message='Name is required')

            email = str(data.get('email') or '').strip().lower()
            if email:
                if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                    return ServiceResult(success=False, message='A user with this email already exists')
                user.email = email
            
            name_parts = name.split() if name else []
            user.first_name = name_parts[0] if name_parts else ''
            user.last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
            user.phone = data.get('phone', '')
            user.is_active = cls.parse_bool(data.get('is_active', user.is_active))
            user.save()

            # Update permissions
            for perm in cls.PHOTOGRAPHER_PERMISSION_FIELDS:
                if perm in data:
                    setattr(photographer, perm, cls.parse_bool(data[perm]))
            photographer.save()

            # Update assignments
            assigned_clients = data.get('assigned_organisations', [])
            if isinstance(assigned_clients, str):
                try:
                    assigned_clients = json.loads(assigned_clients)
                except json.JSONDecodeError:
                    assigned_clients = []

            from django.utils.dateparse import parse_datetime
            existing = {a.client_id: a for a in photographer.photographer_assignments.all()}
            keep_client_ids = set()

            for item in assigned_clients:
                try:
                    client_id = int(item.get('client_id'))
                    expires_at_str = item.get('expires_at')
                    expires_at = parse_datetime(expires_at_str) if expires_at_str else None
                    raw_table_ids = item.get('allowed_table_ids', [])
                    allowed_table_ids = [int(t) for t in raw_table_ids if str(t).isdigit()] if raw_table_ids else []

                    if client_id in existing:
                        assignment = existing[client_id]
                        assignment.expires_at = expires_at
                        assignment.allowed_table_ids = allowed_table_ids
                        assignment.save()
                    else:
                        PhotographerAssignment.objects.create(
                            photographer=photographer,
                            client_id=client_id,
                            expires_at=expires_at,
                            allowed_table_ids=allowed_table_ids,
                        )
                    keep_client_ids.add(client_id)
                except (ValueError, TypeError):
                    pass

            photographer.photographer_assignments.exclude(client_id__in=keep_client_ids).delete()

            # Invalidate permission cache
            from core.services.session_revalidation import bump_user_revalidation
            bump_user_revalidation(user.pk)

            return ServiceResult(success=True, message='Photographer updated successfully', data={'staff': cls.serialize(photographer)})
        except Exception as e:
            return cls._unexpected_error_result('update_photographer', e)

    @classmethod
    def delete(cls, staff_id: int) -> ServiceResult:
        """Delete photographer"""
        try:
            photographer = Photographer.objects.filter(id=staff_id).first()
            if not photographer:
                return ServiceResult(success=False, message='Photographer not found')
            user = photographer.user
            with transaction.atomic():
                photographer.delete()
                user.delete()
            return ServiceResult(success=True, message='Photographer deleted successfully')
        except Exception as e:
            return cls._unexpected_error_result('delete_photographer', e)

    @classmethod
    def toggle_status(cls, staff_id: int) -> ServiceResult:
        """Toggle photographer active status"""
        try:
            photographer = Photographer.objects.filter(id=staff_id).first()
            if not photographer:
                return ServiceResult(success=False, message='Photographer not found')
            user = photographer.user
            user.is_active = not user.is_active
            user.save(update_fields=['is_active'])
            status_str = 'activated' if user.is_active else 'deactivated'
            return ServiceResult(success=True, message=f'Photographer {status_str} successfully', data={'is_active': user.is_active})
        except Exception as e:
            return cls._unexpected_error_result('toggle_status', e)

    @classmethod
    def set_temp_password(cls, staff_id: int, new_password: str, request=None) -> ServiceResult:
        """
        Set a temporary password for a photographer.
        Sends a welcome email with the new credentials.
        """
        try:
            photographer = Photographer.objects.filter(id=staff_id).select_related('user').first()
            if not photographer:
                return ServiceResult(success=False, message='Photographer not found')

            user = photographer.user
            if not new_password or not new_password.strip():
                return ServiceResult(success=False, message='Password cannot be empty')

            # Normalization (e.g. if the user enters space-padded values or phone numbers)
            normalized_password = normalize_password_input(new_password)

            user.set_password(normalized_password)
            user.save(update_fields=['password'])

            # Send welcome email with new temp password
            email_sent = False
            try:
                email_sent, _ = send_welcome_email(
                    name=user.get_full_name(),
                    email=user.email,
                    password=new_password,
                    role='photographer',
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
                logger.warning('Failed to send photographer temp password email: %s', e)

            # Log this action using ActivityService
            from core.services.activity_service import ActivityService
            last_active_str = ActivityService._format_last_active(user)
            ActivityService.log(
                'staff_password_reset',
                f'Temporary password set for Photographer "{user.get_full_name()}" ({last_active_str})',
                user=request.user if request else None,
                request=request,
                target_model='Photographer',
                target_id=photographer.id,
                target_name=user.get_full_name(),
            )

            msg = f'Temporary password updated successfully for photographer "{user.get_full_name()}".'
            return ServiceResult(success=True, message=msg, data={'email_sent': email_sent})
        except Exception as e:
            logger.exception("PhotographerService temp password error: %s", e)
            return ServiceResult(success=False, message='An error occurred')

    @classmethod
    def _unexpected_error_result(cls, method_name: str, e: Exception) -> ServiceResult:
        logger.exception("Unexpected error in PhotographerService.%s: %s", method_name, e)
        return ServiceResult(success=False, message=f"An unexpected error occurred during {method_name}")
