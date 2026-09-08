"""
Core Middleware Module

Contains middleware for:
- Request timing, slow-request detection, and query monitoring
- Permission validation on every request
- Session invalidation when permissions are revoked
- Active status enforcement
"""
import logging
import time
import hashlib
from urllib.parse import quote
from django.conf import settings as django_settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.http import JsonResponse
from django.urls import reverse

logger = logging.getLogger(__name__)
query_logger = logging.getLogger('slow_queries')

# Thresholds — configurable via settings.py / environment
SLOW_REQUEST_THRESHOLD = getattr(django_settings, 'SLOW_REQUEST_THRESHOLD', 1.5)
QUERY_COUNT_THRESHOLD = getattr(django_settings, 'QUERY_COUNT_THRESHOLD', 50)
SLOW_QUERY_THRESHOLD = getattr(django_settings, 'SLOW_QUERY_THRESHOLD', 0.1)

# Read-mostly polling APIs should avoid session writes to reduce DB lock
# contention while background workers are doing heavy writes.
TASK_POLLING_PATH_PREFIXES = (
    '/api/task-status/',
    '/api/task-active/',
    '/api/task-list/',
    '/api/export/status/',
)


def _is_task_polling_path(path: str) -> bool:
    if not path:
        return False
    return any(path.startswith(prefix) for prefix in TASK_POLLING_PATH_PREFIXES)


class MobileAppCSRFBypassMiddleware:
    """
    Bypasses CSRF checks for mobile app and PWA authentication APIs.
    
    This ensures that native app and PWA clients never see 'Security token expired'
    errors during login/logout/otp-verify, regardless of cookie/header state.
    
    Must be placed BEFORE CsrfViewMiddleware in settings.py.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # We check multiple path attributes to ensure coverage across different 
        # proxy/routing configurations.
        path = (request.path or '').lower()
        path_info = (request.path_info or '').lower()
        
        # Explicitly bypass CSRF for all authentication-related API endpoints.
        # This covers:
        # - /api/auth/* (Main panel APIs)
        # - /app/api/auth/* (Mobile/PWA specific APIs)
        # - /reprint/api/* (Reprint workflow APIs)
        auth_patterns = ['/api/auth/', '/app/api/', '/api/mobile/', '/api/desktop/', '/api/web/', '/auth/login', '/auth/logout', '/reprint/api/']
        
        if any(p in path for p in auth_patterns) or any(p in path_info for p in auth_patterns):
            # This is a Django internal flag that CsrfViewMiddleware respects.
            # Setting it to True tells Django to skip CSRF validation for this request.
            request._dont_enforce_csrf_checks = True
        elif getattr(django_settings, 'DEBUG', False) and (path.startswith('/api/') or path_info.startswith('/api/')):
            # In DEBUG mode, bypass CSRF for API routes so multi-device LAN & tunnel previews never fail CSRF checks
            request._dont_enforce_csrf_checks = True
        
        return self.get_response(request)



class RequestTimingMiddleware:
    """
    Logs request duration and adds Server-Timing header.
    
    - Requests slower than SLOW_REQUEST_THRESHOLD → WARNING
    - All others → DEBUG (only visible when DEBUG=True)
    - Server-Timing header visible in browser DevTools → Network → Timing tab
    
    Query counting via connection.execute_wrapper is opt-in using
    ENABLE_REQUEST_QUERY_TRACKING. Request duration timing is always tracked.
    """

    SKIP_PREFIXES = ('/static/', '/media/', '/favicon.ico')

    def __init__(self, get_response):
        self.get_response = get_response
        self._track_queries = bool(getattr(django_settings, 'ENABLE_REQUEST_QUERY_TRACKING', False))

    def __call__(self, request):
        if any(request.path.startswith(p) for p in self.SKIP_PREFIXES):
            return self.get_response(request)

        start = time.monotonic()

        if self._track_queries:
            # Full query counting is opt-in because execute wrappers add overhead.
            response = self._call_with_query_tracking(request, start)
        else:
            # Default: just time the request, no per-query wrapper
            response = self.get_response(request)
            duration = time.monotonic() - start
            duration_ms = duration * 1000
            response['Server-Timing'] = 'total;dur=%.1f' % duration_ms
            self._log_request(request, response.status_code, duration, 0, 0.0)

        return response

    def _call_with_query_tracking(self, request, start):
        """Track individual queries when query tracking is explicitly enabled."""
        from django.db import connection
        query_count = 0
        query_time = 0.0
        slow_queries = []

        def _query_callback(execute, sql, params, many, context):
            nonlocal query_count, query_time
            q_start = time.monotonic()
            result = execute(sql, params, many, context)
            q_dur = time.monotonic() - q_start
            query_count += 1
            query_time += q_dur
            if q_dur >= SLOW_QUERY_THRESHOLD:
                slow_queries.append((sql[:200], round(q_dur * 1000)))
            return result

        with connection.execute_wrapper(_query_callback):
            response = self.get_response(request)

        duration = time.monotonic() - start
        duration_ms = duration * 1000
        db_ms = query_time * 1000
        response['Server-Timing'] = (
            'total;dur=%.1f, db;dur=%.1f;desc="%d queries"'
            % (duration_ms, db_ms, query_count)
        )

        self._log_request(request, response.status_code, duration, query_count, query_time)

        for sql, ms in slow_queries:
            query_logger.warning("SLOW QUERY path=%s time=%dms sql=%s", request.path, ms, sql)

        return response

    def _log_request(self, request, status, duration, query_count, query_time):
        """Log the request at appropriate level."""
        user = getattr(request, 'user', None)
        username = getattr(user, 'username', 'anonymous') if user and getattr(user, 'is_authenticated', False) else 'anonymous'
        role = getattr(user, 'role', '-') if user and getattr(user, 'is_authenticated', False) else '-'

        msg = "method=%s path=%s status=%d duration=%.3fs user=%s role=%s queries=%d db_time=%.3fs"
        args = (request.method, request.path, status, duration, username, role, query_count, query_time)

        if query_count > QUERY_COUNT_THRESHOLD:
            logger.warning("EXCESSIVE QUERIES " + msg, *args)
            query_logger.warning(
                "EXCESSIVE QUERIES path=%s queries=%d db_time=%.3fs user=%s",
                request.path, query_count, query_time, username
            )
        elif duration >= SLOW_REQUEST_THRESHOLD:
            logger.warning("SLOW REQUEST " + msg, *args)
        else:
            logger.debug(msg, *args)


class PermissionValidationMiddleware:
    """
    Middleware to validate user permissions and active status on every request.
    
    CRITICAL SECURITY:
    - Re-fetches user data from DB to catch real-time changes
    - Logs out user immediately if account is deactivated
    - Logs out user immediately if client/staff is disabled
    - Redirects to appropriate page based on context
    
    Enforces:
    - User.is_active must be True
    - For client users: Organisation.status must be 'active'
    - For client_staff: Organisation.status must be 'active' and staff user must be active
    
    Handles paths with and without the /panel/ prefix for flexibility across 
    different deployment environments.
    """
    
    # URL suffixes that are exempt from permission checking.
    # NOTE: These used to combine a /panel/ prefix but that prefix is now removed.
    # Keep this list for backward compat in case any code still references them,
    # but the real exemption logic uses ALWAYS_EXEMPT below.
    EXEMPT_SUFFIXES: list = []

    # Paths that are ALWAYS exempt from the auth gate, regardless of anything.
    # These are the ONLY paths that bypass authentication on the backend.
    ALWAYS_EXEMPT = [
        '/static/',
        '/media/',
        '/favicon.ico',
        '/robots.txt',
        '/sitemap.xml',
        '/__debug__/',
        # Public API endpoints that must work without auth:
        '/api/health/',       # Health check (uptime monitors)
        '/health/',           # Health check alias
        '/api/auth/csrf/',    # CSRF token — SPA fetches on boot before login
        '/api/auth/login/',   # Login endpoint
        '/api/auth/pin-status/',      # Check if account has PIN configured
        '/api/auth/login-pin/',       # Authenticate with PIN
        '/api/auth/create-pin/',      # Create or set security PIN
        '/api/auth/logout/',  # Logout is idempotent — allowed unauthenticated
        '/api/auth/check-email/',     # Email lookup for multi-step login
        '/api/auth/forgot-password/', # Password reset request
        '/api/auth/verify-otp/',      # OTP verification
        '/api/auth/reset-password/',  # Password reset completion
        '/api/auth/me/',      # Used by SPA on boot to check session state
        '/api/banners/',      # Public promotional banners and ads
        '/api/v1/banners/',   # Versioned alias for promotional banners
        '/api/mobile/',       # Mobile app API (has its own token auth)
        '/api/desktop/',      # Desktop app API (has its own token / bootstrap auth)
        '/api/web/',          # Desktop PWA/web API (has its own auth)
        '/app/',              # Mobile download pages (public HTML)
    ]

    
    def __init__(self, get_response):
        self.get_response = get_response
    
    @staticmethod
    def _panel_prefix(request):
        """Return the panel URL prefix. Currently defaults to '/panel' as 
        subdomain routing is decommissioned."""
        return '/panel'
    
    @staticmethod
    def _is_panel_path(request):
        """Check if the current request is a panel API route (not static/media/mobile/app/desktop)."""
        path = request.path
        # Always exempt: static files, media, health, mobile/desktop/web API, app download pages
        exempt_prefixes = ('/static/', '/media/', '/api/health/', '/health/', '/api/mobile/', '/api/desktop/', '/api/web/', '/app/', '/favicon.ico', '/robots.txt', '/sitemap.xml')
        if path.startswith(exempt_prefixes):
            return False
        # All other paths need auth (includes /api/* panel routes)
        return True
    
    def __call__(self, request):
        # Skip for exempt URLs
        if self._is_exempt_url(request):
            return self.get_response(request)
        
        # Ensure request.user exists (should be set by AuthenticationMiddleware)
        if not hasattr(request, 'user'):
            return self.get_response(request)
        
        # Backend is pure REST API — return 401 JSON for any unauthenticated request
        # to a non-public path. The React SPA handles the login UI.
        if not request.user.is_authenticated:
            if self._is_panel_path(request):
                return JsonResponse(
                    {'authenticated': False, 'message': 'Authentication required.'},
                    status=401
                )
            return self.get_response(request)

        # Fast fail-closed for users deactivated since their last request.
        if not getattr(request.user, 'is_active', True):
            return self._force_logout(request, 'Your account has been deactivated.')

        is_task_polling = _is_task_polling_path(request.path)

        # Task polling endpoints are read-mostly and frequent. Avoid touching
        # session keys there to reduce lock contention with background tasks.
        if not is_task_polling:
            self._sync_revalidation_marker(request)

        fingerprint_result = self._validate_session_fingerprint(request)
        if fingerprint_result is not None:
            return fingerprint_result
        
        # Re-fetch user from database to get latest state
        # This catches changes made by admin while user is logged in
        validation_result = self._validate_user_access(request)
        
        if validation_result is not None:
            return validation_result
        
        # Mark successful validation timestamp in session only when stale.
        # This avoids forcing a session write on every request.
        now_ts = time.time()
        prev_ts = float(request.session.get('_pvm_last_check', 0) or 0)
        if (not is_task_polling) and (now_ts - prev_ts) >= max(float(self.REVALIDATION_INTERVAL), 1.0):
            request.session['_pvm_last_check'] = now_ts
        
        # Annotate request with role-based scope (merged from RoleScopingMiddleware)
        self._annotate_request_scope(request)
        
        return self.get_response(request)

    def _sync_revalidation_marker(self, request):
        """Force DB revalidation when a signal marked this user as changed."""
        try:
            from core.services.session_revalidation import get_user_revalidation_marker
            marker = get_user_revalidation_marker(getattr(request.user, 'pk', None))
        except Exception:
            return

        if not marker:
            return

        marker = str(marker)
        seen = str(request.session.get(self.REVALIDATION_MARKER_SESSION_KEY, '') or '')
        if marker != seen:
            request.session[self.REVALIDATION_MARKER_SESSION_KEY] = marker
            request.session['_pvm_force_recheck'] = 1
    
    def _is_exempt_url(self, request):
        """Check if URL is exempt from the authentication gate.
        
        Only paths listed in ALWAYS_EXEMPT bypass the auth check.
        Everything else requires a valid authenticated session.
        """
        path = request.path

        # Check ALWAYS_EXEMPT — exact prefix match
        for exempt in self.ALWAYS_EXEMPT:
            if path.startswith(exempt):
                return True

        return False
    # How often (seconds) to re-validate user from DB.
    # Between checks, the cached validation in the session is trusted.
    # Set to 0 to check every request (original behavior).
    REVALIDATION_INTERVAL = max(int(getattr(django_settings, 'PERMISSION_REVALIDATION_INTERVAL', 20)), 0)
    SESSION_FP_KEY = '_session_fingerprint'
    REVALIDATION_MARKER_SESSION_KEY = '_pvm_reval_marker'

    @staticmethod
    def _client_ip(request):
        """Best-effort client IP extraction for optional session fingerprint binding."""
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')

    @staticmethod
    def _normalize_ip_for_fingerprint(ip_value):
        """Normalize IP to reduce false positives from minor network changes."""
        if not ip_value:
            return ''
        if ':' in ip_value:  # IPv6
            parts = [p for p in ip_value.split(':') if p]
            return ':'.join(parts[:4])
        parts = ip_value.split('.')
        if len(parts) == 4:
            return '.'.join(parts[:3])
        return ip_value

    @staticmethod
    def _extract_stable_ua(ua_string):
        """
        Extract a stable platform + browser family from a User-Agent string.

        We intentionally omit the browser major version so that automatic
        browser updates (e.g. Chrome 126 → 127) do NOT change the fingerprint
        and do NOT force-logout users mid-session.  The combination of
        platform + browser family is still unique enough to detect session
        hijacking across fundamentally different environments.
        """
        import re
        ua = (ua_string or '').strip().lower()
        if not ua:
            return ''

        # Extract platform (Windows, Mac, Linux, Android, iPhone, iPad)
        platform = 'unknown'
        for p in ('windows', 'macintosh', 'linux', 'android', 'iphone', 'ipad'):
            if p in ua:
                platform = p
                break

        # Extract browser family only (no version) to survive auto-updates
        # Order matters: check specific browsers first before generic ones
        browser = 'other'
        patterns = [
            (r'edg[ea]?/\d+', 'edge'),
            (r'opr/\d+', 'opera'),
            (r'chrome/\d+', 'chrome'),
            (r'firefox/\d+', 'firefox'),
            (r'safari/\d+', 'safari'),
            (r'msie\s+\d+', 'ie'),
            (r'trident/.*rv:\d+', 'ie'),
        ]
        for pattern, name in patterns:
            if re.search(pattern, ua):
                browser = name
                break

        return f'{platform}|{browser}'

    @classmethod
    def build_session_fingerprint(cls, request):
        """Build deterministic fingerprint from stable browser identity (+ optional coarse IP)."""
        ua_raw = (request.META.get('HTTP_USER_AGENT', '') or '').strip()
        ua_part = cls._extract_stable_ua(ua_raw)

        ip_part = ''
        if getattr(django_settings, 'SESSION_FINGERPRINT_INCLUDE_IP', False):
            ip_part = cls._normalize_ip_for_fingerprint(cls._client_ip(request))

        raw = f'{ua_part}|{ip_part}'
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    @classmethod
    def seed_session_fingerprint(cls, request):
        """Initialize session fingerprint immediately after auth-context changes."""
        if not getattr(django_settings, 'SESSION_FINGERPRINT_ENABLED', False):
            return
        if not request.META.get('HTTP_USER_AGENT'):
            return
        request.session[cls.SESSION_FP_KEY] = cls.build_session_fingerprint(request)

    SESSION_FP_GRACE_KEY = '_session_fp_grace'

    def _validate_session_fingerprint(self, request):
        """Validate session fingerprint for authenticated requests.

        Uses a one-strike grace mechanism: the first mismatch re-seeds the
        fingerprint (handles browser auto-updates, CDN User-Agent rewrites,
        extension toggles, etc.) instead of immediately force-logging out.
        Only a second consecutive mismatch triggers force-logout.
        """
        if not getattr(django_settings, 'SESSION_FINGERPRINT_ENABLED', False):
            return None

        if not request.META.get('HTTP_USER_AGENT'):
            return None

        current_fp = self.build_session_fingerprint(request)
        stored_fp = request.session.get(self.SESSION_FP_KEY)

        if not stored_fp:
            request.session[self.SESSION_FP_KEY] = current_fp
            request.session.pop(self.SESSION_FP_GRACE_KEY, None)
            return None

        if stored_fp == current_fp:
            # Match — clear any previous grace flag.
            request.session.pop(self.SESSION_FP_GRACE_KEY, None)
            return None

        # ── Mismatch detected ──
        already_graced = request.session.get(self.SESSION_FP_GRACE_KEY)

        if not already_graced:
            # First mismatch: grant grace — re-seed fingerprint and continue.
            # This handles transient UA changes (browser updates, CDN rewrites).
            logger.warning(
                "PermissionValidationMiddleware: session fingerprint mismatch "
                "(grace re-seed) user=%s stored=%s current=%s",
                getattr(request.user, 'username', '?'),
                stored_fp[:12] if stored_fp else '?',
                current_fp[:12],
            )
            request.session[self.SESSION_FP_KEY] = current_fp
            request.session[self.SESSION_FP_GRACE_KEY] = True
            return None

        # Second consecutive mismatch: genuine session hijack concern.
        logger.warning(
            "PermissionValidationMiddleware: session fingerprint mismatch "
            "(post-grace, forcing logout) user=%s",
            getattr(request.user, 'username', '?'),
        )

        return self._force_logout(request, 'Session verification failed. Please log in again.')

    def _validation_unavailable_response(self, request):
        """Fail closed when permission validation cannot be completed."""
        message = 'Session validation is temporarily unavailable. Please try again shortly.'
        is_api_request = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
            request.content_type == 'application/json' or
            '/api/' in request.path
        )
        if is_api_request:
            return JsonResponse({
                'success': False,
                'message': message,
            }, status=503)

        prefix = self._panel_prefix(request)
        return redirect(f'{prefix}/inactive/?reason={quote(message)}')
    
    def _validate_user_access(self, request):
        """Validate user's access."""
        from core.models import User
        user = request.user
        force_recheck = bool(request.session.pop('_pvm_force_recheck', 0))
        if self.REVALIDATION_INTERVAL > 0 and not force_recheck:
            last_check = request.session.get('_pvm_last_check', 0)
            if (time.time() - last_check) < self.REVALIDATION_INTERVAL:
                return None
        _cache_attr = '_pvm_fresh_user'
        fresh_user = getattr(request, _cache_attr, None)
        if fresh_user is None:
            try:
                fresh_user = (
                    User.objects
                    .only('id', 'username', 'role', 'is_active')
                    .get(pk=user.pk)
                )
                setattr(request, _cache_attr, fresh_user)
            except User.DoesNotExist:
                logger.warning("PermissionValidationMiddleware: User %s (ID: %d) no longer exists - forcing logout", user.username, user.pk)
                return self._force_logout(request, 'Your account has been removed.')
            except Exception as exc:
                logger.error("PVM_DEBUG: DB error re-fetching user - exc: %s", exc)
                return self._validation_unavailable_response(request)
        if not fresh_user.is_active:
            logger.warning("PVM_DEBUG: User %s (ID: %d) is now inactive", user.username, user.pk)
            return self._force_logout(request, 'Your account has been deactivated.')
        if fresh_user.role in ('client', 'organisation', 'prime_manager', 'manager', 'guest_prime_manager'):
            return self._validate_client_access(request, fresh_user)
        elif fresh_user.role in ('assistant'):
            return self._validate_assistant_access(request, fresh_user)
        elif fresh_user.role == 'photographer':
            allowed_prefixes = (
                '/api/mobile/',
                '/app/',
                '/api/health/',
                '/media/',
                '/static/',
                '/favicon.ico',
            )
            path = request.path
            is_allowed = any(path.startswith(prefix) for prefix in allowed_prefixes)
            if not is_allowed:
                if 'auth/' in path or 'logout/' in path:
                    is_allowed = True
            
            if not is_allowed:
                logger.warning("PermissionValidationMiddleware: Photographer %s tried to access forbidden web path %s", fresh_user.username, path)
                return self._force_logout(request, 'Photographers are only permitted to access the mobile application.')
        if fresh_user.role in ['super_admin', 'pro_user', 'operator', 'photographer']:
             logger.debug("PVM_DEBUG: Admin validation success for %s", fresh_user.username)
        return None
    
    def _validate_client_access(self, request, user):
        """Validate client user access"""
        from organisation.models import Organisation
        try:
            client_row = Organisation.objects.filter(user_id=user.pk).values('id', 'name', 'status').first()
            if not client_row:
                raise Organisation.DoesNotExist()
        except Organisation.DoesNotExist:
            logger.warning("PermissionValidationMiddleware: Organisation profile not found for user %s", user.username)
            return self._force_logout(request, 'Your client profile is not configured.')
        except Exception as exc:
            logger.error("PermissionValidationMiddleware: DB error fetching client: %s", exc)
            return self._validation_unavailable_response(request)
        if client_row['status'] != 'active':
            logger.warning("PermissionValidationMiddleware: Organisation is now %s", client_row['status'])
            return self._redirect_to_maintenance(request, 'Your organization account has been suspended.')
        session_client_id = request.session.get('_client_id')
        if session_client_id is None:
            request.session['_client_id'] = client_row['id']
        elif session_client_id != client_row['id']:
            logger.warning("PermissionValidationMiddleware: Organisation reassigned")
            return self._force_logout(request, 'Your account configuration has changed. Please log in again.')
        return None
    
    def _validate_assistant_access(self, request, user):
        """Validate assistant user access"""
        from assistants.models import Assistant
        try:
            assistant_row = Assistant.objects.filter(user_id=user.pk).values('id', 'organisation_id', 'organisation__name', 'organisation__status').first()
            if not assistant_row:
                raise Assistant.DoesNotExist()
        except Assistant.DoesNotExist:
            logger.warning("PermissionValidationMiddleware: Assistant profile not found for user %s", user.username)
            return self._force_logout(request, 'Your assistant profile is not configured.')
        except Exception as exc:
            logger.error("PermissionValidationMiddleware: DB error fetching assistant: %s", exc)
            return self._validation_unavailable_response(request)
        if not assistant_row['organisation_id']:
            logger.warning("PermissionValidationMiddleware: Assistant %s has no organisation assigned", user.username)
            return self._force_logout(request, 'You are not assigned to any organisation.')
        if assistant_row['organisation__status'] != 'active':
            logger.warning("PermissionValidationMiddleware: Assistant organisation is now %s", assistant_row['organisation__status'])
            return self._redirect_to_maintenance(request, 'Your organization account has been suspended.')
        session_client_id = request.session.get('_staff_client_id')
        if session_client_id is None:
            request.session['_staff_client_id'] = assistant_row['organisation_id']
        elif session_client_id != assistant_row['organisation_id']:
            logger.warning("PermissionValidationMiddleware: Assistant reassigned")
            return self._force_logout(request, 'You have been reassigned to a different organization. Please log in again.')
        return None
    
    def _annotate_request_scope(self, request):
        """Add role-based scope attributes to request for use by views."""
        from core.services.permission_service import PermissionService
        user = getattr(request, '_pvm_fresh_user', request.user)
        try:
            request.user_scope = {
                'is_super_admin': PermissionService.is_super_admin(user),
                'is_admin_staff': PermissionService.is_operator(user),
                'is_client': PermissionService.is_client(user),
                'is_client_staff': PermissionService.is_assistant(user),
                'client_id': None,
                'accessible_client_ids': PermissionService.get_accessible_client_ids(user),
            }
            if PermissionService.is_client(user):
                from organisation.models import Organisation
                request.user_scope['client_id'] = Organisation.objects.filter(user_id=user.id).values_list('id', flat=True).first()
            elif PermissionService.is_assistant(user):
                from assistants.models import Assistant
                request.user_scope['client_id'] = Assistant.objects.filter(user_id=user.id).values_list('organisation_id', flat=True).first()
        except Exception as exc:
            logger.warning("PermissionValidationMiddleware: _annotate_request_scope failed: %s", exc)
            if not hasattr(request, 'user_scope'):
                request.user_scope = {
                    'is_super_admin': False,
                    'is_admin_staff': False,
                    'is_client': False,
                    'is_client_staff': False,
                    'client_id': None,
                    'accessible_client_ids': [],
                }
    
    def _redirect_to_maintenance(self, request, message):
        """Redirect to maintenance page WITHOUT logging out."""
        from urllib.parse import quote
        prefix = self._panel_prefix(request)
        maintenance_url = f'{prefix}/maintenance/?reason={quote(message)}'
        is_api_request = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
            request.content_type == 'application/json' or
            '/api/' in request.path
        )
        if is_api_request:
            return JsonResponse({
                'success': False,
                'message': message,
                'force_maintenance': True,
                'redirect': maintenance_url
            }, status=403)
        return redirect(maintenance_url)
    
    def _force_logout(self, request, message):
        """Force logout user and redirect to inactive page"""
        from urllib.parse import quote
        logout(request)
        prefix = self._panel_prefix(request)
        is_api_request = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
            request.content_type == 'application/json' or
            '/api/' in request.path
        )
        if is_api_request:
            return JsonResponse({
                'success': False,
                'message': message,
                'force_logout': True,
                'redirect': f'{prefix}/inactive/?reason={quote(message)}'
            }, status=401)
        return redirect(f'{prefix}/inactive/?reason={quote(message)}')
class SubdomainRoutingMiddleware:
    """Compatibility shim for subdomain routing tests.

    Sets `request._is_panel_subdomain` based on a debug-only cookie when
    DEBUG=True. Tests control DEBUG and ALLOWED_HOSTS via override_settings.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            cookie_val = request.COOKIES.get('_panel_ctx')
        except Exception:
            cookie_val = None

        is_panel = bool(cookie_val == '1' and getattr(django_settings, 'DEBUG', False))
        # Only mark panel subdomain when DEBUG is enabled (tests expect this).
        request._is_panel_subdomain = is_panel
        return self.get_response(request)


class PanelEntryGateMiddleware:
    """Compatibility shim that accepts timestamp-signed panel-entry tokens.

    Expected behavior for tests:
    - If `panel_entry_token` is a TimestampSigner(salt='panel-entry-gate') signed
      value of 'website-panel-entry', set `request.session['_panel_entry_ok']='1'`.
    - If token is a legacy non-timestamp signer value, raise Http404.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = request.GET.get('panel_entry_token')
        if not token:
            return self.get_response(request)

        # Only process on panel subdomain (tests set this flag explicitly)
        if not getattr(request, '_is_panel_subdomain', False):
            return self.get_response(request)

        from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
        from django.http import Http404

        signer = TimestampSigner(salt='panel-entry-gate')
        try:
            value = signer.unsign(token)
        except (BadSignature, SignatureExpired, ValueError):
            # Legacy non-timestamp tokens should be rejected with 404 in tests.
            raise Http404()

        if value == 'website-panel-entry':
            # Mark session as OK so subsequent views accept panel entry
            try:
                request.session['_panel_entry_ok'] = '1'
            except Exception:
                # session may be missing in some tests; ensure attribute exists
                request.session = getattr(request, 'session', {})
                request.session['_panel_entry_ok'] = '1'
            return self.get_response(request)

        # Unknown token value — reject
        from django.http import Http404
        raise Http404()


class MaintenanceModeMiddleware:
    """
    Blocks panel access for non-super-admin users when system maintenance
    mode is enabled via SystemSettings.

    Super-admin and pro-user roles can still access the panel.
    Static, media, auth, and maintenance-status API paths are exempt.
    """

    EXEMPT_PREFIXES = (
        '/static/',
        '/media/',
        '/favicon.ico',
    )

    # Panel-relative suffixes that are exempt (prepended with panel prefix)
    EXEMPT_SUFFIXES = (
        'auth/login/',
        'auth/logout/',
        'api/auth/',
        'api/maintenance/',
        'maintenance/',
        'maintenance/system/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Maintenance mode disabled as per user request to allow discovery
        return self.get_response(request)

        # if not self._is_panel_path(request):
        # ...

    # ── helpers ──

    @staticmethod
    def _panel_prefix(request):
        if getattr(request, '_is_panel_subdomain', False):
            return ''
        return '/panel'

    @staticmethod
    def _is_panel_path(request):
        if getattr(request, '_is_panel_subdomain', False):
            return True
        return request.path.startswith('/panel/')

    def _is_exempt(self, request):
        path = request.path
        for pfx in self.EXEMPT_PREFIXES:
            if path.startswith(pfx):
                return True
        prefix = self._panel_prefix(request)
        for sfx in self.EXEMPT_SUFFIXES:
            if path.startswith(f'{prefix}/{sfx}'):
                return True
        return False


class SessionIdleTimeoutMiddleware:
    """
    Enforces two session expiry policies for authenticated users:

    1. IDLE timeout (SESSION_IDLE_TIMEOUT): logs out after N seconds with no requests.
       Default: 30 days. Set to 0 to disable.

    2. ABSOLUTE max-age (SESSION_ABSOLUTE_MAX_AGE): logs out after N seconds from
       first login regardless of activity — prevents indefinitely-valid stolen tokens.
       Default: 90 days. Set to 0 to disable.
    """

    SKIP_PREFIXES = ('/static/', '/media/', '/favicon.ico')
    ACTIVITY_WRITE_INTERVAL = 60  # seconds
    USER_IDLE_TIMEOUT_SESSION_KEY = '_user_idle_timeout_seconds'

    def __init__(self, get_response):
        self.get_response = get_response
        self._timeout = getattr(django_settings, 'SESSION_IDLE_TIMEOUT', 1800)
        self._max_age = getattr(django_settings, 'SESSION_ABSOLUTE_MAX_AGE', 60 * 60 * 24 * 90)

    def _force_logout(self, request, reason):
        """Log user out and return JSON 401 — backend is pure REST API, no HTML redirects."""
        username = getattr(request.user, 'username', 'unknown')
        logger.info("SessionExpiry: user=%s reason=%s", username, reason)
        logout(request)
        return JsonResponse({
            'success': False,
            'authenticated': False,
            'message': 'Session expired. Please log in again.',
            'reason': reason,
        }, status=401)

    def _resolve_user_idle_timeout_seconds(self, request):
        """
        Resolve per-user idle timeout in seconds.
        Falls back to global SESSION_IDLE_TIMEOUT when no user override exists.
        """
        cached = request.session.get(self.USER_IDLE_TIMEOUT_SESSION_KEY)
        if cached is not None:
            try:
                return max(int(cached), 0)
            except (TypeError, ValueError):
                request.session.pop(self.USER_IDLE_TIMEOUT_SESSION_KEY, None)

        try:
            from core.services.user_profile_service import UserProfileService

            security = UserProfileService.get_security_settings(request.user)
            timeout_minutes = int(security.get('session_timeout_minutes') or 0)
            timeout_seconds = max(timeout_minutes, 0) * 60
            request.session[self.USER_IDLE_TIMEOUT_SESSION_KEY] = timeout_seconds
            return timeout_seconds
        except Exception:
            logger.exception(
                "SessionIdleTimeout: failed to resolve per-user timeout for user=%s",
                getattr(request.user, 'pk', None),
            )
            return max(int(self._timeout or 0), 0)

    def __call__(self, request):
        # Skip for static/media and unauthenticated users
        if any(request.path.startswith(p) for p in self.SKIP_PREFIXES):
            return self.get_response(request)

        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return self.get_response(request)

        now = time.time()
        user_idle_timeout = self._resolve_user_idle_timeout_seconds(request)

        # ── Policy 1: Idle timeout ────────────────────────────────────────────
        if user_idle_timeout > 0:
            last_activity = request.session.get('_last_activity')
            if last_activity is not None and (now - last_activity) > user_idle_timeout:
                return self._force_logout(request, reason='idle')

        # ── Policy 2: Absolute max-age ────────────────────────────────────────
        if self._max_age > 0:
            session_created = request.session.get('_session_created')
            if session_created is not None and (now - session_created) > self._max_age:
                return self._force_logout(request, reason='absolute_max_age')

        # Background task polling can be very frequent. Skip activity stamp
        # writes for these paths to avoid DB lock contention on SQLite.
        if _is_task_polling_path(request.path):
            return self.get_response(request)

        # Stamp session on first authenticated use (for absolute max-age tracking)
        # and throttle subsequent writes to once per ACTIVITY_WRITE_INTERVAL.
        # Explicitly mark session as modified so Django's session middleware
        # persists the change even when SESSION_SAVE_EVERY_REQUEST is False.
        session_created = request.session.get('_session_created')
        if session_created is None:
            request.session['_session_created'] = now
            request.session['_last_activity'] = now
            request.session.modified = True
        else:
            last_activity = request.session.get('_last_activity')
            if last_activity is None or (now - last_activity) >= self.ACTIVITY_WRITE_INTERVAL:
                request.session['_last_activity'] = now
                request.session.modified = True

        return self.get_response(request)


class SecurityHeadersMiddleware:
    """
    Adds extra security headers that Django's SecurityMiddleware does not cover.

    Adds:
    - Content-Security-Policy: restricts resource origins, blocks object/plugin injection
    - Permissions-Policy: restricts browser APIs (camera, microphone, etc.)
    - Cache-Control: prevents caching of authenticated HTML pages
    - X-Robots-Tag: noindex on panel subdomain (SEO isolation)
    """

    SKIP_PREFIXES = ('/static/', '/media/')

    def __init__(self, get_response):
        self.get_response = get_response
        self._permissions_policy = getattr(
            django_settings, 'PERMISSIONS_POLICY',
            'camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()'
        )
        self._panel_domain = getattr(django_settings, 'PANEL_DOMAIN', '').lower().strip()
        # Off by default — opt-in only for /app/* pages or local debug.
        # Production API responses NEVER need unsafe-inline or unsafe-eval.
        self._allow_unsafe_inline = bool(getattr(django_settings, 'CSP_ALLOW_UNSAFE_INLINE', False))
        self._allow_unsafe_eval = bool(getattr(django_settings, 'CSP_ALLOW_UNSAFE_EVAL', False))
        self._allow_local_engine = bool(getattr(django_settings, 'CSP_ALLOW_LOCAL_ENGINE_CONNECT', False))

    def _build_script_src(self, extra_sources=None):
        parts = ["'self'"]
        if self._allow_unsafe_inline:
            parts.append("'unsafe-inline'")
        if self._allow_unsafe_eval:
            parts.append("'unsafe-eval'")
        for src in (extra_sources or []):
            if src:
                parts.append(src)
        return ' '.join(parts)

    def _build_connect_src(self):
        parts = ["'self'"]
        if self._allow_local_engine:
            parts.append('http://127.0.0.1:4765')
            parts.append('http://localhost:4765')
        return ' '.join(parts)

    def _build_panel_csp(self, frame_ancestors="'none'"):
        return (
            "default-src 'self'; "
            f"script-src {self._build_script_src(['https://static.cloudflareinsights.com'])}; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            f"connect-src {self._build_connect_src()}; "
            "media-src 'self'; "
            "frame-src 'self' https://www.google.com https://maps.google.com; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            f"frame-ancestors {frame_ancestors};"
        )

    def _build_pwa_csp(self, frame_ancestors="'none'"):
        script_sources = [
            'https://cdn.tailwindcss.com',
            'https://cdn.jsdelivr.net',
            'https://cdnjs.cloudflare.com',
            'https://static.cloudflareinsights.com',
        ]
        return (
            "default-src 'self'; "
            f"script-src {self._build_script_src(script_sources)}; "
            "style-src 'self' 'unsafe-inline' "
                "https://cdnjs.cloudflare.com "
                "https://fonts.googleapis.com "
                "https://cdn.tailwindcss.com; "
            "img-src 'self' data: blob: https:; "
            "font-src 'self' data: "
                "https://cdnjs.cloudflare.com "
                "https://fonts.gstatic.com; "
            f"connect-src {self._build_connect_src()}; "
            "media-src 'self' blob:; "
            "frame-src 'self' https://www.google.com https://maps.google.com; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            f"frame-ancestors {frame_ancestors};"
        )

    @staticmethod
    def _is_dashboard_drawer_embed_request(request):
        """Return True only for dashboard quick-action embed targets."""
        if request.GET.get('embed') != 'drawer':
            return False

        normalized_path = request.path.rstrip('/').lower()
        allowed_suffixes = (
            '/manage-clients',
            '/manage-staff',
            # admin manage-client-staff removed
        )
        return any(normalized_path.endswith(suffix) for suffix in allowed_suffixes)

    def __call__(self, request):
        response = self.get_response(request)

        # Skip for static/media (served by WhiteNoise which handles its own headers)
        if any(request.path.startswith(p) for p in self.SKIP_PREFIXES):
            return response

        # ── Cache-Control: no-store for ALL API responses ──────────────────────
        # Prevents browsers and proxies from caching authenticated API responses.
        # Applied to /api/* regardless of auth state — ensures tokens, user data,
        # and sensitive records are never served from cache after logout.
        if request.path.startswith('/api/'):
            if 'Cache-Control' not in response:
                response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
                response['Pragma'] = 'no-cache'
                response['Expires'] = '0'

        # ── Content-Security-Policy ─────────────────────────────────────────────
        # Only apply CSP to HTML responses (JSON APIs don't need it).
        content_type = response.get('Content-Type', '')
        if 'text/html' in content_type and 'Content-Security-Policy' not in response:
            is_pwa = request.path.startswith('/app/')
            frame_ancestors = "'self'" if self._is_dashboard_drawer_embed_request(request) else "'none'"
            response['Content-Security-Policy'] = (
                self._build_pwa_csp(frame_ancestors=frame_ancestors)
                if is_pwa
                else self._build_panel_csp(frame_ancestors=frame_ancestors)
            )

        # ── Permissions-Policy ──────────────────────────────────────────────────
        if self._permissions_policy:
            # Mobile PWA needs camera access for photo capture.
            if request.path.startswith('/app/'):
                response['Permissions-Policy'] = (
                    'camera=(self), microphone=(), geolocation=(), '
                    'payment=(), usb=(), interest-cohort=()'
                )
            else:
                response['Permissions-Policy'] = self._permissions_policy

        # ── Cross-Origin-Resource-Policy ────────────────────────────────────────
        # Prevents other sites from loading our API responses in no-cors mode.
        # 'same-site' allows the SPA (cardflow.in) and API (privatexyz.cardflow.in)
        # to share resources since they are same-site (*.cardflow.in).
        if 'Cross-Origin-Resource-Policy' not in response:
            if request.path.startswith('/media/'):
                # Media files (ID card images) must only be loadable from same site.
                response['Cross-Origin-Resource-Policy'] = 'same-site'
            elif request.path.startswith('/api/'):
                response['Cross-Origin-Resource-Policy'] = 'same-site'

        return response


# =============================================================================
# GUEST SANDBOX DATABASE MIDDLEWARE
# =============================================================================

import os
import shutil
from django.db import connections
from django.core.management import call_command
from core.db_router import GuestSandboxRouter

TEMPLATE_DB_PATH = os.path.join(django_settings.BASE_DIR, 'guest_sandboxes', 'template.sqlite3')

_TEMPLATE_DB_MIGRATED = False

def ensure_template_db():
    """Ensure the sandbox template database exists and is migrated to the latest state."""
    global _TEMPLATE_DB_MIGRATED
    if _TEMPLATE_DB_MIGRATED:
        return

    os.makedirs(os.path.dirname(TEMPLATE_DB_PATH), exist_ok=True)
    
    import sys
    if any('test' in str(arg).lower() for arg in sys.argv):
        default_name = connections['default'].settings_dict.get('NAME')
        if default_name and os.path.exists(str(default_name)):
            shutil.copy2(default_name, TEMPLATE_DB_PATH)
        else:
            import sqlite3
            with sqlite3.connect(TEMPLATE_DB_PATH) as conn:
                pass
        _TEMPLATE_DB_MIGRATED = True
        return
    
    db_alias = "guest_template_init"
    db_config = dict(connections['default'].settings_dict)
    if 'sqlite' in db_config.get('ENGINE', ''):
        db_config['ENGINE'] = connections['default'].settings_dict['ENGINE']
    db_config['NAME'] = TEMPLATE_DB_PATH
    db_config['OPTIONS'] = {}
    
    django_settings.DATABASES[db_alias] = db_config
    connections.databases[db_alias] = db_config
    
    try:
        logger.info("Ensuring guest sandbox template database is up to date...")
        call_command('migrate', database=db_alias, interactive=False, verbosity=0)
        
        # Clear seeded database rows to start with a clean schema
        from core.models import User
        from organisation.models import Organisation
        User.objects.using(db_alias).all().delete()
        Organisation.objects.using(db_alias).all().delete()
        
        _TEMPLATE_DB_MIGRATED = True
        logger.info("Guest sandbox template database is up to date.")
    except Exception as e:
        logger.exception("Failed to initialize guest sandbox template database: %s", e)
        if os.path.exists(TEMPLATE_DB_PATH):
            try:
                os.remove(TEMPLATE_DB_PATH)
            except Exception:
                pass
        raise e
    finally:
        if db_alias in connections:
            try:
                connections[db_alias].close()
            except Exception:
                pass
        if db_alias in connections.databases:
            del connections.databases[db_alias]
        if db_alias in django_settings.DATABASES:
            del django_settings.DATABASES[db_alias]


def populate_sandbox_database(client_id, db_alias):
    """Copy client-scoped records from the default database to the guest sandbox database."""
    from organisation.models import Organisation
    from core.models import User
    from assistants.models import Assistant
    from operators.models import Operator
    from tables.models import Table, IDCard
    from reprint.models import ReprintRequest
    from mediafiles.models import CardMedia
    
    # 1. Clear any seeded data in the destination database first to avoid unique constraints
    User.objects.using(db_alias).all().delete()
    Organisation.objects.using(db_alias).all().delete()
    Assistant.objects.using(db_alias).all().delete()
    Operator.objects.using(db_alias).all().delete()
    Table.objects.using(db_alias).all().delete()
    Table.objects.using(db_alias).all().delete()
    IDCard.objects.using(db_alias).all().delete()
    ReprintRequest.objects.using(db_alias).all().delete()
    CardMedia.objects.using(db_alias).all().delete()

    # 2. Query data from default database
    try:
        client = Organisation.objects.using('default').get(id=client_id)
    except Organisation.DoesNotExist:
        logger.warning("Organisation profile with id=%s not found during sandbox population", client_id)
        return
        
    client_user = User.objects.using('default').get(id=client.user_id)
    
    assistants = list(Assistant.objects.using('default').filter(organisation_id=client_id))
    assistant_user_ids = [a.user_id for a in assistants]
    
    operators = list(Operator.objects.using('default').filter(assigned_organisations__id=client_id))
    operator_user_ids = [op.user_id for op in operators]
    
    user_ids = list(set(assistant_user_ids + operator_user_ids))
    users = list(User.objects.using('default').filter(id__in=user_ids))
    
    # 3. Save Users (client user and staff users)
    client_user.save(using=db_alias)
    for u in users:
        u.save(using=db_alias)
        
    # 4. Save Client
    client.save(using=db_alias)
    
    # 5. Save assistants and their Many-to-Many fields
    for a in assistants:
        a.save(using=db_alias)
        a.assigned_groups.set(list(a.assigned_groups.using('default').all()), clear=True)
        
    # Save operators and their Many-to-Many fields
    for op in operators:
        op.save(using=db_alias)
        op.assigned_organisations.set(list(op.assigned_organisations.using('default').all()), clear=True)
        
    # 6. Save Table, IDCard, ReprintRequest, CardMedia
    tables = list(Table.objects.using('default').filter(organisation_id=client_id))
    for t in tables:
        t.save(using=db_alias)
        
        cards = list(IDCard.objects.using('default').filter(table_id=t.id))
        for c in cards:
            c.save(using=db_alias)
            
        reprints = list(ReprintRequest.objects.using('default').filter(table_id=t.id))
        for r in reprints:
            r.save(using=db_alias)
            
    # Copy all CardMedia records linked to this client
    media_records = list(CardMedia.objects.using('default').filter(client_id=client_id))
    for m in media_records:
        m.save(using=db_alias)


import threading
_sandbox_lock = threading.Lock()

class GuestSandboxMiddleware:
    """
    Middleware to dynamically setup, populate and route request database operations
    to an isolated, session-scoped SQLite database for guest users.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        guest_db = None
        user = getattr(request, 'user', None)
        
        if user and user.is_authenticated and getattr(user, 'role', '') == 'guest_prime_manager':
            session_key = getattr(request.session, 'session_key', '') or ''
            if not session_key:
                try:
                    request.session.save()
                    session_key = request.session.session_key or ''
                except Exception:
                    pass
            
            if session_key:
                sandbox_dir = os.path.join(django_settings.BASE_DIR, 'guest_sandboxes')
                db_file = os.path.join(sandbox_dir, f"{session_key}.sqlite3")
                db_alias = f"guest_{session_key}"
                
                with _sandbox_lock:
                    if not os.path.exists(db_file):
                        ensure_template_db()
                        os.makedirs(sandbox_dir, exist_ok=True)
                        tmp_file = db_file + ".tmp"
                        if os.path.exists(tmp_file):
                            try:
                                os.remove(tmp_file)
                            except Exception:
                                pass
                        try:
                            shutil.copy2(TEMPLATE_DB_PATH, tmp_file)
                            
                            # Register connection to temp file dynamically
                            db_config = dict(connections['default'].settings_dict)
                            db_config['ENGINE'] = 'django.db.backends.sqlite3'
                            db_config['NAME'] = tmp_file
                            db_config['OPTIONS'] = {'timeout': 60}
                            
                            django_settings.DATABASES[db_alias] = db_config
                            connections.databases[db_alias] = db_config
                            
                            # Populate data from the default database
                            client_profile = getattr(user, 'client_profile', None)
                            if client_profile:
                                try:
                                    populate_sandbox_database(client_profile.id, db_alias)
                                except Exception as e:
                                    if 'DatabaseOperationForbidden' in str(type(e)) or 'DatabaseOperationForbidden' in str(e):
                                        logger.debug("Test runner blocked dynamic sandbox population: %s", e)
                                    else:
                                        logger.exception("Failed to populate sandbox database: %s", e)
                            
                            # Close the dynamically registered temp connection to free the file handle on Windows
                            if db_alias in connections:
                                try:
                                    connections[db_alias].close()
                                except Exception:
                                    pass
                                try:
                                    del connections[db_alias]
                                except Exception:
                                    pass
                            
                            # Atomically move temp database to final session filename
                            os.replace(tmp_file, db_file)
                            
                        except Exception as e:
                            logger.exception("Failed to initialize guest sandbox session database: %s", e)
                            for path in (tmp_file, db_file):
                                if os.path.exists(path):
                                    try:
                                        os.remove(path)
                                    except Exception:
                                        pass
                            db_alias = None
                    
                    if db_alias:
                        # Always ensure the registered connection config points to the final db_file.
                        # After the atomic rename, any previously registered config still pointed to
                        # tmp_file (which no longer exists), so we unconditionally update it here.
                        db_config = dict(connections['default'].settings_dict)
                        db_config['ENGINE'] = 'django.db.backends.sqlite3'
                        db_config['NAME'] = db_file
                        db_config['OPTIONS'] = {'timeout': 60}
                        django_settings.DATABASES[db_alias] = db_config
                        connections.databases[db_alias] = db_config

                if db_alias:
                    guest_db = db_alias
                    GuestSandboxRouter.set_guest_db(guest_db)
        
        try:
            response = self.get_response(request)
        finally:
            GuestSandboxRouter.clear_guest_db()
            
        return response

