import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from organisation.models import Organisation, OrganisationManager
from tables.models import Table, TableAccess
from assistants.models import Assistant
from core.services.permission_service import PermissionService

User = get_user_model()

class HierarchyAndAccessControlTests(TestCase):
    def setUp(self):
        # 1. Create Platform Admin (Prime Admin)
        self.prime_admin = User.objects.create_superuser(
            username='admin_prime',
            email='prime_admin@cardflow.io',
            password='Password123!',
            role='prime_admin'
        )

        # 2. Create Organisation & Prime Manager (Owner)
        self.prime_mgr_user = User.objects.create_user(
            username='org_owner',
            email='owner@school.edu',
            password='Password123!',
            role='prime_manager',
            first_name='Principal',
            last_name='Sharma'
        )
        self.org = Organisation.objects.create(
            user=self.prime_mgr_user,
            name='Delhi Public School',
            max_super_managers=2,  # Configured limit = 2 for testing
            status='active'
        )
        self.prime_org_manager = OrganisationManager.objects.create(
            user=self.prime_mgr_user,
            organisation=self.org,
            manager_type='prime_manager',
            is_active=True
        )

        # 3. Create 2 Tables under the Organisation
        self.table_a = Table.objects.create(
            organisation=self.org,
            name='CLASS_X_STUDENTS',
            fields=[{'name': 'NAME', 'type': 'text'}, {'name': 'ROLL_NO', 'type': 'text'}]
        )
        self.table_b = Table.objects.create(
            organisation=self.org,
            name='CLASS_XII_STUDENTS',
            fields=[{'name': 'NAME', 'type': 'text'}, {'name': 'ROLL_NO', 'type': 'text'}]
        )

        # 4. Create Super Manager 1
        self.sm1_user = User.objects.create_user(
            username='super_mgr_1',
            email='sm1@school.edu',
            password='Password123!',
            role='super_manager',
            first_name='Super',
            last_name='One'
        )
        self.sm1_org_mgr = OrganisationManager.objects.create(
            user=self.sm1_user,
            organisation=self.org,
            manager_type='super_manager',
            is_active=True
        )

    def test_prime_manager_can_create_table(self):
        """Prime Manager is allowed to create tables."""
        client = Client()
        client.force_login(self.prime_mgr_user)
        resp = client.post(
            '/api/schemas/create/',
            data=json.dumps({
                'table_name': 'CLASS_IX_STUDENTS',
                'client_id': self.org.id,
                'fields': [{'name': 'NAME', 'type': 'text'}]
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))

    def test_super_manager_cannot_create_table(self):
        """Super Manager is strictly forbidden from creating tables."""
        client = Client()
        client.force_login(self.sm1_user)
        resp = client.post(
            '/api/schemas/create/',
            data=json.dumps({
                'table_name': 'ILLEGAL_TABLE_BY_SM',
                'client_id': self.org.id,
                'fields': [{'name': 'NAME', 'type': 'text'}]
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertFalse(data.get('success'))
        self.assertIn('Permission denied', data.get('message', ''))

    def test_super_manager_table_scoping(self):
        """Super Manager only sees tables explicitly delegated via TableAccess."""
        # Before delegation: SM1 sees 0 tables
        client = Client()
        client.force_login(self.sm1_user)
        resp = client.get('/api/schemas/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data.get('tables', [])), 0)

        # Delegate Table A to SM1
        TableAccess.objects.create(
            table=self.table_a,
            manager=self.sm1_user,
            can_view=True,
            can_edit_cards=True
        )

        # After delegation: SM1 sees Table A only
        resp2 = client.get('/api/schemas/')
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        tables_seen = data2.get('tables', [])
        self.assertEqual(len(tables_seen), 1)
        self.assertEqual(tables_seen[0]['id'], self.table_a.id)

    def test_max_super_managers_limit_enforced(self):
        """Creating more Super Managers than max_super_managers is rejected."""
        client = Client()
        client.force_login(self.prime_mgr_user)

        # Create SM2 (limit is 2, currently 1 active)
        resp_sm2 = client.post(
            '/api/organisation-managers/',
            data=json.dumps({
                'organisation_id': self.org.id,
                'name': 'Super Manager Two',
                'email': 'sm2@school.edu',
                'manager_type': 'super_manager',
            }),
            content_type='application/json'
        )
        self.assertEqual(resp_sm2.status_code, 200)
        self.assertTrue(resp_sm2.json().get('success'))

        # Try to create SM3 (exceeds limit 2)
        resp_sm3 = client.post(
            '/api/organisation-managers/',
            data=json.dumps({
                'organisation_id': self.org.id,
                'name': 'Super Manager Three',
                'email': 'sm3@school.edu',
                'manager_type': 'super_manager',
            }),
            content_type='application/json'
        )
        self.assertEqual(resp_sm3.status_code, 400)
        data_sm3 = resp_sm3.json()
        self.assertFalse(data_sm3.get('success'))
        self.assertIn('limit', data_sm3.get('message', '').lower())

    def test_table_delegation_api(self):
        """Prime Manager can fetch and update Super Manager table delegation via API."""
        client = Client()
        client.force_login(self.prime_mgr_user)

        # Fetch shared managers for Table B
        resp_get = client.get(f'/api/table/{self.table_b.id}/shared-managers/')
        self.assertEqual(resp_get.status_code, 200)
        data_get = resp_get.json()
        self.assertTrue(data_get.get('success'))
        self.assertEqual(len(data_get.get('super_managers', [])), 1)

        # Delegate Table B to SM1
        resp_share = client.post(
            f'/api/table/{self.table_b.id}/share-managers/',
            data=json.dumps({
                'manager_ids': [self.sm1_user.id],
                'can_edit_cards': True,
                'can_approve_print': False,
            }),
            content_type='application/json'
        )
        self.assertEqual(resp_share.status_code, 200)
        self.assertTrue(resp_share.json().get('success'))

        # Verify TableAccess record in DB
        self.assertTrue(
            TableAccess.objects.filter(table=self.table_b, manager=self.sm1_user, can_view=True).exists()
        )
