import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from organisation.models import Organisation

from ..models import ClientPresenceSession
from .realtime_service import publish_topic_event
from .permission_service import PermissionService

logger = logging.getLogger(__name__)


class LiveClientPresenceService:
    """Tracks live client presence using explicit client-side start/heartbeat/stop events."""

    DASHBOARD_REALTIME_TOPIC = 'dashboard.working'

    @classmethod
    def _live_window_seconds(cls):
        return max(int(getattr(settings, 'DASHBOARD_LIVE_ACTIVE_WINDOW_SECONDS', 300) or 0), 30)

    @classmethod
    def _retention_hours(cls):
        return max(int(getattr(settings, 'LIVE_PRESENCE_RETENTION_HOURS', 24) or 0), 1)

    @classmethod
    def _active_cutoff(cls, now=None):
        now = now or timezone.now()
        return now - timedelta(seconds=cls._live_window_seconds())

    @classmethod
    def _active_queryset(cls, now=None):
        cutoff = cls._active_cutoff(now=now)
        return ClientPresenceSession.objects.filter(
            closed_at__isnull=True,
            last_seen_at__gte=cutoff,
        )

    @classmethod
    def _publish_dashboard_presence_changed(cls, *, trigger, action=''):
        try:
            publish_topic_event(
                topic=cls.DASHBOARD_REALTIME_TOPIC,
                event_type='dashboard.presence.changed',
                payload={
                    'trigger': str(trigger or ''),
                    'action': str(action or ''),
                    'at': timezone.now().isoformat(),
                },
            )
        except Exception:
            logger.exception('Failed to publish dashboard presence websocket event')

    @classmethod
    def retire_stale_sessions(cls, now=None):
        now = now or timezone.now()
        cutoff = cls._active_cutoff(now=now)

        stale_qs = ClientPresenceSession.objects.filter(
            closed_at__isnull=True,
            last_seen_at__lt=cutoff,
        )
        updated = stale_qs.update(closed_at=now)

        retention_cutoff = now - timedelta(hours=cls._retention_hours())
        ClientPresenceSession.objects.filter(closed_at__lt=retention_cutoff).delete()

        if updated:
            cls._publish_dashboard_presence_changed(trigger='retire_stale')

        return updated

    @classmethod
    def resolve_client_id_for_user(cls, user):
        role = str(getattr(user, 'role', '') or '').lower()

        if role in ('client', 'prime_manager', 'manager', 'super_manager', 'guest_prime_manager', 'guest_manager'):
            if hasattr(user, 'client_profile') and user.client_profile:
                return user.client_profile.id
            if hasattr(user, 'org_manager_profile') and user.org_manager_profile:
                return user.org_manager_profile.organisation_id
            org_id = (
                Organisation.objects.filter(
                    user_id=user.id,
                    status='active',
                    user__is_active=True,
                )
                .values_list('id', flat=True)
                .first()
            )
            if org_id:
                return org_id
            from organisation.models import OrganisationManager
            return (
                OrganisationManager.objects.filter(
                    user_id=user.id,
                    is_active=True,
                    organisation__status='active',
                )
                .values_list('organisation_id', flat=True)
                .first()
            )

        if role in ('assistant', 'client_staff', 'staff'):
            if hasattr(user, 'staff_profile') and user.staff_profile:
                return getattr(user.staff_profile, 'client_id', None) or getattr(user.staff_profile, 'organisation_id', None)
            from assistants.models import Assistant
            aid = (
                Assistant.objects.filter(
                    user_id=user.id,
                    user__is_active=True,
                    client_id__isnull=False,
                    client__status='active',
                )
                .values_list('client_id', flat=True)
                .first()
            )
            if aid:
                return aid
            from staff.models import Staff
            return (
                Staff.objects.filter(
                    user_id=user.id,
                    user__is_active=True,
                    client_id__isnull=False,
                )
                .values_list('client_id', flat=True)
                .first()
            )

        return None

    @classmethod
    def is_client_live(cls, client_id, now=None):
        if not client_id:
            return False
        return cls._active_queryset(now=now).filter(client_id=client_id).exists()

    @classmethod
    def is_assistant_live(cls, user_id, now=None):
        if not user_id:
            return False
        return cls._active_queryset(now=now).filter(
            user_id=user_id,
            user_role__in=['assistant', 'client_staff', 'staff']
        ).exists()

    @classmethod
    def record_event(cls, *, user, session_key, tab_id, action):
        action = str(action or '').strip().lower()
        if action not in {'start', 'heartbeat', 'stop'}:
            return {'tracked': False, 'changed': False, 'reason': 'invalid_action'}

        session_key = str(session_key or '').strip()
        tab_id = str(tab_id or '').strip()[:80]
        if not session_key or not tab_id:
            return {'tracked': False, 'changed': False, 'reason': 'missing_session_or_tab'}

        now = timezone.now()
        cls.retire_stale_sessions(now=now)

        client_id = cls.resolve_client_id_for_user(user)
        if not client_id:
            return {'tracked': False, 'changed': False, 'reason': 'role_not_tracked'}

        role = str(getattr(user, 'role', '') or '').lower()
        before_live = cls.is_client_live(client_id, now=now)
        before_assistant_live = cls.is_assistant_live(user.id, now=now) if role in ('assistant', 'client_staff', 'staff') else False

        with transaction.atomic():
            presence, created = ClientPresenceSession.objects.select_for_update().get_or_create(
                session_key=session_key,
                tab_id=tab_id,
                defaults={
                    'user_id': user.id,
                    'client_id': client_id,
                    'user_role': role,
                    'last_seen_at': now,
                    'closed_at': now if action == 'stop' else None,
                },
            )

            if not created:
                presence.user_id = user.id
                presence.client_id = client_id
                presence.user_role = role
                presence.last_seen_at = now
                presence.closed_at = now if action == 'stop' else None
                presence.save(update_fields=['user', 'client', 'user_role', 'last_seen_at', 'closed_at'])

        after_live = cls.is_client_live(client_id, now=now)
        after_assistant_live = cls.is_assistant_live(user.id, now=now) if role in ('assistant', 'client_staff', 'staff') else False
        changed = (before_live != after_live) or (before_assistant_live != after_assistant_live)
        if changed:
            cls._publish_dashboard_presence_changed(trigger='record_event', action=action)

        # Check active users threshold for emergency alerts
        try:
            from django.core.cache import cache
            active_users_count = cls._active_queryset(now=now).values_list('session_key', flat=True).distinct().count()
            if active_users_count > 50:
                if not cache.get('emergency_server_email_sent'):
                    cache.set('emergency_server_email_sent', True, 1800) # Throttled for 30 minutes
                    
                    from core.models import User
                    from core.utils.threaded_email import send_mail_async
                    
                    admin_emails = list(User.objects.filter(
                        role='super_admin',
                        is_active=True,
                        email__isnull=False
                    ).exclude(email='').values_list('email', flat=True))
                    
                    if admin_emails:
                        subject = "[EMERGENCY] Update the Server / High Traffic Detected"
                        message = (
                            f"Emergency! Please update the server.\n\n"
                            f"Live working users count has reached {active_users_count}, which is above the safe threshold of 50."
                        )
                        send_mail_async(
                            subject=subject,
                            message=message,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=admin_emails,
                            email_type='system'
                        )
        except Exception as alert_err:
            logger.error("Failed to process emergency active users alert: %s", alert_err)

        return {
            'tracked': True,
            'changed': changed,
            'client_id': client_id,
            'is_live_now': after_live,
        }

    @classmethod
    def get_live_client_ids_for_user(cls, user):
        now = timezone.now()
        cls.retire_stale_sessions(now=now)

        live_ids = set(cls._active_queryset(now=now).values_list('client_id', flat=True).distinct())
        if PermissionService.is_operator(user):
            allowed_ids = set(PermissionService.get_accessible_client_ids(user))
            live_ids &= allowed_ids

        return sorted(live_ids)

    @classmethod
    def get_live_assistant_count_for_user(cls, user):
        now = timezone.now()
        cls.retire_stale_sessions(now=now)

        qs = cls._active_queryset(now=now).filter(user_role__in=['assistant', 'client_staff', 'staff'])
        if PermissionService.is_operator(user):
            allowed_ids = set(PermissionService.get_accessible_client_ids(user))
            qs = qs.filter(client_id__in=allowed_ids)

        return qs.values_list('user_id', flat=True).distinct().count()

    @classmethod
    def get_live_assistant_client_ids_for_user(cls, user):
        now = timezone.now()
        cls.retire_stale_sessions(now=now)

        qs = cls._active_queryset(now=now).filter(
            user_role__in=['assistant', 'client_staff', 'staff'],
            client_id__isnull=False,
        )
        if PermissionService.is_operator(user):
            allowed_ids = set(PermissionService.get_accessible_client_ids(user))
            qs = qs.filter(client_id__in=allowed_ids)

        live_ids = set(qs.values_list('client_id', flat=True).distinct())
        return sorted(live_ids)

    @classmethod
    def get_live_payload_for_user(cls, user):
        """Build the complete presence payload with minimal DB queries.

        Optimized: calls retire_stale_sessions() and permission checks ONCE
        instead of 3x (one per sub-method).  Reduces DB round-trips from
        6-9 queries to 2-3 per call.
        """
        now = timezone.now()
        cls.retire_stale_sessions(now=now)

        # Determine permission scope once
        is_scoped = PermissionService.is_operator(user)
        allowed_ids = set(PermissionService.get_accessible_client_ids(user)) if is_scoped else None

        # Single query: fetch all active sessions
        active_qs = cls._active_queryset(now=now).values_list('client_id', 'user_id', 'user_role', 'session_key')
        active_rows = list(active_qs)

        # Split into client IDs and assistant data in Python (cheap)
        all_client_ids = set()
        assistant_user_ids = set()
        assistant_client_ids = set()
        active_sessions = set()

        for client_id, user_id, user_role, session_key in active_rows:
            if is_scoped and allowed_ids and client_id not in allowed_ids:
                continue
            if client_id is not None:
                all_client_ids.add(client_id)
            if user_role in ('assistant', 'client_staff', 'staff'):
                assistant_user_ids.add(user_id)
                if client_id is not None:
                    assistant_client_ids.add(client_id)
            active_sessions.add(session_key)

        sorted_client_ids = sorted(all_client_ids)
        sorted_assistant_client_ids = sorted(assistant_client_ids)

        return {
            'active_clients_now': len(sorted_client_ids),
            'active_client_ids': sorted_client_ids,
            'active_assistants_now': len(assistant_user_ids),
            'active_assistant_client_ids': sorted_assistant_client_ids,
            'active_users_now': len(active_sessions),
        }
