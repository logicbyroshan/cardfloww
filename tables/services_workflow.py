"""
Workflow Service Module — SINGLE AUTHORITY FOR ALL STATUS TRANSITIONS.

Every status mutation on IDCard or ReprintRequest MUST go through
WorkflowService.transition() or ReprintWorkflowService.transition().

No view, service, or background task should write `.status =` directly.

Contains:
    WorkflowService         — IDCard status transitions
    ReprintWorkflowService  — ReprintRequest status transitions
"""
import logging
from typing import Dict, List, Optional, Any

from django.db import transaction
from django.utils import timezone

from tables.models import IDCard, Table
from core.services.base import BaseService, ServiceResult
from core.services.cache_version_service import CacheVersionService
from core.services.permission_service import PermissionService

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  IDCard Workflow
# ═══════════════════════════════════════════════════════════════════════

class WorkflowService:
    """
    Single authority for IDCard status transitions.

    Usage (single card):
        result = WorkflowService.transition(card, 'verified', user=request.user, request=request)

    Usage (bulk):
        result = WorkflowService.bulk_transition(table, card_ids, 'verified', user=request.user, request=request)

    Rules enforced:
        1. Transition must be in ALLOWED_TRANSITIONS
        2. Mandatory fields must be present (pending → verified)
        3. Image fields must be present (forward moves)
        4. Permission check via PermissionService.has()
        5. Client-readonly guard (client/client_staff on approved+)
        6. Activity logging on success
    """

    # ── Explicit transition matrix ──────────────────────────────────
    ALLOWED_TRANSITIONS: Dict[str, List[str]] = {
        'pending':  ['verified', 'deleted', 'pool'],
        'verified': ['approved', 'pending', 'deleted', 'pool'],
        'approved': ['printed', 'download', 'request', 'verified', 'pending', 'deleted', 'pool'],
        'download': ['printed', 'request', 'approved', 'pending', 'deleted', 'pool'],
        'printed':  ['request', 'approved', 'pending', 'deleted', 'pool'],
        'request':  ['pending', 'approved', 'deleted', 'pool'],
        'pool':     ['pending'],
        'deleted':  ['pending'],
        'reprint':  ['printed', 'download', 'verified', 'approved', 'pending'],
    }

    VALID_STATUSES = list({s for sources in ALLOWED_TRANSITIONS.values() for s in sources} | set(ALLOWED_TRANSITIONS.keys()))

    # The status every new IDCard starts with (creation is *not* a transition)
    INITIAL_STATUS = 'pending'

    # Forward transitions that require ALL image fields populated
    # key = target status, value = list of source statuses that trigger the check
    FORWARD_IMAGE_CHECK: Dict[str, List[str]] = {
        'verified': ['pending'],       # pending → verified
        'approved': ['verified', 'reprint'],      # verified → approved, reprint → approved
    }

    # Mandatory-field enforcement triggers (target_status, source_status)
    MANDATORY_FIELD_TRIGGERS = {
        ('verified', 'pending'),
        ('approved', 'verified'),
        ('approved', 'reprint'),
    }

    # Statuses that are read-only for client/client_staff roles
    CLIENT_READONLY_STATUSES = frozenset({'approved', 'download', 'printed'})

    # ── Permission mapping ──────────────────────────────────────────
    # Which permission key is required to move a card INTO this target status.
    # Special case: pool→pending requires 'perm_idcard_retrieve' instead.
    TRANSITION_PERM_MAP: Dict[str, str] = {
        'verified': 'perm_idcard_verify',
        'approved': 'perm_idcard_approve',
        'printed':  'perm_idcard_approve',
        'download': 'perm_idcard_approve',
        'request':  'perm_idcard_approve',
        'pending':  'perm_idcard_verify',
        'deleted':  'perm_idcard_delete',
        'pool':     'perm_idcard_delete',
    }

    # ── Image field helpers (delegated to BaseService) ──────────────

    @staticmethod
    def _normalize_positive_int_ids(raw_ids: Any) -> List[int]:
        """Normalize mixed payload IDs into unique positive integers."""
        if not isinstance(raw_ids, (list, tuple, set)):
            return []

        normalized: List[int] = []
        seen = set()
        for value in raw_ids:
            if isinstance(value, bool):
                continue
            try:
                parsed = int(str(value).strip())
            except (TypeError, ValueError):
                continue
            if parsed <= 0 or parsed in seen:
                continue
            seen.add(parsed)
            normalized.append(parsed)
        return normalized

    @staticmethod
    def _get_image_field_names(table_fields: list, mandatory_only: bool = False) -> List[str]:
        """Return names of image-type fields in the table schema.
        If mandatory_only=True, only return fields marked as mandatory."""
        return BaseService.get_image_field_names(table_fields or [], mandatory_only=mandatory_only)

    @staticmethod
    def _get_missing_image_fields(card: IDCard, image_field_names: List[str]) -> List[str]:
        """Return image field names that are missing/pending/not-found on a card."""
        missing = []
        field_data = card.field_data or {}
        for name in image_field_names:
            val = field_data.get(name, '')
            if not val or val == 'NOT_FOUND' or str(val).startswith('PENDING:'):
                missing.append(name)
        return missing

    @staticmethod
    def _get_missing_mandatory_fields(card: IDCard, table_fields: list) -> List[str]:
        """Return mandatory field names that are empty on a card."""
        missing = []
        field_data = card.field_data or {}
        for field in table_fields:
            if not field.get('mandatory', False):
                continue
            field_name = field.get('name', '')
            field_type = field.get('type', 'text')
            if not field_name:
                continue
            val = field_data.get(field_name, '')
            if field_type in BaseService.IMAGE_FIELD_TYPES:
                if not val or val == 'NOT_FOUND' or str(val).startswith('PENDING:'):
                    missing.append(field_name)
            else:
                if not val or str(val).strip() == '':
                    missing.append(field_name)
        return missing

    # ── Allowed transitions query (for frontend) ───────────────────

    @classmethod
    def get_allowed_transitions(cls, card: IDCard, user=None) -> List[str]:
        """
        Return list of statuses this card can move to.
        If user is provided, filters by permission as well.
        """
        allowed = list(cls.ALLOWED_TRANSITIONS.get(card.status, []))
        if user is None:
            return allowed

        # Client-readonly filter: Organisation users can only transition approved/download cards BACKWARD
        is_client = PermissionService.is_client_role(user)

        # Permission filter
        result = []
        for target in allowed:
            # Check client-readonly exemption for backward transitions
            if is_client and card.status in cls.CLIENT_READONLY_STATUSES:
                is_backward = False
                if card.status == 'approved' and target in ('verified', 'pending', 'deleted', 'pool'):
                    is_backward = True
                elif card.status == 'download' and target in ('approved', 'verified', 'pending'):
                    is_backward = True
                
                if not is_backward:
                    continue

            perm = cls._get_required_perm(card.status, target)
            if PermissionService.has(user, perm):
                result.append(target)
        return result

    @classmethod
    def _get_required_perm(cls, current_status: str, target_status: str) -> str:
        """Return the required permission key for a specific transition."""
        # Special case: deleted/pool/download → pending requires perm_idcard_retrieve
        if current_status in ('deleted', 'pool', 'download') and target_status == 'pending':
            return 'perm_idcard_retrieve'
        return cls.TRANSITION_PERM_MAP.get(target_status, 'perm_idcard_verify')

    # ── Single-card transition ──────────────────────────────────────

    @classmethod
    def transition(
        cls,
        card: IDCard,
        target_status: str,
        user=None,
        request=None,
        skip_permission: bool = False,
    ) -> ServiceResult:
        """
        Transition a single IDCard to target_status.

        Args:
            card:            IDCard instance (must be refreshed / have current status)
            target_status:   The desired new status string
            user:            The user performing the action (for permission + logging)
            request:         The HTTP request (for activity logging IP)
            skip_permission: If True, skip permission check (for internal/system use)

        Returns:
            ServiceResult with success/failure + message.
        """
        # ── 1. Valid status value ───────────────────────────────────
        if target_status not in cls.VALID_STATUSES:
            return ServiceResult(success=False, message=f'Invalid status: {target_status}')

        # ── Atomic block with row lock to prevent race conditions ───
        with transaction.atomic():
            # Re-fetch with row lock to get fresh status
            try:
                card = IDCard.objects.select_for_update().get(pk=card.pk)
            except IDCard.DoesNotExist:
                return ServiceResult(success=False, message='Card not found')

            current = card.status

            # ── 2. Transition allowed ───────────────────────────────────
            allowed = cls.ALLOWED_TRANSITIONS.get(current, [])
            if target_status not in allowed:
                return ServiceResult(
                    success=False,
                    message=f'Cannot change status from {card.get_status_display()} to {target_status}.'
                )

            # ── 3. Client-readonly guard ────────────────────────────────
            if user and not skip_permission:
                # Allow client/client_staff to move cards backward (e.g. approved -> verified/pending or download -> approved/pending/verified)
                is_backward = False
                if current == 'approved' and target_status in ('verified', 'pending', 'pool'):
                    is_backward = True
                elif current == 'download' and target_status in ('approved', 'verified', 'pending'):
                    is_backward = True

                if not is_backward and PermissionService.is_client_role(user) and current in cls.CLIENT_READONLY_STATUSES:
                    return ServiceResult(
                        success=False,
                        message='Cards in approved / download status cannot be modified by client users.'
                    )

            # ── 4. Permission check ─────────────────────────────────────
            if user and not skip_permission:
                required_perm = cls._get_required_perm(current, target_status)
                if not PermissionService.has(user, required_perm):
                    return ServiceResult(success=False, message='Permission denied')

            # Super admin can bypass required-field/image forward gates.
            enforce_required_validations = not (user and PermissionService.is_super_admin(user))

            # ── 5. Mandatory field check ────────────────────────────────
            table = card.table
            if enforce_required_validations and (target_status, current) in cls.MANDATORY_FIELD_TRIGGERS:
                missing = cls._get_missing_mandatory_fields(card, table.fields or [])
                if missing:
                    return ServiceResult(
                        success=False,
                        message=f'Cannot verify card: required fields are empty: {", ".join(missing)}',
                        data={'missing_fields': missing, 'blocked': True}
                    )

            # ── 6. Image gate (only mandatory image fields) ──────────
            if enforce_required_validations and target_status in cls.FORWARD_IMAGE_CHECK:
                allowed_from = cls.FORWARD_IMAGE_CHECK[target_status]
                if current in allowed_from:
                    img_names = cls._get_image_field_names(table.fields, mandatory_only=True)
                    if img_names:
                        missing = cls._get_missing_image_fields(card, img_names)
                        if missing:
                            return ServiceResult(
                                success=False,
                                message=f'Cannot move card: images missing for {", ".join(missing)}. Upload all images first.',
                                data={'missing_fields': missing, 'blocked': True}
                            )

            # ── 7. Commit ───────────────────────────────────────────────
            card.status = target_status
            update_fields = ['status', 'updated_at']

            # Track who performed the transition
            if user and hasattr(user, 'username'):
                card.modified_by = user.username
                update_fields.append('modified_by')

            # Set/clear timestamps for download and pool transitions
            if target_status == 'download':
                card.downloaded_at = timezone.now()
                update_fields.append('downloaded_at')
            elif current == 'download' and target_status != 'download':
                card.downloaded_at = None
                update_fields.append('downloaded_at')

            if target_status == 'pool':
                card.deleted_at = timezone.now()
                update_fields.append('deleted_at')
            elif current == 'pool' and target_status != 'pool':
                card.deleted_at = None
                update_fields.append('deleted_at')

            # Track when status changed — used for default sort so that
            # plain field edits do NOT push a card to the top of the list.
            card.status_changed_at = timezone.now()
            update_fields.append('status_changed_at')

            card.save(update_fields=update_fields)

        cls._bump_dashboard_cache_versions(table)
        actor_id = getattr(user, 'pk', None)
        logger.info("Card %d: %s → %s by user %s", card.pk, current, target_status, actor_id if actor_id is not None else 'system')

        # ── 8. Activity log ─────────────────────────────────────────
        cls._log_transition(card, current, target_status, user, request)

        return ServiceResult(
            success=True,
            message=f'Card status changed to {card.get_status_display()}!',
            data={
                'status': card.status,
                'status_display': card.get_status_display(),
            }
        )

    # ── Bulk transition ─────────────────────────────────────────────

    @classmethod
    def bulk_transition(
        cls,
        table: Table,
        card_ids: List[int],
        target_status: str,
        user=None,
        request=None,
        skip_permission: bool = False,
    ) -> ServiceResult:
        """
        Transition multiple IDCards to target_status.

        Applies the same guards as transition() per card but optimises
        with querysets where safe. Cards that fail validation are skipped
        (not rejected entirely).

        Returns:
            ServiceResult with updated_count, skipped_count, skipped_ids.
        """
        # ── 1. Valid status value ───────────────────────────────────
        if target_status not in cls.VALID_STATUSES:
            return ServiceResult(success=False, message=f'Invalid status: {target_status}')

        card_ids = cls._normalize_positive_int_ids(card_ids)
        if not card_ids:
            return ServiceResult(success=False, message='No valid card IDs provided')

        # ── 2. Permission check (once, not per-card) ────────────────
        if user and not skip_permission:
            # Client-readonly: reject unless moving backward
            if PermissionService.is_client_role(user):
                locked_cards_statuses = set(
                    IDCard.objects.filter(table=table, id__in=card_ids, status__in=cls.CLIENT_READONLY_STATUSES)
                    .values_list('status', flat=True)
                )
                for current_status in locked_cards_statuses:
                    is_backward = False
                    if current_status == 'approved' and target_status in ('verified', 'pending', 'pool'):
                        is_backward = True
                    elif current_status == 'download' and target_status in ('approved', 'verified', 'pending'):
                        is_backward = True
                    
                    if not is_backward:
                        return ServiceResult(
                            success=False,
                            message='Cards in approved / download status cannot be modified by client users.'
                        )

            # Keep bulk permission checks consistent with single-card transition rules.
            selected_statuses = set(
                IDCard.objects.filter(table=table, id__in=card_ids)
                .values_list('status', flat=True)
            )
            required_perms = {
                cls._get_required_perm(current_status, target_status)
                for current_status in selected_statuses
                if target_status in cls.ALLOWED_TRANSITIONS.get(current_status, [])
            }
            for required_perm in required_perms:
                if required_perm and not PermissionService.has(user, required_perm):
                    return ServiceResult(success=False, message='Permission denied')

        # Super admin can bypass required-field/image forward gates.
        enforce_required_validations = not (user and PermissionService.is_super_admin(user))

        # ── 3. Filter to cards with valid source status ─────────────
        valid_from = [s for s, targets in cls.ALLOWED_TRANSITIONS.items() if target_status in targets]

        # Find eligible cards (no row lock — the final UPDATE re-checks status
        # to handle races safely, and avoids DB lock contention on SQLite/PG)
        eligible_ids = list(
            IDCard.objects.filter(table=table, id__in=card_ids, status__in=valid_from)
            .values_list('id', flat=True)
        )
        if not eligible_ids:
            return ServiceResult(
                success=False,
                message=f'No cards eligible for transition to {target_status}.'
            )

        skipped_mandatory_ids: List[int] = []
        skipped_image_ids: List[int] = []

        # ── 4. Mandatory field check ──────
        matching_triggers = {src for (tgt, src) in cls.MANDATORY_FIELD_TRIGGERS if tgt == target_status}
        if enforce_required_validations and matching_triggers:
            checked_cards = list(IDCard.objects.filter(table=table, id__in=eligible_ids, status__in=matching_triggers))
            valid_ids = []
            checked_ids = {c.id for c in checked_cards}
            for card in checked_cards:
                missing = cls._get_missing_mandatory_fields(card, table.fields or [])
                if missing:
                    skipped_mandatory_ids.append(card.id)
                else:
                    valid_ids.append(card.id)
            # Unchecked cards skip mandatory check
            unchecked_ids = [cid for cid in eligible_ids if cid not in checked_ids]
            eligible_ids = valid_ids + unchecked_ids

            if not eligible_ids and skipped_mandatory_ids:
                return ServiceResult(
                    success=False,
                    message=f'All {len(skipped_mandatory_ids)} card(s) have missing required fields and cannot be moved.',
                    data={'skipped_count': len(skipped_mandatory_ids), 'skipped_ids': skipped_mandatory_ids}
                )

        # ── 5. Image gate (only mandatory image fields) ──────────
        if enforce_required_validations and target_status in cls.FORWARD_IMAGE_CHECK:
            img_names = cls._get_image_field_names(table.fields, mandatory_only=True)
            if img_names:
                allowed_from_statuses = cls.FORWARD_IMAGE_CHECK[target_status]
                cards = list(IDCard.objects.filter(table=table, id__in=eligible_ids))
                valid_ids = []
                for card in cards:
                    if card.status in allowed_from_statuses:
                        missing = cls._get_missing_image_fields(card, img_names)
                        if missing:
                            skipped_image_ids.append(card.id)
                        else:
                            valid_ids.append(card.id)
                    else:
                        valid_ids.append(card.id)
                eligible_ids = valid_ids

                if not eligible_ids and skipped_image_ids:
                    return ServiceResult(
                        success=False,
                        message=f'All {len(skipped_image_ids)} card(s) have missing images and cannot be moved forward.',
                        data={'skipped_count': len(skipped_image_ids), 'skipped_ids': skipped_image_ids}
                    )

        # ── 6. Commit (single queryset update) ─────────────────────
        if not eligible_ids:
            return ServiceResult(
                success=False,
                message=f'No cards eligible for transition to {target_status}.'
            )

        update_kwargs = {'status': target_status}

        # Track who performed the bulk transition
        if user and hasattr(user, 'username'):
            update_kwargs['modified_by'] = user.username

        # Set/clear timestamps for download and pool transitions
        if target_status == 'download':
            update_kwargs['downloaded_at'] = timezone.now()
        else:
            update_kwargs['downloaded_at'] = None

        if target_status == 'pool':
            update_kwargs['deleted_at'] = timezone.now()
        else:
            update_kwargs['deleted_at'] = None

        # Track when status changed — used for default sort so that
        # plain field edits do NOT push a card to the top of the list.
        update_kwargs['status_changed_at'] = timezone.now()

        card_status_pairs = list(
            IDCard.objects.filter(
                table=table,
                id__in=eligible_ids,
                status__in=valid_from,
            ).values_list('id', 'status')
        )

        # Re-check status in WHERE clause to handle concurrent modifications
        # safely (a card whose status changed since step 3 will simply not match)
        with transaction.atomic():
            updated_count = IDCard.objects.filter(
                table=table, id__in=eligible_ids, status__in=valid_from
            ).update(**update_kwargs)

        if updated_count:
            cls._bump_dashboard_cache_versions(table)

        actor_id = getattr(user, 'pk', None)
        logger.info(
            "Bulk transition: %d cards → %s in table %d by user %s",
            updated_count,
            target_status,
            table.pk,
            actor_id if actor_id is not None else 'system',
        )

        # ── 7. Activity log ─────────────────────────────────────────
        cls._log_bulk_transition(table, card_status_pairs, target_status, user, request)

        # ── 8. Build response ───────────────────────────────────────
        total_skipped = len(skipped_mandatory_ids) + len(skipped_image_ids)
        if total_skipped:
            parts = []
            if skipped_mandatory_ids:
                parts.append(f'{len(skipped_mandatory_ids)} missing required fields')
            if skipped_image_ids:
                parts.append(f'{len(skipped_image_ids)} missing images')
            skip_detail = ', '.join(parts)
            return ServiceResult(
                success=True,
                message=f'{updated_count} card(s) updated. {total_skipped} skipped ({skip_detail}).',
                data={
                    'updated_count': updated_count,
                    'skipped_count': total_skipped,
                    'skipped_ids': skipped_mandatory_ids + skipped_image_ids,
                }
            )

        return ServiceResult(
            success=True,
            message=f'{updated_count} cards updated to {target_status}!',
            data={'updated_count': updated_count}
        )

    # ── Activity logging helpers ────────────────────────────────────

    @staticmethod
    def _bump_dashboard_cache_versions(table: Table) -> None:
        """Invalidate dashboard cache versions for affected scope."""
        try:
            client_id = getattr(getattr(table, 'group', None), 'client_id', None)
            CacheVersionService.bump('dash_rcu', 'global')
            CacheVersionService.bump('global_search', 'all')
            CacheVersionService.bump('admin_dash_counts', 'global')
            if client_id:
                CacheVersionService.bump('client_dash_counts', f'client:{int(client_id)}')
        except Exception as exc:
            logger.debug('WorkflowService cache version bump failed: %s', exc)

    @staticmethod
    def _log_transition(card, _old_status, new_status, _user, request):
        """Log a single-card transition."""
        try:
            from core.services.activity_service import ActivityService
            client_name = ''
            try:
                client_name = card.table.group.client.name
            except Exception as exc:
                logger.debug('WorkflowService transition client-name resolution failed: %s', exc)
            status_labels = dict(IDCard.STATUS_CHOICES)
            old_label = status_labels.get(_old_status, str(_old_status).replace('_', ' ').title())
            new_label = status_labels.get(new_status, str(new_status).replace('_', ' ').title())
            client_suffix = f' for {client_name}' if client_name else ''
            ActivityService.log(
                'card_status',
                f'Card moved from {old_label} to {new_label}{client_suffix}',
                user=_user,
                request=request,
                target_model='IDCard',
                target_id=card.id,
                target_name=f'Card #{card.id}',
            )
        except Exception:
            logger.exception('WorkflowService: failed to log transition')

    @staticmethod
    def _log_bulk_transition(table, card_status_pairs, new_status, user, request):
        """Log a bulk transition."""
        try:
            from core.services.activity_service import ActivityService
            from collections import defaultdict
            client_name = ''
            try:
                client_name = table.group.client.name
            except Exception as exc:
                logger.debug('WorkflowService bulk transition client-name resolution failed: %s', exc)
            if not card_status_pairs:
                return

            status_labels = dict(IDCard.STATUS_CHOICES)
            new_label = status_labels.get(new_status, str(new_status).replace('_', ' ').title())
            client_suffix = f' for {client_name}' if client_name else ''

            # Group card status pairs by their starting (old) status to summarize bulk changes
            grouped = defaultdict(list)
            for card_id, old_status in card_status_pairs:
                grouped[old_status].append(card_id)

            for old_status, card_ids in grouped.items():
                count = len(card_ids)
                old_label = status_labels.get(old_status, str(old_status).replace('_', ' ').title())
                if count == 1:
                    card_id = card_ids[0]
                    ActivityService.log(
                        'card_status',
                        f'Card moved from {old_label} to {new_label}{client_suffix}',
                        user=user,
                        request=request,
                        target_model='IDCard',
                        target_id=card_id,
                        target_name=f'Card #{card_id}',
                    )
                else:
                    ActivityService.log(
                        'card_bulk_status',
                        f'{count} cards moved from {old_label} to {new_label}{client_suffix}',
                        user=user,
                        request=request,
                        target_model='IDCard',
                    )
        except Exception:
            logger.exception('WorkflowService: failed to log bulk transition')

    # ── Debug / introspection ───────────────────────────────────────

    @classmethod
    def debug_workflow(cls, card_id: int, user=None) -> Dict[str, Any]:
        """
        Return workflow state for a card (for debug endpoint).

        Returns dict with current status, allowed transitions,
        mandatory field status, image field status.
        """
        try:
            card = IDCard.objects.select_related('table').get(id=card_id)
        except IDCard.DoesNotExist:
            return {'error': f'Card {card_id} not found'}

        table = card.table
        allowed = cls.get_allowed_transitions(card, user)
        all_transitions = list(cls.ALLOWED_TRANSITIONS.get(card.status, []))

        mandatory_missing = cls._get_missing_mandatory_fields(card, table.fields or [])
        img_names = cls._get_image_field_names(table.fields, mandatory_only=True)
        images_missing = cls._get_missing_image_fields(card, img_names) if img_names else []

        return {
            'card_id': card.id,
            'current_status': card.status,
            'current_status_display': card.get_status_display(),
            'all_possible_transitions': all_transitions,
            'user_allowed_transitions': allowed,
            'mandatory_fields_missing': mandatory_missing,
            'image_fields_missing': images_missing,
            'table_id': table.id,
            'table_name': table.name,
        }



