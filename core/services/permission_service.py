"""
Permission Service Module — SINGLE AUTHORITY FOR ALL PERMISSION DECISIONS.

All permission checks in the entire application MUST go through
PermissionService.has() (or the convenience aliases).  No view, template,
service, or middleware should inspect perm_* booleans directly.

Contains: Role-based permission checking, client scoping, decorators
"""
import logging
from typing import Dict, Optional, List
from functools import wraps

from django.core.cache import cache as _cache
from django.http import JsonResponse
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


class PermissionService:
    """
    Single authority for all permission decisions.

    Usage:
        # Primary API — use everywhere
        PermissionService.has(user, 'perm_idcard_add')
        PermissionService.has(user, 'perm_idcard_add', client=some_client)

        # Template context
        context = PermissionService.get_permission_context(user)

    Roles:
        super_admin  — always True
        admin_staff  — must have perm on Staff model + be assigned to client
        client       — must have perm on Client model + client active
        client_staff — double-gated: Staff perm AND parent Client perm
    """

    PERMISSION_CONTEXT_CACHE_TTL = 30
    ACCESSIBLE_CLIENT_IDS_CACHE_TTL = 30

    # ==================== Known Permission Keys ====================

    IDCARD_CLIENT_PERMISSIONS = [
        'perm_idcard_client_list',
    ]

    ADMIN_USER_MANAGEMENT_PERMISSIONS = [
        'perm_manage_client_staff',
        'perm_manage_photographer_staff',
    ]

    IDCARD_SETTING_PERMISSIONS = [
        'perm_idcard_setting_list', 'perm_idcard_setting_add',
        'perm_idcard_setting_edit', 'perm_idcard_setting_delete',
        'perm_idcard_setting_status',
    ]

    IDCARD_LIST_PERMISSIONS = [
        'perm_idcard_pending_list', 'perm_idcard_verified_list',
        'perm_idcard_approved_list', 'perm_idcard_download_list',
        'perm_idcard_pool_list',
        'perm_idcard_reprint_list',
    ]
    
    REPRINT_LIST_PERMISSIONS = [
        'perm_reprint_request_list',
        'perm_confirmed_list',
    ]

    IDCARD_ACTION_PERMISSIONS = [
        'perm_idcard_add', 'perm_idcard_edit', 'perm_idcard_delete',
        'perm_idcard_info', 'perm_idcard_approve', 'perm_idcard_verify',
        'perm_idcard_bulk_upload', 'perm_idcard_bulk_download',
        'perm_idcard_download_image_rename_mode', 'perm_idcard_download_image_generate_mode',
        'perm_idcard_bulk_reupload',
        'perm_idcard_updated_at',
        'perm_idcard_delete_from_pool', 'perm_delete_all_idcard',
        'perm_reupload_idcard_image', 'perm_idcard_retrieve',
        'perm_idcard_upgrade_all',
        'perm_idcard_clear_pending_path',
    ]

    MANAGE_PANEL_PERMISSIONS = [
        'perm_manage_panel_backup',
        'perm_manage_panel_email',
    ]

    MOBILE_APP_PERMISSIONS = [
        'perm_mobile_app',
    ]

    ACCOUNT_SECURITY_PERMISSIONS = [
        'perm_set_temp_password',
    ]

    PRO_FEATURE_PERMISSIONS = [
        'perm_pro_user_options',        # User Options (Impersonation)
        'perm_pro_log_deletion_guard',  # Log Deletion Guard
        'perm_pro_data_deletion_guard', # Data Deletion Guard
    ]

    # Permissions that operators should always have regardless of their
    # per-profile toggles. Keep this limited to legacy operational
    # access only; pro features are reserved for pro_user and super_admin.
    OPERATOR_AUTO_PERMS: set = {
        'perm_reupload_idcard_image',
    }

    # All known perm keys (computed once at class-load time)
    ALL_PERMISSION_KEYS: List[str] = (
        IDCARD_CLIENT_PERMISSIONS
        + ADMIN_USER_MANAGEMENT_PERMISSIONS
        + IDCARD_SETTING_PERMISSIONS
        + IDCARD_LIST_PERMISSIONS
        + REPRINT_LIST_PERMISSIONS
        + IDCARD_ACTION_PERMISSIONS
        + MANAGE_PANEL_PERMISSIONS
        + MOBILE_APP_PERMISSIONS
        + ACCOUNT_SECURITY_PERMISSIONS
        + PRO_FEATURE_PERMISSIONS
    )

    # Perms intentionally absent from Operator/Assistant profiles
    OPERATOR_BLOCKED_PERMS: set = {
        'perm_delete_all_idcard',  # super_admin only
    }

    # Perms that are NEVER available to client / assistant roles.
    CLIENT_BLOCKED_PERMS: set = {
        # perm_idcard_bulk_upload  — now allowed for clients (gated by toggle)
        'perm_idcard_bulk_reupload',  # admin/operator-only (not available to client roles)
        'perm_delete_all_idcard',    # super_admin-only
        'perm_reupload_idcard_image',
        # Panel management (operator-only)
        'perm_manage_panel_backup',
        'perm_manage_panel_email',
        # 'perm_manage_client_staff' removed to allow client role access
        'perm_idcard_clear_pending_path',
    }

    # Map UI boolean perm keys to Django permissions for operators
    OPERATOR_DJANGO_PERM_MAP = {
        'perm_idcard_pending_list': 'can_view_idcard_data',
        'perm_idcard_verified_list': 'can_view_idcard_data',
        'perm_idcard_approved_list': 'can_view_approved_list',
        'perm_idcard_download_list': 'can_view_download_list',
        'perm_idcard_pool_list': 'can_view_idcard_data',
        'perm_idcard_reprint_list': 'can_view_idcard_data',
        'perm_reprint_request_list': 'can_view_idcard_data',
        'perm_idcard_info': 'can_view_idcard_data',
        'perm_idcard_retrieve': 'can_view_idcard_data',
        'perm_idcard_add': 'can_add_idcard_data',
        'perm_idcard_edit': 'can_edit_idcard_data',
        'perm_idcard_updated_at': 'can_edit_idcard_data',
        'perm_idcard_delete': 'can_delete_idcard_data',
        'perm_idcard_delete_from_pool': 'can_delete_idcard_data',
        'perm_idcard_verify': 'can_verify_idcard',
        'perm_idcard_approve': 'can_approve_idcard',
        'perm_idcard_bulk_download': 'can_bulk_download',
        'perm_idcard_bulk_upload': 'can_bulk_upload',
        'perm_idcard_setting_list': 'can_view_idcard_settings',
    }

    # Sensitive permissions that assistant can never hold
    CLIENT_ASSISTANT_BLOCKED_PERMS: set = {
        'perm_manage_client_staff',       # Assistants cannot manage other staff
        'perm_manage_photographer_staff', # Assistants cannot manage photographers
        'perm_idcard_setting_add',        # Assistants cannot create new tables
        'perm_idcard_setting_delete',     # Assistants cannot delete tables
        'perm_idcard_setting_edit',       # Assistants cannot edit table structure
        'perm_manage_panel_backup',       # Admin-only
        'perm_manage_panel_email',        # Admin-only
        'perm_idcard_approved_list',      # Assistants cannot see approved list
        'perm_idcard_download_list',      # Assistants cannot see download list
        'perm_idcard_approve',            # Assistants cannot approve cards
    }

    # Status → list-permission mapping (shared across views)
    STATUS_LIST_PERM_MAP = {
        'pending': 'perm_idcard_pending_list',
        'verified': 'perm_idcard_verified_list',
        'approved': 'perm_idcard_approved_list',
        'download': 'perm_idcard_download_list',
        'pool': 'perm_idcard_pool_list',
    }

    # Status → action-permission mapping (for status transitions)
    STATUS_ACTION_PERM_MAP = {
        'pending': 'perm_idcard_verify',
        'verified': 'perm_idcard_verify',
        'approved': 'perm_idcard_approve',
        'download': 'perm_idcard_approve',
        'pool': 'perm_idcard_delete',
    }

    # ==================== Role Checks ====================

    @staticmethod
    def is_pro_user(user) -> bool:
        """Check if user is the pro user."""
        if not getattr(user, 'is_authenticated', False):
            return False
        return getattr(user, 'role', None) == 'pro_user'

    @staticmethod
    def can_manage_pro_features(user) -> bool:
        """Return True if the user may manage or operate pro feature management.

        This is broader than `is_pro_user` and allows the Pro User and
        Super Admin roles to perform management tasks (assignments, toggles).
        """
        if not getattr(user, 'is_authenticated', False):
            return False
        return user.role in {'pro_user', 'super_admin'} or getattr(user, 'is_superuser', False)

    @staticmethod
    def is_super_admin(user) -> bool:
        """Check if user is super admin (or pro_user which has all super_admin powers)."""
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        return getattr(user, 'is_superuser', False) or getattr(user, 'role', None) in ('super_admin', 'pro_user')

    @staticmethod
    def is_operator(user) -> bool:
        """Check if user is operator."""
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        return getattr(user, 'role', None) in ('operator', 'admin_staff')

    @staticmethod
    def is_admin_staff(user) -> bool:
        """Check if user is admin staff (operator)."""
        return PermissionService.is_operator(user)

    @staticmethod
    def is_photographer(user) -> bool:
        """Check if user is photographer."""
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        return getattr(user, 'role', None) == 'photographer'

    @staticmethod
    def is_client(user) -> bool:
        """Check if user is a client."""
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        return getattr(user, 'role', None) in ('client', 'guest_prime_manager')

    @staticmethod
    def is_guest_user(user) -> bool:
        """Check if user is a guest/sandbox account."""
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        return getattr(user, 'role', None) == 'guest_prime_manager'

    @staticmethod
    def is_assistant(user) -> bool:
        """Check if user is assistant."""
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        return getattr(user, 'role', None) in ('assistant', 'client_staff')

    @staticmethod
    def is_client_staff(user) -> bool:
        """Check if user is client staff (assistant)."""
        return PermissionService.is_assistant(user)

    @staticmethod
    def is_any_admin(user) -> bool:
        """Check if user is super_admin/pro_user, operator, or photographer."""
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        # Keep this aligned with is_super_admin() so pro_user is never excluded.
        return PermissionService.is_super_admin(user) or getattr(user, 'role', None) in ('operator', 'admin_staff', 'photographer')

    @staticmethod
    def is_client_role(user) -> bool:
        """Check if user is client or assistant."""
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        return getattr(user, 'role', None) in ('client', 'guest_prime_manager', 'assistant', 'client_staff')

    # ==================== Profile Lookup ====================

    @classmethod
    def _revalidation_marker(cls, user) -> str:
        """Read a marker that changes whenever access-relevant models change."""
        try:
            from core.services.session_revalidation import get_user_revalidation_marker

            marker = get_user_revalidation_marker(getattr(user, 'pk', None))
            return str(marker or '')
        except Exception:
            return ''

    @classmethod
    def _permission_context_cache_key(cls, user) -> str:
        marker = cls._revalidation_marker(user)
        role = str(getattr(user, 'role', '') or '')
        return f'perm:ctx:v1:{user.pk}:{role}:{marker}'

    @classmethod
    def _accessible_client_ids_cache_key(cls, user) -> str:
        marker = cls._revalidation_marker(user)
        role = str(getattr(user, 'role', '') or '')
        return f'perm:client_ids:v1:{user.pk}:{role}:{marker}'

    @classmethod
    def _get_or_create_photographer_profile(cls, user):
        """Get or create the Photographer profile for the photographer user.

        Always fetches fresh from the DB to avoid returning a stale cached
        instance (e.g., perm_mobile_app=False) that was loaded before the
        admin saved updated permissions.
        """
        from core.models import Photographer
        try:
            # Direct DB lookup — bypasses any cached instance on the user object
            profile = Photographer.objects.get(user_id=user.id)
            return profile
        except Photographer.DoesNotExist:
            if not cls.is_photographer(user):
                return None
            # Profile doesn't exist yet — create one with all permissions enabled
            try:
                profile, _ = Photographer.objects.get_or_create(
                    user_id=user.id,
                    defaults={
                        'perm_mobile_app': True,
                        'perm_idcard_pending_list': True,
                        'perm_idcard_verified_list': True,
                        'perm_idcard_add': True,
                        'perm_idcard_info': True,
                        'perm_idcard_bulk_download': True,
                    }
                )
                return profile
            except Exception as e:
                logger.error(
                    "Failed to get_or_create photographer profile for user %s: %s",
                    getattr(user, 'username', '?'), e,
                )
                return None
        except Exception as e:
            logger.error(
                "Failed to fetch photographer profile for user %s: %s",
                getattr(user, 'username', '?'), e,
            )
            return None

    @classmethod
    def get_profile(cls, user):
        """
        Get the permission-bearing profile for a user.
        """
        if cls.is_super_admin(user):
            return None
        if cls.is_operator(user):
            return getattr(user, 'operator_profile', None)
        if cls.is_photographer(user):
            return cls._get_or_create_photographer_profile(user)
        if cls.is_client(user):
            return getattr(user, 'client_profile', None)
        if cls.is_assistant(user):
            return getattr(user, 'assistant_profile', None)
        return None

    # ==================== PRIMARY API ====================

    @classmethod
    def has(cls, user, perm_key: str, client=None, table=None, **kwargs) -> bool:
        """
        **Single authority** for all permission decisions.
        Handles both 'client' objects and 'client_id' (int/str) for convenience.

        Args:
            user:      User instance (from request.user or model)
            perm_key:  Permission field name, e.g. 'perm_idcard_add'
            client:    Optional Client instance for scope validation
                       (admin_staff must be assigned to this client)

        Returns:
            True if the user holds the permission, False otherwise.
        """
        try:
            return cls._has_impl(user, perm_key, client=client, table=table, **kwargs)
        except Exception as exc:
            logger.exception("PermissionService.has CRASHED for user %s perm %s: %s", getattr(user, 'pk', 'unknown'), perm_key, exc)
            # Fail closed on error to prevent unauthorized access
            return False

    @classmethod
    def _has_impl(cls, user, perm_key: str, client=None, table=None, **kwargs) -> bool:
        """Internal implementation of has() with error handling wrapper."""
        # --- 0. Resolve client object if passed as ID ---
        client_obj = client
        if client_obj is not None and isinstance(client_obj, (int, str)):
            from client.models import Client
            try:
                client_obj = Client.objects.get(id=client_obj)
            except (Client.DoesNotExist, ValueError, TypeError):
                client_obj = None

        # --- 1. Defensive: unauthenticated ---
        if not user.is_authenticated:
            return False

        # --- Defensive: inactive user ---
        if not user.is_active:
            return False

        # --- Permissions blocked for client / assistant roles ---
        if perm_key in cls.CLIENT_BLOCKED_PERMS:
            if cls.is_client(user) or cls.is_assistant(user):
                return False

        # --- Permissions auto-granted to operator/photographer (no profile toggle needed) ---
        if cls.is_operator(user) and perm_key in cls.OPERATOR_AUTO_PERMS:
            return True
        if cls.is_photographer(user) and perm_key in cls.OPERATOR_AUTO_PERMS:
            return True

        # --- 1. Super admin always passes ---
        if cls.is_super_admin(user):
            return True

        # --- 2. operator / photographer ---
        if cls.is_operator(user) or cls.is_photographer(user):
            profile = cls.get_profile(user)
            if not profile:
                logger.warning("PermissionService.has: user %s has no profile", user.pk)
                return False
            if not user.is_active:
                return False
            if perm_key in cls.PRO_FEATURE_PERMISSIONS:
                return False
            if perm_key in cls.OPERATOR_BLOCKED_PERMS:
                return False

            # Additional block: Photographer can ONLY have specific permissions (view/add, app)
            if cls.is_photographer(user):
                ALLOWED_PHOTOGRAPHER_PERMS = {
                    'perm_mobile_app',
                    'perm_idcard_add',
                    'perm_idcard_info',
                    'perm_idcard_retrieve',
                    'perm_idcard_pending_list',
                    'perm_idcard_verified_list',
                    'perm_idcard_pool_list',
                    'perm_idcard_bulk_download',
                }
                if client_obj is not None:
                    if client_obj.id not in cls.get_accessible_client_ids(user):
                        return False
                if perm_key not in ALLOWED_PHOTOGRAPHER_PERMS:
                    return False
                if hasattr(profile, perm_key):
                    return bool(getattr(profile, perm_key, False))
                return True

            # Check Django permission mapping first
            has_mapped_perm = False
            if perm_key in cls.OPERATOR_DJANGO_PERM_MAP:
                django_perm = cls.OPERATOR_DJANGO_PERM_MAP[perm_key]
                has_mapped_perm = user.has_perm(f'core.{django_perm}') or user.has_perm(django_perm)
            
            # If no mapped perm (or failed), fallback to boolean fields
            if not has_mapped_perm:
                if not hasattr(profile, perm_key):
                    logger.warning("PermissionService.has: unknown perm_key '%s' for user %s", perm_key, user.pk)
                    return False
                if not getattr(profile, perm_key, False):
                    return False
            # Scope check: if a client is supplied, operator/photographer must be assigned to it
            if client_obj is not None:
                if client_obj.id not in cls.get_accessible_client_ids(user):
                    return False
            return True

        # --- 3. client ---
        if cls.is_client(user):
            client_profile = client_obj or getattr(user, 'client_profile', None)

            if not client_profile:
                logger.warning("PermissionService.has: client user %s has no client_profile", user.pk)
                return False

            # Security: if client_obj was provided, it MUST match the user's profile
            if client_obj and client_profile.id != client_obj.id:
                return False

            if client_profile.status != 'active':
                return False

            if cls.is_guest_user(user) and perm_key == 'perm_mobile_app':
                return True

            # ID card lists are controlled by the client profile toggle.
            if perm_key in cls.IDCARD_LIST_PERMISSIONS:
                return bool(getattr(client_profile, perm_key, False))

            # Client management access is also controlled by the client profile toggle.
            if perm_key in cls.IDCARD_CLIENT_PERMISSIONS or perm_key == 'perm_manage_client_staff':
                if perm_key == 'perm_manage_client_staff':
                    return bool(getattr(client_profile, 'perm_idcard_client_list', False))
                if hasattr(client_profile, perm_key):
                    return bool(getattr(client_profile, perm_key, False))
                return False

            if not hasattr(client_profile, perm_key):
                logger.warning("PermissionService.has: unknown perm_key '%s' for client user %s", perm_key, user.pk)
                return False

            return bool(getattr(client_profile, perm_key, False))

        # --- 4. assistant (double-gated) ---
        if cls.is_assistant(user):
            if perm_key in cls.CLIENT_ASSISTANT_BLOCKED_PERMS:
                return False
            assistant = getattr(user, 'assistant_profile', None)
            if not assistant:
                logger.warning("PermissionService.has: assistant user %s has no assistant_profile", user.pk)
                return False
            # Security: if client_obj was provided, it MUST match the assistant's client
            if client_obj and assistant.client_id != client_obj.id:
                return False

            if not assistant.client:
                logger.warning("PermissionService.has: assistant user %s has no assigned client", user.pk)
                return False

            if assistant.client.status != 'active':
                return False
            # ID card lists are auto-granted to active assistants (respecting assistant-level toggle)
            if perm_key in cls.IDCARD_LIST_PERMISSIONS:
                # Assistant perm check
                if hasattr(assistant, perm_key):
                    return bool(getattr(assistant, perm_key, False))
                return True  # fallback: grant if not explicitly blocked on assistant

            # Assistant perm
            if hasattr(assistant, perm_key):
                assistant_value = getattr(assistant, perm_key, False)
            else:
                # Perm not on Assistant model — log and fail closed
                logger.warning(
                    "PermissionService.has: perm_key '%s' not on Assistant model for assistant user %s",
                    perm_key, user.pk
                )
                assistant_value = False  # fail closed: deny if not explicitly defined



            # Client perm
            if hasattr(assistant.client, perm_key):
                client_value = getattr(assistant.client, perm_key, False)
            else:
                logger.warning("PermissionService.has: unknown perm_key '%s' for assistant user %s (client %s)", perm_key, user.pk, assistant.client_id)
                return False
            return bool(assistant_value and client_value)

        # Unknown role
        logger.warning("PermissionService.has: user %s has unrecognised role '%s'", user.pk, getattr(user, 'role', '?'))
        return False

    # Backward-compat alias — all existing callers still work
    has_permission = has

    # ==================== Client Scope Checking ====================

    @classmethod
    def get_accessible_clients(cls, user, base_qs=None):
        """
        Return Client queryset scoped to user's access level.
        super_admin → all clients; operator/photographer → assigned clients only; others → none.
        If base_qs is provided, results are intersected with it.
        """
        from client.models import Client
        qs = base_qs if base_qs is not None else Client.objects.all()
        if not user.is_authenticated:
            return qs.none()
        if cls.is_super_admin(user):
            return qs
        if cls.is_operator(user) or cls.is_photographer(user):
            assigned_ids = cls.get_accessible_client_ids(user)
            return qs.filter(id__in=assigned_ids)
        return qs.none()

    @classmethod
    def can_access_client(cls, user, client_id: int) -> bool:
        """
        Check if user can access a specific client's data.
        Works for all roles.
        """
        if not user.is_authenticated:
            return False
        if cls.is_super_admin(user):
            return True
        if cls.is_operator(user) or cls.is_photographer(user):
            return int(client_id) in cls.get_accessible_client_ids(user)
        if cls.is_client(user):
            client_profile = getattr(user, 'client_profile', None)
            return client_profile is not None and client_profile.id == client_id
        if cls.is_assistant(user):
            assistant = getattr(user, 'assistant_profile', None)
            return assistant is not None and assistant.client_id == client_id
        return False

    @classmethod
    def get_accessible_client_ids(cls, user) -> List[int]:
        """Return list of client IDs the user may access."""
        cached_ids = getattr(user, '_cached_accessible_client_ids', None)
        if cached_ids is not None:
            return cached_ids

        if not user.is_authenticated:
            return []
        if cls.is_super_admin(user):
            user._cached_accessible_client_ids = []
            return []  # Empty means "all" for super_admin — caller should handle
        if cls.is_operator(user) or cls.is_photographer(user):
            cache_key = cls._accessible_client_ids_cache_key(user)
            cached = _cache.get(cache_key)
            if cached is not None:
                ids = [int(cid) for cid in cached]
                user._cached_accessible_client_ids = ids
                return ids

            if cls.is_photographer(user):
                photo = cls.get_profile(user)
                if photo:
                    from django.utils import timezone
                    from django.db.models import Q
                    now = timezone.now()
                    ids = list(
                        photo.photographer_assignments.filter(
                            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
                        ).values_list('client_id', flat=True)
                    )
                else:
                    ids = []
            else:
                op = getattr(user, 'operator_profile', None)
                if op:
                    ids = list(op.assigned_clients.values_list('id', flat=True))
                else:
                    ids = []

            _cache.set(cache_key, ids, cls.ACCESSIBLE_CLIENT_IDS_CACHE_TTL)
            user._cached_accessible_client_ids = ids
            return ids
        if cls.is_client(user):
            cp = getattr(user, 'client_profile', None)
            ids = [cp.id] if cp else []
            user._cached_accessible_client_ids = ids
            return ids
        if cls.is_assistant(user):
            assistant = getattr(user, 'assistant_profile', None) or getattr(user, 'staff_profile', None)
            ids = [assistant.client_id] if assistant and assistant.client_id else []
            user._cached_accessible_client_ids = ids
            return ids

        user._cached_accessible_client_ids = []
        return []

    # ==================== Template Context ====================

    @classmethod
    def get_permission_context(cls, user) -> Dict[str, bool]:
        """
        Build dict of all permission flags + role booleans for template injection.
        Called by context_processors.permissions().
        """
        if not user.is_authenticated:
            context = {
                'is_pro_user': False,
                'is_super_admin': False,
                'is_operator': False,
                'is_photographer': False,
                'is_client': False,
                'is_guest_user': False,
                'is_assistant': False,
                'user_role': None,
            }
            for perm in cls.ALL_PERMISSION_KEYS:
                context[perm] = False
            context['user_permissions'] = {perm: False for perm in cls.ALL_PERMISSION_KEYS}
            return context

        cache_key = cls._permission_context_cache_key(user)
        cached = _cache.get(cache_key)
        if isinstance(cached, dict):
            ctx = dict(cached)
            if isinstance(cached.get('user_permissions'), dict):
                ctx['user_permissions'] = dict(cached['user_permissions'])
            return ctx

        is_sa = cls.is_super_admin(user)
        is_op = cls.is_operator(user)
        is_photo = cls.is_photographer(user)
        is_cl = cls.is_client(user)
        is_guest = cls.is_guest_user(user)
        is_as = cls.is_assistant(user)

        context: Dict[str, bool] = {
            'is_pro_user': cls.is_pro_user(user),
            'is_super_admin': is_sa,
            'is_operator': is_op,
            'is_admin_staff': is_op,
            'is_photographer': is_photo,
            'is_client': is_cl,
            'is_guest_user': is_guest,
            'is_assistant': is_as,
            'is_admin_or_operator': (is_sa or is_op),
            'is_client_viewer': (is_cl or is_guest or is_as),
            'user_role': user.role if user.is_authenticated else None,
        }

        # Super admin gets all permissions True
        if is_sa:
            for perm in cls.ALL_PERMISSION_KEYS:
                context[perm] = True
            if not cls.is_pro_user(user):
                context['perm_pro_log_deletion_guard'] = False
        elif is_op:
            op = getattr(user, 'operator_profile', None)
            for perm in cls.ALL_PERMISSION_KEYS:
                if perm in cls.PRO_FEATURE_PERMISSIONS:
                    context[perm] = False
                elif perm in cls.OPERATOR_AUTO_PERMS:
                    context[perm] = True
                elif perm in cls.OPERATOR_BLOCKED_PERMS:
                    context[perm] = False
                elif perm in cls.OPERATOR_DJANGO_PERM_MAP:
                    django_perm = cls.OPERATOR_DJANGO_PERM_MAP[perm]
                    if user.has_perm(f'core.{django_perm}') or user.has_perm(django_perm):
                        context[perm] = True
                    else:
                        context[perm] = bool(getattr(op, perm, False)) if op and hasattr(op, perm) else False
                elif op and hasattr(op, perm):
                    context[perm] = bool(getattr(op, perm, False))
                else:
                    context[perm] = False
        elif is_photo:
            profile = cls.get_profile(user)
            ALLOWED_PHOTOGRAPHER_PERMS = {
                'perm_mobile_app',
                'perm_idcard_add',
                'perm_idcard_info',
                'perm_idcard_retrieve',
                'perm_idcard_pending_list',
                'perm_idcard_verified_list',
                'perm_idcard_pool_list',
                'perm_idcard_bulk_download',
            }
            for perm in cls.ALL_PERMISSION_KEYS:
                if perm in ALLOWED_PHOTOGRAPHER_PERMS:
                    if profile and hasattr(profile, perm):
                        context[perm] = bool(getattr(profile, perm, False))
                    else:
                        context[perm] = True
                else:
                    context[perm] = False
        elif is_cl:
            profile = getattr(user, 'client_profile', None)
            active = profile.status == 'active' if profile else False
            for perm in cls.ALL_PERMISSION_KEYS:
                if perm in cls.CLIENT_BLOCKED_PERMS:
                    context[perm] = False
                elif is_guest and perm == 'perm_mobile_app':
                    context[perm] = True
                elif active and profile and hasattr(profile, perm):
                    context[perm] = bool(getattr(profile, perm, False))
                elif active and profile and perm == 'perm_manage_client_staff':
                    context[perm] = bool(getattr(profile, 'perm_idcard_client_list', False))
                else:
                    context[perm] = False
        elif is_as:
            assistant = getattr(user, 'assistant_profile', None)
            client_obj = assistant.client if assistant else None
            active = client_obj and client_obj.status == 'active'
            for perm in cls.ALL_PERMISSION_KEYS:
                if perm in cls.CLIENT_BLOCKED_PERMS:
                    context[perm] = False
                    continue
                if perm in cls.CLIENT_ASSISTANT_BLOCKED_PERMS:
                    context[perm] = False
                    continue
                if not active:
                    context[perm] = False
                    continue
                assistant_val = bool(getattr(assistant, perm, False)) if hasattr(assistant, perm) else False
                client_val = bool(getattr(client_obj, perm, False)) if hasattr(client_obj, perm) else False
                context[perm] = assistant_val and client_val
        else:
            for perm in cls.ALL_PERMISSION_KEYS:
                context[perm] = False

        # Convenience composite key used by templates
        context['user_permissions'] = {
            perm: context[perm] for perm in cls.ALL_PERMISSION_KEYS
        }

        _cache.set(cache_key, context, cls.PERMISSION_CONTEXT_CACHE_TTL)
        return context

    # ==================== Convenience Methods ====================

    @classmethod
    def can_view_client_list(cls, user) -> bool:
        return cls.has(user, 'perm_idcard_client_list')

    @classmethod
    def can_view_idcard_settings(cls, user) -> bool:
        return cls.has(user, 'perm_idcard_setting_list')

    @classmethod
    def can_add_idcard(cls, user) -> bool:
        return cls.has(user, 'perm_idcard_add')

    @classmethod
    def can_edit_idcard(cls, user) -> bool:
        return cls.has(user, 'perm_idcard_edit')

    @classmethod
    def can_delete_idcard(cls, user) -> bool:
        return cls.has(user, 'perm_idcard_delete')

    @classmethod
    def can_bulk_upload(cls, user) -> bool:
        return cls.has(user, 'perm_idcard_bulk_upload')

    @classmethod
    def can_bulk_download(cls, user) -> bool:
        return cls.has(user, 'perm_idcard_bulk_download')

    @classmethod
    def can_use_image_rename_mode(cls, user) -> bool:
        return cls.has(user, 'perm_idcard_download_image_rename_mode')

    @classmethod
    def can_use_image_generate_mode(cls, user) -> bool:
        return cls.has(user, 'perm_idcard_download_image_generate_mode')

    @classmethod
    def can_approve_idcard(cls, user) -> bool:
        return cls.has(user, 'perm_idcard_approve')

    @classmethod
    def can_verify_idcard(cls, user) -> bool:
        return cls.has(user, 'perm_idcard_verify')

    @classmethod
    def can_view_status(cls, user, status: str) -> bool:
        """Check if user can view cards with a specific status."""
        perm = cls.STATUS_LIST_PERM_MAP.get(status)
        return cls.has(user, perm) if perm else False

    # ==================== Pro Feature Convenience Methods ====================

    @classmethod
    def can_use_pro_user_options(cls, user) -> bool:
        """Check if user can use User Options (impersonation)."""
        return cls.has(user, 'perm_pro_user_options') or cls.is_super_admin(user)

    @classmethod
    def can_use_pro_log_deletion_guard(cls, user) -> bool:
        """Check if user can use Log Deletion Guard."""
        # Only users with the explicit perm or `pro_user` role may use this.
        # Do NOT grant to super_admin implicitly.
        return cls.has(user, 'perm_pro_log_deletion_guard') or cls.is_pro_user(user)

    @classmethod
    def can_use_pro_data_deletion_guard(cls, user) -> bool:
        """Check if user can use Data Deletion Guard."""
        return cls.has(user, 'perm_pro_data_deletion_guard') or cls.is_super_admin(user)

    # ==================== Debug / Self-Check ====================

    @classmethod
    def debug_permissions(cls, user) -> dict:
        """
        Return a complete snapshot of the user's effective permissions.
        Intended for the /panel/api/debug/permissions/ endpoint (super_admin only).
        """
        info: dict = {
            'user_id': user.pk if user.is_authenticated else None,
            'username': user.username if user.is_authenticated else None,
            'role': getattr(user, 'role', None),
            'is_active': user.is_active if user.is_authenticated else False,
            'is_superuser': user.is_superuser if user.is_authenticated else False,
            'is_super_admin': cls.is_super_admin(user),
            'is_admin_staff': cls.is_admin_staff(user),
            'is_client': cls.is_client(user),
            'is_guest_user': cls.is_guest_user(user),
            'is_client_staff': cls.is_client_staff(user),
            'accessible_client_ids': cls.get_accessible_client_ids(user),
            'effective_permissions': {},
        }

        profile = cls.get_profile(user)
        if profile:
            info['profile_type'] = type(profile).__name__
            info['profile_id'] = profile.pk

        # Populate every known perm
        for perm in cls.ALL_PERMISSION_KEYS:
            info['effective_permissions'][perm] = cls.has(user, perm)

        return info


# ===========================================================================
# DECORATORS — standardised set (page + API)
# ===========================================================================

def _permission_denied_response(request, message='Permission denied', status=403):
    """
    Return the appropriate denied response depending on request type.
    API/AJAX → JSON 403     Page → redirect to login
    """
    is_api = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.content_type == 'application/json'
        or '/api/' in request.path
    )
    if is_api:
        return JsonResponse({'success': False, 'message': message}, status=status)
    return redirect('login')


def _auth_required_response(request):
    """Return 401/redirect for unauthenticated users."""
    is_api = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.content_type == 'application/json'
        or '/api/' in request.path
    )
    if is_api:
        return JsonResponse({'success': False, 'message': 'Authentication required'}, status=401)
    return redirect('login')


# ---------- Page decorators ----------

def require_permission(permission_name: str, redirect_url: str = None):
    """
    Page decorator — requires a specific perm via PermissionService.has().
    Falls back to redirect on denial.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return _auth_required_response(request)
            if not PermissionService.has(request.user, permission_name):
                if redirect_url:
                    return redirect(redirect_url)
                return _permission_denied_response(request)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_super_admin(view_func):
    """Page decorator — super_admin only."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _auth_required_response(request)
        if not PermissionService.is_super_admin(request.user):
            return _permission_denied_response(request, 'Super admin access required')
        return view_func(request, *args, **kwargs)
    return wrapper


def require_any_admin(view_func):
    """Page decorator — super_admin or admin_staff."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _auth_required_response(request)
        if not PermissionService.is_any_admin(request.user):
            return _permission_denied_response(request, 'Admin access required')
        return view_func(request, *args, **kwargs)
    return wrapper


def require_authenticated_role(allowed_roles: list):
    """
    Page decorator — requires user.role to be one of ``allowed_roles``.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return _auth_required_response(request)
            role = getattr(request.user, 'role', None)
            if role not in allowed_roles and not PermissionService.is_super_admin(request.user):
                return _permission_denied_response(request)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ---------- API decorators ----------

def api_require_permission(permission_name: str):
    """API decorator — requires a specific perm via PermissionService.has(). Returns JSON."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({'success': False, 'message': 'Authentication required'}, status=401)
            if not PermissionService.has(request.user, permission_name):
                logger.warning(
                    "PERMISSION_DENIED user=%s role=%s perm=%s path=%s",
                    request.user.username, getattr(request.user, 'role', '-'),
                    permission_name, request.path,
                )
                return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def api_require_any_authenticated(view_func):
    """API decorator — any authenticated user (all four roles). Returns JSON 401."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Authentication required'}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


def api_require_any_admin(view_func):
    """API decorator — super_admin or admin_staff. Returns JSON 403."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Authentication required'}, status=401)
        if not PermissionService.is_any_admin(request.user):
            logger.warning(
                "PERMISSION_DENIED user=%s role=%s required=any_admin path=%s",
                request.user.username, getattr(request.user, 'role', '-'), request.path,
            )
            return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def api_require_super_admin(view_func):
    """API decorator — super_admin only. Returns JSON 403."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Authentication required'}, status=401)
        if not PermissionService.is_super_admin(request.user):
            logger.warning(
                "PERMISSION_DENIED user=%s role=%s required=super_admin path=%s",
                request.user.username, getattr(request.user, 'role', '-'), request.path,
            )
            return JsonResponse({'success': False, 'message': 'Super admin access required'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper
