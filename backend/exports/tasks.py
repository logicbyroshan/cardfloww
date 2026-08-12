"""
Background Export Task Manager
==============================

Thin facade over the DB-backed BackgroundTask + BackgroundWorker system.

Previously this module kept task state in an in-memory dict with raw threads,
which meant task state was lost on server restart and broken with multiple
gunicorn workers.  It now delegates entirely to BackgroundTask (DB-backed) and
the singleton BackgroundWorker (ThreadPoolExecutor with configurable worker
count + heavy-task throttling), so:

  - Task state survives server restarts (stored in DB)
  - Multiple gunicorn workers are safe (DB is the shared source of truth)
    - Multiple tasks can progress concurrently without losing DB-backed state
    - Heavy exports remain guarded by worker-side concurrency limits

The public API (start_pdf_export / get_status) is unchanged so no JS or view
code needs modification.

Usage:
    task_id = BackgroundExportManager.start_pdf_export(user, table_id, card_ids, ...)
    status  = BackgroundExportManager.get_status(task_id)
    # When status['state'] == 'completed':
    #   status['download_url'] → URL to download the file
"""
import logging
import os
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def _safe_media_relative_path(path_value: Any) -> str:
    """Return a media-relative path only when it safely stays inside MEDIA_ROOT."""
    raw = str(path_value or '').strip().replace('\\', '/')
    if not raw:
        return ''

    # Reject absolute and traversal-like paths from task metadata.
    if raw.startswith('/'):
        return ''
    parts = [part for part in raw.split('/') if part]
    if not parts or any(part in ('.', '..') for part in parts):
        return ''

    media_root = os.path.abspath(settings.MEDIA_ROOT)
    candidate = os.path.abspath(os.path.join(media_root, *parts))
    try:
        if os.path.commonpath([media_root, candidate]) != media_root:
            return ''
    except ValueError:
        return ''

    return os.path.relpath(candidate, media_root).replace('\\', '/')


def _format_file_size(size_bytes: Any) -> str:
    """Format a byte count into a short human-readable label."""
    try:
        value = int(size_bytes or 0)
    except (TypeError, ValueError):
        return ''
    if value <= 0:
        return ''

    units = ['B', 'KB', 'MB', 'GB', 'TB']
    amount = float(value)
    unit_idx = 0
    while amount >= 1024 and unit_idx < len(units) - 1:
        amount /= 1024.0
        unit_idx += 1

    precision = 0 if unit_idx == 0 else 1
    return f"{amount:.{precision}f} {units[unit_idx]}"


class BackgroundExportManager:
    """
    Facade that queues PDF exports via BackgroundTask + BackgroundWorker.

    Keeps the same public interface as the old in-memory implementation so
    that existing callers (views, templates, JS) require no changes.
    """

    @classmethod
    def start_pdf_export(
        cls,
        user,
        table_id: int,
        card_ids: list,
        status: str = '',
        template_id: int = None,
        font_mode: str = 'auto',
        shorten_titles: bool = False,
        break_mode: str = 'class_section',
    ) -> str:
        """
        Enqueue a PDF export and return a task_id string.

        Creates a BackgroundTask DB record and submits it to the
        BackgroundWorker queue.  Returns str(task.id) so the URL-safe
        string contract with callers is preserved.
        """
        from core.models import BackgroundTask
        from core.services.task_queue import dispatch_background_task

        metadata: Dict[str, Any] = {
            'table_id': table_id,
            'card_ids': list(card_ids) if card_ids else [],
            'status': status,
            'template_id': template_id,
            'font_mode': font_mode or 'auto',
            'shorten_titles': bool(shorten_titles),
            'break_mode': 'class_only' if str(break_mode or '').strip().lower() == 'class_only' else 'class_section',
        }

        task, error = BackgroundTask.create_if_no_active(
            user=user,
            task_type='export_pdf',
            metadata=metadata,
            total=len(card_ids) if card_ids else 0,
        )

        if task is None:
            # User already has an active PDF export — return its ID so the
            # frontend can poll the existing task rather than receiving an error.
            logger.warning(
                "PDF export blocked for user=%s: %s", user.id, error
            )
            existing = BackgroundTask.has_active_task(user, task_type='export_pdf')
            if existing:
                return str(existing.id)
            # Unlikely fallback: create anyway
            task = BackgroundTask.objects.create(
                user=user,
                task_type='export_pdf',
                metadata=metadata,
                total=len(card_ids) if card_ids else 0,
            )

        dispatch_background_task(task.id)

        logger.info(
            "PDF export enqueued: user=%s table=%d cards=%d task_id=%d",
            user.id, table_id, len(card_ids) if card_ids else 0, task.id,
        )
        return str(task.id)

    @classmethod
    def start_xlsx_export(
        cls,
        user,
        table_id: int,
        card_ids: list,
        status: str = '',
    ) -> str:
        """Enqueue an Excel export and return a task_id string."""
        from core.models import BackgroundTask
        from core.services.task_queue import dispatch_background_task

        metadata: Dict[str, Any] = {
            'table_id': table_id,
            'card_ids': list(card_ids) if card_ids else [],
            'status': status,
        }

        task, error = BackgroundTask.create_if_no_active(
            user=user,
            task_type='export_excel',
            metadata=metadata,
            total=len(card_ids) if card_ids else 0,
        )

        if task is None:
            existing = BackgroundTask.has_active_task(user, task_type='export_excel')
            if existing:
                return str(existing.id)
            task = BackgroundTask.objects.create(
                user=user,
                task_type='export_excel',
                metadata=metadata,
                total=len(card_ids) if card_ids else 0,
            )

        dispatch_background_task(task.id)
        logger.info(
            "XLSX export enqueued: user=%s table=%d cards=%d task_id=%d",
            user.id, table_id, len(card_ids) if card_ids else 0, task.id,
        )
        return str(task.id)

    @classmethod
    def start_docx_export(
        cls,
        user,
        table_id: int,
        card_ids: list,
        status: str = '',
        doc_format: str = 'docx',
        template_id: int = None,
        break_enabled: bool = False,
        break_pages: int = 0,
        break_mode: str = 'class_section',
    ) -> str:
        """Enqueue a Word export and return a task_id string."""
        from core.models import BackgroundTask
        from core.services.task_queue import dispatch_background_task

        metadata: Dict[str, Any] = {
            'table_id': table_id,
            'card_ids': list(card_ids) if card_ids else [],
            'status': status,
            # Word 2003 (.doc) format has been removed — always use .docx
            'doc_format': 'docx',
            'template_id': template_id,
            'break_enabled': break_enabled,
            'break_pages': break_pages,
            'break_mode': break_mode,
        }

        task, error = BackgroundTask.create_if_no_active(
            user=user,
            task_type='export_docx',
            metadata=metadata,
            total=len(card_ids) if card_ids else 0,
        )

        if task is None:
            existing = BackgroundTask.has_active_task(user, task_type='export_docx')
            if existing:
                return str(existing.id)
            task = BackgroundTask.objects.create(
                user=user,
                task_type='export_docx',
                metadata=metadata,
                total=len(card_ids) if card_ids else 0,
            )

        dispatch_background_task(task.id)
        logger.info(
            "DOCX export enqueued: user=%s table=%d cards=%d task_id=%d",
            user.id, table_id, len(card_ids) if card_ids else 0, task.id,
        )
        return str(task.id)

    @classmethod
    def get_status(cls, task_id: str, user=None) -> Optional[Dict[str, Any]]:
        """
        Return a status dict for the given task_id string.

        The returned dict has the same keys as the old in-memory
        implementation so that views and JS need no changes:
          state, progress, message, download_url, filename

        Returns None if the task does not exist or is not owned by user.
        """
        from core.models import BackgroundTask

        try:
            task_qs = BackgroundTask.objects.all()
            if user is not None:
                task_qs = task_qs.filter(user=user)
            task = task_qs.get(id=int(task_id))
        except (BackgroundTask.DoesNotExist, ValueError, TypeError):
            return None

        # Map DB status → state string used by the frontend
        state = task.status
        if state == 'pending':
            state = 'processing'  # frontend only knows processing/completed/failed

        progress = task.progress_percentage

        result_meta = task.metadata.get('result', {}) if isinstance(task.metadata, dict) else {}

        # Build download URL from result_path (relative to MEDIA_ROOT)
        download_url = ''
        filename = ''
        safe_result_rel = ''
        if task.status == 'completed' and task.result_path:
            safe_result_rel = _safe_media_relative_path(task.result_path)
            if safe_result_rel:
                download_url = settings.MEDIA_URL.rstrip('/') + '/' + safe_result_rel
            filename = result_meta.get('filename', os.path.basename(task.result_path))

        file_size_bytes = 0
        try:
            file_size_bytes = int(result_meta.get('file_size_bytes') or 0)
        except (TypeError, ValueError):
            file_size_bytes = 0

        if task.status == 'completed' and file_size_bytes <= 0 and safe_result_rel:
            full_path = os.path.join(settings.MEDIA_ROOT, safe_result_rel.replace('/', os.sep))
            if os.path.exists(full_path):
                try:
                    file_size_bytes = os.path.getsize(full_path)
                except OSError:
                    file_size_bytes = 0

        file_size_label = _format_file_size(file_size_bytes)

        # Human-readable message
        _type_labels = {'export_pdf': 'PDF', 'export_docx': 'Word', 'export_excel': 'Excel', 'export_zip': 'ZIP'}
        _export_label = _type_labels.get(task.task_type, 'Export')
        if task.status == 'pending':
            message = 'Queued, waiting to start...'
        elif task.status == 'processing':
            total = task.total or 0
            if task.progress and total:
                message = f'Generating {_export_label}... ({task.progress}/{total} cards)'
            elif total:
                message = f'Generating {_export_label} for {total} cards...'
            else:
                message = f'Generating {_export_label}...'
        elif task.status == 'completed':
            count = result_meta.get('card_count', '')
            if count and file_size_label:
                message = f'Export complete ({count} cards, {file_size_label})'
            elif count:
                message = f'Export complete ({count} cards)'
            elif file_size_label:
                message = f'Export complete ({file_size_label})'
            else:
                message = 'Export complete'
        elif task.status == 'failed':
            message = task.error_message or 'Export failed. Please try again.'
        else:
            message = task.status

        return {
            'state': state,
            'progress': progress,
            'message': message,
            'download_url': download_url,
            'filename': filename,
            'file_size_bytes': file_size_bytes,
            'file_size_label': file_size_label,
        }
