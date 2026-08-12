"""
core/services/backup_service.py  (shim)
=========================================

All implementation has moved to ``panel/services/backup_service.py``.
This shim re-exports the public API so no existing callers need changes.
"""

from panel.services.backup_service import (  # noqa: F401
    start_backup,
    delete_backup_files,
)
