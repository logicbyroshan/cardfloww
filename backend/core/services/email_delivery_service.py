"""
Email Delivery & Retry Queue Service
====================================
Robust, asynchronous email delivery architecture supporting:
- Non-blocking enqueuing & immediate asynchronous dispatch
- Automatic exponential backoff with jitter on transient SMTP failures / busy states
- Persistent EmailLog status transitions (pending -> sending -> retry / sent / failed)
- Background retry queue processing
- Thread safety and safe SQLite connection recycling
"""

import logging
import random
import threading
import time
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import close_old_connections, transaction
from django.utils import timezone

from core.models import EmailLog

logger = logging.getLogger(__name__)

# Transient SMTP / Network error indicators
_TRANSIENT_ERROR_TOKENS = (
    '421', '450', '451', '452', 'temporarily unavailable', 'rate limit',
    'try again later', 'timeout', 'timed out', 'connection refused',
    'connection reset', 'server disconnected', 'socket', 'network is unreachable',
    'temporary failure', 'too many connections', 'service unavailable',
    'database is locked', 'database table is locked',
)


def _is_transient_error(exc: Exception) -> bool:
    """Determine whether an exception is likely transient and suitable for retry."""
    err_str = str(exc or '').lower()
    return any(token in err_str for token in _TRANSIENT_ERROR_TOKENS)


def _calculate_backoff_seconds(retry_count: int, base_seconds: int = 25, max_seconds: int = 1800) -> int:
    """
    Calculate exponential backoff with jitter:
    attempt 1: ~30-40s
    attempt 2: ~60-80s
    attempt 3: ~130-160s
    attempt 4: ~260-300s
    """
    factor = 2 ** max(0, retry_count)
    calculated = factor * base_seconds
    jitter = random.uniform(3.0, 12.0)
    return min(max_seconds, int(calculated + jitter))


class EmailDeliveryService:
    """Singleton service for queued email delivery and exponential retries."""

    _worker_threads = []

    @classmethod
    def enqueue_and_send(
        cls,
        *,
        subject: str,
        plain_content: str,
        html_content: str = '',
        from_email: str = '',
        recipient_list: list = None,
        email_type: str = EmailLog.EMAIL_TYPE_SYSTEM,
        recipient_name: str = '',
        max_retries: int = 3,
        auto_deliver: bool = True,
        on_success=None,
        on_failure=None,
    ) -> list:
        """
        Create EmailLog records in 'pending' status and spawn asynchronous delivery.
        Returns the list of created EmailLog instances.
        """
        recipients = [r.strip() for r in (recipient_list or []) if r and str(r).strip()]
        if not recipients:
            return []

        from_addr = from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', '')
        created_logs = []

        now = timezone.now()
        for recipient in recipients:
            try:
                log = EmailLog.objects.create(
                    recipient_name=recipient_name or recipient,
                    recipient_email=recipient,
                    subject=subject or '',
                    body_text=plain_content or '',
                    body_html=html_content or '',
                    email_type=email_type or EmailLog.EMAIL_TYPE_SYSTEM,
                    status=EmailLog.STATUS_PENDING,
                    retry_count=0,
                    max_retries=max_retries,
                    next_retry_at=now,
                    metadata={'from_email': from_addr, 'created_via': 'EmailDeliveryService'},
                )
                created_logs.append(log)
            except Exception as e:
                logger.error("Failed to create EmailLog for %s: %s", recipient, e)

        if auto_deliver and created_logs:
            cls._dispatch_async_delivery(created_logs, on_success=on_success, on_failure=on_failure)

        return created_logs

    @classmethod
    def deliver_single_log(cls, log_id: int, on_success=None, on_failure=None) -> bool:
        """
        Attempt immediate delivery of a single EmailLog by ID.
        Handles transient vs permanent errors, backoff scheduling, and callbacks.
        """
        close_old_connections()
        try:
            log = EmailLog.objects.get(id=log_id)
        except EmailLog.DoesNotExist:
            logger.warning("EmailLog #%s not found for delivery.", log_id)
            return False

        if log.status == EmailLog.STATUS_SENT:
            return True

        from_addr = (log.metadata or {}).get('from_email') or getattr(settings, 'DEFAULT_FROM_EMAIL', '')
        now = timezone.now()

        # Mark as sending
        try:
            log.status = EmailLog.STATUS_SENDING
            log.last_attempt_at = now
            log.save(update_fields=['status', 'last_attempt_at'])
        except Exception:
            pass

        try:
            # Perform SMTP send with explicit timeout
            connection = get_connection(timeout=25)
            msg = EmailMultiAlternatives(
                subject=log.subject,
                body=log.body_text or (log.subject or 'Notification'),
                from_email=from_addr,
                to=[log.recipient_email],
                connection=connection,
            )
            if log.body_html:
                msg.attach_alternative(log.body_html, "text/html")

            msg.send(fail_silently=False)

            # Success
            log.status = EmailLog.STATUS_SENT
            log.sent_at = timezone.now()
            log.error_message = ''
            log.next_retry_at = None
            log.save(update_fields=['status', 'sent_at', 'error_message', 'next_retry_at'])
            logger.info("EmailLog #%d successfully delivered to %s", log.id, log.recipient_email)

            if callable(on_success):
                try:
                    on_success()
                except Exception as cb_err:
                    logger.warning("on_success callback error for EmailLog #%d: %s", log.id, cb_err)

            return True

        except Exception as exc:
            logger.error("Email delivery failed for EmailLog #%d (%s): %s", log.id, log.recipient_email, exc)
            is_transient = _is_transient_error(exc)
            new_retry_count = log.retry_count + 1

            meta = dict(log.metadata or {})
            history = meta.get('attempt_history', [])
            history.append({
                'attempt': new_retry_count,
                'timestamp': now.isoformat(),
                'error': str(exc)[:500],
                'transient': is_transient,
            })
            meta['attempt_history'] = history
            meta['last_error'] = str(exc)[:500]

            log.retry_count = new_retry_count
            log.metadata = meta
            log.error_message = str(exc)[:2000]

            if is_transient and new_retry_count <= log.max_retries:
                backoff_sec = _calculate_backoff_seconds(new_retry_count)
                log.status = EmailLog.STATUS_RETRY
                log.next_retry_at = now + timedelta(seconds=backoff_sec)
                log.save(update_fields=['status', 'retry_count', 'next_retry_at', 'error_message', 'metadata'])
                logger.info(
                    "EmailLog #%d scheduled for retry %d/%d in %ds (at %s)",
                    log.id, new_retry_count, log.max_retries, backoff_sec, log.next_retry_at
                )
            else:
                log.status = EmailLog.STATUS_FAILED
                log.next_retry_at = None
                log.save(update_fields=['status', 'retry_count', 'next_retry_at', 'error_message', 'metadata'])
                logger.warning(
                    "EmailLog #%d marked as failed (transient=%s, attempts=%d/%d)",
                    log.id, is_transient, new_retry_count, log.max_retries
                )

                if callable(on_failure):
                    try:
                        on_failure(str(exc))
                    except Exception as cb_err:
                        logger.warning("on_failure callback error for EmailLog #%d: %s", log.id, cb_err)

            return False
        finally:
            close_old_connections()

    @classmethod
    def process_retry_queue(cls, batch_size: int = 50) -> int:
        """
        Query all pending or retrying emails that are due for delivery and process them.
        Returns the number of logs picked up for delivery.
        """
        close_old_connections()
        now = timezone.now()

        # Find emails ready to be sent or retried
        ready_logs = list(
            EmailLog.objects.filter(
                status__in=[EmailLog.STATUS_PENDING, EmailLog.STATUS_RETRY],
                next_retry_at__lte=now,
            ).order_by('next_retry_at', 'id')[:batch_size]
        )

        if not ready_logs:
            return 0

        logger.info("Email queue runner processing %d ready email(s)...", len(ready_logs))
        for log in ready_logs:
            try:
                cls.deliver_single_log(log.id)
            except Exception as e:
                logger.error("Error executing queued delivery for EmailLog #%d: %s", log.id, e)

        return len(ready_logs)

    @classmethod
    def retry_failed_email(cls, log_id: int) -> bool:
        """
        Reset an existing failed or on-hold EmailLog and immediately trigger delivery.
        """
        try:
            log = EmailLog.objects.get(id=log_id)
            log.status = EmailLog.STATUS_PENDING
            log.retry_count = 0
            log.next_retry_at = timezone.now()
            log.error_message = ''
            log.save(update_fields=['status', 'retry_count', 'next_retry_at', 'error_message'])
            cls._dispatch_async_delivery([log])
            return True
        except EmailLog.DoesNotExist:
            return False

    @classmethod
    def retry_all_failed(cls, max_age_days: int = 7) -> int:
        """
        Reschedule all failed emails from recent days back into the delivery queue.
        """
        cutoff = timezone.now() - timedelta(days=max_age_days)
        failed_logs = EmailLog.objects.filter(
            status=EmailLog.STATUS_FAILED,
            created_at__gte=cutoff,
        )
        count = failed_logs.count()
        now = timezone.now()
        failed_logs.update(
            status=EmailLog.STATUS_PENDING,
            retry_count=0,
            next_retry_at=now,
            error_message='',
        )
        cls._trigger_queue_drain_async()
        return count

    # ── Internal Threading Dispatchers ────────────────────────────────────────

    @classmethod
    def _dispatch_async_delivery(cls, logs: list, on_success=None, on_failure=None):
        """Spawn a dedicated worker thread to deliver one or more email logs."""
        log_ids = [log.id for log in logs]

        def _worker():
            for lid in log_ids:
                try:
                    cls.deliver_single_log(lid, on_success=on_success, on_failure=on_failure)
                except Exception as ex:
                    logger.exception("Unexpected error in async email delivery thread for log #%d: %s", lid, ex)

        t = threading.Thread(target=_worker, daemon=True, name=f'email-dispatch-{int(time.time())}')
        t.start()

    @classmethod
    def _trigger_queue_drain_async(cls):
        """Asynchronously triggers a queue processing run."""
        def _drain():
            cls.process_retry_queue(batch_size=50)

        t = threading.Thread(target=_drain, daemon=True, name='email-queue-drain')
        t.start()
