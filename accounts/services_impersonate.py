"""
Impersonation Service — Pro User only.

Allows the Pro User to "login as" any other user for production testing.
Uses Django session to track the original user.
"""
import logging
from django.contrib.auth import get_user_model, login

logger = logging.getLogger(__name__)

User = get_user_model()


class ImpersonateService:
    """
    Session-based impersonation for the Pro User.

    start() — switch current session to target user
    stop()  — switch back to the original Pro User
    is_impersonating() — check if the current session is impersonated
    """

    SESSION_KEY = '_pro_original_user_id'
    SESSION_NAME_KEY = '_pro_original_user_name'

    @classmethod
    def can_impersonate(cls, user) -> bool:
        """Allow admin users with Pro access to impersonate operational accounts."""
        from core.services.permission_service import PermissionService

        return bool(
            user and user.is_authenticated and (
                PermissionService.can_use_pro_user_options(user)
                or PermissionService.is_super_admin(user)
            )
        )

    @classmethod
    def is_impersonating(cls, request) -> bool:
        return bool(request.session.get(cls.SESSION_KEY))

    @classmethod
    def start(cls, request, target_user_id: int) -> dict:
        """
        Start impersonating a target user.

        Args:
            request: Current HttpRequest (must be from a pro_user)
            target_user_id: PK of the user to impersonate

        Returns:
            dict with success, message, redirect_url
        """
        current_user = request.user

        # Only pro_user can impersonate
        if not cls.can_impersonate(current_user):
            return {'success': False, 'message': 'Permission denied.'}

        # Cannot impersonate yourself
        if current_user.pk == target_user_id:
            return {'success': False, 'message': 'Cannot impersonate yourself.'}

        # Decode ID if compatibility wrapped
        from core.services.compat_service import CompatibilityService
        _, real_id = CompatibilityService.decode_id(target_user_id)

        # Cannot impersonate operators or photographers
        UserModel = get_user_model()
        try:
            target_user = UserModel.objects.get(pk=real_id)
        except UserModel.DoesNotExist:
            return {'success': False, 'message': 'User not found.'}

        if target_user.role in ('operator', 'admin_staff', 'photographer'):
            return {'success': False, 'message': 'Cannot impersonate operators or photographers.'}

        # Cannot chain impersonations
        if cls.is_impersonating(request):
            return {'success': False, 'message': 'Already impersonating. Stop first.'}

        if not target_user.is_active:
            return {'success': False, 'message': 'Cannot impersonate an inactive user.'}

        # Save original user info before login() flushes the session
        original_user_id = current_user.pk
        original_user_name = current_user.get_full_name() or current_user.username

        # Impersonation should not revoke the target user's real device sessions.
        request._skip_device_session_enforcement = True
        # Switch to target user — login() flushes and recreates the session
        login(request, target_user, backend='django.contrib.auth.backends.ModelBackend')

        # Set impersonation markers in the new session
        request.session[cls.SESSION_KEY] = original_user_id
        request.session[cls.SESSION_NAME_KEY] = original_user_name
        request.session.modified = True
        request.session.save()

        # Re-seed session fingerprint immediately after login() rotates session.
        try:
            from core.middleware import PermissionValidationMiddleware
            PermissionValidationMiddleware.seed_session_fingerprint(request)
        except Exception:
            pass

        from .services import DASHBOARD_URLS
        redirect_url = DASHBOARD_URLS.get(target_user.role, '/panel/')

        logger.info(
            "Impersonation started: pro_user=%s (ID:%d) → target=%s (ID:%d, role=%s)",
            original_user_name, original_user_id,
            target_user.username, target_user.pk, target_user.role,
        )

        return {
            'success': True,
            'message': f'Now impersonating {target_user.get_full_name() or target_user.username}',
            'redirect_url': redirect_url,
        }

    @classmethod
    def stop(cls, request, next_url: str = '') -> dict:
        """
        Stop impersonating and return to the Pro User session.

        Args:
            request: Current HttpRequest
            next_url: Optional URL to redirect to after stopping

        Returns:
            dict with success, message, redirect_url
        """
        original_user_id = request.session.get(cls.SESSION_KEY)
        if not original_user_id:
            return {'success': False, 'message': 'Not currently impersonating.'}

        UserModel = get_user_model()
        from core.services.compat_service import CompatibilityService
        _, real_orig_id = CompatibilityService.decode_id(original_user_id)
        try:
            original_user = UserModel.objects.using('default').get(pk=real_orig_id)
        except UserModel.DoesNotExist:
            logger.error("Impersonate stop: Original account not found for user ID %s", real_orig_id)
            return {'success': False, 'message': 'Original account not found.'}

        impersonated_name = request.user.get_full_name() or request.user.username

        # Remove impersonation markers so they don't persist after login()
        if cls.SESSION_KEY in request.session:
            del request.session[cls.SESSION_KEY]
        if cls.SESSION_NAME_KEY in request.session:
            del request.session[cls.SESSION_NAME_KEY]

        # Clear any thread-local guest sandbox routing context so login updates default DB
        try:
            from core.db_router import GuestSandboxRouter
            GuestSandboxRouter.clear_guest_db()
        except Exception:
            pass
        original_user._state.db = 'default'

        # Returning from impersonation should also avoid side-effect session revocations.
        request._skip_device_session_enforcement = True
        # Switch back — login() flushes the session but preserves dict, so we manually deleted markers above
        login(request, original_user, backend='django.contrib.auth.backends.ModelBackend')

        try:
            from core.middleware import PermissionValidationMiddleware
            PermissionValidationMiddleware.seed_session_fingerprint(request)
        except Exception:
            pass

        logger.info(
            "Impersonation stopped: pro_user=%s (ID:%d) was impersonating %s",
            original_user.username, original_user.pk, impersonated_name,
        )

        from .services import DASHBOARD_URLS
        redirect_url = DASHBOARD_URLS.get(getattr(original_user, 'role', 'pro_user'), '/panel/')
        
        # If a safe next_url is provided, use it
        if next_url and next_url.startswith('/'):
            redirect_url = next_url

        return {
            'success': True,
            'message': 'Impersonation stopped.',
            'redirect_url': redirect_url,
        }

    @classmethod
    def get_impersonation_targets(cls, request) -> list:
        """
        Get list of users the Pro User can impersonate.
        Returns a list of dicts with id, name, email, role.
        """
        if not cls.can_impersonate(request.user):
            return []

        UserModel = get_user_model()
        users = (
            UserModel.objects
            .filter(is_active=True)
            .select_related('client_profile', 'assistant_profile__client', 'operator_profile')
            .exclude(pk=request.user.pk)
            .exclude(role__in=['pro_user', 'operator', 'admin_staff', 'photographer'])
            .order_by('role', 'first_name', 'username')
        )

        result = []
        for u in users:
            name = f"{u.first_name} {u.last_name}".strip() or u.username
            client_name = ''
            if u.role == 'prime_manager':
                client_profile = getattr(u, 'client_profile', None)
                client_name = getattr(client_profile, 'name', '') or ''
            elif u.role == 'assistant':
                assistant_profile = getattr(u, 'assistant_profile', None)
                client_name = getattr(getattr(assistant_profile, 'client', None), 'name', '') or ''
            elif u.role == 'operator':
                client_name = ''

            from core.services.compat_service import CompatibilityService
            result.append(CompatibilityService.translate_dict({
                'id': u.id,
                'name': name,
                'email': u.email,
                'role': u.role,
                'role_display': dict(UserModel.ROLE_CHOICES).get(u.role, u.role),
                'is_active': u.is_active,
                'client_name': client_name,
            }))

        return result
