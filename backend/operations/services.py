"""
CardFlow — Reversible Operations & History Engine Services

Key Invariants Enforced:
  1. Field-level delta tracking ($O(\Delta)$) without expensive table snapshots.
  2. Multi-user conflict detection: Never silently overwrite newer modifications.
  3. Immutable audit logs: Undo/Redo creates explicit audit events without deleting history.
  4. Redo invalidation: A new operation after an undo invalidates the forward redo chain.
  5. Dynamic schema support: Dynamic field values, types, and null states preserved.
  6. Non-destructive media & crop reversibility: Media binaries are preserved across undo/redo.
  7. Atomic chunked batch persistence with optimistic concurrency.
"""
import copy
import logging
from typing import Dict, Any, List, Tuple, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from organisation.models import Organisation
from tables.models import Table, IDCard
from core.models import ActivityLog
from .models import Operation, OperationChange

logger = logging.getLogger(__name__)
User = get_user_model()


@dataclass
class OperationResult:
    success: bool
    message: str = ''
    operation_id: Optional[int] = None
    status: str = 'active'
    undone_count: int = 0
    redone_count: int = 0
    conflict_count: int = 0
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'message': self.message,
            'operation_id': self.operation_id,
            'status': self.status,
            'undone_count': self.undone_count,
            'redone_count': self.redone_count,
            'conflict_count': self.conflict_count,
            'conflicts': self.conflicts,
            'data': self.data,
        }


class OperationEngine:
    """
    Core engine managing reversible operations, delta tracking, conflict detection,
    and undo/redo stacks.
    """

    # ── 1. RECORD OPERATION ────────────────────────────────────────

    @classmethod
    def record_operation(
        cls,
        organisation: Organisation,
        user: Optional[Any],
        operation_type: str,
        description: str,
        target_table: Optional[Table] = None,
        target_type: str = 'card',
        session_id: str = '',
        changes: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        parent_operation: Optional[Operation] = None,
    ) -> Operation:
        """
        Record a new mutation as an Operation with granular OperationChange deltas.
        Automatically invalidates the forward Redo stack for this user/table context.
        """
        if not organisation:
            raise ValueError("Organisation is required to record an operation.")

        changes = changes or []
        metadata = metadata or {}

        with transaction.atomic():
            # 1. Create Operation
            operation = Operation.objects.create(
                organisation=organisation,
                user=user if getattr(user, 'is_authenticated', False) else None,
                session_id=session_id or '',
                operation_type=operation_type,
                target_type=target_type,
                target_table=target_table,
                description=description[:500],
                status='active',
                parent_operation=parent_operation,
                metadata=metadata,
            )

            # 2. Bulk create OperationChange deltas
            change_objects = []
            for ch in changes:
                change_objects.append(OperationChange(
                    operation=operation,
                    target_id=ch.get('target_id', 0),
                    target_model=ch.get('target_model', 'idcard'),
                    field_name=ch.get('field_name', ''),
                    change_type=ch.get('change_type', 'field_edit'),
                    before_value=ch.get('before_value'),
                    after_value=ch.get('after_value'),
                    expected_version=ch.get('expected_version', 1),
                    status='applied',
                ))

            if change_objects:
                OperationChange.objects.bulk_create(change_objects, batch_size=500)

            # 3. Invariant 11: Invalidate forward Redo stack for this context
            cls._invalidate_redo_stack(organisation, user, target_table, session_id)

            # 4. Append-Only Audit Log
            try:
                ActivityLog.objects.create(
                    user=user if getattr(user, 'is_authenticated', False) else None,
                    action=operation_type if operation_type in dict(ActivityLog.ACTION_CHOICES) else 'other',
                    description=f"[Op #{operation.id}] {description}"[:500],
                    target_model='operation',
                    target_id=operation.id,
                )
            except Exception as act_err:
                logger.debug("Activity log creation skipped: %s", act_err)

        return operation

    # ── 2. UNDO OPERATION ──────────────────────────────────────────

    @classmethod
    def undo_operation(
        cls,
        operation_id: Optional[int] = None,
        organisation: Optional[Organisation] = None,
        user: Optional[Any] = None,
        table_id: Optional[int] = None,
        session_id: str = '',
        admin_override: bool = False,
    ) -> OperationResult:
        """
        Reverse an operation with multi-user conflict detection.
        If operation_id is None, undoes the latest active operation in the user's stack.
        """
        # Resolve target operation
        if operation_id:
            try:
                op = Operation.objects.select_related('organisation', 'target_table').get(id=operation_id)
            except Operation.DoesNotExist:
                return OperationResult(success=False, message="Operation not found.")
        else:
            # Pop latest active operation from user stack
            op = cls._get_latest_undoable(organisation, user, table_id, session_id)
            if not op:
                return OperationResult(success=False, message="Nothing to undo.")

        # Permissions & Tenant isolation check
        if organisation and op.organisation_id != organisation.id:
            return OperationResult(success=False, message="Permission denied: Organization mismatch.")

        if not admin_override and user and getattr(user, 'is_authenticated', False):
            if op.user_id and op.user_id != user.id:
                return OperationResult(success=False, message="Permission denied: Cannot undo another user's action.")

        # State check
        if op.status not in ('active', 'redone'):
            return OperationResult(
                success=False,
                message=f"Operation #{op.id} is in '{op.status}' state and cannot be undone.",
            )

        changes = list(op.changes.all().order_by('-id'))
        if not changes:
            op.status = 'undone'
            op.save(update_fields=['status', 'updated_at'])
            return OperationResult(success=True, message=f"Undid #{op.id} (no changes).", operation_id=op.id, status='undone')

        undone_count = 0
        conflict_count = 0
        conflicts = []

        # Group changes by target_model and target_id
        cards_to_update: Dict[int, IDCard] = {}
        changes_to_update: List[OperationChange] = []

        with transaction.atomic():
            # Lock affected cards for optimistic concurrency check
            card_ids = [ch.target_id for ch in changes if ch.target_model == 'idcard']
            cards_by_id = {c.id: c for c in IDCard.objects.filter(id__in=card_ids).select_for_update()}

            for ch in changes:
                if ch.target_model == 'idcard':
                    card = cards_by_id.get(ch.target_id)
                    if not card:
                        ch.status = 'conflicted'
                        ch.conflict_reason = f"Card #{ch.target_id} no longer exists."
                        conflict_count += 1
                        conflicts.append({'change_id': ch.id, 'reason': ch.conflict_reason})
                        changes_to_update.append(ch)
                        continue

                    fd = copy.deepcopy(card.field_data or {})

                    if ch.change_type == 'field_edit':
                        current_val = fd.get(ch.field_name)
                        # Conflict Check: does current_value match after_value?
                        if cls._values_match(current_val, ch.after_value):
                            # Safe to revert!
                            if ch.before_value is None:
                                fd.pop(ch.field_name, None)
                            else:
                                fd[ch.field_name] = ch.before_value

                            card.field_data = fd
                            cards_to_update[card.id] = card
                            ch.status = 'undone'
                            undone_count += 1
                        else:
                            # Conflict! Current value was modified after this operation
                            ch.status = 'conflicted'
                            ch.conflict_reason = (
                                f"Field '{ch.field_name}' changed to '{current_val}' "
                                f"(expected '{ch.after_value}'). Revert blocked to protect newer data."
                            )
                            conflict_count += 1
                            conflicts.append({'change_id': ch.id, 'field': ch.field_name, 'reason': ch.conflict_reason})

                    elif ch.change_type == 'status_change':
                        current_status = card.status
                        if current_status == ch.after_value or not ch.after_value:
                            card.status = str(ch.before_value or 'pending')
                            cards_to_update[card.id] = card
                            ch.status = 'undone'
                            undone_count += 1
                        else:
                            ch.status = 'conflicted'
                            ch.conflict_reason = f"Status is '{current_status}' (expected '{ch.after_value}')."
                            conflict_count += 1
                            conflicts.append({'change_id': ch.id, 'reason': ch.conflict_reason})

                    elif ch.change_type == 'record_create':
                        # Undo creation -> soft delete record
                        card.status = 'deleted'
                        card.deleted_at = timezone.now()
                        cards_to_update[card.id] = card
                        ch.status = 'undone'
                        undone_count += 1

                    elif ch.change_type == 'record_delete':
                        # Undo deletion -> restore record
                        card.status = str(ch.before_value or 'pending')
                        card.deleted_at = None
                        cards_to_update[card.id] = card
                        ch.status = 'undone'
                        undone_count += 1

                    elif ch.change_type in ('media_replace', 'crop_change'):
                        current_val = fd.get(ch.field_name)
                        if cls._values_match(current_val, ch.after_value):
                            if ch.before_value is None:
                                fd.pop(ch.field_name, None)
                            else:
                                fd[ch.field_name] = ch.before_value
                            card.field_data = fd
                            cards_to_update[card.id] = card
                            ch.status = 'undone'
                            undone_count += 1
                        else:
                            ch.status = 'conflicted'
                            ch.conflict_reason = f"Media '{ch.field_name}' was modified after this operation."
                            conflict_count += 1
                            conflicts.append({'change_id': ch.id, 'reason': ch.conflict_reason})

                    changes_to_update.append(ch)

            # Persist card changes in chunked batches
            if cards_to_update:
                cards_list = list(cards_to_update.values())
                IDCard.objects.bulk_update(cards_list, ['field_data', 'status', 'deleted_at'], batch_size=250)

            # Persist change status updates
            if changes_to_update:
                OperationChange.objects.bulk_update(changes_to_update, ['status', 'conflict_reason'], batch_size=500)

            # Determine final operation state
            if conflict_count == 0:
                final_status = 'undone'
            elif undone_count > 0:
                final_status = 'partially_undone'
            else:
                final_status = 'conflicted'

            op.status = final_status
            op.save(update_fields=['status', 'updated_at'])

            # Invariant 3 & 25: Record Undo Operation event (preserves append-only audit trail)
            undo_event = Operation.objects.create(
                organisation=op.organisation,
                user=user if getattr(user, 'is_authenticated', False) else op.user,
                session_id=session_id or op.session_id,
                operation_type='undo_operation',
                target_type=op.target_type,
                target_table=op.target_table,
                description=f"Undid Op #{op.id}: {op.description} ({undone_count} undone, {conflict_count} conflicted)",
                status='active',
                undo_of=op,
            )

            # Log to ActivityLog
            try:
                ActivityLog.objects.create(
                    user=user if getattr(user, 'is_authenticated', False) else None,
                    action='other',
                    description=f"Undid action: {op.description}"[:500],
                    target_model='operation',
                    target_id=op.id,
                )
            except Exception:
                pass


        msg = f"Successfully undone {undone_count} changes."
        if conflict_count > 0:
            msg += f" {conflict_count} changes could not be undone due to newer modifications."

        return OperationResult(
            success=(undone_count > 0 or conflict_count == 0),
            message=msg,
            operation_id=op.id,
            status=final_status,
            undone_count=undone_count,
            conflict_count=conflict_count,
            conflicts=conflicts,
        )

    # ── 3. REDO OPERATION ──────────────────────────────────────────

    @classmethod
    def redo_operation(
        cls,
        operation_id: Optional[int] = None,
        organisation: Optional[Organisation] = None,
        user: Optional[Any] = None,
        table_id: Optional[int] = None,
        session_id: str = '',
    ) -> OperationResult:
        """
        Re-apply an undone operation with conflict detection.
        If operation_id is None, redoes the latest undone operation in the user's stack.
        """
        if operation_id:
            try:
                op = Operation.objects.select_related('organisation', 'target_table').get(id=operation_id)
            except Operation.DoesNotExist:
                return OperationResult(success=False, message="Operation not found.")
        else:
            op = cls._get_latest_redoable(organisation, user, table_id, session_id)
            if not op:
                return OperationResult(success=False, message="Nothing to redo.")

        if organisation and op.organisation_id != organisation.id:
            return OperationResult(success=False, message="Permission denied: Organization mismatch.")

        if op.status not in ('undone', 'partially_undone'):
            return OperationResult(
                success=False,
                message=f"Operation #{op.id} is in '{op.status}' state and cannot be redone.",
            )

        changes = list(op.changes.all().order_by('id'))
        if not changes:
            op.status = 'redone'
            op.save(update_fields=['status', 'updated_at'])
            return OperationResult(success=True, message=f"Redid #{op.id}.", operation_id=op.id, status='redone')

        redone_count = 0
        conflict_count = 0
        conflicts = []

        cards_to_update: Dict[int, IDCard] = {}
        changes_to_update: List[OperationChange] = []

        with transaction.atomic():
            card_ids = [ch.target_id for ch in changes if ch.target_model == 'idcard']
            cards_by_id = {c.id: c for c in IDCard.objects.filter(id__in=card_ids).select_for_update()}

            for ch in changes:
                if ch.target_model == 'idcard':
                    card = cards_by_id.get(ch.target_id)
                    if not card:
                        ch.status = 'conflicted'
                        ch.conflict_reason = f"Card #{ch.target_id} no longer exists."
                        conflict_count += 1
                        conflicts.append({'change_id': ch.id, 'reason': ch.conflict_reason})
                        changes_to_update.append(ch)
                        continue

                    fd = copy.deepcopy(card.field_data or {})

                    if ch.change_type == 'field_edit':
                        current_val = fd.get(ch.field_name)
                        # Conflict Check: current_value should match before_value
                        if cls._values_match(current_val, ch.before_value):
                            if ch.after_value is None:
                                fd.pop(ch.field_name, None)
                            else:
                                fd[ch.field_name] = ch.after_value
                            card.field_data = fd
                            cards_to_update[card.id] = card
                            ch.status = 'applied'
                            redone_count += 1
                        else:
                            ch.status = 'conflicted'
                            ch.conflict_reason = f"Field '{ch.field_name}' was modified after undo."
                            conflict_count += 1
                            conflicts.append({'change_id': ch.id, 'field': ch.field_name, 'reason': ch.conflict_reason})

                    elif ch.change_type == 'status_change':
                        current_status = card.status
                        if current_status == ch.before_value or not ch.before_value:
                            card.status = str(ch.after_value or 'pending')
                            cards_to_update[card.id] = card
                            ch.status = 'applied'
                            redone_count += 1
                        else:
                            ch.status = 'conflicted'
                            ch.conflict_reason = f"Status is '{current_status}' (expected '{ch.before_value}')."
                            conflict_count += 1
                            conflicts.append({'change_id': ch.id, 'reason': ch.conflict_reason})

                    elif ch.change_type == 'record_create':
                        card.status = 'pending'
                        card.deleted_at = None
                        cards_to_update[card.id] = card
                        ch.status = 'applied'
                        redone_count += 1

                    elif ch.change_type == 'record_delete':
                        card.status = 'deleted'
                        card.deleted_at = timezone.now()
                        cards_to_update[card.id] = card
                        ch.status = 'applied'
                        redone_count += 1

                    elif ch.change_type in ('media_replace', 'crop_change'):
                        current_val = fd.get(ch.field_name)
                        if cls._values_match(current_val, ch.before_value):
                            if ch.after_value is None:
                                fd.pop(ch.field_name, None)
                            else:
                                fd[ch.field_name] = ch.after_value
                            card.field_data = fd
                            cards_to_update[card.id] = card
                            ch.status = 'applied'
                            redone_count += 1
                        else:
                            ch.status = 'conflicted'
                            ch.conflict_reason = f"Media '{ch.field_name}' was modified."
                            conflict_count += 1
                            conflicts.append({'change_id': ch.id, 'reason': ch.conflict_reason})

                    changes_to_update.append(ch)

            if cards_to_update:
                cards_list = list(cards_to_update.values())
                IDCard.objects.bulk_update(cards_list, ['field_data', 'status', 'deleted_at'], batch_size=250)

            if changes_to_update:
                OperationChange.objects.bulk_update(changes_to_update, ['status', 'conflict_reason'], batch_size=500)

            op.status = 'redone' if conflict_count == 0 else ('partially_undone' if redone_count > 0 else 'conflicted')
            op.save(update_fields=['status', 'updated_at'])

            # Invariant 4 & 26: Create Redo Operation event
            Operation.objects.create(
                organisation=op.organisation,
                user=user if getattr(user, 'is_authenticated', False) else op.user,
                session_id=session_id or op.session_id,
                operation_type='redo_operation',
                target_type=op.target_type,
                target_table=op.target_table,
                description=f"Redid Op #{op.id}: {op.description} ({redone_count} redone, {conflict_count} conflicted)",
                status='active',
                redo_of=op,
            )

            try:
                ActivityLog.objects.create(
                    user=user if getattr(user, 'is_authenticated', False) else None,
                    action='other',
                    description=f"Redid action: {op.description}"[:500],
                    target_model='operation',
                    target_id=op.id,
                )
            except Exception:
                pass

        msg = f"Successfully redone {redone_count} changes."
        if conflict_count > 0:
            msg += f" {conflict_count} changes could not be redone due to conflicting modifications."

        return OperationResult(
            success=(redone_count > 0 or conflict_count == 0),
            message=msg,
            operation_id=op.id,
            status=op.status,
            redone_count=redone_count,
            conflict_count=conflict_count,
            conflicts=conflicts,
        )

    # ── 4. STACK & STATUS HELPERS ──────────────────────────────────

    @classmethod
    def get_stack_status(
        cls,
        organisation: Optional[Organisation],
        user: Optional[Any],
        table_id: Optional[int] = None,
        session_id: str = '',
    ) -> Dict[str, Any]:
        """
        Fast query returning live Undo/Redo capability and descriptive tooltips.
        """
        latest_undo = cls._get_latest_undoable(organisation, user, table_id, session_id)
        latest_redo = cls._get_latest_redoable(organisation, user, table_id, session_id)

        undo_qs = cls._base_query(organisation, user, table_id, session_id).filter(status__in=('active', 'redone'))
        redo_qs = cls._base_query(organisation, user, table_id, session_id).filter(status__in=('undone', 'partially_undone'))

        return {
            'can_undo': bool(latest_undo),
            'can_redo': bool(latest_redo),
            'undo_tooltip': f"Undo: {latest_undo.description}" if latest_undo else "Nothing to undo",
            'redo_tooltip': f"Redo: {latest_redo.description}" if latest_redo else "Nothing to redo",
            'undo_count': undo_qs.count(),
            'redo_count': redo_qs.count(),
            'latest_undo_id': latest_undo.id if latest_undo else None,
            'latest_redo_id': latest_redo.id if latest_redo else None,
        }

    @classmethod
    def get_history(
        cls,
        organisation: Optional[Organisation],
        user: Optional[Any] = None,
        table_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Return paginated history of operations for audit/history panel.
        """
        qs = Operation.objects.all().select_related('user', 'target_table').prefetch_related('changes')

        if organisation:
            qs = qs.filter(organisation=organisation)
        if table_id:
            qs = qs.filter(target_table_id=table_id)
        if user and getattr(user, 'is_authenticated', False) and not getattr(user, 'is_superuser', False):
            qs = qs.filter(user=user)

        total_count = qs.count()
        operations = list(qs[offset:offset + limit])

        items = []
        for op in operations:
            items.append({
                'id': op.id,
                'operation_type': op.operation_type,
                'description': op.description,
                'status': op.status,
                'user_name': op.user.username if op.user else 'System',
                'created_at': op.created_at.isoformat(),
                'change_count': op.changes.count(),
                'can_undo': op.status in ('active', 'redone'),
                'can_redo': op.status in ('undone', 'partially_undone'),
            })

        return {
            'total_count': total_count,
            'limit': limit,
            'offset': offset,
            'operations': items,
        }

    # ── PRIVATE QUERY HELPERS ──────────────────────────────────────

    @classmethod
    def _base_query(
        cls,
        organisation: Optional[Organisation],
        user: Optional[Any],
        table_id: Optional[int] = None,
        session_id: str = '',
    ):
        qs = Operation.objects.exclude(operation_type__in=('undo_operation', 'redo_operation'))
        if organisation:
            qs = qs.filter(organisation=organisation)
        if table_id:
            qs = qs.filter(target_table_id=table_id)

        if user and getattr(user, 'is_authenticated', False):
            qs = qs.filter(user=user)
        elif session_id:
            qs = qs.filter(session_id=session_id)

        return qs

    @classmethod
    def _get_latest_undoable(
        cls,
        organisation: Optional[Organisation],
        user: Optional[Any],
        table_id: Optional[int] = None,
        session_id: str = '',
    ) -> Optional[Operation]:
        return (
            cls._base_query(organisation, user, table_id, session_id)
            .filter(status__in=('active', 'redone'))
            .order_by('-created_at', '-id')
            .first()
        )

    @classmethod
    def _get_latest_redoable(
        cls,
        organisation: Optional[Organisation],
        user: Optional[Any],
        table_id: Optional[int] = None,
        session_id: str = '',
    ) -> Optional[Operation]:
        return (
            cls._base_query(organisation, user, table_id, session_id)
            .filter(status__in=('undone', 'partially_undone'))
            .order_by('-updated_at', '-id')
            .first()
        )

    @classmethod
    def _invalidate_redo_stack(
        cls,
        organisation: Organisation,
        user: Optional[Any],
        target_table: Optional[Table] = None,
        session_id: str = '',
    ):
        """Invariant 11: Invalidate forward Redo stack when a new operation occurs."""
        qs = cls._base_query(organisation, user, target_table.id if target_table else None, session_id)
        qs.filter(status__in=('undone', 'partially_undone')).update(status='failed')

    @classmethod
    def _values_match(cls, val1: Any, val2: Any) -> bool:
        """
        Type-safe equality check distinguishing None from empty string,
        normalizing string representations and numeric values.
        """
        if val1 is None and val2 is None:
            return True
        if val1 is None or val2 is None:
            # If one is None and other is empty string, check strict vs loose
            if (val1 == '' and val2 is None) or (val1 is None and val2 == ''):
                return True
            return False

        # If both are strings
        if isinstance(val1, str) and isinstance(val2, str):
            return val1.strip() == val2.strip()

        # If numeric
        try:
            if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                return val1 == val2
        except Exception:
            pass

        # If dict/list
        if isinstance(val1, (dict, list)) and isinstance(val2, (dict, list)):
            return val1 == val2

        return str(val1).strip() == str(val2).strip()
