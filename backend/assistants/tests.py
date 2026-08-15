import io
import pandas as pd
from django.test import TestCase
from core.models import User
from organisation.models import Organisation
from assistants.models import Assistant
from assistants.services import AssistantService
from tables.models import Table, IDCard

class AutoCreateAssistantsTests(TestCase):
    def setUp(self):
        # Create a dummy client with permissions set
        self.user = User.objects.create(username='test_admin', email='test@test.com')
        self.client_obj = Organisation.objects.create(
            name='Test Client Auto Create',
            user=self.user,
            perm_idcard_pending_list=True,
            perm_idcard_verified_list=True,
            perm_mobile_app=True
        )

        # Create dummy Table, IDCard
        self.table = Table.objects.create(
            organisation=self.client_obj, 
            name='Test Table',
            fields=[{'name': 'Class', 'type': 'text'}, {'name': 'Section', 'type': 'text'}]
        )

        IDCard.objects.create(table=self.table, field_data={'Class': 'V', 'Section': 'A'})
        IDCard.objects.create(table=self.table, field_data={'Class': 'V', 'Section': 'B'})
        IDCard.objects.create(table=self.table, field_data={'Class': 'VI', 'Section': ''})

    def test_auto_create_class_mode(self):
        result = AssistantService.auto_create_assistants(self.user, self.client_obj, 'STGS', 'class', True)
        self.assertTrue(result.success)
        self.assertEqual(result.data['count'], 2) # Should create for Class V and VI
        
        # Verify Excel buffer is valid
        buffer = result.data['buffer']
        df = pd.read_excel(buffer, engine='openpyxl')
        self.assertEqual(len(df), 2)
        
        # Verify assistants were created
        self.assertEqual(Assistant.objects.filter(organisation=self.client_obj).count(), 2)
        
        # Verify permissions were auto-assigned matching client permissions
        for assistant in Assistant.objects.filter(organisation=self.client_obj):
            self.assertTrue(assistant.perm_idcard_pending_list)
            self.assertTrue(assistant.perm_idcard_verified_list)
            self.assertTrue(assistant.perm_mobile_app)
            self.assertFalse(assistant.perm_idcard_pool_list)

    def test_auto_create_section_mode(self):
        result = AssistantService.auto_create_assistants(self.user, self.client_obj, 'STGS', 'section', True)
        self.assertTrue(result.success)
        self.assertEqual(result.data['count'], 3) # V-A, V-B, and VI
        
        buffer = result.data['buffer']
        df = pd.read_excel(buffer, engine='openpyxl')
        self.assertEqual(len(df), 3)

        self.assertEqual(Assistant.objects.filter(organisation=self.client_obj).count(), 3)

    def test_auto_create_fallback_mode_when_no_columns(self):
        # Create a new table with NO Class or Section fields
        simple_table = Table.objects.create(
            organisation=self.client_obj,
            name='Simple Staff Table',
            fields=[{'name': 'Full Name', 'type': 'text'}, {'name': 'Phone', 'type': 'text'}]
        )
        IDCard.objects.create(table=simple_table, field_data={'Full Name': 'John Doe', 'Phone': '12345'})

        # Run auto create for this specific table (single list)
        result = AssistantService.auto_create_assistants(
            self.user, self.client_obj, 'STGS', 'class', auto_assign=True,
            table=simple_table
        )
        self.assertTrue(result.success)
        # Should create exactly 1 assistant for the entire table
        self.assertEqual(result.data['count'], 1)

        # Retrieve the assistant and verify properties
        assistant = Assistant.objects.filter(organisation=self.client_obj, user__email__icontains='simplestafftable').first()
        self.assertIsNotNone(assistant)
        # Should be assigned to the table with full access (empty allowed_classes)
        self.assertEqual(assistant.allowed_classes, [])
        self.assertEqual(assistant.allowed_sections, [])
        self.assertEqual(len(assistant.assignment_scopes), 1)
        self.assertEqual(assistant.assignment_scopes[0]['scope_type'], 'table')
        self.assertEqual(assistant.assignment_scopes[0]['table_id'], simple_table.id)
        self.assertEqual(assistant.assignment_scopes[0]['classes'], [])
        self.assertEqual(assistant.assignment_scopes[0]['sections'], [])


from django.urls import reverse

class AssistantAPIViewPermissionTests(TestCase):
    def setUp(self):
        # Create users
        self.super_admin = User.objects.create_user(
            username='super_admin@test.com', email='super_admin@test.com', password='adminpass1', role='super_admin'
        )
        self.client_user = User.objects.create_user(
            username='client_user@test.com', email='client_user@test.com', password='clientpass1', role='client'
        )
        self.client_obj = Organisation.objects.create(name='Test Client Permissions', user=self.client_user)

        self.table = Table.objects.create(
            organisation=self.client_obj, 
            name='Test Table',
            fields=[{'name': 'Class', 'type': 'text'}, {'name': 'Section', 'type': 'text'}]
        )
        # Create at least one IDCard so auto-create has data to work with
        IDCard.objects.create(table=self.table, field_data={'Class': 'V', 'Section': 'A'})

    def test_auto_create_endpoint_allows_super_admin(self):
        self.client.force_login(self.super_admin)
        response = self.client.post(reverse('assistants:api_staff_auto_create'), {
            'client_id': self.client_obj.id,
            'acronym': 'TST',
            'mode': 'class',
            'assign': 'true',
            'id_source': 'table',
            'table_id': self.table.id
        })
        # Should succeed and return the Excel spreadsheet
        self.assertEqual(response.status_code, 200)

    def test_auto_create_endpoint_denies_client_admin(self):
        self.client.force_login(self.client_user)
        response = self.client.post(reverse('assistants:api_staff_auto_create'), {
            'client_id': self.client_obj.id,
            'acronym': 'TST',
            'mode': 'class',
            'assign': 'true',
            'id_source': 'table',
            'table_id': self.table.id
        })
        self.assertEqual(response.status_code, 403)

    def test_bulk_upload_endpoint_allows_super_admin_pass_gate(self):
        self.client.force_login(self.super_admin)
        response = self.client.post(reverse('assistants:api_staff_bulk_upload_xlsx'), {
            'client_id': self.client_obj.id,
        })
        # If it passed the decorator gate, it will fail on file validation (400) rather than permission (403)
        self.assertEqual(response.status_code, 400)

    def test_bulk_upload_endpoint_denies_client_admin(self):
        self.client.force_login(self.client_user)
        response = self.client.post(reverse('assistants:api_staff_bulk_upload_xlsx'), {
            'client_id': self.client_obj.id,
        })
        self.assertEqual(response.status_code, 403)

