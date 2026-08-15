from django.urls import path, include, reverse
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from core.views.health import health_check
from core import views as core_views



def _protected_media_serve(request, path, document_root=None):
    """
    Serve media files with access control for sensitive directories.

    In production (DEBUG=False), protected files are served by Nginx via
    X-Accel-Redirect — Django only performs the auth check then hands off.
    Nginx must have the `location /protected-media/` block marked `internal;`
    (see deployment/nginx_example.conf).

    In development (DEBUG=True), Django's `serve()` is used as a fallback.
    """
    from django.http import HttpResponse
    from django.views.static import serve

    def _normalize_media_path(raw_path):
        parts = []
        for part in str(raw_path or '').replace('\\', '/').split('/'):
            part = part.strip()
            if not part or part == '.':
                continue
            if part == '..':
                return ''
            parts.append(part)
        return '/'.join(parts)

    rel_path = _normalize_media_path(path)
    if not rel_path:
        return HttpResponse(status=404)

    # 'adarshimg/'    - client ID card photos (personal data, most sensitive)
    # 'exports/'      - generated PDF/Excel/Word/ZIP exports
    # 'clients_imgs/' - client profile images
    # 'staff_imgs/'   - staff profile images
    # 'temp/'         - temporary upload holding area
    PROTECTED_PREFIXES = (
        'adarshimg/',
        'exports/',
        'clients_imgs/',
        'staff_imgs/',
        'temp/',
    )
    if any(rel_path.startswith(p) for p in PROTECTED_PREFIXES):
        if not request.user.is_authenticated:
            # Redirect to login, preserving the original URL in ?next=
            # so the user is returned here after successful authentication.
            login_url = reverse('accounts:login')
            return redirect_to_login(request.get_full_path(), login_url=login_url)

        from core.models import BackgroundTask
        from core.services.permission_service import PermissionService

        # Super admin/pro_user keeps unrestricted access to protected media.
        if not PermissionService.is_super_admin(request.user):
            # For card photos, enforce client ownership by folder code.
            if rel_path.startswith('adarshimg/'):
                from organisation.models import Organisation

                parts = rel_path.split('/')
                folder_code = ''
                if len(parts) >= 3 and parts[1].lower() == 'thumbs':
                    folder_code = parts[2]
                elif len(parts) >= 2:
                    folder_code = parts[1]

                client = Organisation.objects.filter(image_folder_code=folder_code).only('id').first() if folder_code else None
                if not client or not PermissionService.can_access_client(request.user, client.id):
                    return HttpResponse(status=404)

            # For async export files, only the owning user can access.
            # Check both 'exports/' and 'temp/exports/' prefixes since async
            # exports are stored under temp/exports/.
            # Normalize stored result_path to forward slashes for cross-platform
            # compatibility (os.path.relpath uses backslashes on Windows).
            elif rel_path.startswith('exports/') or rel_path.startswith('temp/exports/'):
                from django.db.models import Q
                normalized_path = rel_path.replace('\\', '/')
                owns_file = BackgroundTask.objects.filter(
                    user=request.user,
                ).filter(
                    Q(result_path=normalized_path) |
                    Q(result_path=normalized_path.replace('/', '\\'))
                ).exists()
                if not owns_file:
                    # Allow admins/operators to download exports that don't have BackgroundTask records (e.g. synchronous download-all or large image fallback on disk)
                    if PermissionService.is_any_admin(request.user):
                        owns_file = True
                
                if not owns_file:
                    return HttpResponse(status=404)

            # For all other protected folders, keep access to admins only.
            elif not PermissionService.is_any_admin(request.user):
                return HttpResponse(status=404)

    # Production with Nginx: serve via X-Accel-Redirect (zero-copy, non-blocking).
    # Requires MEDIA_USE_XACCEL=true in env AND the Nginx internal
    # /protected-media/ location block (see deployment/nginx_example.conf).
    if getattr(settings, 'MEDIA_USE_XACCEL', False):
        response = HttpResponse()
        response['X-Accel-Redirect'] = f'/protected-media/{rel_path}'
        response['Content-Type'] = ''  # let Nginx detect from file extension
        return response

    # Fallback: Django serves the file directly (dev + prod without X-Accel)
    response = serve(request, rel_path, document_root=document_root)


    return response


urlpatterns = [
    # Health check — no auth, used by load balancers / CI/CD
    path('api/health/', health_check, name='health_check'),

    # Django admin removed — project uses custom panel routes instead.

    # Local-only debug toolbar route.
    # Debug Toolbar is enabled in DEBUG mode only and helps inspect SQL/query
    # behavior without affecting production routing.
    # NOTE: the toolbar package is optional in production. Register its
    # URLs only when DEBUG is enabled and the package is importable.

    # Local-only Sentry test route. Only registered in DEBUG to avoid accidental exposure.
    # Visit /sentry-debug/ in local dev to trigger a test exception (1/0) for verification.
]

# Register debug-only routes (debug_toolbar, sentry test) only when DEBUG and not testing.
import os
import sys

def _running_tests():
    return os.getenv('RUNNING_TESTS', '').lower() in ('1', 'true', 'yes', 'on') or any(
        mod.startswith('_pytest') for mod in sys.modules
    )

if getattr(settings, 'DEBUG', False) and not _running_tests():
    # Debug toolbar: optional dependency; import only if installed.
    try:
        import debug_toolbar  # noqa: F401
    except Exception:
        pass
    else:
        urlpatterns += [
            path('__debug__/', include('debug_toolbar.urls')),
        ]

    from django.urls import path as _path

    def _trigger_error(request):
        raise ZeroDivisionError("division by zero")

    urlpatterns += [
        _path('sentry-debug/', _trigger_error),
    ]

# All canonical REST API endpoints mounted at root (no /panel/ prefix).
urlpatterns += [

    # ==================== CORE REST API (no /panel/ prefix) ====================
    # All REST API endpoints are mounted at their canonical /api/* paths.
    # The /panel/ prefixed aliases are removed — all clients use /api/* directly.
    path('', include('core.urls')),
    path('panel/', include('core.urls')),
    path('', include(('accounts.urls', 'accounts'), namespace='accounts_root')),
    path('', include(('panel.urls', 'panel'), namespace='panel_root')),
    path('panel/', include(('panel.urls', 'panel'), namespace='panel_legacy_root')),
    path('auth/', include(('accounts.urls', 'accounts'), namespace='accounts_auth_root')),
    path('organisations/', include(('organisation.urls', 'organisation'), namespace='organisations_root')),
    path('panel/client/', include(('organisation.urls', 'organisation'), namespace='panel_client_root')),
    path('client/', include(('organisation.urls', 'organisation'), namespace='client_root')),
    path('assistants/', include(('assistants.urls', 'assistants'), namespace='assistants_root')),
    path('panel/assistants/', include(('assistants.urls', 'assistants'), namespace='panel_assistants_root')),
    path('exports/', include(('exports.urls', 'exports'), namespace='exports_root')),
    path('panel/exports/', include(('exports.urls', 'exports'), namespace='panel_exports_root')),
    path('images/', include(('mediafiles.urls', 'mediafiles'), namespace='mediafiles_root')),
    path('operators/', include(('operators.urls', 'operators'), namespace='operators_root')),
    path('panel/operators/', include(('operators.urls', 'operators'), namespace='panel_operators_root')),
    path('staff/', include(('staff.urls', 'staff'), namespace='staff_root')),
    path('panel/staff/', include(('staff.urls', 'staff'), namespace='panel_staff_root')),
    path('tables/', include(('tables.urls', 'tables'), namespace='tables_root')),
    path('panel/tables/', include(('tables.urls', 'tables'), namespace='panel_tables_root')),
    path('reprint/', include(('reprintcard.urls', 'reprintcard'), namespace='reprintcard_root')),
    path('panel/reprint/', include(('reprintcard.urls', 'reprintcard'), namespace='panel_reprintcard_root')),
    path('stats/', include(('stats.urls', 'stats'), namespace='stats_root')),
    path('panel/stats/', include(('stats.urls', 'stats'), namespace='panel_stats_root')),

    # ==================== MOBILE APP DOWNLOAD LANDING (/app/*) ====================
    # Kept as HTML — web fallback for mobile users who scan QR codes and
    # don't have the native app installed. This is the only HTML served by Django.
    path('app/', core_views.mobile_download_page, name='mobile_download_page'),
    path('app/<path:dummy>/', core_views.mobile_download_page),

    # ==================== NATIVE MOBILE APP API (/api/mobile/) ====================
    path('api/mobile/', include('mobile_api.urls')),

    # ==================== DESKTOP APP API (/api/desktop/) ====================
    path('api/desktop/', include('desktop_app.urls')),

    # ==================== WEB APP PUBLIC API (/api/web/) ====================
    path('api/web/', include('web_app.urls')),
]

# Media file serving — always register the route so uploaded images/exports
# are accessible.  In production with Nginx, the reverse proxy should serve
# /media/ directly; this Django view acts as a safe fallback.
urlpatterns += [
    path('media/<path:path>', _protected_media_serve, {'document_root': settings.MEDIA_ROOT}),
]

# JSON error handlers — never return HTML for API clients
handler400 = 'core.views.errors.error_400'
handler403 = 'core.views.errors.error_403'
handler404 = 'core.views.errors.error_404'
handler500 = 'core.views.errors.error_500'


