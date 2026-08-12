"""
Maintenance Mode Service
========================
Manages system-wide maintenance mode using SystemSettings.
- Toggle maintenance on/off
- Get maintenance status
- Send notification to all users when maintenance starts
"""
import logging
from datetime import datetime, timedelta

from django.core.cache import cache
from django.utils import timezone

from core.models import SystemSettings

logger = logging.getLogger(__name__)

CACHE_KEY = 'maintenance_mode_status'
CACHE_TTL = 10  # seconds — short so changes propagate fast


class MaintenanceService:
    """Service for maintenance mode operations."""

    @classmethod
    def is_active(cls):
        """Check if maintenance mode is currently active. Cached 10s."""
        status = cache.get(CACHE_KEY)
        if status is not None:
            return status

        enabled = SystemSettings.get_value('maintenance_mode', 'false')
        if enabled != 'true':
            cache.set(CACHE_KEY, False, CACHE_TTL)
            return False

        # Check if end time has passed
        end_str = SystemSettings.get_value('maintenance_end_time', '')
        if end_str:
            try:
                end_time = datetime.fromisoformat(end_str)
                if timezone.is_naive(end_time):
                    end_time = timezone.make_aware(end_time)
                if timezone.now() >= end_time:
                    # Auto-disable maintenance mode
                    cls.deactivate(auto=True)
                    cache.set(CACHE_KEY, False, CACHE_TTL)
                    return False
            except (ValueError, TypeError):
                pass

        cache.set(CACHE_KEY, True, CACHE_TTL)
        return True

    @classmethod
    def get_status(cls):
        """Get full maintenance status dict."""
        enabled = SystemSettings.get_value('maintenance_mode', 'false') == 'true'
        end_str = SystemSettings.get_value('maintenance_end_time', '')
        message = SystemSettings.get_value('maintenance_message', '')

        end_time = None
        if end_str:
            try:
                end_time = datetime.fromisoformat(end_str)
                if timezone.is_naive(end_time):
                    end_time = timezone.make_aware(end_time)
                # Auto-disable if expired
                if enabled and timezone.now() >= end_time:
                    cls.deactivate(auto=True)
                    enabled = False
            except (ValueError, TypeError):
                end_time = None

        return {
            'enabled': enabled,
            'end_time': end_time.isoformat() if end_time else None,
            'message': message,
        }

    @classmethod
    def activate(cls, *, end_time=None, message='', duration_minutes=None, user=None):
        """
        Enable maintenance mode.

        Args:
            end_time: ISO datetime string for when maintenance ends
            message: Custom message to display
            duration_minutes: Alternative to end_time — minutes from now
            user: The user activating maintenance (for notification)
        """
        if duration_minutes and not end_time:
            end_dt = timezone.now() + timedelta(minutes=int(duration_minutes))
            end_time = end_dt.isoformat()

        SystemSettings.set_value('maintenance_mode', 'true', 'Maintenance mode enabled')
        SystemSettings.set_value('maintenance_end_time', end_time or '', 'Maintenance end time')
        SystemSettings.set_value('maintenance_message', message or 'The system is under scheduled maintenance.', 'Maintenance message')
        cache.delete(CACHE_KEY)

        # Send notification to all users
        cls._send_notification(end_time, message, user)

        logger.info("Maintenance mode ACTIVATED by %s, ends: %s",
                     user.username if user else 'system', end_time or 'manual')

    @classmethod
    def deactivate(cls, auto=False, user=None):
        """Disable maintenance mode."""
        SystemSettings.set_value('maintenance_mode', 'false', 'Maintenance mode disabled')
        cache.delete(CACHE_KEY)

        if not auto:
            cls._send_deactivation_notification(user)

        logger.info("Maintenance mode DEACTIVATED %s",
                     f"by {user.username}" if user else "(auto-expired)" if auto else "")

    @classmethod
    def _send_notification(cls, end_time_str, message, user):
        """Create a broadcast notification for all users."""
        from core.services.notification_service import NotificationService

        end_display = ''
        if end_time_str:
            try:
                end_dt = datetime.fromisoformat(end_time_str)
                if timezone.is_naive(end_dt):
                    end_dt = timezone.make_aware(end_dt)
                end_display = end_dt.strftime('%d %b %Y, %I:%M %p')
            except (ValueError, TypeError):
                pass

        body = message or 'The system is under scheduled maintenance.'
        if end_display:
            body += f'\n\nEstimated completion: {end_display}'

        NotificationService.create_notification(
            title='System Maintenance Started',
            message=body,
            priority='urgent',
            category='maintenance',
            target='all',
            created_by=user,
        )

    @classmethod
    def _send_deactivation_notification(cls, user):
        """Notify all users that maintenance is over."""
        from core.services.notification_service import NotificationService

        NotificationService.create_notification(
            title='System Maintenance Completed',
            message='Maintenance is complete. All services are back to normal.',
            priority='normal',
            category='maintenance',
            target='all',
            created_by=user,
        )
