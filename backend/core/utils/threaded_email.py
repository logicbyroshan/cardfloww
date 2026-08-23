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
from core.services.email_delivery_service import EmailDeliveryService

logger = logging.getLogger(__name__)


def send_mail_async(subject, message, from_email, recipient_list,
                    fail_silently=False, **kwargs):
    """
    Drop-in replacement for ``django.core.mail.send_mail`` that routes through
    ``EmailDeliveryService`` with automatic exponential retries on SMTP glitches.
    """
    email_type = kwargs.pop('email_type', 'system')
    recipient_name = kwargs.pop('recipient_name', '')
    max_retries = kwargs.pop('max_retries', 3)

    return EmailDeliveryService.enqueue_and_send(
        subject=subject,
        plain_content=message,
        html_content='',
        from_email=from_email,
        recipient_list=recipient_list,
        email_type=email_type,
        recipient_name=recipient_name,
        max_retries=max_retries,
        auto_deliver=True,
    )


def send_html_email_async(subject, plain_content, html_content,
                          from_email, recipient_list, **kwargs):
    """
    Send an HTML email with plain-text fallback asynchronously with automatic retries.
    """
    email_type = kwargs.pop('email_type', 'system')
    recipient_name = kwargs.pop('recipient_name', '')
    max_retries = kwargs.pop('max_retries', 3)

    return EmailDeliveryService.enqueue_and_send(
        subject=subject,
        plain_content=plain_content,
        html_content=html_content,
        from_email=from_email,
        recipient_list=recipient_list,
        email_type=email_type,
        recipient_name=recipient_name,
        max_retries=max_retries,
        auto_deliver=True,
    )


def send_html_email_with_callback(subject, plain_content, html_content,
                                   from_email, recipient_list,
                                   on_success=None, on_failure=None, **kwargs):
    """
    Send an HTML email asynchronously with tracking, retries, and success/failure callbacks.
    """
    email_type = kwargs.pop('email_type', 'system')
    recipient_name = kwargs.pop('recipient_name', '')
    max_retries = kwargs.pop('max_retries', 3)

    return EmailDeliveryService.enqueue_and_send(
        subject=subject,
        plain_content=plain_content,
        html_content=html_content,
        from_email=from_email,
        recipient_list=recipient_list,
        email_type=email_type,
        recipient_name=recipient_name,
        max_retries=max_retries,
        auto_deliver=True,
        on_success=on_success,
        on_failure=on_failure,
    )
