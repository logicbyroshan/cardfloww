"""
Notification Service  (panel app)
==================================
Central authority for all notification operations.
Models remain in core.models to avoid migrations; this service just lives here.
"""

# Re-export from core.services so nothing breaks if code still imports from there.
from core.services.notification_service import NotificationService

__all__ = ['NotificationService']
