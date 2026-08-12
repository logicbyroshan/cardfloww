from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from organisation.models import Organisation
from tables.models import Table, IDCard

User = get_user_model()

class WebAppApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create users & client profiles
        cls.user1 = User.objects.create_user(username='client1', email='c1@test.com', password='pass')
        cls.client1 = Organisation.objects.create(user=cls.user1, name='Alpha Client')

        cls.user2 = User.objects.create_user(username='client2', email='c2@test.com', password='pass')
        cls.client2 = Organisation.objects.create(user=cls.user2, name='Beta Client')

        # Create cards for Client 1
        cls.group1 = Table.objects.create(client=cls.client1, name='Group 1')
        cls.table1 = Table.objects.create(group=cls.group1, name='Table 1')
        cls.card1 = IDCard.objects.create(table=cls.table1, field_data={})
        cls.card2 = IDCard.objects.create(table=cls.table1, field_data={})

        # Create cards for Client 2
        cls.group2 = Table.objects.create(client=cls.client2, name='Group 2')
        cls.table2 = Table.objects.create(group=cls.group2, name='Table 2')
        cls.card3 = IDCard.objects.create(table=cls.table2, field_data={})

    @override_settings(WEB_APP_API_KEY='secure_test_token')
    def test_unauthorized_access(self):
        url = reverse('web_app:api_public_clients_list')
        
        # No key
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['success'])

        # Bad key in header
        response = self.client.get(url, HTTP_X_API_KEY='invalid')
        self.assertEqual(response.status_code, 401)

        # Bad key in query params
        response = self.client.get(f"{url}?api_key=invalid")
        self.assertEqual(response.status_code, 401)

    @override_settings(WEB_APP_API_KEY='secure_test_token')
    def test_authorized_access_header(self):
        url = reverse('web_app:api_public_clients_list')
        response = self.client.get(url, HTTP_X_API_KEY='secure_test_token')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        print("DEBUG CLIENTS:", data['clients'])
        self.assertGreaterEqual(len(data['clients']), 2)

        # Check clients details
        client_alpha = next(c for c in data['clients'] if c['name'] == 'Alpha Client')
        self.assertEqual(client_alpha['email'], 'c1@test.com')
        self.assertEqual(client_alpha['total_records'], 2)

        client_beta = next(c for c in data['clients'] if c['name'] == 'Beta Client')
        self.assertEqual(client_beta['email'], 'c2@test.com')
        self.assertEqual(client_beta['total_records'], 1)

    @override_settings(WEB_APP_API_KEY='secure_test_token')
    def test_authorized_access_query_param(self):
        url = reverse('web_app:api_public_clients_list')
        response = self.client.get(f"{url}?api_key=secure_test_token")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
