"""Custom error pages for user-friendly navigation and support messaging."""

import logging
import re
from django.shortcuts import render, redirect
from django.conf import settings as django_settings

logger = logging.getLogger(__name__)


def _panel_prefix(request) -> str:
    """Return '/panel' for single-domain mode and '' for panel subdomain mode."""
    urlconf = str(getattr(request, 'urlconf', '') or '')
    if urlconf.endswith('config.urls_panel') or urlconf.endswith('urls_panel'):
        return ''
    return '/panel'


def _resolve_home_url(request) -> str:
    """Choose a sensible home URL based on auth role and active URL routing mode."""
    path = str(getattr(request, 'path', '') or '')
    if path.startswith('/app/'):
        return '/app/'

    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False):
        return '/'

    role = str(getattr(user, 'role', '') or '').strip().lower()
    panel_prefix = _panel_prefix(request)

    if PermissionService.is_client_role(user):
        return f'{panel_prefix}/organisations/dashboard/' if panel_prefix else '/organisations/dashboard/'
    if role in ('super_admin', 'pro_user', 'operator'):
        return f'{panel_prefix}/' if panel_prefix else '/'

    return '/'


def _is_mobile_app_error(request) -> bool:
    """Return True when the failing request belongs to the mobile app surface."""
    path = str(getattr(request, 'path', '') or '')
    if path.startswith('/app/'):
        return True

    urlconf = str(getattr(request, 'urlconf', '') or '')
    return urlconf.endswith('mobile_app.urls')


def _is_legacy_root_uuid_path(request) -> bool:
    """Return True for bare UUID-style root paths that should no longer 404."""
    path = str(getattr(request, 'path', '') or '').strip('/')
    return bool(re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', path))


def _render_error(request, *, status_code: int, title: str, heading: str, message: str):
    from django.http import JsonResponse
    # Always return JSON — the React SPA frontend handles all error display in the browser.
    # Non-API browser requests also get JSON so the SPA can show the correct error UI.
    return JsonResponse({
        'success': False,
        'message': message,
        'status_code': status_code,
        'title': title
    }, status=status_code)


def error_400(request, exception=None):
    if exception:
        logger.error("400 Bad Request: %s [Path: %s]", exception, request.path)
    
    message = 'The request could not be processed. Please try again.'
    if exception and getattr(django_settings, 'DEBUG', False):
        message = f'Bad Request: {str(exception)}'
        
    return _render_error(
        request,
        status_code=400,
        title='Bad Request',
        heading='Bad Request',
        message=message,
    )


def error_403(request, exception=None):
    return _render_error(
        request,
        status_code=403,
        title='Access Denied',
        heading='Access Denied',
        message='You do not have permission to view this page.',
    )


def error_404(request, exception=None):
    if _is_legacy_root_uuid_path(request):
        return redirect(_resolve_home_url(request))

    return _render_error(
        request,
        status_code=404,
        title='Page Not Found',
        heading='Page Not Found',
        message='This page does not exist or may have been moved.',
    )


def error_500(request):
    return _render_error(
        request,
        status_code=500,
        title='Server Error',
        heading='Something Went Wrong',
        message='We are facing a temporary issue. Please try again in a moment.',
    )


def csrf_failure(request, reason=''):
    """
    Custom CSRF failure handler.

    When the user's session has expired (most common cause of CSRF failures),
    redirect them to the login page instead of showing a dead-end error.
    For AJAX requests, return a JSON response so the frontend can redirect.
    """
    from django.http import JsonResponse

    # Backend is pure REST API — always return JSON for CSRF failures on API paths.
    is_app_path = str(getattr(request, 'path', '') or '').startswith('/app/')
    if is_app_path:
        # For mobile app web views, show a friendly page
        from django.shortcuts import render as _render
        return _render(request, 'mobile_download.html', {}, status=403)

    current_path = str(getattr(request, 'path', '') or '')
    message = 'Security token expired. Please refresh the page.' if '/auth/login/' in current_path else 'Session expired. Please log in again.'
    return JsonResponse({
        'success': False,
        'message': message,
        'force_logout': True,
    }, status=403)


def mobile_download_page(request, dummy=None):
    """
    Mobile app download landing page for /app/* routes.
    Served as HTML (the only HTML Django serves besides mobile_api views).
    Shows a download link for the CardFlow Android app.
    """
    from django.shortcuts import render as _render
    return _render(request, 'mobile_download.html', {})

