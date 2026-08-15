import io
from django.test import TestCase, Client
from django.urls import reverse
from PIL import Image

class PhotoValidationApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('mobile_api:api_validate_photo')

    def test_get_method_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_post_no_photo(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {'success': False, 'message': 'No photo uploaded'})

    def test_post_invalid_image_file(self):
        bad_file = io.BytesIO(b'this is not an image file')
        bad_file.name = 'test.jpg'
        response = self.client.post(self.url, {'photo': bad_file})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid image', response.json().get('message', ''))

    def test_post_valid_image_no_face(self):
        # Create a small 100x100 solid black square image (no face inside)
        img = Image.new('RGB', (100, 100), color='black')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        img_bytes.name = 'noface.jpg'
        
        response = self.client.post(self.url, {'photo': img_bytes})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertFalse(data['face_detected'])
        self.assertEqual(data['message'], 'No Person Detected')


class MobileStaffAssignmentTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from organisation.models import Organisation
        from assistants.models import Assistant
        from tables.models import Table

        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='super@test.com', email='super@test.com', password='superpass1', role='super_admin'
        )
        self.client_user = User.objects.create_user(
            username='client@test.com', email='client@test.com', password='clientpass1', role='client'
        )
        self.client_obj = Organisation.objects.create(user=self.client_user, name='Test Client')
        
        self.assistant_user = User.objects.create_user(
            username='assistant@test.com', email='assistant@test.com', password='assistantpass1', role='client_staff'
        )
        self.assistant = Assistant.objects.create(
            user=self.assistant_user, client=self.client_obj
        )
        
        self.table = Table.objects.create(organisation=self.client_obj, name='Test Table')
        
    def test_mobile_staff_assignment_endpoint(self):
        # Set session flag
        session = self.client.session
        session['mobile_auth_ok'] = True
        session.save()

        self.client.force_login(self.superuser)
        url = reverse('mobile_api:api_mobile_staff_assignment', args=[self.assistant.id])
        
        response = self.client.get(
            url,
            HTTP_USER_AGENT='Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # Verify assignment_id_source and id_source are both present in returned data
        payload = data['data']
        self.assertIn('assignment_id_source', payload)
        self.assertIn('id_source', payload)
        self.assertEqual(payload['assignment_id_source'], payload['id_source'])

    def test_mobile_staff_assignment_update_endpoint(self):
        import json
        # Set session flag
        session = self.client.session
        session['mobile_auth_ok'] = True
        session.save()

        self.client.force_login(self.superuser)
        url = reverse('mobile_api:api_mobile_staff_assignment_update', args=[self.assistant.id])
        
        # Test updating with assignment_id_source = 'table'
        payload = {
            'group_ids': [],
            'table_ids': [self.table.id],
            'client_ids': [],
            'assignment_scopes': [],
            'assignment_id_source': 'table'
        }
        
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_USER_AGENT='Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # Reload and verify assignment_id_source on load
        load_url = reverse('mobile_api:api_mobile_staff_assignment', args=[self.assistant.id])
        load_response = self.client.get(
            load_url,
            HTTP_USER_AGENT='Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1'
        )
        load_data = load_response.json()
        self.assertEqual(load_data['data']['assignment_id_source'], 'table')


class MobilePermissionAndEditLockTests(TestCase):
    def setUp(self):
        import json
        from django.contrib.auth import get_user_model
        from organisation.models import Organisation
        from assistants.models import Assistant
        from tables.models import Table, IDCard

        User = get_user_model()
        self.client_user = User.objects.create_user(
            username='perm_client@test.com', email='perm_client@test.com', password='clientpass1', role='prime_manager'
        )
        self.client_obj = Organisation.objects.create(
            user=self.client_user, name='Perm Client', perm_mobile_app=False, perm_idcard_edit=True, perm_idcard_delete=True
        )

        self.assistant_user = User.objects.create_user(
            username='perm_assistant@test.com', email='perm_assistant@test.com', password='assistantpass1', role='assistant'
        )
        self.assistant = Assistant.objects.create(
            user=self.assistant_user,
            client=self.client_obj,
            perm_mobile_app=False,
            perm_idcard_edit=True,
            perm_idcard_delete=True,
            perm_idcard_pending_list=True,
            perm_idcard_approved_list=True,
            perm_idcard_download_list=True,
        )

        self.table = Table.objects.create(
            organisation=self.client_obj,
            name='Perm Table',
            fields=[{'name': 'NAME', 'type': 'text', 'order': 1}],
        )

        self.pending_card = IDCard.objects.create(
            table=self.table, field_data={'NAME': 'Pending Student'}, status='pending'
        )
        self.approved_card = IDCard.objects.create(
            table=self.table, field_data={'NAME': 'Approved Student'}, status='approved'
        )
        self.download_card = IDCard.objects.create(
            table=self.table, field_data={'NAME': 'Download Student'}, status='download'
        )

    def test_mobile_login_blocked_when_perm_mobile_app_is_false(self):
        import json
        # Client user login
        response = self.client.post(
            reverse('mobile_api:api_mobile_login'),
            data=json.dumps({'email': 'perm_client@test.com', 'password': 'clientpass1'}),
            content_type='application/json',
            HTTP_USER_AGENT='Mobile Safari'
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn('disabled for your account', response.json().get('message', ''))

        # Assistant user login
        response = self.client.post(
            reverse('mobile_api:api_mobile_login'),
            data=json.dumps({'email': 'perm_assistant@test.com', 'password': 'assistantpass1'}),
            content_type='application/json',
            HTTP_USER_AGENT='Mobile Safari'
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn('disabled for your account', response.json().get('message', ''))

    def test_mobile_login_allowed_when_perm_mobile_app_is_true(self):
        import json
        self.client_obj.perm_mobile_app = True
        self.client_obj.save(update_fields=['perm_mobile_app'])

        response = self.client.post(
            reverse('mobile_api:api_mobile_login'),
            data=json.dumps({'email': 'perm_client@test.com', 'password': 'clientpass1'}),
            content_type='application/json',
            HTTP_USER_AGENT='Mobile Safari'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

        self.assistant.perm_mobile_app = True
        self.assistant.save(update_fields=['perm_mobile_app'])

        response = self.client.post(
            reverse('mobile_api:api_mobile_login'),
            data=json.dumps({'email': 'perm_assistant@test.com', 'password': 'assistantpass1'}),
            content_type='application/json',
            HTTP_USER_AGENT='Mobile Safari'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

    def test_client_and_assistant_cannot_edit_approved_or_download_cards(self):
        import json
        self.client.login(username='perm_client@test.com', password='clientpass1')

        # Try editing approved card field
        response = self.client.post(
            f'/api/card/{self.approved_card.id}/update-field/',
            data=json.dumps({'field': 'NAME', 'value': 'Hacked Name'}),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [403, 400])

        # Try editing download card field
        response = self.client.post(
            f'/api/card/{self.download_card.id}/update-field/',
            data=json.dumps({'field': 'NAME', 'value': 'Hacked Name'}),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [403, 400])

        # Editing pending card succeeds
        response = self.client.post(
            f'/api/card/{self.pending_card.id}/update-field/',
            data=json.dumps({'field': 'NAME', 'value': 'Valid Name'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

    def test_client_and_assistant_cannot_delete_approved_or_download_cards(self):
        self.client.login(username='perm_client@test.com', password='clientpass1')

        # Try deleting approved card
        response = self.client.post(f'/api/card/{self.approved_card.id}/delete/')
        self.assertIn(response.status_code, [403, 400])

        # Try deleting download card
        response = self.client.post(f'/api/card/{self.download_card.id}/delete/')
        self.assertIn(response.status_code, [403, 400])

        # Deleting pending card succeeds
        response = self.client.post(f'/api/card/{self.pending_card.id}/delete/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))


