from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest import mock

User = get_user_model()


class IDCardsModelTests(TestCase):
	def setUp(self):
		from organisation.models import Organisation
		from tables.models import Table

		self.owner = User.objects.create_user(
			username='owner-model-id@test.com',
			email='owner-model-id@test.com',
			password='pass1234',
			role='client',
		)
		self.client_obj = Organisation.objects.create(user=self.owner, name='Model IDCards Client')
		self.table = Table.objects.create(
			organisation=self.client_obj,
			name='Students',
			fields=[
				{'name': 'Name', 'type': 'text', 'mandatory': True},
				{'name': 'Class', 'type': 'class', 'mandatory': True},
				{'name': 'Section', 'type': 'section', 'mandatory': False},
				{'name': 'Photo', 'type': 'photo', 'mandatory': True},
			],
		)

	def test_table_field_helpers_detect_class_section_and_images(self):
		self.assertTrue(self.table.has_class_field())
		self.assertTrue(self.table.has_section_field())
		self.assertTrue(self.table.has_image_fields())
		self.assertEqual(self.table.get_image_fields(), ['Photo'])

	def test_idcard_save_sanitizes_text_but_keeps_image_markers(self):
		from tables.models import IDCard

		card = IDCard.objects.create(
			table=self.table,
			field_data={
				'Name': 'Aditya🙂\u0007 Kumar',
				'Photo': 'PENDING:photo_1.jpg',
			},
			status='pending',
		)

		card.refresh_from_db()
		self.assertEqual(card.field_data['Name'], 'Aditya Kumar')
		self.assertEqual(card.field_data['Photo'], 'PENDING:photo_1.jpg')

	def test_idcard_client_and_group_properties(self):
		from tables.models import IDCard

		card = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'Neha', 'Class': '10', 'Photo': 'adarshimg/a.jpg'},
			status='pending',
		)

		self.assertEqual(card.table.id, self.table.id)
		self.assertEqual(card.client.id, self.client_obj.id)


class WorkflowServiceTests(TestCase):
	def setUp(self):
		from organisation.models import Organisation
		from tables.models import Table, IDCard

		self.super_admin = User.objects.create_user(
			username='super-workflow@test.com',
			email='super-workflow@test.com',
			password='pass1234',
			role='super_admin',
		)
		self.client_user = User.objects.create_user(
			username='client-workflow@test.com',
			email='client-workflow@test.com',
			password='pass1234',
			role='client',
		)
		self.client_obj = Organisation.objects.create(
			user=self.client_user,
			name='Workflow Client',
			status='active',
			perm_idcard_verify=True,
			perm_idcard_approve=True,
			perm_idcard_delete=True,
			perm_idcard_retrieve=False,
			perm_idcard_reprint_list=True,
		)

		self.table = Table.objects.create(
			organisation=self.client_obj,
			name='Workflow Table',
			fields=[
				{'name': 'Name', 'type': 'text', 'mandatory': True},
				{'name': 'Photo', 'type': 'photo', 'mandatory': True},
				{'name': 'Class', 'type': 'class', 'mandatory': False},
			],
		)

		self.card_good_pending = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'Good', 'Photo': 'adarshimg/good.jpg', 'Class': '10'},
			status='pending',
		)
		self.card_missing_text = IDCard.objects.create(
			table=self.table,
			field_data={'Name': '', 'Photo': 'adarshimg/missing-text.jpg'},
			status='pending',
		)
		self.card_missing_image = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'No Image', 'Photo': ''},
			status='pending',
		)

	def test_get_allowed_transitions_filters_by_permissions(self):
		from tables.services_workflow import WorkflowService

		allowed = WorkflowService.get_allowed_transitions(self.card_good_pending, user=self.client_user)
		self.assertIn('verified', allowed)
		self.assertIn('pool', allowed)

	def test_transition_rejects_invalid_target_status(self):
		from tables.services_workflow import WorkflowService

		result = WorkflowService.transition(
			self.card_good_pending,
			'not-a-status',
			user=self.client_user,
		)
		self.assertFalse(result.success)
		self.assertIn('Invalid status', result.message)

	def test_transition_blocks_when_mandatory_fields_missing(self):
		from tables.services_workflow import WorkflowService

		result = WorkflowService.transition(
			self.card_missing_text,
			'verified',
			user=self.client_user,
		)
		self.assertFalse(result.success)
		self.assertIn('required fields are empty', result.message)

	def test_transition_blocks_when_mandatory_images_missing(self):
		from tables.services_workflow import WorkflowService

		result = WorkflowService.transition(
			self.card_missing_image,
			'verified',
			user=self.client_user,
		)
		self.assertFalse(result.success)
		self.assertIn('required fields are empty', result.message)

	def test_super_admin_bypasses_required_field_and_image_gates(self):
		from tables.services_workflow import WorkflowService

		result = WorkflowService.transition(
			self.card_missing_image,
			'verified',
			user=self.super_admin,
		)
		self.assertTrue(result.success)
		self.card_missing_image.refresh_from_db()
		self.assertEqual(self.card_missing_image.status, 'verified')

	def test_transition_pool_to_pending_requires_retrieve_permission(self):
		from tables.models import IDCard
		from tables.services_workflow import WorkflowService

		card = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'Pool Card', 'Photo': 'adarshimg/pool.jpg'},
			status='pool',
		)
		result = WorkflowService.transition(card, 'pending', user=self.client_user)
		self.assertFalse(result.success)
		self.assertIn('Permission denied', result.message)

	def test_transition_sets_and_clears_downloaded_timestamp(self):
		from tables.models import IDCard
		from tables.services_workflow import WorkflowService

		card = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'Approved Card', 'Photo': 'adarshimg/appr.jpg'},
			status='approved',
		)

		first = WorkflowService.transition(card, 'download', user=self.super_admin)
		self.assertTrue(first.success)
		card.refresh_from_db()
		self.assertIsNotNone(card.downloaded_at)
		self.assertEqual(card.modified_by, self.super_admin.username)

		second = WorkflowService.transition(card, 'approved', user=self.super_admin)
		self.assertTrue(second.success)
		card.refresh_from_db()
		self.assertIsNone(card.downloaded_at)

	def test_bulk_transition_download_to_pending_clears_downloaded_timestamp(self):
		from django.utils import timezone
		from tables.models import IDCard
		from tables.services_workflow import WorkflowService

		card = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'Bulk Downloaded', 'Photo': 'adarshimg/bulk-dl.jpg'},
			status='download',
			downloaded_at=timezone.now(),
		)

		result = WorkflowService.bulk_transition(
			table=self.table,
			card_ids=[card.id],
			target_status='pending',
			user=self.super_admin,
		)
		self.assertTrue(result.success)
		card.refresh_from_db()
		self.assertEqual(card.status, 'pending')
		self.assertIsNone(card.downloaded_at)

	def test_bulk_transition_pending_from_download_requires_retrieve_not_verify(self):
		from tables.models import IDCard
		from tables.services_workflow import WorkflowService

		staff_like_user = User.objects.create_user(
			username='workflow-adminstaff@test.com',
			email='workflow-adminstaff@test.com',
			password='pass1234',
			role='operator',
		)
		card = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'Retrieve Only', 'Photo': 'adarshimg/retrieve.jpg'},
			status='download',
		)

		with mock.patch('tables.services_workflow.PermissionService.has', side_effect=lambda _u, perm: perm == 'perm_idcard_retrieve'):
			result = WorkflowService.bulk_transition(
				table=self.table,
				card_ids=[card.id],
				target_status='pending',
				user=staff_like_user,
			)

		self.assertTrue(result.success)
		card.refresh_from_db()
		self.assertEqual(card.status, 'pending')

	def test_bulk_transition_updates_eligible_and_skips_invalid(self):
		from tables.services_workflow import WorkflowService

		result = WorkflowService.bulk_transition(
			table=self.table,
			card_ids=[self.card_good_pending.id, self.card_missing_text.id, self.card_missing_image.id],
			target_status='verified',
			user=self.client_user,
		)
		self.assertTrue(result.success)
		self.assertEqual(result.data['updated_count'], 1)
		self.assertEqual(result.data['skipped_count'], 2)

		self.card_good_pending.refresh_from_db()
		self.card_missing_text.refresh_from_db()
		self.card_missing_image.refresh_from_db()
		self.assertEqual(self.card_good_pending.status, 'verified')
		self.assertEqual(self.card_missing_text.status, 'pending')
		self.assertEqual(self.card_missing_image.status, 'pending')

	def test_bulk_transition_to_pool_sets_deleted_timestamp(self):
		from tables.models import IDCard
		from tables.services_workflow import WorkflowService

		card_verified = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'To Pool', 'Photo': 'adarshimg/poolit.jpg'},
			status='verified',
		)

		result = WorkflowService.bulk_transition(
			table=self.table,
			card_ids=[card_verified.id],
			target_status='pool',
			user=self.client_user,
		)
		self.assertTrue(result.success)
		card_verified.refresh_from_db()
		self.assertEqual(card_verified.status, 'pool')
		self.assertIsNotNone(card_verified.deleted_at)

	def test_debug_workflow_reports_missing_fields_and_images(self):
		from tables.services_workflow import WorkflowService

		info = WorkflowService.debug_workflow(self.card_missing_image.id, user=self.client_user)
		self.assertEqual(info['current_status'], 'pending')
		self.assertNotIn('Name', info['mandatory_fields_missing'])
		self.assertIn('Photo', info['image_fields_missing'])

	def test_transition_without_user_does_not_crash(self):
		from tables.services_workflow import WorkflowService

		result = WorkflowService.transition(
			self.card_good_pending,
			'verified',
			user=None,
		)
		self.assertTrue(result.success)
		self.card_good_pending.refresh_from_db()
		self.assertEqual(self.card_good_pending.status, 'verified')

	def test_transition_logs_per_card_activity_entry(self):
		from tables.services_workflow import WorkflowService
		from core.models import ActivityLog

		result = WorkflowService.transition(
			self.card_good_pending,
			'verified',
			user=self.client_user,
		)
		self.assertTrue(result.success)

		self.assertTrue(
			ActivityLog.objects.filter(
				action='card_status',
				target_model='IDCard',
				target_id=self.card_good_pending.id,
			).exists()
		)

	def test_bulk_transition_logs_single_bulk_activity_entry(self):
		from tables.models import IDCard
		from tables.services_workflow import WorkflowService
		from core.models import ActivityLog

		second_card = IDCard.objects.create(
			table=self.table,
			field_data={'Name': 'Second', 'Photo': 'adarshimg/second.jpg', 'Class': '10'},
			status='pending',
		)

		result = WorkflowService.bulk_transition(
			table=self.table,
			card_ids=[self.card_good_pending.id, second_card.id],
			target_status='verified',
			user=self.client_user,
		)
		self.assertTrue(result.success)

		# Bulk transition should create one single bulk status log entry
		bulk_logs = ActivityLog.objects.filter(
			action='card_bulk_status',
			target_model='IDCard',
		)
		self.assertEqual(bulk_logs.count(), 1)
		self.assertIn('2 cards moved from Pending to Verified', bulk_logs.first().description)

		# It should not create individual status log entries
		self.assertFalse(
			ActivityLog.objects.filter(
				action='card_status',
				target_model='IDCard',
			).exists()
		)

	def test_bulk_transition_normalizes_invalid_card_ids(self):
		from tables.services_workflow import WorkflowService

		result = WorkflowService.bulk_transition(
			table=self.table,
			card_ids=['bad', None, -1, self.card_good_pending.id, str(self.card_good_pending.id)],
			target_status='verified',
			user=self.client_user,
		)

		self.assertTrue(result.success)
		self.card_good_pending.refresh_from_db()
		self.assertEqual(self.card_good_pending.status, 'verified')

	def test_bulk_transition_ignores_locked_cards_outside_target_table(self):
		from tables.models import Table, IDCard
		from tables.services_workflow import WorkflowService

		other_table = Table.objects.create(
			organisation=self.client_obj,
			name='Other Table',
			fields=self.table.fields,
		)
		locked_other_table_card = IDCard.objects.create(
			table=other_table,
			field_data={'Name': 'Locked', 'Photo': 'adarshimg/locked.jpg'},
			status='approved',
		)

		result = WorkflowService.bulk_transition(
			table=self.table,
			card_ids=[self.card_good_pending.id, locked_other_table_card.id],
			target_status='verified',
			user=self.client_user,
		)

		self.assertTrue(result.success)
		self.card_good_pending.refresh_from_db()
		locked_other_table_card.refresh_from_db()
		self.assertEqual(self.card_good_pending.status, 'verified')
		self.assertEqual(locked_other_table_card.status, 'approved')


class RowScopingCacheTests(TestCase):
	def setUp(self):
		from organisation.models import Organisation
		from tables.models import Table

		self.owner = User.objects.create_user(
			username='scoping-owner@test.com',
			email='scoping-owner@test.com',
			password='pass1234',
			role='client',
		)
		self.client_obj = Organisation.objects.create(user=self.owner, name='Scoping Client')
		self.table = Table.objects.create(
			organisation=self.client_obj,
			name='Scoping Table',
			fields=[
				{'name': 'Name', 'type': 'text'},
				{'name': 'Class', 'type': 'class'},
				{'name': 'Section', 'type': 'section'},
			],
		)

	def test_scoping_distinct_cache_and_invalidation(self):
		from django.core.cache import cache
		from tables.models import IDCard
		from core.views.idcard_helpers import _get_distinct_field_values_cached, invalidate_table_distinct_cache

		# Ensure cache is empty initially
		invalidate_table_distinct_cache(self.table.id)
		
		# Create cards with classes and sections
		IDCard.objects.create(table=self.table, field_data={'Name': 'Alice', 'Class': '10', 'Section': 'A'})
		IDCard.objects.create(table=self.table, field_data={'Name': 'Bob', 'Class': '10', 'Section': 'B'})
		IDCard.objects.create(table=self.table, field_data={'Name': 'Charlie', 'Class': '11', 'Section': 'A'})

		# Call cached distinct lookup
		class_variants = ['Class', 'class', 'CLASS']

		# 1. First lookup triggers cache miss and database query
		classes_1 = _get_distinct_field_values_cached(self.table, 'class', class_variants)
		self.assertCountEqual(classes_1, ['10', '11'])

		# Verify cache is populated
		cache_key = f"table_distinct_fields:{self.table.id}:class"
		self.assertEqual(cache.get(cache_key), classes_1)

		# 2. Modify card, triggering post_save signal and cache invalidation
		card = IDCard.objects.create(table=self.table, field_data={'Name': 'Dave', 'Class': '12', 'Section': 'C'})
		self.assertIsNone(cache.get(cache_key)) # Cache must be cleared by signal receiver!

		# 3. Next lookup repopulates cache with new value
		classes_2 = _get_distinct_field_values_cached(self.table, 'class', class_variants)
		self.assertCountEqual(classes_2, ['10', '11', '12'])
		self.assertEqual(cache.get(cache_key), classes_2)

		# 4. Delete card, triggering post_delete signal and cache invalidation
		card.delete()
		self.assertIsNone(cache.get(cache_key))

		# 5. Lookup returns to original values
		classes_3 = _get_distinct_field_values_cached(self.table, 'class', class_variants)
		self.assertCountEqual(classes_3, ['10', '11'])

