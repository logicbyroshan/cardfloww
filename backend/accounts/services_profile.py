"""
User Profile Service
====================
Single authority for user profile mutations (update profile, change password,
manage profile image). Views must ONLY validate request → call service → return.

Architecture rule:
  - This service owns ALL profile-related mutations
  - No view may call user.save(), user.set_password(), os.remove() on profile images
  - All mutations go through UserProfileService methods
"""
import logging

from django.db import transaction
from accounts.services import normalize_password_input

logger = logging.getLogger(__name__)

# Allowed MIME types for profile images
ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


class UserProfileService:
    """Manages user profile data: name, email, phone, password, profile image."""

    SECURITY_SETTINGS_DEFAULTS = {
        'two_factor_enabled': False,
        'login_notifications_enabled': True,
        'session_timeout_minutes': 10080,
    }
    SECURITY_SESSION_TIMEOUT_CHOICES = {0, 15, 30, 60, 120, 10080}

    @staticmethod
    def _security_key(user_id, field_name):
        return f'user_security:{user_id}:{field_name}'

    @staticmethod
    def _to_bool(value):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}

    @staticmethod
    def update_profile(user, data, request=None):
        """
        Update user profile fields.
        data: dict with optional keys: first_name, last_name, username, email, phone.
        Returns (success: bool, message: str, profile_data: dict|None).
        """
        from core.models import User

        with transaction.atomic():
            changed_fields = []
            if 'first_name' in data:
                if user.first_name != data['first_name'].strip():
                    changed_fields.append('First name')
                user.first_name = data['first_name'].strip()
            if 'last_name' in data:
                if user.last_name != data['last_name'].strip():
                    changed_fields.append('Last name')
                user.last_name = data['last_name'].strip()

            if 'username' in data and data['username'].strip():
                new_username = data['username'].strip()
                if User.objects.filter(username=new_username).exclude(id=user.id).exists():
                    return False, 'Username already taken', None
                if user.username != new_username:
                    changed_fields.append('Username')
                user.username = new_username

            if 'email' in data and data['email'].strip():
                new_email = data['email'].strip()
                if User.objects.filter(email=new_email).exclude(id=user.id).exists():
                    return False, 'Email already in use', None
                if user.email != new_email:
                    changed_fields.append('Email')
                user.email = new_email

            if 'phone' in data:
                if getattr(user, 'phone', '') != data['phone'].strip():
                    changed_fields.append('Phone')
                user.phone = data['phone'].strip()

            user.save()

        # Log profile update
        if changed_fields:
            try:
                from core.services.activity_service import ActivityService
                ActivityService.log_profile_update(user, changed_fields, request=request)
            except Exception:
                logger.warning('Failed to log profile update for user=%s', user.pk)

        return True, 'Profile updated', {
            'full_name': user.get_full_name() or user.username,
            'email': user.email,
            'username': user.username,
        }

    @staticmethod
    def change_password(user, current_password, new_password, current_session_key=None):
        """
        Change user's password after validating current password.
        Uses Django AUTH_PASSWORD_VALIDATORS for strength checks.
        Returns (success: bool, message: str).
        """
        if not current_password or not new_password:
            return False, 'Both current and new password are required'

        # Universal password normalization (phone formats -> digits, text -> intact)
        normalized_current = normalize_password_input(current_password)
        normalized_new = normalize_password_input(new_password)

        if not user.check_password(current_password) and not user.check_password(normalized_current):
            return False, 'Current password is incorrect'

        # Use Django's password validators for consistent strength checks
        from django.contrib.auth.password_validation import validate_password
        try:
            validate_password(normalized_new, user=user)
        except Exception as e:
            return False, str(e)

        user.set_password(normalized_new)
        user.save()

        # Security hardening: revoke other active sessions after password change.
        try:
            from accounts.services import _revoke_user_sessions
            _revoke_user_sessions(user.pk, exclude_session_key=current_session_key or '')
        except Exception as exc:
            logger.warning('Password-change session revocation failed for user=%s: %s', user.pk, exc)

        # Log password change
        try:
            from core.services.activity_service import ActivityService
            last_active_str = ActivityService._format_last_active(user)
            ActivityService.log(
                'password_reset',
                f'Password changed by "{user.get_full_name() or user.email}" ({last_active_str})',
                user=user,
                target_model='User',
                target_id=user.pk,
                target_name=user.get_full_name() or user.email,
            )
        except Exception:
            logger.warning('Failed to log password change for user=%s', user.pk)

        return True, 'Password changed successfully'

    @staticmethod
    def upload_profile_image(user, image_file):
        """
        Upload/replace the user's profile image.
        Returns (success: bool, message: str, image_url: str|None).

        NOTE: profile_image field was removed from User model in Phase 1 refactor.
        This method is kept for backward compat but now returns an error.
        """
        return False, 'Profile image feature is no longer available. Avatars are generated automatically.', None

    @staticmethod
    def remove_profile_image(user):
        """
        Remove the user's profile image.
        Returns (success: bool, message: str).

        NOTE: profile_image field was removed from User model in Phase 1 refactor.
        This method is kept for backward compat but now returns an error.
        """
        return False, 'Profile image feature is no longer available.'

    @staticmethod
    def get_security_settings(user):
        """Return persisted security preferences for the given user."""
        from core.models import SystemSettings

        defaults = UserProfileService.SECURITY_SETTINGS_DEFAULTS
        two_factor_enabled = UserProfileService._to_bool(
            SystemSettings.get_value(
                UserProfileService._security_key(user.id, 'two_factor_enabled'),
                '1' if defaults['two_factor_enabled'] else '0',
            )
        )
        login_notifications_enabled = UserProfileService._to_bool(
            SystemSettings.get_value(
                UserProfileService._security_key(user.id, 'login_notifications_enabled'),
                '1' if defaults['login_notifications_enabled'] else '0',
            )
        )

        raw_timeout = SystemSettings.get_value(
            UserProfileService._security_key(user.id, 'session_timeout_minutes'),
            str(defaults['session_timeout_minutes']),
        )
        try:
            session_timeout_minutes = int(str(raw_timeout).strip())
        except (TypeError, ValueError):
            session_timeout_minutes = defaults['session_timeout_minutes']

        if session_timeout_minutes not in UserProfileService.SECURITY_SESSION_TIMEOUT_CHOICES:
            session_timeout_minutes = defaults['session_timeout_minutes']

        return {
            'two_factor_enabled': two_factor_enabled,
            'login_notifications_enabled': login_notifications_enabled,
            'session_timeout_minutes': session_timeout_minutes,
        }

    @staticmethod
    def get_profile(user, request=None):
        """Return profile data."""
        first_name = user.first_name
        last_name = user.last_name
        username = user.username
        email = user.email
        phone = getattr(user, 'phone', '') or ''

        full_name = (first_name or '') + ' ' + (last_name or '')
        full_name = full_name.strip() or username

        return {
            'username': username,
            'email': email or '',
            'first_name': first_name or '',
            'last_name': last_name or '',
            'full_name': full_name,
            'phone': phone,
            'role': getattr(user, 'role', 'client'),
            'role_display': user.get_role_display() if hasattr(user, 'get_role_display') else getattr(user, 'role', 'client'),
            'profile_image': None,
            'member_since': user.date_joined.strftime('%b %Y') if getattr(user, 'date_joined', None) else '',
        }

    @staticmethod
    def update_security_settings(user, data):
        """
        Update persisted security preferences for the given user.
        Returns (success: bool, message: str, security_settings: dict|None).
        """
        from core.models import SystemSettings

        if not isinstance(data, dict):
            return False, 'Invalid request payload', None

        updates = {}

        if 'two_factor_enabled' in data:
            updates['two_factor_enabled'] = UserProfileService._to_bool(data.get('two_factor_enabled'))

        if 'login_notifications_enabled' in data:
            updates['login_notifications_enabled'] = UserProfileService._to_bool(data.get('login_notifications_enabled'))

        if 'session_timeout_minutes' in data:
            try:
                timeout = int(str(data.get('session_timeout_minutes')).strip())
            except (TypeError, ValueError):
                return False, 'Invalid session timeout value', None

            if timeout not in UserProfileService.SECURITY_SESSION_TIMEOUT_CHOICES:
                return False, 'Invalid session timeout value', None

            updates['session_timeout_minutes'] = timeout

        if not updates:
            return False, 'No valid fields provided', None

        for field_name, value in updates.items():
            if isinstance(value, bool):
                stored_value = '1' if value else '0'
            else:
                stored_value = str(value)

            SystemSettings.set_value(
                UserProfileService._security_key(user.id, field_name),
                stored_value,
                description=f'Security setting ({field_name}) for user {user.id}',
            )

        current = UserProfileService.get_security_settings(user)

        # Log security settings change
        try:
            from core.services.activity_service import ActivityService
            # Build human-readable changed settings dict
            readable = {}
            if 'two_factor_enabled' in updates:
                readable['two_factor_enabled'] = 'On' if updates['two_factor_enabled'] else 'Off'
            if 'login_notifications_enabled' in updates:
                readable['login_notifications_enabled'] = 'On' if updates['login_notifications_enabled'] else 'Off'
            if 'session_timeout_minutes' in updates:
                t = updates['session_timeout_minutes']
                readable['session_timeout_minutes'] = ('Never' if t == 0 else str(t) + ' min')
            ActivityService.log_security_settings_update(user, readable)
        except Exception:
            logger.warning('Failed to log security settings update for user=%s', user.pk)

        return True, 'Security settings updated', current
