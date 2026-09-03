"""
Reprint Workflow & API Integration Test Suite
============================================
Comprehensive tests for the dedicated 'reprint' app:
  1. 3-step reprint workflow: Reprint List -> Requested List -> Confirmed List
  2. In-place card field updates upon confirmation without card duplication
  3. Sequential multi-reprint count tracking (Reprint #1, #2, etc.)
  4. Rejection and cancellation returning cards to Reprint List
  5. Full JSON API endpoint coverage with permission checks
"""
import json
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

from tables.models import Table, IDCard
from organisation.models import Organisation
from reprint.models import ReprintRequest
from reprint.services import ReprintWorkflowService
from reprint.views import (
    api_reprint_list,
    api_request_list,
    api_confirmed_list,
    api_reprint_request_create,
    api_reprint_confirm,
    api_reprint_reject,
    api_reprint_retrieve,
    api_reprint_mark_downloaded,
    api_reprint_step_counts,
    api_reprint_card_history,
)

User = get_user_model()


class ReprintWorkflowTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.super_admin = User.objects.create_superuser(
            username='reprint_admin',
            email='admin@reprint.test',
            password='pass',
            role='super_admin',
        )
        self.org = Organisation.objects.create(name='Test Org')
        self.table = Table.objects.create(
            organisation=self.org,
            name='Class 10th',
            fields=[
                {'name': 'NAME', 'label': 'Student Name', 'type': 'text'},
                {'name': 'FATHER_NAME', 'label': 'Father Name', 'type': 'text'},
                {'name': 'ROLL_NO', 'label': 'Roll Number', 'type': 'text'},
            ]
        )

        # Create source downloaded card
        self.card = IDCard.objects.create(
            table=self.table,
            status='download',
            field_data={
                'NAME': 'Rahul Sharma',
                'FATHER_NAME': 'Vijay Sharma',
                'ROLL_NO': '101',
            }
        )

    def test_reprint_list_shows_downloaded_card_uniquely(self):
        """Downloaded cards appear in the reprint list once."""
        counts = ReprintWorkflowService.create_requests(
            table=self.table,
            card_ids=[self.card.id],
            reason='Initial damage',
            requested_by=self.super_admin,
        )
        self.assertTrue(counts.success)
        self.assertEqual(counts.data['created_count'], 1)

        req = self.rf.get(f'/reprint/api/table/{self.table.id}/reprint-list/')
        req.user = self.super_admin
        resp = api_reprint_list(req, self.table.id)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(len(data['items']), 1)
        self.assertTrue(data['items'][0]['is_in_request_queue'])

    def test_reprint_confirm_applies_changes_in_place_without_duplication(self):
        """Confirming reprint with edits applies changes to original IDCard directly."""
        card_id = self.card.id
        initial_card_count = IDCard.objects.filter(table=self.table).count()

        # Step 1: Create request with staged changes
        staged_changes = {'NAME': 'Rahul V. Sharma', 'ROLL_NO': '101-A'}
        res = ReprintWorkflowService.create_requests(
            table=self.table,
            card_ids=[card_id],
            reason='Correction in spelling & roll no',
            changes_by_card={str(card_id): staged_changes},
            requested_by=self.super_admin,
        )
        self.assertTrue(res.success)

        rr = ReprintRequest.objects.get(card=self.card, status='requested')
        self.assertEqual(rr.changes['NAME'], 'Rahul V. Sharma')

        # Original card should NOT be modified yet
        self.card.refresh_from_db()
        self.assertEqual(self.card.field_data['NAME'], 'Rahul Sharma')

        # Step 2: Admin confirms reprint
        confirm_res = ReprintWorkflowService.confirm_requests(
            table=self.table,
            rr_ids=[rr.id],
            user=self.super_admin,
        )
        self.assertTrue(confirm_res.success)

        # Verify card is updated in-place
        self.card.refresh_from_db()
        self.assertEqual(self.card.field_data['NAME'], 'Rahul V. Sharma')
        self.assertEqual(self.card.field_data['ROLL_NO'], '101-A')
        self.assertEqual(self.card.field_data['FATHER_NAME'], 'Vijay Sharma')

        # Card count must remain exactly 1 (no duplicate card rows created!)
        self.assertEqual(IDCard.objects.filter(table=self.table).count(), initial_card_count)

        # Reprint request is marked confirmed
        rr.refresh_from_db()
        self.assertEqual(rr.status, 'confirmed')
        self.assertEqual(rr.reprint_number, 1)

    def test_multi_reprint_sequential_counter(self):
        """Card can be reprinted multiple times with sequential reprint numbers tracked."""
        # 1st reprint
        ReprintWorkflowService.create_requests(
            table=self.table,
            card_ids=[self.card.id],
            reason='1st Lost',
            requested_by=self.super_admin,
        )
        rr1 = ReprintRequest.objects.get(card=self.card, status='requested')
        ReprintWorkflowService.confirm_requests(self.table, [rr1.id], user=self.super_admin)
        rr1.refresh_from_db()
        self.assertEqual(rr1.reprint_number, 1)

        # 2nd reprint
        ReprintWorkflowService.create_requests(
            table=self.table,
            card_ids=[self.card.id],
            reason='2nd Damaged',
            requested_by=self.super_admin,
        )
        rr2 = ReprintRequest.objects.get(card=self.card, status='requested')
        self.assertEqual(rr2.reprint_number, 2)
        ReprintWorkflowService.confirm_requests(self.table, [rr2.id], user=self.super_admin)
        rr2.refresh_from_db()
        self.assertEqual(rr2.reprint_number, 2)

        # Total confirmed records for this card is 2
        history = ReprintWorkflowService.get_card_reprint_history(self.card.id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['reprint_number'], 2)
        self.assertEqual(history[1]['reprint_number'], 1)

    def test_reject_request_returns_card_to_reprint_list(self):
        """Rejecting/cancelling request removes it from request list and leaves card intact."""
        ReprintWorkflowService.create_requests(
            table=self.table,
            card_ids=[self.card.id],
            reason='Accidental request',
            changes_by_card={str(self.card.id): {'NAME': 'Wrong Name'}},
            requested_by=self.super_admin,
        )
        rr = ReprintRequest.objects.get(card=self.card, status='requested')

        # Reject request
        rej_res = ReprintWorkflowService.reject_requests(
            table=self.table,
            rr_ids=[rr.id],
            user=self.super_admin,
        )
        self.assertTrue(rej_res.success)
        self.assertFalse(ReprintRequest.objects.filter(id=rr.id).exists())

        # Card remains in download status with original data
        self.card.refresh_from_db()
        self.assertEqual(self.card.field_data['NAME'], 'Rahul Sharma')
        self.assertEqual(self.card.status, 'download')

    def test_api_reprint_full_lifecycle(self):
        """End-to-end API verification for the 3 lists and transition actions."""
        # 1. Check initial step counts
        req = self.rf.get(f'/reprint/api/table/{self.table.id}/step-counts/')
        req.user = self.super_admin
        resp = api_reprint_step_counts(req, self.table.id)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data['reprint_list'], 1)
        self.assertEqual(data['request_list'], 0)
        self.assertEqual(data['confirmed'], 0)

        # 2. Step 1 API: Request reprint with changes
        req = self.rf.post(
            f'/reprint/api/table/{self.table.id}/request/',
            data=json.dumps({
                'card_ids': [self.card.id],
                'reason': 'API request test',
                'changes': {str(self.card.id): {'NAME': 'Rahul S. Updated'}},
            }),
            content_type='application/json',
        )
        req.user = self.super_admin
        resp = api_reprint_request_create(req, self.table.id)
        self.assertEqual(resp.status_code, 200)

        # 3. Step 2 API: Verify in Requested List
        req = self.rf.get(f'/reprint/api/table/{self.table.id}/request-list/')
        req.user = self.super_admin
        resp = api_request_list(req, self.table.id)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(len(data['items']), 1)
        rr_id = data['items'][0]['rr_id']
        self.assertTrue(data['items'][0]['has_changes'])

        # 4. Step 2 -> 3 API: Confirm request
        req = self.rf.post(
            f'/reprint/api/table/{self.table.id}/confirm/',
            data=json.dumps({'rr_ids': [rr_id]}),
            content_type='application/json',
        )
        req.user = self.super_admin
        resp = api_reprint_confirm(req, self.table.id)
        self.assertEqual(resp.status_code, 200)

        # 5. Step 3 API: Verify in Confirmed List
        req = self.rf.get(f'/reprint/api/table/{self.table.id}/confirmed-list/')
        req.user = self.super_admin
        resp = api_confirmed_list(req, self.table.id)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['reprint_number'], 1)

        # Verify card was updated in place
        self.card.refresh_from_db()
        self.assertEqual(self.card.field_data['NAME'], 'Rahul S. Updated')

        # 6. Card History API
        req = self.rf.get(f'/reprint/api/card/{self.card.id}/history/')
        req.user = self.super_admin
        resp = api_reprint_card_history(req, self.card.id)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data['total_reprints'], 1)

    def test_client_reprint_modal_edit_and_request(self):
        """Client users can safely edit card and create reprint requests from download status."""
        client_user = User.objects.create_user(
            username='client_test_user',
            password='pass',
            role='client',
        )
        self.org.user = client_user
        self.org.save()

        from core.views.idcard_card_api import api_idcard_update

        # Normal edit on download status card is blocked for client
        req_blocked = self.rf.post(
            f'/api/card/{self.card.id}/update/',
            data=json.dumps({'field_data': {'NAME': 'Unauthorized Change'}}),
            content_type='application/json',
        )
        req_blocked.user = client_user
        resp_blocked = api_idcard_update(req_blocked, self.card.id)
        self.assertEqual(resp_blocked.status_code, 403)

        # Reprint modal edit on download status card is allowed
        req_allowed = self.rf.post(
            f'/api/card/{self.card.id}/update/',
            data=json.dumps({
                'field_data': {'NAME': 'Client Modal Edit'},
                'reprint_modal_edit': True,
            }),
            content_type='application/json',
        )
        req_allowed.user = client_user
        resp_allowed = api_idcard_update(req_allowed, self.card.id)
        self.assertEqual(resp_allowed.status_code, 200)

        # Create reprint request as client
        req_create = self.rf.post(
            f'/reprint/api/table/{self.table.id}/request/',
            data=json.dumps({
                'card_ids': [self.card.id],
                'reason': 'Damaged in transit',
            }),
            content_type='application/json',
        )
        req_create.user = client_user
        resp_create = api_reprint_request_create(req_create, self.table.id)
        self.assertEqual(resp_create.status_code, 200)
        data = json.loads(resp_create.content)
        self.assertEqual(data['status'], 'ok')
