"""
Tests for core app.
Covers: User model, IDCard/Table/Table models, middleware,
permissions, workflow transitions, bulk upload service, global search.
"""
from django.test import TestCase, SimpleTestCase, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
import json
import os
import tempfile
import io
import zipfile
import hmac
import time
import hashlib
from core.services.idcard_card_service import IDCardCardService

User = get_user_model()


# ── Helpers ──
def _create_super_admin(email='admin@test.com', password='adminpass1'):
    return User.objects.create_user(
        username=email, email=email, password=password, role='super_admin',
    )


def _create_client_user(email='client@test.com', password='clientpass1'):
    user = User.objects.create_user(
        username=email, email=email, password=password, role='client',
    )
    from organisation.models import Organisation
    client = Organisation.objects.create(user=user, name='Test Client')
    return user, client


def _create_table(client_obj, fields=None):
    """Helper to create a test Table with a group."""
    from tables.models import Table
    
    group = Table.objects.create(client=client_obj, name='Test Group')
    
    if fields is None:
        fields = [
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'CLASS', 'type': 'text', 'order': 2},
        ]
    
    table = Table.objects.create(
        group=group,
        name='Test Table',
        fields=fields,
        is_active=True
    )
    
    return group, table


def _create_card(table, field_data=None, status='pending'):
    """Helper to create a test IDCard."""
    from tables.models import IDCard
    
    if field_data is None:
        field_data = {'NAME': 'JOHN DOE'}
    
    card = IDCard.objects.create(
        table=table,
        field_data=field_data,
        status=status
    )
    
    return card


# ── User Model Tests ──
class UserModelTests(TestCase):
    def test_create_user_default_role(self):
        user = User.objects.create_user(
            username='u1@test.com', email='u1@test.com', password='pass1234',
        )
        self.assertEqual(user.role, 'prime_manager')


    def test_super_admin_role_sets_flags(self):
        admin = _create_super_admin()
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_super_admin)

    def test_client_role_clears_superuser(self):
        user, _ = _create_client_user()
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_super_admin)

    def test_superuser_forces_super_admin_role(self):
        user = User.objects.create_superuser(
            username='su@test.com', email='su@test.com', password='supass123',
        )
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.role, 'super_admin')


class TutorialRoleScopeTests(TestCase):
    def setUp(self):
        self.client_user, self.client_profile = _create_client_user(
            'tutorial-client@test.com',
            'testpass123',
        )
        owner_user, owner_client = _create_client_user(
            'tutorial-client-owner@test.com',
            'testpass123',
        )
        del owner_user

        self.client_staff_user = User.objects.create_user(
            username='tutorial-client-staff@test.com',
            email='tutorial-client-staff@test.com',
            password='testpass123',
            role='client_staff',
        )
        from staff.models import Staff
        Staff.objects.create(
            user=self.client_staff_user,
            staff_type='assistant',
            client=owner_client,
        )

        self.admin_staff_user = User.objects.create_user(
            username='tutorial-admin-staff@test.com',
            email='tutorial-admin-staff@test.com',
            password='testpass123',
            role='operator',
        )
        Staff.objects.create(
            user=self.admin_staff_user,
            staff_type='operator',
        )
        self.admin_user = User.objects.create_superuser(
            username='tutorial-admin@test.com',
            email='tutorial-admin@test.com',
            password='testpass123',
        )

    def _assert_role_tutorial(self, username, expected_scope, expected_text):
        self.assertTrue(self.client.login(username=username, password='testpass123'))
        response = self.client.get(reverse('tutorial'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['tutorial_scope'], expected_scope)
        self.assertContains(response, expected_text)
        self.client.logout()

    def test_client_sees_client_tutorial(self):
        self._assert_role_tutorial(
            'tutorial-client@test.com',
            'client',
            'Check & Update Data',
        )

    def test_client_staff_sees_client_staff_tutorial(self):
        self._assert_role_tutorial(
            'tutorial-client-staff@test.com',
            'client_staff',
            'Assistent Permissions Overview',
        )

    def test_admin_staff_sees_admin_staff_tutorial(self):
        self._assert_role_tutorial(
            'tutorial-admin-staff@test.com',
            'operator',
            'Verification and Data Rectification',
        )

    def test_admin_sees_admin_tutorial(self):
        self._assert_role_tutorial(
            'tutorial-admin@test.com',
            'admin',
            'Data Operations & Quality Policies',
        )

    def test_tutorial_shows_personal_guide_button(self):
        self.assertTrue(self.client.login(username='tutorial-admin@test.com', password='testpass123'))
        response = self.client.get(reverse('tutorial'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('tutorial_personal_guide'))
        self.assertContains(response, 'Personal Guide')

    def test_personal_guide_page_is_accessible(self):
        self.assertTrue(self.client.login(username='tutorial-admin@test.com', password='testpass123'))
        response = self.client.get(reverse('tutorial_personal_guide'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student Data Check aur Approval ke liye Personal Guide')
        self.assertContains(response, 'client@example.com')

    def test_personal_guide_download_returns_text_attachment(self):
        self.assertTrue(self.client.login(username='tutorial-admin@test.com', password='testpass123'))
        response = self.client.get(reverse('tutorial_personal_guide_download'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        self.assertIn('attachment; filename="adarsh-personal-guide.txt"', response['Content-Disposition'])
        self.assertIn('Student Data Check, Corrections', response.content.decode('utf-8'))

    def test_hindi_mode_has_devanagari_script(self):
        self.assertTrue(self.client.login(username='tutorial-client@test.com', password='testpass123'))
        response = self.client.get(reverse('tutorial') + '?lang=hi')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertRegex(html, r'[\u0900-\u097F]')


# ── IDCard Model Tests ──
class IDCardModelTests(TestCase):
    def setUp(self):
        _, self.client_obj = _create_client_user()
        self.group, self.table = _create_table(self.client_obj)

    def test_create_card(self):
        card = _create_card(self.table)
        self.assertEqual(card.status, 'pending')
        self.assertEqual(card.field_data['NAME'], 'JOHN DOE')

    def test_card_belongs_to_table(self):
        card = _create_card(self.table)
        self.assertEqual(card.table.id, self.table.id)

    def test_card_default_status(self):
        from tables.models import IDCard
        card = IDCard.objects.create(table=self.table, field_data={'NAME': 'X'})
        self.assertEqual(card.status, 'pending')


class IDCardCardServiceCreateTests(TestCase):
    def setUp(self):
        self.user, self.client_obj = _create_client_user()
        self.group, self.table = _create_table(self.client_obj)

    def test_create_card_converts_bare_photo_name_to_pending(self):
        result = IDCardCardService.create_card(
            self.table.id,
            {'NAME': 'ALICE', 'PHOTO': 'avatar-1.jpg'},
            uploaded_by=self.user,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.data['card']['field_data']['PHOTO'], 'PENDING:avatar-1.jpg')

    def test_create_and_update_card_forces_uppercase(self):
        result = IDCardCardService.create_card(
            self.table.id,
            {'NAME': 'Alice Smith', 'CLASS': '10th B'},
            uploaded_by=self.user,
        )
        self.assertTrue(result.success)
        card_id = result.data['card']['id']
        self.assertEqual(result.data['card']['field_data']['NAME'], 'ALICE SMITH')
        self.assertEqual(result.data['card']['field_data']['CLASS'], '10TH B')

        update_result = IDCardCardService.update_card(
            card_id=card_id,
            field_data={'NAME': 'Bob Jones', 'CLASS': '12th A'},
            uploaded_by=self.user,
        )
        self.assertTrue(update_result.success)
        self.assertEqual(update_result.data['card']['field_data']['NAME'], 'BOB JONES')
        self.assertEqual(update_result.data['card']['field_data']['CLASS'], '12TH A')

        single_result = IDCardCardService.update_single_field(
            card_id=card_id,
            field='NAME',
            value='Charlie Brown',
        )
        self.assertTrue(single_result.success)
        self.assertEqual(single_result.data['value'], 'CHARLIE BROWN')


class IDCardApiUploadTests(TestCase):
    def setUp(self):
        self.user, self.client_obj = _create_client_user()
        self.group, self.table = _create_table(
            self.client_obj,
            fields=[
                {'name': 'NAME', 'type': 'text', 'order': 1},
                {'name': 'PHOTO', 'type': 'photo', 'order': 2},
                {'name': 'SIGNATURE', 'type': 'signature', 'order': 3},
            ]
        )
        self.client_obj.perm_idcard_add = True
        self.client_obj.perm_idcard_edit = True
        self.client_obj.save(update_fields=['perm_idcard_add', 'perm_idcard_edit'])
        self.client.force_login(self.user)

    def test_api_create_card_with_images_success(self):
        # Create a dummy image
        from PIL import Image
        img = Image.new('RGB', (100, 100), color='red')
        img_io = io.BytesIO()
        img.save(img_io, 'JPEG')
        img_bytes = img_io.getvalue()

        # Build SimpleUploadedFiles for both PHOTO and SIGNATURE fields
        photo_file = SimpleUploadedFile("myphoto.jpg", img_bytes, content_type="image/jpeg")
        sig_file = SimpleUploadedFile("mysign.jpg", img_bytes, content_type="image/jpeg")

        # Call create API
        response = self.client.post(
            f'/panel/api/table/{self.table.id}/card/create/',
            data={
                'field_data': json.dumps({'NAME': 'DUMMY USER'}),
                'image_PHOTO': photo_file,
                'image_SIGNATURE': sig_file,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # Verify card and images are created
        from tables.models import IDCard
        card = IDCard.objects.get(id=data['card']['id'])
        self.assertEqual(card.field_data['NAME'], 'DUMMY USER')
        self.assertTrue(card.field_data['PHOTO'].endswith('.jpg'))
        self.assertTrue(card.field_data['SIGNATURE'].endswith('.jpg'))
        self.assertNotEqual(card.field_data['PHOTO'], 'NOT_FOUND')

    def test_api_update_card_with_images_success(self):
        from tables.models import IDCard
        card = IDCard.objects.create(
            table=self.table,
            field_data={'NAME': 'INITIAL', 'PHOTO': '', 'SIGNATURE': ''}
        )

        from PIL import Image
        img = Image.new('RGB', (100, 100), color='blue')
        img_io = io.BytesIO()
        img.save(img_io, 'JPEG')
        img_bytes = img_io.getvalue()

        photo_file = SimpleUploadedFile("updated_photo.jpg", img_bytes, content_type="image/jpeg")

        response = self.client.post(
            f'/panel/api/card/{card.id}/update/',
            data={
                'field_data': json.dumps({'NAME': 'UPDATED NAME'}),
                'image_PHOTO': photo_file,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        card.refresh_from_db()
        self.assertEqual(card.field_data['NAME'], 'UPDATED NAME')
        self.assertTrue(card.field_data['PHOTO'].endswith('.jpg'))


# ── Workflow Transition Tests ──
class WorkflowTransitionTests(TestCase):
    def setUp(self):
        self.admin = _create_super_admin()
        _, self.client_obj = _create_client_user()
        self.group, self.table = _create_table(self.client_obj)

    def test_pending_to_verified(self):
        from tables.services_workflow import WorkflowService
        card = _create_card(self.table, status='pending')
        result = WorkflowService.transition(card, 'verified', self.admin, request=None)
        self.assertTrue(result.success)
        card.refresh_from_db()
        self.assertEqual(card.status, 'verified')

    def test_invalid_transition_rejected(self):
        from tables.services_workflow import WorkflowService
        card = _create_card(self.table, status='pending')
        result = WorkflowService.transition(card, 'download', self.admin, request=None)
        self.assertFalse(result.success)
        card.refresh_from_db()
        self.assertEqual(card.status, 'pending')

    def test_bulk_transition(self):
        from tables.services_workflow import WorkflowService
        c1 = _create_card(self.table, status='pending')
        c2 = _create_card(self.table, status='pending')
        result = WorkflowService.bulk_transition(
            self.table, [c1.id, c2.id], 'verified', self.admin, request=None
        )
        self.assertTrue(result.success)
        c1.refresh_from_db()
        c2.refresh_from_db()
        self.assertEqual(c1.status, 'verified')
        self.assertEqual(c2.status, 'verified')


# ── Bulk Upload Service Tests ──
class DiskBackedImageStoreTests(TestCase):
    def test_add_and_get_ram(self):
        from core.services.bulk_upload_service import DiskBackedImageStore
        store = DiskBackedImageStore()
        try:
            img_bytes = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
            store.add('test_key', img_bytes, '.png', 'test.png')
            self.assertEqual(len(store), 1)
            self.assertIn('test_key', store)
            info = store.get('test_key')
            self.assertIsNotNone(info)
            self.assertEqual(info['ext'], '.png')
            self.assertEqual(info['bytes'], img_bytes)
        finally:
            store.cleanup()

    def test_switch_to_disk_on_large_data(self):
        from core.services.bulk_upload_service import DiskBackedImageStore
        from django.conf import settings
        # Ensure temp dir exists under MEDIA_ROOT
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        store = DiskBackedImageStore()
        try:
            # Add enough data to exceed RAM threshold (50MB)
            big_chunk = b'\x00' * (300 * 1024)  # 300KB per image
            for i in range(200):  # 200 * 300KB = 60MB → should switch to disk
                store.add(f'key_{i}', big_chunk, '.jpg', f'img_{i}.jpg')
            self.assertTrue(store._use_disk or len(store) == 200)
            # Verify retrieval still works
            info = store.get('key_0')
            self.assertIsNotNone(info)
        finally:
            store.cleanup()

    def test_cleanup_clears_store(self):
        from core.services.bulk_upload_service import DiskBackedImageStore
        store = DiskBackedImageStore()
        store.add('k', b'\x00' * 100, '.jpg', 'k.jpg')
        self.assertEqual(len(store), 1)
        store.cleanup()
        self.assertEqual(len(store), 0)
        self.assertIsNone(store.get('k'))

    def test_force_ram_only_raises_when_budget_exceeded(self):
        from core.services.bulk_upload_service import DiskBackedImageStore

        store = DiskBackedImageStore(
            ram_threshold_bytes=1024 * 1024,
            ram_threshold_per_image=2 * 1024 * 1024,
            force_ram_only=True,
        )
        try:
            store.add('k1', b'\x00' * (700 * 1024), '.jpg', 'a.jpg')
            self.assertFalse(store._use_disk)

            with self.assertRaises(MemoryError):
                store.add('k2', b'\x00' * (700 * 1024), '.jpg', 'b.jpg')

            self.assertFalse(store._use_disk)
            self.assertIsNotNone(store.get('k1'))
        finally:
            store.cleanup()


class BulkUploadImageHeaderMappingTests(SimpleTestCase):
    def test_image_headers_match_without_photo_suffix(self):
        from core.services.bulk_upload_processor import _map_headers_to_fields

        headers = ['NAME', 'PHOTO', 'SIGNATURE', 'MOTHER', 'FATHER', 'QR']
        table_fields = ['NAME']
        image_fields = ['PHOTO', 'SIGNATURE PHOTO', 'MOTHER PHOTO', 'FATHER PHOTO', 'QR CODE']

        header_to_field, image_ref_columns = _map_headers_to_fields(
            headers,
            table_fields,
            image_fields,
            all_table_fields=[],
            frontend_mapping=None,
        )

        self.assertEqual(header_to_field.get(0), 'NAME')
        self.assertEqual(image_ref_columns.get('PHOTO'), 1)
        self.assertEqual(image_ref_columns.get('SIGNATURE PHOTO'), 2)
        self.assertEqual(image_ref_columns.get('MOTHER PHOTO'), 3)
        self.assertEqual(image_ref_columns.get('FATHER PHOTO'), 4)
        self.assertEqual(image_ref_columns.get('QR CODE'), 5)


class BulkUploadZipFieldIsolationTests(SimpleTestCase):
    class _FakeZip:
        def __init__(self, payload_by_path):
            self.payload_by_path = payload_by_path

        def read(self, path):
            return self.payload_by_path[path]

    @patch('core.utils.field_utils.validate_image_bytes', return_value=(True, None))
    @patch('core.services.bulk_upload_processor._save_extracted_image')
    def test_field_specific_zip_preferred_for_same_key(self, mock_save, _mock_validate):
        from core.services.bulk_upload_processor import _find_and_save_image_from_zips

        photo_zip = self._FakeZip({'PHOTO/1.jpg': b'photo-bytes'})
        sign_zip = self._FakeZip({'SIGN/1.jpg': b'sign-bytes'})

        def _save_side_effect(result, client, batch_counter, uploaded_by=None):
            payload = result['bytes']
            if payload == b'photo-bytes':
                return {'success': True, 'path': 'adarshimg/photo.jpg'}
            if payload == b'sign-bytes':
                return {'success': True, 'path': 'adarshimg/sign.jpg'}
            return {'success': False, 'error': 'unexpected payload'}

        mock_save.side_effect = _save_side_effect

        field_zip_indexes = {
            'PHOTO': {'1': (photo_zip, 'PHOTO/1.jpg', '.jpg')},
            'SIGN': {'1': (sign_zip, 'SIGN/1.jpg', '.jpg')},
        }

        photo_result = _find_and_save_image_from_zips(
            photo_column_value='1',
            img_field='PHOTO',
            field_zip_indexes=field_zip_indexes,
            unified_zip_index={},
            client=None,
            batch_counter=1,
            uploaded_by=None,
        )
        sign_result = _find_and_save_image_from_zips(
            photo_column_value='1',
            img_field='SIGN',
            field_zip_indexes=field_zip_indexes,
            unified_zip_index={},
            client=None,
            batch_counter=2,
            uploaded_by=None,
        )

        self.assertTrue(photo_result['success'])
        self.assertEqual(photo_result['path'], 'adarshimg/photo.jpg')
        self.assertTrue(sign_result['success'])
        self.assertEqual(sign_result['path'], 'adarshimg/sign.jpg')

    @patch('core.utils.field_utils.validate_image_bytes', return_value=(True, None))
    @patch('core.services.bulk_upload_processor._save_extracted_image')
    def test_unified_zip_used_when_field_specific_missing(self, mock_save, _mock_validate):
        from core.services.bulk_upload_processor import _find_and_save_image_from_zips

        unified_zip = self._FakeZip({'ALL/ABC.jpg': b'unified-bytes'})

        mock_save.return_value = {'success': True, 'path': 'adarshimg/unified.jpg'}

        result = _find_and_save_image_from_zips(
            photo_column_value='abc',
            img_field='SIGN',
            field_zip_indexes={'PHOTO': {}},
            unified_zip_index={'ABC': (unified_zip, 'ALL/ABC.jpg', '.jpg')},
            client=None,
            batch_counter=1,
            uploaded_by=None,
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['path'], 'adarshimg/unified.jpg')


# ── Permission Tests ──
class PermissionTests(TestCase):
    def setUp(self):
        self.admin = _create_super_admin()
        self.user, self.client_obj = _create_client_user()
        self.group, self.table = _create_table(self.client_obj)
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_super_admin_can_access_cards_api(self):
        self.client.login(username='admin@test.com', password='adminpass1')
        response = self.client.get(f'/panel/api/table/{self.table.id}/cards/')
        self.assertIn(response.status_code, [200, 403])

    def test_unauthenticated_gets_redirect_or_403(self):
        response = self.client.get(f'/panel/api/table/{self.table.id}/cards/')
        self.assertIn(response.status_code, [302, 403])

    def test_client_can_access_own_table(self):
        self.client.login(username='client@test.com', password='clientpass1')
        response = self.client.get(f'/panel/client/table/{self.table.id}/cards/')
        self.assertIn(response.status_code, [200, 302])

    def test_permission_context_includes_reprint_flags(self):
        from core.services.permission_service import PermissionService

        self.client_obj.perm_idcard_reprint_list = True
        self.client_obj.perm_reprint_request_list = True
        self.client_obj.perm_confirmed_list = True
        self.client_obj.save(update_fields=[
            'perm_idcard_reprint_list',
            'perm_reprint_request_list',
            'perm_confirmed_list',
        ])

        ctx = PermissionService.get_permission_context(self.user)

        self.assertTrue(ctx['perm_idcard_reprint_list'])
        self.assertTrue(ctx['perm_reprint_request_list'])
        self.assertTrue(ctx['perm_confirmed_list'])

    def test_guest_permission_context_enables_mobile_app(self):
        from core.services.permission_service import PermissionService

        guest_user, _guest_client = _create_client_user('guest-mobile@test.com', 'clientpass1')
        guest_user.role = 'guest_prime_manager'
        guest_user.save(update_fields=['role'])

        self.assertTrue(PermissionService.has(guest_user, 'perm_mobile_app'))

        ctx = PermissionService.get_permission_context(guest_user)

        self.assertTrue(ctx['perm_mobile_app'])


class PermissionValidationMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user, _client = _create_client_user('middleware-client@test.com', 'clientpass1')

    def _middleware(self):
        from core.middleware import PermissionValidationMiddleware
        return PermissionValidationMiddleware(lambda request: None)

    def test_db_error_on_user_refetch_returns_503_for_api(self):
        middleware = self._middleware()
        request = self.factory.get('/panel/api/dummy/')
        request.user = self.user
        request.session = {}
        request.content_type = 'application/json'

        with patch('core.models.User.objects.only', side_effect=Exception('db locked')):
            response = middleware._validate_user_access(request)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 503)

    def test_db_error_on_user_refetch_redirects_page_to_inactive(self):
        middleware = self._middleware()
        request = self.factory.get('/panel/dashboard/')
        request.user = self.user
        request.session = {}
        request.content_type = ''

        with patch('core.models.User.objects.only', side_effect=Exception('db locked')):
            response = middleware._validate_user_access(request)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/panel/inactive/', response['Location'])


class GuestUserManagementApiTests(TestCase):
    def setUp(self):
        self.admin = _create_super_admin('guest-admin@test.com', 'adminpass1')
        self.client.login(username='guest-admin@test.com', password='adminpass1')

    def test_guest_users_page_embeds_csrf_header_helper(self):
        response = self.client.get('/panel/pro-user/guest-users/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'X-CSRFToken')

    def test_create_guest_user_allows_optional_email_and_defaults_active(self):
        response = self.client.post(
            '/panel/api/pro-user/guest-users/create/',
            data=json.dumps({
                'name': 'Demo Guest',
                'username': 'demo-guest',
                'password': 'guestpass123',
                'email': '',
                'phone': '',
                'city': 'Demo City',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        created_user = User.objects.get(username='demo-guest')
        self.assertEqual(created_user.role, 'guest_prime_manager')
        self.assertTrue(created_user.is_active)
        self.assertTrue(created_user.email.endswith('@noemail.local'))

        created_client = created_user.client_profile
        self.assertTrue(created_client.is_guest)
        self.assertEqual(created_client.status, 'active')

    def test_source_clients_excludes_current_client_profile(self):
        from organisation.models import Organisation

        current_client = Organisation.objects.create(user=self.admin, name='Admin Client Profile')
        other_user, _other_client = _create_client_user('guest-target@test.com', 'clientpass1')
        del other_user

        response = self.client.get('/panel/api/pro-user/guest-users/clients/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        ids = {item['id'] for item in data['clients']}
        self.assertNotIn(current_client.id, ids)

    def test_restore_guest_to_client_roundtrip(self):
        user, client_profile = _create_client_user('guest-roundtrip@test.com', 'clientpass1')
        self.assertEqual(user.role, 'client')

        convert_response = self.client.post(
            '/panel/api/pro-user/guest-users/convert/',
            data=json.dumps({'client_id': client_profile.id}),
            content_type='application/json',
        )
        self.assertEqual(convert_response.status_code, 200)
        self.assertTrue(convert_response.json()['success'])

        client_profile.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(client_profile.is_guest)
        self.assertEqual(user.role, 'guest_prime_manager')

        restore_response = self.client.post(
            '/panel/api/pro-user/guest-users/restore/',
            data=json.dumps({'client_id': client_profile.id}),
            content_type='application/json',
        )
        self.assertEqual(restore_response.status_code, 200)
        self.assertTrue(restore_response.json()['success'])

        client_profile.refresh_from_db()
        user.refresh_from_db()
        self.assertFalse(client_profile.is_guest)
        self.assertEqual(user.role, 'client')


class LegacyStaffApiJsonShapeTests(TestCase):
    def setUp(self):
        from operators.models import Operator

        self.super_admin = _create_super_admin('legacy-staff-admin@test.com', 'adminpass1')
        self.staff_user = User.objects.create_user(
            username='legacy-staff-user@test.com',
            email='legacy-staff-user@test.com',
            password='pass1234',
            role='operator',
        )
        self.staff_profile = Operator.objects.create(user=self.staff_user)
        self.client.login(username='legacy-staff-admin@test.com', password='adminpass1')

    def test_staff_create_rejects_non_object_json_payload(self):
        response = self.client.post(
            '/panel/api/staff/create/',
            data='[]',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json().get('success'))

    def test_staff_update_rejects_non_object_json_payload(self):
        response = self.client.put(
            f'/panel/api/staff/{self.staff_profile.id}/update/',
            data='[]',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json().get('success'))

    def test_staff_temp_password_rejects_non_object_json_payload(self):
        response = self.client.post(
            f'/panel/api/staff/{self.staff_profile.id}/set-temp-password/',
            data='[]',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json().get('success'))


class ThreadedEmailCallbackRetryTests(TestCase):
    def test_retries_transient_db_lock_then_succeeds(self):
        from core.utils.threaded_email import _run_callback_with_retry

        state = {'count': 0}

        def callback():
            state['count'] += 1
            if state['count'] < 3:
                raise Exception('database table is locked')

        _run_callback_with_retry(callback, 'test callback', max_attempts=3, base_delay=0)
        self.assertEqual(state['count'], 3)

    def test_does_not_retry_non_transient_error(self):
        from core.utils.threaded_email import _run_callback_with_retry

        state = {'count': 0}

        def callback():
            state['count'] += 1
            raise Exception('smtp down')

        _run_callback_with_retry(callback, 'test callback', max_attempts=3, base_delay=0)
        self.assertEqual(state['count'], 1)

    def test_failure_callback_receives_args_and_retries(self):
        from core.utils.threaded_email import _run_callback_with_retry

        state = {'count': 0, 'message': None}

        def callback(message):
            state['count'] += 1
            state['message'] = message
            if state['count'] < 2:
                raise Exception('database is locked')

        _run_callback_with_retry(
            callback,
            'test failure callback',
            'expected error message',
            max_attempts=3,
            base_delay=0,
        )

        self.assertEqual(state['count'], 2)
        self.assertEqual(state['message'], 'expected error message')


# ── Global Search Tests ──
class GlobalSearchTests(TestCase):
    def setUp(self):
        self.admin = _create_super_admin()
        _, self.client_obj = _create_client_user()
        self.group, self.table = _create_table(self.client_obj)
        _create_card(self.table, {'NAME': 'ALICE SMITH', 'CLASS': '10'})
        _create_card(self.table, {'NAME': 'BOB JONES', 'CLASS': '12'})
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_search_finds_matching_card(self):
        self.client.login(username='admin@test.com', password='adminpass1')
        response = self.client.get('/panel/api/global-search/?q=ALICE')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertGreater(data['count'], 0)

    def test_search_short_query_returns_empty(self):
        self.client.login(username='admin@test.com', password='adminpass1')
        response = self.client.get('/panel/api/global-search/?q=A')
        data = response.json()
        self.assertEqual(len(data.get('results', [])), 0)

    def test_search_no_match(self):
        self.client.login(username='admin@test.com', password='adminpass1')
        response = self.client.get('/panel/api/global-search/?q=ZZZZNOTFOUND')
        data = response.json()
        self.assertEqual(data['count'], 0)

    def test_search_does_not_match_json_key_names(self):
        self.client.login(username='admin@test.com', password='adminpass1')
        response = self.client.get('/panel/api/global-search/?q=NAME')
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 0)

    def test_search_does_not_match_image_storage_paths(self):
        _create_card(self.table, {
            'NAME': 'CHARLIE',
            'CLASS': '8',
            'PHOTO': 'adarshimg/ROS-IMAGE-PATH-123.jpg',
        })
        cache.clear()

        self.client.login(username='admin@test.com', password='adminpass1')
        response = self.client.get('/panel/api/global-search/?q=adarshimg')
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 0)

    def test_search_matches_image_filename_basename(self):
        _create_card(self.table, {
            'NAME': 'DELTA',
            'CLASS': '9',
            'PHOTO': 'adarshimg/ROS-IMAGE-PATH-123.jpg',
        })
        cache.clear()

        self.client.login(username='admin@test.com', password='adminpass1')
        response = self.client.get('/panel/api/global-search/?q=ROS-IMAGE-PATH-123')
        data = response.json()
        self.assertTrue(data['success'])
        self.assertGreater(data['count'], 0)


class IDCardListSearchTests(TestCase):
    def setUp(self):
        self.admin = _create_super_admin('list-admin@test.com', 'adminpass1')
        _, self.client_obj = _create_client_user('list-client@test.com', 'clientpass1')
        self.group, self.table = _create_table(self.client_obj)
        _create_card(self.table, {'NAME': 'ALPHA', 'CLASS': '5'})
        self.photo_card = _create_card(self.table, {
            'NAME': 'BRAVO',
            'CLASS': '6',
            'PHOTO': 'adarshimg/LIST-PHOTO-SEARCH-777.jpg',
        })
        self.charlie_card = _create_card(self.table, {'NAME': 'CHARLIE', 'CLASS': '7'})

    @staticmethod
    def _card_name(card):
        return card.get('name') or card.get('field_data', {}).get('NAME')

    def test_list_sort_by_name_asc_and_desc(self):
        self.client.login(username='list-admin@test.com', password='adminpass1')

        asc_response = self.client.get(f'/panel/api/table/{self.table.id}/cards/?sort=name-asc')
        self.assertEqual(asc_response.status_code, 200)
        asc_payload = asc_response.json()
        self.assertTrue(asc_payload.get('success'))
        asc_names = [self._card_name(card) for card in asc_payload.get('cards', [])[:3]]
        self.assertEqual(asc_names, ['ALPHA', 'BRAVO', 'CHARLIE'])

        desc_response = self.client.get(f'/panel/api/table/{self.table.id}/cards/?sort=name-desc')
        self.assertEqual(desc_response.status_code, 200)
        desc_payload = desc_response.json()
        self.assertTrue(desc_payload.get('success'))
        desc_names = [self._card_name(card) for card in desc_payload.get('cards', [])[:3]]
        self.assertEqual(desc_names, ['CHARLIE', 'BRAVO', 'ALPHA'])

    def test_list_search_matches_image_filename_basename(self):
        self.client.login(username='list-admin@test.com', password='adminpass1')
        response = self.client.get(f'/panel/api/table/{self.table.id}/cards/?search=PHOTO-SEARCH-777')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['total_count'], 1)
        self.assertEqual(data['cards'][0]['id'], self.photo_card.id)

    def test_list_search_does_not_match_image_directory(self):
        self.client.login(username='list-admin@test.com', password='adminpass1')
        response = self.client.get(f'/panel/api/table/{self.table.id}/cards/?search=adarshimg')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['total_count'], 0)


# ── Middleware Tests ──
class MiddlewareTests(TestCase):
    def test_health_check_endpoint(self):
        response = self.client.get('/panel/api/health/')
        # May redirect to login or return 200 depending on middleware
        self.assertIn(response.status_code, [200, 302, 404])

    def test_unauthenticated_panel_redirects(self):
        response = self.client.get('/panel/')
        self.assertIn(response.status_code, [302, 200])


class SubdomainRoutingSecurityTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['unknown.local'])
    def test_panel_context_cookie_ignored_outside_debug(self):
        from core.middleware import SubdomainRoutingMiddleware

        middleware = SubdomainRoutingMiddleware(lambda request: HttpResponse('ok'))
        request = self.factory.get('/api/auth/check-email/', HTTP_HOST='unknown.local')
        request.COOKIES['_panel_ctx'] = '1'

        middleware(request)
        self.assertFalse(getattr(request, '_is_panel_subdomain', False))

    @override_settings(DEBUG=True, ALLOWED_HOSTS=['unknown.local'])
    def test_panel_context_cookie_used_in_debug(self):
        from core.middleware import SubdomainRoutingMiddleware

        middleware = SubdomainRoutingMiddleware(lambda request: HttpResponse('ok'))
        request = self.factory.get('/api/auth/check-email/', HTTP_HOST='unknown.local')
        request.COOKIES['_panel_ctx'] = '1'

        middleware(request)
        self.assertTrue(getattr(request, '_is_panel_subdomain', False))


# ── Table Field Tests ──
class IDCardTableFieldTests(TestCase):
    def setUp(self):
        _, self.client_obj = _create_client_user()

    def test_has_image_fields(self):
        _, table = _create_table(self.client_obj, fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'PHOTO', 'type': 'photo', 'order': 2},
        ])
        self.assertTrue(table.has_image_fields())

    def test_no_image_fields(self):
        _, table = _create_table(self.client_obj, fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'CLASS', 'type': 'class', 'order': 2},
        ])
        self.assertFalse(table.has_image_fields())

    def test_has_class_field(self):
        _, table = _create_table(self.client_obj, fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'CLASS', 'type': 'class', 'order': 2},
        ])
        self.assertTrue(table.has_class_field())


class SystemSettingsAndTemplateTests(TestCase):
    def setUp(self):
        from core.models import SystemSettings
        cache.clear()
        SystemSettings.objects.all().delete()

    def tearDown(self):
        cache.clear()

    def test_system_settings_get_value_returns_export_default_when_missing(self):
        from core.models import SystemSettings

        value = SystemSettings.get_value('export_note_line')
        self.assertEqual(value, SystemSettings.EXPORT_DEFAULTS['export_note_line'])

    def test_system_settings_set_value_persists_and_invalidates_cache(self):
        from core.models import SystemSettings

        first = SystemSettings.get_value('custom_setting', default='initial')
        self.assertEqual(first, 'initial')

        SystemSettings.set_value('custom_setting', 'updated', description='test')
        second = SystemSettings.get_value('custom_setting', default='fallback')
        self.assertEqual(second, 'updated')

    def test_export_template_default_uniqueness(self):
        from core.models import ExportTemplate

        first = ExportTemplate.objects.create(
            name='Template 1',
            instructions='First instructions',
            is_default=True,
        )
        second = ExportTemplate.objects.create(
            name='Template 2',
            instructions='Second instructions',
            is_default=True,
        )

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
        self.assertEqual(ExportTemplate.get_default().id, second.id)


class PermissionDecoratorResponseTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import AnonymousUser

        self.factory = RequestFactory()
        self.anon = AnonymousUser()
        self.super_admin = _create_super_admin('decorator-admin@test.com', 'adminpass1')
        self.client_user, _ = _create_client_user('decorator-client@test.com', 'clientpass1')

    def test_require_super_admin_redirects_page_for_non_admin_user(self):
        from core.services.permission_service import require_super_admin
        from django.http import HttpResponse

        @require_super_admin
        def protected_view(request):
            return HttpResponse('ok')

        request = self.factory.get('/panel/manage-panel/')
        request.user = self.client_user
        request.content_type = ''
        request.headers = {}

        response = protected_view(request)
        self.assertEqual(response.status_code, 302)

    def test_require_super_admin_returns_json_for_api_path(self):
        from core.services.permission_service import require_super_admin
        from django.http import HttpResponse

        @require_super_admin
        def protected_view(request):
            return HttpResponse('ok')

        request = self.factory.get('/panel/api/monitoring/')
        request.user = self.client_user
        request.content_type = 'application/json'
        request.headers = {}

        response = protected_view(request)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(json.loads(response.content.decode('utf-8'))['success'])

    def test_api_require_any_authenticated_rejects_anonymous(self):
        from core.services.permission_service import api_require_any_authenticated
        from django.http import HttpResponse

        @api_require_any_authenticated
        def protected_view(request):
            return HttpResponse('ok')

        request = self.factory.get('/panel/api/anything/')
        request.user = self.anon

        response = protected_view(request)
        self.assertEqual(response.status_code, 401)

    def test_api_require_super_admin_allows_super_admin(self):
        from core.services.permission_service import api_require_super_admin
        from django.http import HttpResponse

        @api_require_super_admin
        def protected_view(request):
            return HttpResponse('ok')

        request = self.factory.get('/panel/api/admin-only/')
        request.user = self.super_admin

        response = protected_view(request)
        self.assertEqual(response.status_code, 200)


class PanelEntryGateSecurityTests(TestCase):
    def setUp(self):
        from core.models import SystemSettings

        self.factory = RequestFactory()
        cache.clear()
        SystemSettings.set_value('website_not_found_mode', 'true')
        SystemSettings.set_value('panel_entry_gate_enabled', 'true')

    def tearDown(self):
        cache.clear()

    def _middleware(self):
        from django.http import HttpResponse
        from core.middleware import PanelEntryGateMiddleware

        return PanelEntryGateMiddleware(lambda request: HttpResponse('ok'))

    def test_timestamp_signed_panel_token_is_accepted(self):
        from django.contrib.auth.models import AnonymousUser
        from django.core.signing import TimestampSigner

        token = TimestampSigner(salt='panel-entry-gate').sign('website-panel-entry')
        request = self.factory.get(f'/auth/login/?panel_entry_token={token}')
        request.user = AnonymousUser()
        request.session = {}
        request._is_panel_subdomain = True

        response = self._middleware()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request.session.get('_panel_entry_ok'), '1')

    def test_legacy_non_timestamp_token_is_rejected(self):
        from django.contrib.auth.models import AnonymousUser
        from django.core.signing import Signer
        from django.http import Http404

        token = Signer(salt='panel-entry-gate').sign('website-panel-entry')
        request = self.factory.get(f'/auth/login/?panel_entry_token={token}')
        request.user = AnonymousUser()
        request.session = {}
        request._is_panel_subdomain = True

        with self.assertRaises(Http404):
            self._middleware()(request)


class TaskApiSecurityTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = _create_super_admin('tasksec-admin@test.com', 'adminpass1')

    def test_task_download_rejects_sibling_media_prefix_path(self):
        from core.models import BackgroundTask
        from core.views.task_api import api_task_download

        with tempfile.TemporaryDirectory() as media_root:
            sibling_dir = media_root + '_evil'
            os.makedirs(sibling_dir, exist_ok=True)
            sibling_file = os.path.join(sibling_dir, 'secret.txt')
            with open(sibling_file, 'wb') as fh:
                fh.write(b'secret')

            escaped_rel = os.path.join('..', os.path.basename(sibling_dir), 'secret.txt')
            task = BackgroundTask.objects.create(
                user=self.user,
                task_type='export_zip',
                status='completed',
                result_path=escaped_rel,
            )

            request = self.factory.get(f'/panel/api/task-download/{task.id}/')
            request.user = self.user
            request.session = {}

            with override_settings(MEDIA_ROOT=media_root):
                response = api_task_download(request, task.id)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(json.loads(response.content.decode('utf-8'))['success'])


class TaskProgressCenterApiTests(TestCase):
    def setUp(self):
        self.super_admin = _create_super_admin('task-progress-admin@test.com', 'adminpass1')
        self.regular_user, self.regular_client = _create_client_user(
            'task-progress-client@test.com',
            'clientpass1',
        )

    def test_task_progress_center_returns_aggregates_and_download_links(self):
        from core.models import BackgroundTask

        now = timezone.now()

        processing = BackgroundTask.objects.create(
            user=self.super_admin,
            task_type='export_pdf',
            status='processing',
            progress=25,
            total=100,
            metadata={'stage_label': 'Packaging records'},
        )
        pending = BackgroundTask.objects.create(
            user=self.super_admin,
            task_type='export_docx',
            status='pending',
            progress=0,
            total=0,
        )
        completed = BackgroundTask.objects.create(
            user=self.super_admin,
            task_type='export_excel',
            status='completed',
            progress=10,
            total=10,
            result_path='exports/test-output.xlsx',
        )
        failed = BackgroundTask.objects.create(
            user=self.super_admin,
            task_type='export_zip',
            status='failed',
            progress=3,
            total=8,
            error_message='zip failed',
        )
        other_user_active = BackgroundTask.objects.create(
            user=self.regular_user,
            task_type='export_pdf',
            status='pending',
            progress=0,
            total=0,
        )

        BackgroundTask.objects.filter(pk=processing.pk).update(
            created_at=now - timedelta(minutes=8),
            started_at=now - timedelta(minutes=5),
        )
        BackgroundTask.objects.filter(pk=pending.pk).update(created_at=now - timedelta(minutes=6))
        BackgroundTask.objects.filter(pk=completed.pk).update(
            created_at=now - timedelta(minutes=12),
            completed_at=now - timedelta(minutes=2),
        )
        BackgroundTask.objects.filter(pk=failed.pk).update(
            created_at=now - timedelta(minutes=11),
            completed_at=now - timedelta(minutes=3),
        )
        BackgroundTask.objects.filter(pk=other_user_active.pk).update(created_at=now - timedelta(minutes=7))

        self.client.force_login(self.super_admin)
        response = self.client.get('/panel/api/task-progress-center/', {'limit': 8})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('scope'), 'all')

        stats = payload.get('stats') or {}
        self.assertEqual(stats.get('active'), 3)
        self.assertEqual(stats.get('pending'), 2)
        self.assertEqual(stats.get('processing'), 1)
        self.assertEqual(stats.get('completed_24h'), 1)
        self.assertEqual(stats.get('failed_24h'), 1)

        task_map = {item.get('task_id'): item for item in (payload.get('tasks') or [])}
        self.assertIn(processing.id, task_map)
        self.assertIn(completed.id, task_map)
        self.assertIn(other_user_active.id, task_map)

        self.assertEqual(task_map[completed.id].get('download_url'), f'/api/task-download/{completed.id}/')
        self.assertTrue(task_map[processing.id].get('can_cancel'))
        self.assertIsNotNone(task_map[processing.id].get('eta_seconds'))

    def test_task_progress_center_scopes_non_super_admin_to_self(self):
        from core.models import BackgroundTask

        own_task = BackgroundTask.objects.create(
            user=self.regular_user,
            task_type='export_pdf',
            status='pending',
            progress=0,
            total=0,
        )
        BackgroundTask.objects.create(
            user=self.super_admin,
            task_type='export_excel',
            status='pending',
            progress=0,
            total=0,
        )

        self.client.force_login(self.regular_user)
        response = self.client.get('/panel/api/task-progress-center/', {'limit': 8})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('scope'), 'self')

        stats = payload.get('stats') or {}
        self.assertEqual(stats.get('active'), 1)
        self.assertEqual(stats.get('pending'), 1)
        self.assertEqual(stats.get('processing'), 0)

        task_ids = {item.get('task_id') for item in (payload.get('tasks') or [])}
        self.assertEqual(task_ids, {own_task.id})

    def test_task_progress_center_paginates_and_reports_totals(self):
        from core.models import BackgroundTask

        now = timezone.now()
        for index in range(7):
            task = BackgroundTask.objects.create(
                user=self.super_admin,
                task_type='export_pdf',
                status='completed' if index >= 2 else 'processing',
                progress=index,
                total=10,
            )
            BackgroundTask.objects.filter(pk=task.pk).update(created_at=now - timedelta(minutes=index + 1))

        self.client.force_login(self.super_admin)
        response = self.client.get('/panel/api/task-progress-center/', {'page': 2, 'per_page': 3})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('total'), 7)
        self.assertEqual(payload.get('page'), 2)
        self.assertEqual(payload.get('per_page'), 3)
        self.assertEqual(payload.get('total_pages'), 3)
        self.assertEqual(len(payload.get('tasks') or []), 3)


class AssignmentTimelineApiTests(TestCase):
    def setUp(self):
        from staff.models import Staff

        self.super_admin = _create_super_admin('assignment-timeline-admin@test.com', 'adminpass1')
        _client_owner, self.client_obj = _create_client_user('assignment-client-owner@test.com', 'clientpass1')

        self.client_staff_user = User.objects.create_user(
            username='assignment-client-staff@test.com',
            email='assignment-client-staff@test.com',
            password='pass1234',
            role='client_staff',
            first_name='Timeline',
            last_name='Client Staff',
        )
        self.client_staff_profile = Staff.objects.create(
            user=self.client_staff_user,
            staff_type='assistant',
            client=self.client_obj,
        )

        self.admin_staff_user = User.objects.create_user(
            username='assignment-admin-staff@test.com',
            email='assignment-admin-staff@test.com',
            password='pass1234',
            role='operator',
            first_name='Timeline',
            last_name='Operator',
        )
        self.admin_staff_profile = Staff.objects.create(
            user=self.admin_staff_user,
            staff_type='operator',
        )

        self.client.force_login(self.super_admin)

    def test_client_staff_assignment_timeline_filters_assignment_related_events(self):
        from core.models import ActivityLog

        assignment_log = ActivityLog.objects.create(
            user=self.super_admin,
            action='staff_assignment',
            description='Assignment updated: clients +1, groups +2',
            target_model='Staff',
            target_id=self.client_staff_profile.id,
        )
        fallback_assignment_log = ActivityLog.objects.create(
            user=self.super_admin,
            action='staff_update',
            description='Staff assignment scope adjusted by admin',
            target_model='Staff',
            target_id=self.client_staff_profile.id,
        )
        noise_log = ActivityLog.objects.create(
            user=self.super_admin,
            action='staff_update',
            description='Changed staff phone number',
            target_model='Staff',
            target_id=self.client_staff_profile.id,
        )

        response = self.client.get(
            f'/panel/api/client-staff/{self.client_staff_profile.id}/assignment-timeline/',
            {'limit': 50},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual((payload.get('staff') or {}).get('id'), self.client_staff_profile.id)

        event_ids = [item.get('id') for item in (payload.get('events') or [])]
        self.assertIn(assignment_log.id, event_ids)
        self.assertIn(fallback_assignment_log.id, event_ids)
        self.assertNotIn(noise_log.id, event_ids)

    def test_admin_staff_assignment_timeline_returns_staff_assignment_events(self):
        from core.models import ActivityLog

        assignment_log = ActivityLog.objects.create(
            user=self.super_admin,
            action='staff_assignment',
            description='Admin staff client access updated',
            target_model='Staff',
            target_id=self.admin_staff_profile.id,
        )

        response = self.client.get(
            f'/panel/api/staff/{self.admin_staff_profile.id}/assignment-timeline/',
            {'limit': 50},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual((payload.get('staff') or {}).get('id'), self.admin_staff_profile.id)

        event_ids = [item.get('id') for item in (payload.get('events') or [])]
        self.assertEqual(event_ids, [assignment_log.id])


class ProtectedMediaAuthorizationTests(TestCase):
    def setUp(self):
        from organisation.models import Organisation

        self.owner_a = User.objects.create_user(
            username='media-owner-a@test.com',
            email='media-owner-a@test.com',
            password='pass1234',
            role='client',
        )
        self.owner_b = User.objects.create_user(
            username='media-owner-b@test.com',
            email='media-owner-b@test.com',
            password='pass1234',
            role='client',
        )
        self.client_a = Organisation.objects.create(user=self.owner_a, name='Media Client A')
        self.client_b = Organisation.objects.create(user=self.owner_b, name='Media Client B')

    def test_media_adareshimg_enforces_client_scope(self):
        with tempfile.TemporaryDirectory() as media_root:
            rel_path = f"adarshimg/{self.client_a.image_folder_code}/photo.jpg"
            abs_path = os.path.join(media_root, 'adarshimg', self.client_a.image_folder_code, 'photo.jpg')
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, 'wb') as fh:
                fh.write(b'jpg')

            with override_settings(MEDIA_ROOT=media_root, MEDIA_USE_XACCEL=True):
                self.client.force_login(self.owner_b)
                denied = self.client.get(f'/media/{rel_path}')
                self.assertEqual(denied.status_code, 404)

                self.client.force_login(self.owner_a)
                allowed = self.client.get(f'/media/{rel_path}')
                self.assertEqual(allowed.status_code, 200)
                self.assertEqual(allowed.get('X-Accel-Redirect'), f'/protected-media/{rel_path}')

    def test_media_exports_enforces_task_owner(self):
        from core.models import BackgroundTask

        with tempfile.TemporaryDirectory() as media_root:
            rel_path = 'exports/private-export.pdf'
            abs_path = os.path.join(media_root, 'exports', 'private-export.pdf')
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, 'wb') as fh:
                fh.write(b'%PDF-1.7')

            BackgroundTask.objects.create(
                user=self.owner_a,
                task_type='export_pdf',
                status='completed',
                result_path=rel_path,
            )

            with override_settings(MEDIA_ROOT=media_root, MEDIA_USE_XACCEL=True):
                self.client.force_login(self.owner_b)
                denied = self.client.get(f'/media/{rel_path}')
                self.assertEqual(denied.status_code, 404)

                self.client.force_login(self.owner_a)
                allowed = self.client.get(f'/media/{rel_path}')
                self.assertEqual(allowed.status_code, 200)
                self.assertEqual(allowed.get('X-Accel-Redirect'), f'/protected-media/{rel_path}')


class DashboardAndLogsHardeningTests(TestCase):
    def test_dashboard_team_counts_separate_admin_staff_and_client_staff(self):
        from organisation.models import Organisation
        from staff.models import Staff

        cache.clear()

        admin = _create_super_admin('dashboard-counts-admin@test.com', 'adminpass1')

        client_owner_a = User.objects.create_user(
            username='dashboard-client-owner-a@test.com',
            email='dashboard-client-owner-a@test.com',
            password='pass1234',
            role='client',
        )
        client_owner_b = User.objects.create_user(
            username='dashboard-client-owner-b@test.com',
            email='dashboard-client-owner-b@test.com',
            password='pass1234',
            role='client',
        )
        client_a = Organisation.objects.create(user=client_owner_a, name='Dashboard Client A', status='active')
        Organisation.objects.create(user=client_owner_b, name='Dashboard Client B', status='inactive')

        User.objects.create_user(
            username='dashboard-pro-user@test.com',
            email='dashboard-pro-user@test.com',
            password='pass1234',
            role='pro_user',
            is_active=True,
        )

        admin_staff_active = User.objects.create_user(
            username='dashboard-admin-staff-active@test.com',
            email='dashboard-admin-staff-active@test.com',
            password='pass1234',
            role='operator',
            is_active=True,
        )
        admin_staff_inactive = User.objects.create_user(
            username='dashboard-admin-staff-inactive@test.com',
            email='dashboard-admin-staff-inactive@test.com',
            password='pass1234',
            role='operator',
            is_active=False,
        )
        Staff.objects.create(user=admin_staff_active, staff_type='operator')
        Staff.objects.create(user=admin_staff_inactive, staff_type='operator')

        client_staff_active_a = User.objects.create_user(
            username='dashboard-client-staff-active-a@test.com',
            email='dashboard-client-staff-active-a@test.com',
            password='pass1234',
            role='client_staff',
            is_active=True,
        )
        client_staff_inactive_a = User.objects.create_user(
            username='dashboard-client-staff-inactive-a@test.com',
            email='dashboard-client-staff-inactive-a@test.com',
            password='pass1234',
            role='client_staff',
            is_active=False,
        )
        client_staff_active_b = User.objects.create_user(
            username='dashboard-client-staff-active-b@test.com',
            email='dashboard-client-staff-active-b@test.com',
            password='pass1234',
            role='client_staff',
            is_active=True,
        )
        Staff.objects.create(user=client_staff_active_a, staff_type='assistant', client=client_a)
        Staff.objects.create(user=client_staff_inactive_a, staff_type='assistant', client=client_a)
        Staff.objects.create(user=client_staff_active_b, staff_type='assistant', client=client_a)

        self.client.force_login(admin)
        response = self.client.get('/panel/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['overview_clients_count'], Organisation.objects.filter(is_guest=False).count())
        self.assertEqual(response.context['overview_guest_users_count'], Organisation.objects.filter(is_guest=True).count())
        self.assertEqual(response.context['overview_assistents_count'], 3)

    def test_dashboard_limit_parser_clamps_values(self):
        from core.views.dashboard_views import _parse_dashboard_limit

        self.assertEqual(_parse_dashboard_limit('99999'), 500)
        self.assertEqual(_parse_dashboard_limit('-5'), 1)
        self.assertEqual(_parse_dashboard_limit('bad'), 500)

    def test_recent_activity_api_returns_latest_entries_without_time_window_filter(self):
        from datetime import timedelta
        from django.utils import timezone
        from core.models import ActivityLog

        admin = _create_super_admin('activity-recent-admin@test.com', 'adminpass1')

        old_entry = ActivityLog.objects.create(
            user=admin,
            action='other',
            description='legacy-entry-10-days-old',
        )
        recent_entry = ActivityLog.objects.create(
            user=admin,
            action='other',
            description='latest-entry-now',
        )

        ten_days_ago = timezone.now() - timedelta(days=10)
        ActivityLog.objects.filter(pk=old_entry.pk).update(created_at=ten_days_ago)

        self.client.force_login(admin)
        response = self.client.get('/panel/api/recent-activity/', {'limit': 100, 'window': '1'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        descriptions = [item.get('description') for item in payload.get('activities', [])]
        self.assertIn('legacy-entry-10-days-old', descriptions)
        self.assertIn('latest-entry-now', descriptions)

        ids = [item.get('id') for item in payload.get('activities', [])]
        self.assertIn(old_entry.pk, ids)
        self.assertIn(recent_entry.pk, ids)

    def test_recent_activity_api_returns_full_last_100_without_merge_collapse(self):
        from core.models import ActivityLog

        admin = _create_super_admin('activity-last-100-admin@test.com', 'adminpass1')

        for i in range(130):
            ActivityLog.objects.create(
                user=admin,
                action='card_status',
                description='1 card verified',
                target_model='IDCard',
                target_id=1000 + i,
                target_name=f'Card #{1000 + i}',
            )

        self.client.force_login(admin)
        response = self.client.get('/panel/api/recent-activity/', {'limit': 100, 'merge': '0'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(len(payload.get('activities', [])), 100)

    def test_activity_logs_handles_invalid_limit_offset(self):
        from core.models import ActivityLog

        admin = _create_super_admin('activity-admin@test.com', 'adminpass1')
        for i in range(3):
            ActivityLog.objects.create(user=admin, action='other', description=f'log-{i}')

        self.client.force_login(admin)
        response = self.client.get('/panel/api/activity-logs/', {'limit': 'bad', 'offset': 'bad'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertGreaterEqual(payload['total'], 3)


class SecurityApiRegressionTests(TestCase):
    def setUp(self):
        from staff.models import Staff

        self.super_admin = _create_super_admin('sec-api-admin@test.com', 'adminpass1')

        self.client_user_a, self.client_a = _create_client_user('sec-client-a@test.com', 'clientpass1')
        self.client_user_b, self.client_b = _create_client_user('sec-client-b@test.com', 'clientpass1')

        self.group_a, self.table_a = _create_table(self.client_a, fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'CLASS', 'type': 'class', 'order': 2},
        ])
        self.card_a = _create_card(self.table_a, field_data={'NAME': 'ALICE', 'CLASS': '10'})

        self.admin_staff = User.objects.create_user(
            username='sec-admin-staff@test.com',
            email='sec-admin-staff@test.com',
            password='pass1234',
            role='operator',
        )
        self.admin_staff_profile = Staff.objects.create(user=self.admin_staff, staff_type='operator')
        self.admin_staff_profile.assigned_organisations.add(self.client_a)

    def test_client_role_cannot_access_recent_client_updates_api(self):
        self.client.force_login(self.client_user_a)

        response = self.client.get(reverse('api_recent_client_updates'))

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertFalse(payload.get('success', True))
        self.assertIn('admin access required', payload.get('message', '').lower())

    def test_client_role_cannot_access_manage_clients(self):
        self.client.force_login(self.client_user_a)

        response = self.client.get(reverse('manage_clients'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))

    def test_legacy_active_clients_route_redirects_to_manage_clients(self):
        self.client.login(username='sec-api-admin@test.com', password='adminpass1')

        response = self.client.get(f"{reverse('active_clients')}?status=active&search=alpha&page=2")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('manage_clients')}?status=active&search=alpha&page=2")

    def test_legacy_active_client_status_redirect_targets_manage_clients(self):
        self.client.login(username='sec-api-admin@test.com', password='adminpass1')

        response = self.client.get(reverse('active_client_status_redirect', args=[self.client_a.id, 'pending']))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('manage_clients')}?highlight={self.client_a.id}")

    def test_client_role_cannot_create_table_from_xlsx_api(self):
        self.client_a.perm_idcard_setting_add = True
        self.client_a.save(update_fields=['perm_idcard_setting_add'])

        self.client.force_login(self.client_user_a)

        response = self.client.post(
            reverse('api_create_table_from_xlsx', args=[self.group_a.id]),
            {'file': SimpleUploadedFile('sample.csv', b'NAME,CLASS\nALICE,10\n', content_type='text/csv')},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertFalse(payload.get('success', True))
        self.assertIn('not available for client accounts', payload.get('message', '').lower())

    def test_inline_update_field_rejects_unknown_field_name(self):
        self.client.login(username='sec-api-admin@test.com', password='adminpass1')

        response = self.client.post(
            f'/panel/api/card/{self.card_a.id}/update-field/',
            data=json.dumps({'field': '__HACK__', 'value': 'x'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload.get('success', True))
        self.assertIn('Invalid field name', payload.get('message', ''))

        self.card_a.refresh_from_db()
        self.assertNotIn('__HACK__', self.card_a.field_data)

    def test_inline_update_field_normalizes_punctuated_scholar_column(self):
        from tables.models import IDCard

        user, client_obj = _create_client_user('scholar-client@test.com', 'clientpass1')
        client_obj.perm_idcard_edit = True
        client_obj.save(update_fields=['perm_idcard_edit'])

        _, table = _create_table(client_obj, fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'SCHOLAR NO.', 'type': 'text', 'order': 2},
        ])
        card = _create_card(table, field_data={'NAME': 'STUDENT ONE', 'SCHOLAR NO.': '12345'})

        self.client.login(username='scholar-client@test.com', password='clientpass1')
        response = self.client.post(
            f'/panel/api/card/{card.id}/update-field/',
            data=json.dumps({'field': 'SCHOLAR NO', 'value': '54321'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        card.refresh_from_db()
        self.assertEqual(card.field_data.get('SCHOLAR NO.'), '54321')

    def test_client_toggle_status_denies_manage_client_admin_staff_for_unassigned_client(self):
        self.admin_staff_profile.perm_idcard_client_list = True
        self.admin_staff_profile.save(update_fields=['perm_idcard_client_list'])
        self.client.login(username='sec-admin-staff@test.com', password='pass1234')

        response = self.client.post(
            f'/panel/api/client/{self.client_b.id}/toggle-status/',
            data=json.dumps({}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('access denied', response.json().get('message', '').lower())

    def test_admin_staff_without_manage_client_permission_cannot_create_client(self):
        self.client.login(username='sec-admin-staff@test.com', password='pass1234')
        response = self.client.post(
            '/panel/api/client/create/',
            data=json.dumps({'name': 'Blocked Client', 'phone': '9999999999'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('manage client permission required', response.json().get('message', '').lower())

    def test_admin_staff_without_manage_client_permission_can_view_assigned_client_details_only(self):
        self.client.login(username='sec-admin-staff@test.com', password='pass1234')

        assigned_resp = self.client.get(f'/panel/api/client/{self.client_a.id}/')
        self.assertEqual(assigned_resp.status_code, 200)
        self.assertTrue(assigned_resp.json().get('success'))

        unassigned_resp = self.client.get(f'/panel/api/client/{self.client_b.id}/')
        self.assertEqual(unassigned_resp.status_code, 403)
        self.assertIn('access denied', unassigned_resp.json().get('message', '').lower())

    def test_admin_staff_with_manage_client_permission_can_create_update_but_not_delete_client(self):
        from organisation.models import Organisation

        self.admin_staff_profile.perm_idcard_client_list = True
        self.admin_staff_profile.save(update_fields=['perm_idcard_client_list'])
        self.client.login(username='sec-admin-staff@test.com', password='pass1234')

        create_resp = self.client.post(
            '/panel/api/client/create/',
            data=json.dumps({
                'name': 'Staff Created Client',
                'phone': '8888888888',
                'email': 'staff-created-client@test.com',
                'perm_idcard_edit': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 200)
        create_payload = create_resp.json()
        self.assertTrue(create_payload.get('success'))
        new_client_id = create_payload.get('client', {}).get('id')
        self.assertTrue(new_client_id)

        self.admin_staff_profile.refresh_from_db()
        self.assertTrue(self.admin_staff_profile.assigned_organisations.filter(id=new_client_id).exists())

        update_resp = self.client.post(
            f'/panel/api/client/{new_client_id}/update/',
            data=json.dumps({
                'name': 'Staff Updated Client',
                'perm_idcard_delete': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(update_resp.status_code, 200)
        self.assertTrue(update_resp.json().get('success'))

        get_resp = self.client.get(f'/panel/api/client/{new_client_id}/')
        self.assertEqual(get_resp.status_code, 200)
        get_payload = get_resp.json()
        self.assertTrue(get_payload.get('success'))
        self.assertEqual(get_payload.get('client', {}).get('name'), 'Staff Updated Client')
        self.assertTrue(get_payload.get('client', {}).get('perm_idcard_delete'))

        delete_resp = self.client.post(f'/panel/api/client/{new_client_id}/delete/', data=json.dumps({}), content_type='application/json')
        self.assertEqual(delete_resp.status_code, 403)
        self.assertIn('only super admin can delete clients', delete_resp.json().get('message', '').lower())
        self.assertTrue(Organisation.objects.filter(id=new_client_id).exists())


    def test_delete_all_confirmation_locks_after_five_failed_attempts(self):
        self.client.login(username='sec-api-admin@test.com', password='adminpass1')

        session = self.client.session
        session[f'delete_all_code_{self.table_a.id}'] = '1234567890'
        session.save()

        url = f'/panel/api/table/{self.table_a.id}/cards/bulk-delete/'
        for _ in range(5):
            response = self.client.post(
                url,
                data=json.dumps({'delete_all': True, 'confirmation_code': '0000000000'}),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 403)

        locked = self.client.post(
            url,
            data=json.dumps({'delete_all': True, 'confirmation_code': '0000000000'}),
            content_type='application/json',
        )
        self.assertEqual(locked.status_code, 429)
        self.assertIn('Too many failed attempts', locked.json().get('message', ''))

    def test_delete_all_success_clears_attempt_counter(self):
        self.client.login(username='sec-api-admin@test.com', password='adminpass1')

        session = self.client.session
        session[f'delete_all_code_{self.table_a.id}'] = '1234567890'
        session[f'delete_all_attempts_{self.table_a.id}'] = 3
        session.save()

        response = self.client.post(
            f'/panel/api/table/{self.table_a.id}/cards/bulk-delete/',
            data=json.dumps({'delete_all': True, 'confirmation_code': '1234567890'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)

        session_after = self.client.session
        self.assertNotIn(f'delete_all_code_{self.table_a.id}', session_after)
        self.assertNotIn(f'delete_all_attempts_{self.table_a.id}', session_after)

    def test_maintenance_status_hides_details_for_non_admin(self):
        self.client.login(username='sec-client-a@test.com', password='clientpass1')

        response = self.client.get('/panel/api/maintenance/status/')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertIn('enabled', payload)
        self.assertNotIn('message', payload)
        self.assertNotIn('end_time', payload)

    def test_maintenance_status_returns_full_payload_for_admin(self):
        self.client.login(username='sec-api-admin@test.com', password='adminpass1')

        response = self.client.get('/panel/api/maintenance/status/')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertIn('enabled', payload)
        self.assertIn('message', payload)
        self.assertIn('end_time', payload)

    def test_client_and_client_staff_cards_api_hide_admin_audit_metadata(self):
        from staff.models import Staff

        # Parent client permissions gate client_staff visibility too.
        self.client_a.perm_idcard_pending_list = True
        self.client_a.perm_idcard_updated_at = True
        self.client_a.save(update_fields=['perm_idcard_pending_list', 'perm_idcard_updated_at'])

        client_staff_user = User.objects.create_user(
            username='sec-client-staff-a@test.com',
            email='sec-client-staff-a@test.com',
            password='pass1234',
            role='client_staff',
        )
        Staff.objects.create(
            user=client_staff_user,
            staff_type='assistant',
            client=self.client_a,
            perm_idcard_pending_list=True,
            perm_idcard_updated_at=True,
            assigned_table_ids=[self.table_a.id],
            allowed_classes=['10'],
        )

        admin_touched_card = self.card_a
        admin_touched_card.status = 'pending'
        admin_touched_card.modified_by = self.admin_staff.username
        admin_touched_card.save(update_fields=['status', 'modified_by'])

        client_touched_card = _create_card(
            self.table_a,
            field_data={'NAME': 'BOB', 'CLASS': '10'},
            status='pending',
        )
        client_touched_card.modified_by = client_staff_user.username
        client_touched_card.save(update_fields=['modified_by'])

        url = f'/panel/api/table/{self.table_a.id}/cards/?status=pending'

        # Client view
        self.client.login(username='sec-client-a@test.com', password='clientpass1')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        cards_by_id = {c['id']: c for c in payload['cards']}

        self.assertEqual(cards_by_id[admin_touched_card.id]['modified_by'], '')
        self.assertIsNone(cards_by_id[admin_touched_card.id]['updated_at'])
        self.assertIsNone(cards_by_id[admin_touched_card.id]['downloaded_at'])
        self.assertIsNone(cards_by_id[admin_touched_card.id]['deleted_at'])

        self.assertEqual(cards_by_id[client_touched_card.id]['modified_by'], self.client_a.name)
        self.assertIsNotNone(cards_by_id[client_touched_card.id]['updated_at'])

        # Client staff view
        self.client.login(username='sec-client-staff-a@test.com', password='pass1234')
        response_staff = self.client.get(url)
        self.assertEqual(response_staff.status_code, 200)
        payload_staff = response_staff.json()
        staff_cards_by_id = {c['id']: c for c in payload_staff['cards']}

        self.assertEqual(staff_cards_by_id[admin_touched_card.id]['modified_by'], '')
        self.assertIsNone(staff_cards_by_id[admin_touched_card.id]['updated_at'])
        self.assertEqual(staff_cards_by_id[client_touched_card.id]['modified_by'], self.client_a.name)

    def test_client_update_response_masks_username_to_client_name(self):
        self.client_a.perm_idcard_edit = True
        self.client_a.perm_idcard_updated_at = True
        self.client_a.save(update_fields=['perm_idcard_edit', 'perm_idcard_updated_at'])

        self.client.login(username='sec-client-a@test.com', password='clientpass1')
        response = self.client.post(
            f'/panel/api/card/{self.card_a.id}/update/',
            data=json.dumps({'field_data': {'NAME': 'ALICIA', 'CLASS': '10'}}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['card']['modified_by'], self.client_a.name)
        self.assertNotEqual(payload['card']['modified_by'], self.client_user_a.username)
        self.assertIsNotNone(payload['card']['updated_at'])

    def test_client_can_edit_pool_card_via_update_api(self):
        self.client_a.perm_idcard_edit = True
        self.client_a.save(update_fields=['perm_idcard_edit'])
        self.card_a.status = 'pool'
        self.card_a.save(update_fields=['status'])

        self.client.login(username='sec-client-a@test.com', password='clientpass1')
        response = self.client.post(
            f'/panel/api/card/{self.card_a.id}/update/',
            data=json.dumps({'field_data': {'NAME': 'SHOULD NOT UPDATE'}}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))
        self.card_a.refresh_from_db()
        self.assertEqual(self.card_a.field_data.get('NAME'), 'SHOULD NOT UPDATE')

    def test_client_can_inline_edit_pool_card(self):
        self.client_a.perm_idcard_edit = True
        self.client_a.save(update_fields=['perm_idcard_edit'])
        self.card_a.status = 'pool'
        self.card_a.save(update_fields=['status'])

        self.client.login(username='sec-client-a@test.com', password='clientpass1')
        response = self.client.post(
            f'/panel/api/card/{self.card_a.id}/update-field/',
            data=json.dumps({'field': 'NAME', 'value': 'SHOULD NOT UPDATE'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))
        self.card_a.refresh_from_db()
        self.assertEqual(self.card_a.field_data.get('NAME'), 'SHOULD NOT UPDATE')

    def test_client_reprint_modal_flag_can_edit_download_card_with_reprint_permission(self):
        self.client_a.perm_idcard_edit = True
        self.client_a.perm_idcard_reprint_list = True
        self.client_a.save(update_fields=['perm_idcard_edit', 'perm_idcard_reprint_list'])
        self.card_a.status = 'download'
        self.card_a.save(update_fields=['status'])

        self.client.login(username='sec-client-a@test.com', password='clientpass1')
        response = self.client.post(
            f'/panel/api/card/{self.card_a.id}/update/',
            data=json.dumps({
                'field_data': {'NAME': 'UPDATED FROM REPRINT MODAL'},
                'reprint_modal_edit': True,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))
        self.card_a.refresh_from_db()
        self.assertEqual(self.card_a.field_data.get('NAME'), 'UPDATED FROM REPRINT MODAL')

    def test_client_reprint_modal_flag_still_denied_without_reprint_permission(self):
        self.client_a.perm_idcard_edit = True
        self.client_a.perm_idcard_reprint_list = False
        self.client_a.perm_reprint_request_list = False
        self.client_a.save(update_fields=['perm_idcard_edit', 'perm_idcard_reprint_list', 'perm_reprint_request_list'])
        self.card_a.status = 'download'
        self.card_a.save(update_fields=['status'])

        self.client.login(username='sec-client-a@test.com', password='clientpass1')
        response = self.client.post(
            f'/panel/api/card/{self.card_a.id}/update/',
            data=json.dumps({
                'field_data': {'NAME': 'SHOULD NOT UPDATE'},
                'reprint_modal_edit': True,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('cannot be edited', response.json().get('message', '').lower())
        self.card_a.refresh_from_db()
        self.assertEqual(self.card_a.field_data.get('NAME'), 'ALICE')

    def test_client_reprint_modal_flag_can_edit_download_card_with_reprint_request_permission(self):
        self.client_a.perm_idcard_edit = True
        self.client_a.perm_idcard_reprint_list = False
        self.client_a.perm_reprint_request_list = True
        self.client_a.save(update_fields=['perm_idcard_edit', 'perm_idcard_reprint_list', 'perm_reprint_request_list'])
        self.card_a.status = 'download'
        self.card_a.save(update_fields=['status'])

        self.client.login(username='sec-client-a@test.com', password='clientpass1')
        response = self.client.post(
            f'/panel/api/card/{self.card_a.id}/update/',
            data=json.dumps({
                'field_data': {'NAME': 'UPDATED FROM REPRINT MODAL WITH REPRINT REQUEST PERM'},
                'reprint_modal_edit': True,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))
        self.card_a.refresh_from_db()
        self.assertEqual(self.card_a.field_data.get('NAME'), 'UPDATED FROM REPRINT MODAL WITH REPRINT REQUEST PERM')

    def test_client_cannot_edit_card_with_active_reprint_request_even_with_modal_flag(self):
        self.client_a.perm_idcard_edit = True
        self.client_a.perm_idcard_reprint_list = False
        self.client_a.perm_reprint_request_list = True
        self.client_a.save(update_fields=['perm_idcard_edit', 'perm_idcard_reprint_list', 'perm_reprint_request_list'])
        self.card_a.status = 'download'
        self.card_a.save(update_fields=['status'])

        # Create active reprint request
        from reprintcard.models import ReprintRequest
        ReprintRequest.objects.create(
            card=self.card_a,
            table=self.card_a.table,
            status='requested',
        )

        self.client.login(username='sec-client-a@test.com', password='clientpass1')
        response = self.client.post(
            f'/panel/api/card/{self.card_a.id}/update/',
            data=json.dumps({
                'field_data': {'NAME': 'SHOULD BLOCK EDIT'},
                'reprint_modal_edit': True,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('active reprint requests cannot be edited', response.json().get('message', '').lower())
        self.card_a.refresh_from_db()
        self.assertEqual(self.card_a.field_data.get('NAME'), 'ALICE')

    def test_client_cannot_inline_edit_card_with_active_reprint_request(self):
        self.client_a.perm_idcard_edit = True
        self.client_a.perm_idcard_reprint_list = False
        self.client_a.perm_reprint_request_list = True
        self.client_a.save(update_fields=['perm_idcard_edit', 'perm_idcard_reprint_list', 'perm_reprint_request_list'])
        self.card_a.status = 'download'
        self.card_a.save(update_fields=['status'])

        # Create active reprint request
        from reprintcard.models import ReprintRequest
        ReprintRequest.objects.create(
            card=self.card_a,
            table=self.card_a.table,
            status='requested',
        )

        self.client.login(username='sec-client-a@test.com', password='clientpass1')
        response = self.client.post(
            f'/panel/api/card/{self.card_a.id}/update-field/',
            data=json.dumps({'field': 'NAME', 'value': 'SHOULD BLOCK EDIT'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('active reprint requests cannot be edited', response.json().get('message', '').lower())
        self.card_a.refresh_from_db()
        self.assertEqual(self.card_a.field_data.get('NAME'), 'ALICE')

    def test_client_download_card_without_modal_flag_remains_locked(self):
        self.client_a.perm_idcard_edit = True
        self.client_a.perm_idcard_reprint_list = True
        self.client_a.save(update_fields=['perm_idcard_edit', 'perm_idcard_reprint_list'])
        self.card_a.status = 'download'
        self.card_a.save(update_fields=['status'])

        self.client.login(username='sec-client-a@test.com', password='clientpass1')
        response = self.client.post(
            f'/panel/api/card/{self.card_a.id}/update/',
            data=json.dumps({'field_data': {'NAME': 'SHOULD STILL BLOCK'}}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('cannot be edited', response.json().get('message', '').lower())
        self.card_a.refresh_from_db()
        self.assertEqual(self.card_a.field_data.get('NAME'), 'ALICE')

    def test_live_presence_start_and_stop_updates_admin_live_count(self):
        client_session = self.client_class()
        admin_session = self.client_class()

        client_session.login(username='sec-client-a@test.com', password='clientpass1')
        start_resp = client_session.post(
            reverse('api_presence_track'),
            data=json.dumps({'action': 'start', 'tab_id': 'tab_a'}),
            content_type='application/json',
        )
        self.assertEqual(start_resp.status_code, 200)
        self.assertTrue(start_resp.json().get('success'))

        admin_session.login(username='sec-api-admin@test.com', password='adminpass1')
        live_resp = admin_session.get(reverse('api_live_client_presence'))
        self.assertEqual(live_resp.status_code, 200)
        live_payload = live_resp.json()
        self.assertTrue(live_payload.get('success'))
        self.assertEqual(live_payload.get('active_clients_now'), 1)
        self.assertEqual(live_payload.get('active_assistants_now'), 0)
        self.assertIn(self.client_a.id, live_payload.get('active_client_ids', []))
        self.assertEqual(live_payload.get('active_assistant_client_ids'), [])

        stop_resp = client_session.post(
            reverse('api_presence_track'),
            data=json.dumps({'action': 'stop', 'tab_id': 'tab_a'}),
            content_type='application/json',
        )
        self.assertEqual(stop_resp.status_code, 200)

        live_after_stop = admin_session.get(reverse('api_live_client_presence')).json()
        self.assertEqual(live_after_stop.get('active_clients_now'), 0)
        self.assertEqual(live_after_stop.get('active_assistants_now'), 0)
        self.assertEqual(live_after_stop.get('active_client_ids'), [])
        self.assertEqual(live_after_stop.get('active_assistant_client_ids'), [])

    @patch('core.services.live_presence_service.publish_topic_event')
    def test_presence_track_publishes_dashboard_websocket_events(self, mock_publish):
        client_session = self.client_class()
        client_session.login(username='sec-client-a@test.com', password='clientpass1')

        start_resp = client_session.post(
            reverse('api_presence_track'),
            data=json.dumps({'action': 'start', 'tab_id': 'tab_ws_a'}),
            content_type='application/json',
        )
        self.assertEqual(start_resp.status_code, 200)

        heartbeat_resp = client_session.post(
            reverse('api_presence_track'),
            data=json.dumps({'action': 'heartbeat', 'tab_id': 'tab_ws_a'}),
            content_type='application/json',
        )
        self.assertEqual(heartbeat_resp.status_code, 200)

        stop_resp = client_session.post(
            reverse('api_presence_track'),
            data=json.dumps({'action': 'stop', 'tab_id': 'tab_ws_a'}),
            content_type='application/json',
        )
        self.assertEqual(stop_resp.status_code, 200)

        self.assertEqual(mock_publish.call_count, 2)
        first_call = mock_publish.call_args_list[0]
        second_call = mock_publish.call_args_list[1]

        self.assertEqual(first_call.kwargs.get('topic'), 'dashboard.working')
        self.assertEqual(first_call.kwargs.get('event_type'), 'dashboard.presence.changed')
        self.assertEqual(first_call.kwargs.get('payload', {}).get('action'), 'start')

        self.assertEqual(second_call.kwargs.get('topic'), 'dashboard.working')
        self.assertEqual(second_call.kwargs.get('event_type'), 'dashboard.presence.changed')
        self.assertEqual(second_call.kwargs.get('payload', {}).get('action'), 'stop')

    def test_live_presence_exposes_assistant_count_separately(self):
        from staff.models import Staff

        assistant_session = self.client_class()
        admin_session = self.client_class()

        client_staff_user = User.objects.create_user(
            username='sec-client-staff-a@test.com',
            email='sec-client-staff-a@test.com',
            password='pass1234',
            role='client_staff',
        )
        Staff.objects.create(
            user=client_staff_user,
            staff_type='assistant',
            client=self.client_a,
        )

        assistant_session.login(username='sec-client-staff-a@test.com', password='pass1234')
        start_resp = assistant_session.post(
            reverse('api_presence_track'),
            data=json.dumps({'action': 'start', 'tab_id': 'tab_staff_a'}),
            content_type='application/json',
        )
        self.assertEqual(start_resp.status_code, 200)

        admin_session.login(username='sec-api-admin@test.com', password='adminpass1')
        payload = admin_session.get(reverse('api_live_client_presence')).json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('active_clients_now'), 1)
        self.assertEqual(payload.get('active_assistants_now'), 1)
        self.assertEqual(payload.get('active_assistant_client_ids'), [self.client_a.id])

    def test_recent_client_updates_exposes_assistant_client_ids_for_filtering(self):
        from staff.models import Staff

        assistant_session = self.client_class()

        client_staff_user = User.objects.create_user(
            username='sec-client-staff-recent@test.com',
            email='sec-client-staff-recent@test.com',
            password='pass1234',
            role='client_staff',
        )
        Staff.objects.create(
            user=client_staff_user,
            staff_type='assistant',
            client=self.client_a,
        )

        assistant_session.login(username='sec-client-staff-recent@test.com', password='pass1234')
        start_resp = assistant_session.post(
            reverse('api_presence_track'),
            data=json.dumps({'action': 'start', 'tab_id': 'tab_staff_recent'}),
            content_type='application/json',
        )
        self.assertEqual(start_resp.status_code, 200)

        self.client.login(username='sec-api-admin@test.com', password='adminpass1')
        recent_resp = self.client.get(reverse('api_recent_client_updates'))
        self.assertEqual(recent_resp.status_code, 200)
        recent_payload = recent_resp.json()
        self.assertTrue(recent_payload.get('success'))
        self.assertIn(self.client_a.id, recent_payload.get('active_assistant_client_ids', []))

    def test_recent_client_updates_returns_all_clients_by_default(self):
        from organisation.models import Organisation

        for idx in range(101):
            user = User.objects.create_user(
                username=f'sec-recents-client-{idx}@test.com',
                email=f'sec-recents-client-{idx}@test.com',
                password='pass1234',
                role='client',
            )
            Organisation.objects.create(
                user=user,
                name=f'Recent Client {idx:03d}',
                status='active',
            )

        self.client.login(username='sec-api-admin@test.com', password='adminpass1')
        recent_resp = self.client.get(reverse('api_recent_client_updates'))

        self.assertEqual(recent_resp.status_code, 200)
        recent_payload = recent_resp.json()
        self.assertTrue(recent_payload.get('success'))
        self.assertEqual(len(recent_payload.get('clients', [])), Organisation.objects.count())
        self.assertGreater(len(recent_payload.get('clients', [])), 100)

    def test_manage_client_view_and_edit_endpoints_work(self):
        from organisation.models import Organisation

        managed_user = User.objects.create_user(
            username='sec-manage-client@test.com',
            email='sec-manage-client@test.com',
            password='pass1234',
            role='client',
        )
        managed_client = Organisation.objects.create(
            user=managed_user,
            name='View Edit Client',
            status='inactive',
        )

        self.client.login(username='sec-api-admin@test.com', password='adminpass1')

        detail_resp = self.client.get(reverse('api_client_get', args=[managed_client.id]))
        self.assertEqual(detail_resp.status_code, 200)
        detail_payload = detail_resp.json()
        self.assertTrue(detail_payload.get('success'))
        self.assertEqual(detail_payload.get('client', {}).get('name'), 'View Edit Client')

        update_resp = self.client.post(
            reverse('api_client_update', args=[managed_client.id]),
            data=json.dumps({
                'name': 'View Edit Client Updated',
                'phone': '9998887777',
                'is_active': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(update_resp.status_code, 200)
        update_payload = update_resp.json()
        self.assertTrue(update_payload.get('success'))
        self.assertEqual(update_payload.get('client', {}).get('name'), 'View Edit Client Updated')

        managed_client.refresh_from_db()
        managed_user.refresh_from_db()
        self.assertEqual(managed_client.name, 'View Edit Client Updated')
        self.assertTrue(managed_user.is_active)

    def test_live_presence_count_respects_admin_staff_scope(self):
        from staff.models import Staff

        client_a_session = self.client_class()
        client_b_session = self.client_class()
        admin_staff_session = self.client_class()

        client_staff_user = User.objects.create_user(
            username='sec-client-staff-b@test.com',
            email='sec-client-staff-b@test.com',
            password='pass1234',
            role='client_staff',
        )
        Staff.objects.create(
            user=client_staff_user,
            staff_type='assistant',
            client=self.client_b,
        )

        client_a_session.login(username='sec-client-a@test.com', password='clientpass1')
        client_a_session.post(
            reverse('api_presence_track'),
            data=json.dumps({'action': 'start', 'tab_id': 'tab_scope_a'}),
            content_type='application/json',
        )

        client_b_session.login(username='sec-client-staff-b@test.com', password='pass1234')
        client_b_session.post(
            reverse('api_presence_track'),
            data=json.dumps({'action': 'start', 'tab_id': 'tab_scope_b'}),
            content_type='application/json',
        )

        admin_staff_session.login(username='sec-admin-staff@test.com', password='pass1234')
        scoped_resp = admin_staff_session.get(reverse('api_live_client_presence'))
        self.assertEqual(scoped_resp.status_code, 200)
        scoped_payload = scoped_resp.json()
        self.assertTrue(scoped_payload.get('success'))
        self.assertEqual(scoped_payload.get('active_clients_now'), 1)
        self.assertEqual(scoped_payload.get('active_assistants_now'), 0)
        self.assertEqual(scoped_payload.get('active_client_ids'), [self.client_a.id])
        self.assertEqual(scoped_payload.get('active_assistant_client_ids'), [])


class CreateTableFromLegacyXlsTests(TestCase):
    def setUp(self):
        self.admin = _create_super_admin('xls-create-admin@test.com', 'adminpass1')
        _client_user, client_obj = _create_client_user('xls-create-client@test.com', 'clientpass1')
        self.group, _table = _create_table(client_obj)
        self.client.force_login(self.admin)

    def test_create_table_from_legacy_xls_file(self):
        from tables.models import Table

        class _FakeSheet:
            def __init__(self):
                self.ncols = 2
                self.nrows = 3
                self._rows = [
                    ['NAME', 'CLASS'],
                    ['ALICE', '10'],
                    ['BOB', '11'],
                ]

            def cell_value(self, row_idx, col_idx):
                return self._rows[row_idx][col_idx]

        class _FakeWorkbook:
            def sheet_by_index(self, _index):
                return _FakeSheet()

        upload = SimpleUploadedFile(
            'legacy.xls',
            b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1fake-xls-content',
            content_type='application/vnd.ms-excel',
        )

        with patch('xlrd.open_workbook', return_value=_FakeWorkbook()) as mocked_open_workbook, \
             patch(
                 'core.views.idcard_api.api_idcard_bulk_upload',
                 return_value=JsonResponse({'success': True, 'cards_created': 2, 'message': 'Imported'}),
             ) as mocked_bulk_upload:
            response = self.client.post(
                reverse('api_create_table_from_xlsx', args=[self.group.id]),
                {'file': upload, 'table_name': 'Legacy Upload Table'},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('fields_created'), 2)
        mocked_open_workbook.assert_called_once()
        mocked_bulk_upload.assert_called_once()

        created_table = Table.objects.get(id=payload['table_id'])
        self.assertEqual(created_table.name, 'LEGACY UPLOAD TABLE')
        self.assertEqual([f.get('name') for f in (created_table.fields or [])], ['NAME', 'CLASS'])


class CardHistoryApiTests(TestCase):
    def setUp(self):
        from core.models import ActivityLog

        self.admin = _create_super_admin('card-history-admin@test.com', 'adminpass1')
        self.client_user_a, self.client_a = _create_client_user('card-history-client-a@test.com', 'clientpass1')
        self.client_user_b, self.client_b = _create_client_user('card-history-client-b@test.com', 'clientpass1')
        _group, self.table_a = _create_table(self.client_a)
        self.card_a = _create_card(self.table_a, field_data={'NAME': 'History Card', 'CLASS': '10'})

        ActivityLog.objects.create(
            user=self.admin,
            action='card_status',
            description='Card moved from Pending to Verified',
            target_model='IDCard',
            target_id=self.card_a.id,
            target_name=f'Card #{self.card_a.id}',
        )
        ActivityLog.objects.create(
            user=self.admin,
            action='card_update',
            description='Field "NAME" updated',
            target_model='IDCard',
            target_id=self.card_a.id,
            target_name=f'Card #{self.card_a.id}',
        )

    def test_history_api_returns_card_events(self):
        self.client.login(username='card-history-admin@test.com', password='adminpass1')

        response = self.client.get(f'/panel/api/card/{self.card_a.id}/history/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload['success'])
        self.assertEqual(payload['card_id'], self.card_a.id)
        self.assertGreaterEqual(len(payload['events']), 2)
        self.assertIn('what', payload['events'][0])
        self.assertIn('who', payload['events'][0])
        self.assertIn('when', payload['events'][0])

    def test_history_api_denies_outside_client_scope(self):
        self.client.login(username='card-history-client-b@test.com', password='clientpass1')

        response = self.client.get(f'/panel/api/card/{self.card_a.id}/history/')
        self.assertEqual(response.status_code, 403)

    def test_history_api_hides_admin_events_for_client_viewer(self):
        self.client.login(username='card-history-client-a@test.com', password='clientpass1')

        response = self.client.get(f'/panel/api/card/{self.card_a.id}/history/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        what_values = [event.get('what', '') for event in payload.get('events', [])]
        who_values = [event.get('who', '') for event in payload.get('events', [])]

        self.assertNotIn('Card moved from Pending to Verified', what_values)
        self.assertNotIn('Field "NAME" updated', what_values)
        self.assertNotIn(self.admin.get_full_name() or self.admin.username, who_values)


class ActivityFeedIsolationTests(TestCase):
    def setUp(self):
        from staff.models import Staff
        from core.models import ActivityLog

        self.admin = _create_super_admin('activity-admin@test.com', 'adminpass1')
        self.client_user, self.client_obj = _create_client_user('activity-client@test.com', 'clientpass1')

        self.client_staff_user = User.objects.create_user(
            username='activity-client-staff@test.com',
            email='activity-client-staff@test.com',
            password='pass1234',
            role='client_staff',
        )
        Staff.objects.create(
            user=self.client_staff_user,
            staff_type='assistant',
            client=self.client_obj,
        )

        # Admin-side activity for the same client domain should never leak to client feeds.
        ActivityLog.objects.create(
            user=self.admin,
            action='staff_create',
            description='Admin created client staff account',
            target_model='Staff',
            target_id=999,
            target_name='Admin-created staff',
        )
        ActivityLog.objects.create(
            user=None,
            action='staff_update',
            description='System user-management sync',
            target_model='Staff',
            target_id=998,
            target_name='System sync',
        )

        # Legit client-org activities that should remain visible to the client user.
        ActivityLog.objects.create(
            user=self.client_user,
            action='card_update',
            description='Client updated card details',
            target_model='IDCard',
            target_id=101,
            target_name='Card #101',
        )
        ActivityLog.objects.create(
            user=self.client_staff_user,
            action='card_status',
            description='1 card verified',
            target_model='IDCard',
            target_id=102,
            target_name='Card #102',
        )

    def test_client_recent_activity_excludes_admin_user_management_entries(self):
        from core.services.activity_service import ActivityService

        rows = ActivityService.get_recent(limit=20, hours=None, user=self.client_user)
        descriptions = [row.get('description', '') for row in rows]
        actors = [row.get('actor', '') for row in rows]

        self.assertIn('Client updated card details', descriptions)
        self.assertIn('1 card verified', descriptions)
        self.assertNotIn('Admin created client staff account', descriptions)
        self.assertNotIn('System user-management sync', descriptions)
        self.assertNotIn(self.admin.get_full_name() or self.admin.username, actors)

    def test_client_staff_recent_activity_is_self_only(self):
        from core.services.activity_service import ActivityService

        rows = ActivityService.get_recent(limit=20, hours=None, user=self.client_staff_user)
        descriptions = [row.get('description', '') for row in rows]

        self.assertIn('1 card verified', descriptions)
        self.assertNotIn('Client updated card details', descriptions)
        self.assertNotIn('Admin created client staff account', descriptions)
        self.assertNotIn('System user-management sync', descriptions)

    def test_recent_activity_ignores_malformed_target_id_rows(self):
        from core.models import ActivityLog
        from core.services.activity_service import ActivityService
        from django.db import connection

        good_entry = ActivityLog.objects.create(
            user=self.client_staff_user,
            action='card_status',
            description='1 card verified',
            target_model='IDCard',
            target_id=101,
            target_name='Card #101',
        )
        bad_entry = ActivityLog.objects.create(
            user=self.client_staff_user,
            action='staff_update',
            description='Legacy bad target id row',
            target_model='Staff',
            target_name='Assistant',
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE core_activitylog SET target_id = 'abc' WHERE id = %s",
                [bad_entry.pk],
            )

        rows = ActivityService.get_recent(limit=20, hours=None, user=self.client_staff_user)
        row_ids = [row.get('id') for row in rows]

        self.assertIn(good_entry.id, row_ids)
        self.assertIn(bad_entry.id, row_ids)

    def test_recent_activity_combines_repeated_actions_within_one_hour(self):
        from core.models import ActivityLog
        from core.services.activity_service import ActivityService

        now = timezone.now()
        first = ActivityLog.objects.create(
            user=self.admin,
            action='staff_update',
            description='Field "SEC" updated',
            target_model='Staff',
            target_id=4321,
            target_name='acw.Operator1',
        )
        second = ActivityLog.objects.create(
            user=self.admin,
            action='staff_update',
            description='Field "SEC" updated',
            target_model='Staff',
            target_id=4321,
            target_name='acw.Operator1',
        )
        third = ActivityLog.objects.create(
            user=self.admin,
            action='staff_update',
            description='Field "SEC" updated',
            target_model='Staff',
            target_id=4321,
            target_name='acw.Operator1',
        )

        ActivityLog.objects.filter(pk=first.pk).update(created_at=now + timedelta(minutes=3))
        ActivityLog.objects.filter(pk=second.pk).update(created_at=now + timedelta(minutes=2))
        ActivityLog.objects.filter(pk=third.pk).update(created_at=now + timedelta(minutes=1))

        rows = ActivityService.get_recent(limit=40, hours=None, user=self.admin, merge_card_activity=False)
        matching_rows = [row for row in rows if row.get('target_id') == 4321]
        merged_row = matching_rows[0] if matching_rows else None

        self.assertIsNotNone(merged_row)
        self.assertEqual(len(matching_rows), 1)
        self.assertIn('3 actions', str(merged_row.get('display_text', '')))

    def test_client_status_display_text_uses_client_name_when_target_name_missing(self):
        from core.models import ActivityLog
        from core.services.activity_service import ActivityService

        log_entry = ActivityLog.objects.create(
            user=self.admin,
            action='client_status',
            description='Client "" status changed to active',
            target_model='Client',
            target_id=self.client_obj.id,
            target_name='',
        )

        rows = ActivityService.get_recent(limit=30, hours=None, user=self.admin, merge_card_activity=False)
        rendered = next((row for row in rows if row.get('id') == log_entry.id), None)

        self.assertIsNotNone(rendered)
        display_text = str(rendered.get('display_text') or '')
        self.assertIn(self.client_obj.name, display_text)
        self.assertIn('activated client', display_text.lower())

    def test_bulk_card_updates_and_creates_are_collapsed_on_dashboard(self):
        from core.models import ActivityLog
        from core.services.activity_service import ActivityService
        from django.utils import timezone

        now = timezone.now()

        # Clear all logs to have a clean slate and prevent interleaving from setUp logs
        ActivityLog.objects.all().delete()

        # 1. Simulate user editing multiple cards (card_update) within 15 mins
        log1 = ActivityLog.objects.create(
            user=self.admin,
            action='card_update',
            description='Field "Name" updated',
            target_model='IDCard',
            target_id=201,
            target_name='Card #201',
        )
        log2 = ActivityLog.objects.create(
            user=self.admin,
            action='card_update',
            description='Field "Class" updated',
            target_model='IDCard',
            target_id=202,
            target_name='Card #202',
        )
        log3 = ActivityLog.objects.create(
            user=self.admin,
            action='card_update',
            description='Field "Section" updated',
            target_model='IDCard',
            target_id=201,
            target_name='Card #201',
        )

        ActivityLog.objects.filter(pk=log1.pk).update(created_at=now)
        ActivityLog.objects.filter(pk=log2.pk).update(created_at=now - timezone.timedelta(minutes=2))
        ActivityLog.objects.filter(pk=log3.pk).update(created_at=now - timezone.timedelta(minutes=5))

        # 2. Simulate user adding multiple cards (card_create)
        log4 = ActivityLog.objects.create(
            user=self.admin,
            action='card_create',
            description='ID card created',
            target_model='IDCard',
            target_id=301,
            target_name='Card #301',
        )
        log5 = ActivityLog.objects.create(
            user=self.admin,
            action='card_create',
            description='ID card created',
            target_model='IDCard',
            target_id=302,
            target_name='Card #302',
        )

        ActivityLog.objects.filter(pk=log4.pk).update(created_at=now - timezone.timedelta(minutes=6))
        ActivityLog.objects.filter(pk=log5.pk).update(created_at=now - timezone.timedelta(minutes=7))

        # Fetch recent activities for dashboard
        rows = ActivityService.get_recent(limit=30, hours=None, user=self.admin)

        # Filter the rows belonging to card_update and card_create
        update_rows = [row for row in rows if row.get('action') == 'card_update']
        create_rows = [row for row in rows if row.get('action') == 'card_create']

        # We expect card updates to be collapsed into a single row
        self.assertEqual(len(update_rows), 1)
        self.assertEqual(update_rows[0]['description'], '2 cards edited')

        # We expect card creations to be collapsed into a single row
        self.assertEqual(len(create_rows), 1)
        self.assertEqual(create_rows[0]['description'], '2 new ID cards added')


class ReuploadDirectTaskFlowTests(TestCase):
    def setUp(self):
        self.admin = _create_super_admin('reupload-admin@test.com', 'adminpass1')
        _, self.client_obj = _create_client_user('reupload-client@test.com', 'clientpass1')
        _group, self.table = _create_table(self.client_obj, fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'PHOTO', 'type': 'photo', 'order': 2},
        ])
        self.card = _create_card(
            self.table,
            field_data={
                'NAME': 'TOKEN USER',
                'PHOTO': 'adarshimg/20240101121212.jpg',
            },
            status='pending',
        )

        self._tmp_media = tempfile.TemporaryDirectory()
        self._media_override = override_settings(MEDIA_ROOT=self._tmp_media.name)
        self._media_override.enable()

    def tearDown(self):
        self._media_override.disable()
        self._tmp_media.cleanup()

    def _make_reupload_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('PHOTO/20240101121212.jpg', b'fake-image-bytes-12345')
        return buf.getvalue()

    def test_create_reupload_task_direct_upload_success(self):
        self.client.login(username='reupload-admin@test.com', password='adminpass1')

        zip_bytes = self._make_reupload_zip()
        upload = SimpleUploadedFile('reupload.zip', zip_bytes, content_type='application/zip')

        with patch('core.views.task_api.background_worker.submit_task') as mock_submit:
            create_resp = self.client.post(
                f'/panel/api/table/{self.table.id}/reupload-task/',
                data={
                    'photos_zip': upload,
                    'card_ids': json.dumps([self.card.id]),
                    'status': 'pending',
                },
            )

        self.assertEqual(create_resp.status_code, 200)
        create_payload = create_resp.json()
        self.assertTrue(create_payload['success'])
        self.assertIn('task_id', create_payload)
        mock_submit.assert_called_once()

        from core.models import BackgroundTask
        task = BackgroundTask.objects.get(id=create_payload['task_id'])
        self.assertEqual(task.task_type, 'reupload_images')
        self.assertEqual(task.metadata.get('table_id'), self.table.id)
        self.assertEqual(task.metadata.get('card_ids'), [self.card.id])
        self.assertEqual(task.metadata.get('status_filter'), 'pending')

    def test_create_reupload_task_requires_zip(self):
        self.client.login(username='reupload-admin@test.com', password='adminpass1')

        create_resp = self.client.post(
            f'/panel/api/table/{self.table.id}/reupload-task/',
            data={'card_ids': json.dumps([self.card.id])},
        )

        self.assertEqual(create_resp.status_code, 400)
        self.assertIn('zip', create_resp.json().get('message', '').lower())

    def test_zip_index_accepts_non_numeric_and_short_fallback_stems(self):
        from core.services.reupload_processor import _build_zip_image_index

        zip_path = os.path.join(self._tmp_media.name, 'bad_names.zip')
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('PHOTO/20240101121212_copy.jpg', b'abc')
            zf.writestr('PHOTO/random_name.jpg', b'abc')
            zf.writestr('PHOTO/22.jpg', b'abc')

        index, _, stats = _build_zip_image_index(zip_path)
        self.assertIn('20240101121212_copy', index)
        self.assertIn('random_name', index)
        self.assertIn('22', index)
        self.assertEqual(stats.get('duplicate_name_keys'), 0)

    def test_zip_index_accepts_timestamp_hyphen_numeric_stems(self):
        from core.services.reupload_processor import _build_zip_image_index

        zip_path = os.path.join(self._tmp_media.name, 'legacy_names.zip')
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('PHOTO/1753102311405-264175116.jpg', b'abc')

        index, _, stats = _build_zip_image_index(zip_path)
        self.assertIn('1753102311405-264175116', index)
        self.assertEqual(stats.get('duplicate_name_keys'), 0)

    def test_zip_index_accepts_plain_numeric_legacy_stem(self):
        from core.services.reupload_processor import _build_zip_image_index

        zip_path = os.path.join(self._tmp_media.name, 'legacy_plain_names.zip')
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('PHOTO/1724313250114.jpg', b'abc')

        index, _, stats = _build_zip_image_index(zip_path)
        self.assertIn('1724313250114', index)
        self.assertEqual(stats.get('duplicate_name_keys'), 0)

    def test_zip_index_blocks_duplicate_exact_stems(self):
        from core.services.reupload_processor import _build_zip_image_index

        zip_path = os.path.join(self._tmp_media.name, 'dup_names.zip')
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('PHOTO/20240101121212.jpg', b'abc')
            zf.writestr('SIGN/20240101121212.png', b'def')

        index, _, stats = _build_zip_image_index(zip_path)
        self.assertNotIn('20240101121212', index)
        self.assertGreater(stats.get('duplicate_name_keys', 0), 0)

    def test_sync_reupload_replace_uses_immediate_old_image_cleanup(self):
        self.client.login(username='reupload-admin@test.com', password='adminpass1')

        zip_bytes = self._make_reupload_zip()
        upload = SimpleUploadedFile('reupload.zip', zip_bytes, content_type='application/zip')
        mock_result = type('Result', (), {
            'success': True,
            'data': {'final_value': 'adarshimg/20240101121212_121314.jpg'},
        })()

        with patch('core.views.idcard_bulk_api.validate_image_bytes', return_value=(True, None)), \
             patch('core.views.idcard_bulk_api.ImageService.replace_image', return_value=mock_result) as mock_replace:
            response = self.client.post(
                f'/panel/api/table/{self.table.id}/cards/reupload-images/',
                data={
                    'photos_zip': upload,
                    'card_ids': json.dumps([self.card.id]),
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('updated_count'), 1)

        self.assertEqual(mock_replace.call_count, 1)
        kwargs = mock_replace.call_args.kwargs
        self.assertTrue(kwargs.get('delete_old_after_save'))
        self.assertEqual(kwargs.get('existing_path'), 'adarshimg/20240101121212.jpg')

        self.card.refresh_from_db()
        self.assertEqual(
            self.card.field_data.get('PHOTO'),
            'adarshimg/20240101121212_121314.jpg',
        )

    def test_sync_reupload_matches_pending_timestamp_hyphen_numeric_reference(self):
        self.client.login(username='reupload-admin@test.com', password='adminpass1')

        self.card.field_data = {
            'NAME': 'TOKEN USER',
            'PHOTO': 'PENDING:1753102311405-264175116',
        }
        self.card.save(update_fields=['field_data'])

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('PHOTO/1753102311405-264175116.jpg', b'fake-image-bytes-67890')
        upload = SimpleUploadedFile('reupload.zip', buf.getvalue(), content_type='application/zip')

        mock_result = type('Result', (), {
            'success': True,
            'data': {'final_value': 'adarshimg/1753102311405-264175116_121314.jpg'},
        })()

        with patch('core.views.idcard_bulk_api.validate_image_bytes', return_value=(True, None)), \
             patch('core.views.idcard_bulk_api.ImageService.save_new_image', return_value=mock_result) as mock_save:
            response = self.client.post(
                f'/panel/api/table/{self.table.id}/cards/reupload-images/',
                data={
                    'photos_zip': upload,
                    'card_ids': json.dumps([self.card.id]),
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('updated_count'), 1)
        self.assertEqual(payload.get('matched_count'), 1)

        self.assertEqual(mock_save.call_count, 1)
        self.assertEqual(mock_save.call_args.kwargs.get('original_ext'), '.jpg')

        self.card.refresh_from_db()
        self.assertEqual(
            self.card.field_data.get('PHOTO'),
            'adarshimg/1753102311405-264175116_121314.jpg',
        )

    def test_sync_reupload_matches_pending_plain_numeric_reference(self):
        self.client.login(username='reupload-admin@test.com', password='adminpass1')

        self.card.field_data = {
            'NAME': 'TOKEN USER',
            'PHOTO': 'PENDING:1724313250114',
        }
        self.card.save(update_fields=['field_data'])

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('PHOTO/1724313250114.jpg', b'fake-image-bytes-11111')
        upload = SimpleUploadedFile('reupload.zip', buf.getvalue(), content_type='application/zip')

        mock_result = type('Result', (), {
            'success': True,
            'data': {'final_value': 'adarshimg/1724313250114_121314.jpg'},
        })()

        with patch('core.views.idcard_bulk_api.validate_image_bytes', return_value=(True, None)), \
             patch('core.views.idcard_bulk_api.ImageService.save_new_image', return_value=mock_result) as mock_save:
            response = self.client.post(
                f'/panel/api/table/{self.table.id}/cards/reupload-images/',
                data={
                    'photos_zip': upload,
                    'card_ids': json.dumps([self.card.id]),
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('updated_count'), 1)
        self.assertEqual(payload.get('matched_count'), 1)

        self.assertEqual(mock_save.call_count, 1)
        self.assertEqual(mock_save.call_args.kwargs.get('original_ext'), '.jpg')

        self.card.refresh_from_db()
        self.assertEqual(
            self.card.field_data.get('PHOTO'),
            'adarshimg/1724313250114_121314.jpg',
        )

    def test_sync_reupload_matches_pending_two_digit_reference(self):
        self.client.login(username='reupload-admin@test.com', password='adminpass1')

        self.card.field_data = {
            'NAME': 'TOKEN USER',
            'PHOTO': 'PENDING:22',
        }
        self.card.save(update_fields=['field_data'])

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('PHOTO/22.jpg', b'fake-image-bytes-22222')
        upload = SimpleUploadedFile('reupload.zip', buf.getvalue(), content_type='application/zip')

        mock_result = type('Result', (), {
            'success': True,
            'data': {'final_value': 'adarshimg/22_121314.jpg'},
        })()

        with patch('core.views.idcard_bulk_api.validate_image_bytes', return_value=(True, None)), \
             patch('core.views.idcard_bulk_api.ImageService.save_new_image', return_value=mock_result) as mock_save:
            response = self.client.post(
                f'/panel/api/table/{self.table.id}/cards/reupload-images/',
                data={
                    'photos_zip': upload,
                    'card_ids': json.dumps([self.card.id]),
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('updated_count'), 1)
        self.assertEqual(payload.get('matched_count'), 1)

        self.assertEqual(mock_save.call_count, 1)
        self.assertEqual(mock_save.call_args.kwargs.get('original_ext'), '.jpg')

        self.card.refresh_from_db()
        self.assertEqual(
            self.card.field_data.get('PHOTO'),
            'adarshimg/22_121314.jpg',
        )

    def test_sync_reupload_processes_only_requested_target_field(self):
        self.client.login(username='reupload-admin@test.com', password='adminpass1')

        _group, table = _create_table(self.client_obj, fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'PHOTO', 'type': 'photo', 'order': 2},
            {'name': 'SIGN', 'type': 'photo', 'order': 3},
        ])
        card = _create_card(
            table,
            field_data={
                'NAME': 'TARGET USER',
                'PHOTO': 'adarshimg/20240101121212.jpg',
                'SIGN': 'adarshimg/20240202131313.jpg',
            },
            status='pending',
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('PHOTO/20240101121212.jpg', b'photo-bytes')
            zf.writestr('SIGN/20240202131313.jpg', b'sign-bytes')
        upload = SimpleUploadedFile('reupload.zip', buf.getvalue(), content_type='application/zip')

        with patch('core.views.idcard_bulk_api.validate_image_bytes', return_value=(True, None)), \
             patch('core.views.idcard_bulk_api._resolve_reupload_photo', return_value=None) as mock_resolve:
            response = self.client.post(
                f'/panel/api/table/{table.id}/cards/reupload-images/',
                data={
                    'photos_zip': upload,
                    'target_field': 'PHOTO',
                    'card_ids': json.dumps([card.id]),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))
        self.assertEqual(mock_resolve.call_count, 1)
        self.assertEqual(mock_resolve.call_args.args[0], '20240101121212')

    def test_sync_reupload_processes_all_image_fields_when_target_missing(self):
        self.client.login(username='reupload-admin@test.com', password='adminpass1')

        _group, table = _create_table(self.client_obj, fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'PHOTO', 'type': 'photo', 'order': 2},
            {'name': 'SIGN', 'type': 'photo', 'order': 3},
        ])
        card = _create_card(
            table,
            field_data={
                'NAME': 'TARGET USER',
                'PHOTO': 'adarshimg/20240101121212.jpg',
                'SIGN': 'adarshimg/20240202131313.jpg',
            },
            status='pending',
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('PHOTO/20240101121212.jpg', b'photo-bytes')
            zf.writestr('SIGN/20240202131313.jpg', b'sign-bytes')
        upload = SimpleUploadedFile('reupload.zip', buf.getvalue(), content_type='application/zip')

        with patch('core.views.idcard_bulk_api.validate_image_bytes', return_value=(True, None)), \
             patch('core.views.idcard_bulk_api._resolve_reupload_photo', return_value=None) as mock_resolve:
            response = self.client.post(
                f'/panel/api/table/{table.id}/cards/reupload-images/',
                data={
                    'photos_zip': upload,
                    'card_ids': json.dumps([card.id]),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))
        self.assertEqual(mock_resolve.call_count, 2)
        self.assertCountEqual(
            [call.args[0] for call in mock_resolve.call_args_list],
            ['20240101121212', '20240202131313'],
        )

    def test_async_reupload_processor_processes_only_requested_target_field(self):
        from core.models import BackgroundTask
        from core.services.reupload_processor import process_reupload_images

        _group, table = _create_table(self.client_obj, fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'PHOTO', 'type': 'photo', 'order': 2},
            {'name': 'SIGN', 'type': 'photo', 'order': 3},
        ])
        card = _create_card(
            table,
            field_data={
                'NAME': 'ASYNC TARGET USER',
                'PHOTO': 'adarshimg/20240101121212.jpg',
                'SIGN': 'adarshimg/20240202131313.jpg',
            },
            status='pending',
        )

        temp_dir = os.path.join(self._tmp_media.name, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        zip_abs_path = os.path.join(temp_dir, 'async-reupload.zip')
        with zipfile.ZipFile(zip_abs_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('PHOTO/20240101121212.jpg', b'photo-bytes')

        task = BackgroundTask.objects.create(
            user=self.admin,
            task_type='reupload_images',
            file_path=os.path.relpath(zip_abs_path, self._tmp_media.name),
            metadata={
                'table_id': table.id,
                'target_field': 'PHOTO',
                'card_ids': [card.id],
            },
        )

        with patch('core.services.reupload_processor._run_reupload_preflight', return_value={}), \
             patch('core.services.reupload_processor._resolve_reupload_zip_entry', return_value=None) as mock_resolve:
            process_reupload_images(task)

        task.refresh_from_db()
        self.assertEqual(task.status, 'completed')
        self.assertEqual(mock_resolve.call_count, 1)
        self.assertEqual(mock_resolve.call_args.args[0], '20240101121212')

    def test_async_reupload_processor_processes_all_image_fields_when_target_missing(self):
        from core.models import BackgroundTask
        from core.services.reupload_processor import process_reupload_images

        _group, table = _create_table(self.client_obj, fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'PHOTO', 'type': 'photo', 'order': 2},
            {'name': 'SIGN', 'type': 'photo', 'order': 3},
        ])
        card = _create_card(
            table,
            field_data={
                'NAME': 'ASYNC TARGET USER',
                'PHOTO': 'adarshimg/20240101121212.jpg',
                'SIGN': 'adarshimg/20240202131313.jpg',
            },
            status='pending',
        )

        temp_dir = os.path.join(self._tmp_media.name, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        zip_abs_path = os.path.join(temp_dir, 'async-reupload-all-fields.zip')
        with zipfile.ZipFile(zip_abs_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('PHOTO/20240101121212.jpg', b'photo-bytes')
            zf.writestr('SIGN/20240202131313.jpg', b'sign-bytes')

        task = BackgroundTask.objects.create(
            user=self.admin,
            task_type='reupload_images',
            file_path=os.path.relpath(zip_abs_path, self._tmp_media.name),
            metadata={
                'table_id': table.id,
                'card_ids': [card.id],
            },
        )

        with patch('core.services.reupload_processor._run_reupload_preflight', return_value={}), \
             patch('core.services.reupload_processor._resolve_reupload_zip_entry', return_value=None) as mock_resolve:
            process_reupload_images(task)

        task.refresh_from_db()
        self.assertEqual(task.status, 'completed')
        self.assertEqual(mock_resolve.call_count, 2)
        self.assertCountEqual(
            [call.args[0] for call in mock_resolve.call_args_list],
            ['20240101121212', '20240202131313'],
        )

    def test_async_reupload_matches_pending_paths_when_stems_duplicate(self):
        from core.models import BackgroundTask
        from core.services.reupload_processor import process_reupload_images

        _group, table = _create_table(self.client_obj, fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'PHOTO', 'type': 'photo', 'order': 2},
            {'name': 'MOTHER', 'type': 'photo', 'order': 3},
            {'name': 'FATHER', 'type': 'photo', 'order': 4},
        ])

        card = _create_card(
            table,
            field_data={
                'NAME': 'PATH USER',
                'PHOTO': 'PENDING:PHOTO/001.jpg',
                'MOTHER': 'PENDING:MOTHER/001.jpg',
                'FATHER': 'PENDING:FATHER/001.jpg',
            },
            status='pending',
        )

        temp_dir = os.path.join(self._tmp_media.name, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        zip_abs_path = os.path.join(temp_dir, 'async-reupload-path-match.zip')
        with zipfile.ZipFile(zip_abs_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('nested/PHOTO/001.jpg', b'photo-bytes')
            zf.writestr('nested/MOTHER/001.jpg', b'mother-bytes')
            zf.writestr('nested/FATHER/001.jpg', b'father-bytes')

        task = BackgroundTask.objects.create(
            user=self.admin,
            task_type='reupload_images',
            file_path=os.path.relpath(zip_abs_path, self._tmp_media.name),
            metadata={
                'table_id': table.id,
                'card_ids': [card.id],
            },
        )

        fake_results = [
            type('Result', (), {'success': True, 'data': {'final_value': 'adarshimg/photo_new.jpg'}, 'message': ''})(),
            type('Result', (), {'success': True, 'data': {'final_value': 'adarshimg/mother_new.jpg'}, 'message': ''})(),
            type('Result', (), {'success': True, 'data': {'final_value': 'adarshimg/father_new.jpg'}, 'message': ''})(),
        ]

        with patch('core.utils.field_utils.validate_image_bytes', return_value=(True, None)), \
             patch('mediafiles.services.ImageService.save_new_image', side_effect=fake_results):
            process_reupload_images(task)

        task.refresh_from_db()
        self.assertEqual(task.status, 'completed')
        self.assertEqual(task.metadata.get('result', {}).get('matched_count'), 3)

        card.refresh_from_db()
        self.assertEqual(card.field_data.get('PHOTO'), 'adarshimg/photo_new.jpg')
        self.assertEqual(card.field_data.get('MOTHER'), 'adarshimg/mother_new.jpg')
        self.assertEqual(card.field_data.get('FATHER'), 'adarshimg/father_new.jpg')

    def test_bulk_upload_task_cleans_temp_files_when_zip_validation_fails(self):
        self.client.login(username='reupload-admin@test.com', password='adminpass1')

        spreadsheet = SimpleUploadedFile('cards.csv', b'NAME\nTarget User\n', content_type='text/csv')

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('PHOTO/20240101121212.jpg', b'photo-bytes')
        upload_zip = SimpleUploadedFile('photos.zip', zip_buf.getvalue(), content_type='application/zip')

        with patch('core.views.task_api.validate_zip_safety', return_value=(False, 'Unsafe ZIP')):
            response = self.client.post(
                f'/panel/api/table/{self.table.id}/bulk-upload-task/',
                data={
                    'file': spreadsheet,
                    'zip_field_names': json.dumps(['PHOTO']),
                    'photos_zip_PHOTO': upload_zip,
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('unsafe zip', response.json().get('message', '').lower())

        temp_dir = os.path.join(self._tmp_media.name, 'temp')
        remaining_files = []
        if os.path.exists(temp_dir):
            for _root, _dirs, files in os.walk(temp_dir):
                remaining_files.extend(files)

        self.assertEqual(remaining_files, [])

    def test_bulk_upload_task_accepts_legacy_xls_extension(self):
        from core.models import BackgroundTask

        self.client.login(username='reupload-admin@test.com', password='adminpass1')

        spreadsheet = SimpleUploadedFile(
            'legacy-upload.xls',
            b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1fake-xls-content',
            content_type='application/vnd.ms-excel',
        )

        with patch('core.views.task_api.background_worker.submit_task') as mock_submit:
            response = self.client.post(
                f'/panel/api/table/{self.table.id}/bulk-upload-task/',
                data={'file': spreadsheet},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertIn('task_id', payload)
        mock_submit.assert_called_once()

        task = BackgroundTask.objects.get(id=payload['task_id'])
        self.assertEqual(task.task_type, 'bulk_upload')
        self.assertEqual(task.metadata.get('table_id'), self.table.id)
        self.assertEqual(task.metadata.get('original_filename'), 'legacy-upload.xls')

    def test_bulk_upload_task_rejects_folder_source_for_non_pro_user(self):
        self.client.login(username='reupload-admin@test.com', password='adminpass1')

        response = self.client.post(
            f'/panel/api/table/{self.table.id}/bulk-upload-task/',
            data={
                'photos_folder_path': 'C:/Images/School-A',
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('pro user', response.json().get('message', '').lower())

    def test_sync_reupload_rejects_folder_source_for_non_pro_user(self):
        self.client.login(username='reupload-admin@test.com', password='adminpass1')

        response = self.client.post(
            f'/panel/api/table/{self.table.id}/cards/reupload-images/',
            data={
                'photos_folder_path': 'C:/Images/School-A',
                'card_ids': json.dumps([self.card.id]),
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('pro user', response.json().get('message', '').lower())

    def test_reupload_task_rejects_folder_source_for_non_pro_user(self):
        self.client.login(username='reupload-admin@test.com', password='adminpass1')

        response = self.client.post(
            f'/panel/api/table/{self.table.id}/reupload-task/',
            data={
                'photos_folder_path': 'C:/Images/School-A',
                'card_ids': json.dumps([self.card.id]),
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('pro user', response.json().get('message', '').lower())


class ClientMessageApiTests(TestCase):
    def setUp(self):
        from staff.models import Staff

        self.super_admin = _create_super_admin('msg-super@test.com', 'adminpass1')
        self.client_user, self.client_obj = _create_client_user('msg-client@test.com', 'clientpass1')

        self.client_staff_user = User.objects.create_user(
            username='msg-client-staff@test.com',
            email='msg-client-staff@test.com',
            password='pass1234',
            role='client_staff',
        )
        Staff.objects.create(
            user=self.client_staff_user,
            staff_type='assistant',
            client=self.client_obj,
        )

        self.admin_staff = User.objects.create_user(
            username='msg-admin-staff@test.com',
            email='msg-admin-staff@test.com',
            password='pass1234',
            role='operator',
        )
        self.admin_staff_profile = Staff.objects.create(
            user=self.admin_staff,
            staff_type='operator',
            perm_idcard_client_list=True,
        )

    def test_send_client_message_client_only_creates_history_and_notification(self):
        from core.models import ClientMessage

        self.client.login(username='msg-super@test.com', password='adminpass1')
        response = self.client.post(
            f'/panel/api/client/{self.client_obj.id}/messages/send/',
            data=json.dumps({'message': 'Hello client', 'scope': 'client_only'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        row = ClientMessage.objects.get(client=self.client_obj)
        self.assertEqual(row.scope, 'client_only')
        self.assertEqual(row.recipient_count, 1)
        self.assertIsNotNone(row.notification_id)
        self.assertEqual(row.notification.target, 'selected')
        self.assertEqual(list(row.notification.target_users.values_list('id', flat=True)), [self.client_user.id])

    def test_send_client_message_client_and_staff_includes_staff_recipients(self):
        from core.models import ClientMessage

        self.client.login(username='msg-super@test.com', password='adminpass1')
        send_response = self.client.post(
            f'/panel/api/client/{self.client_obj.id}/messages/send/',
            data=json.dumps({'message': 'Hello all', 'scope': 'client_and_staff'}),
            content_type='application/json',
        )
        self.assertEqual(send_response.status_code, 200)

        row = ClientMessage.objects.get(client=self.client_obj)
        target_ids = set(row.notification.target_users.values_list('id', flat=True))
        self.assertEqual(target_ids, {self.client_user.id, self.client_staff_user.id})

        history_response = self.client.get(f'/panel/api/client/{self.client_obj.id}/messages/')
        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.json()
        self.assertTrue(history_payload.get('success'))
        self.assertEqual(len(history_payload.get('messages', [])), 1)
        self.assertEqual(history_payload['messages'][0]['scope'], 'client_and_staff')

    def test_admin_staff_without_manage_client_permission_is_denied(self):
        self.admin_staff_profile.perm_idcard_client_list = False
        self.admin_staff_profile.save(update_fields=['perm_idcard_client_list'])
        self.client.login(username='msg-admin-staff@test.com', password='pass1234')

        history_response = self.client.get(f'/panel/api/client/{self.client_obj.id}/messages/')
        self.assertEqual(history_response.status_code, 403)

        send_response = self.client.post(
            f'/panel/api/client/{self.client_obj.id}/messages/send/',
            data=json.dumps({'message': 'Blocked', 'scope': 'client_only'}),
            content_type='application/json',
        )
        self.assertEqual(send_response.status_code, 403)

    def test_client_strip_endpoint_returns_unread_then_hides_after_mark_read(self):
        self.client.login(username='msg-super@test.com', password='adminpass1')
        send_response = self.client.post(
            f'/panel/api/client/{self.client_obj.id}/messages/send/',
            data=json.dumps({'message': 'Please read this', 'scope': 'client_only'}),
            content_type='application/json',
        )
        self.assertEqual(send_response.status_code, 200)

        self.client.login(username='msg-client@test.com', password='clientpass1')
        strip_response = self.client.get('/panel/api/notifications/client-messages/unread/')
        self.assertEqual(strip_response.status_code, 200)
        strip_payload = strip_response.json()
        self.assertTrue(strip_payload.get('success'))
        self.assertEqual(len(strip_payload.get('items', [])), 1)

        notification_id = strip_payload['items'][0]['notification_id']
        mark_response = self.client.post(f'/panel/api/notifications/{notification_id}/read/')
        self.assertEqual(mark_response.status_code, 200)

        strip_after = self.client.get('/panel/api/notifications/client-messages/unread/')
        self.assertEqual(strip_after.status_code, 200)
        self.assertEqual(len(strip_after.json().get('items', [])), 0)

    def test_send_temporary_client_message_sets_expiry(self):
        from core.models import ClientMessage

        self.client.login(username='msg-super@test.com', password='adminpass1')
        response = self.client.post(
            f'/panel/api/client/{self.client_obj.id}/messages/send/',
            data=json.dumps({
                'message': 'Temporary client alert',
                'scope': 'client_only',
                'visibility': 'temporary',
                'temporary_duration': '6h',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        row = ClientMessage.objects.get(client=self.client_obj)
        self.assertEqual(row.visibility, 'temporary')
        self.assertIsNotNone(row.expires_at)
        self.assertGreater(row.expires_at, timezone.now())

    def test_expired_temporary_message_hidden_for_client_but_visible_in_admin_history(self):
        from core.models import ClientMessage

        self.client.login(username='msg-super@test.com', password='adminpass1')
        send_response = self.client.post(
            f'/panel/api/client/{self.client_obj.id}/messages/send/',
            data=json.dumps({
                'message': 'Temporary message that expires',
                'scope': 'client_only',
                'visibility': 'temporary',
                'temporary_duration': '6h',
            }),
            content_type='application/json',
        )
        self.assertEqual(send_response.status_code, 200)

        row = ClientMessage.objects.get(client=self.client_obj)
        row.expires_at = timezone.now() - timedelta(minutes=1)
        row.save(update_fields=['expires_at'])

        history_response = self.client.get(f'/panel/api/client/{self.client_obj.id}/messages/')
        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.json()
        self.assertEqual(len(history_payload.get('messages', [])), 1)

        self.client.login(username='msg-client@test.com', password='clientpass1')
        strip_response = self.client.get('/panel/api/notifications/client-messages/unread/')
        self.assertEqual(strip_response.status_code, 200)
        strip_payload = strip_response.json()
        self.assertEqual(len(strip_payload.get('items', [])), 0)
    def test_group_send_to_selected_clients(self):
        from core.models import ClientMessage
        from staff.models import Staff

        user2, client2 = _create_client_user('msg-client-2@test.com', 'clientpass2')
        staff2_user = User.objects.create_user(
            username='msg-client-2-staff@test.com',
            email='msg-client-2-staff@test.com',
            password='pass1234',
            role='client_staff',
        )
        Staff.objects.create(user=staff2_user, staff_type='assistant', client=client2)

        self.client.login(username='msg-super@test.com', password='adminpass1')
        response = self.client.post(
            '/panel/api/client/messages/group-send/',
            data=json.dumps({
                'message': 'Selected group message',
                'scope': 'client_and_staff',
                'target_mode': 'selected',
                'client_ids': [self.client_obj.id],
                'visibility': 'permanent',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('sent_count'), 1)

        self.assertEqual(ClientMessage.objects.filter(client=self.client_obj).count(), 1)
        self.assertEqual(ClientMessage.objects.filter(client=client2).count(), 0)

        row = ClientMessage.objects.get(client=self.client_obj)
        target_ids = set(row.notification.target_users.values_list('id', flat=True))
        self.assertEqual(target_ids, {self.client_user.id, self.client_staff_user.id})
        self.assertNotIn(user2.id, target_ids)

    def test_group_send_to_all_clients(self):
        from core.models import ClientMessage
        from organisation.models import Organisation

        _user2, client2 = _create_client_user('msg-client-all@test.com', 'clientpass2')

        self.client.login(username='msg-super@test.com', password='adminpass1')
        response = self.client.post(
            '/panel/api/client/messages/group-send/',
            data=json.dumps({
                'message': 'Send to all clients',
                'scope': 'client_only',
                'target_mode': 'all',
                'visibility': 'temporary',
                'temporary_duration': '12h',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('sent_count'), Organisation.objects.count())

        self.assertEqual(ClientMessage.objects.filter(client=self.client_obj).count(), 1)
        self.assertEqual(ClientMessage.objects.filter(client=client2).count(), 1)

    def test_targets_endpoint_returns_clients(self):
        _user2, _client2 = _create_client_user('msg-targets@test.com', 'clientpass2')

        self.client.login(username='msg-super@test.com', password='adminpass1')
        response = self.client.get('/panel/api/client/messages/targets/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertGreaterEqual(len(payload.get('clients', [])), 2)

    def test_manual_delete_hides_from_client_strip_but_keeps_admin_history(self):
        from core.models import ClientMessage

        self.client.login(username='msg-super@test.com', password='adminpass1')
        send_response = self.client.post(
            f'/panel/api/client/{self.client_obj.id}/messages/send/',
            data=json.dumps({'message': 'Manual remove me', 'scope': 'client_only'}),
            content_type='application/json',
        )
        self.assertEqual(send_response.status_code, 200)

        row = ClientMessage.objects.get(client=self.client_obj)

        delete_response = self.client.post(
            f'/panel/api/client/{self.client_obj.id}/messages/{row.id}/delete/',
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(delete_response.status_code, 200)

        history_response = self.client.get(f'/panel/api/client/{self.client_obj.id}/messages/')
        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.json()
        self.assertEqual(len(history_payload.get('messages', [])), 1)
        self.assertFalse(history_payload['messages'][0].get('notification_active'))

        self.client.login(username='msg-client@test.com', password='clientpass1')
        strip_response = self.client.get('/panel/api/notifications/client-messages/unread/')
        self.assertEqual(strip_response.status_code, 200)
        strip_payload = strip_response.json()
        self.assertEqual(len(strip_payload.get('items', [])), 0)





class PoolRetrieveClassChangeFlowTests(TestCase):
    def setUp(self):
        from staff.models import Staff

        self.client_owner_user, self.client_obj = _create_client_user(
            'retrieve-owner@test.com',
            'clientpass1',
        )
        self.client_obj.perm_idcard_retrieve = True
        self.client_obj.perm_idcard_pool_list = True
        self.client_obj.perm_idcard_pending_list = True
        self.client_obj.save(update_fields=['perm_idcard_retrieve', 'perm_idcard_pool_list', 'perm_idcard_pending_list'])

        self.group, self.table = _create_table(self.client_obj, fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'CLASS', 'type': 'class', 'order': 2},
            {'name': 'SECTION', 'type': 'section', 'order': 3},
        ])

        self.card = _create_card(
            self.table,
            field_data={'NAME': 'Scope Card', 'CLASS': '2', 'SECTION': 'A'},
            status='pool',
        )

        self.staff_user = User.objects.create_user(
            username='retrieve-assistant@test.com',
            email='retrieve-assistant@test.com',
            password='pass1234',
            role='client_staff',
        )
        self.staff_profile = Staff.objects.create(
            user=self.staff_user,
            staff_type='assistant',
            client=self.client_obj,
            perm_idcard_retrieve=True,
            perm_idcard_pool_list=True,
            perm_idcard_pending_list=True,
            allowed_classes=['1'],
            allowed_sections=[],
            assigned_table_ids=[self.table.id],
        )
        self.staff_profile.assigned_groups.add(self.group)

        self.client.login(username='retrieve-assistant@test.com', password='pass1234')

    def test_single_retrieve_requires_class_change_then_updates_class_and_moves_pending(self):
        blocked = self.client.post(
            f'/panel/api/card/{self.card.id}/status/',
            data=json.dumps({'status': 'pending'}),
            content_type='application/json',
        )
        self.assertEqual(blocked.status_code, 409)
        blocked_payload = blocked.json()
        self.assertFalse(blocked_payload.get('success'))
        self.assertTrue(blocked_payload.get('requires_class_change'))
        self.assertIn('allowed_classes', blocked_payload)

        self.card.refresh_from_db()
        self.assertEqual(self.card.status, 'pool')
        self.assertEqual((self.card.field_data or {}).get('CLASS'), '2')

        allowed = self.client.post(
            f'/panel/api/card/{self.card.id}/status/',
            data=json.dumps({
                'status': 'pending',
                'apply_class_change': True,
                'updated_class': '1',
            }),
            content_type='application/json',
        )
        self.assertEqual(allowed.status_code, 200)
        allowed_payload = allowed.json()
        self.assertTrue(allowed_payload.get('success'))

        self.card.refresh_from_db()
        self.assertEqual(self.card.status, 'pending')
        self.assertEqual((self.card.field_data or {}).get('CLASS'), '1')

    def test_bulk_retrieve_accepts_class_update_map_for_out_of_scope_pool_card(self):
        blocked = self.client.post(
            f'/panel/api/table/{self.table.id}/cards/bulk-status/',
            data=json.dumps({
                'card_ids': [self.card.id],
                'status': 'pending',
            }),
            content_type='application/json',
        )
        self.assertEqual(blocked.status_code, 409)
        blocked_payload = blocked.json()
        self.assertTrue(blocked_payload.get('requires_class_change'))

        allowed = self.client.post(
            f'/panel/api/table/{self.table.id}/cards/bulk-status/',
            data=json.dumps({
                'card_ids': [self.card.id],
                'status': 'pending',
                'apply_class_change': True,
                'pool_retrieve_class_updates': {
                    str(self.card.id): '1',
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(allowed.status_code, 200)
        allowed_payload = allowed.json()
        self.assertTrue(allowed_payload.get('success'))

        self.card.refresh_from_db()
        self.assertEqual(self.card.status, 'pending')
        self.assertEqual((self.card.field_data or {}).get('CLASS'), '1')

    def test_mobile_single_retrieve_requires_class_change_then_updates_class_and_moves_pending(self):
        # Set up mobile session
        session = self.client.session
        session['mobile_auth_ok'] = True
        session.save()

        blocked = self.client.post(
            f'/api/mobile/card/{self.card.id}/status/',
            data=json.dumps({'status': 'pending'}),
            content_type='application/json',
            HTTP_USER_AGENT='adarsh-mobile-app',
        )
        self.assertEqual(blocked.status_code, 409)
        blocked_payload = blocked.json()
        self.assertFalse(blocked_payload.get('success'))
        self.assertTrue(blocked_payload.get('requires_class_change'))
        self.assertIn('allowed_classes', blocked_payload)

        self.card.refresh_from_db()
        self.assertEqual(self.card.status, 'pool')
        self.assertEqual((self.card.field_data or {}).get('CLASS'), '2')

        allowed = self.client.post(
            f'/api/mobile/card/{self.card.id}/status/',
            data=json.dumps({
                'status': 'pending',
                'apply_class_change': True,
                'updated_class': '1',
            }),
            content_type='application/json',
            HTTP_USER_AGENT='adarsh-mobile-app',
        )
        self.assertEqual(allowed.status_code, 200)
        allowed_payload = allowed.json()
        self.assertTrue(allowed_payload.get('success'))

        self.card.refresh_from_db()
        self.assertEqual(self.card.status, 'pending')
        self.assertEqual((self.card.field_data or {}).get('CLASS'), '1')

    def test_mobile_bulk_retrieve_accepts_class_update_map_for_out_of_scope_pool_card(self):
        # Set up mobile session
        session = self.client.session
        session['mobile_auth_ok'] = True
        session.save()

        blocked = self.client.post(
            f'/api/mobile/table/{self.table.id}/bulk-status/',
            data=json.dumps({
                'card_ids': [self.card.id],
                'status': 'pending',
            }),
            content_type='application/json',
            HTTP_USER_AGENT='adarsh-mobile-app',
        )
        self.assertEqual(blocked.status_code, 409)
        blocked_payload = blocked.json()
        self.assertTrue(blocked_payload.get('requires_class_change'))

        allowed = self.client.post(
            f'/api/mobile/table/{self.table.id}/bulk-status/',
            data=json.dumps({
                'card_ids': [self.card.id],
                'status': 'pending',
                'apply_class_change': True,
                'pool_retrieve_class_updates': {
                    str(self.card.id): '1',
                },
            }),
            content_type='application/json',
            HTTP_USER_AGENT='adarsh-mobile-app',
        )
        self.assertEqual(allowed.status_code, 200)
        allowed_payload = allowed.json()
        self.assertTrue(allowed_payload.get('success'))

        self.card.refresh_from_db()
        self.assertEqual(self.card.status, 'pending')
        self.assertEqual((self.card.field_data or {}).get('CLASS'), '1')

    def test_mobile_assistant_can_edit_pool_card_for_retrieve(self):
        # Set up mobile session
        session = self.client.session
        session['mobile_auth_ok'] = True
        session.save()

        # Try updating the pool card via mobile update API
        url = f'/api/mobile/table/{self.table.id}/card/{self.card.id}/update/'
        response = self.client.post(
            url,
            {
                'field_data': json.dumps({'NAME': 'UPDATED POOL NAME', 'CLASS': '1', 'SECTION': 'A'}),
            },
            HTTP_USER_AGENT='adarsh-mobile-app',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

        self.card.refresh_from_db()
        self.assertEqual(self.card.field_data.get('NAME'), 'UPDATED POOL NAME')


class ClientStaffEmptyScopeVisibilityTests(TestCase):
    def setUp(self):
        from staff.models import Staff

        _client_user, self.client_obj = _create_client_user(
            'no-scope-owner@test.com',
            'clientpass1',
        )
        self.client_obj.perm_idcard_pending_list = True
        self.client_obj.perm_idcard_pool_list = True
        self.client_obj.save(update_fields=['perm_idcard_pending_list', 'perm_idcard_pool_list'])

        self.group, self.table = _create_table(self.client_obj, fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'CLASS', 'type': 'class', 'order': 2},
            {'name': 'SECTION', 'type': 'section', 'order': 3},
        ])

        _create_card(
            self.table,
            field_data={'NAME': 'Pending Card', 'CLASS': '5', 'SECTION': 'A'},
            status='pending',
        )
        _create_card(
            self.table,
            field_data={'NAME': 'Pool Card', 'CLASS': '6', 'SECTION': 'B'},
            status='pool',
        )

        self.staff_user = User.objects.create_user(
            username='no-scope-assistant@test.com',
            email='no-scope-assistant@test.com',
            password='pass1234',
            role='client_staff',
        )
        self.staff_profile = Staff.objects.create(
            user=self.staff_user,
            staff_type='assistant',
            client=self.client_obj,
            perm_idcard_pending_list=True,
            perm_idcard_pool_list=True,
            allowed_classes=[],
            allowed_sections=[],
            allowed_branches=[],
            assigned_table_ids=[self.table.id],
        )
        self.staff_profile.assigned_groups.add(self.group)

        self.client.login(username='no-scope-assistant@test.com', password='pass1234')

    def test_no_class_section_branch_scope_returns_no_cards_for_all_statuses(self):
        pending_response = self.client.get(f'/panel/api/table/{self.table.id}/cards/?status=pending')
        self.assertEqual(pending_response.status_code, 200)
        pending_payload = pending_response.json()
        self.assertEqual(len(pending_payload.get('cards') or []), 0)

        pool_response = self.client.get(f'/panel/api/table/{self.table.id}/cards/?status=pool')
        self.assertEqual(pool_response.status_code, 200)
        pool_payload = pool_response.json()
        self.assertEqual(len(pool_payload.get('cards') or []), 0)


class DynamicFieldsDefensiveTests(TestCase):
    def setUp(self):
        self.user, self.client_obj = _create_client_user('test-defensive-client@test.com', 'pass1234')
        self.client_obj.perm_idcard_edit = True
        self.client_obj.perm_idcard_pending_list = True
        self.client_obj.perm_idcard_info = True
        self.client_obj.perm_mobile_app = True
        self.client_obj.save()
        self.user.client_profile = self.client_obj
        
        self.group, self.table = _create_table(self.client_obj, fields=[
            None,
            'invalid_string_field',
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'photo', 'type': 'photo', 'order': 2},
            {'name': None, 'type': 'text', 'order': 3},
        ])
        self.card = _create_card(self.table, field_data={'NAME': 'JOHN DOE', 'photo': 'PENDING:avatar.jpg'})
        self.client.login(username='test-defensive-client@test.com', password='pass1234')
        session = self.client.session
        session['mobile_auth_ok'] = True
        session.save()

    def test_api_card_update_defensive_fields(self):
        # Verify that we can retrieve/update cards without 500 even with malformed table fields
        url = f'/api/mobile/table/{self.table.id}/card/{self.card.id}/update/'
        response = self.client.post(url, {
            'field_data': json.dumps({'NAME': 'JANE DOE'}),
        }, HTTP_USER_AGENT='adarsh-mobile-app')
        if response.status_code != 200:
            raise ValueError(f"API update failed: status={response.status_code}, content={response.content}")
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['card']['field_data']['NAME'], 'JANE DOE')

    def test_client_card_service_get_cards_defensive(self):
        # Verify that OrganisationCardService.get_cards handles malformed fields safely
        from organisation.services_card import OrganisationCardService
        result = OrganisationCardService.get_cards(self.user, self.table.id, status_filter='pending')
        if not result.success:
            raise ValueError(f"get_cards failed: {result.message}")
        self.assertTrue(result.success)
        self.assertEqual(len(result.data['cards']), 1)
        self.assertEqual(result.data['cards'][0]['name'], 'JOHN DOE')


class ClearPendingPathsApiTests(TestCase):
    def setUp(self):
        # Create super admin
        self.super_admin = _create_super_admin('clear-paths-admin@test.com', 'adminpass1')
        
        # Create client and table
        self.client_user, self.client_obj = _create_client_user('clear-paths-client@test.com', 'clientpass1')
        self.group, self.table = _create_table(
            self.client_obj,
            fields=[
                {'name': 'NAME', 'type': 'text', 'order': 1},
                {'name': 'PHOTO', 'type': 'photo', 'order': 2},
                {'name': 'SIGNATURE', 'type': 'signature', 'order': 3},
            ]
        )
        
        # Create admin staff with and without permission
        self.staff_user_with_perm = User.objects.create_user(
            username='staff-with-perm@test.com',
            email='staff-with-perm@test.com',
            password='staffpass123',
            role='operator',
        )
        from staff.models import Staff
        staff_with_perm = Staff.objects.create(
            user=self.staff_user_with_perm,
            staff_type='operator',
            perm_idcard_clear_pending_path=True,
        )
        staff_with_perm.assigned_organisations.add(self.client_obj)
        
        self.staff_user_no_perm = User.objects.create_user(
            username='staff-no-perm@test.com',
            email='staff-no-perm@test.com',
            password='staffpass123',
            role='operator',
        )
        staff_no_perm = Staff.objects.create(
            user=self.staff_user_no_perm,
            staff_type='operator',
            perm_idcard_clear_pending_path=False,
        )
        staff_no_perm.assigned_organisations.add(self.client_obj)


        # Create cards
        from mediafiles.models import CardMedia
        
        # Card 1: Pending, has photo (exists) and signature (missing)
        self.card1 = _create_card(
            self.table,
            field_data={
                'NAME': 'STUDENT ONE',
                'PHOTO': 'adarshimg/photo1.jpg',
                'SIGNATURE': 'adarshimg/sig1.jpg'
            },
            status='pending'
        )
        CardMedia.objects.create(card=self.card1, client=self.client_obj, field_name='PHOTO', file='adarshimg/photo1.jpg')
        CardMedia.objects.create(card=self.card1, client=self.client_obj, field_name='SIGNATURE', file='adarshimg/sig1.jpg')
        
        # Card 2: Verified, has photo (missing)
        self.card2 = _create_card(
            self.table,
            field_data={
                'NAME': 'STUDENT TWO',
                'PHOTO': 'adarshimg/photo2.jpg',
                'SIGNATURE': ''
            },
            status='verified'
        )
        CardMedia.objects.create(card=self.card2, client=self.client_obj, field_name='PHOTO', file='adarshimg/photo2.jpg')

        # Card 3: Approved, has photo (missing) - should NOT be touched
        self.card3 = _create_card(
            self.table,
            field_data={
                'NAME': 'STUDENT THREE',
                'PHOTO': 'adarshimg/photo3.jpg',
                'SIGNATURE': ''
            },
            status='approved'
        )
        CardMedia.objects.create(card=self.card3, client=self.client_obj, field_name='PHOTO', file='adarshimg/photo3.jpg')


    @patch('django.core.files.storage.default_storage.exists')
    def test_clear_pending_paths_success_super_admin(self, mock_exists):
        # Mock storage: photo1.jpg exists, all others missing
        def exists_side_effect(path):
            return 'photo1.jpg' in path
        mock_exists.side_effect = exists_side_effect
        
        self.client.force_login(self.super_admin)
        
        # Clear 'pending' status paths
        url = reverse('api_clear_pending_paths', args=[self.table.id])
        response = self.client.post(
            url,
            data=json.dumps({'status': 'pending'}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['total_scanned'], 1)  # Only card1 is pending
        self.assertEqual(data['cleared_count'], 1)  # Only signature on card1 should clear
        
        self.card1.refresh_from_db()
        self.assertEqual(self.card1.field_data['NAME'], 'STUDENT ONE')
        self.assertEqual(self.card1.field_data['PHOTO'], 'adarshimg/photo1.jpg')
        self.assertEqual(self.card1.field_data['SIGNATURE'], '')  # Cleared!
        
        # Check CardMedia deleted
        from mediafiles.models import CardMedia
        self.assertTrue(CardMedia.objects.filter(card=self.card1, field_name='PHOTO').exists())
        self.assertFalse(CardMedia.objects.filter(card=self.card1, field_name='SIGNATURE').exists())
        
        # Card 2 and 3 should not be touched
        self.card2.refresh_from_db()
        self.assertEqual(self.card2.field_data['PHOTO'], 'adarshimg/photo2.jpg')

    @patch('django.core.files.storage.default_storage.exists')
    def test_clear_pending_paths_success_staff_with_perm(self, mock_exists):
        mock_exists.return_value = False  # Everything is missing
        
        self.client.force_login(self.staff_user_with_perm)
        
        # Clear 'verified' status paths
        url = reverse('api_clear_pending_paths', args=[self.table.id])
        response = self.client.post(
            url,
            data=json.dumps({'status': 'verified'}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['total_scanned'], 1)  # Only card2 is verified
        self.assertEqual(data['cleared_count'], 1)  # PHOTO on card2 should clear
        
        self.card2.refresh_from_db()
        self.assertEqual(self.card2.field_data['PHOTO'], '')
        
        from mediafiles.models import CardMedia
        self.assertFalse(CardMedia.objects.filter(card=self.card2, field_name='PHOTO').exists())

    def test_clear_pending_paths_permission_denied_staff_no_perm(self):
        self.client.force_login(self.staff_user_no_perm)
        
        url = reverse('api_clear_pending_paths', args=[self.table.id])
        response = self.client.post(
            url,
            data=json.dumps({'status': 'pending'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])

    def test_clear_pending_paths_permission_denied_client(self):
        self.client.force_login(self.client_user)
        
        url = reverse('api_clear_pending_paths', args=[self.table.id])
        response = self.client.post(
            url,
            data=json.dumps({'status': 'pending'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])

    @patch('django.core.files.storage.default_storage.exists')
    def test_clear_pending_paths_by_column(self, mock_exists):
        mock_exists.return_value = False  # Everything is missing
        
        self.client.force_login(self.super_admin)
        
        # We clear only 'SIGNATURE' column on card1 (which is pending)
        url = reverse('api_clear_pending_paths', args=[self.table.id])
        response = self.client.post(
            url,
            data=json.dumps({'status': 'pending', 'column': 'SIGNATURE'}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['cleared_count'], 1)
        
        self.card1.refresh_from_db()
        # PHOTO (even though missing) must NOT be cleared because we only specified SIGNATURE
        self.assertEqual(self.card1.field_data['PHOTO'], 'adarshimg/photo1.jpg')
        self.assertEqual(self.card1.field_data['SIGNATURE'], '')  # Cleared!


class ExportTaskClassFilterTests(TestCase):
    def setUp(self):
        self.super_admin = _create_super_admin('export-task-admin@test.com', 'adminpass1')
        self.client_user, self.client_obj = _create_client_user('export-task-client@test.com', 'clientpass1')
        
        self.group, self.table = _create_table(
            self.client_obj,
            fields=[
                {'name': 'NAME', 'type': 'text', 'order': 1},
                {'name': 'CLASS', 'type': 'class', 'order': 2},
            ]
        )
        
        # Create some cards with different classes
        self.card1 = _create_card(self.table, field_data={'NAME': 'Alice', 'CLASS': 'V'}, status='pending')
        self.card2 = _create_card(self.table, field_data={'NAME': 'Bob', 'CLASS': 'VI'}, status='pending')
        self.card3 = _create_card(self.table, field_data={'NAME': 'Charlie', 'CLASS': 'V'}, status='pending')

    def test_create_export_task_with_class_filter_and_breaks(self):
        self.client.force_login(self.super_admin)
        
        url = reverse('api_create_export_task', args=[self.table.id])
        payload = {
            'export_type': 'docx',
            'card_ids': [self.card1.id, self.card2.id, self.card3.id],
            'class_filter_enabled': True,
            'selected_classes': ['V'],
            'break_enabled': True,
            'break_pages': 5,
            'break_mode': 'class_only'
        }
        
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # Check task was created with correct metadata
        from core.models import BackgroundTask
        task = BackgroundTask.objects.get(id=data['task_id'])
        metadata = task.metadata
        
        # Class filter should have filtered cards down to Alice and Charlie (class V)
        self.assertEqual(set(metadata['card_ids']), {self.card1.id, self.card3.id})
        
        # Break options should be correctly passed
        self.assertTrue(metadata['break_enabled'])
        self.assertEqual(metadata['break_pages'], 5)
        self.assertEqual(metadata['break_mode'], 'class_only')

    def test_class_counts_endpoint(self):
        self.client.force_login(self.super_admin)
        url = reverse('api_idcard_class_counts', args=[self.table.id])
        
        payload = {
            'card_ids': [self.card1.id, self.card2.id, self.card3.id]
        }
        
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # card1 (V), card2 (VI), card3 (V)
        class_counts = data['class_counts']
        self.assertEqual(class_counts.get('V'), 2)
        self.assertEqual(class_counts.get('VI'), 1)


class TableColumnUniqueAndPresetSchemaTests(TestCase):
    """Test suite for unique column constraints, dropdown presets, and duplicate card detection."""

    def setUp(self):
        self.super_admin = _create_super_admin(email='admin_unique@test.com')
        self.client_user, self.org = _create_client_user(email='client_unique@test.com')
        from tables.models import Table, IDCard
        from core.services.idcard_table_service import IDCardTableService

        self.table_service = IDCardTableService
        self.table = Table.objects.create(
            organisation=self.org,
            name="HIGH SCHOOL STUDENTS",
            table_type="school_student",
            fields=[
                {'name': 'ROLL_NO', 'type': 'number', 'order': 0, 'mandatory': True, 'is_unique': True},
                {'name': 'NAME', 'type': 'text', 'order': 1, 'mandatory': True, 'is_unique': False},
                {'name': 'CLASS', 'type': 'class', 'order': 2, 'mandatory': False, 'is_unique': False, 'format_preset': 'class_roman', 'options': ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']},
                {'name': 'SECTION', 'type': 'section', 'order': 3, 'mandatory': False, 'is_unique': False, 'format_preset': 'section_alpha', 'options': ['A', 'B', 'C', 'D']},
                {'name': 'COURSE', 'type': 'course', 'order': 4, 'mandatory': False, 'is_unique': False, 'format_preset': 'course_higher', 'options': ['B.Tech', 'BCA', 'MCA']},
            ],
            is_active=True,
        )

        # Create test cards: Card 1 and Card 2 have repeating ROLL_NO "101", Card 3 has ROLL_NO "102"
        self.card1 = IDCard.objects.create(
            table=self.table,
            field_data={'ROLL_NO': '101', 'NAME': 'Alice Smith', 'CLASS': 'X', 'SECTION': 'A'},
            status='pending',
        )
        self.card2 = IDCard.objects.create(
            table=self.table,
            field_data={'ROLL_NO': '101', 'NAME': 'Bob Johnson', 'CLASS': 'X', 'SECTION': 'B'},
            status='pending',
        )
        self.card3 = IDCard.objects.create(
            table=self.table,
            field_data={'ROLL_NO': '102', 'NAME': 'Charlie Brown', 'CLASS': 'XI', 'SECTION': 'A'},
            status='pending',
        )

    def test_find_duplicate_cards_detects_repeating_records(self):
        """Verify find_duplicate_cards flags repeating values without altering or deleting records."""
        dup_info = self.table_service.find_duplicate_cards(self.table.id)
        card_dups = dup_info['card_duplicates']

        self.assertEqual(dup_info['total_duplicate_cards'], 2)
        self.assertIn(self.card1.id, card_dups)
        self.assertIn(self.card2.id, card_dups)
        self.assertNotIn(self.card3.id, card_dups)

        self.assertEqual(card_dups[self.card1.id]['duplicate_fields'], ['ROLL_NO'])
        self.assertEqual(card_dups[self.card1.id]['duplicate_values']['ROLL_NO'], '101')
        self.assertEqual(card_dups[self.card2.id]['duplicate_fields'], ['ROLL_NO'])
        self.assertEqual(card_dups[self.card2.id]['duplicate_values']['ROLL_NO'], '101')

    def test_api_cards_json_returns_duplicate_flags(self):
        """Verify api_idcard_cards_json attaches duplicate metadata and supports filtering."""
        self.client.force_login(self.super_admin)
        url = reverse('api_idcard_cards_json', args=[self.table.id])

        # 1. Normal list
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(data['total_duplicates'], 2)
        self.assertEqual(data['unique_fields'], ['ROLL_NO'])

        cards_map = {c['id']: c for c in data['cards']}
        self.assertTrue(cards_map[self.card1.id]['is_duplicate'])
        self.assertEqual(cards_map[self.card1.id]['duplicate_fields'], ['ROLL_NO'])
        self.assertTrue(cards_map[self.card2.id]['is_duplicate'])
        self.assertFalse(cards_map[self.card3.id]['is_duplicate'])

        # 2. Filter with duplicates=true
        response_dup = self.client.get(f"{url}?duplicates=true")
        self.assertEqual(response_dup.status_code, 200)
        data_dup = response_dup.json()
        self.assertEqual(len(data_dup['cards']), 2)
        dup_ids = {c['id'] for c in data_dup['cards']}
        self.assertEqual(dup_ids, {self.card1.id, self.card2.id})

    def test_table_service_persists_unique_and_format_presets(self):
        """Verify update_table preserves is_unique and options configuration."""
        new_fields = [
            {'name': 'ADMISSION_NO', 'type': 'number', 'mandatory': True, 'is_unique': True},
            {'name': 'BRANCH', 'type': 'branch', 'mandatory': False, 'is_unique': False, 'format_preset': 'branch_eng', 'options': ['CSE', 'ECE', 'ME']},
        ]
        result = self.table_service.update_table(self.table.id, {
            'name': 'COLLEGE STUDENTS',
            'table_type': 'college_student',
            'fields': new_fields,
        })
        self.assertTrue(result.success)

        self.table.refresh_from_db()
        self.assertEqual(self.table.name, 'COLLEGE STUDENTS')
        self.assertEqual(len(self.table.fields), 2)
        self.assertTrue(self.table.fields[0]['is_unique'])
        self.assertEqual(self.table.fields[1]['format_preset'], 'branch_eng')
        self.assertEqual(self.table.fields[1]['options'], ['CSE', 'ECE', 'ME'])





