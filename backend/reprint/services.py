"""
Reprint Workflow Services
=========================
ReprintWorkflowService — Single authority for reprint lifecycle state transitions.

Architecture & Business Rules:
1. Only cards where status='download' are eligible for the Reprint List.
2. In the Reprint List, each card is shown uniquely (deduplicated).
3. Student cards can be edited in the Reprint List before or during request submission.
4. When requested, a ReprintRequest is created in status='requested' with staged changes.
5. In the Requested List, each card appears once. Admin can:
   - Reject / Cancel: Request is removed/rejected; card returns to normal in the Reprint List.
   - Confirm: Staged changes are applied directly in-place to the original IDCard.field_data
     without creating duplicate cards. The card's lifetime reprint_number is incremented.
6. In the Confirmed List, all confirmed reprint occurrences are tracked with their reprint count.
"""
import logging
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from tables.models import IDCard, Table
from core.services.base import ServiceResult
from core.services.cache_version_service import CacheVersionService
from core.services.activity_service import ActivityService
from .models import ReprintRequest

logger = logging.getLogger(__name__)


class ReprintWorkflowService:
    """
    Core service managing the 3-step reprint lifecycle:
      Reprint List (Downloaded source) -> Requested List -> Confirmed List
    """

    ALLOWED_TRANSITIONS: Dict[str, List[str]] = {
        'requested':  ['confirmed', 'rejected', 'cancelled'],
        'confirmed':  ['requested', 'downloaded', 'cancelled'],
        'downloaded': [],
        'rejected':   ['requested'],
        'cancelled':  ['requested'],
    }

    VALID_STATUSES = ['requested', 'confirmed', 'downloaded', 'rejected', 'cancelled']
    INITIAL_STATUS = 'requested'

    @staticmethod
    def _status_label(status: str) -> str:
        labels = dict(ReprintRequest.REPRINT_STATUS_CHOICES)
        return labels.get(status, str(status or '').replace('_', ' ').title())

    @staticmethod
    def _normalize_positive_int_ids(raw_ids: Any) -> List[int]:
        """Normalize raw ID payloads into unique positive integers."""
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

    @classmethod
    def _bump_dashboard_cache_versions(cls, table: Table) -> None:
        """Invalidate dashboard cache versions for reprint data updates."""
        try:
            CacheVersionService.bump('admin_dash_counts', 'global')
            client_id = getattr(getattr(table, 'group', None), 'client_id', None)
            if client_id:
                CacheVersionService.bump('client_dash_counts', f'client:{int(client_id)}')
        except Exception:
            pass

    # ── 1. Create Reprint Requests (Reprint List -> Requested List) ───

    @classmethod
    def create_requests(
        cls,
        table: Table,
        card_ids: List[int],
        reason: str = '',
        changes_by_card: Optional[Dict[str, Dict[str, Any]]] = None,
        requested_by=None,
    ) -> ServiceResult:
        """
        Create reprint requests for the given card IDs.
        Skips cards that already have an active pending request (status='requested').
        Captures any staged field updates in `changes` without modifying original card until confirmed.
        """
        card_ids = cls._normalize_positive_int_ids(card_ids)
        if not card_ids:
            return ServiceResult(success=False, message='No card IDs provided')

        reason = str(reason or '').strip()
        changes_map = changes_by_card or {}

        with transaction.atomic():
            valid_cards = list(
                IDCard.objects.select_for_update().filter(
                    table=table,
                    id__in=card_ids,
                    status='download',
                )
            )
            valid_ids = {c.id for c in valid_cards}

            already_requested = set(
                ReprintRequest.objects.filter(
                    table=table,
                    card_id__in=valid_ids,
                    status='requested',
                ).values_list('card_id', flat=True)
            )

            eligible_cards = [c for c in valid_cards if c.id not in already_requested]
            to_create = []

            for card in eligible_cards:
                # Count prior confirmed reprints for this card
                prior_count = ReprintRequest.objects.filter(
                    card=card,
                    status__in=['confirmed', 'downloaded'],
                ).count()
                next_reprint_number = prior_count + 1

                card_changes = changes_map.get(str(card.id)) or changes_map.get(card.id) or {}
                if not isinstance(card_changes, dict):
                    card_changes = {}

                to_create.append(
                    ReprintRequest(
                        card=card,
                        table=table,
                        status=cls.INITIAL_STATUS,
                        reason=reason,
                        changes=card_changes,
                        reprint_number=next_reprint_number,
                        requested_by=requested_by,
                    )
                )

            if to_create:
                ReprintRequest.objects.bulk_create(to_create, batch_size=500)
            created = len(to_create)

        skipped_count = len(already_requested & set(card_ids))

        if created > 0:
            cls._bump_dashboard_cache_versions(table)
            ActivityService.log_reprint_summary(
                user=requested_by,
                action='reprint request(s) created',
                count=created,
                table=table,
            )

        return ServiceResult(
            success=True,
            message=f'{created} reprint request(s) created',
            data={
                'created_count': created,
                'skipped_count': skipped_count,
            },
        )

    # ── 2. Confirm Requests (Requested List -> Confirmed List) ────────

    @classmethod
    def confirm_requests(
        cls,
        table: Table,
        rr_ids: List[int],
        user=None,
    ) -> ServiceResult:
        """
        Confirm reprint requests: status becomes 'confirmed'.
        If any request had staged changes in `changes`, applies them directly
        in-place to the original IDCard.field_data.
        The card itself remains the same card (no duplicate created).
        """
        rr_ids = cls._normalize_positive_int_ids(rr_ids)
        if not rr_ids:
            return ServiceResult(success=False, message='No reprint IDs provided')

        now = timezone.now()
        confirmed_count = 0
        confirmed_ids = []

        with transaction.atomic():
            requests_qs = ReprintRequest.objects.select_for_update().select_related('card').filter(
                id__in=rr_ids,
                table=table,
                status='requested',
            )

            for rr in requests_qs:
                card = rr.card
                # Apply in-place field changes if any were staged
                if rr.changes and isinstance(rr.changes, dict) and len(rr.changes) > 0:
                    current_fd = dict(card.field_data or {})
                    current_fd.update(rr.changes)
                    card.field_data = current_fd
                    card.updated_at = now
                    card.save(update_fields=['field_data', 'updated_at'])

                # Recalculate lifetime confirmed reprint count for this card
                prior_confirmed = ReprintRequest.objects.filter(
                    card=card,
                    status__in=['confirmed', 'downloaded'],
                ).exclude(id=rr.id).count()

                rr.status = 'confirmed'
                rr.reprint_number = prior_confirmed + 1
                rr.confirmed_by = user
                rr.confirmed_at = now
                rr.updated_at = now
                rr.save(update_fields=['status', 'reprint_number', 'confirmed_by', 'confirmed_at', 'updated_at'])

                confirmed_count += 1
                confirmed_ids.append(rr.id)

        if confirmed_count == 0:
            return ServiceResult(success=False, message='No eligible requested reprint items found to confirm.')

        cls._bump_dashboard_cache_versions(table)
        ActivityService.log_reprint_summary(
            user=user,
            action='confirmed',
            count=confirmed_count,
            table=table,
            from_status='requested',
            to_status='confirmed',
        )

        return ServiceResult(
            success=True,
            message=f'{confirmed_count} reprint request(s) confirmed successfully.',
            data={
                'confirmed_count': confirmed_count,
                'confirmed_ids': confirmed_ids,
            },
        )

    # ── 3. Reject / Cancel Requests (Returns card to Reprint List) ─────

    @classmethod
    def reject_requests(
        cls,
        table: Table,
        rr_ids: List[int],
        reason: str = '',
        move_card_to_deleted: bool = False,
        user=None,
    ) -> ServiceResult:
        """
        Reject or cancel reprint requests in 'requested' or 'confirmed' status.
        Removes the request record, returning the card to the available Reprint List.
        Any unconfirmed staged changes are discarded safely without affecting the card.
        """
        rr_ids = cls._normalize_positive_int_ids(rr_ids)
        if not rr_ids:
            return ServiceResult(success=False, message='No reprint IDs provided')

        with transaction.atomic():
            rr_qs = ReprintRequest.objects.select_for_update().filter(
                id__in=rr_ids,
                table=table,
                status__in=['requested', 'confirmed'],
            )

            rejected_ids = list(rr_qs.values_list('id', flat=True))
            rejected_count = len(rejected_ids)
            card_ids = list(rr_qs.values_list('card_id', flat=True))

            if move_card_to_deleted and card_ids:
                now = timezone.now()
                IDCard.objects.filter(id__in=card_ids).update(
                    status='deleted',
                    deleted_at=now,
                    status_changed_at=now,
                    updated_at=now,
                )

            rr_qs.delete()

        if rejected_count == 0:
            return ServiceResult(success=False, message='No matching reprint requests found to reject.')

        cls._bump_dashboard_cache_versions(table)
        ActivityService.log_reprint_reject(
            user=user,
            count=rejected_count,
            table=table,
            move_to_pool=bool(move_card_to_deleted),
        )

        return ServiceResult(
            success=True,
            message=f'{rejected_count} reprint request(s) rejected/cancelled.',
            data={
                'rejected_count': rejected_count,
                'rejected_ids': rejected_ids,
            },
        )

    # ── 4. Bulk Transition (Generic / Downloaded) ─────────────────────

    @classmethod
    def bulk_transition(
        cls,
        table: Table,
        rr_ids: List[int],
        target_status: str,
        user=None,
    ) -> ServiceResult:
        """Generic bulk status transition for ReprintRequest entries."""
        if target_status == 'confirmed':
            return cls.confirm_requests(table=table, rr_ids=rr_ids, user=user)

        if target_status not in cls.VALID_STATUSES:
            return ServiceResult(success=False, message=f'Invalid reprint status: {target_status}')

        rr_ids = cls._normalize_positive_int_ids(rr_ids)
        if not rr_ids:
            return ServiceResult(success=False, message='No reprint IDs provided')

        valid_from = [s for s, targets in cls.ALLOWED_TRANSITIONS.items() if target_status in targets]
        if not valid_from:
            return ServiceResult(success=False, message=f'No valid source status for {target_status}.')

        now = timezone.now()
        transition_rows = list(
            ReprintRequest.objects.filter(
                id__in=rr_ids,
                table=table,
                status__in=valid_from,
            ).values('id', 'card_id', 'status')
        )
        eligible_ids = [row['id'] for row in transition_rows]

        updated = ReprintRequest.objects.filter(
            id__in=eligible_ids,
            table=table,
            status__in=valid_from,
        ).update(status=target_status, updated_at=now)

        if not updated:
            return ServiceResult(
                success=False,
                message=f'No reprint requests eligible for transition to {target_status}.'
            )

        cls._bump_dashboard_cache_versions(table)
        ActivityService.log_reprint_summary(
            user=user,
            action='',
            count=updated,
            table=table,
            from_status=', '.join(set(row.get('status', '') for row in transition_rows)),
            to_status=target_status,
        )

        return ServiceResult(
            success=True,
            message=f'{updated} reprint(s) updated to {target_status}.',
            data={'updated_count': updated, 'updated_ids': eligible_ids}
        )

    # ── 5. Single Transition ──────────────────────────────────────────

    @classmethod
    def transition(
        cls,
        reprint_req: ReprintRequest,
        target_status: str,
        user=None,
    ) -> ServiceResult:
        """Transition a single ReprintRequest."""
        if target_status == 'confirmed':
            return cls.confirm_requests(table=reprint_req.table, rr_ids=[reprint_req.id], user=user)

        if target_status not in cls.VALID_STATUSES:
            return ServiceResult(success=False, message=f'Invalid reprint status: {target_status}')

        with transaction.atomic():
            try:
                reprint_req = ReprintRequest.objects.select_for_update().get(pk=reprint_req.pk)
            except ReprintRequest.DoesNotExist:
                return ServiceResult(success=False, message='Reprint request not found')

            current = reprint_req.status
            allowed = cls.ALLOWED_TRANSITIONS.get(current, [])
            if target_status not in allowed:
                return ServiceResult(
                    success=False,
                    message=f'Cannot change reprint status from {current} to {target_status}.'
                )

            reprint_req.status = target_status
            reprint_req.save(update_fields=['status', 'updated_at'])

        cls._bump_dashboard_cache_versions(reprint_req.table)
        return ServiceResult(
            success=True,
            message=f'Reprint request status changed to {target_status}.',
            data={'status': target_status}
        )

    # ── 6. Card Reprint History & Counters ────────────────────────────

    @classmethod
    def get_card_reprint_history(cls, card_id: int) -> List[Dict[str, Any]]:
        """Return chronological reprint history for a specific IDCard."""
        records = ReprintRequest.objects.filter(
            card_id=card_id
        ).select_related('requested_by', 'confirmed_by').order_by('-id')

        history = []
        for r in records:
            history.append({
                'id': r.id,
                'status': r.status,
                'status_display': r.get_status_display(),
                'reprint_number': r.reprint_number,
                'reason': r.reason,
                'changes': r.changes,
                'has_changes': r.has_changes,
                'requested_by': (r.requested_by.get_full_name() or r.requested_by.username) if r.requested_by else 'System',
                'confirmed_by': (r.confirmed_by.get_full_name() or r.confirmed_by.username) if r.confirmed_by else None,
                'requested_at': r.created_at.isoformat() if r.created_at else None,
                'confirmed_at': r.confirmed_at.isoformat() if r.confirmed_at else None,
            })
        return history
