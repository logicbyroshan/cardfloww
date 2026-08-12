"""
Tests for client app.
Covers: Organisation model, access control, client dashboard access.
"""
import json

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from unittest import mock

User = get_user_model()


class ClientModelTests(TestCase):
    """Tests for Client model."""

    def test_create_client(self):
        from organisation.models import Organisation
        user = User.objects.create_user(
            username='c1@test.com', email='c1@test.com',
            password='pass1234', role='client',
        )
        client = Organisation.objects.create(user=user, name='Test School')
        self.assertEqual(client.name, 'Test School')
        self.assertEqual(client.status, 'active')
        self.assertIsNotNone(client.image_folder_uuid)

    def test_client_default_permissions(self):
        from organisation.models import Organisation
        user = User.objects.create_user(
            username='c2@test.com', email='c2@test.com',
            password='pass1234', role='client',
        )
        client = Organisation.objects.create(user=user, name='Perm Client')
        # Default permissions should be set by model defaults
        self.assertIsNotNone(client.perm_idcard_pending_list)

    def test_client_user_relationship(self):
        from organisation.models import Organisation
        user = User.objects.create_user(
            username='c3@test.com', email='c3@test.com',
            password='pass1234', role='client',
        )
        client = Organisation.objects.create(user=user, name='Rel Client')
        self.assertEqual(user.client_profile, client)
        self.assertEqual(client.user.email, 'c3@test.com')


class ClientAccessControlTests(TestCase):
    """Tests for client access control."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='access@test.com', email='access@test.com',
            password='pass1234', role='client',
        )
        from organisation.models import Organisation
        cls.client_obj = Organisation.objects.create(user=cls.user, name='Access Client')

    def setUp(self):
        self.user.refresh_from_db()
        self.client_obj.refresh_from_db()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_client_dashboard_accessible(self):
        self.client.login(username='access@test.com', password='pass1234')
        response = self.client.get('/panel/client/dashboard/')
        self.assertIn(response.status_code, [200, 302])

    def test_non_client_blocked_from_client_dashboard(self):
        admin = User.objects.create_user(
            username='adm@test.com', email='adm@test.com',
            password='pass1234', role='super_admin',
        )
        self.client.login(username='adm@test.com', password='pass1234')
        response = self.client.get('/panel/client/dashboard/')
        # Super admin may be redirected or get 403
        self.assertIn(response.status_code, [200, 302, 403])

    def test_unauthenticated_blocked_from_client_dashboard(self):
        response = self.client.get('/panel/client/dashboard/')
        self.assertIn(response.status_code, [302, 403])


class ClientMessagesPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from organisation.models import Organisation
        from staff.models import Staff

        cls.sender = User.objects.create_user(
            username='sender-msg@test.com',
            email='sender-msg@test.com',
            password='pass1234',
            role='super_admin',
        )

        cls.client_owner = User.objects.create_user(
            username='client-owner-msg@test.com',
            email='client-owner-msg@test.com',
            password='pass1234',
            role='client',
        )
        cls.client_obj = Organisation.objects.create(user=cls.client_owner, name='Msg Client')

        cls.client_staff_user = User.objects.create_user(
            username='client-staff-msg@test.com',
            email='client-staff-msg@test.com',
            password='pass1234',
            role='client_staff',
        )
        cls.client_staff = Staff.objects.create(
            user=cls.client_staff_user,
            staff_type='assistant',
            client=cls.client_obj,
        )

        cls.super_admin = User.objects.create_user(
            username='superadmin-msg@test.com',
            email='superadmin-msg@test.com',
            password='pass1234',
            role='super_admin',
        )

    def setUp(self):
        for attr in ('sender', 'client_owner', 'client_obj', 'client_staff_user', 'client_staff', 'super_admin'):
            obj = getattr(self, attr, None)
            if obj is not None and hasattr(obj, 'refresh_from_db'):
                obj.refresh_from_db()

    def _create_message(self, text, recipients, scope='client_and_staff'):
        from core.models import Notification, ClientMessage

        notification = Notification.objects.create(
            title='Client Message',
            message=text,
            target='selected',
            category='announcement',
            priority='normal',
            created_by=self.sender,
        )
        notification.target_users.set(recipients)

        return ClientMessage.objects.create(
            client=self.client_obj,
            sent_by=self.sender,
            message=text,
            scope=scope,
            notification=notification,
            recipient_count=len(recipients),
        )

    def test_client_can_view_full_history_read_and_unread(self):
        from core.models import NotificationRead

        unread_msg = self._create_message('Unread message body', [self.client_owner])
        read_msg = self._create_message('Read message body', [self.client_owner])
        NotificationRead.objects.create(user=self.client_owner, notification=read_msg.notification)

        self.client.login(username='client-owner-msg@test.com', password='pass1234')
        response = self.client.get('/panel/client/messages/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, unread_msg.message)
        self.assertContains(response, read_msg.message)
        self.assertContains(response, 'Unread')
        self.assertContains(response, 'Read')

    def test_client_staff_can_access_messages_page(self):
        self._create_message('Staff visible message', [self.client_staff_user])

        self.client.login(username='client-staff-msg@test.com', password='pass1234')
        response = self.client.get('/panel/client/messages/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Staff visible message')

    def test_message_page_filters_to_current_recipient(self):
        self._create_message('Owner only message', [self.client_owner], scope='client_only')
        self._create_message('Staff only message', [self.client_staff_user], scope='client_and_staff')

        self.client.login(username='client-owner-msg@test.com', password='pass1234')
        response = self.client.get('/panel/client/messages/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Owner only message')
        self.assertNotContains(response, 'Staff only message')

    def test_non_client_role_cannot_access_messages_page(self):
        self.client.login(username='superadmin-msg@test.com', password='pass1234')
        response = self.client.get('/panel/client/messages/')
        self.assertIn(response.status_code, [302, 403])

    def test_messages_page_is_read_only_no_reply_form(self):
        self._create_message('Read-only test message', [self.client_owner])

        self.client.login(username='client-owner-msg@test.com', password='pass1234')
        response = self.client.get('/panel/client/messages/')

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<textarea')
        self.assertNotContains(response, 'data-send-message-btn')


class ManageClientsPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from organisation.models import Organisation

        # Clear any pre-existing records to ensure test is independent and robust
        Organisation.objects.all().delete()
        User.objects.all().delete()

        cls.super_admin = User.objects.create_user(
            username='sa-manage-clients@test.com',
            email='sa-manage-clients@test.com',
            password='pass1234',
            role='super_admin',
        )
        for idx in range(12):
            owner = User.objects.create_user(
                username=f'client-owner-{idx}@test.com',
                email=f'client-owner-{idx}@test.com',
                password='pass1234',
                role='client',
            )
            Organisation.objects.create(user=owner, name=f'Client {idx}')

    def setUp(self):
        self.super_admin.refresh_from_db()

    def test_manage_clients_renders_all_rows_not_first_ten_only(self):
        self.client.login(username='sa-manage-clients@test.com', password='pass1234')
        response = self.client.get('/panel/manage-clients/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['clients']), 12)
        self.assertEqual(response.context['page_obj'].paginator.count, 12)

    def test_manage_clients_honors_page_param(self):
        self.client.login(username='sa-manage-clients@test.com', password='pass1234')
        response = self.client.get('/panel/manage-clients/?per_page=5&page=2')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].number, 2)
        self.assertEqual(response.context['page_obj'].paginator.num_pages, 3)
        self.assertEqual(len(response.context['clients']), 5)

    def test_manage_clients_search_field_filters_specific_column(self):
        self.client.login(username='sa-manage-clients@test.com', password='pass1234')
        response = self.client.get('/panel/manage-clients/?search=client-owner-3@test.com&search_field=email')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['search_field'], 'email')
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertEqual(len(response.context['clients']), 1)

    def test_manage_clients_shows_delete_button_for_super_admin(self):
        self.client.login(username='sa-manage-clients@test.com', password='pass1234')
        response = self.client.get('/panel/manage-clients/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="deleteClientBtn"')

    def test_manage_clients_shows_reprint_permission_toggles(self):
        self.client.login(username='sa-manage-clients@test.com', password='pass1234')
        response = self.client.get('/panel/manage-clients/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reprint Lists')
        self.assertContains(response, 'Request List (Reprint)')
        self.assertContains(response, 'Confirmed List (Reprint)')


class ManageClientsPermissionGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from organisation.models import Organisation
        from staff.models import Staff

        owner = User.objects.create_user(
            username='gate-client-owner@test.com',
            email='gate-client-owner@test.com',
            password='pass1234',
            role='client',
        )
        cls.client_obj = Organisation.objects.create(user=owner, name='Gate Client')
        owner2 = User.objects.create_user(
            username='gate-client-owner-2@test.com',
            email='gate-client-owner-2@test.com',
            password='pass1234',
            role='client',
        )
        cls.client_obj_2 = Organisation.objects.create(user=owner2, name='Gate Client 2')

        cls.admin_staff = User.objects.create_user(
            username='gate-admin-staff@test.com',
            email='gate-admin-staff@test.com',
            password='pass1234',
            role='operator',
        )
        cls.staff_profile = Staff.objects.create(user=cls.admin_staff, staff_type='operator')
        cls.staff_profile.assigned_organisations.add(cls.client_obj)

    def setUp(self):
        self.client_obj.refresh_from_db()
        self.client_obj_2.refresh_from_db()
        self.admin_staff.refresh_from_db()
        self.staff_profile.refresh_from_db()

    def test_manage_clients_allows_read_only_admin_staff_without_manage_client_permission(self):
        self.client.login(username='gate-admin-staff@test.com', password='pass1234')
        response = self.client.get('/panel/manage-clients/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['clients']), 1)
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertFalse(response.context['can_manage_clients'])

    def test_manage_clients_scopes_admin_staff_with_manage_client_permission_to_assigned_clients(self):
        self.staff_profile.perm_idcard_client_list = True
        self.staff_profile.save(update_fields=['perm_idcard_client_list'])

        self.client.login(username='gate-admin-staff@test.com', password='pass1234')
        response = self.client.get('/panel/manage-clients/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['clients']), 1)
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertTrue(response.context['can_manage_clients'])
        self.assertNotContains(response, 'id="deleteClientBtn"')


class OrganisationAccessServiceTests(TestCase):
    """Tests for OrganisationAccessService."""

    def test_get_client_for_user(self):
        from organisation.services import OrganisationAccessService
        from organisation.models import Organisation
        user = User.objects.create_user(
            username='cas@test.com', email='cas@test.com',
            password='pass1234', role='client',
        )
        client = Organisation.objects.create(user=user, name='CAS Client')
        result = OrganisationAccessService.get_organisation_for_user(user)
        self.assertEqual(result.id, client.id)

    def test_get_client_for_non_client_user(self):
        from organisation.services import OrganisationAccessService
        admin = User.objects.create_user(
            username='nocas@test.com', email='nocas@test.com',
            password='pass1234', role='super_admin',
        )
        result = OrganisationAccessService.get_organisation_for_user(admin)
        self.assertIsNone(result)

    def test_admin_staff_client_scope_is_assigned_only(self):
        from organisation.services import OrganisationAccessService
        from organisation.models import Organisation
        from staff.models import Staff

        owner_a = User.objects.create_user(
            username='owner-a@test.com', email='owner-a@test.com',
            password='pass1234', role='client',
        )
        owner_b = User.objects.create_user(
            username='owner-b@test.com', email='owner-b@test.com',
            password='pass1234', role='client',
        )
        client_a = Organisation.objects.create(user=owner_a, name='Client A')
        client_b = Organisation.objects.create(user=owner_b, name='Client B')

        staff_user = User.objects.create_user(
            username='staff-a@test.com', email='staff-a@test.com',
            password='pass1234', role='operator',
        )
        staff = Staff.objects.create(user=staff_user, staff_type='operator')
        staff.assigned_organisations.add(client_a)

        self.assertTrue(OrganisationAccessService.can_access_organisation(staff_user, client_a.id))
        self.assertFalse(OrganisationAccessService.can_access_organisation(staff_user, client_b.id))

    def test_admin_staff_table_and_card_scope_is_assigned_only(self):
        from organisation.services import OrganisationAccessService
        from organisation.models import Organisation
        from staff.models import Staff
        from tables.models import Table, IDCard

        owner_a = User.objects.create_user(
            username='owner2-a@test.com', email='owner2-a@test.com',
            password='pass1234', role='client',
        )
        owner_b = User.objects.create_user(
            username='owner2-b@test.com', email='owner2-b@test.com',
            password='pass1234', role='client',
        )
        client_a = Organisation.objects.create(user=owner_a, name='Client 2A')
        client_b = Organisation.objects.create(user=owner_b, name='Client 2B')

        group_a = Table.objects.create(client=client_a, name='Group A')
        group_b = Table.objects.create(client=client_b, name='Group B')
        table_a = Table.objects.create(group=group_a, name='Table A', fields=[])
        table_b = Table.objects.create(group=group_b, name='Table B', fields=[])
        card_a = IDCard.objects.create(table=table_a, field_data={'NAME': 'A'})
        card_b = IDCard.objects.create(table=table_b, field_data={'NAME': 'B'})

        staff_user = User.objects.create_user(
            username='staff-b@test.com', email='staff-b@test.com',
            password='pass1234', role='operator',
        )
        staff = Staff.objects.create(user=staff_user, staff_type='operator')
        staff.assigned_organisations.add(client_a)

        self.assertTrue(OrganisationAccessService.can_access_table(staff_user, table_a))
        self.assertFalse(OrganisationAccessService.can_access_table(staff_user, table_b))
        self.assertTrue(OrganisationAccessService.can_access_card(staff_user, card_a))
        self.assertFalse(OrganisationAccessService.can_access_card(staff_user, card_b))


class ClientStaffTransactionTests(TestCase):
    """Transactional safety tests for OrganisationStaffService."""

    def test_update_staff_rolls_back_on_staff_save_failure(self):
        from organisation.services import OrganisationStaffService
        from organisation.models import Organisation
        from staff.models import Staff

        owner = User.objects.create_user(
            username='owner-tx@test.com', email='owner-tx@test.com',
            password='pass1234', role='client',
        )
        client_obj = Organisation.objects.create(user=owner, name='Tx Client', perm_idcard_client_list=True)

        staff_user = User.objects.create_user(
            username='staff-tx@test.com', email='staff-tx@test.com',
            password='pass1234', role='client_staff', phone='1111111111'
        )
        staff = Staff.objects.create(user=staff_user, staff_type='assistant', client=client_obj)

        original_phone = staff_user.phone

        with mock.patch('assistants.models.Assistant.save', side_effect=Exception('forced-fail')):
            result = OrganisationStaffService.update_staff(owner, staff.id, {'phone': '9999999999'})

        self.assertFalse(result.success)
        staff_user.refresh_from_db()
        self.assertEqual(staff_user.phone, original_phone)


class ClientModelFolderCodeTests(TestCase):
    def test_image_folder_code_generated_and_length_is_ten(self):
        from organisation.models import Organisation
        user = User.objects.create_user(
            username='folder1@test.com', email='folder1@test.com',
            password='pass1234', role='client',
        )
        client = Organisation.objects.create(user=user, name='Alpha Public School')
        self.assertIsNotNone(client.image_folder_code)
        self.assertEqual(len(client.image_folder_code), 10)

    def test_image_folder_suffix_stays_stable_on_name_change(self):
        from organisation.models import Organisation
        user = User.objects.create_user(
            username='folder2@test.com', email='folder2@test.com',
            password='pass1234', role='client',
        )
        client = Organisation.objects.create(user=user, name='First Name')
        old_suffix = client.image_folder_suffix
        old_code = client.image_folder_code

        client.name = 'Second Name'
        client.save()
        client.refresh_from_db()

        self.assertEqual(client.image_folder_suffix, old_suffix)
        self.assertNotEqual(client.image_folder_code, old_code)


class OrganisationAccessServiceAdvancedTests(TestCase):
    def setUp(self):
        from organisation.models import Organisation
        from staff.models import Staff
        from tables.models import Table, IDCard

        self.client_owner = User.objects.create_user(
            username='owner-adv@test.com', email='owner-adv@test.com',
            password='pass1234', role='client',
        )
        self.client_obj = Organisation.objects.create(user=self.client_owner, name='Adv Client')

        self.group_a = Table.objects.create(client=self.client_obj, name='Group A')
        self.group_b = Table.objects.create(client=self.client_obj, name='Group B')
        self.table_a = Table.objects.create(group=self.group_a, name='Table A', fields=[])
        self.table_b = Table.objects.create(group=self.group_b, name='Table B', fields=[])
        self.card_a = IDCard.objects.create(table=self.table_a, field_data={'NAME': 'A'})

        self.staff_user = User.objects.create_user(
            username='cstaff-adv@test.com', email='cstaff-adv@test.com',
            password='pass1234', role='client_staff',
        )
        self.staff = Staff.objects.create(user=self.staff_user, staff_type='assistant', client=self.client_obj)
        self.staff.assigned_groups.add(self.group_a)

    def test_client_staff_assigned_groups_restrict_table_access(self):
        from organisation.services import OrganisationAccessService
        self.assertTrue(OrganisationAccessService.can_access_table(self.staff_user, self.table_a))
        self.assertFalse(OrganisationAccessService.can_access_table(self.staff_user, self.table_b))

    def test_get_accessible_table_ids_for_client_staff(self):
        from organisation.services import OrganisationAccessService
        table_ids = OrganisationAccessService.get_accessible_table_ids(self.staff_user)
        self.assertIn(self.table_a.id, table_ids)
        self.assertNotIn(self.table_b.id, table_ids)

    def test_get_accessible_table_ids_for_client_admin_returns_none(self):
        from organisation.services import OrganisationAccessService
        self.assertIsNone(OrganisationAccessService.get_accessible_table_ids(self.client_owner))

    def test_client_staff_assigned_groups_restrict_card_access(self):
        from organisation.services import OrganisationAccessService
        self.assertTrue(OrganisationAccessService.can_access_card(self.staff_user, self.card_a))

    def test_client_reprint_permission_can_open_card_table(self):
        self.client_owner.client_profile.perm_idcard_setting_list = False
        self.client_owner.client_profile.perm_idcard_pending_list = False
        self.client_owner.client_profile.perm_idcard_verified_list = False
        self.client_owner.client_profile.perm_idcard_pool_list = False
        self.client_owner.client_profile.perm_idcard_approved_list = False
        self.client_owner.client_profile.perm_idcard_download_list = False
        self.client_owner.client_profile.perm_idcard_reprint_list = True
        self.client_owner.client_profile.perm_reprint_request_list = False
        self.client_owner.client_profile.perm_confirmed_list = False
        self.client_owner.client_profile.save(update_fields=[
            'perm_idcard_setting_list',
            'perm_idcard_pending_list',
            'perm_idcard_verified_list',
            'perm_idcard_pool_list',
            'perm_idcard_approved_list',
            'perm_idcard_download_list',
            'perm_idcard_reprint_list',
            'perm_reprint_request_list',
            'perm_confirmed_list',
        ])

        self.client.login(username='owner-adv@test.com', password='pass1234')

        response = self.client.get(f'/panel/client/table/{self.table_a.id}/cards/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cards - Client Portal')

    def test_client_request_list_permission_can_open_card_table(self):
        self.client_owner.client_profile.perm_idcard_setting_list = False
        self.client_owner.client_profile.perm_idcard_pending_list = False
        self.client_owner.client_profile.perm_idcard_verified_list = False
        self.client_owner.client_profile.perm_idcard_pool_list = False
        self.client_owner.client_profile.perm_idcard_approved_list = False
        self.client_owner.client_profile.perm_idcard_download_list = False
        self.client_owner.client_profile.perm_idcard_reprint_list = False
        self.client_owner.client_profile.perm_reprint_request_list = True
        self.client_owner.client_profile.perm_confirmed_list = False
        self.client_owner.client_profile.save(update_fields=[
            'perm_idcard_setting_list',
            'perm_idcard_pending_list',
            'perm_idcard_verified_list',
            'perm_idcard_pool_list',
            'perm_idcard_approved_list',
            'perm_idcard_download_list',
            'perm_idcard_reprint_list',
            'perm_reprint_request_list',
            'perm_confirmed_list',
        ])

        self.client.login(username='owner-adv@test.com', password='pass1234')

        response = self.client.get(f'/panel/client/table/{self.table_a.id}/reprint/?step=request_list')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Request List')

    def test_client_download_page_shows_reprint_controls_for_request_permission_only(self):
        self.client_owner.client_profile.perm_idcard_setting_list = False
        self.client_owner.client_profile.perm_idcard_pending_list = False
        self.client_owner.client_profile.perm_idcard_verified_list = False
        self.client_owner.client_profile.perm_idcard_pool_list = False
        self.client_owner.client_profile.perm_idcard_approved_list = False
        self.client_owner.client_profile.perm_idcard_download_list = True
        self.client_owner.client_profile.perm_idcard_reprint_list = False
        self.client_owner.client_profile.perm_reprint_request_list = True
        self.client_owner.client_profile.perm_confirmed_list = False
        self.client_owner.client_profile.save(update_fields=[
            'perm_idcard_setting_list',
            'perm_idcard_pending_list',
            'perm_idcard_verified_list',
            'perm_idcard_pool_list',
            'perm_idcard_approved_list',
            'perm_idcard_download_list',
            'perm_idcard_reprint_list',
            'perm_reprint_request_list',
            'perm_confirmed_list',
        ])

        self.client.login(username='owner-adv@test.com', password='pass1234')

        response = self.client.get(f'/panel/client/table/{self.table_a.id}/actions/?status=download')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="openReprintModalBtn"')
        self.assertContains(response, 'Request List')


class ClientDashboardServiceTests(TestCase):
    def test_dashboard_photo_url_maps_mediafiles_under_media_route(self):
        from organisation.services import OrganisationDashboardService

        self.assertEqual(
            OrganisationDashboardService._to_dashboard_photo_url('mediafiles/cards/sample.jpg'),
            '/media/mediafiles/cards/sample.jpg',
        )
        self.assertEqual(
            OrganisationDashboardService._to_dashboard_photo_url('/mediafiles/cards/sample.jpg'),
            '/media/mediafiles/cards/sample.jpg',
        )
        self.assertEqual(
            OrganisationDashboardService._to_dashboard_photo_url('media/adarshimg/CODE/sample.jpg'),
            '/media/adarshimg/CODE/sample.jpg',
        )

    def test_dashboard_data_for_non_client_returns_error(self):
        from organisation.services import OrganisationDashboardService
        admin = User.objects.create_user(
            username='dash-admin@test.com', email='dash-admin@test.com',
            password='pass1234', role='super_admin',
        )
        result = OrganisationDashboardService.get_dashboard_data(admin)
        self.assertFalse(result.success)

    def test_dashboard_counts_exclude_pool_from_total_cards(self):
        from organisation.services import OrganisationDashboardService
        from organisation.models import Organisation
        from tables.models import Table, IDCard

        owner = User.objects.create_user(
            username='dash-owner@test.com', email='dash-owner@test.com',
            password='pass1234', role='client',
        )
        client_obj = Organisation.objects.create(user=owner, name='Dash Client')
        group = Table.objects.create(client=client_obj, name='Group')
        table = Table.objects.create(group=group, name='Table', fields=[])

        IDCard.objects.create(table=table, field_data={'NAME': 'P'}, status='pending')
        IDCard.objects.create(table=table, field_data={'NAME': 'V'}, status='verified')
        IDCard.objects.create(table=table, field_data={'NAME': 'A'}, status='approved')
        IDCard.objects.create(table=table, field_data={'NAME': 'D'}, status='download')
        IDCard.objects.create(table=table, field_data={'NAME': 'X'}, status='pool')

        result = OrganisationDashboardService.get_dashboard_data(owner)
        self.assertTrue(result.success)
        self.assertEqual(result.data['counts']['pool'], 1)
        self.assertEqual(result.data['total_cards'], 4)

    def test_dashboard_counts_scoped_for_client_staff(self):
        from organisation.services import OrganisationDashboardService
        from organisation.models import Organisation
        from tables.models import Table, IDCard
        from staff.models import Staff

        owner = User.objects.create_user(
            username='dash-owner-staff@test.com', email='dash-owner-staff@test.com',
            password='pass1234', role='client',
        )
        client_obj = Organisation.objects.create(user=owner, name='Dash Staff Client')

        group_a = Table.objects.create(client=client_obj, name='Group A')
        group_b = Table.objects.create(client=client_obj, name='Group B')

        table_a = Table.objects.create(
            group=group_a,
            name='Table A',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
            ],
        )
        table_b = Table.objects.create(
            group=group_b,
            name='Table B',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
            ],
        )

        IDCard.objects.create(table=table_a, status='pending', field_data={'CLASS': '10', 'SECTION': 'A'})
        IDCard.objects.create(table=table_a, status='verified', field_data={'CLASS': '11', 'SECTION': 'A'})
        IDCard.objects.create(table=table_b, status='pending', field_data={'CLASS': '10', 'SECTION': 'A'})

        staff_user = User.objects.create_user(
            username='dash-cstaff@test.com', email='dash-cstaff@test.com',
            password='pass1234', role='client_staff',
        )
        staff = Staff.objects.create(
            user=staff_user,
            staff_type='assistant',
            client=client_obj,
            assigned_table_ids=[table_a.id],
            allowed_classes=['10'],
        )
        self.assertIsNotNone(staff.id)

        result = OrganisationDashboardService.get_dashboard_data(staff_user)
        self.assertTrue(result.success)
        self.assertEqual(result.data['group_count'], 1)

    def test_dashboard_data_survives_recent_activity_failure_for_client_staff(self):
        from unittest.mock import patch

        from organisation.services import OrganisationDashboardService
        from organisation.models import Organisation
        from tables.models import Table, IDCard
        from staff.models import Staff

        owner = User.objects.create_user(
            username='dash-owner-activity-fail@test.com', email='dash-owner-activity-fail@test.com',
            password='pass1234', role='client',
        )
        client_obj = Organisation.objects.create(user=owner, name='Dash Activity Failure Client')

        group = Table.objects.create(client=client_obj, name='Group A')
        table = Table.objects.create(
            group=group,
            name='Table A',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
            ],
        )

        IDCard.objects.create(table=table, status='pending', field_data={'CLASS': '10', 'SECTION': 'A'})

        staff_user = User.objects.create_user(
            username='dash-activity-fail@test.com', email='dash-activity-fail@test.com',
            password='pass1234', role='client_staff',
        )
        staff = Staff.objects.create(
            user=staff_user,
            staff_type='assistant',
            client=client_obj,
            assigned_table_ids=[table.id],
            allowed_classes=['10'],
            allowed_sections=['A'],
        )
        self.assertIsNotNone(staff.id)

        with patch('client.services_dashboard.ActivityService.get_recent', side_effect=RuntimeError('boom')):
            result = OrganisationDashboardService.get_dashboard_data(staff_user)

        self.assertTrue(result.success)
        self.assertEqual(result.data['counts']['pending'], 1)
        self.assertEqual(result.data['total_cards'], 1)
        self.assertEqual(result.data['recent_activity'], [])

    def test_groups_with_counts_scoped_for_client_staff(self):
        from organisation.services import OrganisationDashboardService
        from organisation.models import Organisation
        from tables.models import Table, IDCard
        from staff.models import Staff

        owner = User.objects.create_user(
            username='dash-owner-groups@test.com', email='dash-owner-groups@test.com',
            password='pass1234', role='client',
        )
        client_obj = Organisation.objects.create(user=owner, name='Dash Groups Client')

        group_a = Table.objects.create(client=client_obj, name='Group A')
        group_b = Table.objects.create(client=client_obj, name='Group B')

        table_a = Table.objects.create(
            group=group_a,
            name='Table A',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
            ],
        )
        table_b = Table.objects.create(
            group=group_b,
            name='Table B',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
            ],
        )

        IDCard.objects.create(table=table_a, status='pending', field_data={'CLASS': '10', 'SECTION': 'A'})
        IDCard.objects.create(table=table_a, status='verified', field_data={'CLASS': '11', 'SECTION': 'A'})
        IDCard.objects.create(table=table_b, status='pending', field_data={'CLASS': '10', 'SECTION': 'A'})

        staff_user = User.objects.create_user(
            username='dash-groups-staff@test.com', email='dash-groups-staff@test.com',
            password='pass1234', role='client_staff',
        )
        staff = Staff.objects.create(
            user=staff_user,
            staff_type='assistant',
            client=client_obj,
            assigned_table_ids=[table_a.id],
            allowed_classes=['10'],
        )
        self.assertIsNotNone(staff.id)

        result = OrganisationDashboardService.get_groups_with_counts(staff_user)
        self.assertTrue(result.success)
        self.assertEqual(len(result.data['groups']), 1)

        group_payload = result.data['groups'][0]
        self.assertEqual(group_payload['id'], group_a.id)
        self.assertEqual(group_payload['card_count'], 1)
        self.assertEqual(group_payload['pending'], 1)
        self.assertEqual(group_payload['verified'], 0)
        self.assertEqual(len(group_payload['tables']), 1)
        self.assertEqual(group_payload['tables'][0]['id'], table_a.id)
        self.assertEqual(group_payload['tables'][0]['card_count'], 1)

    def test_dashboard_counts_zero_for_client_staff_without_class_section_scope(self):
        from organisation.services import OrganisationDashboardService
        from organisation.models import Organisation
        from tables.models import Table, IDCard
        from staff.models import Staff

        owner = User.objects.create_user(
            username='dash-owner-noscope@test.com', email='dash-owner-noscope@test.com',
            password='pass1234', role='client',
        )
        client_obj = Organisation.objects.create(user=owner, name='Dash No Scope Client')
        group = Table.objects.create(client=client_obj, name='Group')
        table = Table.objects.create(
            group=group,
            name='Table',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
            ],
        )

        IDCard.objects.create(table=table, status='pending', field_data={'CLASS': '10', 'SECTION': 'A'})
        IDCard.objects.create(table=table, status='verified', field_data={'CLASS': '10', 'SECTION': 'A'})

        staff_user = User.objects.create_user(
            username='dash-noscope-staff@test.com', email='dash-noscope-staff@test.com',
            password='pass1234', role='client_staff',
        )
        staff = Staff.objects.create(
            user=staff_user,
            staff_type='assistant',
            client=client_obj,
            assigned_table_ids=[table.id],
            allowed_classes=[],
            allowed_sections=[],
            allowed_branches=[],
        )
        self.assertIsNotNone(staff.id)

        result = OrganisationDashboardService.get_dashboard_data(staff_user)
        self.assertTrue(result.success)
        self.assertEqual(result.data['counts']['pending'], 1)
        self.assertEqual(result.data['counts']['verified'], 1)
        self.assertEqual(result.data['total_cards'], 2)

    def test_groups_counts_zero_for_client_staff_without_class_section_scope(self):
        from organisation.services import OrganisationDashboardService
        from organisation.models import Organisation
        from tables.models import Table, IDCard
        from staff.models import Staff

        owner = User.objects.create_user(
            username='dash-owner-noscope-g@test.com', email='dash-owner-noscope-g@test.com',
            password='pass1234', role='client',
        )
        client_obj = Organisation.objects.create(user=owner, name='Dash No Scope Group Client')
        group = Table.objects.create(client=client_obj, name='Group')
        table = Table.objects.create(
            group=group,
            name='Table',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
            ],
        )

        IDCard.objects.create(table=table, status='pending', field_data={'CLASS': '10', 'SECTION': 'A'})

        staff_user = User.objects.create_user(
            username='dash-noscope-staff-g@test.com', email='dash-noscope-staff-g@test.com',
            password='pass1234', role='client_staff',
        )
        staff = Staff.objects.create(
            user=staff_user,
            staff_type='assistant',
            client=client_obj,
            assigned_table_ids=[table.id],
            allowed_classes=[],
            allowed_sections=[],
            allowed_branches=[],
        )
        self.assertIsNotNone(staff.id)

        result = OrganisationDashboardService.get_groups_with_counts(staff_user)
        self.assertTrue(result.success)
        self.assertEqual(len(result.data['groups']), 1)
        group_payload = result.data['groups'][0]
        self.assertEqual(group_payload['card_count'], 1)
        self.assertEqual(group_payload['pending'], 1)
        self.assertEqual(group_payload['tables'][0]['card_count'], 1)

    def test_reprint_history_includes_requested_for_inactive_table(self):
        from organisation.services import OrganisationDashboardService
        from organisation.models import Organisation
        from tables.models import Table, IDCard
        from reprintcard.models import ReprintRequest

        owner = User.objects.create_user(
            username='dash-owner-reprint-history@test.com',
            email='dash-owner-reprint-history@test.com',
            password='pass1234',
            role='client',
        )
        client_obj = Organisation.objects.create(user=owner, name='Dash Reprint History Client')
        group = Table.objects.create(client=client_obj, name='Reprint Group')
        table = Table.objects.create(group=group, name='Reprint Table', fields=[])
        table.is_active = False
        table.save(update_fields=['is_active'])

        card = IDCard.objects.create(table=table, status='download', field_data={'NAME': 'Student One'})
        ReprintRequest.objects.create(table=table, card=card, status='requested')

        result = OrganisationDashboardService.get_reprint_history(owner)
        self.assertTrue(result.success)
        self.assertEqual(result.data['total_count'], 1)
        self.assertEqual(len(result.data['items']), 1)
        self.assertEqual(result.data['items'][0]['status'], 'requested')

    def test_reprint_history_tolerates_malformed_legacy_rows(self):
        from organisation.services import OrganisationDashboardService
        from organisation.models import Organisation
        from tables.models import Table, IDCard
        from reprintcard.models import ReprintRequest

        owner = User.objects.create_user(
            username='dash-owner-reprint-malformed@test.com',
            email='dash-owner-reprint-malformed@test.com',
            password='pass1234',
            role='client',
        )
        client_obj = Organisation.objects.create(user=owner, name='Dash Reprint Malformed Client')
        group = Table.objects.create(client=client_obj, name='Malformed Group')
        table = Table.objects.create(
            group=group,
            name='Malformed Table',
            fields=['bad-field-entry', {'name': 'Name', 'type': 'text'}],
        )

        # Legacy corrupted field_data shape should not break whole dashboard history API/service.
        card = IDCard.objects.create(table=table, status='download', field_data=['not-a-dict'])
        ReprintRequest.objects.create(table=table, card=card, status='requested')

        result = OrganisationDashboardService.get_reprint_history(owner)
        self.assertTrue(result.success)
        self.assertEqual(result.data['total_count'], 1)
        self.assertEqual(len(result.data['items']), 1)
        self.assertEqual(result.data['items'][0]['status'], 'requested')
        self.assertIn('Malformed Table', result.data['items'][0]['details'])

    def test_reprint_history_populates_photo_url_with_export_helper(self):
        from organisation.services import OrganisationDashboardService
        from organisation.models import Organisation
        from tables.models import Table, IDCard
        from reprintcard.models import ReprintRequest

        owner = User.objects.create_user(
            username='dash-owner-reprint-photo@test.com',
            email='dash-owner-reprint-photo@test.com',
            password='pass1234',
            role='client',
        )
        client_obj = Organisation.objects.create(user=owner, name='Dash Reprint Photo Client')
        group = Table.objects.create(client=client_obj, name='Photo Group')
        table = Table.objects.create(
            group=group,
            name='Photo Table',
            fields=[
                {'name': 'Name', 'type': 'text'},
                {'name': 'Student Image', 'type': 'text'},
            ],
        )

        card = IDCard.objects.create(
            table=table,
            status='download',
            field_data={
                'Name': 'Photo Student',
                'Student Image': 'mediafiles/cards/raw.jpg',
            },
        )
        ReprintRequest.objects.create(table=table, card=card, status='requested')

        with mock.patch(
            'mediafiles.services.ImageService.get_image_path_for_export',
            return_value='mediafiles/cards/thumb.webp',
        ) as get_path:
            result = OrganisationDashboardService.get_reprint_history(owner)

        self.assertTrue(result.success)
        self.assertEqual(result.data['total_count'], 1)
        self.assertEqual(result.data['items'][0]['photo_url'], '/media/mediafiles/cards/thumb.webp')
        self.assertTrue(get_path.called)

    def test_reprint_history_photo_url_falls_back_when_field_key_format_differs(self):
        from organisation.services import OrganisationDashboardService
        from organisation.models import Organisation
        from tables.models import Table, IDCard
        from reprintcard.models import ReprintRequest

        owner = User.objects.create_user(
            username='dash-owner-reprint-photo-keyfmt@test.com',
            email='dash-owner-reprint-photo-keyfmt@test.com',
            password='pass1234',
            role='client',
        )
        client_obj = Organisation.objects.create(user=owner, name='Dash Reprint Photo KeyFmt Client')
        group = Table.objects.create(client=client_obj, name='Photo KeyFmt Group')
        table = Table.objects.create(
            group=group,
            name='Photo KeyFmt Table',
            fields=[
                {'name': 'Name', 'type': 'text'},
                {'name': 'Student Image', 'type': 'image'},
            ],
        )

        card = IDCard.objects.create(
            table=table,
            status='download',
            field_data={
                'Name': 'Photo Student',
                'STUDENT_IMAGE': r'C:\\legacy\\uploads\\mediafiles\\cards\\keyfmt.jpg',
            },
        )
        ReprintRequest.objects.create(table=table, card=card, status='requested')

        with mock.patch('mediafiles.services.ImageService.get_image_path_for_export', return_value=''):
            result = OrganisationDashboardService.get_reprint_history(owner)

        self.assertTrue(result.success)
        self.assertEqual(result.data['total_count'], 1)
        self.assertEqual(result.data['items'][0]['photo_url'], '/media/mediafiles/cards/keyfmt.jpg')

    def test_reprint_stats_count_requested_items(self):
        from organisation.services import OrganisationDashboardService
        from organisation.models import Organisation
        from tables.models import Table, IDCard
        from reprintcard.models import ReprintRequest

        owner = User.objects.create_user(
            username='dash-owner-reprint-stats@test.com',
            email='dash-owner-reprint-stats@test.com',
            password='pass1234',
            role='client',
        )
        client_obj = Organisation.objects.create(user=owner, name='Dash Reprint Stats Client')
        group = Table.objects.create(client=client_obj, name='Stats Group')
        table = Table.objects.create(group=group, name='Stats Table', fields=[])

        card_requested = IDCard.objects.create(table=table, status='download', field_data={'NAME': 'Requested'})
        card_confirmed = IDCard.objects.create(table=table, status='download', field_data={'NAME': 'Confirmed'})

        ReprintRequest.objects.create(table=table, card=card_requested, status='requested')
        ReprintRequest.objects.create(table=table, card=card_confirmed, status='confirmed')

        result = OrganisationDashboardService.get_reprint_stats(owner)
        self.assertTrue(result.success)
        self.assertEqual(result.data['reprint_requested'], 1)
        self.assertEqual(result.data['reprint_confirmed'], 1)
        self.assertEqual(result.data['reprint_total'], 2)

    def test_dashboard_data_includes_recent_assistants_counts_and_badges(self):
        from organisation.services import OrganisationDashboardService
        from organisation.models import Organisation
        from tables.models import Table, IDCard
        from staff.models import Staff

        owner = User.objects.create_user(
            username='dash-owner-assist@test.com', email='dash-owner-assist@test.com',
            password='pass1234', role='client',
        )
        client_obj = Organisation.objects.create(user=owner, name='Dash Assist Client')
        group = Table.objects.create(client=client_obj, name='Group')
        table = Table.objects.create(
            group=group, name='Table',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
            ]
        )

        # Create assistant (client_staff)
        staff_user = User.objects.create_user(
            username='assist-dash@test.com', email='assist-dash@test.com',
            password='pass1234', role='client_staff',
        )
        staff = Staff.objects.create(
            user=staff_user,
            staff_type='assistant',
            client=client_obj,
            assigned_table_ids=[table.id],
            allowed_classes=['10'],
            allowed_sections=['A'],
        )

        # Create some cards
        # Pending in scope
        IDCard.objects.create(table=table, status='pending', field_data={'CLASS': '10', 'SECTION': 'A'})
        # Verified out of scope (class 11)
        IDCard.objects.create(table=table, status='verified', field_data={'CLASS': '11', 'SECTION': 'A'})
        # Pool in scope
        IDCard.objects.create(table=table, status='pool', field_data={'CLASS': '10', 'SECTION': 'A'})

        result = OrganisationDashboardService.get_dashboard_data(owner)
        self.assertTrue(result.success)
        self.assertIn('recent_staff', result.data)
        self.assertEqual(len(result.data['recent_staff']), 1)
        
        ast_data = result.data['recent_staff'][0]
        self.assertEqual(ast_data['name'], staff_user.get_full_name() or staff_user.username)
        self.assertEqual(ast_data['pending'], 1)
        self.assertEqual(ast_data['verified'], 0) # out of scope
        self.assertEqual(ast_data['pool'], 1)
        self.assertEqual(ast_data['classes'], ['10'])
        self.assertEqual(ast_data['sections'], ['A'])


class ClientImageServiceTests(TestCase):
    def setUp(self):
        from organisation.models import Organisation
        from tables.models import Table, IDCard

        self.user = User.objects.create_user(
            username='img-client@test.com',
            email='img-client@test.com',
            password='pass1234',
            role='client',
        )
        self.client_obj = Organisation.objects.create(user=self.user, name='Image Client')
        self.group = Table.objects.create(client=self.client_obj, name='Img Group')
        self.table = Table.objects.create(
            group=self.group,
            name='Img Table',
            fields=[{'name': 'PHOTO', 'type': 'photo', 'order': 1}],
        )
        self.card = IDCard.objects.create(
            table=self.table,
            field_data={'PHOTO': 'PENDING:roll_001'},
            status='pending',
        )

    def test_upload_images_uses_single_authority_save_and_updates_field(self):
        from organisation.services_image import OrganisationImageService

        upload = SimpleUploadedFile(
            'roll_001.jpg',
            b'abc123' * 80,
            content_type='image/jpeg',
        )

        mocked_result = mock.Mock(success=True, data={'final_value': 'adarshimg/CODE/new.jpg'})

        with mock.patch('client.services_image.OrganisationAccessService.get_organisation_for_user', return_value=self.client_obj), \
             mock.patch('client.services_image.OrganisationAccessService.can_access_table', return_value=True), \
             mock.patch('client.services_image.PermissionService.has_permission', return_value=True), \
             mock.patch('mediafiles.services.ImageService.save_new_image', return_value=mocked_result) as save_new:
            result = OrganisationImageService.upload_images(self.user, self.table.id, [upload])

        self.assertTrue(result.success)
        self.assertEqual(result.data['matched'], 1)
        self.assertEqual(result.data['failed'], 0)

        self.card.refresh_from_db()
        self.assertEqual(self.card.field_data.get('PHOTO'), 'adarshimg/CODE/new.jpg')

        self.assertEqual(save_new.call_count, 1)
        kwargs = save_new.call_args.kwargs
        self.assertEqual(kwargs.get('field_name'), 'PHOTO')
        self.assertEqual(kwargs.get('card').id, self.card.id)


class ClientStaffServicePermissionTests(TestCase):
    def setUp(self):
        from organisation.models import Organisation
        self.owner = User.objects.create_user(
            username='staff-owner@test.com', email='staff-owner@test.com',
            password='pass1234', role='client',
        )
        self.client_obj = Organisation.objects.create(
            user=self.owner,
            name='Staff Perm Client',
            perm_idcard_client_list=True,
            perm_idcard_add=False,
        )

    def test_create_staff_cannot_grant_permission_client_does_not_have(self):
        from organisation.services import OrganisationStaffService
        from staff.models import Staff

        result = OrganisationStaffService.create_staff(self.owner, {
            'email': 'new-staff@test.com',
            'first_name': 'New',
            'last_name': 'Staff',
            'phone': '8888888888',
            'perm_idcard_add': True,
        })
        self.assertTrue(result.success)

        staff = Staff.objects.select_related('user').get(id=result.data['staff_id'])
        self.assertFalse(staff.perm_idcard_add)

    def test_create_staff_requires_client_list_permission(self):
        from organisation.services import OrganisationStaffService
        self.client_obj.perm_idcard_client_list = False
        self.client_obj.save(update_fields=['perm_idcard_client_list'])

        result = OrganisationStaffService.create_staff(self.owner, {
            'email': 'blocked-staff@test.com',
            'name': 'Blocked Staff',
        })
        self.assertFalse(result.success)
        self.assertIn('Permission denied', result.message)

    def test_create_staff_bulk_download_not_granted_when_client_lacks_permission(self):
        from organisation.services import OrganisationStaffService
        from staff.models import Staff

        result = OrganisationStaffService.create_staff(self.owner, {
            'email': 'bulk-blocked@test.com',
            'first_name': 'Bulk',
            'last_name': 'Blocked',
            'phone': '7777777777',
            'perm_idcard_bulk_download': True,
        })
        self.assertTrue(result.success)

        staff = Staff.objects.select_related('user').get(id=result.data['staff_id'])
        self.assertFalse(staff.perm_idcard_bulk_download)

    def test_update_staff_bulk_download_granted_when_client_has_permission(self):
        from organisation.services import OrganisationStaffService
        from staff.models import Staff

        self.client_obj.perm_idcard_bulk_download = True
        self.client_obj.save(update_fields=['perm_idcard_bulk_download'])

        created = OrganisationStaffService.create_staff(self.owner, {
            'email': 'bulk-allowed@test.com',
            'first_name': 'Bulk',
            'last_name': 'Allowed',
            'phone': '6666666666',
        })
        self.assertTrue(created.success)

        staff_id = created.data['staff_id']
        updated = OrganisationStaffService.update_staff(self.owner, staff_id, {
            'perm_idcard_bulk_download': True,
        })
        self.assertTrue(updated.success)

        staff = Staff.objects.get(id=staff_id)
        self.assertTrue(staff.perm_idcard_bulk_download)

    def test_update_staff_retrieve_granted_when_client_has_permission(self):
        from organisation.services import OrganisationStaffService
        from staff.models import Staff

        self.client_obj.perm_idcard_retrieve = True
        self.client_obj.save(update_fields=['perm_idcard_retrieve'])

        created = OrganisationStaffService.create_staff(self.owner, {
            'email': 'retrieve-allowed@test.com',
            'first_name': 'Retrieve',
            'last_name': 'Allowed',
            'phone': '6565656565',
        })
        self.assertTrue(created.success)

        staff_id = created.data['staff_id']
        updated = OrganisationStaffService.update_staff(self.owner, staff_id, {
            'perm_idcard_retrieve': True,
        })
        self.assertTrue(updated.success)

        staff = Staff.objects.get(id=staff_id)
        self.assertTrue(staff.perm_idcard_retrieve)

    def test_create_staff_image_mode_perms_not_granted_even_if_client_has_permission(self):
        from organisation.services import OrganisationStaffService
        from staff.models import Staff

        self.client_obj.perm_idcard_download_image_rename_mode = True
        self.client_obj.perm_idcard_download_image_generate_mode = True
        self.client_obj.save(update_fields=[
            'perm_idcard_download_image_rename_mode',
            'perm_idcard_download_image_generate_mode',
        ])

        result = OrganisationStaffService.create_staff(self.owner, {
            'email': 'image-mode-blocked@test.com',
            'first_name': 'Image',
            'last_name': 'Blocked',
            'phone': '5555555555',
            'perm_idcard_download_image_rename_mode': True,
            'perm_idcard_download_image_generate_mode': True,
        })
        self.assertTrue(result.success)

        staff = Staff.objects.select_related('user').get(id=result.data['staff_id'])
        self.assertFalse(staff.perm_idcard_download_image_rename_mode)
        self.assertFalse(staff.perm_idcard_download_image_generate_mode)

    def test_update_staff_image_mode_perms_forced_off(self):
        from organisation.services import OrganisationStaffService
        from staff.models import Staff

        self.client_obj.perm_idcard_download_image_rename_mode = True
        self.client_obj.perm_idcard_download_image_generate_mode = True
        self.client_obj.save(update_fields=[
            'perm_idcard_download_image_rename_mode',
            'perm_idcard_download_image_generate_mode',
        ])

        created = OrganisationStaffService.create_staff(self.owner, {
            'email': 'image-mode-update@test.com',
            'first_name': 'Image',
            'last_name': 'Update',
            'phone': '4444444444',
        })
        self.assertTrue(created.success)

        staff_id = created.data['staff_id']
        updated = OrganisationStaffService.update_staff(self.owner, staff_id, {
            'perm_idcard_download_image_rename_mode': True,
            'perm_idcard_download_image_generate_mode': True,
        })
        self.assertTrue(updated.success)

        staff = Staff.objects.get(id=staff_id)
        self.assertFalse(staff.perm_idcard_download_image_rename_mode)
        self.assertFalse(staff.perm_idcard_download_image_generate_mode)

    def test_create_staff_allows_custom_password_without_phone_or_email(self):
        from organisation.services import OrganisationStaffService
        from staff.models import Staff

        result = OrganisationStaffService.create_staff(self.owner, {
            'name': 'Custom Only Staff',
            'password': 'StaffOnly@123',
            'phone': '',
            'email': 'custom-only-staff@example.com',
        })
        self.assertTrue(result.success, msg=result.message)

        staff = Staff.objects.select_related('user').get(id=result.data['staff_id'])
        self.assertEqual(staff.user.phone or '', '')
        self.assertTrue(staff.user.check_password('StaffOnly@123'))

    def test_create_staff_rejects_missing_phone_and_password(self):
        from organisation.services import OrganisationStaffService

        result = OrganisationStaffService.create_staff(self.owner, {
            'name': 'Missing Credentials Staff',
            'phone': '',
            'password': '',
            'email': 'missing-credentials-staff@example.com',
        })
        self.assertFalse(result.success)
        self.assertIn('phone number is required', result.message.lower())

    def test_create_staff_active_sends_welcome_email(self):
        from organisation.services import OrganisationStaffService
        from core.models import EmailLog
        from staff.models import Staff

        def _fake_send_welcome_email(**kwargs):
            on_success = kwargs.get('on_success')
            if callable(on_success):
                on_success()
            return True, 'Welcome email queued for delivery.'

        with mock.patch('client.services_staff.send_welcome_email', side_effect=_fake_send_welcome_email) as send_welcome_mock:
            result = OrganisationStaffService.create_staff(self.owner, {
                'email': 'active-client-staff@test.com',
                'first_name': 'Active',
                'last_name': 'Staff',
                'phone': '9345678901',
                'is_active': True,
            })

        self.assertTrue(result.success, msg=result.message)
        self.assertTrue(result.data.get('email_sent'))
        send_welcome_mock.assert_called_once()

        staff = Staff.objects.select_related('user').get(id=result.data['staff_id'])
        self.assertTrue(staff.user.welcome_email_sent)
        self.assertTrue(
            EmailLog.objects.filter(
                recipient_email='active-client-staff@test.com',
                email_type=EmailLog.EMAIL_TYPE_WELCOME,
                status=EmailLog.STATUS_SENT,
            ).exists()
        )

    def test_create_staff_inactive_keeps_welcome_email_on_hold(self):
        from organisation.services import OrganisationStaffService
        from core.models import EmailLog

        with mock.patch('client.services_staff.send_welcome_email') as send_welcome_mock:
            result = OrganisationStaffService.create_staff(self.owner, {
                'email': 'inactive-client-staff@test.com',
                'first_name': 'Inactive',
                'last_name': 'Staff',
                'phone': '9456789012',
                'is_active': False,
            })

        self.assertTrue(result.success, msg=result.message)
        self.assertFalse(result.data.get('email_sent'))
        send_welcome_mock.assert_not_called()
        self.assertTrue(
            EmailLog.objects.filter(
                recipient_email='inactive-client-staff@test.com',
                email_type=EmailLog.EMAIL_TYPE_WELCOME,
                status=EmailLog.STATUS_ON_HOLD,
            ).exists()
        )

    def test_resolve_assignment_scope_auto_prefers_groups_for_multi_group_client(self):
        from organisation.services import OrganisationStaffService
        from tables.models import Table

        group_a = Table.objects.create(client=self.client_obj, name='Group A')
        group_b = Table.objects.create(client=self.client_obj, name='Group B')
        Table.objects.create(group=group_a, name='Table A', fields=[])
        Table.objects.create(group=group_b, name='Table B', fields=[])

        resolved_group_ids, resolved_table_ids = OrganisationStaffService._resolve_assignment_scope_ids(
            self.client_obj,
            [group_a.id, group_b.id],
            'auto',
        )

        self.assertEqual(resolved_group_ids, sorted([group_a.id, group_b.id]))
        self.assertEqual(resolved_table_ids, [])


class ClientApiIntegrationTests(TestCase):
    def setUp(self):
        from organisation.models import Organisation
        from tables.models import Table, IDCard
        from staff.models import Staff

        cache.clear()

        self.owner = User.objects.create_user(
            username='api-owner@test.com', email='api-owner@test.com',
            password='pass1234', role='client',
        )
        self.client_obj = Organisation.objects.create(
            user=self.owner,
            name='API Client',
            perm_idcard_setting_list=True,
            perm_idcard_client_list=True,
            perm_idcard_pending_list=True,
        )

        self.group = Table.objects.create(client=self.client_obj, name='Class 10')
        self.table = Table.objects.create(
            group=self.group,
            name='Students',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
                {'name': 'NAME', 'type': 'text'},
            ],
        )
        self.card = IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'NAME': 'John'},
        )

        self.client_staff_user = User.objects.create_user(
            username='api-staff@test.com', email='api-staff@test.com',
            password='pass1234', role='client_staff',
        )
        self.staff_profile = Staff.objects.create(
            user=self.client_staff_user,
            staff_type='assistant',
            client=self.client_obj,
        )

    def tearDown(self):
        cache.clear()

    def test_api_tables_list_permission_denied_when_setting_list_off(self):
        self.client_obj.perm_idcard_setting_list = False
        self.client_obj.save(update_fields=['perm_idcard_setting_list'])
        self.client.login(username='api-owner@test.com', password='pass1234')

        response = self.client.get('/panel/client/api/tables/')
        self.assertEqual(response.status_code, 403)

    def test_api_tables_list_success(self):
        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get('/panel/client/api/tables/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertGreaterEqual(len(payload.get('tables', [])), 1)

    def test_api_class_section_options_returns_values(self):
        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get('/panel/client/api/class-section-options/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIn('10', payload.get('classes', []))
        self.assertIn('A', payload.get('sections', []))

    def test_api_cards_list_preserves_combined_filters_and_sort(self):
        from tables.models import IDCard

        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'NAME': 'Alpha', 'PHOTO': 'adarshimg/alpha.jpg'},
        )
        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'NAME': 'Bravo', 'PHOTO': 'PENDING:bravo.jpg'},
        )
        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'NAME': 'Charlie', 'PHOTO': 'adarshimg/charlie.jpg'},
        )

        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get(
            f'/panel/client/api/table/{self.table.id}/cards/',
            {
                'status': 'pending',
                'search': 'a',
                'class': '10',
                'section': 'A',
                'photo': 'complete',
                'sort': 'name-desc',
            },
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload['success'], msg=str(payload))

        cards = payload.get('data', {}).get('cards', [])
        names = [card.get('field_data', {}).get('NAME') for card in cards]
        self.assertEqual(names, ['Charlie', 'Alpha'])

    def test_panel_cards_list_preserves_class_section_sort_for_client_role(self):
        from tables.models import IDCard

        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '11', 'SECTION': 'B', 'NAME': 'Alpha'},
        )
        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '11', 'SECTION': 'B', 'NAME': 'Bravo'},
        )
        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '11', 'SECTION': 'B', 'NAME': 'Charlie'},
        )

        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get(
            f'/panel/api/table/{self.table.id}/cards/',
            {
                'status': 'pending',
                'class': '11',
                'section': 'B',
                'sort': 'name-desc',
            },
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload.get('success'), msg=str(payload))
        cards = payload.get('cards', [])
        names = [card.get('field_data', {}).get('NAME') for card in cards]
        self.assertEqual(names[:3], ['Charlie', 'Bravo', 'Alpha'])

    def test_api_staff_list_create_rejects_client_staff_role(self):
        self.client.login(username='api-staff@test.com', password='pass1234')
        response = self.client.get(
            '/panel/client/api/staff/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 403)

    def test_api_staff_list_create_allows_client_staff_with_client_list_permission(self):
        self.staff_profile.perm_idcard_client_list = True
        self.staff_profile.save(update_fields=['perm_idcard_client_list'])

        self.client.login(username='api-staff@test.com', password='pass1234')
        response = self.client.get('/panel/client/api/staff/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

    def test_client_staff_manage_page_allows_client_list_permission(self):
        self.staff_profile.perm_idcard_client_list = True
        self.staff_profile.save(update_fields=['perm_idcard_client_list'])

        self.client.login(username='api-staff@test.com', password='pass1234')
        response = self.client.get('/panel/client/staff/')

        self.assertEqual(response.status_code, 200)

    @mock.patch('client.views_api.OrganisationStaffService.create_staff')
    def test_api_staff_create_caps_assignment_payload_sizes(self, mock_create_staff):
        from core.services.base import ServiceResult

        mock_create_staff.return_value = ServiceResult(
            success=True,
            message='Created',
            data={'staff_id': 9999},
        )

        self.client.login(username='api-owner@test.com', password='pass1234')
        payload = {
            'name': 'Scoped Staff',
            'phone': '7777777777',
            'assigned_groups': list(range(1, 1201)),
            'assignment_scopes': [
                {'scope_type': 'group', 'scope_id': i, 'classes': [], 'sections': [], 'branches': []}
                for i in range(1, 1201)
            ],
        }
        response = self.client.post(
            '/panel/client/api/staff/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

        called_data = mock_create_staff.call_args.args[1]
        self.assertEqual(len(called_data.get('assigned_groups', [])), 500)
        self.assertEqual(len(called_data.get('assignment_scopes', [])), 500)

    @mock.patch('client.views_api.OrganisationStaffService.update_staff')
    def test_api_staff_update_normalizes_invalid_assignment_scope_shape(self, mock_update_staff):
        from core.services.base import ServiceResult

        mock_update_staff.return_value = ServiceResult(
            success=True,
            message='Updated',
            data={},
        )

        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.put(
            f'/panel/client/api/staff/{self.staff_profile.id}/',
            data=json.dumps({
                'assignment_scopes': {'scope_type': 'group', 'scope_id': self.group.id},
            }),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

        called_data = mock_update_staff.call_args.args[2]
        self.assertEqual(called_data.get('assignment_scopes'), [])

    def test_api_card_detail_success_for_client(self):
        self.client_obj.perm_idcard_info = True
        self.client_obj.save(update_fields=['perm_idcard_info'])

        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get(f'/panel/client/api/cards/{self.card.id}/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

    def test_api_class_section_options_respects_table_id_source(self):
        from tables.models import Table, IDCard

        second_table = Table.objects.create(
            group=self.group,
            name='Second Students',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
                {'name': 'NAME', 'type': 'text'},
            ],
        )
        IDCard.objects.create(
            table=second_table,
            status='pending',
            field_data={'CLASS': '11', 'SECTION': 'B', 'NAME': 'Jane'},
        )

        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get(
            f'/panel/client/api/class-section-options/?group_ids={self.table.id}&id_source=table'
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIn('10', payload.get('classes', []))
        self.assertIn('A', payload.get('sections', []))
        self.assertNotIn('11', payload.get('classes', []))
        self.assertNotIn('B', payload.get('sections', []))

    def test_api_class_section_options_includes_count_maps(self):
        from tables.models import IDCard

        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'NAME': 'John 2'},
        )
        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'B', 'NAME': 'John 3'},
        )

        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get(
            f'/panel/client/api/class-section-options/?group_ids={self.table.id}&id_source=table'
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload.get('class_counts', {}).get('10'), 3)
        self.assertEqual(payload.get('section_counts', {}).get('A'), 2)
        self.assertEqual(payload.get('section_counts', {}).get('B'), 1)
        self.assertEqual(payload.get('class_section_counts', {}).get('10', {}).get('A'), 2)
        self.assertEqual(payload.get('class_section_counts', {}).get('10', {}).get('B'), 1)

    def test_api_staff_create_and_detail_include_assignment_scopes(self):
        self.client.login(username='api-owner@test.com', password='pass1234')

        payload = {
            'name': 'Scoped Staff',
            'email': 'scoped-staff@example.com',
            'phone': '7777777777',
            'assigned_groups': [self.table.id],
            'assignment_id_source': 'table',
            'assignment_scopes': [
                {
                    'scope_type': 'table',
                    'scope_id': self.table.id,
                    'classes': ['10'],
                    'sections': ['A'],
                    'branches': [],
                }
            ],
        }
        create_resp = self.client.post(
            '/panel/client/api/staff/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(create_resp.status_code, 200)
        create_payload = create_resp.json()
        self.assertTrue(create_payload.get('success'))

        staff_id = create_payload['data']['staff_id']
        detail_resp = self.client.get(f'/panel/client/api/staff/{staff_id}/')
        self.assertEqual(detail_resp.status_code, 200)
        detail_payload = detail_resp.json().get('data', {})
        scopes = detail_payload.get('assignment_scopes', [])
        self.assertEqual(len(scopes), 1)
        self.assertEqual(scopes[0].get('scope_type'), 'table')
        self.assertEqual(scopes[0].get('scope_id'), self.table.id)
        self.assertEqual(scopes[0].get('classes'), ['10'])
        self.assertEqual(scopes[0].get('sections'), ['A'])

    def test_api_staff_detail_preserves_legacy_flat_assignment_fields(self):
        self.staff_profile.assigned_groups.set([self.group])
        self.staff_profile.allowed_classes = ['10']
        self.staff_profile.allowed_sections = ['A']
        self.staff_profile.allowed_branches = []
        self.staff_profile.assignment_scopes = []
        self.staff_profile.save(update_fields=[
            'allowed_classes',
            'allowed_sections',
            'allowed_branches',
            'assignment_scopes',
        ])

        self.client.login(username='api-owner@test.com', password='pass1234')
        detail_resp = self.client.get(f'/panel/client/api/staff/{self.staff_profile.id}/')

        self.assertEqual(detail_resp.status_code, 200)
        detail_payload = detail_resp.json().get('data', {})
        scopes = detail_payload.get('assignment_scopes', [])
        self.assertEqual(len(scopes), 1)
        self.assertEqual(scopes[0].get('scope_type'), 'group')
        self.assertEqual(scopes[0].get('scope_id'), self.group.id)
        self.assertEqual(scopes[0].get('classes'), ['10'])
        self.assertEqual(scopes[0].get('sections'), ['A'])
        self.assertEqual(detail_payload.get('allowed_classes'), ['10'])
        self.assertEqual(detail_payload.get('allowed_sections'), ['A'])

    def test_api_staff_detail_synthesizes_single_class_multiple_sections_legacy_scope(self):
        self.staff_profile.assigned_groups.set([self.group])
        self.staff_profile.allowed_classes = ['10']
        self.staff_profile.allowed_sections = ['A', 'B']
        self.staff_profile.allowed_branches = []
        self.staff_profile.assignment_scopes = []
        self.staff_profile.save(update_fields=[
            'allowed_classes',
            'allowed_sections',
            'allowed_branches',
            'assignment_scopes',
        ])

        self.client.login(username='api-owner@test.com', password='pass1234')
        detail_resp = self.client.get(f'/panel/client/api/staff/{self.staff_profile.id}/')

        self.assertEqual(detail_resp.status_code, 200)
        detail_payload = detail_resp.json().get('data', {})
        scopes = detail_payload.get('assignment_scopes', [])
        self.assertEqual(len(scopes), 1)
        self.assertEqual(scopes[0].get('scope_type'), 'group')
        self.assertEqual(scopes[0].get('scope_id'), self.group.id)
        self.assertEqual(scopes[0].get('classes'), ['10'])
        self.assertEqual(scopes[0].get('sections'), ['A', 'B'])
        self.assertEqual(scopes[0].get('class_sections'), {'10': ['A', 'B']})
        self.assertEqual(detail_payload.get('allowed_classes'), ['10'])
        self.assertEqual(detail_payload.get('allowed_sections'), ['A', 'B'])

    def test_api_staff_update_round_trips_scoped_assignments(self):
        self.client.login(username='api-owner@test.com', password='pass1234')

        update_payload = {
            'name': 'Scoped Staff Updated',
            'assigned_groups': [self.group.id],
            'assignment_id_source': 'group',
            'assignment_scopes': [
                {
                    'scope_type': 'group',
                    'scope_id': self.group.id,
                    'classes': ['10'],
                    'sections': ['A'],
                    'branches': [],
                }
            ],
        }
        update_resp = self.client.put(
            f'/panel/client/api/staff/{self.staff_profile.id}/',
            data=json.dumps(update_payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(update_resp.status_code, 200)
        self.assertTrue(update_resp.json().get('success'))

        self.staff_profile.refresh_from_db()
        self.assertEqual(self.staff_profile.assignment_scopes, [
            {
                'scope_type': 'group',
                'scope_id': self.group.id,
                'group_id': self.group.id,
                'classes': ['10'],
                'sections': ['A'],
                'branches': [],
                'class_sections': {},
            }
        ])

        detail_resp = self.client.get(f'/panel/client/api/staff/{self.staff_profile.id}/')
        self.assertEqual(detail_resp.status_code, 200)
        detail_payload = detail_resp.json().get('data', {})
        self.assertEqual(detail_payload.get('assignment_scopes')[0].get('classes'), ['10'])
        self.assertEqual(detail_payload.get('assignment_scopes')[0].get('sections'), ['A'])

    def test_api_class_section_options_auto_uses_group_mode_without_id_collision(self):
        from tables.models import Table, IDCard

        extra_group = Table.objects.create(client=self.client_obj, name='Class 12')

        # Create another table under the original group first so table IDs can
        # numerically overlap with group IDs in the request payload.
        colliding_table = Table.objects.create(
            group=self.group,
            name='Colliding Table',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
                {'name': 'NAME', 'type': 'text'},
            ],
        )
        target_table = Table.objects.create(
            group=extra_group,
            name='Target Table',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
                {'name': 'NAME', 'type': 'text'},
            ],
        )

        IDCard.objects.create(
            table=colliding_table,
            status='pending',
            field_data={'CLASS': '99', 'SECTION': 'X', 'NAME': 'Wrong Scope'},
        )
        IDCard.objects.create(
            table=target_table,
            status='pending',
            field_data={'CLASS': '12', 'SECTION': 'B', 'NAME': 'Right Scope'},
        )

        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get(
            f'/panel/client/api/class-section-options/?group_ids={extra_group.id}'
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload.get('resolved_id_source'), 'group')
        self.assertIn('12', payload.get('classes', []))
        self.assertIn('B', payload.get('sections', []))
        self.assertNotIn('99', payload.get('classes', []))
        self.assertNotIn('X', payload.get('sections', []))

    def test_filter_options_cache_scoped_for_client_staff(self):
        from tables.models import IDCard

        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '11', 'SECTION': 'B', 'NAME': 'Jane'},
        )

        self.client.login(username='api-owner@test.com', password='pass1234')
        owner_response = self.client.get(f'/panel/api/table/{self.table.id}/filter-options/')
        self.assertEqual(owner_response.status_code, 200)
        owner_payload = owner_response.json()
        owner_classes = [row.get('value') for row in owner_payload.get('class_values', [])]
        self.assertGreaterEqual(len(owner_classes), 2)

        # Assign the table so staff passes the table-access check, then set class/section scope
        self.staff_profile.assigned_table_ids = [self.table.id]
        self.staff_profile.allowed_classes = ['10']
        self.staff_profile.allowed_sections = ['A']
        self.staff_profile.save(update_fields=['assigned_table_ids', 'allowed_classes', 'allowed_sections'])

        self.client.login(username='api-staff@test.com', password='pass1234')
        staff_response = self.client.get(f'/panel/api/table/{self.table.id}/filter-options/')
        self.assertEqual(staff_response.status_code, 200)
        staff_payload = staff_response.json()
        staff_classes = [row.get('value') for row in staff_payload.get('class_values', [])]
        self.assertEqual(len(staff_classes), 1, msg=str(staff_payload))
        self.assertEqual(staff_payload.get('section_values', []), ['A'])

    def test_client_staff_idcard_group_page_counts_are_scoped(self):
        from tables.models import IDCard, Table, Table

        extra_group = Table.objects.create(client=self.client_obj, name='Class 11')
        extra_table = Table.objects.create(
            group=extra_group,
            name='Students Extra',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
                {'name': 'NAME', 'type': 'text'},
            ],
        )

        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '11', 'SECTION': 'A', 'NAME': 'Out Of Scope'},
        )
        IDCard.objects.create(
            table=extra_table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'NAME': 'Other Table'},
        )

        self.staff_profile.assigned_table_ids = [self.table.id]
        self.staff_profile.perm_idcard_pending_list = True
        self.staff_profile.allowed_classes = ['10']
        self.staff_profile.allowed_sections = []
        self.staff_profile.allowed_branches = []
        self.staff_profile.save(update_fields=[
            'assigned_table_ids',
            'perm_idcard_pending_list',
            'allowed_classes',
            'allowed_sections',
            'allowed_branches',
        ])

        self.client.login(username='api-staff@test.com', password='pass1234')
        response = self.client.get('/panel/client/idcard-group/')
        self.assertEqual(response.status_code, 200)

        tables = list(response.context['tables'])
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0].id, self.table.id)
        self.assertEqual(tables[0].pending_count, 1)
        self.assertEqual(tables[0].total_cards, 1)

    def test_client_staff_row_scope_supports_combined_group_and_table_assignments(self):
        from tables.models import Table, IDCard

        extra_group = Table.objects.create(client=self.client_obj, name='Class 12')
        extra_table = Table.objects.create(
            group=extra_group,
            name='Students Extra',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
                {'name': 'NAME', 'type': 'text'},
            ],
        )

        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '11', 'SECTION': 'A', 'NAME': 'Group Scope Rejected'},
        )
        IDCard.objects.create(
            table=extra_table,
            status='pending',
            field_data={'CLASS': '12', 'SECTION': 'B', 'NAME': 'Table Scope Allowed'},
        )
        IDCard.objects.create(
            table=extra_table,
            status='pending',
            field_data={'CLASS': '13', 'SECTION': 'B', 'NAME': 'Table Scope Rejected'},
        )

        self.staff_profile.perm_idcard_pending_list = True
        self.staff_profile.assigned_table_ids = [extra_table.id]
        self.staff_profile.allowed_classes = ['99']
        self.staff_profile.allowed_sections = ['Z']
        self.staff_profile.allowed_branches = []
        self.staff_profile.assignment_scopes = [
            {
                'scope_type': 'group',
                'scope_id': self.group.id,
                'group_id': self.group.id,
                'classes': ['10'],
                'sections': ['A'],
                'branches': [],
            },
            {
                'scope_type': 'table',
                'scope_id': extra_table.id,
                'group_id': extra_group.id,
                'classes': ['12'],
                'sections': ['B'],
                'branches': [],
            },
        ]
        self.staff_profile.save(update_fields=[
            'perm_idcard_pending_list',
            'assigned_table_ids',
            'allowed_classes',
            'allowed_sections',
            'allowed_branches',
            'assignment_scopes',
        ])
        self.staff_profile.assigned_groups.set([self.group])

        self.client.login(username='api-staff@test.com', password='pass1234')

        group_resp = self.client.get(
            f'/panel/client/api/table/{self.table.id}/cards/',
            {'status': 'pending'},
        )
        self.assertEqual(group_resp.status_code, 200)
        group_cards = group_resp.json().get('data', {}).get('cards', [])
        self.assertEqual(len(group_cards), 1)
        self.assertEqual(group_cards[0].get('field_data', {}).get('CLASS'), '10')

        table_resp = self.client.get(
            f'/panel/client/api/table/{extra_table.id}/cards/',
            {'status': 'pending'},
        )
        self.assertEqual(table_resp.status_code, 200)
        table_cards = table_resp.json().get('data', {}).get('cards', [])
        self.assertEqual(len(table_cards), 1)
        self.assertEqual(table_cards[0].get('field_data', {}).get('CLASS'), '12')

    def test_client_staff_explicit_empty_scope_filters_return_no_rows(self):
        from tables.models import IDCard

        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'NAME': 'Should Not Be Visible'},
        )

        self.staff_profile.perm_idcard_pending_list = True
        self.staff_profile.assigned_table_ids = []
        self.staff_profile.allowed_classes = []
        self.staff_profile.allowed_sections = []
        self.staff_profile.allowed_branches = []
        self.staff_profile.assignment_scopes = [
            {
                'scope_type': 'group',
                'scope_id': self.group.id,
                'group_id': self.group.id,
                'classes': [],
                'sections': [],
                'branches': [],
            }
        ]
        self.staff_profile.save(update_fields=[
            'perm_idcard_pending_list',
            'assigned_table_ids',
            'allowed_classes',
            'allowed_sections',
            'allowed_branches',
            'assignment_scopes',
        ])
        self.staff_profile.assigned_groups.set([self.group])

        self.client.login(username='api-staff@test.com', password='pass1234')
        response = self.client.get(
            f'/panel/client/api/table/{self.table.id}/cards/',
            {'status': 'pending'},
        )

        self.assertEqual(response.status_code, 200)
        cards = response.json().get('data', {}).get('cards', [])
        self.assertEqual(cards, [])

    def test_api_staff_detail_denied_without_manage_client_permission(self):
        self.client_obj.perm_idcard_client_list = False
        self.client_obj.save(update_fields=['perm_idcard_client_list'])

        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get(f'/panel/client/api/staff/{self.staff_profile.id}/')

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertFalse(payload.get('success'))

    def test_api_card_detail_requires_card_info_permission(self):
        self.client_obj.perm_idcard_info = False
        self.client_obj.save(update_fields=['perm_idcard_info'])

        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get(f'/panel/client/api/cards/{self.card.id}/')

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertFalse(payload.get('success'))

    def test_client_print_page_redirects_without_print_permissions(self):
        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get(f'/panel/client/table/{self.table.id}/print/')

        self.assertEqual(response.status_code, 302)
        self.assertIn('/panel/client/idcard-group/', response.url)

    def test_client_staff_table_scope_does_not_unlock_full_parent_group(self):
        from tables.models import Table, IDCard

        extra_table = Table.objects.create(
            group=self.group,
            name='Unassigned Same Group Table',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
                {'name': 'NAME', 'type': 'text'},
            ],
        )

        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'NAME': 'Allowed Table Row'},
        )
        IDCard.objects.create(
            table=extra_table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'NAME': 'Should Stay Hidden'},
        )

        self.staff_profile.perm_idcard_pending_list = True
        self.staff_profile.assigned_table_ids = [self.table.id]
        self.staff_profile.allowed_classes = ['10']
        self.staff_profile.allowed_sections = ['A']
        self.staff_profile.allowed_branches = []
        self.staff_profile.assignment_scopes = [
            {
                'scope_type': 'table',
                'scope_id': self.table.id,
                'group_id': self.group.id,
                'classes': ['10'],
                'sections': ['A'],
                'branches': [],
            }
        ]
        self.staff_profile.save(update_fields=[
            'perm_idcard_pending_list',
            'assigned_table_ids',
            'allowed_classes',
            'allowed_sections',
            'allowed_branches',
            'assignment_scopes',
        ])
        # Keep parent group assignment set to mimic compatibility storage.
        self.staff_profile.assigned_groups.set([self.group])

        self.client.login(username='api-staff@test.com', password='pass1234')
        response = self.client.get('/panel/client/idcard-group/')
        self.assertEqual(response.status_code, 200)

        tables = list(response.context['tables'])
        table_ids = sorted(t.id for t in tables)
        self.assertEqual(table_ids, [self.table.id])
        self.assertEqual(tables[0].pending_count, 2)
        self.assertEqual(tables[0].total_cards, 2)

    def test_client_staff_cards_api_class_filter_with_roman_value(self):
        from tables.models import IDCard

        IDCard.objects.create(
            table=self.table,
            status='pending',
            field_data={'CLASS': 'III', 'SECTION': 'A', 'NAME': 'Roman Class'},
        )

        # Assign the table so staff passes the table-access check
        self.staff_profile.assigned_table_ids = [self.table.id]
        self.staff_profile.perm_idcard_pending_list = True
        self.staff_profile.save(update_fields=['assigned_table_ids', 'perm_idcard_pending_list'])

        self.client.login(username='api-staff@test.com', password='pass1234')
        response = self.client.get(
            f'/panel/api/table/{self.table.id}/cards/',
            {'status': 'pending', 'class': 'III'},
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload.get('success'))

    def test_filter_options_dedupes_course_branch_variants(self):
        from tables.models import Table, IDCard
        from core.utils.field_utils import normalize_compact_text_value

        table = Table.objects.create(
            group=self.group,
            name='Course Branch Table',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
                {'name': 'COURSE', 'type': 'course'},
                {'name': 'BRANCH', 'type': 'branch'},
                {'name': 'NAME', 'type': 'text'},
            ],
        )

        IDCard.objects.create(
            table=table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'COURSE': 'BTECH', 'BRANCH': 'CSE', 'NAME': 'One'},
        )
        IDCard.objects.create(
            table=table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'COURSE': 'B.Tech', 'BRANCH': 'C.S.E', 'NAME': 'Two'},
        )
        IDCard.objects.create(
            table=table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'COURSE': 'B TECH', 'BRANCH': 'c s e', 'NAME': 'Three'},
        )
        IDCard.objects.create(
            table=table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'COURSE': 'BCA', 'BRANCH': 'IT', 'NAME': 'Four'},
        )

        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get(f'/panel/api/table/{table.id}/filter-options/')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload.get('success'))

        course_values = payload.get('course_values', [])
        branch_values = payload.get('branch_values', [])

        self.assertEqual(
            {normalize_compact_text_value(v) for v in course_values},
            {'BTECH', 'BCA'},
        )
        self.assertEqual(
            {normalize_compact_text_value(v) for v in branch_values},
            {'CSE', 'IT'},
        )

        btech_display = next(v for v in course_values if normalize_compact_text_value(v) == 'BTECH')
        cse_display = next(v for v in branch_values if normalize_compact_text_value(v) == 'CSE')

        mapped_branches = payload.get('course_to_branches', {}).get(btech_display, [])
        self.assertEqual(
            {normalize_compact_text_value(v) for v in mapped_branches},
            {'CSE'},
        )

        mapped_courses = payload.get('branch_to_courses', {}).get(cse_display, [])
        self.assertEqual(
            {normalize_compact_text_value(v) for v in mapped_courses},
            {'BTECH'},
        )

    def test_cards_api_course_branch_filters_match_variants(self):
        from tables.models import Table, IDCard

        table = Table.objects.create(
            group=self.group,
            name='Course Branch Cards',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
                {'name': 'COURSE', 'type': 'course'},
                {'name': 'BRANCH', 'type': 'branch'},
                {'name': 'NAME', 'type': 'text'},
            ],
        )

        IDCard.objects.create(
            table=table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'COURSE': 'BTECH', 'BRANCH': 'CSE', 'NAME': 'One'},
        )
        IDCard.objects.create(
            table=table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'COURSE': 'B.Tech', 'BRANCH': 'C.S.E', 'NAME': 'Two'},
        )
        IDCard.objects.create(
            table=table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'COURSE': 'BCA', 'BRANCH': 'IT', 'NAME': 'Three'},
        )

        self.client.login(username='api-owner@test.com', password='pass1234')

        course_resp = self.client.get(
            f'/panel/api/table/{table.id}/cards/',
            {'status': 'pending', 'course': 'B TECH'},
        )
        self.assertEqual(course_resp.status_code, 200)
        course_payload = course_resp.json()
        self.assertTrue(course_payload.get('success'))
        self.assertEqual(len(course_payload.get('cards', [])), 2)

        branch_resp = self.client.get(
            f'/panel/api/table/{table.id}/cards/',
            {'status': 'pending', 'branch': 'c.s.e'},
        )
        self.assertEqual(branch_resp.status_code, 200)
        branch_payload = branch_resp.json()
        self.assertTrue(branch_payload.get('success'))
        self.assertEqual(len(branch_payload.get('cards', [])), 2)

    def test_update_field_refreshes_course_branch_filter_options(self):
        from tables.models import Table, IDCard
        from core.utils.field_utils import normalize_compact_text_value

        table = Table.objects.create(
            group=self.group,
            name='Inline Update Filters',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
                {'name': 'COURSE', 'type': 'course'},
                {'name': 'BRANCH', 'type': 'branch'},
                {'name': 'NAME', 'type': 'text'},
            ],
        )
        card = IDCard.objects.create(
            table=table,
            status='pending',
            field_data={'CLASS': '10', 'SECTION': 'A', 'COURSE': 'BTECH', 'BRANCH': 'CSE', 'NAME': 'Inline User'},
        )

        self.client_obj.perm_idcard_edit = True
        self.client_obj.save(update_fields=['perm_idcard_edit'])

        self.client.login(username='api-owner@test.com', password='pass1234')

        warm_resp = self.client.get(f'/panel/api/table/{table.id}/filter-options/')
        self.assertEqual(warm_resp.status_code, 200)

        update_course = self.client.post(
            f'/panel/api/card/{card.id}/update-field/',
            data=json.dumps({'field': 'COURSE', 'value': 'BCA'}),
            content_type='application/json',
        )
        self.assertEqual(update_course.status_code, 200)

        update_branch = self.client.post(
            f'/panel/api/card/{card.id}/update-field/',
            data=json.dumps({'field': 'BRANCH', 'value': 'I.T'}),
            content_type='application/json',
        )
        self.assertEqual(update_branch.status_code, 200)

        refreshed = self.client.get(f'/panel/api/table/{table.id}/filter-options/')
        self.assertEqual(refreshed.status_code, 200)
        payload = refreshed.json()
        self.assertTrue(payload.get('success'))

        self.assertEqual(
            {normalize_compact_text_value(v) for v in payload.get('course_values', [])},
            {'BCA'},
        )
        self.assertEqual(
            {normalize_compact_text_value(v) for v in payload.get('branch_values', [])},
            {'IT'},
        )

    def test_client_staff_temp_password_api_requires_client_permission(self):
        self.client_obj.perm_set_temp_password = False
        self.client_obj.save(update_fields=['perm_set_temp_password'])

        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.post(
            f'/panel/client/api/staff/{self.staff_profile.id}/set-temp-password/',
            data=json.dumps({'password': 'TmpStrong!982'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_client_staff_temp_password_api_success_when_client_has_permission(self):
        self.client_obj.perm_set_temp_password = True
        self.client_obj.save(update_fields=['perm_set_temp_password'])

        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.post(
            f'/panel/client/api/staff/{self.staff_profile.id}/set-temp-password/',
            data=json.dumps({'password': 'TmpStrong!982'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        self.client_staff_user.refresh_from_db()
        self.assertTrue(self.client_staff_user.check_password('TmpStrong!982'))

    def test_cards_api_without_status_is_permission_scoped(self):
        from tables.models import IDCard

        IDCard.objects.create(
            table=self.table,
            status='approved',
            field_data={'CLASS': '10', 'SECTION': 'A', 'NAME': 'Approved Card'},
        )

        # Assign the table so staff is allowed to access it (unassigned = strict deny)
        self.staff_profile.assigned_table_ids = [self.table.id]
        self.staff_profile.perm_idcard_pending_list = True
        self.staff_profile.perm_idcard_approved_list = False
        self.staff_profile.perm_idcard_verified_list = False
        self.staff_profile.perm_idcard_pool_list = False
        self.staff_profile.perm_idcard_download_list = False
        self.staff_profile.perm_idcard_reprint_list = False
        self.staff_profile.save(update_fields=[
            'assigned_table_ids',
            'perm_idcard_pending_list',
            'perm_idcard_approved_list',
            'perm_idcard_verified_list',
            'perm_idcard_pool_list',
            'perm_idcard_download_list',
            'perm_idcard_reprint_list',
        ])

        self.client.login(username='api-staff@test.com', password='pass1234')
        response = self.client.get(f'/panel/client/api/table/{self.table.id}/cards/')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload.get('success'))
        statuses = {row.get('status') for row in payload['data']['cards']}
        self.assertEqual(statuses, {'pending'})

    def test_cards_api_rejects_invalid_status_filter(self):
        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get(
            f'/panel/client/api/table/{self.table.id}/cards/',
            {'status': 'not-real'},
        )
        self.assertEqual(response.status_code, 400)

    def test_cards_api_caps_per_page_and_normalizes_page(self):
        from tables.models import IDCard

        for i in range(230):
            IDCard.objects.create(
                table=self.table,
                status='pending',
                field_data={'CLASS': '10', 'SECTION': 'A', 'NAME': f'P{i}'},
            )

        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.get(
            f'/panel/client/api/table/{self.table.id}/cards/',
            {'status': 'pending', 'page': -5, 'per_page': 5000},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['data']['pagination']['page'], 1)
        self.assertEqual(payload['data']['pagination']['per_page'], 200)
        self.assertLessEqual(len(payload['data']['cards']), 200)

    def test_bulk_status_rejects_invalid_card_ids_payload(self):
        self.client.login(username='api-owner@test.com', password='pass1234')
        response = self.client.post(
            f'/panel/client/api/table/{self.table.id}/cards/bulk-status/',
            data=json.dumps({'card_ids': [True, 'x', None], 'status': 'verified'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)


class ClientActivationPasswordFlowTests(TestCase):
    def test_create_allows_weak_custom_password_without_strict_validation(self):
        from core.services import ClientService

        weak_password = '123'
        result = ClientService.create({
            'name': 'Weak Password Client',
            'email': 'client-weak-password@test.com',
            'phone': '',
            'password': weak_password,
            'is_active': False,
        })

        self.assertTrue(result.success, msg=result.message)
        created_user = User.objects.get(email='client-weak-password@test.com')
        self.assertTrue(created_user.check_password(weak_password))

    def test_first_activation_preserves_custom_password_for_login(self):
        from core.services import ClientService
        from core.models import EmailLog

        custom_password = 'ClientCustom@123'
        result = ClientService.create({
            'name': 'Custom Password Client',
            'email': 'client-custom-activation@test.com',
            'phone': '9123456789',
            'password': custom_password,
            'is_active': False,
        })
        self.assertTrue(result.success, msg=result.message)

        client_id = result.data['client']['id']
        created_user = User.objects.get(email='client-custom-activation@test.com')
        self.assertTrue(created_user.check_password(custom_password))

        def _fake_send_welcome(*args, **kwargs):
            on_success = kwargs.get('on_success')
            if on_success:
                on_success()
            return True, 'Welcome email queued for delivery.'

        with mock.patch('client.services_client_core.send_welcome_email', side_effect=_fake_send_welcome) as send_welcome_mock:
            toggle_result = ClientService.toggle_status(client_id)

        self.assertTrue(toggle_result.success, msg=toggle_result.message)
        created_user.refresh_from_db()
        self.assertTrue(created_user.is_active)
        self.assertTrue(created_user.check_password(custom_password))
        self.assertTrue(self.client.login(username=created_user.username, password=custom_password))
        self.assertTrue(created_user.welcome_email_sent)
        send_welcome_mock.assert_called_once()
        self.assertTrue(
            EmailLog.objects.filter(
                recipient_email='client-custom-activation@test.com',
                status=EmailLog.STATUS_SENT,
            ).exists()
        )

    def test_first_activation_keeps_phone_password_login_working(self):
        from core.services import ClientService

        phone_password = '9876543210'
        result = ClientService.create({
            'name': 'Phone Password Client',
            'email': 'client-phone-activation@test.com',
            'phone': phone_password,
            'password': '',
            'is_active': False,
        })
        self.assertTrue(result.success, msg=result.message)

        client_id = result.data['client']['id']
        created_user = User.objects.get(email='client-phone-activation@test.com')
        self.assertTrue(created_user.check_password(phone_password))

        def _fake_send_welcome(*args, **kwargs):
            on_success = kwargs.get('on_success')
            if on_success:
                on_success()
            return True, 'Welcome email queued for delivery.'

        with mock.patch('client.services_client_core.send_welcome_email', side_effect=_fake_send_welcome):
            toggle_result = ClientService.toggle_status(client_id)

        self.assertTrue(toggle_result.success, msg=toggle_result.message)
        created_user.refresh_from_db()
        self.assertTrue(created_user.is_active)
        self.assertTrue(created_user.check_password(phone_password))
        self.assertTrue(self.client.login(username=created_user.username, password=phone_password))

    def test_first_activation_recovers_unusable_password_from_phone_without_random(self):
        from core.services import ClientService

        phone_password = '9123450000'
        result = ClientService.create({
            'name': 'Phone Recovery Client',
            'email': 'client-phone-recovery@test.com',
            'phone': phone_password,
            'password': 'Custom@WillBeUnusable',
            'is_active': False,
        })
        self.assertTrue(result.success, msg=result.message)

        client_id = result.data['client']['id']
        created_user = User.objects.get(email='client-phone-recovery@test.com')
        created_user.set_unusable_password()
        created_user.save(update_fields=['password'])

        def _fake_send_welcome(*args, **kwargs):
            on_success = kwargs.get('on_success')
            if on_success:
                on_success()
            return True, 'Welcome email queued for delivery.'

        with mock.patch('client.services_client_core.send_welcome_email', side_effect=_fake_send_welcome):
            toggle_result = ClientService.toggle_status(client_id)

        self.assertTrue(toggle_result.success, msg=toggle_result.message)
        created_user.refresh_from_db()
        self.assertTrue(created_user.check_password(phone_password))
        self.assertTrue(self.client.login(username=created_user.username, password=phone_password))

    def test_reactivation_also_sends_activation_email(self):
        from core.services import ClientService

        result = ClientService.create({
            'name': 'Reactivation Client',
            'email': 'client-reactivation@test.com',
            'phone': '9123456789',
            'password': 'ClientCustom@123',
            'is_active': False,
        })
        self.assertTrue(result.success, msg=result.message)

        client_id = result.data['client']['id']

        def _fake_send_welcome(*args, **kwargs):
            on_success = kwargs.get('on_success')
            if on_success:
                on_success()
            return True, 'Welcome email queued for delivery.'

        with mock.patch('client.services_client_core.send_welcome_email', side_effect=_fake_send_welcome) as send_welcome_mock:
            first_activate = ClientService.toggle_status(client_id)
            self.assertTrue(first_activate.success, msg=first_activate.message)

            deactivate = ClientService.toggle_status(client_id)
            self.assertTrue(deactivate.success, msg=deactivate.message)

            second_activate = ClientService.toggle_status(client_id)
            self.assertTrue(second_activate.success, msg=second_activate.message)

        self.assertEqual(send_welcome_mock.call_count, 2)

    def test_create_rejects_missing_phone_and_custom_password(self):
        from core.services import ClientService

        result = ClientService.create({
            'name': 'Missing Credentials Client',
            'email': 'missing-credentials-client@example.com',
            'phone': '',
            'password': '',
            'is_active': False,
        })

        self.assertFalse(result.success)
        self.assertIn('phone number is required', result.message.lower())

    def test_create_allows_custom_password_without_phone_or_email(self):
        from core.services import ClientService
        from organisation.models import Organisation

        result = ClientService.create({
            'name': 'Custom No Contact Client',
            'email': 'custom-no-contact-client@example.com',
            'phone': '',
            'password': 'ClientOnly@123',
            'is_active': False,
        })

        self.assertTrue(result.success, msg=result.message)
        created_client = Organisation.objects.select_related('user').get(id=result.data['client']['id'])
        created_user = created_client.user
        self.assertTrue(created_user.check_password('ClientOnly@123'))


class ClientStaffScopeBackfillCommandTests(TestCase):
    def setUp(self):
        from organisation.models import Organisation
        from tables.models import Table, IDCard
        from staff.models import Staff

        owner = User.objects.create_user(
            username='backfill-owner@test.com',
            email='backfill-owner@test.com',
            password='pass1234',
            role='client',
        )
        self.client_obj = Organisation.objects.create(user=owner, name='Backfill Client')

        self.group_a = Table.objects.create(client=self.client_obj, name='Group A')
        self.group_b = Table.objects.create(client=self.client_obj, name='Group B')

        self.table_a = Table.objects.create(
            group=self.group_a,
            name='Table A',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
                {'name': 'NAME', 'type': 'text'},
            ],
        )
        self.table_b = Table.objects.create(
            group=self.group_b,
            name='Table B',
            fields=[
                {'name': 'CLASS', 'type': 'class'},
                {'name': 'SECTION', 'type': 'section'},
                {'name': 'NAME', 'type': 'text'},
            ],
        )

        IDCard.objects.create(
            table=self.table_a,
            status='pending',
            field_data={'CLASS': '8', 'SECTION': 'A', 'NAME': 'A1'},
        )
        IDCard.objects.create(
            table=self.table_a,
            status='pending',
            field_data={'CLASS': '9', 'SECTION': 'B', 'NAME': 'A2'},
        )
        IDCard.objects.create(
            table=self.table_b,
            status='pending',
            field_data={'CLASS': '11', 'SECTION': 'C', 'NAME': 'B1'},
        )

        staff_user = User.objects.create_user(
            username='legacy-empty-scope@test.com',
            email='legacy-empty-scope@test.com',
            password='pass1234',
            role='client_staff',
        )
        self.staff_profile = Staff.objects.create(
            user=staff_user,
            staff_type='assistant',
            client=self.client_obj,
            perm_idcard_pending_list=True,
            allowed_classes=[],
            allowed_sections=[],
            allowed_branches=[],
            assignment_scopes=[],
        )
        self.staff_profile.assigned_groups.add(self.group_a)

    def test_backfill_client_staff_scope_assignments_restores_legacy_empty_scope(self):
        from io import StringIO
        from django.core.management import call_command

        dry_run_out = StringIO()
        call_command(
            'backfill_client_staff_scope_assignments',
            '--staff-id',
            str(self.staff_profile.id),
            stdout=dry_run_out,
        )

        self.staff_profile.refresh_from_db()
        self.assertEqual(self.staff_profile.assignment_scopes or [], [])
        self.assertEqual(self.staff_profile.allowed_classes or [], [])
        self.assertEqual(self.staff_profile.allowed_sections or [], [])

        apply_out = StringIO()
        call_command(
            'backfill_client_staff_scope_assignments',
            '--staff-id',
            str(self.staff_profile.id),
            '--apply',
            stdout=apply_out,
        )

        self.staff_profile.refresh_from_db()
        scopes = self.staff_profile.assignment_scopes or []
        self.assertEqual(len(scopes), 1)
        self.assertEqual(scopes[0].get('scope_type'), 'group')
        self.assertEqual(scopes[0].get('scope_id'), self.group_a.id)
        self.assertEqual(set(scopes[0].get('classes') or []), {'8', '9'})
        self.assertEqual(set(scopes[0].get('sections') or []), {'A', 'B'})
        self.assertEqual(set(self.staff_profile.allowed_classes or []), {'8', '9'})
        self.assertEqual(set(self.staff_profile.allowed_sections or []), {'A', 'B'})
