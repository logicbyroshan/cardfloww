"""
Notification Service
====================
Central authority for all notification operations:
- Create / broadcast / target notifications
- Query notifications for a user (with read/unread status)
- Mark notifications as read
- Send optional email alerts via threaded email

ARCHITECTURE: Service layer only — no direct model mutations in views.
"""

import logging
from datetime import timedelta
from html import escape

from django.core.cache import cache as _cache
from django.conf import settings
from django.db import transaction
from django.db.models import Q, Exists, OuterRef, Value, BooleanField
from django.utils import timezone
from django.utils.timesince import timesince

from core.models import Notification, NotificationRead, User
from core.utils.email_utils import build_unified_email_html
from .cache_version_service import CacheVersionService
from .base import ServiceResult

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for creating, querying, and managing notifications."""

    MAX_VISIBLE_HOURS = 24

    # ── creation ────────────────────────────────────────────

    @classmethod
    def create_notification(cls, *, title, message, priority='normal',
                            category='general', target='all',
                            target_user_ids=None, created_by=None,
                            send_email=False, visibility_hours=None):
        """
        Create a notification and optionally send email alerts.

        Args:
            title: Notification title (max 200 chars)
            message: Notification body text
            priority: low / normal / high / urgent
            category: general / announcement / update / maintenance / alert
            target: all / super_admin / admin_staff / client / client_staff / selected
            target_user_ids: list of user IDs when target='selected'
            created_by: User who created the notification
            send_email: Whether to also send email to targeted users
            visibility_hours: Number of hours notification should remain visible.
                Use None for no auto-expiry.

        Returns:
            ServiceResult with notification data on success
        """
        # Validate
        if not title or not title.strip():
            return ServiceResult(success=False, message='Title is required.')
        if not message or not message.strip():
            return ServiceResult(success=False, message='Message is required.')
        if target == 'selected' and not target_user_ids:
            return ServiceResult(success=False, message='Select at least one user.')

        expires_at = None
        if visibility_hours is None:
            visibility_hours = cls.MAX_VISIBLE_HOURS
        try:
            visibility_hours = int(visibility_hours)
        except (TypeError, ValueError):
            return ServiceResult(success=False, message='Visibility duration must be a number of hours.')

        # Hard cap user-facing visibility at 24 hours. This keeps new and
        # existing notifications aligned with the global retention policy.
        visibility_hours = max(1, min(visibility_hours, cls.MAX_VISIBLE_HOURS))
        expires_at = timezone.now() + timedelta(hours=visibility_hours)

        try:
            recipient_user_ids = []
            with transaction.atomic():
                notif = Notification.objects.create(
                    title=title.strip(),
                    message=message.strip(),
                    priority=priority,
                    category=category,
                    target=target,
                    created_by=created_by,
                    expires_at=expires_at,
                )

                # If selected users, add M2M
                if target == 'selected' and target_user_ids:
                    users = User.objects.filter(
                        id__in=target_user_ids, is_active=True
                    )
                    recipient_user_ids = list(users.values_list('id', flat=True))
                    notif.target_users.set(users)
                    recipient_count = len(recipient_user_ids)
                else:
                    target_qs = cls._get_target_users_queryset(target)
                    recipient_user_ids = list(target_qs.values_list('id', flat=True))
                    recipient_count = len(recipient_user_ids)

            # Optional email alert (fire-and-forget in background thread with retry support)
            if send_email:
                cls._send_email_alerts(notif)

            # Send push notifications in a decoupled background thread
            try:
                if recipient_user_ids:
                    cls._send_push_notifications_async(recipient_user_ids, title.strip(), message.strip())
            except Exception as e:
                logger.error("Failed to trigger push notifications: %s", e)

            if recipient_user_ids:
                cls._invalidate_users_notification_caches(recipient_user_ids)

            # Ensure unread counters for all targets (selected/role/all) move
            # to a fresh cache namespace immediately after creation.
            CacheVersionService.bump('notif_global', 'all')

            logger.info(
                "Notification created: '%s' → %s (%d recipients) by %s",
                title, target, recipient_count,
                created_by.username if created_by else 'system'
            )

            return ServiceResult(
                success=True,
                message=f'Notification sent to {recipient_count} user(s).',
                data={
                    'notification': cls._serialize(notif),
                    'recipient_count': recipient_count,
                }
            )

        except Exception as exc:
            logger.error("Failed to create notification: %s", exc)
            return ServiceResult(success=False, message='Failed to create notification.')

    # ── querying ────────────────────────────────────────────

    @classmethod
    def _build_user_role_filter(cls, user):
        """Construct Q filter for a given user's role visibility."""
        role = getattr(user, 'role', '') or ('super_admin' if user.is_superuser else '')
        matching_targets = {'all'}
        if user.is_superuser or role in ('super_admin', 'prime_admin'):
            matching_targets.update({'super_admin', 'prime_admin'})
        if role == 'prime_manager':
            matching_targets.update({'prime_manager', 'client'})
        elif role in ('super_manager', 'manager'):
            matching_targets.update({'super_manager', 'manager'})
        elif role == 'operator':
            matching_targets.update({'operator', 'admin_staff'})
        elif role == 'assistant':
            matching_targets.update({'assistant', 'client_staff'})
        elif role == 'photographer':
            matching_targets.add('photographer')
        elif role:
            matching_targets.add(role)

        role_filter = Q(target__in=matching_targets)
        selected_filter = Q(target='selected', target_users=user)
        return role_filter | selected_filter

    @classmethod
    def get_notifications_for_user(cls, user, limit=20, offset=0,
                                   unread_only=False, include_expired=False):
        """
        Get notifications visible to a user, annotated with read status.
        """
        now = timezone.now()
        visible_cutoff = now - timedelta(hours=cls.MAX_VISIBLE_HOURS)
        qs = Notification.objects.filter(is_active=True)
        qs = qs.filter(created_at__gte=visible_cutoff)
        if not include_expired:
            qs = qs.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        qs = qs.select_related('created_by')

        # Filter by target scope
        qs = qs.filter(cls._build_user_role_filter(user)).distinct()

        # Annotate read status
        qs = qs.annotate(
            is_read=Exists(
                NotificationRead.objects.filter(
                    notification=OuterRef('pk'),
                    user=user,
                )
            )
        )

        if unread_only:
            qs = qs.filter(is_read=False)

        qs = qs.order_by('-created_at')
        total = qs.count()
        notifications = list(qs[offset:offset + limit])

        return {
            'notifications': [cls._serialize(n, user) for n in notifications],
            'total': total,
            'unread_count': qs.filter(is_read=False).count() if not unread_only else total,
        }

    @classmethod
    def get_unread_count(cls, user):
        """Fast count of unread notifications for badge display."""
        global_version = CacheVersionService.get('notif_global', 'all')
        user_version = CacheVersionService.get('client_messages_drawer_user', f'user:{int(user.pk)}')
        cache_key = f'notif_unread:{user.pk}:gv{global_version}:uv{user_version}'
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        now = timezone.now()
        visible_cutoff = now - timedelta(hours=cls.MAX_VISIBLE_HOURS)
        qs = Notification.objects.filter(is_active=True).filter(
            Q(created_at__gte=visible_cutoff)
            & (Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        )

        qs = qs.filter(cls._build_user_role_filter(user)).distinct()

        count = qs.exclude(reads__user=user).count()
        _cache.set(cache_key, count, 120)
        return count

    # ── read tracking ───────────────────────────────────────

    @classmethod
    def _invalidate_user_notification_caches(cls, user_id):
        if not user_id:
            return
        user_id_int = int(user_id)
        global_version = CacheVersionService.get('notif_global', 'all')
        user_version = CacheVersionService.get('client_messages_drawer_user', f'user:{user_id_int}')
        _cache.delete(f'notif_unread:{user_id_int}:gv{global_version}:uv{user_version}')
        _cache.delete(f'notif_unread:{user_id_int}:v{global_version}')
        # Backward-compatible cleanup for any legacy key readers.
        _cache.delete(f'notif_unread:{user_id_int}')
        CacheVersionService.bump('client_messages_drawer_user', f'user:{user_id_int}')

    @classmethod
    def _invalidate_users_notification_caches(cls, user_ids):
        for raw_uid in (user_ids or []):
            try:
                uid = int(raw_uid)
            except (TypeError, ValueError):
                continue
            if uid > 0:
                cls._invalidate_user_notification_caches(uid)

    @classmethod
    def mark_as_read(cls, user, notification_id):
        """Mark a single notification as read for a user."""
        try:
            NotificationRead.objects.get_or_create(
                user=user,
                notification_id=notification_id,
            )
            cls._invalidate_user_notification_caches(getattr(user, 'pk', None))
            return ServiceResult(success=True)
        except Notification.DoesNotExist:
            return ServiceResult(success=False, message='Notification not found.')

    @classmethod
    def mark_all_as_read(cls, user):
        """Mark all user-visible notifications as read, including historical expired items."""
        now = timezone.now()
        visible_cutoff = now - timedelta(hours=cls.MAX_VISIBLE_HOURS)
        qs = Notification.objects.filter(is_active=True).filter(created_at__gte=visible_cutoff)
        role_filter = Q(target='all') | Q(target=user.role)
        selected_filter = Q(target='selected', target_users=user)
        qs = qs.filter(role_filter | selected_filter).distinct()

        read_ids = set(
            NotificationRead.objects.filter(user=user).values_list(
                'notification_id', flat=True
            )
        )
        unread = qs.exclude(id__in=read_ids)

        new_reads = [
            NotificationRead(user=user, notification_id=nid)
            for nid in unread.values_list('id', flat=True)
        ]
        if new_reads:
            NotificationRead.objects.bulk_create(new_reads, ignore_conflicts=True)

        cls._invalidate_user_notification_caches(getattr(user, 'pk', None))
        return ServiceResult(
            success=True,
            message=f'Marked {len(new_reads)} notification(s) as read.'
        )

    # ── admin management ────────────────────────────────────

    @classmethod
    def list_all_notifications(cls, limit=50, offset=0, search=''):
        """List all notifications (admin panel view)."""
        now = timezone.now()
        qs = Notification.objects.filter(is_active=True).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).select_related('created_by').order_by('-created_at')
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(message__icontains=search)
            )
        total = qs.count()
        notifications = list(qs[offset:offset + limit])
        # Aggregate counts across ALL notifications (not just this page)
        all_active = Notification.objects.filter(is_active=True).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )
        stats = {
            'broadcast': all_active.filter(target='all').count(),
            'targeted':  all_active.filter(target='selected').count(),
            'urgent':    all_active.filter(priority='urgent').count(),
        }
        return {
            'notifications': [cls._serialize_admin(n) for n in notifications],
            'total': total,
            'stats': stats,
        }

    @classmethod
    def delete_notification(cls, notification_id):
        """Hide a notification from all users (deactivate)."""
        try:
            notif = Notification.objects.get(id=notification_id)
            notif.is_active = False
            notif.save(update_fields=['is_active'])
            return ServiceResult(success=True, message='Notification hidden from users.')
        except Notification.DoesNotExist:
            return ServiceResult(success=False, message='Notification not found.')

    @classmethod
    def get_target_user_options(cls):
        """
        Get users grouped by role for the target user picker.
        Returns dict of role → list of {id, name, username}.
        """
        users = User.objects.filter(is_active=True).order_by('role', 'first_name')
        grouped = {}
        for u in users:
            role = u.role
            if role not in grouped:
                grouped[role] = []
            grouped[role].append({
                'id': u.id,
                'name': u.get_full_name() or u.username,
                'username': u.username,
                'role_display': u.get_role_display(),
            })
        return grouped

    # ── cleanup ─────────────────────────────────────────────

    @classmethod
    def cleanup_old_notifications(cls, days=90):
        """Delete notifications older than N days and their read records."""
        min_days = max(int(getattr(settings, 'NOTIFICATION_MIN_RETENTION_DAYS', 90) or 90), 1)
        try:
            requested_days = int(days)
        except (TypeError, ValueError):
            requested_days = min_days
        safe_days = max(requested_days, min_days)

        if safe_days != requested_days:
            logger.warning(
                'Notification cleanup days=%s below minimum retention=%s; clamped to %s.',
                requested_days,
                min_days,
                safe_days,
            )

        threshold = timezone.now() - timedelta(days=safe_days)
        count, _ = Notification.objects.filter(created_at__lt=threshold).delete()
        if count:
            logger.info("Cleaned up %d old notifications", count)
        return count

    # ── private helpers ─────────────────────────────────────

    @classmethod
    def _get_target_users_queryset(cls, target, target_user_ids=None):
        """Resolve queryset of active users matching target criteria."""
        qs = User.objects.filter(is_active=True)
        if target == 'all':
            return qs
        elif target == 'selected':
            if target_user_ids:
                return qs.filter(id__in=target_user_ids)
            return qs.none()
        elif target == 'super_admin':
            return qs.filter(Q(role='super_admin') | Q(role='prime_admin') | Q(is_superuser=True))
        elif target in ('prime_manager', 'client'):
            return qs.filter(role='prime_manager')
        elif target in ('super_manager', 'manager'):
            return qs.filter(role__in=['super_manager', 'manager'])
        elif target in ('operator', 'admin_staff'):
            return qs.filter(role='operator')
        elif target in ('assistant', 'client_staff'):
            return qs.filter(role='assistant')
        elif target == 'photographer':
            return qs.filter(role='photographer')
        else:
            return qs.filter(role=target)

    @classmethod
    def _count_target_users(cls, target):
        """Count how many active users match a target scope."""
        return cls._get_target_users_queryset(target).count()

    @classmethod
    def _serialize(cls, notif, user=None):
        """Serialize notification for API response."""
        data = {
            'id': notif.id,
            'title': notif.title,
            'message': notif.message,
            'priority': notif.priority,
            'priority_color': notif.priority_color,
            'category': notif.category,
            'category_display': notif.get_category_display(),
            'icon_class': notif.icon_class,
            'created_at': notif.created_at.isoformat(),
            'time_ago': timesince(notif.created_at, timezone.now()),
            'expires_at': notif.expires_at.isoformat() if notif.expires_at else None,
        }
        if user and hasattr(notif, 'is_read'):
            data['is_read'] = notif.is_read
        return data

    @classmethod
    def _serialize_admin(cls, notif):
        """Serialize notification for admin panel list."""
        data = cls._serialize(notif)
        data.update({
            'target': notif.target,
            'target_display': notif.get_target_display(),
            'created_by': (
                notif.created_by.get_full_name() or notif.created_by.username
            ) if notif.created_by else 'System',
            'is_active': notif.is_active,
            'read_count': notif.reads.count(),
        })
        return data

    @classmethod
    def _build_email_context(cls, notif):
        """Build context values used for plain and HTML notification emails."""
        return {
            'notification': notif,
            'category_display': notif.get_category_display(),
            'priority_display': notif.get_priority_display(),
            'target_display': notif.get_target_display(),
            'is_urgent': notif.priority == 'urgent',
            'created_at_display': timezone.localtime(notif.created_at).strftime('%d %b %Y, %I:%M %p'),
            'sender_name': (
                notif.created_by.get_full_name() or notif.created_by.username
            ) if notif.created_by else 'System',
        }

    @classmethod
    def _build_plain_email_body(cls, notif, context):
        """Build plain-text email body for a notification."""
        lines = [
            f"Adarsh Admin Notification: {notif.title}",
            "=" * 40,
            f"Category: {context['category_display']}",
            f"Priority: {context['priority_display']}",
            f"Date:     {context['created_at_display']}",
            f"From:     {context['sender_name']}",
            "",
            notif.message,
            "",
            "---",
            "This is an automated notification from Adarsh Admin.",
        ]
        if context['is_urgent']:
            lines.insert(0, "*** URGENT NOTIFICATION ***\n")
        return "\n".join(lines)

    @classmethod
    def _build_html_email_body(cls, notif, context):
        """Build HTML email body for a notification using the unified design system."""
        body_html = (
            '<div style="font-size:14px;color:#334155;line-height:1.7;margin-bottom:16px;">'
            f'{escape(notif.message).replace(chr(10), "<br>")}'
            '</div>'
            '<table style="width:100%;border-collapse:collapse;font-size:12px;color:#64748b;margin-top:16px;border-top:1px solid #e2e8f0;padding-top:12px;">'
            f'<tr><td style="padding:4px 0;font-weight:600;">Category:</td><td style="padding:4px 0;">{escape(context["category_display"])}</td></tr>'
            f'<tr><td style="padding:4px 0;font-weight:600;">Priority:</td><td style="padding:4px 0;">{escape(context["priority_display"])}</td></tr>'
            f'<tr><td style="padding:4px 0;font-weight:600;">Sent by:</td><td style="padding:4px 0;">{escape(context["sender_name"])}</td></tr>'
            f'<tr><td style="padding:4px 0;font-weight:600;">Date:</td><td style="padding:4px 0;">{escape(context["created_at_display"])}</td></tr>'
            '</table>'
        )

        if context['is_urgent']:
            body_html += (
                '<div style="margin-top:12px;border:1px solid #fecaca;border-left:4px solid #dc2626;border-radius:10px;background:#fef2f2;padding:10px 12px;font-size:12px;color:#991b1b;line-height:1.65;">'
                '<strong>Urgent:</strong> Please review this notification as soon as possible.'
                '</div>'
            )

        return build_unified_email_html(
            theme=notif.category,
            kicker='Adarsh Admin Notification',
            title=notif.title,
            subtitle='You are receiving this based on your notification preferences.',
            body_html=body_html,
        )

    @classmethod
    def _send_email_alerts(cls, notif):
        """
        Send email alerts for a notification via send_html_email_async with automatic retries.
        Each recipient gets an individual email so addresses aren't exposed.
        """
        try:
            from core.utils.threaded_email import send_html_email_async
            from core.models import EmailLog
            from django.conf import settings

            if notif.target == 'selected':
                users = notif.target_users.filter(is_active=True, email__isnull=False).exclude(email='')
            else:
                users = cls._get_target_users_queryset(notif.target).filter(email__isnull=False).exclude(email='')

            user_list = list(users.values('id', 'email', 'first_name', 'last_name', 'username'))
            if not user_list:
                return

            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '')
            priority_label = f"[{notif.get_priority_display()}] " if notif.priority != 'normal' else ''
            subject = f"{priority_label}{notif.title}"
            context = cls._build_email_context(notif)
            html_content = cls._build_html_email_body(notif, context)
            plain_content = cls._build_plain_email_body(notif, context)

            for u in user_list:
                full_name = f"{u.get('first_name') or ''} {u.get('last_name') or ''}".strip() or u.get('username')
                send_html_email_async(
                    subject=subject,
                    plain_content=plain_content,
                    html_content=html_content,
                    from_email=from_email,
                    recipient_list=[u['email']],
                    email_type=EmailLog.EMAIL_TYPE_NOTIFICATION,
                    recipient_name=full_name,
                )

            logger.info("Email alerts queued for notification #%d to %d recipients", notif.id, len(user_list))

        except Exception as exc:
            logger.error("Failed to send email alerts for notification #%d: %s", notif.id, exc)

    @classmethod
    def _send_push_notifications_async(cls, user_ids, title, message):
        """Send push notifications to mobile devices via Expo push notification service in a background thread."""
        try:
            import threading
            from mobile_api.models import MobileDeviceToken

            tokens = list(
                MobileDeviceToken.objects.filter(user_id__in=user_ids)
                .values_list('push_token', flat=True)
            )
            if not tokens:
                return

            def _send_expo_push_tokens(token_list, notif_title, notif_body):
                import requests
                url = "https://exp.host/--/api/v2/push/send"
                headers = {
                    "Content-Type": "application/json",
                    "accept-encoding": "gzip, deflate",
                    "accept": "application/json",
                }
                # Chunk into batches of 100 per Expo recommendations
                chunk_size = 100
                for i in range(0, len(token_list), chunk_size):
                    chunk = token_list[i:i + chunk_size]
                    payload = [
                        {
                            "to": tok,
                            "sound": "default",
                            "title": notif_title,
                            "body": notif_body,
                        }
                        for tok in chunk if tok and str(tok).strip()
                    ]
                    if not payload:
                        continue
                    try:
                        response = requests.post(url, json=payload, headers=headers, timeout=12)
                        logger.info("Expo push response: status=%s, delivered=%d", response.status_code, len(payload))
                    except Exception as e:
                        logger.error("Failed to send Expo push notification chunk: %s", e)

            threading.Thread(
                target=_send_expo_push_tokens,
                args=(tokens, title, message),
                daemon=True
            ).start()
            logger.info("Triggered push notification thread for user_ids=%s", user_ids)
        except Exception as exc:
            logger.error("Failed to initiate push notifications: %s", exc)
