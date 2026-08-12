"""
Backup API views  (core/views shim)
=====================================

All implementation has moved to ``panel/views/backup_views.py``.
This shim re-exports everything so that existing imports in
``core/views/__init__.py`` and ``core/urls.py`` continue to work unchanged.
"""

from panel.views.backup_views import (  # noqa: F401
    backup_select_clients,
    api_backup_generate_code,
    api_backup_initiate,
    api_backup_start,
    api_backup_status,
    api_backup_list,
    api_backup_delete_now,
    api_backup_download,
)
