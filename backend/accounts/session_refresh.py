"""
Session Refresh API
===================

Lightweight endpoint that extends the current session and returns a fresh
CSRF token.  Called automatically by ``session-keepalive.js`` every 5 min.

This prevents "security token expired" errors for active users without
weakening security:

- Requires an authenticated session (returns 401 if expired)
- Rate-limited: 1 call per 30 seconds per user
- Safe GET request (no side-effects beyond touching the session)
"""
import logging
import time

from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

# Minimum interval between session refreshes per user (seconds)
_MIN_REFRESH_INTERVAL = 30


@require_http_methods(["GET"])
def api_session_refresh(request):
    """Extend the session and return a fresh CSRF token.

    Response::

        200 OK
        {
          "success": true,
          "csrf_token": "...",
          "session_age": 604800
        }

        401 Unauthorized  (session expired)
        {
          "success": false,
          "message": "Session expired. Please log in again."
        }
    """
    # ── Auth check ──
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'message': 'Session expired. Please log in again.',
        }, status=401)

    # ── Rate-limit (per-user, session-stored) ──
    now = time.time()
    last_refresh = request.session.get('_last_session_refresh', 0)
    if (now - last_refresh) < _MIN_REFRESH_INTERVAL:
        # Still return success + current token; just don't write the session again
        csrf_token = get_token(request)
        return JsonResponse({
            'success': True,
            'csrf_token': csrf_token,
            'session_age': getattr(settings, 'SESSION_COOKIE_AGE', 0),
        })

    # ── Extend session ──
    request.session['_last_session_refresh'] = now
    # Touch _last_activity so the idle-timeout middleware sees fresh activity
    request.session['_last_activity'] = now
    request.session.modified = True

    # ── Fresh CSRF token ──
    # get_token() sets the CSRF cookie on the response automatically
    csrf_token = get_token(request)

    logger.debug(
        "Session refreshed for user=%s",
        getattr(request.user, 'pk', None),
    )

    return JsonResponse({
        'success': True,
        'csrf_token': csrf_token,
        'session_age': getattr(settings, 'SESSION_COOKIE_AGE', 0),
    })
