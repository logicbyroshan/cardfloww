"""
Background task dispatch helpers.

This module keeps the current in-process worker as the default path, but can
optionally dispatch tasks to Celery when a broker is configured.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _celery_enabled() -> bool:
    """Return True only when Celery can be used safely."""
    broker_url = str(getattr(settings, 'CELERY_BROKER_URL', '') or '').strip()
    if not broker_url:
        return False
    try:
        import celery  # noqa: F401
    except Exception:
        return False
    return True


def dispatch_background_task(task_id: int):
    """Dispatch a task to Celery when available, otherwise use the local worker."""
    # Check if a guest sandbox database is active in the current thread
    from core.db_router import GuestSandboxRouter
    guest_db = GuestSandboxRouter.get_guest_db()
    if guest_db:
        from core.services.background_worker import background_worker
        logger.info('Running task_id=%s synchronously for guest sandbox %s', task_id, guest_db)
        background_worker._process_task(task_id)
        return {'backend': 'synchronous', 'status': 'processed'}

    if _celery_enabled():
        try:
            from core.tasks import process_background_task

            async_result = process_background_task.delay(task_id)
            logger.info('Dispatched task_id=%s to Celery job_id=%s', task_id, async_result.id)
            return {'backend': 'celery', 'job_id': async_result.id}
        except Exception:
            logger.exception('Celery dispatch failed for task_id=%s; falling back to local worker', task_id)

    from core.services.background_worker import background_worker

    future = background_worker.submit_task(task_id)
    logger.info('Dispatched task_id=%s to local background worker', task_id)
    return {'backend': 'threadpool', 'future': future}
