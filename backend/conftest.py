import os
import sys
import django.core.validators


# CRITICAL: Set RUNNING_TESTS BEFORE DJANGO IMPORTS
os.environ['RUNNING_TESTS'] = '1'
os.environ['DEBUG'] = 'True'  # Force settings to think we're in DEBUG mode for checks, but exclude debug_toolbar

# Now import pytest
import pytest

# Configure Django BEFORE setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Import settings BEFORE django.setup() so we can override them
from django.conf import settings
import tempfile

_pytest_temp_db = os.path.join(tempfile.gettempdir(), f"pytest_db_{os.getpid()}.sqlite3")
settings.DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': _pytest_temp_db,
        'ATOMIC_REQUESTS': True,
        'OPTIONS': {
            'timeout': 20,
        }
    }
}

# Now setup Django with the overridden settings
import django
django.setup()

import builtins
from mobile_api.views import Staff

builtins.Staff = Staff

# Note: pytest-django sets up the test environment; avoid calling
# `setup_test_environment()` at import time to prevent repeated-initialization errors.

# After Django setup, remove debug_toolbar from MIDDLEWARE and INSTALLED_APPS if present
if 'debug_toolbar' in settings.INSTALLED_APPS:
    settings.INSTALLED_APPS = tuple(
        app for app in settings.INSTALLED_APPS if app != 'debug_toolbar'
    )
if 'debug_toolbar.middleware.DebugToolbarMiddleware' in settings.MIDDLEWARE:
    settings.MIDDLEWARE = tuple(
        m for m in settings.MIDDLEWARE if m != 'debug_toolbar.middleware.DebugToolbarMiddleware'
    )

# Run migrations on the in-memory database immediately after Django setup
# REMOVED: call_command at module level causes RuntimeError with pytest-django
# Will run migrations via pytest_configure hook instead

def pytest_configure(config):
    """Initialize test database with migrations."""
    # Running migrations here causes pytest-django to raise "Database access not allowed"
    # because database access is blocked until the proper fixtures are used. Rely on
    # pytest-django to manage the test database lifecycle via its fixtures instead.
    # If an explicit migrate run is required, run tests with a dedicated option
    # or implement a session-scoped fixture that uses the `django_db_blocker`.
    return

# Marker lanes are applied centrally so we don't need to touch hundreds of test files.
SLOW_NODEID_PREFIXES = (
    "exports/tests.py::",
    "core/tests.py::",
    "client/tests.py::",
    "panel/tests.py::",
    "reprintcard/tests.py::",
    "staff/tests.py::",
)

VERY_SLOW_NODEID_CONTAINS = (
)

IMPORTANT_NODEID_CONTAINS = (
    "SecurityApiRegressionTests",
    # OfficeWork app removed; keep marker list focused on active suites
    "ReprintApiIntegrationTests",
    "ClientApiIntegrationTests",
    "ExportApiIntegrationAdvancedTests",
    "ExportDeepLimitAndRoleTests",
)



def pytest_collection_modifyitems(items):
    for item in items:
        nodeid = item.nodeid

        if nodeid.startswith(SLOW_NODEID_PREFIXES):
            item.add_marker(pytest.mark.slow)

        if any(token in nodeid for token in VERY_SLOW_NODEID_CONTAINS):
            item.add_marker(pytest.mark.very_slow)

        if any(token in nodeid for token in IMPORTANT_NODEID_CONTAINS):
            item.add_marker(pytest.mark.important)



