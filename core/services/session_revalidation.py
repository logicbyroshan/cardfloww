import logging
import time
from typing import Iterable

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models.signals import m2m_changed, post_save

from .cache_version_service import CacheVersionService

logger = logging.getLogger(__name__)

_CACHE_PREFIX = 'pvm_reval_marker:'
_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30
_SIGNALS_REGISTERED = False


def _cache_key(user_id: int) -> str:
    return f'{_CACHE_PREFIX}{int(user_id)}'


def get_user_revalidation_marker(user_id: int) -> str:
    """Return marker used by middleware to decide if revalidation must be forced."""
    if not user_id:
        return ''
    value = cache.get(_cache_key(user_id))
    return str(value or '')


def bump_user_revalidation(user_id: int) -> None:
    """Force next request for the user to refresh permission/access state."""
    if not user_id:
        return
    marker = f'{time.time():.6f}'
    try:
        cache.set(_cache_key(user_id), marker, timeout=_CACHE_TTL_SECONDS)
    except Exception as exc:
        logger.debug('Failed to bump revalidation marker for user=%s: %s', user_id, exc)


def bump_users_revalidation(user_ids: Iterable[int]) -> None:
    unique_ids = {int(uid) for uid in (user_ids or []) if uid}
    for user_id in unique_ids:
        bump_user_revalidation(user_id)


def register_revalidation_signals() -> None:
    """Register model signals that invalidate middleware revalidation markers."""
    global _SIGNALS_REGISTERED
    if _SIGNALS_REGISTERED:
        return

    User = get_user_model()

    def _bump_dashboard_versions_for_client(client_id):
        if not client_id:
            return
        try:
            CacheVersionService.bump('client_dash_counts', f'client:{int(client_id)}')
            CacheVersionService.bump('client_staff', f'client:{int(client_id)}')
        except Exception as exc:
            logger.debug('Client dashboard cache bump failed for client=%s: %s', client_id, exc)

    def _bump_admin_dashboard_versions():
        try:
            CacheVersionService.bump('dash_team_overview', 'global')
            CacheVersionService.bump('dash_rcu', 'global')
        except Exception as exc:
            logger.debug('Admin dashboard cache bump failed: %s', exc)

    def _on_user_saved(sender, instance, created=False, raw=False, update_fields=None, **kwargs):
        if raw or not getattr(instance, 'pk', None):
            return
        if update_fields:
            touched = {str(name) for name in update_fields}
            # Login timestamp-only writes do not need forced access revalidation.
            if touched.issubset({'last_login', 'updated_at'}):
                return
        bump_user_revalidation(instance.pk)

        role = str(getattr(instance, 'role', '') or '').strip().lower()
        if role in ('operator', 'assistant'):
            _bump_admin_dashboard_versions()
        if role == 'assistant':
            try:
                from assistants.models import Assistant

                client_id = (
                    Assistant.objects.filter(user_id=instance.pk)
                    .values_list('client_id', flat=True)
                    .first()
                )
                _bump_dashboard_versions_for_client(client_id)
            except Exception as exc:
                logger.debug('Assistant cache bump from user save failed for user=%s: %s', instance.pk, exc)

    def _on_user_m2m_changed(sender, instance, action, **kwargs):
        if action in ('post_add', 'post_remove', 'post_clear'):
            bump_user_revalidation(getattr(instance, 'pk', None))

    def _on_client_saved(sender, instance, raw=False, **kwargs):
        if raw:
            return
        try:
            from assistants.models import Assistant
            from operators.models import Operator

            affected = [instance.user_id]
            affected.extend(
                Assistant.objects.filter(client_id=instance.pk).values_list('user_id', flat=True)
            )
            affected.extend(
                Operator.objects.filter(assigned_clients=instance)
                .values_list('user_id', flat=True)
            )
            bump_users_revalidation(affected)
            _bump_admin_dashboard_versions()
            _bump_dashboard_versions_for_client(getattr(instance, 'pk', None))
        except Exception as exc:
            logger.debug('Client revalidation bump failed for client=%s: %s', getattr(instance, 'pk', None), exc)

    def _on_profile_saved(sender, instance, raw=False, **kwargs):
        if raw:
            return
        bump_user_revalidation(getattr(instance, 'user_id', None))
        _bump_admin_dashboard_versions()
        client_id = getattr(instance, 'client_id', None)
        _bump_dashboard_versions_for_client(client_id)

    def _on_profile_m2m_changed(sender, instance, action, **kwargs):
        if action in ('post_add', 'post_remove', 'post_clear'):
            bump_user_revalidation(getattr(instance, 'user_id', None))
            _bump_admin_dashboard_versions()
            client_id = getattr(instance, 'client_id', None)
            _bump_dashboard_versions_for_client(client_id)

    post_save.connect(
        _on_user_saved,
        sender=User,
        dispatch_uid='pvm_reval_user_post_save',
        weak=False,
    )
    m2m_changed.connect(
        _on_user_m2m_changed,
        sender=User.groups.through,
        dispatch_uid='pvm_reval_user_groups_m2m',
        weak=False,
    )
    m2m_changed.connect(
        _on_user_m2m_changed,
        sender=User.user_permissions.through,
        dispatch_uid='pvm_reval_user_permissions_m2m',
        weak=False,
    )

    # Imported lazily here so app loading is fully initialized first.
    from client.models import Client
    from operators.models import Operator
    from assistants.models import Assistant

    post_save.connect(
        _on_client_saved,
        sender=Client,
        dispatch_uid='pvm_reval_client_post_save',
        weak=False,
    )
    post_save.connect(
        _on_profile_saved,
        sender=Operator,
        dispatch_uid='pvm_reval_operator_post_save',
        weak=False,
    )
    post_save.connect(
        _on_profile_saved,
        sender=Assistant,
        dispatch_uid='pvm_reval_assistant_post_save',
        weak=False,
    )
    m2m_changed.connect(
        _on_profile_m2m_changed,
        sender=Operator.assigned_clients.through,
        dispatch_uid='pvm_reval_operator_assigned_clients_m2m',
        weak=False,
    )
    m2m_changed.connect(
        _on_profile_m2m_changed,
        sender=Assistant.assigned_groups.through,
        dispatch_uid='pvm_reval_assistant_assigned_groups_m2m',
        weak=False,
    )

    _SIGNALS_REGISTERED = True
