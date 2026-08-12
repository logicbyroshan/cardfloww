"""
Notification API Views  (core/views shim)
==========================================

All implementation has moved to ``panel/views/notification_views.py``.
This shim re-exports everything so that existing imports in
``core/views/__init__.py`` and ``core/urls.py`` continue to work unchanged.
"""

from panel.views.notification_views import (  # noqa: F401
    api_notifications_list,
    api_notifications_unread_count,
    api_notification_mark_read,
    api_notifications_mark_all_read,
    api_client_message_strip,
    api_panel_notifications_list,
    api_panel_notification_create,
    api_panel_notification_delete,
    api_panel_target_users,
)
