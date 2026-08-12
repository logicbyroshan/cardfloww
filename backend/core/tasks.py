"""Celery task definitions for optional external queue execution."""

try:
    from celery import shared_task
except Exception:  # pragma: no cover - optional dependency
    shared_task = None


if shared_task is not None:
    @shared_task(bind=True, name='core.process_background_task')
    def process_background_task(self, task_id: int):
        """Run the existing background worker logic inside a Celery worker."""
        from core.services.background_worker import get_background_worker

        worker = get_background_worker()
        worker._process_task(task_id)
        return {'task_id': task_id, 'status': 'processed'}
else:
    def process_background_task(task_id: int):
        """Fallback placeholder when Celery is not installed."""
        from core.services.background_worker import get_background_worker

        worker = get_background_worker()
        worker._process_task(task_id)
        return {'task_id': task_id, 'status': 'processed'}
