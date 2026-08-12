
from pathlib import Path
import sys
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured
import os
import dj_database_url
import logging
from django.urls import resolve, Resolver404

# Sentry imports are optional — import lazily to avoid hard failures when SDK
# is not installed. The actual import is attempted only if SENTRY_DSN is set.
_SENTRY_AVAILABLE = False
try:
    import sentry_sdk  # type: ignore
    from sentry_sdk.integrations.django import DjangoIntegration  # type: ignore
    from sentry_sdk.integrations.logging import LoggingIntegration  # type: ignore
    _SENTRY_AVAILABLE = True
except Exception:
    sentry_sdk = None
    DjangoIntegration = None
    LoggingIntegration = None

# Load environment variables from .env file (if exists)
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# =============================================================================
# CORE SETTINGS
# =============================================================================

# SECURITY: SECRET_KEY must always come from .env — no hardcoded fallback.
# Generate one with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured(
        'SECRET_KEY is not set. Add it to your .env file. '
        'Generate one with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
    )
# In production, enforce a minimum key length (Django requires 50+ chars)
if not os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes'):
    if len(SECRET_KEY) < 50:
        raise ImproperlyConfigured(
            f'SECRET_KEY is too short ({len(SECRET_KEY)} chars). '
            'Generate a proper key: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
        )

# SECURITY WARNING: don't run with debug turned on in production!
# Safe default: False — must explicitly opt-in to DEBUG mode
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')


def _env_bool(name: str, default: bool = False) -> bool:
    """Read boolean-like environment variables safely."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _running_tests() -> bool:
    """Detect pytest/test execution early, before conftest can mutate settings."""
    if _env_bool('RUNNING_TESTS'):
        return True
    if any(arg == 'test' or arg.endswith(' test') for arg in sys.argv):
        return True
    return any(mod.startswith('_pytest') for mod in sys.modules)


def _env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    """Read integer-like environment variables safely with optional bounds."""
    value = os.getenv(name)
    try:
        parsed = int(str(value).strip()) if value is not None else int(default)
    except (TypeError, ValueError):
        parsed = int(default)

    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _env_float(name: str, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
    """Read float-like environment variables safely with optional bounds."""
    value = os.getenv(name)
    try:
        parsed = float(str(value).strip()) if value is not None else float(default)
    except (TypeError, ValueError):
        parsed = float(default)

    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed

# Allowed Hosts
# In DEBUG mode, default to localhost hosts only. Override via DEBUG_ALLOWED_HOSTS.
if DEBUG:
    _debug_hosts = os.getenv('DEBUG_ALLOWED_HOSTS', '127.0.0.1,localhost,testserver')
    ALLOWED_HOSTS = [
        host.strip()
        for host in _debug_hosts.split(',')
        if host.strip()
    ]
    if not ALLOWED_HOSTS:
        ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
else:
    ALLOWED_HOSTS = [
        host.strip()
        for host in os.getenv('ALLOWED_HOSTS', '').split(',')
        if host.strip()
    ]
    if not ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            'ALLOWED_HOSTS is not set. Add comma-separated hostnames to your .env file.'
        )


# =============================================================================
# SUBDOMAIN ROUTING
# When both are set, SubdomainRoutingMiddleware splits traffic:
#   WEBSITE_DOMAIN → config.urls_website  (public site only)
#   PANEL_DOMAIN   → config.urls_panel    (admin panel + PWA)
# In local dev, leave both blank to serve everything on one domain.
# =============================================================================
# Subdomain Routing decommissioned - all traffic flows through ROOT_URLCONF.
# Convenience URLs for templates / email links
PANEL_URL = os.getenv('PANEL_URL', '').rstrip('/')


# =============================================================================
# APPLICATION DEFINITION
# =============================================================================

INSTALLED_APPS = [
    'corsheaders',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'core',
    'accounts',
    # ── New domain apps (replacing old names) ──────────────
    'organisation',      # replaces 'client'
    'managers',          # replaces 'assistants'
    'tables',            # replaces 'idcards' (merged IDCardGroup+IDCardTable → Table)
    # ── Legacy apps kept temporarily during transition ─────
    'client',            # TODO: remove after all imports updated
    'assistants',        # TODO: remove after all imports updated
    'idcards',           # TODO: remove after all imports updated
    # ──────────────────────────────────────────────────────
    'exports',
    'mediafiles',
    'staff',
    'operators',
    'stats',
    'reprintcard',
    'panel',
    'mobile_api',
    'desktop_app',
    'web_app',
]

# Debug toolbar is optional; only enable if DEBUG is on and package is installed.
_HAS_DEBUG_TOOLBAR = False
if DEBUG and not _running_tests():
    try:
        import debug_toolbar  # noqa: F401
        _HAS_DEBUG_TOOLBAR = True
    except ImportError:
        pass

if _HAS_DEBUG_TOOLBAR:
    INSTALLED_APPS += ['debug_toolbar']

SITE_ID = 1

# Custom User Model - Keep pointing to core.User for database compatibility
# The User class is defined in accounts but re-exported from core for migrations
AUTH_USER_MODEL = 'core.User'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'core.middleware.MobileAppCSRFBypassMiddleware',
    "django.middleware.security.SecurityMiddleware",
]

if _HAS_DEBUG_TOOLBAR:
    MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']

MIDDLEWARE += [
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Guest Sandbox Middleware - routes guest requests to isolated SQLite DB
    'core.middleware.GuestSandboxMiddleware',
    # Device-based session management — tracks last_active per device/session
    'accounts.middleware.DeviceSessionMiddleware',
    # Messages MUST be before custom middleware so force-logout redirects
    # can attach messages that are visible on the landing page.
    'django.contrib.messages.middleware.MessageMiddleware',
    # Request timing — logs duration, slow-request warnings (>1.5 s)
    'core.middleware.RequestTimingMiddleware',
    # Permission Validation Middleware - re-checks permissions on every request
    'core.middleware.PermissionValidationMiddleware',
    # Session idle timeout — logs out after SESSION_IDLE_TIMEOUT of inactivity
    'core.middleware.SessionIdleTimeoutMiddleware',
    # Security headers — Permissions-Policy, Cache-Control
    'core.middleware.SecurityHeadersMiddleware',
    # Maintenance mode — blocks panel for non-superadmin when enabled
    'core.middleware.MaintenanceModeMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# =============================================================================
# SEPARATE FRONTEND & BACKEND CORS & CSRF CONFIGURATION
# =============================================================================
CORS_ALLOW_ALL_ORIGINS = os.getenv('CORS_ALLOW_ALL_ORIGINS', 'True').lower() in ('true', '1', 'yes')
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',')
    if origin.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000').split(',')
    if origin.strip()
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.permissions',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DESKTOP_APP_ENABLED = _env_bool('DESKTOP_APP_ENABLED', True)
DESKTOP_APP_BOOTSTRAP_TOKEN = os.getenv('DESKTOP_APP_BOOTSTRAP_TOKEN', '').strip()
DESKTOP_APP_MAX_CONNECTIONS = _env_int('DESKTOP_APP_MAX_CONNECTIONS', 5, minimum=1, maximum=50)
DESKTOP_APP_TOKEN_MAX_AGE_SECONDS = _env_int('DESKTOP_APP_TOKEN_MAX_AGE_SECONDS', 60 * 60 * 24 * 30, minimum=3600)
DESKTOP_APP_DOWNLOAD_CHUNK_SIZE = _env_int('DESKTOP_APP_DOWNLOAD_CHUNK_SIZE', 1024 * 1024, minimum=64 * 1024, maximum=8 * 1024 * 1024)


if DEBUG:
    INTERNAL_IPS = ['127.0.0.1', 'localhost']

    def _debug_toolbar_show_toolbar(request):
        host = (request.get_host() or '').split(':')[0].lower()
        remote_addr = (request.META.get('REMOTE_ADDR') or '').strip()
        return remote_addr in {'127.0.0.1', '::1'} or host in {'127.0.0.1', 'localhost'}

    DEBUG_TOOLBAR_CONFIG = {
        'SHOW_TOOLBAR_CALLBACK': _debug_toolbar_show_toolbar,
    }
    # When running tests, Django sets DEBUG=False; allow tests to opt-out
    # of the Debug Toolbar system check by explicitly marking test mode.
    if _running_tests():
        DEBUG_TOOLBAR_CONFIG['IS_RUNNING_TESTS'] = False


# -----------------
# Sentry configuration
# -----------------
# Only initialize Sentry when a DSN is provided via env; keep disabled by default
SENTRY_DSN = os.getenv('SENTRY_DSN', '').strip()
if SENTRY_DSN:
    def _env_float_safe(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, default))
        except (TypeError, ValueError):
            return float(default)

    def _env_float_optional(name: str):
        v = os.getenv(name)
        if v is None or v == '':
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    SENTRY_TRACES_SAMPLE_RATE = _env_float_safe('SENTRY_TRACES_SAMPLE_RATE', 0.0)
    # Do NOT send PII to Sentry by default; make it opt-in via env var.
    SENTRY_SEND_PII = os.getenv('SENTRY_SEND_PII', 'False').strip().lower() in ('1', 'true', 'yes')
    SENTRY_ENABLE_LOGS = os.getenv('SENTRY_ENABLE_LOGS', 'False').strip().lower() in ('1', 'true', 'yes')
    SENTRY_PROFILES_SAMPLE_RATE = _env_float_optional('SENTRY_PROFILES_SAMPLE_RATE')
    SENTRY_PROFILE_SESSION_SAMPLE_RATE = _env_float_optional('SENTRY_PROFILE_SESSION_SAMPLE_RATE')
    SENTRY_PROFILE_LIFECYCLE = os.getenv('SENTRY_PROFILE_LIFECYCLE', '').strip() or None

    # Drop events originating from deprecated domains or unwanted noise if needed.
    def _sentry_before_send(event, hint):
        return event

    try:
        with open(os.path.join(BASE_DIR, 'VERSION.txt')) as f:
            SENTRY_RELEASE = f.read().strip()
    except Exception:
        SENTRY_RELEASE = None

    integrations = [DjangoIntegration()]
    if SENTRY_ENABLE_LOGS:
        log_integration = LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)
        integrations.append(log_integration)

    init_kwargs = dict(
        dsn=SENTRY_DSN,
        integrations=integrations,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=SENTRY_SEND_PII,
        before_send=_sentry_before_send,
        release=SENTRY_RELEASE,
    )

    # Optional profiling options
    if SENTRY_PROFILES_SAMPLE_RATE is not None:
        init_kwargs['profiles_sample_rate'] = SENTRY_PROFILES_SAMPLE_RATE
    if SENTRY_PROFILE_SESSION_SAMPLE_RATE is not None:
        init_kwargs['profile_session_sample_rate'] = SENTRY_PROFILE_SESSION_SAMPLE_RATE
    if SENTRY_PROFILE_LIFECYCLE:
        init_kwargs['profile_lifecycle'] = SENTRY_PROFILE_LIFECYCLE

    sentry_sdk.init(**init_kwargs)


# =============================================================================
# DATABASE
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases
# =============================================================================

# Production: Set DATABASE_URL in .env
# Example DATABASE_URL: postgres://user:password@host:5432/dbname

import sys
if os.getenv('RUNNING_TESTS') == '1' or 'pytest' in sys.modules or any('pytest' in arg or 'test' in arg for arg in sys.argv):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'test_db.sqlite3',
            'ATOMIC_REQUESTS': True,
        }
    }
else:
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        db_name = os.getenv('POSTGRES_DB', 'cardflow_db')
        db_user = os.getenv('POSTGRES_USER', 'postgres')
        db_password = os.getenv('POSTGRES_PASSWORD', 'postgres')
        db_host = os.getenv('POSTGRES_HOST', 'localhost')
        db_port = os.getenv('POSTGRES_PORT', '5432')
        DATABASE_URL = f"postgres://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }

DATABASE_ROUTERS = ['core.db_router.GuestSandboxRouter']


# =============================================================================
# SECURITY SETTINGS
# =============================================================================

# CSRF Trusted Origins
# Local: Not needed | Production: Add your domains
# Auto-configure for Render deployment
_csrf_origins = os.getenv('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [
    origin.strip() 
    for origin in _csrf_origins.split(',') 
    if origin.strip()
]

# Auto-add Render domain if RENDER_EXTERNAL_HOSTNAME is set
render_hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME')
if render_hostname:
    render_url = f'https://{render_hostname}'
    if render_url not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_url)

# CSRF failure view
CSRF_FAILURE_VIEW = 'core.views.errors.csrf_failure'

# ── Reverse-proxy SSL detection ──
# MUST be set whenever Django is behind Nginx/Apache that terminates SSL,
# REGARDLESS of DEBUG. Without this, Django thinks requests arrive over HTTP
# and CSRF origin checks fail (Origin says https:// but Django expects http://).
# This is configured outside the "if not DEBUG" block on purpose.
SECURE_PROXY_SSL_HEADER = (
    os.getenv('SECURE_PROXY_SSL_HEADER_NAME', 'HTTP_X_FORWARDED_PROTO'),
    os.getenv('SECURE_PROXY_SSL_HEADER_VALUE', 'https'),
) if os.getenv('SECURE_PROXY_SSL_HEADER_NAME', 'HTTP_X_FORWARDED_PROTO') else None

# Production security settings (only when DEBUG=False)
if not DEBUG:
    # HTTPS settings
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1', 'yes')
    
    # Cookie security is enforced later (below) based on DEBUG and an
    # optional FORCE_SECURE_COOKIES env toggle to avoid forcing secure
    # cookies in local, HTTP-only development environments.
    
    # HSTS settings
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ── Security headers (always applied, both dev and prod) ──
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

# ── Cookie hardening ──
# Allow forcing secure cookies via env in dev, otherwise enable them
# automatically only when DEBUG is False (production) or when the explicit
# toggle `FORCE_SECURE_COOKIES` is set to true. This prevents accidental
# secure-cookie enforcement when developing over plain HTTP locally.
FORCE_SECURE_COOKIES = _env_bool('FORCE_SECURE_COOKIES', False)
SECURE_COOKIES = (not DEBUG) or FORCE_SECURE_COOKIES

SESSION_COOKIE_HTTPONLY = True          # JS cannot read session cookie
SESSION_COOKIE_SAMESITE = 'Lax'        # CSRF mitigation
SESSION_COOKIE_SECURE = SECURE_COOKIES # Enforce HTTPS when appropriate
CSRF_COOKIE_SECURE = SECURE_COOKIES    # Enforce HTTPS when appropriate
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30   # 30-day sessions
SESSION_EXPIRE_AT_BROWSER_CLOSE = False # Session persists after browser close
CSRF_COOKIE_SAMESITE = 'Lax'           # CSRF cookie SameSite
# Ensure session cookie expiry is extended on every request.
SESSION_SAVE_EVERY_REQUEST = False

# ── Domain restriction ──
# REMOVE any existing domain overrides to prevent duplicate cookies
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_DOMAIN = None

# ── Session idle timeout (seconds) ──
# If a user has no requests for this period, session expires on next request.
# Set to 0 to disable. Default: 30 days (matches SESSION_COOKIE_AGE).
# The absolute max-age policy provides a secondary safety net.
SESSION_IDLE_TIMEOUT = int(os.getenv('SESSION_IDLE_TIMEOUT', str(60 * 60 * 24 * 30)))

# ── Session absolute max-age (seconds) ──
# Hard cap on session lifetime regardless of activity.
# Prevents indefinitely-valid stolen tokens from staying valid forever.
# Set to 0 to disable. Default: 30 days.
SESSION_ABSOLUTE_MAX_AGE = int(os.getenv('SESSION_ABSOLUTE_MAX_AGE', str(60 * 60 * 24 * 30)))

# ── Dashboard live-activity window (seconds) ──
# Used by dashboard "Live Working Clients". A user is considered live only if
# their session `_last_activity` is within this recent window.
DASHBOARD_LIVE_ACTIVE_WINDOW_SECONDS = int(os.getenv('DASHBOARD_LIVE_ACTIVE_WINDOW_SECONDS', '300'))

# ── Activity log clear safety toggles ──
# Disabled by default to prevent accidental destructive clears from the UI.
ACTIVITY_LOG_MANUAL_CLEAR_ENABLED = _env_bool('ACTIVITY_LOG_MANUAL_CLEAR_ENABLED', False)
ACTIVITY_LOG_CLEAR_CONFIRM_PHRASE = (
    os.getenv('ACTIVITY_LOG_CLEAR_CONFIRM_PHRASE', 'DELETE ALL LOGS').strip() or 'DELETE ALL LOGS'
)
# Automatic retention cleanup is disabled by default.
# Keep False in production unless you intentionally run scheduled archival/cleanup.
ACTIVITY_LOG_AUTOCLEAN_ENABLED = _env_bool('ACTIVITY_LOG_AUTOCLEAN_ENABLED', False)

# ── Session fingerprint validation ──
# Adds lightweight binding of a session to browser fingerprint material.
# Include IP binding only when infra has stable client egress IPs.
SESSION_FINGERPRINT_ENABLED = os.getenv(
    'SESSION_FINGERPRINT_ENABLED',
    'false' if DEBUG else 'true'
).strip().lower() in ('1', 'true', 'yes')
SESSION_FINGERPRINT_INCLUDE_IP = os.getenv(
    'SESSION_FINGERPRINT_INCLUDE_IP',
    'false'
).strip().lower() in ('1', 'true', 'yes')

# How often PermissionValidationMiddleware can skip DB revalidation.
# Lower values reduce access-revocation windows.
PERMISSION_REVALIDATION_INTERVAL = int(os.getenv('PERMISSION_REVALIDATION_INTERVAL', '20'))

# Dev-only OTP log visibility toggle.
# DEBUG alone no longer enables plaintext OTP logs.
DEV_LOG_OTP = _env_bool('DEV_LOG_OTP', False)

# CSP hardening toggles.
# IMPORTANT: The current templates still rely on inline <script> blocks and
# inline event handlers (onclick/oninput). Keep unsafe-inline enabled by
# default until those scripts are migrated to nonce/hash-safe external files.
CSP_ALLOW_UNSAFE_INLINE = _env_bool('CSP_ALLOW_UNSAFE_INLINE', True)
# Alpine full evaluator is required by existing x-show/x-bind expressions
# that use comparisons and logical operators across desktop/mobile templates.
CSP_ALLOW_UNSAFE_EVAL = _env_bool('CSP_ALLOW_UNSAFE_EVAL', True)

# ── Permissions-Policy header ──
# Restricts browser APIs not needed by this app.
# camera and microphone are allowed (self) for the PWA photo capture feature.
PERMISSIONS_POLICY = 'camera=(self), microphone=(self), geolocation=(), payment=(), usb=()'


# =============================================================================
# PASSWORD VALIDATION
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators
# =============================================================================

# Password validation baseline.
# Only enforce minimum 6-character length — no common-password or
# user-similarity checks.  Any combination of characters is allowed.
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 6,
        }
    },
]


# =============================================================================
# INTERNATIONALIZATION
# https://docs.djangoproject.com/en/5.2/topics/i18n/
# =============================================================================

LANGUAGE_CODE = 'en-us'

TIME_ZONE = os.getenv('TIME_ZONE', 'Asia/Kolkata')

USE_I18N = True

USE_TZ = True


# =============================================================================
# STATIC FILES (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/
# =============================================================================

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Whitenoise for serving static files in production
# CompressedManifest version: content-hashes filenames (app.js → app.abc123.js)
# enabling permanent caching with Cache-Control: immutable
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Safety: don't crash with 500 if a static file is missing from the manifest
# (e.g. dynamically-referenced vendor files in lazy-load.js or xlsx-worker.js)
WHITENOISE_MANIFEST_STRICT = False

# Media files (Uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Set to True ONLY when Nginx is configured with an internal /protected-media/
# location block (see deployment/nginx_example.conf). When False, Django serves
# media files directly even in production — slower but works without Nginx.
MEDIA_USE_XACCEL = os.getenv('MEDIA_USE_XACCEL', 'false').strip().lower() in ('1', 'true', 'yes')

# =============================================================================
# FILE UPLOAD LIMITS
# =============================================================================

# Max request body size. Keep this comfortably above the portfolio image/video upload
# paths so normal uploads do not trip Django's request-size guard before parsing.
DATA_UPLOAD_MAX_MEMORY_SIZE = _env_int(
    'DATA_UPLOAD_MAX_MEMORY_SIZE',
    512 * 1024 * 1024,
    minimum=10 * 1024 * 1024,
    maximum=2 * 1024 * 1024 * 1024,
)

# Max size for a single uploaded file kept in memory before spilling to disk.
# Larger portfolio videos will spill to disk and continue processing normally.
FILE_UPLOAD_MAX_MEMORY_SIZE = _env_int(
    'FILE_UPLOAD_MAX_MEMORY_SIZE',
    25 * 1024 * 1024,
    minimum=1 * 1024 * 1024,
    maximum=256 * 1024 * 1024,
)

# Max number of files per upload request.
# Create-with-XLSX folder uploads can legitimately include thousands of images.
# Keep this configurable via env while bounding to a safe upper limit.
DATA_UPLOAD_MAX_NUMBER_FILES = _env_int(
    'DATA_UPLOAD_MAX_NUMBER_FILES',
    6000,
    minimum=60,
    maximum=20000,
)


# =============================================================================
# BACKGROUND TASK WORKER
# =============================================================================

# ThreadPool size for DB-backed background tasks.
# Default 2 improves queue throughput while keeping memory bounded.
BACKGROUND_WORKER_MAX_WORKERS = max(
    1,
    min(4, int(os.getenv('BACKGROUND_WORKER_MAX_WORKERS', '2')))
)

# Heavy task concurrency cap (PDF/DOCX/ZIP generation, bulk uploads).
# Keep lower than worker count on low-memory hosts.
BACKGROUND_HEAVY_TASK_CONCURRENCY = max(
    1,
    min(BACKGROUND_WORKER_MAX_WORKERS, int(os.getenv('BACKGROUND_HEAVY_TASK_CONCURRENCY', '1')))
)


# =============================================================================
# CACHING
# =============================================================================

def _build_redis_location() -> str:
    """Return Redis location from URL or host/port components."""
    redis_url = os.getenv('REDIS_URL', '').strip()
    if redis_url:
        return redis_url

    redis_host = os.getenv('REDIS_HOST', '').strip()
    if not redis_host:
        return ''

    redis_scheme = os.getenv('REDIS_SCHEME', 'redis').strip() or 'redis'
    redis_port = _env_int('REDIS_PORT', 6379, minimum=1, maximum=65535)
    redis_db = _env_int('REDIS_DB', 1, minimum=0, maximum=15)
    redis_username = os.getenv('REDIS_USERNAME', '').strip()
    redis_password = os.getenv('REDIS_PASSWORD', '').strip()

    auth_segment = ''
    if redis_username or redis_password:
        auth_segment = f'{redis_username}:{redis_password}@' if redis_username else f':{redis_password}@'

    return f'{redis_scheme}://{auth_segment}{redis_host}:{redis_port}/{redis_db}'


# Production/shared cache path:
# - REDIS_URL (preferred), or REDIS_HOST + REDIS_PORT + REDIS_DB components.
# Local dev:
# - falls back to LocMemCache when Redis is not configured.
REDIS_LOCATION = _build_redis_location()
CACHE_DEFAULT_TIMEOUT = _env_int('CACHE_DEFAULT_TIMEOUT', 300, minimum=1, maximum=86400)
CACHE_KEY_PREFIX = os.getenv('CACHE_KEY_PREFIX', 'adarsh').strip() or 'adarsh'
CACHE_VERSION = _env_int('CACHE_VERSION', 1, minimum=1)

if REDIS_LOCATION:
    # Production: Redis — OTP, rate limiting, and export locks are shared
    # across all Gunicorn workers.
    REDIS_SOCKET_TIMEOUT = _env_float('REDIS_SOCKET_TIMEOUT', 1.5, minimum=0.1, maximum=30.0)
    REDIS_SOCKET_CONNECT_TIMEOUT = _env_float('REDIS_SOCKET_CONNECT_TIMEOUT', 1.5, minimum=0.1, maximum=30.0)
    REDIS_HEALTH_CHECK_INTERVAL = _env_int('REDIS_HEALTH_CHECK_INTERVAL', 30, minimum=1, maximum=300)
    REDIS_MAX_CONNECTIONS = _env_int('REDIS_MAX_CONNECTIONS', 100, minimum=10, maximum=2000)

    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_LOCATION,
            'TIMEOUT': CACHE_DEFAULT_TIMEOUT,
            'KEY_PREFIX': CACHE_KEY_PREFIX,
            'VERSION': CACHE_VERSION,
            'OPTIONS': {
                'socket_connect_timeout': REDIS_SOCKET_CONNECT_TIMEOUT,
                'socket_timeout': REDIS_SOCKET_TIMEOUT,
                'health_check_interval': REDIS_HEALTH_CHECK_INTERVAL,
                'retry_on_timeout': True,
                'max_connections': REDIS_MAX_CONNECTIONS,
                'client_name': os.getenv('REDIS_CLIENT_NAME', 'adarsh-django-cache').strip() or 'adarsh-django-cache',
            },
        }
    }

    # Reduce session DB pressure in production by caching session reads.
    SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
    SESSION_CACHE_ALIAS = 'default'
else:
    # Local development: choose cache backend.
    # For low-memory servers without Redis, enable a disk-backed file cache by
    # setting USE_FILE_CACHE=1 and optional FILE_CACHE_DIR=<path> in .env.
    _USE_FILE_CACHE = os.getenv('USE_FILE_CACHE', 'False').strip().lower() in ('1', 'true', 'yes')
    if _USE_FILE_CACHE:
        FILE_CACHE_DIR = os.getenv('FILE_CACHE_DIR', str(BASE_DIR / 'cache')).strip() or str(BASE_DIR / 'cache')
        try:
            os.makedirs(FILE_CACHE_DIR, exist_ok=True)
        except Exception:
            # If we cannot create the directory, fall back to LocMemCache to avoid startup failure.
            FILE_CACHE_DIR = None

    if _USE_FILE_CACHE and FILE_CACHE_DIR:
        CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
                'LOCATION': FILE_CACHE_DIR,
                'TIMEOUT': CACHE_DEFAULT_TIMEOUT,
                'KEY_PREFIX': CACHE_KEY_PREFIX,
                'VERSION': CACHE_VERSION,
            }
        }
        # Use cached DB-backed sessions to reduce DB pressure when possible
        SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
        SESSION_CACHE_ALIAS = 'default'
    else:
        # Local development: LocMemCache (per-process, no setup needed)
        CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                'TIMEOUT': CACHE_DEFAULT_TIMEOUT,
                'KEY_PREFIX': CACHE_KEY_PREFIX,
                'VERSION': CACHE_VERSION,
                'OPTIONS': {
                    'MAX_ENTRIES': 1000,
                },
            }
        }

# Redis is optional. If it is not configured or temporarily unavailable at
# deploy time, the app keeps working with the existing local cache fallback.

# =============================================================================
# REAL-TIME (DJANGO CHANNELS)
# =============================================================================

# Reuse existing Redis by default so websocket fanout is shared across workers.
# Override REDIS_CHANNEL_LAYER_URL only when channel traffic must use a different Redis.
REDIS_CHANNEL_LAYER_URL = os.getenv('REDIS_CHANNEL_LAYER_URL', '').strip() or REDIS_LOCATION
REDIS_CHANNEL_PREFIX = os.getenv('REDIS_CHANNEL_PREFIX', 'adarsh:realtime').strip() or 'adarsh:realtime'
REDIS_CHANNEL_CAPACITY = _env_int('REDIS_CHANNEL_CAPACITY', 1500, minimum=100, maximum=20000)
REDIS_CHANNEL_EXPIRY = _env_int('REDIS_CHANNEL_EXPIRY', 30, minimum=5, maximum=3600)

# Optional Celery scaffold for offloading background tasks to a real worker.
# When unset, the app keeps using the existing in-process ThreadPool fallback.
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', '').strip()
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', '').strip()
CELERY_TASK_ALWAYS_EAGER = _env_bool('CELERY_TASK_ALWAYS_EAGER', False)
CELERY_TASK_EAGER_PROPAGATES = True

if REDIS_CHANNEL_LAYER_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_CHANNEL_LAYER_URL],
                'capacity': REDIS_CHANNEL_CAPACITY,
                'expiry': REDIS_CHANNEL_EXPIRY,
                'prefix': REDIS_CHANNEL_PREFIX,
            },
        }
    }
else:
    # Local fallback when Redis is not configured (DEBUG-only expected).
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        }
    }


# =============================================================================
# AUTHENTICATION
# =============================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Login settings
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'


# =============================================================================
# EMAIL CONFIGURATION
# Local: Console backend (emails printed to terminal)
# Production: SMTP backend (set credentials in .env)
# =============================================================================

# Check if email credentials are provided
_email_configured = bool(os.getenv('EMAIL_HOST_USER'))

if _email_configured:
    # Production: Use SMTP
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
    EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
    DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)
else:
    # Local development: Print emails to console
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    EMAIL_HOST_USER = ''
    EMAIL_HOST_PASSWORD = ''
    DEFAULT_FROM_EMAIL = 'noreply@localhost'

# Contact form recipient — if not set, contact-form emails are silently skipped
CONTACT_FORM_RECIPIENT = os.getenv('CONTACT_FORM_RECIPIENT', '')

# Site URL for email links
# Local: http://localhost:8000 | Production: Set SITE_URL in .env
SITE_URL = os.getenv('SITE_URL', 'http://localhost:8000')

# Client tutorial page video URL (shown on /panel/tutorial/)
CLIENT_TUTORIAL_VIDEO_URL = os.getenv('CLIENT_TUTORIAL_VIDEO_URL', 'https://www.youtube.com/')



# =============================================================================
# APP VERSION
# =============================================================================

def _get_app_version() -> str:
    """
    Resolve the running app version using these sources (in order):
      1. VERSION.txt file at the project root  (canonical source)
      2. APP_VERSION environment variable
      3. `git describe --tags --always`  (dev fallback)
      4. Hard-coded fallback
    """
    import subprocess as _sp

    # 1. VERSION.txt  (canonical)
    ver_file = BASE_DIR / 'VERSION.txt'
    try:
        if ver_file.exists():
            v = ver_file.read_text().strip()
            if v:
                return v if v.startswith('v') else f'v{v}'
    except Exception:
        pass

    # 2. Environment variable
    env_ver = os.getenv('APP_VERSION', '').strip()
    if env_ver:
        return env_ver if env_ver.startswith('v') else f'v{env_ver}'

    # 3. Git describe (fallback for dev)
    try:
        r = _sp.run(
            ['git', 'describe', '--tags', '--always'],
            capture_output=True, text=True,
            cwd=str(BASE_DIR), timeout=2,
        )
        if r.returncode == 0:
            v = r.stdout.strip()
            if v:
                return v if v.startswith('v') else f'v{v}'
    except Exception:
        pass

    return 'v0.00.00'


APP_VERSION = _get_app_version()
LATEST_MOBILE_VERSION = os.getenv('LATEST_MOBILE_VERSION', '1.0.56')

try:
    MOBILE_PWA_CACHE_GENERATION = max(1, int(os.getenv('MOBILE_PWA_CACHE_GENERATION', '2')))
except ValueError:
    MOBILE_PWA_CACHE_GENERATION = 2

try:
    MOBILE_PWA_CACHE_ROLLBACK_WINDOW = max(1, int(os.getenv('MOBILE_PWA_CACHE_ROLLBACK_WINDOW', '2')))
except ValueError:
    MOBILE_PWA_CACHE_ROLLBACK_WINDOW = 2


# =============================================================================
# PERFORMANCE MONITORING THRESHOLDS
# =============================================================================

# Requests slower than this are logged as WARNING by RequestTimingMiddleware
SLOW_REQUEST_THRESHOLD = float(os.getenv('SLOW_REQUEST_THRESHOLD', '1.5'))

# Requests with more queries than this trigger EXCESSIVE QUERIES warning
QUERY_COUNT_THRESHOLD = int(os.getenv('QUERY_COUNT_THRESHOLD', '50'))

# Individual SQL queries slower than this (seconds) are logged to queries.log
SLOW_QUERY_THRESHOLD = float(os.getenv('SLOW_QUERY_THRESHOLD', '0.1'))

# Optional per-query execute_wrapper instrumentation.
# Keep disabled by default because it adds noticeable overhead on busy systems,
# especially when DEBUG=True.
ENABLE_REQUEST_QUERY_TRACKING = _env_bool('ENABLE_REQUEST_QUERY_TRACKING', default=False)


# =============================================================================
# LOGGING
# =============================================================================

# M3: Whether to also write logs to rotating files on disk.
# Enable on VPS / bare-metal by setting LOG_TO_FILE=true in .env.
# Leave unset (default False) on ephemeral containers (Render, Docker)
# where logs/ is wiped on restart — stdout/stderr is captured by the host.
LOG_TO_FILE = os.getenv('LOG_TO_FILE', 'false').strip().lower() in ('1', 'true', 'yes')

# Keep DB backend query logging conservative by default. Full DEBUG SQL logs
# can significantly slow requests under concurrent usage.
_DB_BACKEND_LOG_LEVEL = os.getenv('DJANGO_DB_LOG_LEVEL', 'WARNING').strip().upper()
if _DB_BACKEND_LOG_LEVEL not in {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}:
    _DB_BACKEND_LOG_LEVEL = 'WARNING'

LOG_DIR = os.path.join(BASE_DIR, 'logs')
if LOG_TO_FILE:
    os.makedirs(LOG_DIR, exist_ok=True)

# Handler lists — conditionally include file handlers to avoid creating
# RotatingFileHandler instances (which open file descriptors) on containers.
_APP_HANDLERS = ['console'] + (['file_app', 'file_error'] if LOG_TO_FILE else [])
_APP_HANDLER  = ['console'] + (['file_app'] if LOG_TO_FILE else [])
_SEC_HANDLERS = ['console'] + (['file_security', 'file_app'] if LOG_TO_FILE else [])
_QRY_HANDLER  = ['file_queries'] if LOG_TO_FILE else ['console']

_file_handlers: dict = {}
if LOG_TO_FILE:
    _file_handlers = {
        'file_app': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'app.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
            'level': 'INFO',
        },
        'file_error': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'error.log'),
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'ERROR',
        },
        'file_security': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'security.log'),
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'verbose',
            'level': 'INFO',
        },
        'file_queries': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'queries.log'),
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 3,
            'formatter': 'verbose',
            'level': 'WARNING',
        },
    }

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {module}.{funcName}:{lineno} — {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '{levelname} {name}: {message}',
            'style': '{',
        },
    },

    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },

    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose' if not DEBUG else 'simple',
            'level': 'DEBUG' if DEBUG else 'INFO',
        },
        **_file_handlers,
    },

    # Root logger — console always; file handlers only when LOG_TO_FILE=true
    'root': {
        'handlers': _APP_HANDLERS,
        'level': 'DEBUG' if DEBUG else 'INFO',
    },

    'loggers': {
        'django': {
            'handlers': _APP_HANDLER,
            'level': 'INFO',
            'propagate': False,
        },
        # Capture 500 errors from Django's request handler — written to error.log
        'django.request': {
            'handlers': _APP_HANDLERS,  # includes file_error (ERROR level) when LOG_TO_FILE
            'level': 'WARNING',
            'propagate': False,
        },
        # Security-sensitive loggers — also write to security.log when enabled
        'django.security': {
            'handlers': _SEC_HANDLERS,
            'level': 'INFO',
            'propagate': False,
        },
        'accounts': {
            'handlers': _SEC_HANDLERS,
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'core.middleware': {
            'handlers': _SEC_HANDLERS,
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        # Slow/excessive query logging — file when LOG_TO_FILE, else console
        'slow_queries': {
            'handlers': _QRY_HANDLER,
            'level': 'WARNING',
            'propagate': False,
        },
        # DB backend query logging — only verbose in DEBUG mode
        'django.db.backends': {
            'handlers': ['console'],
            'level': _DB_BACKEND_LOG_LEVEL,
            'propagate': False,
        },
    },
}

# Mobile App Version Tracking
# Can be set dynamically via .env (e.g. LATEST_MOBILE_VERSION=1.1.7)
LATEST_MOBILE_VERSION = os.getenv('LATEST_MOBILE_VERSION', '').strip() or None

# Web App API Key for Landing Website Integration
# Default fallback is provided if not set in .env
WEB_APP_API_KEY = os.getenv('WEB_APP_API_KEY', 'adarsh_secure_fallback_key_2026_web_app').strip().strip("'\"")

