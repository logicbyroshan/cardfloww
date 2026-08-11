"""
Context Processors — Permission & App Context

Injects permission and app context into Django template renders (index.html SPA shell).
Used by the backend to pass server-side state to the React 19 SPA shell on first load.

Context variables available:
    - is_super_admin, is_admin_staff, is_client, is_client_staff: Role checks
    - user_role: User's role string
    - All individual permissions: perm_idcard_client_list, perm_idcard_setting_list, etc.
    - PANEL_URL: Absolute URL for cross-domain links
    - APP_VERSION: Current application version
"""
import logging

from django.conf import settings
from core.services.permission_service import PermissionService


logger = logging.getLogger(__name__)


def _resolve_mobile_android_download_url(request):
    """Return the configured Android app download URL or empty string."""
    return getattr(settings, 'MOBILE_ANDROID_APP_DOWNLOAD_URL', '')


def permissions(request):
    """
    Inject permission context into all Django template renders.

    Returns dict with role flags, permission booleans, and app URLs.
    For unauthenticated users, returns empty dict with all values as False.

    Performance: caches the result on request._cached_permissions so that
    repeated calls within the same request are free.
    """
    # Always-available context (works for both authenticated and anonymous)
    base_context = {
        'PANEL_URL': getattr(settings, 'PANEL_URL', ''),
        'APP_VERSION': getattr(settings, 'APP_VERSION', 'v0.00.00'),
        'MOBILE_ANDROID_APP_DOWNLOAD_URL': _resolve_mobile_android_download_url(request),
    }

    if not request.user.is_authenticated:
        base_context.update({
            'is_pro_user': False,
            'is_super_admin': False,
            'is_admin_staff': False,
            'is_client': False,
            'is_client_staff': False,
            'is_client_admin': False,
            'is_impersonating': False,
            'impersonation_original_name': '',
            'user_role': None,
        })
        return base_context

    # Return cached result if already computed this request
    cached = getattr(request, '_cached_permissions', None)
    if cached is not None:
        return cached

    # Get all permissions from the centralized PermissionService.
    try:
        context = PermissionService.get_permission_context(request.user)
    except Exception:
        import logging as _log
        _log.getLogger(__name__).exception(
            'PermissionService.get_permission_context failed for user %s',
            request.user.pk,
        )
        context = {
            'is_pro_user': False,
            'is_super_admin': False, 'is_admin_staff': False,
            'is_client': False, 'is_client_staff': False,
            'user_role': getattr(request.user, 'role', None),
        }

    # Backward compatibility flag
    context['is_client_admin'] = context.get('is_client', False)

    # Impersonation session state
    context['is_impersonating'] = bool(request.session.get('_pro_original_user_id'))
    context['impersonation_original_name'] = request.session.get('_pro_original_user_name', '')

    # Merge base context
    context.update(base_context)

    current_client = getattr(request.user, '_cached_current_client', None)
    if current_client is None:
        try:
            if context.get('is_client'):
                current_client = getattr(request.user, 'client_profile', None)
            elif context.get('is_client_staff'):
                assistant = getattr(request.user, 'assistant_profile', None) or getattr(request.user, 'staff_profile', None)
                current_client = getattr(assistant, 'client', None) if assistant else None
        except Exception:
            current_client = None
        if current_client is not None:
            request.user._cached_current_client = current_client

    context['current_client'] = current_client

    # Cache on request for this request lifecycle
    request._cached_permissions = context

    return context
