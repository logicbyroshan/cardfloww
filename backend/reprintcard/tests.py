import json
from datetime import timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

User = get_user_model()


class ReprintRequestModelTests(TestCase):
	def test_reprint_request_string_representation(self):
		from organisation.models import Organisation
		from tables.models import Table, IDCard
		from reprintcard.models import ReprintRequest

		owner = User.objects.create_user(
			username='owner-model@test.com',
			email='owner-model@test.com',
			password='pass1234',
			role='client',
		)
		client = Organisation.objects.create(user=owner, name='Model Client')
		group = Table.objects.create(client=client, name='Model Group')
		table = Table.objects.create(
			group=group,
			name='Model Table',
			fields=[{'name': 'Name', 'type': 'text'}],
		)
		card = IDCard.objects.create(table=table, field_data={'Name': 'A'}, status='download')
		rr = ReprintRequest.objects.create(card=card, table=table, status='requested', requested_by=owner)

		self.assertIn(f'Reprint #{rr.id}', str(rr))
		self.assertIn(f'Card #{card.id}', str(rr))
		self.assertIn('requested', str(rr))


class ReprintWorkflowServiceTests(TestCase):
	def setUp(self):
		from organisation.models import Organisation
		from tables.models import Table, IDCard
		from reprintcard.models import ReprintRequest

		self.owner = User.objects.create_user(
			username='owner-service@test.com',
			email='owner-service@test.com',
			password='pass1234',
			role='client',
		)
		self.client_obj = Organisation.objects.create(user=self.owner, name='Service Client')
		self.group = Table.objects.create(client=self.client_obj, name='Service Group')
		self.table = Table.objects.create(
			group=self.group,
			name='Service Table',
			fields=[
				{'name': 'Name', 'type': 'text'},
				{'name': 'Class', 'type': 'class'},
				{'name': 'Section', 'type': 'section'},
			],
		)

		self.card_download_1 = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'Card One', 'Class': '10', 'Section': 'A'},
			status='download',
		)
		self.card_download_2 = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'Card Two', 'Class': '10', 'Section': 'B'},
			status='download',
		)
		self.card_pending = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'Card Three'},
			status='pending',
		)

		self.rr_requested = ReprintRequest.objects.create(
			card=self.card_download_1,
			table=self.table,
			status='requested',
			requested_by=self.owner,
		)

	def test_create_requests_requires_card_ids(self):
		from reprintcard.services import ReprintWorkflowService

		result = ReprintWorkflowService.create_requests(table=self.table, card_ids=[], requested_by=self.owner)
		self.assertFalse(result.success)
		self.assertIn('No card IDs provided', result.message)

	def test_create_requests_creates_only_eligible_download_cards(self):
		from reprintcard.services import ReprintWorkflowService
		from reprintcard.models import ReprintRequest

		result = ReprintWorkflowService.create_requests(
			table=self.table,
			card_ids=[self.card_download_1.id, self.card_download_2.id, self.card_pending.id, 999999],
			reason='Need reprint',
			requested_by=self.owner,
		)

		self.assertTrue(result.success)
		self.assertEqual(result.data['created_count'], 1)
		self.assertEqual(result.data['skipped_count'], 1)
		self.assertTrue(
			ReprintRequest.objects.filter(
				card=self.card_download_2,
				table=self.table,
				status='requested',
			).exists()
		)
		self.assertFalse(ReprintRequest.objects.filter(card=self.card_pending).exists())

	def test_transition_blocks_invalid_requested_to_downloaded(self):
		from reprintcard.services import ReprintWorkflowService

		result = ReprintWorkflowService.transition(self.rr_requested, 'downloaded', user=self.owner)
		self.assertFalse(result.success)
		self.assertIn('Cannot change reprint status', result.message)

	def test_bulk_transition_confirms_only_requested(self):
		from reprintcard.services import ReprintWorkflowService
		from reprintcard.models import ReprintRequest

		rr_confirmed = ReprintRequest.objects.create(
			card=self.card_download_2,
			table=self.table,
			status='confirmed',
			requested_by=self.owner,
		)

		result = ReprintWorkflowService.bulk_transition(
			table=self.table,
			rr_ids=[self.rr_requested.id, rr_confirmed.id],
			target_status='confirmed',
			user=self.owner,
		)

		self.assertTrue(result.success)
		self.assertEqual(result.data['updated_count'], 1)
		self.rr_requested.refresh_from_db()
		rr_confirmed.refresh_from_db()
		self.assertEqual(self.rr_requested.status, 'confirmed')
		self.assertEqual(rr_confirmed.status, 'confirmed')

	def test_bulk_transition_allows_confirmed_back_to_requested(self):
		from reprintcard.services import ReprintWorkflowService
		from reprintcard.models import ReprintRequest

		rr_confirmed = ReprintRequest.objects.create(
			card=self.card_download_2,
			table=self.table,
			status='confirmed',
			requested_by=self.owner,
		)

		result = ReprintWorkflowService.bulk_transition(
			table=self.table,
			rr_ids=[self.rr_requested.id, rr_confirmed.id],
			target_status='requested',
			user=self.owner,
		)

		self.assertTrue(result.success)
		self.assertEqual(result.data['updated_count'], 1)
		self.rr_requested.refresh_from_db()
		rr_confirmed.refresh_from_db()
		self.assertEqual(self.rr_requested.status, 'requested')
		self.assertEqual(rr_confirmed.status, 'requested')

	def test_bulk_transition_updates_updated_at(self):
		from reprintcard.services import ReprintWorkflowService
		from reprintcard.models import ReprintRequest

		old_updated_at = timezone.now() - timedelta(days=1)
		ReprintRequest.objects.filter(id=self.rr_requested.id).update(updated_at=old_updated_at)

		result = ReprintWorkflowService.bulk_transition(
			table=self.table,
			rr_ids=[self.rr_requested.id],
			target_status='confirmed',
			user=self.owner,
		)

		self.assertTrue(result.success)
		self.rr_requested.refresh_from_db()
		self.assertGreater(self.rr_requested.updated_at, old_updated_at)

	def test_bulk_transition_rejects_invalid_rr_ids(self):
		from reprintcard.services import ReprintWorkflowService

		result = ReprintWorkflowService.bulk_transition(
			table=self.table,
			rr_ids=['x', None, {}],
			target_status='confirmed',
			user=self.owner,
		)

		self.assertFalse(result.success)
		self.assertIn('No reprint IDs provided', result.message)

	def test_reject_requests_keeps_cards_in_download_by_default(self):
		from reprintcard.services import ReprintWorkflowService
		from reprintcard.models import ReprintRequest

		result = ReprintWorkflowService.reject_requests(
			table=self.table,
			rr_ids=[self.rr_requested.id],
		)

		self.assertTrue(result.success)
		self.assertEqual(result.data['rejected_count'], 1)
		self.assertFalse(ReprintRequest.objects.filter(id=self.rr_requested.id).exists())
		self.card_download_1.refresh_from_db()
		self.assertEqual(self.card_download_1.status, 'download')
		self.assertIsNone(self.card_download_1.deleted_at)

	def test_reject_requests_can_optionally_move_cards_to_pool(self):
		from reprintcard.services import ReprintWorkflowService

		result = ReprintWorkflowService.reject_requests(
			table=self.table,
			rr_ids=[self.rr_requested.id],
			move_card_to_pool=True,
		)

		self.assertTrue(result.success)
		self.card_download_1.refresh_from_db()
		self.assertEqual(self.card_download_1.status, 'pool')
		self.assertIsNotNone(self.card_download_1.deleted_at)
		self.assertIsNotNone(self.card_download_1.status_changed_at)

	def test_debug_reprint_for_missing_id(self):
		from reprintcard.services import ReprintWorkflowService

		info = ReprintWorkflowService.debug_reprint(987654)
		self.assertIn('error', info)

	def test_bulk_transition_logs_per_card_activity_entries(self):
		from reprintcard.services import ReprintWorkflowService
		from core.models import ActivityLog

		result = ReprintWorkflowService.bulk_transition(
			table=self.table,
			rr_ids=[self.rr_requested.id],
			target_status='confirmed',
			user=self.owner,
		)
		self.assertTrue(result.success)

		self.assertTrue(
			ActivityLog.objects.filter(
				action='reprint_status',
				target_model='Table',
				target_id=self.table.id,
			).exists()
		)


class ReprintApiIntegrationTests(TestCase):
	def setUp(self):
		from organisation.models import Organisation
		from tables.models import Table, IDCard
		from staff.models import Staff
		from reprintcard.models import ReprintRequest

		cache.clear()

		self.super_admin = User.objects.create_user(
			username='super-reprint@test.com',
			email='super-reprint@test.com',
			password='pass1234',
			role='super_admin',
		)

		self.client_user = User.objects.create_user(
			username='client-reprint@test.com',
			email='client-reprint@test.com',
			password='pass1234',
			role='client',
		)
		self.client_obj = Organisation.objects.create(
			user=self.client_user,
			name='Reprint Client',
			perm_idcard_download_list=True,
			perm_idcard_reprint_list=True,
		)

		self.other_client_user = User.objects.create_user(
			username='other-client-reprint@test.com',
			email='other-client-reprint@test.com',
			password='pass1234',
			role='client',
		)
		self.other_client = Organisation.objects.create(
			user=self.other_client_user,
			name='Other Reprint Client',
		)

		self.group = Table.objects.create(client=self.client_obj, name='Reprint Group')
		self.table = Table.objects.create(
			group=self.group,
			name='Reprint Table',
			fields=[
				{'name': 'Name', 'type': 'text'},
				{'name': 'Class', 'type': 'class'},
				{'name': 'Section', 'type': 'section'},
			],
		)

		self.card_a = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'Alpha', 'Class': '10', 'Section': 'A'},
			status='download',
		)
		self.card_b = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'Beta', 'Class': '10', 'Section': 'B'},
			status='download',
		)
		self.card_c = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'Gamma', 'Class': '10', 'Section': 'C'},
			status='download',
		)

		self.rr_requested = ReprintRequest.objects.create(
			card=self.card_a,
			table=self.table,
			status='requested',
			requested_by=self.super_admin,
		)

		self.assigned_staff_user = User.objects.create_user(
			username='assigned-staff@test.com',
			email='assigned-staff@test.com',
			password='pass1234',
			role='operator',
		)
		self.assigned_staff = Staff.objects.create(
			user=self.assigned_staff_user,
			staff_type='operator',
			perm_idcard_download_list=True,
			perm_idcard_reprint_list=True,
			perm_reprint_request_list=True,
			perm_confirmed_list=True,
		)
		self.assigned_staff.assigned_organisations.add(self.client_obj)

		self.unassigned_staff_user = User.objects.create_user(
			username='unassigned-staff@test.com',
			email='unassigned-staff@test.com',
			password='pass1234',
			role='operator',
		)
		Staff.objects.create(
			user=self.unassigned_staff_user,
			staff_type='operator',
		)

	def _url(self, name, table_id=None):
		from django.urls import reverse

		tid = table_id or self.table.id
		return reverse(f'reprintcard:{name}', args=[tid])

	def test_step_counts_requires_authentication(self):
		response = self.client.get(self._url('api_reprint_step_counts'))
		self.assertIn(response.status_code, [302, 401])

	def test_step_counts_denies_unassigned_admin_staff_scope(self):
		self.client.force_login(self.unassigned_staff_user)
		response = self.client.get(self._url('api_reprint_step_counts'))
		self.assertEqual(response.status_code, 403)

	def test_step_counts_for_assigned_staff(self):
		self.client.force_login(self.assigned_staff_user)
		response = self.client.get(self._url('api_reprint_step_counts'))

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload['status'], 'ok')
		self.assertEqual(payload['download_list'], 3)
		self.assertEqual(payload['request_list'], 1)

	def test_step_counts_do_not_subtract_request_or_confirmed_cards_from_download_list(self):
		from reprintcard.models import ReprintRequest

		ReprintRequest.objects.create(
			card=self.card_b,
			table=self.table,
			status='confirmed',
			requested_by=self.super_admin,
		)

		self.client.force_login(self.assigned_staff_user)
		response = self.client.get(self._url('api_reprint_step_counts'))
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload['download_list'], 3)
		self.assertEqual(payload['request_list'], 1)
		self.assertEqual(payload['confirmed'], 1)

	def test_reprint_request_create_invalid_json(self):
		self.client.force_login(self.super_admin)
		response = self.client.post(
			self._url('api_reprint_request_create'),
			data='bad-json',
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 400)

	def test_reprint_request_create_rejects_non_object_json_payload(self):
		self.client.force_login(self.super_admin)
		response = self.client.post(
			self._url('api_reprint_request_create'),
			data='[]',
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 400)

	def test_reprint_request_create_and_request_list(self):
		self.client.force_login(self.super_admin)

		create_response = self.client.post(
			self._url('api_reprint_request_create'),
			data=json.dumps({'card_ids': [self.card_b.id], 'reason': 'Correction'}),
			content_type='application/json',
		)
		self.assertEqual(create_response.status_code, 200)
		self.assertEqual(create_response.json()['created_count'], 1)

		list_response = self.client.get(self._url('api_request_list'))
		self.assertEqual(list_response.status_code, 200)
		self.assertGreaterEqual(len(list_response.json()['items']), 2)

	def test_download_list_reprint_button_and_modal_work_for_client_admin_and_operator(self):
		from django.urls import reverse

		page_urls = [
			(self.super_admin, reverse('api_idcard_list', args=[self.table.id]) + '?status=download'),
			(self.client_user, reverse('client_root:api_cards', args=[self.table.id]) + '?status=download'),
			(self.assigned_staff_user, reverse('api_idcard_list', args=[self.table.id]) + '?status=download'),
		]
		for label, user, url in [
			('super_admin', self.super_admin, page_urls[0][1]),
			('client', self.client_user, page_urls[1][1]),
			('operator', self.assigned_staff_user, page_urls[2][1]),
		]:
			with self.subTest(role=label):
				self.client.force_login(user)
				response = self.client.get(url)
				self.assertEqual(response.status_code, 200)
				self.assertTrue(response.json().get('success'))

		self.client.force_login(self.client_user)
		plain_response = self.client.post(
			self._url('api_reprint_request_create'),
			data=json.dumps({
				'card_ids': [self.card_c.id],
				'reason': 'Need reprint',
			}),
			content_type='application/json',
		)
		self.assertEqual(plain_response.status_code, 200)
		self.assertEqual(plain_response.json().get('created_count'), 1)

		request_list_response = self.client.get(self._url('api_request_list'))
		self.assertEqual(request_list_response.status_code, 200)
		request_payload = request_list_response.json()
		self.assertEqual(request_payload.get('total'), 2)
		plain_item = next((item for item in request_payload.get('items', []) if item.get('card_id') == self.card_c.id), None)
		self.assertIsNotNone(plain_item)
		plain_name_field = next((field for field in plain_item.get('ordered_fields', []) if str(field.get('name', '')).lower() == 'name'), None)
		self.assertIsNotNone(plain_name_field)
		self.assertEqual(str(plain_name_field.get('value')).strip(), 'Gamma')

		edit_response = self.client.post(
			self._url('api_reprint_request_create'),
			data=json.dumps({
				'card_ids': [self.card_b.id],
				'inline_field_data': {
					'Name': 'Beta Edited',
					'Class': '10',
					'Section': 'B',
				},
			}),
			content_type='application/json',
		)
		self.assertEqual(edit_response.status_code, 200)
		self.assertEqual(edit_response.json().get('created_count'), 1)

		request_list_response = self.client.get(self._url('api_request_list'))
		self.assertEqual(request_list_response.status_code, 200)
		request_payload = request_list_response.json()
		self.assertEqual(request_payload.get('total'), 3)
		edited_item = next((item for item in request_payload.get('items', []) if item.get('card_id') == self.card_b.id), None)
		self.assertIsNotNone(edited_item)
		edited_name_field = next((field for field in edited_item.get('ordered_fields', []) if str(field.get('name', '')).lower() == 'name'), None)
		self.assertIsNotNone(edited_name_field)
		self.assertEqual(str(edited_name_field.get('value') or '').strip().upper(), 'BETA EDITED')

		download_list_response = self.client.get(self._url('api_reprint_list'))
		self.assertEqual(download_list_response.status_code, 200)
		download_payload = download_list_response.json()
		self.assertEqual(download_payload.get('total'), 3)
		download_item = next((item for item in download_payload.get('items', []) if item.get('card_id') == self.card_b.id), None)
		self.assertIsNotNone(download_item)
		download_name_field = next((field for field in download_item.get('ordered_fields', []) if str(field.get('name', '')).lower() == 'name'), None)
		self.assertIsNotNone(download_name_field)
		self.assertEqual(str(download_name_field.get('value') or '').strip().upper(), 'BETA EDITED')

	def test_reprint_request_create_allows_inline_edit_for_client_reprint_flow(self):
		self.client.force_login(self.client_user)

		response = self.client.post(
			self._url('api_reprint_request_create'),
			data=json.dumps({
				'card_ids': [self.card_b.id],
				'inline_field_data': {
					'Name': 'Beta Inline',
					'Class': '10',
					'Section': 'B',
				},
			}),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload.get('status'), 'ok')
		self.assertEqual(payload.get('created_count'), 1)

		self.card_b.refresh_from_db()
		field_data = self.card_b.field_data or {}
		updated_name = field_data.get('Name') or field_data.get('NAME') or ''
		self.assertEqual(str(updated_name).upper(), 'BETA INLINE')

	def test_reprint_request_create_inline_edit_requires_single_card(self):
		self.client.force_login(self.client_user)

		response = self.client.post(
			self._url('api_reprint_request_create'),
			data=json.dumps({
				'card_ids': [self.card_a.id, self.card_b.id],
				'inline_field_data': {'Name': 'Should Fail'},
			}),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn('exactly one card', response.json().get('message', '').lower())

	def test_reprint_request_create_inline_edit_rejects_non_object(self):
		self.client.force_login(self.client_user)

		response = self.client.post(
			self._url('api_reprint_request_create'),
			data=json.dumps({
				'card_ids': [self.card_b.id],
				'inline_field_data': 'bad',
			}),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn('must be an object', response.json().get('message', '').lower())

	def test_reprint_request_create_inline_edit_ignores_image_fields(self):
		from tables.models import Table, IDCard

		image_table = Table.objects.create(
			group=self.group,
			name='Inline Image Safe Table',
			fields=[
				{'name': 'Name', 'type': 'text'},
				{'name': 'Photo', 'type': 'image'},
			],
		)
		image_card = IDCard.objects.create(
			table=image_table,
			field_data={
				'Name': 'Inline Image Card',
				'Photo': 'mediafiles/cards/original-photo.jpg',
			},
			status='download',
		)

		self.client.force_login(self.client_user)
		response = self.client.post(
			self._url('api_reprint_request_create', table_id=image_table.id),
			data=json.dumps({
				'card_ids': [image_card.id],
				'inline_field_data': {
					'Name': 'Inline Updated',
					'Photo': '',
				},
			}),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 200)
		image_card.refresh_from_db()
		field_data = image_card.field_data or {}
		updated_name = field_data.get('Name') or field_data.get('NAME') or ''
		self.assertEqual(str(updated_name).upper(), 'INLINE UPDATED')
		self.assertEqual(field_data.get('Photo') or field_data.get('PHOTO'), 'mediafiles/cards/original-photo.jpg')

	def test_request_list_visible_for_client_with_reprint_permission(self):
		self.client.force_login(self.client_user)

		response = self.client.get(self._url('api_request_list'))
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload.get('status'), 'ok')
		self.assertGreaterEqual(payload.get('total', 0), 1)

	def test_request_list_visible_for_client_with_request_permission_only(self):
		self.client_obj.perm_idcard_reprint_list = False
		self.client_obj.perm_reprint_request_list = True
		self.client_obj.save(update_fields=['perm_idcard_reprint_list', 'perm_reprint_request_list'])

		self.client.force_login(self.client_user)

		page_response = self.client.get(self._url('reprint_cards') + '?step=request_list')
		self.assertEqual(page_response.status_code, 200)
		self.assertEqual(page_response.json().get('status'), 'ok')

		api_response = self.client.get(self._url('api_request_list'))
		self.assertEqual(api_response.status_code, 200)
		self.assertEqual(api_response.json().get('status'), 'ok')

		list_response = self.client.get(self._url('api_reprint_list'))
		self.assertEqual(list_response.status_code, 200)
		self.assertEqual(list_response.json().get('status'), 'ok')

		create_response = self.client.post(
			self._url('api_reprint_request_create'),
			data=json.dumps({'card_ids': [self.card_a.id]}),
			content_type='application/json',
		)
		self.assertEqual(create_response.status_code, 200)
		self.assertEqual(create_response.json().get('status'), 'ok')

	def test_reprint_list_normalizes_legacy_mediafiles_image_paths(self):
		from tables.models import Table, IDCard

		legacy_table = Table.objects.create(
			group=self.group,
			name='Legacy Image Table',
			fields=[
				{'name': 'Name', 'type': 'text'},
				{'name': 'Photo', 'type': 'image'},
			],
		)
		legacy_card = IDCard.objects.create(
			table=legacy_table,
			field_data={
				'Name': 'Legacy Alpha',
				'Photo': r'C:\\legacy\\uploads\\mediafiles\\cards\\alpha.jpg',
			},
			status='download',
		)

		self.client.force_login(self.super_admin)
		response = self.client.get(self._url('api_reprint_list', table_id=legacy_table.id))
		self.assertEqual(response.status_code, 200)

		payload = response.json()
		self.assertEqual(payload.get('status'), 'ok')
		item = next((entry for entry in payload.get('items', []) if entry.get('card_id') == legacy_card.id), None)
		self.assertIsNotNone(item)
		photo_field = next((f for f in item.get('ordered_fields', []) if str(f.get('name', '')).lower() == 'photo'), None)
		self.assertIsNotNone(photo_field)
		self.assertEqual(photo_field.get('value'), 'mediafiles/cards/alpha.jpg')

	def test_reprint_list_relation_photo_media_type_fallback(self):
		from tables.models import Table, IDCard
		from mediafiles.models import CardMedia

		rel_table = Table.objects.create(
			group=self.group,
			name='Relation Photo Fallback Table',
			fields=[
				{'name': 'Name', 'type': 'text'},
				{'name': 'Rel 1 Photo', 'type': 'image'},
			],
		)
		rel_card = IDCard.objects.create(
			table=rel_table,
			field_data={
				'Name': 'Legacy Relation',
				'Rel 1 Photo': '',
			},
			status='download',
		)

		CardMedia.objects.create(
			card=rel_card,
			client=self.client_obj,
			file='mediafiles/cards/rel-fallback.jpg',
			media_type='rel_photo',
			field_name=None,
			uploaded_by=self.super_admin,
		)

		self.client.force_login(self.super_admin)
		response = self.client.get(self._url('api_reprint_list', table_id=rel_table.id))
		self.assertEqual(response.status_code, 200)

		payload = response.json()
		self.assertEqual(payload.get('status'), 'ok')
		item = next((entry for entry in payload.get('items', []) if entry.get('card_id') == rel_card.id), None)
		self.assertIsNotNone(item)
		rel_field = next((f for f in item.get('ordered_fields', []) if str(f.get('name', '')).lower() == 'rel 1 photo'), None)
		self.assertIsNotNone(rel_field)
		self.assertEqual(rel_field.get('value'), 'mediafiles/cards/rel-fallback.jpg')

	def test_request_list_normalizes_legacy_mediafiles_image_paths(self):
		from tables.models import Table, IDCard
		from reprintcard.models import ReprintRequest

		legacy_table = Table.objects.create(
			group=self.group,
			name='Legacy Requested Image Table',
			fields=[
				{'name': 'Name', 'type': 'text'},
				{'name': 'Photo', 'type': 'image'},
			],
		)
		legacy_card = IDCard.objects.create(
			table=legacy_table,
			field_data={
				'Name': 'Legacy Beta',
				'Photo': r'C:\\legacy\\uploads\\mediafiles\\cards\\beta.jpg',
			},
			status='download',
		)
		ReprintRequest.objects.create(
			table=legacy_table,
			card=legacy_card,
			status='requested',
			requested_by=self.super_admin,
		)

		self.client.force_login(self.super_admin)
		response = self.client.get(self._url('api_request_list', table_id=legacy_table.id))
		self.assertEqual(response.status_code, 200)

		payload = response.json()
		self.assertEqual(payload.get('status'), 'ok')
		item = next((entry for entry in payload.get('items', []) if entry.get('card_id') == legacy_card.id), None)
		self.assertIsNotNone(item)
		photo_field = next((f for f in item.get('ordered_fields', []) if str(f.get('name', '')).lower() == 'photo'), None)
		self.assertIsNotNone(photo_field)
		self.assertEqual(photo_field.get('value'), 'mediafiles/cards/beta.jpg')

	def test_request_list_reads_image_value_when_field_key_format_differs(self):
		from tables.models import Table, IDCard
		from reprintcard.models import ReprintRequest

		table = Table.objects.create(
			group=self.group,
			name='Key Format Table',
			fields=[
				{'name': 'Name', 'type': 'text'},
				{'name': 'Student Image', 'type': 'image'},
			],
		)
		card = IDCard.objects.create(
			table=table,
			field_data={
				'Name': 'Format Student',
				'STUDENT_IMAGE': 'mediafiles/cards/keyfmt-request.jpg',
			},
			status='download',
		)
		ReprintRequest.objects.create(
			table=table,
			card=card,
			status='requested',
			requested_by=self.super_admin,
		)

		self.client.force_login(self.super_admin)
		response = self.client.get(self._url('api_request_list', table_id=table.id))
		self.assertEqual(response.status_code, 200)

		payload = response.json()
		self.assertEqual(payload.get('status'), 'ok')
		item = next((entry for entry in payload.get('items', []) if entry.get('card_id') == card.id), None)
		self.assertIsNotNone(item)
		img_field = next((f for f in item.get('ordered_fields', []) if str(f.get('name', '')).lower() == 'student image'), None)
		self.assertIsNotNone(img_field)
		self.assertEqual(img_field.get('value'), 'mediafiles/cards/keyfmt-request.jpg')

	def test_request_list_clamps_offset_and_limit(self):
		self.client.force_login(self.super_admin)
		response = self.client.get(self._url('api_request_list'), {'offset': -100, 'limit': 99999})
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload['offset'], 0)
		self.assertEqual(payload['limit'], 200)

	def test_request_list_non_numeric_query_is_stable(self):
		self.client.force_login(self.super_admin)
		response = self.client.get(self._url('api_request_list'), {'q': 'alpha'})
		self.assertEqual(response.status_code, 200)

	def test_confirm_invalid_rr_ids_payload_returns_400(self):
		self.client.force_login(self.super_admin)
		response = self.client.post(
			self._url('api_reprint_confirm'),
			data=json.dumps({'rr_ids': ['bad', None, {}]}),
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 400)

	def test_confirm_rejects_non_object_json_payload(self):
		self.client.force_login(self.super_admin)
		response = self.client.post(
			self._url('api_reprint_confirm'),
			data='[]',
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 400)

	def test_confirm_requires_admin_role_even_with_client_permission(self):
		from reprintcard.models import ReprintRequest

		self.client.force_login(self.client_user)
		rr = ReprintRequest.objects.create(
			card=self.card_b,
			table=self.table,
			status='requested',
			requested_by=self.super_admin,
		)
		response = self.client.post(
			self._url('api_reprint_confirm'),
			data=json.dumps({'rr_ids': [rr.id]}),
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 403)

	def test_confirm_then_mark_downloaded(self):
		from reprintcard.models import ReprintRequest

		self.client.force_login(self.super_admin)
		confirm_response = self.client.post(
			self._url('api_reprint_confirm'),
			data=json.dumps({'rr_ids': [self.rr_requested.id]}),
			content_type='application/json',
		)
		self.assertEqual(confirm_response.status_code, 200)

		self.rr_requested.refresh_from_db()
		self.assertEqual(self.rr_requested.status, 'confirmed')

		mark_response = self.client.post(
			self._url('api_reprint_mark_downloaded'),
			data=json.dumps({'rr_ids': [self.rr_requested.id]}),
			content_type='application/json',
		)
		self.assertEqual(mark_response.status_code, 200)

		self.rr_requested.refresh_from_db()
		self.assertEqual(self.rr_requested.status, 'downloaded')

		download_response = self.client.get(self._url('api_download_list'))
		self.assertEqual(download_response.status_code, 200)
		rr_ids = [item['rr_id'] for item in download_response.json()['items']]
		self.assertIn(self.rr_requested.id, rr_ids)

		self.assertTrue(ReprintRequest.objects.filter(id=self.rr_requested.id, status='downloaded').exists())

	def test_confirmed_list_retrieve_moves_back_to_request(self):
		from reprintcard.models import ReprintRequest

		self.client.force_login(self.super_admin)
		confirm_response = self.client.post(
			self._url('api_reprint_confirm'),
			data=json.dumps({'rr_ids': [self.rr_requested.id]}),
			content_type='application/json',
		)
		self.assertEqual(confirm_response.status_code, 200)

		retrieve_response = self.client.post(
			self._url('api_reprint_retrieve'),
			data=json.dumps({'rr_ids': [self.rr_requested.id]}),
			content_type='application/json',
		)
		self.assertEqual(retrieve_response.status_code, 200)
		self.assertEqual(retrieve_response.json().get('requested_count'), 1)

		self.rr_requested.refresh_from_db()
		self.assertEqual(self.rr_requested.status, 'requested')
		self.assertTrue(ReprintRequest.objects.filter(id=self.rr_requested.id, status='requested').exists())

	def test_reject_keeps_card_in_download(self):
		self.client.force_login(self.super_admin)
		response = self.client.post(
			self._url('api_reprint_reject'),
			data=json.dumps({'rr_ids': [self.rr_requested.id]}),
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 200)

		self.card_a.refresh_from_db()
		self.assertEqual(self.card_a.status, 'download')

	def test_send_to_print_requires_selected_ids(self):
		self.client.force_login(self.super_admin)
		response = self.client.post(
			self._url('api_reprint_send_to_print'),
			data=json.dumps({'rr_ids': []}),
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 400)

	def test_send_to_print_creates_print_request_and_moves_to_confirmed(self):
		try:
			from cardprint.models import PrintRequest  # may be removed in some branches
		except Exception:
			PrintRequest = None

		self.client.force_login(self.super_admin)
		response = self.client.post(
			self._url('api_reprint_send_to_print'),
			data=json.dumps({'rr_ids': [self.rr_requested.id]}),
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 200)

		self.rr_requested.refresh_from_db()
		self.assertEqual(self.rr_requested.status, 'confirmed')

		if PrintRequest is not None:
			self.assertTrue(
				PrintRequest.objects.filter(
					table=self.table,
					card_id=self.card_a.id,
					status='generate_list',
				).exists()
			)

	def test_confirmed_cards_are_available_in_reprint_list(self):
		from reprintcard.models import ReprintRequest
		from reprintcard.services import ReprintWorkflowService

		# Initially, self.card_a has a reprint request in 'requested' status.
		# Check that card_a is NOT in the available reprint list
		self.client.force_login(self.client_user)
		response = self.client.get(self._url('api_reprint_list'), {'available_only': '1'})
		self.assertEqual(response.status_code, 200)
		items = response.json().get('items', [])
		card_ids = [item['card_id'] for item in items]
		self.assertNotIn(self.card_a.id, card_ids)

		# Move self.rr_requested status to 'confirmed'
		self.rr_requested.status = 'confirmed'
		self.rr_requested.save()

		# Check that card_a is now available in the reprint list!
		response = self.client.get(self._url('api_reprint_list'), {'available_only': '1'})
		self.assertEqual(response.status_code, 200)
		items = response.json().get('items', [])
		card_ids = [item['card_id'] for item in items]
		self.assertIn(self.card_a.id, card_ids)

		# Check that we can create a new reprint request for self.card_a
		create_response = self.client.post(
			self._url('api_reprint_request_create'),
			data=json.dumps({'card_ids': [self.card_a.id], 'reason': 'Reprint again'}),
			content_type='application/json',
		)
		self.assertEqual(create_response.status_code, 200)
		self.assertEqual(create_response.json()['created_count'], 1)

		# There should now be two reprint requests for card_a: one confirmed, one requested
		self.assertEqual(
			ReprintRequest.objects.filter(card=self.card_a, status='requested').count(),
			1
		)
		self.assertEqual(
			ReprintRequest.objects.filter(card=self.card_a, status='confirmed').count(),
			1
		)

