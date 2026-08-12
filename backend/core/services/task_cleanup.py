"""
Task Cleanup Service

Handles cleanup of stale and completed tasks:
- Mark stuck tasks as failed
- Remove old result files
- Clean up orphaned temp files

Should be called:
1. On server startup (via Django's AppConfig.ready())
2. Periodically (e.g., via cron or Django management command)
"""
import os
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def cleanup_stale_tasks(hours=24):
    """
    Mark tasks stuck in 'processing' or 'pending' state as failed.
    
    Pending tasks older than the threshold likely had their submission
    lost due to a server restart before the worker picked them up.
    
    Args:
        hours: Consider tasks stale if older than this
        
    Returns:
        Number of tasks cleaned up
    """
    from core.models import BackgroundTask
    
    stale_threshold = timezone.now() - timedelta(hours=hours)

    # Processing tasks — check started_at
    stale_processing = BackgroundTask.objects.filter(
        status='processing',
        started_at__lt=stale_threshold
    )
    # Pending tasks — check created_at (never started)
    stale_pending = BackgroundTask.objects.filter(
        status='pending',
        created_at__lt=stale_threshold
    )
    
    count = 0
    for task in list(stale_processing) + list(stale_pending):
        try:
            task.mark_failed(f'Task timed out after {hours} hours (server restart or worker crash)')
            count += 1
            logger.info("Marked stale task %d (%s) as failed", task.id, task.status)
        except Exception as e:
            logger.error("Failed to mark task %d as failed: %s", task.id, e)
    
    if count:
        logger.info("Cleaned up %d stale background tasks", count)
    
    return count


def cleanup_old_results(days=7):
    """
    Delete old completed task records and their result files.
    
    Args:
        days: Delete records older than this many days
        
    Returns:
        Number of tasks cleaned up
    """
    from core.models import BackgroundTask
    from django.core.files.storage import default_storage

    min_days = max(int(getattr(settings, 'BACKGROUND_TASK_RESULT_MIN_RETENTION_DAYS', 7) or 7), 1)
    try:
        requested_days = int(days)
    except (TypeError, ValueError):
        requested_days = min_days
    safe_days = max(requested_days, min_days)

    if safe_days != requested_days:
        logger.warning(
            "cleanup_old_results days=%s below minimum=%s; clamped to %s",
            requested_days,
            min_days,
            safe_days,
        )
    
    old_threshold = timezone.now() - timedelta(days=safe_days)
    old_tasks = BackgroundTask.objects.filter(
        status__in=['completed', 'failed', 'cancelled'],
        completed_at__lt=old_threshold
    )
    
    count = 0
    for task in old_tasks:
        try:
            # Clean up result file if exists
            if task.result_path:
                try:
                    if default_storage.exists(task.result_path):
                        default_storage.delete(task.result_path)
                        logger.debug("Deleted result file: %s", task.result_path)
                except Exception as e:
                    logger.warning("Failed to delete result file %s: %s", task.result_path, e)
            
            task.delete()
            count += 1
        except Exception as e:
            logger.error("Failed to delete old task %d: %s", task.id, e)
    
    if count:
        logger.info("Deleted %d old background task records", count)
    
    return count


# ── Rate-limiter: prevent cleanup from running more than once per interval ──
# Uses a per-process dict keyed by directory path.  Minimal overhead; works
# correctly with BackgroundWorker's single-threaded executor (max_workers=1).
# Multiple gunicorn workers each have their own memory — that's fine, we only
# need to avoid the same process doing back-to-back scans.

import time as _time

_last_cleanup: dict = {}  # {marker_key: last_run_epoch_seconds}
_MIN_CLEANUP_INTERVAL = 3600  # 1 hour minimum between cleanup runs


def _should_run(marker_key: str) -> bool:
    """Return True if it is time to run cleanup for the given marker key."""
    last = _last_cleanup.get(marker_key, 0)
    return (_time.time() - last) >= _MIN_CLEANUP_INTERVAL


def _mark_ran(marker_key: str) -> None:
    """Record that cleanup for marker_key just ran."""
    _last_cleanup[marker_key] = _time.time()


def _safe_remove(file_path: str) -> bool:
    """
    Delete a file, tolerating concurrent deletions (TOCTOU safety).

    Returns True if the file was deleted by this call, False if it was already
    gone (another process deleted it first) or if deletion failed for another
    reason (logged as warning).
    """
    try:
        os.remove(file_path)
        return True
    except FileNotFoundError:
        # Another process beat us to the delete — not an error
        return False
    except OSError as exc:
        logger.warning("Could not delete %s: %s", file_path, exc)
        return False


def cleanup_orphaned_temp_files(hours=24):
    """
    Remove temp files that are older than specified hours.
    These may be left over from crashed uploads or failed tasks.

    Rate-limited: skips the scan if called again within _MIN_CLEANUP_INTERVAL
    to avoid hammering the filesystem after every background task.

    Args:
        hours: Delete files older than this many hours

    Returns:
        Number of files deleted (0 if rate-limiter blocked the run)
    """
    marker_key = f'temp:{hours}'
    if not _should_run(marker_key):
        return 0

    temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
    if not os.path.exists(temp_dir):
        _mark_ran(marker_key)
        return 0

    cutoff_time = _time.time() - (hours * 3600)
    count = 0

    try:
        entries = os.listdir(temp_dir)
    except OSError as exc:
        logger.error("Error listing temp directory: %s", exc)
        return 0

    for filename in entries:
        file_path = os.path.join(temp_dir, filename)

        # Skip directories (e.g. exports/ sub-dir)
        try:
            if os.path.isdir(file_path):
                continue
            mtime = os.path.getmtime(file_path)
        except FileNotFoundError:
            continue  # Already deleted between listdir and stat
        except OSError as exc:
            logger.warning("Cannot stat temp file %s: %s", filename, exc)
            continue

        if mtime < cutoff_time:
            if _safe_remove(file_path):
                count += 1
                logger.debug("Deleted orphaned temp file: %s", filename)

    _mark_ran(marker_key)
    if count:
        logger.info("Deleted %d orphaned temp files", count)
    return count


def cleanup_old_exports(days=3):
    """
    Remove old export files from the exports directory.

    Rate-limited: skips the scan if called again within _MIN_CLEANUP_INTERVAL.

    Args:
        days: Delete files older than this many days

    Returns:
        Number of files deleted (0 if rate-limiter blocked the run)
    """
    marker_key = f'exports:{days}'
    if not _should_run(marker_key):
        return 0

    exports_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
    if not os.path.exists(exports_dir):
        _mark_ran(marker_key)
        return 0

    cutoff_time = _time.time() - (days * 24 * 3600)
    count = 0

    try:
        entries = os.listdir(exports_dir)
    except OSError as exc:
        logger.error("Error listing exports directory: %s", exc)
        return 0

    for filename in entries:
        file_path = os.path.join(exports_dir, filename)

        try:
            if os.path.isdir(file_path):
                continue
            mtime = os.path.getmtime(file_path)
        except FileNotFoundError:
            continue  # Race: already deleted
        except OSError as exc:
            logger.warning("Cannot stat export file %s: %s", filename, exc)
            continue

        if mtime < cutoff_time:
            if _safe_remove(file_path):
                count += 1
                logger.debug("Deleted old export file: %s", filename)

    _mark_ran(marker_key)
    if count:
        logger.info("Deleted %d old export files", count)
    return count


def cleanup_expired_guest_sandboxes():
    """
    Remove guest sandbox SQLite database files whose sessions have expired or been deleted.
    """
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    sandbox_dir = os.path.join(settings.BASE_DIR, 'guest_sandboxes')
    if not os.path.exists(sandbox_dir):
        return 0

    try:
        filenames = os.listdir(sandbox_dir)
    except OSError:
        return 0

    count = 0
    now = timezone.now()

    for filename in filenames:
        if not filename.endswith('.sqlite3') or filename == 'template.sqlite3':
            continue

        session_key = filename[:-8]  # Remove '.sqlite3'

        # Check if session still exists and is not expired
        session_exists = Session.objects.filter(session_key=session_key, expire_date__gt=now).exists()
        if not session_exists:
            file_path = os.path.join(sandbox_dir, filename)
            try:
                # Close connection if registered
                db_alias = f"guest_{session_key}"
                from django.db import connections
                if db_alias in connections:
                    connections[db_alias].close()
                    del connections.databases[db_alias]
                if db_alias in settings.DATABASES:
                    del settings.DATABASES[db_alias]
            except Exception:
                pass

            try:
                os.remove(file_path)
                count += 1
                logger.info("Deleted expired guest sandbox database file: %s", filename)
            except Exception as e:
                logger.warning("Failed to delete expired sandbox database file %s: %s", file_path, e)

    return count


def run_all_cleanup():
    """
    Run all cleanup operations.
    
    Returns:
        Dict with counts of cleaned up items
    """
    results = {
        'stale_tasks': cleanup_stale_tasks(hours=24),
        'old_results': cleanup_old_results(days=7),
        'orphaned_temp': cleanup_orphaned_temp_files(hours=24),
        'old_exports': cleanup_old_exports(days=3),
        'expired_sandboxes': cleanup_expired_guest_sandboxes(),
    }
    # Activity logs are intentionally NOT auto-cleared.
    # They can be cleared manually from Operations Hub.
    results['old_activity_logs'] = 0
    
    total = sum(results.values())
    if total:
        logger.info("Cleanup completed: %s", results)
    
    return results


def ensure_directories():
    """
    Ensure required directories exist.
    """
    directories = [
        os.path.join(settings.MEDIA_ROOT, 'temp'),
        os.path.join(settings.MEDIA_ROOT, 'exports'),
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        logger.debug("Ensured directory exists: %s", directory)
