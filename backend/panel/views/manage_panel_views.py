"""
Manage Panel views  (panel app)
================================
Main manage-panel page, email-logs API, and notifications page.
Moved from core/views/admin_page_views.py.
"""

import logging
import json
from datetime import timedelta

from django.conf import settings as django_settings
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.models import User, Notification, EmailLog
from tables.models import IDCard
from organisation.models import Organisation
from core.services.activity_service import ActivityService
from core.services.permission_service import (
    PermissionService,
    require_any_admin,
    api_require_permission,
)

logger = logging.getLogger(__name__)

DEFAULT_EMAIL_TEMPLATE = (
    'Hello {name},\n\n'
    'This is a message from Adarsh Admin.\n\n'
    'Regards,\n'
    'Adarsh Admin Team'
)


def _normalize_email_type(value):
    """Return a valid EmailLog type or fallback to system."""
    candidate = str(value or '').strip()
    valid_types = {choice[0] for choice in EmailLog.TYPE_CHOICES}
    if candidate in valid_types:
        return candidate
    return EmailLog.EMAIL_TYPE_SYSTEM


def _send_email_now(subject, body_text, body_html, recipient_email):
    """Send email synchronously with bounded timeout and explicit HTML fallback."""
    connection = get_connection(timeout=30)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=body_text,
        from_email=getattr(django_settings, 'DEFAULT_FROM_EMAIL', ''),
        to=[recipient_email],
        connection=connection,
    )
    if body_html:
        msg.attach_alternative(body_html, 'text/html')
    msg.send(fail_silently=False)


def _can_access_manage_panel(user) -> bool:
    return (
        PermissionService.is_super_admin(user)
        or PermissionService.has(user, 'perm_manage_panel_backup')
        or PermissionService.has(user, 'perm_manage_panel_email')
    )


@require_any_admin
def manage_panel(request):
    """Manage Panel view supporting both HTML render and tab inspection."""
    if not _can_access_manage_panel(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access Denied")

    is_super = PermissionService.is_super_admin(request.user)
    can_backup = is_super or PermissionService.has(request.user, 'perm_manage_panel_backup')
    can_email = is_super or PermissionService.has(request.user, 'perm_manage_panel_email')

    content_parts = []
    if can_backup:
        content_parts.append('Backups <div data-tab="backups"></div>')
    if can_email:
        content_parts.append('Email Management <div data-tab="email-logs"></div>')
    if is_super:
        content_parts.append('<div data-tab="notifications"></div><div data-tab="download-templates"></div>')

    html = f"""<!DOCTYPE html>
<html>
<head><title>Manage Panel</title></head>
<body>
    <h1>Manage Panel</h1>
    {''.join(content_parts)}
</body>
</html>"""
    return HttpResponse(html)


# ── Email Logs API ────────────────────────────────────────────────────────

@api_require_permission('perm_manage_panel_email')
@require_http_methods(['GET'])
def api_email_logs(request):
    """Return paginated email log entries for the Email Management tab."""
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')
    email_type_filter = request.GET.get('email_type', '')
    sort_order = str(request.GET.get('sort', 'latest') or 'latest').strip().lower()
    if sort_order not in {'latest', 'oldest'}:
        sort_order = 'latest'

    # B1: guard against non-integer query params (would cause HTTP 500)
    try:
        page = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = int(request.GET.get('per_page', 50))
    except (ValueError, TypeError):
        per_page = 50
    # B2: clamp per_page to prevent memory-exhaustion DoS
    per_page = min(max(1, per_page), 200)

    # B3: explicit ordering for stable pagination
    if sort_order == 'oldest':
        qs = EmailLog.objects.order_by('created_at', 'id')
    else:
        qs = EmailLog.objects.order_by('-created_at', '-id')
    if search_query:
        qs = qs.filter(
            Q(recipient_name__icontains=search_query)
            | Q(recipient_email__icontains=search_query)
            | Q(subject__icontains=search_query)
            | Q(body_text__icontains=search_query)
            | Q(error_message__icontains=search_query)
        )
    if status_filter:
        qs = qs.filter(status=status_filter)
    if email_type_filter:
        qs = qs.filter(email_type=email_type_filter)

    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page)

    logs = [
        {
            'id': log.id,
            'recipient_name': log.recipient_name,
            'recipient_email': log.recipient_email,
            'subject': log.subject,
            'body_text': log.body_text,
            'body_html': log.body_html,
            'email_type': log.email_type,
            'email_type_display': log.get_email_type_display(),
            'status': log.status,
            'status_display': log.get_status_display(),
            'retry_count': log.retry_count,
            'max_retries': log.max_retries,
            'last_attempt_at': timezone.localtime(log.last_attempt_at).strftime('%d-%m-%Y %H:%M') if log.last_attempt_at else None,
            'next_retry_at': timezone.localtime(log.next_retry_at).strftime('%d-%m-%Y %H:%M') if log.next_retry_at else None,
            'is_retrying': log.status == EmailLog.STATUS_RETRY,
            'error_message': log.error_message,
            'created_at': timezone.localtime(log.created_at).strftime('%d-%m-%Y %H:%M'),
            'sent_at': timezone.localtime(log.sent_at).strftime('%d-%m-%Y %H:%M') if log.sent_at else None,
        }
        for log in page_obj
    ]

    # P1: single aggregated query instead of separate COUNT queries
    _sc_qs = EmailLog.objects.values('status').annotate(n=Count('id'))
    _sc_map = {row['status']: row['n'] for row in _sc_qs}

    return JsonResponse({
        'success': True,
        'logs': logs,
        'total': paginator.count,
        'page': page,
        'total_pages': paginator.num_pages,
        'sort': sort_order,
        'status_counts': {
            'on_hold': _sc_map.get(EmailLog.STATUS_ON_HOLD, 0),
            'pending': _sc_map.get(EmailLog.STATUS_PENDING, 0),
            'sending': _sc_map.get(EmailLog.STATUS_SENDING, 0),
            'retry':   _sc_map.get(EmailLog.STATUS_RETRY, 0),
            'sent':    _sc_map.get(EmailLog.STATUS_SENT, 0),
            'failed':  _sc_map.get(EmailLog.STATUS_FAILED, 0),
        },
    })


# ── Email Resend API ──────────────────────────────────────────────────────

@api_require_permission('perm_manage_panel_email')
@require_http_methods(['POST'])
def api_email_resend(request, log_id):
    """Resend a welcome/activation email for on_hold or failed email log entries.
    Generates a new temporary password for the user and resends the welcome email."""
    import secrets
    import string
    from accounts.services import OTPService
    from core.utils.email_utils import send_welcome_email

    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body)
        except Exception:
            payload = {}

    try:
        log = EmailLog.objects.get(id=log_id)
    except EmailLog.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Log entry not found.'}, status=404)

    is_custom_send = any(k in payload for k in ['subject', 'body_text', 'body_html', 'recipient_email', 'recipient_name'])
    if is_custom_send:
        recipient_email = (payload.get('recipient_email') or log.recipient_email or '').strip()
        recipient_name = (payload.get('recipient_name') or log.recipient_name or '').strip()
        subject = (payload.get('subject') or log.subject or '').strip()
        body_text = (payload.get('body_text') or log.body_text or '').strip()
        body_html = (payload.get('body_html') or log.body_html or '').strip()
        email_type = _normalize_email_type(payload.get('email_type') or log.email_type)

        if not recipient_email or not subject or not body_text:
            return JsonResponse({'success': False, 'message': 'Recipient email, subject, and message are required.'}, status=400)

        try:
            _send_email_now(subject, body_text, body_html, recipient_email)
            log.recipient_name = recipient_name or recipient_email
            log.recipient_email = recipient_email
            log.subject = subject
            log.body_text = body_text
            log.body_html = body_html
            log.email_type = email_type
            log.status = EmailLog.STATUS_SENT
            log.error_message = ''
            log.sent_at = timezone.now()
            log.save(update_fields=['recipient_name', 'recipient_email', 'subject', 'body_text', 'body_html', 'email_type', 'status', 'error_message', 'sent_at'])
            ActivityService.log(
                'email_resend',
                f'Email resent to {recipient_email}',
                request=request,
                target_model='EmailLog',
                target_id=log.id,
                target_name=recipient_email,
            )
            return JsonResponse({
                'success': True,
                'message': 'Email resent successfully.',
                'new_status': log.status,
                'new_status_display': log.get_status_display(),
            })
        except Exception as e:
            logger.exception('api_email_resend custom send failed for log %s', log_id)
            log.status = EmailLog.STATUS_FAILED
            log.error_message = str(e)[:2000]
            log.save(update_fields=['status', 'error_message'])
            return JsonResponse({'success': False, 'message': 'Failed to send email.'}, status=500)

    is_otp_log = log.email_type == EmailLog.EMAIL_TYPE_OTP_RESET
    if (not is_otp_log) and log.status not in [EmailLog.STATUS_ON_HOLD, EmailLog.STATUS_FAILED, EmailLog.STATUS_RETRY]:
        return JsonResponse({
            'success': False,
            'message': f'Cannot resend an email with status "{log.get_status_display()}".',
        }, status=400)

    if is_otp_log:
        return JsonResponse({
            'success': False,
            'message': 'OTP verification codes expire after 10 minutes and cannot be resent. Please trigger a fresh request.',
        }, status=400)

    user = User.objects.filter(email=log.recipient_email).first()
    if not user:
        return JsonResponse({
            'success': False,
            'message': f'No user found with email "{log.recipient_email}".',
        }, status=404)

    alphabet = string.ascii_letters + string.digits
    new_password = ''.join(secrets.choice(alphabet) for _ in range(12))

    try:
        success, message = send_welcome_email(
            user=user,
            password=new_password,
            role=user.role,
            request=request,
            email_variant='temp_password',
        )
    except Exception as e:
        logger.exception('api_email_resend error for log %s', log_id)
        log.status = EmailLog.STATUS_FAILED
        log.error_message = 'Failed to send welcome email.'
        log.save(update_fields=['status', 'error_message'])
        return JsonResponse({'success': False, 'message': 'Failed to send email. Password was not changed.'}, status=500)

    if success:
        try:
            with transaction.atomic():
                user.set_password(new_password)
                user.save(update_fields=['password'])
                log.status = EmailLog.STATUS_SENT
                log.sent_at = timezone.now()
                log.error_message = ''
                log.save(update_fields=['status', 'sent_at', 'error_message'])
                ActivityService.log(
                    'email_resend',
                    f'Welcome email resent to {log.recipient_email}',
                    request=request,
                    target_model='EmailLog',
                    target_id=log.id,
                    target_name=log.recipient_email,
                )
        except Exception:
            logger.exception('api_email_resend post-send update failed for log %s', log_id)
            log.status = EmailLog.STATUS_FAILED
            log.error_message = 'Email was sent, but account update failed. Please resend to generate a new password.'
            log.save(update_fields=['status', 'error_message'])
            return JsonResponse({
                'success': False,
                'message': 'Email was sent, but account update could not be completed. Please resend.',
                'new_status': log.status,
                'new_status_display': log.get_status_display(),
            }, status=500)
    else:
        log.status = EmailLog.STATUS_FAILED
        log.error_message = message
        log.save(update_fields=['status', 'error_message'])

    return JsonResponse({
        'success': success,
        'message': message if success else f'Failed: {message}',
        'new_status': log.status,
        'new_status_display': log.get_status_display(),
    })


@api_require_permission('perm_manage_panel_email')
@require_http_methods(['POST'])
def api_email_send_new(request):
    """Create and send a new email from Email Management compose modal."""
    try:
        payload = json.loads(request.body or '{}')
    except Exception:
        payload = {}

    recipient_email = (payload.get('recipient_email') or '').strip()
    recipient_name = (payload.get('recipient_name') or recipient_email).strip()
    subject = (payload.get('subject') or '').strip()
    body_text = (payload.get('body_text') or '').strip()
    body_html = (payload.get('body_html') or '').strip()
    email_type = _normalize_email_type(payload.get('email_type'))

    if not recipient_email or not subject or not body_text:
        return JsonResponse({'success': False, 'message': 'Recipient email, subject, and message are required.'}, status=400)

    log = EmailLog.objects.create(
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        email_type=email_type,
        status=EmailLog.STATUS_PENDING,
        max_retries=3,
    )

    try:
        _send_email_now(subject, body_text, body_html, recipient_email)
        log.status = EmailLog.STATUS_SENT
        log.sent_at = timezone.now()
        log.error_message = ''
        log.save(update_fields=['status', 'sent_at', 'error_message'])
        ActivityService.log(
            'email_send',
            f'New email sent to {recipient_email}',
            request=request,
            target_model='EmailLog',
            target_id=log.id,
            target_name=recipient_email,
        )
        return JsonResponse({'success': True, 'message': 'Email sent successfully.', 'log_id': log.id})
    except Exception as e:
        logger.exception('api_email_send_new immediate attempt failed for recipient=%s', recipient_email)
        from core.services.email_delivery_service import EmailDeliveryService
        is_transient = EmailDeliveryService._is_transient_error(e)
        if is_transient:
            log.status = EmailLog.STATUS_RETRY
            log.retry_count = 1
            log.next_retry_at = timezone.now() + timedelta(seconds=35)
            log.error_message = f"Immediate send error (transient): {str(e)[:1000]}"
            log.save(update_fields=['status', 'retry_count', 'next_retry_at', 'error_message'])
            return JsonResponse({'success': True, 'message': 'Email queued for retry delivery.', 'log_id': log.id})
        else:
            log.status = EmailLog.STATUS_FAILED
            log.error_message = str(e)[:2000]
            log.save(update_fields=['status', 'error_message'])
            try:
                ActivityService.log(
                    'email_send',
                    '[FAILED] Email to ' + recipient_email + ' — ' + str(e)[:100],
                    request=request,
                    target_model='EmailLog',
                    target_id=log.id,
                    target_name=recipient_email,
                )
            except Exception:
                pass
            return JsonResponse({'success': False, 'message': 'Failed to send email.'}, status=500)


@api_require_permission('perm_manage_panel_email')
@require_http_methods(['POST'])
def api_email_retry_single(request, log_id):
    """Manually trigger immediate retry of a specific email log."""
    from core.services.email_delivery_service import EmailDeliveryService

    success = EmailDeliveryService.retry_failed_email(log_id)
    if success:
        ActivityService.log(
            'email_retry',
            f'Retrying email delivery for log #{log_id}',
            request=request,
            target_model='EmailLog',
            target_id=log_id,
        )
        return JsonResponse({'success': True, 'message': f'Email #{log_id} queued for immediate retry.'})
    return JsonResponse({'success': False, 'message': 'Email log not found.'}, status=404)


@api_require_permission('perm_manage_panel_email')
@require_http_methods(['POST'])
def api_email_retry_all_failed(request):
    """Reschedule all failed emails for immediate delivery."""
    from core.services.email_delivery_service import EmailDeliveryService

    count = EmailDeliveryService.retry_all_failed()
    ActivityService.log(
        'email_retry_all',
        f'Rescheduled {count} failed email(s) for delivery',
        request=request,
    )
    return JsonResponse({'success': True, 'message': f'{count} failed email(s) queued for retry.', 'count': count})


@api_require_permission('perm_manage_panel_email')
@require_http_methods(['GET'])
def api_email_compose_defaults(request):
    """Provide default prefilled template for Add New Email compose modal."""
    recipient_name = (request.GET.get('name') or 'User').strip() or 'User'
    body_text = DEFAULT_EMAIL_TEMPLATE.replace('{name}', recipient_name)
    return JsonResponse({
        'success': True,
        'default_subject': 'Message from Adarsh Admin',
        'default_body_text': body_text,
    })
