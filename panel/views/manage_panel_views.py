"""
Manage Panel views  (panel app)
================================
Main manage-panel page, email-logs API, and notifications page.
Moved from core/views/admin_page_views.py.
"""

import logging
import json

from django.conf import settings as django_settings
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
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


# ── Notifications page (all authenticated users) ─────────────────────────

@login_required
def notifications_page(request):
    """Full notifications page for all authenticated users."""
    return render(request, 'index.html', {'active_page': 'notifications'})


# ── Manage Panel ─────────────────────────────────────────────────────────

@require_any_admin
def manage_panel(request):
    """Manage Panel page — notifications, backups, logs, monitoring."""
    if not _can_access_manage_panel(request.user):
        return redirect('/panel/')

    import sys
    import django

    context = {
        'active_page': 'manage_panel',
        'django_version': django.get_version(),
        'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        'environment': 'Development' if django_settings.DEBUG else 'Production',
        'total_clients': Organisation.objects.count(),
        'total_cards': IDCard.objects.count(),
        'active_tasks': 0,
        'total_notifications': Notification.objects.filter(is_active=True).count(),
        'email_backend': getattr(django_settings, 'EMAIL_BACKEND', 'SMTP').split('.')[-1].replace('Backend', ''),
        'email_from': getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'Not configured'),
        'debug_mode': django_settings.DEBUG,
        'activity_log_clear_enabled': bool(getattr(django_settings, 'ACTIVITY_LOG_MANUAL_CLEAR_ENABLED', False)),
        'activity_log_clear_confirm_phrase': str(
            getattr(django_settings, 'ACTIVITY_LOG_CLEAR_CONFIRM_PHRASE', 'DELETE ALL LOGS')
        ),
    }

    user_counts = User.objects.filter(is_active=True).aggregate(
        total=Count('id'),
        admin_staff=Count('id', filter=Q(role__in=('operator'))),
        guest_users=Count('id', filter=Q(role='guest_prime_manager')),
        organisations=Count('id', filter=Q(role__in=('prime_manager', 'manager', 'client'))),
        assistants=Count('id', filter=Q(role__in=('assistant'))),
    )
    context['can_manage_panel_backup'] = PermissionService.has(request.user, 'perm_manage_panel_backup')
    context['can_manage_panel_email'] = PermissionService.has(request.user, 'perm_manage_panel_email')
    context['total_users'] = user_counts['total']
    context['total_admin_staff'] = user_counts['operator']
    context['total_guest_users'] = user_counts['guest_users']
    context['total_organisations'] = user_counts['organisations']
    context['total_assistants'] = user_counts['assistants']
    context['total_client_staff'] = user_counts['assistants']  # compat alias
    return render(request, 'index.html', context)


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
            'error_message': log.error_message,
            'created_at': timezone.localtime(log.created_at).strftime('%d-%m-%Y %H:%M'),
            'sent_at': timezone.localtime(log.sent_at).strftime('%d-%m-%Y %H:%M') if log.sent_at else None,
        }
        for log in page_obj
    ]

    # P1: single aggregated query instead of 4 separate COUNT queries
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
    if (not is_otp_log) and log.status not in [EmailLog.STATUS_ON_HOLD, EmailLog.STATUS_FAILED]:
        return JsonResponse({'success': False, 'message': 'Only on_hold or failed emails can be resent for this type.'})

    if is_otp_log:
        result = OTPService.send_otp(log.recipient_email)
        if result.get('success'):
            log.status = EmailLog.STATUS_PENDING
            log.error_message = ''
            log.sent_at = None
            log.save(update_fields=['status', 'error_message', 'sent_at'])
            ActivityService.log(
                'email_resend',
                f'OTP resend requested for {log.recipient_email}',
                request=request,
                target_model='EmailLog',
                target_id=log.id,
                target_name=log.recipient_email,
            )
            return JsonResponse({
                'success': True,
                'message': 'OTP resend request queued successfully.',
                'new_status': log.status,
                'new_status_display': log.get_status_display(),
            })

        log.status = EmailLog.STATUS_FAILED
        log.error_message = result.get('message', 'Failed to resend OTP email.')
        log.save(update_fields=['status', 'error_message'])
        return JsonResponse({
            'success': False,
            'message': result.get('message', 'Failed to resend OTP email.'),
            'new_status': log.status,
            'new_status_display': log.get_status_display(),
        }, status=500)

    try:
        user = User.objects.get(email=log.recipient_email, is_active=True)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'No active user found with that email address.'})

    # S3 fix: generate a new temporary password but do NOT save it yet.
    # Saving the password before confirming email delivery would lock the user
    # out if SMTP fails — they'd have a new unknown password with no way to log in.
    chars = string.ascii_letters + string.digits
    new_password = ''.join(secrets.choice(chars) for _ in range(10))

    try:
        success, message = send_welcome_email(
            name=log.recipient_name or user.get_full_name() or user.username,
            email=log.recipient_email,
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
        # Password intentionally NOT changed — email never reached the user
        return JsonResponse({'success': False, 'message': 'Failed to send email. Password was not changed.'}, status=500)

    if success:
        # Only now save the new password — email delivery confirmed
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
        logger.exception('api_email_send_new failed for recipient=%s', recipient_email)
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

