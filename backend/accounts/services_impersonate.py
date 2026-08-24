"""
Impersonation Service — Super Admin & Pro User.

Allows administrators to "login as" any operational user for testing and troubleshooting.
Uses Django session to track the original administrator.
"""
import logging
from django.contrib.auth import get_user_model, login

logger = logging.getLogger(__name__)

User = get_user_model()


class ImpersonateService:
    """
    Session-based impersonation for Administrators / Pro Users.

    start() — switch current session to target user
    stop()  — switch back to the original Administrator
    is_impersonating() — check if the current session is impersonated
    """

    SESSION_KEY = '_pro_original_user_id'
    SESSION_NAME_KEY = '_pro_original_user_name'

    @classmethod
    def can_impersonate(cls, user) -> bool:
        """Allow super admins and pro users to impersonate operational accounts."""
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False):
            return True
        if getattr(user, 'role', '') in ('super_admin', 'pro_user', 'prime_admin'):
            return True
        from core.services.permission_service import PermissionService
        return PermissionService.can_use_pro_user_options(user) or PermissionService.is_super_admin(user)

    @classmethod
    def is_impersonating(cls, request) -> bool:
        return bool(
            request.session.get(cls.SESSION_KEY)
            or request.session.get('_impersonator_id')
        )

    @classmethod
    def start(cls, request, target_user_id: int) -> dict:
        """
        Start impersonating a target user.

        Args:
            request: Current HttpRequest (must be from an administrator)
            target_user_id: PK of the user to impersonate

        Returns:
            dict with success, message, redirect_url, user
        """
        current_user = request.user

        if not cls.can_impersonate(current_user):
            return {'success': False, 'message': 'Permission denied.'}

        # Decode ID if compatibility wrapped or string
        from core.services.compat_service import CompatibilityService
        _, real_id = CompatibilityService.decode_id(target_user_id)

        try:
            real_id = int(real_id)
        except (ValueError, TypeError):
            return {'success': False, 'message': 'Invalid user ID.'}

        # Cannot impersonate yourself
        if current_user.pk == real_id:
            return {'success': False, 'message': 'Cannot impersonate yourself.'}

        UserModel = get_user_model()
        try:
            target_user = UserModel.objects.get(pk=real_id)
        except UserModel.DoesNotExist:
            return {'success': False, 'message': 'Target user not found.'}

        # Cannot impersonate another super admin or pro user
        if target_user.is_superuser or target_user.role in ('super_admin', 'pro_user', 'prime_admin'):
            return {'success': False, 'message': 'Cannot impersonate another administrator.'}

        # Cannot chain impersonations
        if cls.is_impersonating(request):
            return {'success': False, 'message': 'Already in an impersonation session. Stop the current session first.'}

        if not target_user.is_active:
            return {'success': False, 'message': 'Cannot impersonate an inactive user.'}

        # Save original admin info before login() flushes the session
        original_user_id = current_user.pk
        original_user_name = current_user.get_full_name() or current_user.username

        # Impersonation should not revoke the target user's real device sessions.
        request._skip_device_session_enforcement = True
        saved_keys = {
            k: request.session[k] for k in ('mobile_auth_ok', '_auth_login_surface', 'selected_role')
            if k in request.session
        }

        # Switch to target user — login() flushes and recreates the session
        login(request, target_user, backend='django.contrib.auth.backends.ModelBackend')
        for k, v in saved_keys.items():
            request.session[k] = v

        # Set impersonation markers in the new session (both key formats for backward compatibility)
        request.session[cls.SESSION_KEY] = original_user_id
        request.session[cls.SESSION_NAME_KEY] = original_user_name
        request.session['_impersonator_id'] = original_user_id
        request.session['_impersonator_name'] = original_user_name
        request.session['selected_role'] = target_user.role
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
            "Impersonation started: admin=%s (ID:%d) → target=%s (ID:%d, role=%s)",
            original_user_name, original_user_id,
            target_user.username, target_user.pk, target_user.role,
        )

        full_name = target_user.get_full_name() or target_user.username

        return {
            'success': True,
            'message': f'Now impersonating {full_name} ({target_user.role})',
            'redirect_url': redirect_url,
            'user': {
                'id': target_user.id,
                'username': target_user.username,
                'email': target_user.email,
                'role': target_user.role,
                'full_name': full_name,
            }
        }

    @classmethod
    def stop(cls, request, next_url: str = '') -> dict:
        """
        Stop impersonating and return to the Administrator session.

        Args:
            request: Current HttpRequest
            next_url: Optional URL to redirect to after stopping

        Returns:
            dict with success, message, redirect_url
        """
        original_user_id = request.session.get(cls.SESSION_KEY) or request.session.get('_impersonator_id')
        if not original_user_id:
            return {'success': False, 'message': 'Not currently impersonating.'}

        UserModel = get_user_model()
        from core.services.compat_service import CompatibilityService
        _, real_orig_id = CompatibilityService.decode_id(original_user_id)
        try:
            original_user = UserModel.objects.using('default').get(pk=real_orig_id)
        except UserModel.DoesNotExist:
            logger.error("Impersonate stop: Original account not found for user ID %s", real_orig_id)
            return {'success': False, 'message': 'Original administrator account not found.'}

        impersonated_name = request.user.get_full_name() or request.user.username

        # Remove all impersonation markers
        for k in (cls.SESSION_KEY, cls.SESSION_NAME_KEY, '_impersonator_id', '_impersonator_name'):
            if k in request.session:
                del request.session[k]

        # Clear any thread-local guest sandbox routing context so login updates default DB
        try:
            from core.db_router import GuestSandboxRouter
            GuestSandboxRouter.clear_guest_db()
        except Exception:
            pass
        original_user._state.db = 'default'

        # Returning from impersonation should also avoid side-effect session revocations.
        request._skip_device_session_enforcement = True
        saved_keys = {
            k: request.session[k] for k in ('mobile_auth_ok', '_auth_login_surface', 'selected_role')
            if k in request.session
        }

        # Switch back to original administrator
        login(request, original_user, backend='django.contrib.auth.backends.ModelBackend')
        for k, v in saved_keys.items():
            request.session[k] = v
        # Ensure selected_role is restored to the administrator's genuine role
        request.session['selected_role'] = getattr(original_user, 'role', 'super_admin')
        request.session.modified = True
        request.session.save()

        try:
            from core.middleware import PermissionValidationMiddleware
            PermissionValidationMiddleware.seed_session_fingerprint(request)
        except Exception:
            pass

        logger.info(
            "Impersonation stopped: admin=%s (ID:%d) was impersonating %s",
            original_user.username, original_user.pk, impersonated_name,
        )

        from .services import DASHBOARD_URLS
        redirect_url = DASHBOARD_URLS.get(getattr(original_user, 'role', 'super_admin'), '/panel/')
        
        # If a safe next_url is provided, use it
        if next_url and next_url.startswith('/'):
            redirect_url = next_url

        return {
            'success': True,
            'message': 'Impersonation session ended. Returned to Administrator account.',
            'redirect_url': redirect_url,
        }

    @classmethod
    def get_impersonation_targets(cls, request) -> list:
        """
        Get list of users the Administrator can impersonate.
        Returns a list of dicts with id, rawId, name, email, role, role_display, client_name.
        """
        if not cls.can_impersonate(request.user):
            return []

        UserModel = get_user_model()
        users = (
            UserModel.objects
            .filter(is_active=True)
            .exclude(pk=request.user.pk)
            .exclude(is_superuser=True)
            .exclude(role__in=['pro_user', 'super_admin', 'prime_admin'])
            .select_related('organisation_profile', 'assistant_profile__organisation', 'operator_profile')
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
                client_name = getattr(getattr(assistant_profile, 'organisation', None) or getattr(assistant_profile, 'client', None), 'name', '') or ''
            elif u.role == 'operator':
                client_name = ''

            result.append({
                'id': u.id,
                'rawId': u.id,
                'user_id': u.id,
                'name': name,
                'username': u.username,
                'email': u.email or '',
                'role': u.role,
                'role_display': dict(UserModel.ROLE_CHOICES).get(u.role, u.role),
                'is_active': u.is_active,
                'client_name': client_name,
            })

        return result
