"""
Accounts Services Module

Handles authentication, OTP management, and role-based logic.
No models - uses Django's built-in auth and cache for OTP storage.
"""
import hmac
import logging
import secrets
import string
import hashlib
import os
import re
from django.core.cache import cache
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.models import Group
from django.conf import settings
from core.utils.threaded_email import send_html_email_async
from core.utils.email_utils import (
    get_password_reset_otp_email_template,
    get_security_alert_email_template,
)
from django.utils import timezone

logger = logging.getLogger(__name__)

User = get_user_model()

# Role mapping - Maps frontend role names to User model role values
ROLE_MAPPING = {
    'pro_user': 'pro_user',
    'super_admin': 'super_admin',
    'operator': 'operator',
    'client': 'client',
    'guest_prime_manager': 'guest_prime_manager',
    'assistant': 'assistant',
}

# Group names for Django Groups
GROUP_NAMES = {
    'pro_user': 'PRO_USER',
    'super_admin': 'SUPER_ADMIN',
    'operator': 'OPERATOR',
    'client': 'CLIENT',
    'guest_prime_manager': 'guest_prime_manager',
    'assistant': 'ASSISTANT',
}

# Dashboard redirect URLs based on role
# pro_user, super_admin & operator → main dashboard at /panel/
# client & assistant → client dashboard at /panel/client/dashboard/
DASHBOARD_URLS = {
    'pro_user': '/panel/',
    'super_admin': '/panel/',
    'operator': '/panel/',
    'client': '/panel/client/dashboard/',
    'guest_prime_manager': '/panel/client/dashboard/',
    'assistant': '/panel/client/dashboard/',
}

# OTP settings
OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 3

# Login hardening settings (cache-based per-identifier throttle)
AUTH_FAIL_WINDOW_SECONDS = int(os.getenv('AUTH_FAIL_WINDOW_SECONDS', '900'))
AUTH_FAIL_MAX_ATTEMPTS = int(os.getenv('AUTH_FAIL_MAX_ATTEMPTS', '15'))
AUTH_FAIL_NOTIFY_THRESHOLD = int(os.getenv('AUTH_FAIL_NOTIFY_THRESHOLD', '5'))
AUTH_FAIL_NOTIFY_COOLDOWN_SECONDS = int(
    os.getenv('AUTH_FAIL_NOTIFY_COOLDOWN_SECONDS', str(AUTH_FAIL_WINDOW_SECONDS))
)
MAX_CONCURRENT_SESSIONS = int(os.getenv('MAX_CONCURRENT_SESSIONS', '5'))
DEV_LOG_OTP = os.getenv('DEV_LOG_OTP', 'false').strip().lower() in ('1', 'true', 'yes', 'on')

_ROLE_SURFACE_LIMITS = {
    # One desktop + one mobile for standard staff/client roles.
    'client': {'desktop': 1, 'mobile': 1},
    'assistant': {'desktop': 1, 'mobile': 1},
    # Guest users can use the same account on up to 20 devices per surface.
    'guest_prime_manager': {'desktop': 20, 'mobile': 20},
    # PRO and ADMIN have effectively no limit (9999).
    'operator': {'desktop': 9999, 'mobile': 9999},
    'super_admin': {'desktop': 9999, 'mobile': 9999},
    'pro_user': {'desktop': 9999, 'mobile': 9999},
}


def _normalize_identifier(value: str) -> str:
    """Normalize user-provided identifiers used for lookups/cache keys."""
    return str(value or '').strip().lower()


def _normalize_phone_digits(value: str) -> str:
    """Normalize phone-like input to digits only for resilient matching."""
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def _phone_digits_match(left: str, right: str) -> bool:
    """Return True when two normalized phone strings can represent the same number."""
    a = _normalize_phone_digits(left)
    b = _normalize_phone_digits(right)
    if not a or not b:
        return False
    if a == b:
        return True
    # Allow matching local 10-digit numbers against country-code-prefixed values.
    if len(a) >= 10 and len(b) >= 10:
        return a.endswith(b) or b.endswith(a)
    return False


def normalize_password_input(password: str) -> str:
    if not password:
        return password

    password = password.strip()

    # Keep alphanumeric/symbolic custom passwords intact.
    if re.search(r'[A-Za-z]', password):
        return password

    digits = re.sub(r'\D', '', password)
    if not digits:
        return password

    # Normalize only when every non-digit character is a common phone separator.
    # This accepts values like "+91 98765-43210", "(987) 654-3210", or "91.98765.43210"
    # while preserving custom passwords such as "1234!@#".
    leftover = re.sub(r'[\d\s\-\+\(\)\.]', '', password)
    if not leftover:
        if len(digits) > 10:
            digits = digits[-10:]
        return digits

    return password


def _auth_fail_cache_key(identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode('utf-8')).hexdigest()
    return f'auth_fail:{digest}'


def _auth_fail_notify_cache_key(identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode('utf-8')).hexdigest()
    return f'auth_fail_notify:{digest}'


def _revoke_user_sessions(user_id: int, *, exclude_session_key: str = '') -> None:
    """Best-effort revocation of active DB sessions for a user."""
    from django.contrib.sessions.models import Session

    try:
        qs = Session.objects.filter(expire_date__gt=timezone.now())
        for session in qs.iterator(chunk_size=200):
            if exclude_session_key and session.session_key == exclude_session_key:
                continue
            try:
                data = session.get_decoded()
            except Exception:
                continue
            if str(data.get('_auth_user_id')) == str(user_id):
                session.delete()
    except Exception as exc:
        logger.warning('Session revocation failed for user_id=%s: %s', user_id, exc)


class AuthService:
    """
    Authentication service handling login, user verification,
    and session management.
    """
    
    @staticmethod
    def max_concurrent_sessions() -> int:
        return max(1, MAX_CONCURRENT_SESSIONS)

    @staticmethod
    def normalize_login_surface(surface: str) -> str:
        s = str(surface or '').strip().lower()
        return 'mobile' if s == 'mobile' else 'desktop'

    @staticmethod
    def session_surface_from_payload(session_data: dict) -> str:
        data = session_data or {}
        explicit = AuthService.normalize_login_surface(data.get('_auth_login_surface'))
        if explicit == 'mobile':
            return 'mobile'
        # Backward compatibility for sessions created before _auth_login_surface.
        if bool(data.get('mobile_auth_ok')):
            return 'mobile'
        return 'desktop'

    @staticmethod
    def role_surface_limits(user_or_role) -> dict:
        role = ''
        if isinstance(user_or_role, str):
            role = user_or_role.strip().lower()
        else:
            role = str(getattr(user_or_role, 'role', '') or '').strip().lower()

        limits = _ROLE_SURFACE_LIMITS.get(role)
        if limits:
            return {
                'desktop': max(1, int(limits.get('desktop', 1))),
                'mobile': max(1, int(limits.get('mobile', 1))),
            }

        fallback = max(1, MAX_CONCURRENT_SESSIONS)
        return {'desktop': fallback, 'mobile': fallback}

    @staticmethod
    def count_active_sessions_for_user(user_id, *, exclude_session_key: str = '', stop_after=None) -> int:
        """Count active DB-backed sessions currently authenticated as this user."""
        if not user_id:
            return 0

        from django.contrib.sessions.models import Session

        active = 0
        for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator(chunk_size=200):
            if exclude_session_key and session.session_key == exclude_session_key:
                continue
            try:
                data = session.get_decoded()
            except Exception:
                continue
            if str(data.get('_auth_user_id')) == str(user_id):
                active += 1
                if stop_after is not None and active >= stop_after:
                    break
        return active

    @staticmethod
    def build_browser_fingerprint(user_agent: str, accept_language: str = '') -> str:
        """Build a stable, non-reversible browser fingerprint for session comparison."""
        ua = str(user_agent or '').strip().lower()
        al = str(accept_language or '').strip().lower()
        raw = f'{ua}|{al}'
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]

    @staticmethod
    def _surface_default_device_label(surface: str) -> str:
        return 'Mobile Device' if AuthService.normalize_login_surface(surface) == 'mobile' else 'Desktop Browser'

    @staticmethod
    def _detect_platform_from_user_agent(user_agent: str, surface: str = 'desktop') -> str:
        ua = str(user_agent or '').lower()
        if 'android' in ua:
            return 'Android'
        if 'iphone' in ua:
            return 'iPhone'
        if 'ipad' in ua:
            return 'iPad'
        if 'ipod' in ua:
            return 'iPod'
        if 'windows' in ua:
            return 'Windows'
        if 'mac os x' in ua or 'macintosh' in ua:
            return 'Mac'
        if 'linux' in ua:
            return 'Linux'
        if AuthService.normalize_login_surface(surface) == 'mobile':
            return 'Mobile'
        return 'Desktop'

    @staticmethod
    def _detect_browser_from_user_agent(user_agent: str, surface: str = 'desktop') -> str:
        ua = str(user_agent or '').lower()
        if 'edg/' in ua or 'edge/' in ua:
            return 'Edge'
        if 'opr/' in ua or 'opera' in ua:
            return 'Opera'
        if 'firefox/' in ua:
            return 'Firefox'
        if 'chrome/' in ua and 'edg/' not in ua:
            return 'Chrome'
        if 'safari/' in ua and 'chrome/' not in ua and 'crios/' not in ua:
            return 'Safari'
        return 'App' if AuthService.normalize_login_surface(surface) == 'mobile' else 'Browser'

    @staticmethod
    def device_label_from_user_agent(user_agent: str, *, surface: str = 'desktop') -> str:
        """Create a concise, human-readable device label from User-Agent."""
        normalized_surface = AuthService.normalize_login_surface(surface)
        ua = str(user_agent or '').strip()
        if not ua:
            return AuthService._surface_default_device_label(normalized_surface)

        platform = AuthService._detect_platform_from_user_agent(ua, normalized_surface)
        browser = AuthService._detect_browser_from_user_agent(ua, normalized_surface)
        return f'{platform} {browser}'.strip() or AuthService._surface_default_device_label(normalized_surface)

    @staticmethod
    def device_label_from_request(request, *, surface: str = 'desktop') -> str:
        if request is None:
            return AuthService._surface_default_device_label(surface)
        ua = str(getattr(request, 'META', {}).get('HTTP_USER_AGENT', '') or '')
        return AuthService.device_label_from_user_agent(ua, surface=surface)

    @staticmethod
    def session_device_info(session_data: dict, *, session_key: str = '') -> dict:
        data = session_data or {}
        surface = AuthService.session_surface_from_payload(data)
        fingerprint = str(data.get('_auth_browser_fp') or '').strip()
        device_label = str(data.get('_auth_device_label') or '').strip()
        if not device_label:
            device_label = AuthService._surface_default_device_label(surface)

        ip_address = str(data.get('_auth_login_ip') or '').strip()
        login_ts_raw = data.get('_auth_login_ts')
        try:
            login_ts = int(float(login_ts_raw)) if login_ts_raw is not None else 0
        except (TypeError, ValueError):
            login_ts = 0

        safe_session_key = str(session_key or '')
        session_tail = safe_session_key[-8:] if safe_session_key else ''

        return {
            'surface': surface,
            'device_label': device_label,
            'ip_address': ip_address,
            'fingerprint': fingerprint,
            'session_tail': session_tail,
            'login_ts': login_ts,
        }

    @staticmethod
    def apply_session_auth_context(request, *, surface: str = 'desktop', ip_address: str = '') -> None:
        """Persist normalized login metadata to session for audit and device visibility."""
        if request is None:
            return

        normalized_surface = AuthService.normalize_login_surface(surface)
        request.session['_auth_browser_fp'] = AuthService.browser_fingerprint_from_request(request)
        request.session['_auth_login_surface'] = normalized_surface
        request.session['_auth_device_label'] = AuthService.device_label_from_request(
            request,
            surface=normalized_surface,
        )
        request.session['_auth_login_ip'] = str(ip_address or '').strip()
        request.session['_auth_login_ts'] = int(timezone.now().timestamp())
        if normalized_surface == 'mobile':
            request.session['mobile_auth_ok'] = True

    @staticmethod
    def list_active_sessions_for_user(
        user_id,
        *,
        surface: str = '',
        exclude_session_key: str = '',
        limit: int = 5,
    ) -> list:
        """Return active sessions for user with best-effort device metadata."""
        if not user_id:
            return []

        from django.contrib.sessions.models import Session

        normalized_surface = str(surface or '').strip().lower()
        rows = []
        for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator(chunk_size=200):
            if exclude_session_key and session.session_key == exclude_session_key:
                continue
            try:
                data = session.get_decoded()
            except Exception:
                continue

            if str(data.get('_auth_user_id')) != str(user_id):
                continue

            info = AuthService.session_device_info(data, session_key=session.session_key)
            if normalized_surface and info.get('surface') != normalized_surface:
                continue

            rows.append(info)

        rows.sort(key=lambda item: int(item.get('login_ts') or 0), reverse=True)
        max_items = max(1, int(limit or 1))
        return rows[:max_items]

    @staticmethod
    def revoke_active_sessions_for_user(
        user_id,
        *,
        surface: str = '',
        exclude_session_key: str = '',
        max_revoke=None,
    ) -> dict:
        """Revoke active sessions for user, optionally constrained by surface."""
        if not user_id:
            return {'revoked_count': 0, 'revoked_sessions': []}

        from django.contrib.sessions.models import Session

        normalized_surface = str(surface or '').strip().lower()
        candidates = []

        for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator(chunk_size=200):
            if exclude_session_key and session.session_key == exclude_session_key:
                continue

            try:
                data = session.get_decoded()
            except Exception:
                continue

            if str(data.get('_auth_user_id')) != str(user_id):
                continue

            info = AuthService.session_device_info(data, session_key=session.session_key)
            if normalized_surface and info.get('surface') != normalized_surface:
                continue

            candidates.append((int(info.get('login_ts') or 0), session, info))

        # Revoke oldest sessions first when max_revoke is provided.
        candidates.sort(key=lambda row: row[0])
        if max_revoke is not None:
            try:
                cap = max(1, int(max_revoke))
            except (TypeError, ValueError):
                cap = len(candidates)
            candidates = candidates[:cap]

        revoked_sessions = []
        for _, session, info in candidates:
            try:
                session_key = session.session_key
                if session_key:
                    from django.core.cache import cache
                    cache.set(f'concurrent_logout:{session_key}', True, 86400)
                session.delete()
                revoked_sessions.append(info)
            except Exception:
                continue

        return {
            'revoked_count': len(revoked_sessions),
            'revoked_sessions': revoked_sessions,
        }

    @staticmethod
    def browser_fingerprint_from_request(request) -> str:
        if request is None:
            return ''
        return AuthService.build_browser_fingerprint(
            request.META.get('HTTP_USER_AGENT', ''),
            request.META.get('HTTP_ACCEPT_LANGUAGE', ''),
        )

    @staticmethod
    def inspect_active_sessions_for_user(
        user_id,
        *,
        browser_fingerprint: str = '',
        exclude_session_key: str = '',
        stop_after=None,
        include_device_info: bool = True,
        device_info_limit: int = 5,
    ) -> dict:
        """
        Inspect active sessions for a user and detect concurrent logins from other browsers.
        """
        if not user_id:
            return {
                'count': 0,
                'has_different_browser': False,
                'known_browser_fingerprints': [],
            }

        from django.contrib.sessions.models import Session

        active = 0
        has_different_browser = False
        known_browser_fingerprints = set()
        surface_counts = {'desktop': 0, 'mobile': 0}
        active_sessions = []
        current_fp = str(browser_fingerprint or '').strip()

        for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator(chunk_size=200):
            if exclude_session_key and session.session_key == exclude_session_key:
                continue

            try:
                data = session.get_decoded()
            except Exception:
                continue

            if str(data.get('_auth_user_id')) != str(user_id):
                continue

            active += 1
            surface = AuthService.session_surface_from_payload(data)
            surface_counts[surface] = surface_counts.get(surface, 0) + 1

            if include_device_info and len(active_sessions) < max(1, int(device_info_limit or 1)):
                active_sessions.append(
                    AuthService.session_device_info(data, session_key=session.session_key)
                )

            fp = str(data.get('_auth_browser_fp') or '').strip()
            if fp:
                known_browser_fingerprints.add(fp)
                if current_fp and fp != current_fp:
                    has_different_browser = True

            if stop_after is not None and active >= stop_after:
                break

        return {
            'count': active,
            'has_different_browser': has_different_browser,
            'known_browser_fingerprints': sorted(known_browser_fingerprints),
            'active_sessions': active_sessions,
            'surface_counts': {
                'desktop': int(surface_counts.get('desktop', 0) or 0),
                'mobile': int(surface_counts.get('mobile', 0) or 0),
            },
        }

    @staticmethod
    def _find_user(identifier, role=None):
        """
        Find a user by email, username, or phone, with optional role filter.

        Args:
            identifier: Email address, username, or phone number
            role: Optional role to filter by

        Returns:
            User instance or None
        """
        from django.db.models import Q
        if not identifier:
            return None

        role_filter = Q()
        if role and role in ROLE_MAPPING:
            if role == 'super_admin':
                role_filter = Q(role__in=['super_admin', 'pro_user'])
            else:
                role_filter = Q(role=role)

        # Try email first, then username.
        user = User.objects.filter(Q(email__iexact=identifier) & role_filter).first()
        if not user:
            user = User.objects.filter(Q(username__iexact=identifier) & role_filter).first()
        if user:
            return user

        # Finally, allow phone-number based login identifiers.
        raw_identifier = str(identifier or '').strip()
        normalized_identifier = _normalize_phone_digits(raw_identifier)
        if not normalized_identifier:
            return None

        candidates = []
        phone_qs = (
            User.objects
            .filter(role_filter)
            .exclude(phone__isnull=True)
            .exclude(phone__exact='')
            .only('id', 'phone', 'username', 'password', 'is_active', 'role', 'email')
        )
        for candidate in phone_qs.iterator(chunk_size=200):
            if _phone_digits_match(candidate.phone, normalized_identifier):
                candidates.append(candidate)
                if len(candidates) > 5:
                    break  # Safety cap

        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # Multiple users share this phone — prefer the single active user
        active_candidates = [c for c in candidates if c.is_active]
        if len(active_candidates) == 1:
            return active_candidates[0]
        # Still ambiguous — log warning and return None for safety
        logger.warning(
            "Ambiguous phone login: %d users share phone digits ***%s (active: %d)",
            len(candidates), normalized_identifier[-4:], len(active_candidates),
        )
        return None

    @staticmethod
    def check_user_exists(identifier, role=None):
        """
        Check login preflight without disclosing whether an account exists.

        Args:
            identifier: User's email address or username
            role: Optional role to filter by

        Returns:
            dict: response safe for unauthenticated clients
        """
        try:
            identifier = _normalize_identifier(identifier)
            # Perform a lookup so timing stays consistent, but never reveal result.
            AuthService._find_user(identifier, role)
            return {
                'exists': True,
                'user_name': 'User',
                'user_email': identifier,
                'message': 'If an account exists, continue with password.'
            }
        except Exception:
            return {
                'exists': True,
                'user_name': 'User',
                'user_email': identifier,
                'message': 'If an account exists, continue with password.'
            }
    
    @staticmethod
    def _is_login_blocked(identifier: str) -> bool:
        if not identifier:
            return False
        try:
            attempts = int(cache.get(_auth_fail_cache_key(identifier), 0) or 0)
            return attempts >= max(1, AUTH_FAIL_MAX_ATTEMPTS)
        except Exception:
            return False

    @staticmethod
    def _record_login_failure(identifier: str) -> None:
        if not identifier:
            return 0
        key = _auth_fail_cache_key(identifier)
        try:
            cache.add(key, 0, AUTH_FAIL_WINDOW_SECONDS)
            return int(cache.incr(key) or 0)
        except ValueError:
            cache.set(key, 1, AUTH_FAIL_WINDOW_SECONDS)
            return 1
        except Exception:
            return 0

    @staticmethod
    def _maybe_notify_failed_login(user, identifier: str, attempts: int) -> None:
        """Send best-effort suspicious login notification without changing API responses."""
        if not user or not getattr(user, 'email', ''):
            return
        if attempts < max(1, AUTH_FAIL_NOTIFY_THRESHOLD):
            return

        notify_key = _auth_fail_notify_cache_key(identifier)
        # cache.add => notify only once per cooldown window.
        try:
            should_notify = cache.add(notify_key, 1, AUTH_FAIL_NOTIFY_COOLDOWN_SECONDS)
        except Exception:
            return
        if not should_notify:
            return

        try:
            subject = '🚨 Security Alert: Multiple failed login attempts'
            html_content, plain_content = get_security_alert_email_template(
                name=user.get_full_name() or user.username,
                attempts=attempts,
            )
            send_html_email_async(
                subject=subject,
                plain_content=plain_content,
                html_content=html_content,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                recipient_list=[user.email],
                email_type='security_alert',
                skip_logging=False,
            )
        except Exception as exc:
            logger.warning('Failed to send login-failure alert for user=%s: %s', user.pk, exc)

    @staticmethod
    def _clear_login_failures(identifier: str) -> None:
        if not identifier:
            return
        try:
            cache.delete(_auth_fail_cache_key(identifier))
        except Exception as exc:
            logger.debug('Failed to clear login-failure cache for identifier=%s: %s', identifier, exc)

    @staticmethod
    def authenticate_user(identifier, password, role=None):
        """
        Authenticate user with email/username and password.

        Args:
            identifier: User's email or username
            password: User's password
            role: Expected role (optional)

        Returns:
            dict: {success: bool, user: User, redirect_url: str, message: str}
        """
        try:
            identifier = _normalize_identifier(identifier)

            _AUTH_FAIL_MSG = 'Invalid credentials. Please try again.'

            if not identifier or len(identifier) > 254:
                return {'success': False, 'message': _AUTH_FAIL_MSG}

            if AuthService._is_login_blocked(identifier):
                return {'success': False, 'message': _AUTH_FAIL_MSG}

            user = AuthService._find_user(identifier, role=None)

            if not user:
                AuthService._record_login_failure(identifier)
                return {'success': False, 'message': _AUTH_FAIL_MSG}

            # Check role if specified
            if role and user.role != role:
                if not (role == 'super_admin' and user.role == 'pro_user'):
                    attempts = AuthService._record_login_failure(identifier)
                    AuthService._maybe_notify_failed_login(user, identifier, attempts)
                    return {'success': False, 'message': _AUTH_FAIL_MSG}

            if not user.is_active:
                attempts = AuthService._record_login_failure(identifier)
                AuthService._maybe_notify_failed_login(user, identifier, attempts)
                return {'success': False, 'message': _AUTH_FAIL_MSG}

            # Normalize password input (phone formats -> digits, text -> intact)
            normalized_password = normalize_password_input(password)

            authenticated_user = authenticate(username=user.username, password=normalized_password)

            if authenticated_user is None:
                # Fallback: direct password check
                if user.check_password(normalized_password):
                    # Set backend attribute required by django.contrib.auth.login()
                    user.backend = 'django.contrib.auth.backends.ModelBackend'
                    authenticated_user = user
                else:
                    attempts = AuthService._record_login_failure(identifier)
                    AuthService._maybe_notify_failed_login(user, identifier, attempts)
                    return {'success': False, 'message': _AUTH_FAIL_MSG}

            AuthService._clear_login_failures(identifier)

            redirect_url = DASHBOARD_URLS.get(user.role, '/panel/')

            return {
                'success': True,
                'user': authenticated_user,
                'redirect_url': redirect_url,
                'message': 'Login successful'
            }

        except Exception as e:
            return {
                'success': False,
                'message': 'An authentication error occurred. Please try again.'
            }
    
    @staticmethod
    def get_dashboard_url(user):
        """Get the appropriate dashboard URL for a user based on their role."""
        from core.services.permission_service import PermissionService
        if PermissionService.is_super_admin(user):
            return DASHBOARD_URLS['super_admin']
        return DASHBOARD_URLS.get(user.role, '/panel/')


class OTPService:
    """
    OTP service for password reset functionality.
    Uses Django's cache backend for OTP storage (no database models needed).
    """
    
    @staticmethod
    def _get_otp_cache_key(email):
        """Generate a unique cache key for OTP storage."""
        email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
        return f'otp_{email_hash}'
    
    @staticmethod
    def _get_otp_attempts_key(email):
        """Generate a cache key for tracking OTP attempts."""
        email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
        return f'otp_attempts_{email_hash}'
    
    @staticmethod
    def _get_reset_token_key(email):
        """Generate a cache key for reset token storage."""
        email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
        return f'reset_token_{email_hash}'

    @staticmethod
    def _otp_hash(email, otp):
        """Derive deterministic HMAC digest for OTP verification."""
        payload = f'{email.lower()}:{otp}'.encode('utf-8')
        return hmac.new(settings.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
    
    @staticmethod
    def generate_otp():
        """Generate a cryptographically secure random 6-digit OTP."""
        return ''.join(secrets.choice(string.digits) for _ in range(OTP_LENGTH))
    
    @staticmethod
    def generate_reset_token():
        """Generate a cryptographically secure reset token with HMAC signature."""
        raw_token = secrets.token_urlsafe(32)
        # Sign the token with SECRET_KEY to prevent forgery
        signature = hmac.new(
            settings.SECRET_KEY.encode(),
            raw_token.encode(),
            hashlib.sha256
        ).hexdigest()[:16]
        return f"{raw_token}.{signature}"
    
    @classmethod
    def send_otp(cls, email):
        """
        Generate and send OTP to user's email.
        
        Args:
            email: User's email address, username, or phone number
            
        Returns:
            dict: {success: bool, message: str, dev_otp: str (only in DEBUG)}
        """
        try:
            from core.models import EmailLog

            identifier = _normalize_identifier(email)

            # Find user using the robust helper (finds via email, username, or phone number)
            user = AuthService._find_user(identifier)
            if not user:
                # Return same success message to prevent user enumeration
                return {
                    'success': True,
                    'message': f'If an account exists with this email, an OTP has been sent to {email}'
                }
            
            # Use the user's actual registered email address for sending and caching
            actual_email = (user.email or '').strip()
            
            # If the user doesn't have a valid email address (e.g. placeholder locals used for phones)
            if not actual_email or actual_email.endswith('@noemail.local'):
                return {
                    'success': False,
                    'message': 'This account does not have a valid registered email address. Please contact your administrator.'
                }

            # Generate OTP
            otp = cls.generate_otp()
            cache_key = cls._get_otp_cache_key(actual_email)
            
            # Store OTP in cache with expiry
            cache.set(cache_key, {
                'otp_hash': cls._otp_hash(actual_email, otp),
                'email': actual_email.lower(),
                'created_at': timezone.now().isoformat()
            }, timeout=OTP_EXPIRY_MINUTES * 60)
            
            # Reset attempts counter
            attempts_key = cls._get_otp_attempts_key(actual_email)
            cache.set(attempts_key, 0, timeout=OTP_EXPIRY_MINUTES * 60)

            log = EmailLog.objects.create(
                recipient_name=user.get_full_name() or user.username or actual_email,
                recipient_email=actual_email,
                subject='Password Reset OTP',
                email_type=EmailLog.EMAIL_TYPE_OTP_RESET,
                status=EmailLog.STATUS_PENDING,
            )
            
            # Send email (or just log in development)
            if settings.DEBUG:
                if getattr(settings, 'DEV_LOG_OTP', DEV_LOG_OTP):
                    logger.info("[DEV] OTP for %s: %s", actual_email, otp)
                else:
                    logger.debug("[DEV] OTP generated for %s (logging suppressed)", actual_email)
                log.status = EmailLog.STATUS_SENT
                log.sent_at = timezone.now()
                log.error_message = ''
                log.save(update_fields=['status', 'sent_at', 'error_message'])
                return {
                    'success': True,
                    'message': f'If an account exists with this email, an OTP has been sent to {email}',
                    'dev_otp': otp  # Only in debug mode
                }
            else:
                # Production: Send branded HTML OTP email
                from core.utils.threaded_email import send_html_email_with_callback
                user_name = user.get_full_name() or user.username
                html_content, plain_content = get_password_reset_otp_email_template(
                    user_name=user_name,
                    otp=otp,
                    expiry_minutes=OTP_EXPIRY_MINUTES,
                )

                def _mark_sent():
                    EmailLog.objects.filter(pk=log.pk).update(
                        status=EmailLog.STATUS_SENT,
                        sent_at=timezone.now(),
                        error_message='',
                        subject='🔐 Password Reset OTP — Adarsh Admin',
                        body_text=plain_content,
                        body_html=html_content,
                    )

                def _mark_failed(error_msg):
                    EmailLog.objects.filter(pk=log.pk).update(
                        status=EmailLog.STATUS_FAILED,
                        error_message=error_msg or 'Failed to send OTP email.',
                        subject='🔐 Password Reset OTP — Adarsh Admin',
                        body_text=plain_content,
                        body_html=html_content,
                    )

                send_html_email_with_callback(
                    subject='🔐 Password Reset OTP — Adarsh Admin',
                    plain_content=plain_content,
                    html_content=html_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[actual_email],
                    on_success=_mark_sent,
                    on_failure=_mark_failed,
                    skip_logging=True,
                )
                # Queued for send in thread — keep as pending for accurate state.
                return {
                    'success': True,
                    'message': f'If an account exists with this email, an OTP has been sent to {email}'
                }
                     
        except Exception as e:
            logger.error("Error generating OTP for %s: %s", email, e)
            try:
                from core.models import EmailLog
                EmailLog.objects.create(
                    recipient_name=email,
                    recipient_email=email,
                    subject='Password Reset OTP',
                    email_type=EmailLog.EMAIL_TYPE_OTP_RESET,
                    status=EmailLog.STATUS_FAILED,
                    error_message=str(e),
                )
            except Exception:
                logger.debug('Failed to persist OTP failure EmailLog for %s', email)
            return {
                'success': False,
                'message': 'An error occurred. Please try again.'
            }
    
    @classmethod
    def verify_otp(cls, email, otp):
        """
        Verify the OTP entered by user.
        
        Args:
            email: User's email, username, or phone number
            otp: OTP entered by user
            
        Returns:
            dict: {success: bool, reset_token: str, message: str}
        """
        try:
            identifier = _normalize_identifier(email)
            user = AuthService._find_user(identifier)
            actual_email = (user.email or '').strip().lower() if user else identifier.lower()

            cache_key = cls._get_otp_cache_key(actual_email)
            attempts_key = cls._get_otp_attempts_key(actual_email)
            
            # Get stored OTP data
            otp_data = cache.get(cache_key)
            
            if not otp_data:
                return {
                    'success': False,
                    'message': 'OTP has expired. Please request a new one.'
                }
            
            # Check attempts atomically using cache.incr to prevent TOCTOU race
            try:
                attempts = cache.incr(attempts_key)
            except ValueError:
                # Key expired or missing — first attempt in a fresh window
                cache.set(attempts_key, 1, timeout=OTP_EXPIRY_MINUTES * 60)
                attempts = 1
            
            if attempts > OTP_MAX_ATTEMPTS:
                # Clear OTP after max attempts
                cache.delete(cache_key)
                return {
                    'success': False,
                    'message': 'Too many failed attempts. Please request a new OTP.'
                }
            
            # Verify OTP (constant-time comparison to prevent timing attacks)
            # Backward-compatible fallback supports entries created before hashing.
            stored_hash = otp_data.get('otp_hash')
            if stored_hash:
                candidate_hash = cls._otp_hash(actual_email, otp)
                is_valid = hmac.compare_digest(str(stored_hash), str(candidate_hash))
            else:
                is_valid = hmac.compare_digest(str(otp_data.get('otp', '')), str(otp))

            if not is_valid:
                return {
                    'success': False,
                    'message': 'Invalid OTP. Please try again.'
                }
            
            # OTP verified - generate reset token
            reset_token = cls.generate_reset_token()
            token_key = cls._get_reset_token_key(actual_email)
            
            # Store reset token (valid for 15 minutes)
            cache.set(token_key, {
                'token': reset_token,
                'email': actual_email,
                'verified_at': timezone.now().isoformat()
            }, timeout=15 * 60)
            
            # Clear OTP data
            cache.delete(cache_key)
            cache.delete(attempts_key)
            
            return {
                'success': True,
                'reset_token': reset_token,
                'message': 'OTP verified successfully'
            }
            
        except Exception as e:
            logger.error("Error verifying OTP for %s: %s", email, e)
            return {
                'success': False,
                'message': 'An error occurred. Please try again.'
            }
    
    @classmethod
    def reset_password(cls, email, reset_token, new_password):
        """
        Reset user's password after OTP verification.
        
        Args:
            email: User's email, username, or phone number
            reset_token: Token from OTP verification
            new_password: New password to set
            
        Returns:
            dict: {success: bool, message: str}
        """
        try:
            identifier = _normalize_identifier(email)
            user = AuthService._find_user(identifier)
            actual_email = (user.email or '').strip().lower() if user else identifier.lower()

            token_key = cls._get_reset_token_key(actual_email)
            token_data = cache.get(token_key)
            
            if not token_data:
                return {
                    'success': False,
                    'message': 'Reset session expired. Please start again.'
                }
            
            if not hmac.compare_digest(str(token_data['token']), str(reset_token)):
                return {
                    'success': False,
                    'message': 'Invalid reset token. Please start again.'
                }

            if str(token_data.get('email', '')).lower() != actual_email:
                return {
                    'success': False,
                    'message': 'Invalid reset session. Please start again.'
                }
            
            # Verify HMAC signature on the token to prevent forgery
            token_parts = reset_token.split('.')
            if len(token_parts) != 2:
                return {
                    'success': False,
                    'message': 'Invalid reset token format. Please start again.'
                }
            raw_token, provided_sig = token_parts
            expected_sig = hmac.new(
                settings.SECRET_KEY.encode(),
                raw_token.encode(),
                hashlib.sha256
            ).hexdigest()[:16]
            if not hmac.compare_digest(provided_sig, expected_sig):
                return {
                    'success': False,
                    'message': 'Tampered reset token. Please start again.'
                }
            
            # Get user and update password
            if not user:
                user = User.objects.filter(email__iexact=actual_email).first()
            if not user:
                return {
                    'success': False,
                    'message': 'Invalid reset request. Please start again.'
                }
            
            # Validate password (using AUTH_PASSWORD_VALIDATORS from settings —
            # currently only MinimumLengthValidator, so mobile numbers etc. are allowed)
            from django.contrib.auth.password_validation import validate_password
            
            # Universal password normalization (phone formats -> digits, text -> intact)
            normalized_new_password = normalize_password_input(new_password)
            
            try:
                validate_password(normalized_new_password, user=user)
            except Exception as validation_error:
                # Collect all error messages from validators
                msgs = getattr(validation_error, 'messages', [str(validation_error)])
                return {
                    'success': False,
                    'message': '; '.join(msgs)
                }

            # Set new password
            user.set_password(normalized_new_password)
            user.save()

            # Security: invalidate all active sessions for this user.
            _revoke_user_sessions(user.pk)
            AuthService._clear_login_failures(email)
            
            # Clear reset token
            cache.delete(token_key)

            # Log password reset
            try:
                from core.services.activity_service import ActivityService
                last_active_str = ActivityService._format_last_active(user)
                ActivityService.log(
                    'password_reset',
                    f'Password reset completed for "{user.get_full_name() or user.email}" via OTP ({last_active_str})',
                    user=user,
                    target_model='User',
                    target_id=user.pk,
                    target_name=user.get_full_name() or user.email,
                )
            except Exception:
                logger.warning('Failed to log OTP password reset for user=%s', user.pk)
            
            return {
                'success': True,
                'message': 'Password reset successfully. You can now login with your new password.'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Error resetting password. Please try again.'
            }


class RoleService:
    """
    Service for managing user roles and groups.
    Uses Django's built-in Group model.
    """
    
    @staticmethod
    def setup_groups():
        """
        Create Django Groups for each role.
        Call this from a management command or migration.
        
        Returns:
            dict: {success: bool, groups: list, message: str}
        """
        created_groups = []
        
        try:
            for role_key, group_name in GROUP_NAMES.items():
                group, created = Group.objects.get_or_create(name=group_name)
                if created:
                    created_groups.append(group_name)
            
            return {
                'success': True,
                'groups': list(GROUP_NAMES.values()),
                'created': created_groups,
                'message': f'Groups setup complete. Created: {created_groups}'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Error setting up groups. Please try again.'
            }
    
    @staticmethod
    def get_role_display_name(role):
        """Get human-readable role name."""
        role_display = {
            'pro_user': 'Pro Admin',
            'super_admin': 'Super Admin',
            'operator': 'Operator',
            'admin_staff': 'Operator',
            'client': 'Client Admin',
            'guest_prime_manager': 'Guest Sandbox User',
            'assistant': 'Assistant',
            'client_staff': 'Assistant',
            'photographer': 'Photographer',
        }
        return role_display.get(role, str(role).title())
