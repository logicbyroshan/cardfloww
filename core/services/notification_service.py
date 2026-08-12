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
                    recipient_count = cls._count_target_users(target)

            # Optional email alert (fire-and-forget in background thread)
            if send_email:
                cls._send_email_alerts(notif)

            # Send push notifications in a decoupled background thread
            try:
                push_user_ids = []
                if target == 'selected' and target_user_ids:
                    push_user_ids = list(recipient_user_ids)
                elif target == 'all':
                    push_user_ids = list(User.objects.filter(is_active=True).values_list('id', flat=True))
                else:
                    role = 'operator' if target == 'admin_staff' else ('assistant' if target == 'client_staff' else target)
                    push_user_ids = list(User.objects.filter(is_active=True, role=role).values_list('id', flat=True))
                
                if push_user_ids:
                    cls._send_push_notifications_async(push_user_ids, title.strip(), message.strip())
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
    def get_notifications_for_user(cls, user, limit=20, offset=0,
                                   unread_only=False, include_expired=False):
        """
        Get notifications visible to a user, annotated with read status.

        Args:
            user: Request user.
            limit: Max rows to return.
            offset: Pagination offset.
            unread_only: If True, return only unread items.
            include_expired: If True, include expired notifications in results.

        Returns list of dicts with 'is_read' flag and 'time_ago' string.
        """
        now = timezone.now()
        visible_cutoff = now - timedelta(hours=cls.MAX_VISIBLE_HOURS)
        qs = Notification.objects.filter(is_active=True)
        qs = qs.filter(created_at__gte=visible_cutoff)
        if not include_expired:
            qs = qs.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        qs = qs.select_related('created_by')

        # Filter by target scope
        target_role = 'admin_staff' if user.role == 'operator' else user.role
        role_filter = Q(target='all') | Q(target=target_role)
        if user.role in ('super_admin',):
            # Super admin sees everything
            role_filter = Q(target='all') | Q(target='super_admin')
        selected_filter = Q(target='selected', target_users=user)
        qs = qs.filter(role_filter | selected_filter).distinct()

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
        """Fast count of unread notifications for badge display.
        
        Cached per user with version keys (global + user scopes).
        Invalidated immediately on notification create/read operations.
        """
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

        target_role = 'admin_staff' if user.role == 'operator' else user.role
        role_filter = Q(target='all') | Q(target=target_role)
        selected_filter = Q(target='selected', target_users=user)
        qs = qs.filter(role_filter | selected_filter).distinct()

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
    def _count_target_users(cls, target):
        """Count how many active users match a target scope."""
        if target == 'all':
            return User.objects.filter(is_active=True).count()
        role = 'operator' if target == 'admin_staff' else ('assistant' if target == 'client_staff' else target)
        return User.objects.filter(is_active=True, role=role).count()

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
        """Generate plain-text fallback body for notification emails."""
        return (
            f"Adarsh Admin Notification\n"
            f"Category: {context['category_display']}\n"
            f"Priority: {context['priority_display']}\n"
            f"Target: {context['target_display']}\n"
            f"Sent by: {context['sender_name']}\n"
            f"Sent at: {context['created_at_display']}\n\n"
            f"{notif.title}\n"
            f"{'=' * len(notif.title)}\n"
            f"{notif.message}\n\n"
            "This is an automated notification from Adarsh Admin."
        )

    @classmethod
    def _build_html_email_body(cls, notif, context):
        """Generate unified HTML body for notification emails."""
        safe_message = escape(notif.message or '').replace('\n', '<br>')
        body_html = (
            '<p style="margin:0 0 12px;">A new system notification is available.</p>'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="border:1px solid #dbe4f2;border-radius:12px;background:#f8fbff;">'
            '<tr><td style="padding:12px 14px;">'
            f'<div style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.06em;">Category</div>'
            f'<div style="font-size:14px;font-weight:700;color:#0f172a;">{escape(context["category_display"])}</div>'
            '<div style="height:8px;"></div>'
            f'<div style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.06em;">Priority</div>'
            f'<div style="font-size:14px;font-weight:700;color:#0f172a;">{escape(context["priority_display"])}</div>'
            '<div style="height:8px;"></div>'
            f'<div style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.06em;">Target</div>'
            f'<div style="font-size:14px;font-weight:700;color:#0f172a;">{escape(context["target_display"])}</div>'
            '<div style="height:8px;"></div>'
            f'<div style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.06em;">Sent by</div>'
            f'<div style="font-size:14px;font-weight:700;color:#0f172a;">{escape(context["sender_name"])}</div>'
            '<div style="height:8px;"></div>'
            f'<div style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.06em;">Sent at</div>'
            f'<div style="font-size:14px;font-weight:700;color:#0f172a;">{escape(context["created_at_display"])}</div>'
            '</td></tr></table>'
            '<div style="margin-top:12px;border:1px solid #cbd5e1;border-radius:10px;background:#ffffff;padding:12px 14px;">'
            '<div style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;">Message</div>'
            f'<div style="font-size:13px;line-height:1.7;color:#334155;">{safe_message}</div>'
            '</div>'
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
        Send email alerts for a notification in background thread.
        Each recipient gets an individual email so addresses aren't exposed.
        """
        try:
            from core.utils.threaded_email import send_html_email_async
            from django.conf import settings

            # Skip if email is not configured
            if not getattr(settings, 'EMAIL_HOST_USER', ''):
                logger.debug("Skipping notification email — EMAIL_HOST_USER not set")
                return

            # Determine recipients
            if notif.target == 'selected':
                recipients = list(
                    notif.target_users.filter(
                        is_active=True, email__isnull=False
                    ).exclude(email='').values_list('email', flat=True)
                )
            elif notif.target == 'all':
                recipients = list(
                    User.objects.filter(
                        is_active=True, email__isnull=False
                    ).exclude(email='').values_list('email', flat=True)
                )
            else:
                role = 'operator' if notif.target == 'admin_staff' else ('assistant' if notif.target == 'client_staff' else notif.target)
                recipients = list(
                    User.objects.filter(
                        is_active=True, role=role, email__isnull=False
                    ).exclude(email='').values_list('email', flat=True)
                )

            if not recipients:
                return

            from_email = settings.DEFAULT_FROM_EMAIL
            priority_label = f"[{notif.get_priority_display()}] " if notif.priority != 'normal' else ''
            subject = f"{priority_label}{notif.title}"
            context = cls._build_email_context(notif)
            html_content = cls._build_html_email_body(notif, context)
            plain_content = cls._build_plain_email_body(notif, context)

            # Send individually so recipients don't see each other's addresses
            for email_addr in recipients:
                send_html_email_async(
                    subject=subject,
                    plain_content=plain_content,
                    html_content=html_content,
                    from_email=from_email,
                    recipient_list=[email_addr],
                    email_type='system',
                )

            logger.info("Email alerts queued for notification #%d to %d recipients",
                        notif.id, len(recipients))

        except Exception as exc:
            logger.error("Failed to send email alerts for notification #%d: %s",
                         notif.id, exc)

    @classmethod
    def _send_push_notifications_async(cls, user_ids, title, message):
        """Send push notifications to mobile devices via Expo push notification service in a background thread."""
        try:
            import threading
            from mobile_api.models import MobileDeviceToken
            
            # Fetch all tokens for these user IDs
            tokens = list(MobileDeviceToken.objects.filter(user_id__in=user_ids).values_list('push_token', flat=True))
            if not tokens:
                return
                
            def _send_expo_push_tokens(tokens, title, message):
                import requests
                url = "https://exp.host/--/api/v2/push/send"
                headers = {
                    "Content-Type": "application/json",
                    "accept-encoding": "gzip, deflate",
                    "accept": "application/json",
                }
                # Expo recommends chunking to 100 messages at a time
                chunk_size = 100
                for i in range(0, len(tokens), chunk_size):
                    chunk = tokens[i:i + chunk_size]
                    payload = []
                    for token in chunk:
                        payload.append({
                            "to": token,
                            "sound": "default",
                            "title": title,
                            "body": message,
                        })
                    try:
                        response = requests.post(url, json=payload, headers=headers, timeout=10)
                        logger.info("Expo push response: status=%s, payload_len=%d", response.status_code, len(chunk))
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
