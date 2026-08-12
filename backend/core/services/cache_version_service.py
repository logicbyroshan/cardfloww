"""
Cache version helpers for targeted invalidation.

Instead of deleting broad key patterns, callers include a version token in cache
keys and bump the matching namespace/scope on writes.
"""

import logging

from django.core.cache import cache


logger = logging.getLogger(__name__)


class CacheVersionService:
    """Version counters for namespace-scoped cache invalidation."""

    PREFIX = 'cache_ver'
    TTL_SECONDS = 60 * 60 * 24 * 30

    @classmethod
    def _normalize(cls, value, default: str) -> str:
        token = str(value or '').strip().lower()
        return token or default

    @classmethod
    def _key(cls, namespace: str, scope: str = 'global') -> str:
        ns = cls._normalize(namespace, 'default')
        sc = cls._normalize(scope, 'global')
        return f'{cls.PREFIX}:{ns}:{sc}'

    @classmethod
    def get(cls, namespace: str, scope: str = 'global') -> int:
        """Return current version (initializes to 1)."""
        key = cls._key(namespace, scope)
        value = cache.get(key)
        if value is None:
            cache.set(key, 1, timeout=cls.TTL_SECONDS)
            return 1
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            cache.set(key, 1, timeout=cls.TTL_SECONDS)
            return 1

    @classmethod
    def bump(cls, namespace: str, scope: str = 'global') -> int:
        """Increment version for a namespace/scope and return the new value."""
        key = cls._key(namespace, scope)
        current = cache.get(key)
        if current is None:
            cache.set(key, 2, timeout=cls.TTL_SECONDS)
            return 2

        try:
            new_value = cache.incr(key)
            return max(int(new_value), 1)
        except Exception as exc:
            logger.debug('CacheVersionService.bump fallback for %s: %s', key, exc)
            try:
                new_value = max(int(current), 1) + 1
            except (TypeError, ValueError):
                new_value = 2
            cache.set(key, new_value, timeout=cls.TTL_SECONDS)
            return new_value