"""
Threaded Email Utility

Sends emails in a background thread so the HTTP response is not blocked
by SMTP round-trips.  Falls back to synchronous sending if the thread
fails to start.

Usage:
    from core.utils.threaded_email import send_mail_async, send_html_email_async

    # Simple text email (fire-and-forget)
    send_mail_async(subject, message, from_email, recipient_list)

    # HTML email with plain-text fallback
    send_html_email_async(subject, plain, html, from_email, recipient_list)

Thread safety: each call spawns a short-lived non-daemon thread so that
email delivery is guaranteed even if the calling thread finishes early.
Django's SMTP backend is thread-safe and the GIL makes the spawn overhead
negligible for the low email volume this app produces.
"""

import logging
import threading
import time
from django.core.mail import send_mail, EmailMultiAlternatives
from django.utils import timezone

logger = logging.getLogger(__name__)

_TRANSIENT_DB_LOCK_ERRORS = (
    'database is locked',
    'database table is locked',
)


def _is_transient_db_lock_error(exc):
    message = str(exc or '').lower()
    return any(token in message for token in _TRANSIENT_DB_LOCK_ERRORS)


def _run_callback_with_retry(callback, callback_name, *args, max_attempts=3, base_delay=0.05):
    if not callback:
        return

    for attempt in range(1, max_attempts + 1):
        try:
            callback(*args)
            return
        except Exception as cb_err:
            if _is_transient_db_lock_error(cb_err) and attempt < max_attempts:
                sleep_for = base_delay * attempt
                logger.warning(
                    "%s failed due to transient DB lock; retrying (%d/%d): %s",
                    callback_name,
                    attempt,
                    max_attempts,
                    cb_err,
                )
                time.sleep(sleep_for)
                continue
            logger.error("%s error: %s", callback_name, cb_err)
            return


def _create_logs(recipient_list, subject, body_text, body_html, email_type, recipient_name):
    try:
        from core.models import EmailLog
    except Exception:
        return []

    logs = []
    for recipient in recipient_list or []:
        try:
            logs.append(
                EmailLog.objects.create(
                    recipient_name=recipient_name or recipient,
                    recipient_email=recipient,
                    subject=subject or '',
                    body_text=body_text or '',
                    body_html=body_html or '',
                    email_type=email_type or EmailLog.EMAIL_TYPE_SYSTEM,
                    status=EmailLog.STATUS_PENDING,
                )
            )
        except Exception:
            continue
    return logs


def _mark_logs(logs, success, error_message=''):
    if not logs:
        return
    try:
        from core.models import EmailLog
    except Exception:
        return

    status = EmailLog.STATUS_SENT if success else EmailLog.STATUS_FAILED
    sent_at = timezone.now() if success else None
    for log in logs:
        try:
            log.status = status
            log.error_message = '' if success else (error_message or 'Email send failed')
            log.sent_at = sent_at
            log.save(update_fields=['status', 'error_message', 'sent_at'])
        except Exception:
            continue


def send_mail_async(subject, message, from_email, recipient_list,
                    fail_silently=False, **kwargs):
    """
    Drop-in replacement for ``django.core.mail.send_mail`` that runs
    in a daemon thread.  Keyword arguments are forwarded to ``send_mail``.
    """
    email_type = kwargs.pop('email_type', 'system')
    recipient_name = kwargs.pop('recipient_name', '')
    skip_logging = kwargs.pop('skip_logging', False)
    logs = [] if skip_logging else _create_logs(
        recipient_list=recipient_list,
        subject=subject,
        body_text=message,
        body_html='',
        email_type=email_type,
        recipient_name=recipient_name,
    )

    def _send():
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
                fail_silently=fail_silently,
                **kwargs,
            )
            logger.info("Threaded email sent to %s", recipient_list)
            _mark_logs(logs, True)
        except Exception as exc:
            logger.error("Threaded email to %s failed: %s", recipient_list, exc)
            _mark_logs(logs, False, str(exc))

    t = threading.Thread(target=_send, daemon=False, name='email-send')
    t.start()


def send_html_email_async(subject, plain_content, html_content,
                          from_email, recipient_list, **kwargs):
    """
    Send an HTML email with plain-text fallback in a background thread.
    """
    email_type = kwargs.pop('email_type', 'system')
    recipient_name = kwargs.pop('recipient_name', '')
    skip_logging = kwargs.pop('skip_logging', False)
    logs = [] if skip_logging else _create_logs(
        recipient_list=recipient_list,
        subject=subject,
        body_text=plain_content,
        body_html=html_content,
        email_type=email_type,
        recipient_name=recipient_name,
    )

    def _send():
        try:
            msg = EmailMultiAlternatives(
                subject, plain_content, from_email, recipient_list
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            logger.info("Threaded HTML email sent to %s", recipient_list)
            _mark_logs(logs, True)
        except Exception as exc:
            logger.error("Threaded HTML email to %s failed: %s",
                         recipient_list, exc)
            _mark_logs(logs, False, str(exc))

    t = threading.Thread(target=_send, daemon=False, name='html-email-send')
    t.start()


def send_html_email_with_callback(subject, plain_content, html_content,
                                   from_email, recipient_list,
                                   on_success=None, on_failure=None, **kwargs):
    """
    Send an HTML email in a background thread with success/failure callbacks.

    Used for welcome emails where we need to track delivery status in the DB
    without blocking the HTTP response.

    Args:
        on_success: callable()  — called after successful send
        on_failure: callable(error_message: str) — called on SMTP failure
    """
    email_type = kwargs.pop('email_type', 'system')
    recipient_name = kwargs.pop('recipient_name', '')
    skip_logging = kwargs.pop('skip_logging', False)
    logs = [] if skip_logging else _create_logs(
        recipient_list=recipient_list,
        subject=subject,
        body_text=plain_content,
        body_html=html_content,
        email_type=email_type,
        recipient_name=recipient_name,
    )

    def _send():
        try:
            msg = EmailMultiAlternatives(
                subject, plain_content, from_email, recipient_list
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            logger.info("Threaded welcome email sent to %s", recipient_list)
            _mark_logs(logs, True)
            _run_callback_with_retry(
                on_success,
                'Welcome email on_success callback',
            )
        except Exception as exc:
            logger.error("Threaded welcome email to %s failed: %s",
                         recipient_list, exc)
            _mark_logs(logs, False, str(exc))
            _run_callback_with_retry(
                on_failure,
                'Welcome email on_failure callback',
                str(exc),
            )

    t = threading.Thread(target=_send, daemon=False, name='welcome-email-send')
    t.start()
