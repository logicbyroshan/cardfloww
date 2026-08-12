"""
Monitoring API  (core/views shim)
==================================

All implementation has moved to ``panel/views/monitoring_views.py``.
This shim re-exports everything so that existing imports in
``core/views/__init__.py`` and ``core/urls.py`` continue to work unchanged.
"""

from panel.views.monitoring_views import (  # noqa: F401
    api_activity_log_clear_generate_code,
    api_activity_log_clear_state,
    api_client_errors,
    api_clear_activity_logs,
    api_monitoring_data,
    api_operations_feed,
    api_server_info_snapshot,
)
