"""
Global Export Concurrency Throttle
===================================

Limits the number of *sync* (in-request) exports running across all Gunicorn
workers using a Redis INCR counter with TTL.  Async exports (BackgroundTask /
BackgroundWorker) are NOT affected — they have their own semaphore-based limits.

Usage in views::

    from .export_throttle import acquire_global_export_slot, release_global_export_slot

    slot = acquire_global_export_slot()
    if slot is None:
        return JsonResponse({'success': False, 'message': '...'}, status=429)
    try:
        # ... sync export work ...
    finally:
        release_global_export_slot(slot)
"""
import logging
import uuid

from django.conf import settings
from django.core.cache import cache as django_cache

logger = logging.getLogger(__name__)

# Redis key for the global sync export counter
_GLOBAL_KEY = 'global_sync_export_slots'

# Safety TTL — auto-release if a worker crashes mid-export (seconds)
_SLOT_TTL = 300  # 5 minutes


def _max_slots() -> int:
    """Maximum concurrent sync exports system-wide (configurable via settings)."""
    return max(1, int(getattr(settings, 'MAX_CONCURRENT_SYNC_EXPORTS', 3) or 3))


def acquire_global_export_slot() -> str | None:
    """Try to acquire a global sync-export slot.

    Returns a slot key (str) on success, or None when the system is at capacity.
    The slot key must be passed to :func:`release_global_export_slot` in a
    ``finally`` block.
    """
    max_slots = _max_slots()

    # Each slot is a separate cache key with TTL — this is simpler and more
    # reliable than INCR/DECR (which can drift on crashes).
    for _attempt in range(max_slots):
        slot_key = f'{_GLOBAL_KEY}:{_attempt}'
        # cache.add() is atomic: returns True only if the key didn't exist.
        if django_cache.add(slot_key, 1, _SLOT_TTL):
            return slot_key

    logger.warning(
        'Global sync export throttle reached (max=%d). Request rejected.',
        max_slots,
    )
    return None


def release_global_export_slot(slot_key: str | None) -> None:
    """Release a previously acquired slot."""
    if slot_key:
        django_cache.delete(slot_key)
