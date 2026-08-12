"""
Statistics Dashboard Views
Real data only — no random/mock fallbacks.
Now tracks active desktop (web) and mobile (app) users.
"""
from datetime import datetime, timedelta

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Q

from core.services.permission_service import PermissionService, api_require_any_authenticated
from core.services.live_presence_service import LiveClientPresenceService
from django.contrib.auth import get_user_model
User = get_user_model()
from organisation.models import Organisation
from accounts.models import UserDeviceSession
from stats.models import StatsSnapshot, ServerLoadAlert
from core.models import BackgroundTask

import logging
logger = logging.getLogger(__name__)


def _get_user_role(user):
    return str(getattr(user, 'role', '') or '').strip().lower()


def _estimate_activity_from_logs(start_time, end_time):
    """Estimate active desktop/web vs mobile users from ActivityLog during a time period."""
    from core.models import ActivityLog

    total_active_users = ActivityLog.objects.filter(
        created_at__range=(start_time, end_time),
    ).values('user_id').distinct().count()

    mobile_users = ActivityLog.objects.filter(
        created_at__range=(start_time, end_time),
        action__in=('login', 'logout'),
        description__icontains='mobile app'
    ).values('user_id').distinct().count()

    photographer_users = ActivityLog.objects.filter(
        created_at__range=(start_time, end_time),
        user__role='photographer'
    ).values('user_id').distinct().count()

    ma = mobile_users + photographer_users
    da = max(0, total_active_users - ma)
    return da, ma


@login_required
def statistics_page(request):
    """Render the main statistics dashboard for pro users and super admins."""
    if not PermissionService.can_use_pro_user_options(request.user):
        return redirect('dashboard')

    context = {
        'active_page': 'impersonate',
        'pro_tab': 'statistics',
        'user_role': _get_user_role(request.user),
    }
    return render(request, 'index.html', context)


def _get_active_device_counts():
    """Retrieve current distinct active users by device type (web vs mobile) in the last 15 minutes."""
    now = timezone.now()
    cutoff = now - timezone.timedelta(minutes=15)

    desktop_count = UserDeviceSession.objects.filter(
        last_active__gte=cutoff,
        device_type='web'
    ).values('user_id').distinct().count()

    mobile_count = UserDeviceSession.objects.filter(
        last_active__gte=cutoff,
        device_type='mobile'
    ).values('user_id').distinct().count()

    return desktop_count, mobile_count


def _take_hourly_snapshot(user):
    """Write a real snapshot right now if the last one is older than 1 hour."""
    from tables.models import IDCard

    now = timezone.localtime(timezone.now())
    latest = StatsSnapshot.objects.order_by('-timestamp').first()
    if latest and (now - timezone.localtime(latest.timestamp)) < timedelta(hours=1):
        return  # not time yet

    desktop_users_count, mobile_users_count = _get_active_device_counts()
    live_users_count = desktop_users_count + mobile_users_count

    hour_ago = now - timedelta(hours=1)
    cards_created = IDCard.objects.filter(created_at__gte=hour_ago).count()
    processing_jobs = BackgroundTask.objects.filter(status__in=['pending', 'processing']).count()

    peak = max(desktop_users_count + mobile_users_count, live_users_count)

    StatsSnapshot.objects.create(
        timestamp=now,
        active_desktop_users=desktop_users_count,
        active_mobile_users=mobile_users_count,
        peak_active_users=peak,
        total_cards_created=cards_created,
        batch_jobs_count=processing_jobs,
    )


@api_require_any_authenticated
def api_statistics_data(request):
    """
    JSON API — real activity metrics over time.
    Supports range: 'hourly' (last 24 h), 'daily' (last 30 d),
                    'weekly' (last 12 wk), 'monthly' (last 12 mo).
    """
    from core.models import ActivityLog
    from tables.models import IDCard

    if not PermissionService.can_use_pro_user_options(request.user):
        return JsonResponse({'success': False, 'message': 'Access denied.'}, status=403)

    _take_hourly_snapshot(request.user)

    range_type = str(request.GET.get('range', 'hourly')).strip().lower()
    if range_type not in ('hourly', 'daily', 'weekly', 'monthly'):
        range_type = 'hourly'

    now = timezone.localtime(timezone.now())
    labels           = []
    desktop_activity = []
    mobile_activity  = []
    cards_created    = []
    all_user_activity = []

    snapshots_qs = StatsSnapshot.objects.order_by('timestamp')

    if range_type == 'hourly':
        start_time = now - timedelta(hours=24)
        snapshots = list(snapshots_qs.filter(timestamp__gte=start_time))

        for i in range(24):
            slot_start = start_time + timedelta(hours=i)
            slot_end   = slot_start + timedelta(hours=1)
            labels.append(slot_end.strftime('%H:00'))

            bucket = [s for s in snapshots if slot_start <= timezone.localtime(s.timestamp) < slot_end]

            if bucket:
                da = int(sum((s.active_desktop_users or (s.active_clients + s.active_assistants)) for s in bucket) / len(bucket))
                ma = int(sum((s.active_mobile_users or 0) for s in bucket) / len(bucket))
                cc = sum(s.total_cards_created for s in bucket)
                if ma == 0:
                    _, estimated_ma = _estimate_activity_from_logs(slot_start, slot_end)
                    ma = estimated_ma
            else:
                da, ma = _estimate_activity_from_logs(slot_start, slot_end)
                cc = 0

            desktop_activity.append(da)
            mobile_activity.append(ma)
            cards_created.append(cc)

            au = ActivityLog.objects.filter(
                created_at__gte=slot_start,
                created_at__lt=slot_end,
            ).values('user_id').distinct().count()
            all_user_activity.append(max(au, da + ma))

    elif range_type == 'daily':
        start_time = now - timedelta(days=30)
        snapshots = list(snapshots_qs.filter(timestamp__gte=start_time))

        for i in range(30):
            day = (start_time + timedelta(days=i + 1)).date()
            labels.append(day.strftime('%b %d'))

            day_start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
            day_end   = timezone.make_aware(datetime.combine(day, datetime.max.time()))

            bucket = [s for s in snapshots if timezone.localtime(s.timestamp).date() == day]
            if bucket:
                da = int(sum((s.active_desktop_users or (s.active_clients + s.active_assistants)) for s in bucket) / len(bucket))
                ma = int(sum((s.active_mobile_users or 0) for s in bucket) / len(bucket))
                cc = sum(s.total_cards_created for s in bucket)
                if ma == 0:
                    _, estimated_ma = _estimate_activity_from_logs(day_start, day_end)
                    ma = estimated_ma
            else:
                da, ma = _estimate_activity_from_logs(day_start, day_end)
                cc = IDCard.objects.filter(
                    created_at__range=(day_start, day_end),
                ).count()

            desktop_activity.append(da)
            mobile_activity.append(ma)
            cards_created.append(cc)

            au = ActivityLog.objects.filter(
                created_at__range=(day_start, day_end),
            ).values('user_id').distinct().count()
            all_user_activity.append(max(au, da + ma))

    elif range_type == 'weekly':
        start_time = now - timedelta(weeks=12)
        snapshots = list(snapshots_qs.filter(timestamp__gte=start_time))

        for i in range(12):
            wk_start = start_time + timedelta(weeks=i)
            wk_end   = wk_start + timedelta(weeks=1)
            iso_wk   = wk_start.isocalendar()[1]
            labels.append(f'Wk {iso_wk}')

            bucket = [s for s in snapshots if wk_start <= timezone.localtime(s.timestamp) < wk_end]
            if bucket:
                da = int(sum((s.active_desktop_users or (s.active_clients + s.active_assistants)) for s in bucket) / len(bucket))
                ma = int(sum((s.active_mobile_users or 0) for s in bucket) / len(bucket))
                cc = sum(s.total_cards_created for s in bucket)
                if ma == 0:
                    _, estimated_ma = _estimate_activity_from_logs(wk_start, wk_end)
                    ma = estimated_ma
            else:
                da, ma = _estimate_activity_from_logs(wk_start, wk_end)
                cc = IDCard.objects.filter(
                    created_at__gte=wk_start, created_at__lt=wk_end,
                ).count()

            desktop_activity.append(da)
            mobile_activity.append(ma)
            cards_created.append(cc)

            au = ActivityLog.objects.filter(
                created_at__gte=wk_start, created_at__lt=wk_end,
            ).values('user_id').distinct().count()
            all_user_activity.append(max(au, da + ma))

    else:  # monthly
        for i in range(12):
            offset = 11 - i
            target_month = now.month - offset
            target_year  = now.year
            while target_month < 1:
                target_month += 12
                target_year  -= 1

            import calendar
            _, last_day = calendar.monthrange(target_year, target_month)
            mo_start = timezone.make_aware(datetime(target_year, target_month, 1, 0, 0, 0))
            mo_end   = timezone.make_aware(datetime(target_year, target_month, last_day, 23, 59, 59))
            labels.append(mo_start.strftime('%b %Y'))

            bucket = [s for s in StatsSnapshot.objects.filter(
                timestamp__gte=mo_start, timestamp__lte=mo_end
            )]
            if bucket:
                da = int(sum((s.active_desktop_users or (s.active_clients + s.active_assistants)) for s in bucket) / len(bucket))
                ma = int(sum((s.active_mobile_users or 0) for s in bucket) / len(bucket))
                cc = sum(s.total_cards_created for s in bucket)
                if ma == 0:
                    _, estimated_ma = _estimate_activity_from_logs(mo_start, mo_end)
                    ma = estimated_ma
            else:
                da, ma = _estimate_activity_from_logs(mo_start, mo_end)
                cc = IDCard.objects.filter(
                    created_at__range=(mo_start, mo_end),
                ).count()

            desktop_activity.append(da)
            mobile_activity.append(ma)
            cards_created.append(cc)

            from core.models import ActivityLog as AL2
            au = AL2.objects.filter(
                created_at__range=(mo_start, mo_end),
            ).values('user_id').distinct().count()
            all_user_activity.append(max(au, da + ma))

    # ── Live summary metrics ────────────────────────────────────────────
    current_desktop, current_mobile = _get_active_device_counts()
    current_active_users    = current_desktop + current_mobile

    # Overwrite the last data point with actual live numbers (most-recent on right)
    if desktop_activity:
        desktop_activity[-1]   = max(desktop_activity[-1],   current_desktop)
    if mobile_activity:
        mobile_activity[-1] = max(mobile_activity[-1], current_mobile)
    if all_user_activity:
        all_user_activity[-1] = max(all_user_activity[-1],  current_active_users)

    # Today's Peak Active
    from django.utils.timezone import localdate
    today = localdate()
    todays_snapshots = StatsSnapshot.objects.filter(timestamp__date=today)
    peak_active_users = current_active_users
    for snap in todays_snapshots:
        snap_peak = max(snap.peak_active_users, snap.active_desktop_users + snap.active_mobile_users)
        if snap_peak > peak_active_users:
            peak_active_users = snap_peak

    # Busiest 2-hour window (hourly range only)
    busiest_hour_str = '—'
    if range_type == 'hourly' and len(all_user_activity) >= 2:
        max_sum = -1
        max_idx = -1
        for idx in range(len(all_user_activity) - 1):
            s = all_user_activity[idx] + all_user_activity[idx + 1]
            if s > max_sum:
                max_sum = s
                max_idx = idx
        if max_idx != -1:
            try:
                start_hour = int(labels[max_idx].split(':')[0])
                end_hour   = (start_hour + 2) % 24
                busiest_hour_str = f'{start_hour:02d}:00 - {end_hour:02d}:00'
            except Exception:
                pass

    from tables.models import IDCard as IDCard2
    total_cards_ever = IDCard2.objects.count()

    return JsonResponse({
        'success': True,
        'labels':             labels,
        'desktop_activity':   desktop_activity,
        'mobile_activity':    mobile_activity,
        'client_activity':    desktop_activity,
        'assistant_activity': mobile_activity,
        'all_user_activity':  all_user_activity,
        'cards_created':      cards_created,
        'batch_jobs_count':   cards_created,
        'summary': {
            'current_active_users':    current_active_users,
            'live_desktop_users':      current_desktop,
            'live_mobile_users':       current_mobile,
            'peak_active_users':       peak_active_users,
            'peak_working_hour':       busiest_hour_str,
            'total_cards_ever':        total_cards_ever,
        },
    })


# ── Server load alert helpers ──────────────────────────────────────────────────

LOAD_THRESHOLDS = [
    (100, ServerLoadAlert.LEVEL_DANGER,
     '🚨 CRITICAL: Server Will Crash',
     '100 or more concurrent users are active right now. The server is at serious risk of crashing. Please scale immediately.'),
    (75, ServerLoadAlert.LEVEL_CRITICAL,
     '⚠️ WARNING: Server Is Struggling',
     '75 or more concurrent users are active right now. The server is struggling. Please investigate and scale if needed.'),
    (50, ServerLoadAlert.LEVEL_WARNING,
     '🟡 NOTICE: Server Is Slow',
     '50 or more concurrent users are active right now. Response times may be degrading. Monitor the situation.'),
]

ALERT_COOLDOWN_MINUTES = 30


def _get_admin_emails():
    """Return emails of all active super_admin / pro_user accounts."""
    admins = User.objects.filter(
        is_active=True,
        role__in=('super_admin', 'pro_user'),
    ).values_list('email', flat=True)
    return [e for e in admins if e and '@' in e]


def check_and_send_load_alerts(concurrent_users: int):
    """Sends a single email per alert level per cooldown window."""
    from django.conf import settings
    from core.utils.threaded_email import send_html_email_async

    admin_emails = _get_admin_emails()
    if not admin_emails:
        logger.warning('check_and_send_load_alerts: no admin emails found, skipping.')
        return

    now = timezone.now()

    for (threshold, level, subject, intro) in LOAD_THRESHOLDS:
        if concurrent_users < threshold:
            continue

        alert, _ = ServerLoadAlert.objects.get_or_create(level=level)
        cooldown_ok = (
            alert.last_sent is None or
            (now - alert.last_sent) >= timedelta(minutes=ALERT_COOLDOWN_MINUTES)
        )
        if not cooldown_ok:
            break

        subject_full = f'[Adarsh Panel] {subject} — {concurrent_users} users online'
        panel_url = getattr(settings, 'PANEL_URL', '') or 'https://panel.adarshbhopal.in'

        plain = (
            f'{intro}\n\n'
            f'Concurrent users right now: {concurrent_users}\n'
            f'Threshold triggered: {threshold}+\n'
            f'Time: {now.strftime("%Y-%m-%d %H:%M:%S %Z")}\n\n'
            f'Please log in to the panel and check server health:\n{panel_url}/panel/statistics/\n\n'
            f'— Adarsh ID Cards Auto-Alert System'
        )

        level_color = {'warning': '#f59e0b', 'critical': '#ef4444', 'danger': '#7f1d1d'}.get(level, '#333')
        html = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px;">
          <div style="background:{level_color};color:#fff;border-radius:8px 8px 0 0;padding:20px 24px;">
            <h2 style="margin:0;font-size:20px;">{subject}</h2>
          </div>
          <div style="background:#f9fafb;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;padding:24px;">
            <p style="font-size:15px;color:#111;">{intro}</p>
            <table style="width:100%;border-collapse:collapse;margin:16px 0;">
              <tr><td style="padding:8px;color:#6b7280;font-size:13px;width:50%;">Concurrent users</td>
                  <td style="padding:8px;font-weight:700;font-size:15px;">{concurrent_users}</td></tr>
              <tr style="background:#f3f4f6;"><td style="padding:8px;color:#6b7280;font-size:13px;">Threshold</td>
                  <td style="padding:8px;font-weight:700;font-size:15px;">{threshold}+</td></tr>
              <tr><td style="padding:8px;color:#6b7280;font-size:13px;">Time (UTC)</td>
                  <td style="padding:8px;font-size:13px;">{now.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
            </table>
            <a href="{panel_url}/panel/statistics/"
               style="display:inline-block;background:#4f46e5;color:#fff;padding:10px 20px;
                      border-radius:6px;text-decoration:none;font-weight:600;font-size:14px;">
              Open Statistics Dashboard →
            </a>
            <p style="margin-top:24px;font-size:12px;color:#9ca3af;">
              This is an automated alert from the Adarsh ID Cards panel.<br>
              Alerts repeat at most once every {ALERT_COOLDOWN_MINUTES} minutes per severity level.
            </p>
          </div>
        </div>
        """

        try:
            send_html_email_async(
                subject=subject_full,
                plain_content=plain,
                html_content=html,
                from_email=None,
                recipient_list=admin_emails,
                skip_logging=True,
                email_type='alert',
            )
            alert.last_sent  = now
            alert.last_count = concurrent_users
            alert.save(update_fields=['last_sent', 'last_count'])
            logger.info('Server load alert [%s] sent to %s (%d users online)',
                        level, admin_emails, concurrent_users)
        except Exception:
            logger.exception('Failed to send server load alert [%s]', level)

        break


@api_require_any_authenticated
def api_check_server_load(request):
    """Lightweight endpoint polled by the statistics page JS."""
    if not PermissionService.can_use_pro_user_options(request.user):
        return JsonResponse({'success': False}, status=403)

    desktop, mobile = _get_active_device_counts()
    concurrent = desktop + mobile

    alert_level = None
    if concurrent >= 100:
        alert_level = 'danger'
    elif concurrent >= 75:
        alert_level = 'critical'
    elif concurrent >= 50:
        alert_level = 'warning'

    if alert_level:
        try:
            check_and_send_load_alerts(concurrent)
        except Exception:
            logger.exception('api_check_server_load: alert dispatch failed')

    return JsonResponse({
        'success':      True,
        'concurrent':   concurrent,
        'alert_level':  alert_level,
    })
