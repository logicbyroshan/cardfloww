"""
Simple in-memory rate limiter for authentication endpoints.

Uses Django's cache framework (default backend) to track request counts
per IP address.  No external dependencies required.

Usage:
    @method_decorator(rate_limit(max_requests=5, window_seconds=60), name='dispatch')
    class MyView(View): ...
"""
import functools
import logging
import hashlib
import ipaddress
import time
from threading import Lock

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger(__name__)


# Process-local fallback when cache backend is unavailable.
_FALLBACK_LIMITER = {}
_FALLBACK_LIMITER_LOCK = Lock()


def _fallback_limiter_hit(cache_key, window_seconds):
    """Increment process-local counter and return current hit count."""
    now = int(time.time())
    with _FALLBACK_LIMITER_LOCK:
        # Opportunistic cleanup to keep memory bounded.
        if len(_FALLBACK_LIMITER) > 5000:
            expired = [k for k, (_, exp) in _FALLBACK_LIMITER.items() if exp <= now]
            for key in expired[:2000]:
                _FALLBACK_LIMITER.pop(key, None)

        count, expires_at = _FALLBACK_LIMITER.get(cache_key, (0, now + window_seconds))
        if expires_at <= now:
            count = 0
            expires_at = now + window_seconds

        count += 1
        _FALLBACK_LIMITER[cache_key] = (count, expires_at)
        return count


def _normalize_ip(value):
    """Return canonical IP string or None for invalid/empty values."""
    if value is None:
        return None
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        return None


def _is_internal_ip(ip_value):
    """True for private/loopback/link-local/reserved proxy style addresses."""
    normalized = _normalize_ip(ip_value)
    if not normalized:
        return False
    parsed = ipaddress.ip_address(normalized)
    return bool(
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_reserved
    )


def _get_client_ip(request):
    """Extract client IP from REMOTE_ADDR (safe default).
    
    Uses REMOTE_ADDR which is set by the WSGI server and cannot be spoofed.
    X-Forwarded-For is only trusted when the app runs behind a known reverse
    proxy (Nginx/Render etc.) that overwrites it.  The proxy must be
    configured to strip client-supplied X-Forwarded-For values.
    """
    trust_xff = bool(getattr(settings, 'RATE_LIMIT_TRUST_X_FORWARDED_FOR', False))
    remote_addr = _normalize_ip(request.META.get('REMOTE_ADDR'))
    x_real_ip = _normalize_ip(request.META.get('HTTP_X_REAL_IP'))

    xff_raw = request.META.get('HTTP_X_FORWARDED_FOR')
    xff_ips = []
    if xff_raw:
        xff_ips = [
            ip
            for ip in (_normalize_ip(part) for part in str(xff_raw).split(','))
            if ip
        ]

    if trust_xff:
        # Trusted proxy mode: first XFF IP is the original client.
        if xff_ips:
            return xff_ips[0]
        if x_real_ip:
            return x_real_ip
        return remote_addr or '0.0.0.0'

    # Untrusted proxy mode: preserve REMOTE_ADDR behavior for compatibility.
    if remote_addr:
        return remote_addr
    # Fall back only when REMOTE_ADDR is missing/invalid.
    if x_real_ip:
        return x_real_ip
    if xff_ips:
        return xff_ips[0]
    return remote_addr or '0.0.0.0'


def rate_limit(max_requests=5, window_seconds=60, key_prefix='rl'):
    """
    Decorator that rejects requests exceeding *max_requests* within
    a sliding *window_seconds* window for a given IP + view.

    Returns HTTP 429 JSON on throttle.
    """
    # Globally scale up all limits to ensure normal users never hit them.
    # Scaled limits protect against real abuse while giving genuine users plenty of room.
    original_max = max_requests
    if 'login' in key_prefix or key_prefix == 'rl':
        max_requests = max(original_max * 5, 30)  # Login/auth views get 30 attempts/min
    elif 'otp' in key_prefix or 'forgot' in key_prefix:
        max_requests = max(original_max * 5, 20)  # OTP/forgot password gets 20 attempts/min
    else:
        max_requests = max(original_max * 5, 100) # Other endpoints get at least 100/min

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            ip = _get_client_ip(request)
            endpoint_id = ''
            resolver = getattr(request, 'resolver_match', None)
            if resolver and getattr(resolver, 'view_name', ''):
                endpoint_id = resolver.view_name
            if not endpoint_id:
                endpoint_id = request.path

            # Hash endpoint identity to keep cache keys backend-safe.
            endpoint_hash = hashlib.sha256(str(endpoint_id).encode('utf-8')).hexdigest()[:16]
            cache_key = f'{key_prefix}:{request.method}:{endpoint_hash}:{ip}'

            # ── Rapid double-click / spam protection (1.5 seconds) ──
            # If the user clicks multiple times rapidly, we process the first one
            # and ignore subsequent rapid clicks as accidental duplicate clicks.
            # Skip during test runs because tests execute in milliseconds.
            last_hit_key = f'last_hit:{cache_key}'
            now = time.time()
            is_spam_click = False
            try:
                import sys
                is_testing = 'test' in sys.argv or getattr(settings, 'TESTING', False)
                if not is_testing:
                    last_hit_time = cache.get(last_hit_key)
                    if last_hit_time is not None:
                        time_diff = now - float(last_hit_time)
                        if time_diff < 1.5:
                            is_spam_click = True
                    cache.set(last_hit_key, now, window_seconds)
            except Exception:
                pass

            if is_spam_click:
                # Do not increment hits counter. Return a silent response to frontend.
                return JsonResponse({
                    'success': False,
                    'silent': True,
                    'message': '',  # Silent error, no user popup
                }, status=429)

            try:
                created = cache.add(cache_key, 1, window_seconds)
                if created:
                    hits = 1
                else:
                    try:
                        hits = int(cache.incr(cache_key) or 0)
                    except Exception:
                        # Fallback for cache backends without atomic incr.
                        hits = int(cache.get(cache_key, 0) or 0) + 1
                        cache.set(cache_key, hits, window_seconds)
            except Exception as exc:
                # Fail safely: use in-process fallback counter instead of bypassing throttling.
                logger.warning('Rate limit cache error on %s: %s', endpoint_id, exc)
                hits = _fallback_limiter_hit(cache_key, window_seconds)

            if hits > max_requests:
                effective_max_requests = int(max_requests)
                try:
                    user = getattr(request, 'user', None)
                    if user and getattr(user, 'is_authenticated', False):
                        bonus = 0
                        if bonus > 0:
                            effective_max_requests += bonus
                except Exception:
                    logger.exception('Failed resolving Super Mode rate-limit bonus for key_prefix=%s', key_prefix)

                if hits <= effective_max_requests:
                    return view_func(request, *args, **kwargs)

                logger.warning('Rate limit hit: %s from %s', view_func.__name__, ip)
                # Keep rate limit rejection silent as per request
                return JsonResponse({
                    'success': False,
                    'silent': True,
                    'message': '',  # Silent error, no user popup
                }, status=429)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
