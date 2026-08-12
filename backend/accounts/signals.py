from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.sessions.models import Session
from .models import UserDeviceSession

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_device_type(request):
    # IMPROVED: Highest priority to explicit client header
    client_type = request.headers.get('X-Client-Type', '').lower()
    if client_type in ('mobile', 'web'):
        return client_type

    ua = request.META.get('HTTP_USER_AGENT', '').lower()
    # Check if this is the mobile app surface or explicitly marked as mobile app
    if request.path.startswith('/app/') or request.path.startswith('/api/mobile/') or request.headers.get('X-Mobile-App') == 'true':
        return 'mobile'
    
    # Common mobile indicators in User-Agent (including custom app identifier and okhttp client)
    mobile_indicators = ['android', 'iphone', 'ipad', 'webos', 'iemobile', 'opera mini', 'adarsh', 'okhttp']
    if any(ind in ua for ind in mobile_indicators):
        return 'mobile'
    
    return 'web'

def get_limits(user):
    """
    Define session limits based on user role.
    Delegates to AuthService for centralized limit management.
    """
    from .services import AuthService
    raw_limits = AuthService.role_surface_limits(user)
    # Map 'desktop' key from service to 'web' key used in signal logic
    return {
        'web': raw_limits.get('desktop', 1),
        'mobile': raw_limits.get('mobile', 1)
    }


def _purge_orphaned_device_sessions(user, device_type, logger):
    """
    Remove UserDeviceSession records whose Django Session no longer exists.

    Without this cleanup, expired/revoked sessions accumulate as orphans and
    inflate the active-session count, causing premature eviction of real
    sessions when the limit is enforced.
    """
    try:
        device_records = UserDeviceSession.objects.filter(
            user=user,
            device_type=device_type,
        ).values_list('id', 'session_key', named=True)

        if not device_records:
            return

        # Collect session keys that still exist in the Django Session table
        all_keys = [r.session_key for r in device_records]
        existing_keys = set(
            Session.objects
            .filter(session_key__in=all_keys, expire_date__gt=timezone.now())
            .values_list('session_key', flat=True)
        )

        # Delete records whose session no longer exists
        orphan_ids = [r.id for r in device_records if r.session_key not in existing_keys]
        if orphan_ids:
            deleted_count = UserDeviceSession.objects.filter(id__in=orphan_ids).delete()[0]
            if deleted_count:
                logger.info(
                    "Purged %d orphaned UserDeviceSession records for user=%s device_type=%s",
                    deleted_count, user.username, device_type,
                )
    except Exception as exc:
        logger.warning("Orphan device-session cleanup failed for user=%s: %s", user.username, exc)


def _delete_session_thoroughly(session_key, logger):
    """
    Delete a Django session from both the DB and the cache layer.

    When using cached_db session backend, deleting only the DB row leaves a
    stale copy in Redis that can keep the evicted user authenticated until the
    cache entry expires.  This helper invalidates both layers.
    """
    # 1. Delete from DB
    Session.objects.filter(session_key=session_key).delete()

    # 2. Invalidate cache (for cached_db backend)
    try:
        from django.contrib.sessions.backends.db import SessionStore
        store = SessionStore(session_key=session_key)
        store.delete()
    except Exception:
        pass

    # 3. Explicit cache key deletion (belt-and-suspenders for Redis)
    try:
        from django.core.cache import cache
        from django.conf import settings
        prefix = getattr(settings, 'CACHE_KEY_PREFIX', '')
        version = getattr(settings, 'CACHE_VERSION', 1)
        # Django's cached_db backend uses this cache-key pattern
        cache_key = f"django.contrib.sessions.cached_db{session_key}"
        cache.delete(cache_key, version=version)
    except Exception:
        pass


@receiver(user_logged_in)
def manage_user_device_sessions(sender, request, user, **kwargs):
    """
    Hook into login to record the session and enforce device-type limits.
    Uses atomic transaction and select_for_update to prevent race conditions.
    """
    if not user or not user.id:
        return

    # Impersonation transitions intentionally bypass global device-limit enforcement
    # so acting as a user from Pro mode does not log out that user's real devices.
    if getattr(request, '_skip_device_session_enforcement', False):
        return

    from django.db import transaction
    import logging
    logger = logging.getLogger(__name__)

    # Ensure session exists
    if not request.session.session_key:
        request.session.create()
    
    session_key = request.session.session_key
    device_type = get_device_type(request)

    try:
        # STEP 0: Purge orphaned records BEFORE doing limit math.
        # This prevents expired sessions from inflating the count.
        _purge_orphaned_device_sessions(user, device_type, logger)

        with transaction.atomic():
            # 1. Record/Update current device session
            UserDeviceSession.objects.update_or_create(
                session_key=session_key,
                defaults={
                    'user': user,
                    'device_type': device_type,
                    'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
                    'ip_address': get_client_ip(request),
                    'last_active': timezone.now()
                }
            )

            # 2. Enforce limits for this device type
            limits = get_limits(user)
            limit = limits.get(device_type, 1)

            # Use select_for_update for race protection.
            # Compute how many OTHER sessions exist and revoke the oldest ones
            # when the count would exceed the per-surface limit. This approach
            # avoids relying solely on queryset ordering semantics and is
            # deterministic: we explicitly pick the oldest records by
            # ascending `(last_active, id)` and remove exactly the required
            # number of entries.
            other_qs = UserDeviceSession.objects.select_for_update().filter(
                user=user,
                device_type=device_type
            ).exclude(session_key=session_key).only('id', 'session_key', 'last_active')

            other_count = other_qs.count()
            # We keep at most (limit - 1) other sessions because the current
            # session occupies one slot. If other_count >= limit, we must remove
            # `other_count - (limit - 1)` oldest entries.
            if other_count >= limit:
                num_to_remove = max(1, other_count - (limit - 1))
                stale_qs = other_qs.order_by('last_active', 'id')[:num_to_remove]

                for entry in stale_qs:
                    try:
                        _delete_session_thoroughly(entry.session_key, logger)
                        logger.info(
                            "Revoked session %s for user %s (device_type=%s, limit=%d hit)",
                            entry.session_key[:8], user.username, device_type, limit,
                        )
                        entry.delete()
                    except Exception:
                        pass
    except Exception as e:
        # FAIL GRACEFULLY: Do not block the user from logging in if session tracking fails
        logger.error(f"Failed to enforce session limits for {user.username}: {e}")

@receiver(user_logged_out)
def cleanup_device_session(sender, request, user, **kwargs):
    """Remove the device session record and clean up guest sandbox database upon manual logout."""
    session_key = request.session.session_key
    if session_key:
        UserDeviceSession.objects.filter(session_key=session_key).delete()

        # Clean up guest sandbox database and connections
        from django.conf import settings
        from django.db import connections
        import os

        db_alias = f"guest_{session_key}"
        db_file = os.path.join(settings.BASE_DIR, 'guest_sandboxes', f"{session_key}.sqlite3")

        try:
            if db_alias in connections:
                connections[db_alias].close()
                del connections.databases[db_alias]
            if db_alias in settings.DATABASES:
                del settings.DATABASES[db_alias]
        except Exception as conn_err:
            logger.warning("Failed to clean up sandbox DB connections for alias %s: %s", db_alias, conn_err)

        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception as e:
                logger.warning("Failed to delete guest sandbox database file %s: %s", db_file, e)
