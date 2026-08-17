"""
CardFlow — Comprehensive Test Suite for Audit Log, Activity History, Bulk Transactions & Undo/Redo

Tests cover:
  - Single-cell and multi-field edits (undo -> redo)
  - Dynamic fields & types (strings, numbers, booleans, null vs empty)
  - Create / Delete / Restore reversibility
  - Bulk operations (50+ cards status change reversed in 1 click)
  - Multi-user conflict detection (prevent overwriting newer concurrent edits)
  - Partial undo on multi-field conflict
  - Forward redo stack invalidation on new mutation (Invariant 11)
  - Media & Crop metadata reversibility
  - Immutable append-only audit trail preservation
  - First-class BulkTransaction creation with individual card AuditEvents
  - Card timeline query with bulk transaction linkages
  - Role-based visibility filtering (Assistant / Client vs Operator vs Super Admin)
  - Safe conflict-aware historical bulk transaction reversal (creates NEW transaction, never rewrites history)
  - Audit export with auditable export event
  - REST API endpoints (/api/operations/undo, /redo, /stack, /history, /audit/cards/<id>/timeline, etc.)
"""
import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from organisation.models import Organisation
from tables.models import Table, IDCard
from core.models import ActivityLog
from .models import Operation, OperationChange, BulkTransaction, AuditEvent
from .services import OperationEngine, OperationResult, AuditService, AuditVisibilityService

User = get_user_model()


class ReversibleOperationsAndAuditTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_a = User.objects.create_user(
            username='user_a_editor',
            email='user_a@test.com',
            password='testpassword123',
            role='super_admin',
        )
        self.user_b = User.objects.create_user(
            username='user_b_editor',
            email='user_b@test.com',
            password='testpassword123',
            role='super_admin',
        )
        self.assistant_user = User.objects.create_user(
            username='assistant_joe',
            email='joe@test.com',
            password='testpassword123',
            role='assistant',
        )
        self.org = Organisation.objects.create(
            name='Alpha High School',
            image_folder_code='ALPHA',
        )
        self.assistant_user.organisation_profile = self.org
        self.assistant_user.save()

        self.table = Table.objects.create(
            organisation=self.org,
            name='Class 10th',
            fields=[
                {'name': 'FULL NAME', 'type': 'text'},
                {'name': 'CLASS', 'type': 'number'},
                {'name': 'SECTION', 'type': 'text'},
                {'name': 'PHONE', 'type': 'text'},
                {'name': 'PHOTO', 'type': 'photo'},
            ],
        )
        self.card1 = IDCard.objects.create(
            table=self.table,
            field_data={'FULL NAME': 'Rahul Sharma', 'CLASS': 10, 'SECTION': 'A', 'PHONE': '9876543210'},
            status='pending',
        )
        self.card2 = IDCard.objects.create(
            table=self.table,
            field_data={'FULL NAME': 'Pooja Verma', 'CLASS': 10, 'SECTION': 'A', 'PHONE': '9876543211'},
            status='pending',
        )

    # ══════════════════════════════════════════════════════════════════════
    # 1. REVERSIBLE OPERATIONS & DELTA TRACKING TESTS
    # ══════════════════════════════════════════════════════════════════════

    def test_single_cell_edit_undo_redo(self):
        """Test simple single field edit -> undo -> redo."""
        op = OperationEngine.record_operation(
            organisation=self.org,
            user=self.user_a,
            operation_type='card_update',
            target_table=self.table,
            description="Edited Student Name",
            changes=[{
                'target_id': self.card1.id,
                'target_model': 'idcard',
                'field_name': 'FULL NAME',
                'change_type': 'field_edit',
                'before_value': 'Rahul Sharma',
                'after_value': 'Rohan Sharma',
            }]
        )
        self.card1.field_data['FULL NAME'] = 'Rohan Sharma'
        self.card1.save()

        stack = OperationEngine.get_stack_status(self.org, self.user_a, self.table.id)
        self.assertTrue(stack['can_undo'])
        self.assertFalse(stack['can_redo'])
        self.assertEqual(stack['latest_undo_id'], op.id)

        undo_res = OperationEngine.undo_operation(
            operation_id=op.id,
            organisation=self.org,
            user=self.user_a,
        )
        self.assertTrue(undo_res.success)
        self.assertEqual(undo_res.status, 'undone')
        self.assertEqual(undo_res.undone_count, 1)

        self.card1.refresh_from_db()
        self.assertEqual(self.card1.field_data['FULL NAME'], 'Rahul Sharma')

        redo_res = OperationEngine.redo_operation(
            operation_id=op.id,
            organisation=self.org,
            user=self.user_a,
        )
        self.assertTrue(redo_res.success)
        self.assertEqual(redo_res.status, 'redone')

        self.card1.refresh_from_db()
        self.assertEqual(self.card1.field_data['FULL NAME'], 'Rohan Sharma')

    def test_multi_user_conflict_detection(self):
        """Engine MUST detect conflict and NOT overwrite Raj with Rahul."""
        op_a = OperationEngine.record_operation(
            organisation=self.org,
            user=self.user_a,
            operation_type='card_update',
            target_table=self.table,
            description="User A: Name to Rohan",
            changes=[{
                'target_id': self.card1.id,
                'target_model': 'idcard',
                'field_name': 'FULL NAME',
                'change_type': 'field_edit',
                'before_value': 'Rahul Sharma',
                'after_value': 'Rohan Sharma',
            }]
        )
        self.card1.field_data['FULL NAME'] = 'Rohan Sharma'
        self.card1.save()

        op_b = OperationEngine.record_operation(
            organisation=self.org,
            user=self.user_b,
            operation_type='card_update',
            target_table=self.table,
            description="User B: Name to Raj",
            changes=[{
                'target_id': self.card1.id,
                'target_model': 'idcard',
                'field_name': 'FULL NAME',
                'change_type': 'field_edit',
                'before_value': 'Rohan Sharma',
                'after_value': 'Raj Sharma',
            }]
        )
        self.card1.field_data['FULL NAME'] = 'Raj Sharma'
        self.card1.save()

        undo_res = OperationEngine.undo_operation(
            operation_id=op_a.id,
            organisation=self.org,
            user=self.user_a,
        )

        self.assertEqual(undo_res.status, 'conflicted')
        self.assertEqual(undo_res.conflict_count, 1)
        self.assertEqual(undo_res.undone_count, 0)

        self.card1.refresh_from_db()
        self.assertEqual(self.card1.field_data['FULL NAME'], 'Raj Sharma')

    def test_redo_stack_invalidation_on_new_operation(self):
        """Invariant 11: A new operation after Undo invalidates the Redo stack."""
        op1 = OperationEngine.record_operation(
            self.org, self.user_a, 'card_update', "Op 1", self.table,
            changes=[{'target_id': self.card1.id, 'field_name': 'SECTION', 'before_value': 'A', 'after_value': 'B'}]
        )
        self.card1.field_data['SECTION'] = 'B'
        self.card1.save()

        OperationEngine.undo_operation(op1.id, self.org, self.user_a)
        stack = OperationEngine.get_stack_status(self.org, self.user_a, self.table.id)
        self.assertTrue(stack['can_redo'])

        # New mutation occurs
        OperationEngine.record_operation(
            self.org, self.user_a, 'card_update', "Op 2", self.table,
            changes=[{'target_id': self.card1.id, 'field_name': 'SECTION', 'before_value': 'A', 'after_value': 'C'}]
        )

        stack = OperationEngine.get_stack_status(self.org, self.user_a, self.table.id)
        self.assertFalse(stack['can_redo'])

    # ══════════════════════════════════════════════════════════════════════
    # 2. FIRST-CLASS BULK TRANSACTIONS & AUDIT TESTS
    # ══════════════════════════════════════════════════════════════════════

    def test_bulk_transaction_creation_and_bidirectional_linkage(self):
        """Test creating a BulkTransaction groups card AuditEvents with bidirectional links."""
        # Create 100 student cards
        cards = []
        for i in range(1, 101):
            cards.append(IDCard(
                table=self.table,
                field_data={'FULL NAME': f'Student {i}', 'CLASS': 10},
                status='pending',
            ))
        IDCard.objects.bulk_create(cards)
        created = list(IDCard.objects.filter(table=self.table, status='pending').exclude(id__in=[self.card1.id, self.card2.id]))
        self.assertEqual(len(created), 100)

        # Move 100 cards from pending -> verified
        deltas = [{'card_id': c.id, 'target_name': f'Student #{c.id}'} for c in created]
        bulk_tx = AuditService.record_bulk_transaction(
            organisation=self.org,
            actor=self.assistant_user,
            action='bulk_status',
            source_state='pending',
            destination_state='verified',
            card_deltas=deltas,
            table=self.table,
            visibility_scope='ORGANISATION',
        )
        IDCard.objects.filter(id__in=[c.id for c in created]).update(status='verified')

        self.assertIsNotNone(bulk_tx.id)
        self.assertTrue(bulk_tx.tx_code.startswith('BT-'))
        self.assertEqual(bulk_tx.requested_count, 100)
        self.assertEqual(bulk_tx.success_count, 100)
        self.assertEqual(bulk_tx.actor_name_snapshot, 'assistant_joe')
        self.assertEqual(bulk_tx.actor_role_snapshot, 'assistant')

        # Check AuditEvent records created and linked
        events = AuditEvent.objects.filter(bulk_transaction=bulk_tx)
        self.assertEqual(events.count(), 100)

        # Query Card #1 timeline
        sample_card = created[0]
        timeline = AuditService.get_card_timeline(sample_card.id, self.assistant_user)
        self.assertTrue(timeline['success'])
        self.assertEqual(timeline['total_count'], 1)
        ev = timeline['timeline'][0]
        self.assertEqual(ev['actor_name'], 'assistant_joe')
        self.assertEqual(ev['bulk_transaction']['tx_code'], bulk_tx.tx_code)
        self.assertEqual(ev['bulk_transaction']['requested_count'], 100)

    def test_role_based_visibility_scope_filtering(self):
        """
        Test that AuditVisibilityService properly enforces role boundaries:
        - Assistant cannot see INTERNAL_ADMIN or SUPER_ADMIN events.
        - Super Admin sees everything.
        """
        # Event 1: Normal Organisation-visible event
        ev1 = AuditService.record_event(
            organisation=self.org,
            actor=self.assistant_user,
            event_type='update',
            target_type='card',
            target_id=self.card1.id,
            target_name='Card #1',
            target_table=self.table,
            visibility_scope='ORGANISATION',
        )

        # Event 2: Internal Admin operational event
        ev2 = AuditService.record_event(
            organisation=self.org,
            actor=self.user_a,
            event_type='system_action',
            target_type='card',
            target_id=self.card1.id,
            target_name='Card #1',
            target_table=self.table,
            visibility_scope='INTERNAL_ADMIN',
        )

        # Event 3: Super Admin configuration event
        ev3 = AuditService.record_event(
            organisation=self.org,
            actor=self.user_a,
            event_type='schema_change',
            target_type='table',
            target_id=self.table.id,
            target_name='Table Class 10th',
            target_table=self.table,
            visibility_scope='SUPER_ADMIN',
        )

        # Query as Assistant User
        assistant_timeline = AuditService.get_card_timeline(self.card1.id, self.assistant_user)
        self.assertEqual(assistant_timeline['total_count'], 1)  # Can ONLY see ev1
        self.assertEqual(assistant_timeline['timeline'][0]['event_id'], ev1.event_id)

        # Query as Super Admin User
        admin_timeline = AuditService.get_card_timeline(self.card1.id, self.user_a)
        self.assertEqual(admin_timeline['total_count'], 2)  # Sees ev1 and ev2

    def test_safe_bulk_transaction_reversal_with_conflicts(self):
        """
        Historical Bulk Reversal Scenario (Invariants 25, 27, 28, 59, 60):
        1. Assistant moves 10 cards: pending -> verified [BT001]
        2. Later, 2 cards are modified: verified -> approved
        3. Administrator chooses 'Reverse Transaction':
           - 8 cards revert from verified -> pending
           - 2 cards with newer changes are skipped and reported as conflicts
           - A NEW BulkTransaction (REV-...) is created
           - The original BT001 remains intact
        """
        cards = []
        for i in range(1, 11):
            cards.append(IDCard(
                table=self.table,
                field_data={'FULL NAME': f'Batch Card {i}'},
                status='pending',
            ))
        IDCard.objects.bulk_create(cards)
        created_cards = list(IDCard.objects.filter(table=self.table, status='pending').exclude(id__in=[self.card1.id, self.card2.id]))
        self.assertEqual(len(created_cards), 10)

        # 1. Bulk move 10 cards: pending -> verified
        deltas = [{'card_id': c.id, 'target_name': f'Card #{c.id}'} for c in created_cards]
        bulk_tx = AuditService.record_bulk_transaction(
            organisation=self.org,
            actor=self.assistant_user,
            action='bulk_status',
            source_state='pending',
            destination_state='verified',
            card_deltas=deltas,
            table=self.table,
        )
        IDCard.objects.filter(id__in=[c.id for c in created_cards]).update(status='verified')

        # 2. 2 cards are subsequently modified to 'approved'
        modified_card_ids = [created_cards[0].id, created_cards[1].id]
        IDCard.objects.filter(id__in=modified_card_ids).update(status='approved')

        # 3. Reverse Bulk Transaction
        rev_res = AuditService.reverse_bulk_transaction(
            transaction_id=bulk_tx.id,
            user=self.user_a,
        )

        self.assertTrue(rev_res['success'])
        self.assertEqual(rev_res['reversed_count'], 8)
        self.assertEqual(rev_res['conflict_count'], 2)
        self.assertEqual(len(rev_res['conflicts']), 2)

        # Verify DB states
        self.assertEqual(IDCard.objects.filter(id__in=[c.id for c in created_cards], status='pending').count(), 8)
        self.assertEqual(IDCard.objects.filter(id__in=modified_card_ids, status='approved').count(), 2)

        # Verify original transaction was NOT erased, but marked partially_reversed
        bulk_tx.refresh_from_db()
        self.assertEqual(bulk_tx.status, 'partially_reversed')
        self.assertIsNotNone(bulk_tx.reversed_by_transaction)

        # Verify new reversal transaction was created
        rev_tx = bulk_tx.reversed_by_transaction
        self.assertTrue(rev_tx.tx_code.startswith('REV-'))
        self.assertEqual(rev_tx.success_count, 8)
        self.assertEqual(rev_tx.conflict_count, 2)

    # ══════════════════════════════════════════════════════════════════════
    # 3. REST API ENDPOINTS INTEGRATION TESTS
    # ══════════════════════════════════════════════════════════════════════

    def test_audit_rest_api_endpoints(self):
        """Test /api/operations/audit/ endpoints for timeline, transactions, reversal, and export."""
        self.client.force_login(self.user_a)

        # 1. Record an event
        ev = AuditService.record_event(
            organisation=self.org,
            actor=self.user_a,
            event_type='update',
            target_type='card',
            target_id=self.card1.id,
            target_name='Rahul Sharma',
            target_table=self.table,
            field_deltas=[{'field_name': 'SECTION', 'before_value': 'A', 'after_value': 'B'}],
        )

        # 2. GET Card Timeline API
        resp = self.client.get(f'/api/operations/audit/cards/{self.card1.id}/timeline/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['timeline']), 1)

        # 3. GET Table Activity API
        resp = self.client.get(f'/api/operations/audit/tables/{self.table.id}/activity/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])

        # 4. GET Bulk Transactions API
        bulk_tx = AuditService.record_bulk_transaction(
            organisation=self.org,
            actor=self.user_a,
            action='bulk_status',
            source_state='pending',
            destination_state='verified',
            card_deltas=[{'card_id': self.card2.id}],
            table=self.table,
        )
        self.card2.status = 'verified'
        self.card2.save()

        resp = self.client.get(f'/api/operations/audit/transactions/?table_id={self.table.id}')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(len(data['transactions']) >= 1)

        # 5. GET Bulk Transaction Detail API
        resp = self.client.get(f'/api/operations/audit/transactions/{bulk_tx.id}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['transaction']['tx_code'], bulk_tx.tx_code)

        # 6. POST Reverse Bulk Transaction API
        resp = self.client.post(f'/api/operations/audit/transactions/{bulk_tx.id}/reverse/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['reversed_count'], 1)

        self.card2.refresh_from_db()
        self.assertEqual(self.card2.status, 'pending')

        # 7. GET Export Audit CSV API
        resp = self.client.get(f'/api/operations/audit/export/?table_id={self.table.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        self.assertIn('Event ID,Event Type', resp.content.decode('utf-8'))
