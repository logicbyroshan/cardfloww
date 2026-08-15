import json
import os
import tempfile
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from organisation.models import Organisation
from staff.models import Staff
from core.models import ActivityLog, BackgroundTask, BackupTask, EmailLog, Notification, NotificationRead
from core.services.notification_service import NotificationService
from tables.models import IDCard, Table


User = get_user_model()


class PanelBaseTestCase(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_user(
            username='panel-super@test.com',
            email='panel-super@test.com',
            password='pass1234',
            role='super_admin',
        )
        self.client_user = User.objects.create_user(
            username='panel-client@test.com',
            email='panel-client@test.com',
            password='pass1234',
            role='client',
        )
        self.admin_staff_user = User.objects.create_user(
            username='panel-admin-staff@test.com',
            email='panel-admin-staff@test.com',
            password='pass1234',
            role='operator',
        )
        self.client_profile = Organisation.objects.create(
            user=self.client_user,
            name='Panel Client',
            status='active',
        )
        self.admin_staff_profile = Staff.objects.create(
            user=self.admin_staff_user,
            staff_type='operator',
        )
        cache.clear()

    def tearDown(self):
        cache.clear()


class PanelAccessTests(PanelBaseTestCase):
    def test_manage_panel_denies_client_role(self):
        self.client.login(username='panel-client@test.com', password='pass1234')
        response = self.client.get('/panel/manage-panel/')
        self.assertIn(response.status_code, [302, 403])

    def test_manage_panel_admin_staff_without_new_permissions_is_denied(self):
        self.client.login(username='panel-admin-staff@test.com', password='pass1234')
        response = self.client.get('/panel/manage-panel/')
        self.assertIn(response.status_code, [302, 403])

    def test_manage_panel_admin_staff_with_backup_permission_can_access(self):
        self.admin_staff_profile.perm_manage_panel_backup = True
        self.admin_staff_profile.save(update_fields=['perm_manage_panel_backup'])

        self.client.login(username='panel-admin-staff@test.com', password='pass1234')
        response = self.client.get('/panel/manage-panel/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Backups')

    def test_manage_panel_admin_staff_with_email_permission_can_access(self):
        self.admin_staff_profile.perm_manage_panel_email = True
        self.admin_staff_profile.save(update_fields=['perm_manage_panel_email'])

        self.client.login(username='panel-admin-staff@test.com', password='pass1234')
        response = self.client.get('/panel/manage-panel/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Email Management')

    def test_manage_panel_admin_staff_with_backup_permission_hides_super_admin_tabs(self):
        self.admin_staff_profile.perm_manage_panel_backup = True
        self.admin_staff_profile.save(update_fields=['perm_manage_panel_backup'])

        self.client.login(username='panel-admin-staff@test.com', password='pass1234')
        response = self.client.get('/panel/manage-panel/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-tab="backups"')
        self.assertNotContains(response, 'data-tab="notifications"')
        self.assertNotContains(response, 'data-tab="download-templates"')

    def test_manage_panel_admin_staff_with_email_permission_hides_super_admin_tabs(self):
        self.admin_staff_profile.perm_manage_panel_email = True
        self.admin_staff_profile.save(update_fields=['perm_manage_panel_email'])

        self.client.login(username='panel-admin-staff@test.com', password='pass1234')
        response = self.client.get('/panel/manage-panel/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-tab="email-logs"')
        self.assertNotContains(response, 'data-tab="notifications"')
        self.assertNotContains(response, 'data-tab="download-templates"')

    def test_manage_panel_super_admin_can_access(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.get('/panel/manage-panel/')
        self.assertEqual(response.status_code, 200)


class PanelNotificationApiTests(PanelBaseTestCase):
    def setUp(self):
        super().setUp()
        self.notif_all = Notification.objects.create(
            title='All users',
            message='Visible to everyone',
            target='all',
            created_by=self.super_admin,
        )
        self.notif_client = Notification.objects.create(
            title='Client only',
            message='Visible to client role',
            target='client',
            created_by=self.super_admin,
        )
        self.notif_selected = Notification.objects.create(
            title='Selected user',
            message='Visible to one user',
            target='selected',
            created_by=self.super_admin,
        )
        self.notif_selected.target_users.add(self.client_user)
        self.notif_expired = Notification.objects.create(
            title='Expired notice',
            message='Should stay in history only',
            target='selected',
            created_by=self.super_admin,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.notif_expired.target_users.add(self.client_user)

    def test_user_notifications_list_returns_visible_entries(self):
        self.client.login(username='panel-client@test.com', password='pass1234')
        response = self.client.get('/panel/api/notifications/list/?limit=10&offset=0')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload['success'])
        returned_ids = {item['id'] for item in payload['notifications']}
        self.assertIn(self.notif_all.id, returned_ids)
        self.assertIn(self.notif_client.id, returned_ids)
        self.assertIn(self.notif_selected.id, returned_ids)

    def test_user_notifications_list_hides_expired_by_default(self):
        self.client.login(username='panel-client@test.com', password='pass1234')

        response = self.client.get('/panel/api/notifications/list/?limit=20&offset=0')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        returned_ids = {item['id'] for item in payload['notifications']}
        self.assertNotIn(self.notif_expired.id, returned_ids)

    def test_user_notifications_history_includes_expired_when_requested(self):
        self.client.login(username='panel-client@test.com', password='pass1234')

        response = self.client.get('/panel/api/notifications/list/?limit=20&offset=0&include_expired=true')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        returned_ids = {item['id'] for item in payload['notifications']}
        self.assertIn(self.notif_expired.id, returned_ids)

    def test_user_notifications_hide_items_older_than_24h(self):
        old_notification = Notification.objects.create(
            title='Too old',
            message='Should never appear to users',
            target='all',
            created_by=self.super_admin,
            expires_at=timezone.now() + timedelta(days=7),
        )
        Notification.objects.filter(id=old_notification.id).update(
            created_at=timezone.now() - timedelta(hours=25)
        )

        self.client.login(username='panel-client@test.com', password='pass1234')
        response = self.client.get('/panel/api/notifications/list/?limit=20&offset=0&include_expired=true')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        returned_ids = {item['id'] for item in payload['notifications']}
        self.assertNotIn(old_notification.id, returned_ids)

    def test_mark_read_updates_unread_count(self):
        self.client.login(username='panel-client@test.com', password='pass1234')

        before = self.client.get('/panel/api/notifications/unread-count/').json()
        self.assertTrue(before['unread_count'] >= 1)

        response = self.client.post(f'/panel/api/notifications/{self.notif_all.id}/read/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(NotificationRead.objects.filter(user=self.client_user, notification=self.notif_all).exists())

        after = self.client.get('/panel/api/notifications/unread-count/').json()
        self.assertLess(after['unread_count'], before['unread_count'])

    def test_admin_create_and_delete_notification(self):
        self.client.login(username='panel-super@test.com', password='pass1234')

        create_response = self.client.post(
            '/panel/api/notifications/admin/create/',
            data=json.dumps({
                'title': 'Panel create',
                'message': 'Created from API',
                'priority': 'high',
                'category': 'announcement',
                'target': 'selected',
                'target_user_ids': [self.client_user.id],
                'send_email': False,
            }),
            content_type='application/json',
        )
        self.assertEqual(create_response.status_code, 200)
        created_id = create_response.json()['notification']['id']

        notif = Notification.objects.get(id=created_id)
        self.assertEqual(notif.target, 'selected')
        self.assertTrue(notif.target_users.filter(id=self.client_user.id).exists())

        delete_response = self.client.delete(f'/panel/api/notifications/admin/{created_id}/delete/')
        self.assertEqual(delete_response.status_code, 200)
        notif.refresh_from_db()
        self.assertFalse(notif.is_active)

    def test_admin_create_rejects_empty_title(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.post(
            '/panel/api/notifications/admin/create/',
            data=json.dumps({'title': '', 'message': 'x'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])


class PanelNotificationEmailTemplateTests(PanelBaseTestCase):
    @mock.patch('core.utils.threaded_email.send_html_email_async')
    @mock.patch('django.conf.settings.EMAIL_HOST_USER', 'smtp-user')
    @mock.patch('django.conf.settings.DEFAULT_FROM_EMAIL', 'Adarsh Admin <noreply@test.com>')
    def test_send_email_alerts_uses_unified_html_template_with_category_theme(self, mock_send_html):
        self.client_user.email = 'panel-client@test.com'
        self.client_user.save(update_fields=['email'])

        notif = Notification.objects.create(
            title='Server notice',
            message='Database maintenance starts at 11 PM.',
            priority='urgent',
            category='alert',
            target='selected',
            created_by=self.super_admin,
        )
        notif.target_users.add(self.client_user)

        NotificationService._send_email_alerts(notif)

        mock_send_html.assert_called_once()
        send_kwargs = mock_send_html.call_args.kwargs
        self.assertEqual(send_kwargs['subject'], '[Urgent] Server notice')
        self.assertEqual(send_kwargs['recipient_list'], ['panel-client@test.com'])
        self.assertIn('Category: Alert', send_kwargs['plain_content'])
        self.assertIn('Database maintenance starts at 11 PM.', send_kwargs['plain_content'])
        self.assertIn('Adarsh Admin Notification', send_kwargs['html_content'])
        self.assertIn('Server notice', send_kwargs['html_content'])
        self.assertIn('Category', send_kwargs['html_content'])
        self.assertIn('#dc2626', send_kwargs['html_content'])

    @mock.patch('core.utils.threaded_email.send_html_email_async')
    @mock.patch('django.conf.settings.EMAIL_HOST_USER', 'smtp-user')
    @mock.patch('django.conf.settings.DEFAULT_FROM_EMAIL', 'Adarsh Admin <noreply@test.com>')
    def test_send_email_alerts_renders_alert_theme_template(self, mock_send_html):
        notif = Notification.objects.create(
            title='Immediate action needed',
            message='Please review suspicious activity logs now.',
            priority='urgent',
            category='alert',
            target='selected',
            created_by=self.super_admin,
        )
        notif.target_users.add(self.client_user)

        NotificationService._send_email_alerts(notif)

        mock_send_html.assert_called_once()
        html_content = mock_send_html.call_args.kwargs['html_content']
        self.assertIn('Adarsh Admin Notification', html_content)
        self.assertIn('Immediate action needed', html_content)
        self.assertIn('Please review suspicious activity logs now.', html_content)
        self.assertIn('Urgent:', html_content)


class PanelEmailApiTests(PanelBaseTestCase):
    def setUp(self):
        super().setUp()
        self.sent_log = EmailLog.objects.create(
            recipient_name='Client User',
            recipient_email='panel-client@test.com',
            subject='Welcome',
            body_text='Hello',
            email_type=EmailLog.EMAIL_TYPE_WELCOME,
            status=EmailLog.STATUS_ON_HOLD,
        )
        EmailLog.objects.create(
            recipient_name='Other User',
            recipient_email='other@test.com',
            subject='OTP',
            body_text='Code',
            email_type=EmailLog.EMAIL_TYPE_OTP_RESET,
            status=EmailLog.STATUS_FAILED,
        )

    def test_email_logs_endpoint_supports_query_params(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.get('/panel/api/email-logs/?page=abc&per_page=999&status=on_hold')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['page'], 1)
        self.assertEqual(payload['total'], 1)
        self.assertEqual(len(payload['logs']), 1)

    def test_email_logs_endpoint_supports_search(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.get('/panel/api/email-logs/?search=other@test.com')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['total'], 1)
        self.assertEqual(payload['logs'][0]['recipient_email'], 'other@test.com')

    def test_email_logs_endpoint_supports_oldest_sort(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        EmailLog.objects.filter(id=self.sent_log.id).update(created_at=timezone.now() - timedelta(days=2))

        response = self.client.get('/panel/api/email-logs/?sort=oldest')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['sort'], 'oldest')
        self.assertEqual(payload['logs'][0]['id'], self.sent_log.id)

    def test_email_logs_endpoint_serializes_local_timezone(self):
        self.client.login(username='panel-super@test.com', password='pass1234')

        created_utc = datetime(2026, 1, 1, 0, 0, tzinfo=dt_timezone.utc)
        EmailLog.objects.filter(pk=self.sent_log.pk).update(created_at=created_utc)

        response = self.client.get('/panel/api/email-logs/?search=panel-client@test.com')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['total'], 1)

        expected_local = timezone.localtime(created_utc).strftime('%d-%m-%Y %H:%M')
        self.assertEqual(payload['logs'][0]['created_at'], expected_local)

    def test_email_logs_endpoint_denies_admin_staff_without_email_permission(self):
        self.client.login(username='panel-admin-staff@test.com', password='pass1234')
        response = self.client.get('/panel/api/email-logs/')
        self.assertEqual(response.status_code, 403)

    def test_email_logs_endpoint_allows_admin_staff_with_email_permission(self):
        self.admin_staff_profile.perm_manage_panel_email = True
        self.admin_staff_profile.save(update_fields=['perm_manage_panel_email'])

        self.client.login(username='panel-admin-staff@test.com', password='pass1234')
        response = self.client.get('/panel/api/email-logs/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

    def test_compose_defaults_uses_name(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.get('/panel/api/email-compose-defaults/?name=Ravi')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIn('Ravi', payload['default_body_text'])

    def test_send_new_requires_required_fields(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.post(
            '/panel/api/email-send/',
            data=json.dumps({'recipient_email': '', 'subject': '', 'body_text': ''}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    @mock.patch('panel.views.manage_panel_views._send_email_now')
    def test_send_new_marks_log_as_sent_on_success(self, mock_send):
        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.post(
            '/panel/api/email-send/',
            data=json.dumps({
                'recipient_email': 'new-user@test.com',
                'recipient_name': 'New User',
                'subject': 'Hello',
                'body_text': 'Welcome',
                'email_type': EmailLog.EMAIL_TYPE_SYSTEM,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        log = EmailLog.objects.get(id=payload['log_id'])
        self.assertEqual(log.status, EmailLog.STATUS_SENT)
        self.assertIsNotNone(log.sent_at)
        mock_send.assert_called_once()

    @mock.patch('panel.views.manage_panel_views._send_email_now')
    def test_send_new_normalizes_invalid_email_type(self, mock_send):
        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.post(
            '/panel/api/email-send/',
            data=json.dumps({
                'recipient_email': 'new-user@test.com',
                'recipient_name': 'New User',
                'subject': 'Hello',
                'body_text': 'Welcome',
                'email_type': 'invalid_type',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        log = EmailLog.objects.get(id=payload['log_id'])
        self.assertEqual(log.email_type, EmailLog.EMAIL_TYPE_SYSTEM)

    @mock.patch('panel.views.manage_panel_views._send_email_now')
    def test_email_resend_custom_payload_updates_log(self, mock_send):
        self.client.login(username='panel-super@test.com', password='pass1234')

        response = self.client.post(
            f'/panel/api/email-resend/{self.sent_log.id}/',
            data=json.dumps({
                'recipient_email': 'panel-client@test.com',
                'recipient_name': 'Client Updated',
                'subject': 'Updated Subject',
                'body_text': 'Updated body',
                'body_html': '<b>Updated</b>',
                'email_type': EmailLog.EMAIL_TYPE_SYSTEM,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        self.sent_log.refresh_from_db()
        self.assertEqual(self.sent_log.status, EmailLog.STATUS_SENT)
        self.assertEqual(self.sent_log.subject, 'Updated Subject')
        mock_send.assert_called_once()


class PanelBackupApiTests(PanelBaseTestCase):
    def test_backup_generate_code_returns_10_digits(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.get('/panel/api/backup/generate-code/')
        self.assertEqual(response.status_code, 200)
        code = response.json()['code']
        self.assertEqual(len(code), 10)
        self.assertTrue(code.isdigit())

    def test_backup_generate_code_denies_admin_staff_without_backup_permission(self):
        self.client.login(username='panel-admin-staff@test.com', password='pass1234')
        response = self.client.get('/panel/api/backup/generate-code/')
        self.assertEqual(response.status_code, 403)

    def test_backup_generate_code_allows_admin_staff_with_backup_permission(self):
        self.admin_staff_profile.perm_manage_panel_backup = True
        self.admin_staff_profile.save(update_fields=['perm_manage_panel_backup'])

        self.client.login(username='panel-admin-staff@test.com', password='pass1234')
        response = self.client.get('/panel/api/backup/generate-code/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

    def test_backup_initiate_validates_confirmation_code(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.post(
            '/panel/api/backup/initiate/',
            data=json.dumps({'code': '123'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_backup_initiate_creates_pending_task(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.post(
            '/panel/api/backup/initiate/',
            data=json.dumps({'code': '1234567890'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        task_id = response.json()['task_id']
        task = BackupTask.objects.get(id=task_id)
        self.assertEqual(task.status, 'pending')
        self.assertEqual(task.confirmation_code, '1234567890')

    @mock.patch('panel.services.backup_service.start_backup')
    def test_backup_start_sets_clients_and_calls_service(self, mock_start_backup):
        self.client.login(username='panel-super@test.com', password='pass1234')
        task = BackupTask.objects.create(
            created_by=self.super_admin,
            confirmation_code='1234567890',
            status='pending',
        )

        response = self.client.post(
            '/panel/api/backup/start/',
            data=json.dumps({'task_id': task.id, 'client_ids': [self.client_profile.id]}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.total, 1)
        self.assertIn(self.client_profile.id, task.client_ids)
        mock_start_backup.assert_called_once_with(task.id)

    @mock.patch('panel.services.backup_service.start_backup')
    def test_backup_start_ignores_invalid_client_ids_when_valid_exists(self, mock_start_backup):
        self.client.login(username='panel-super@test.com', password='pass1234')
        task = BackupTask.objects.create(
            created_by=self.super_admin,
            confirmation_code='1234567890',
            status='pending',
        )

        response = self.client.post(
            '/panel/api/backup/start/',
            data=json.dumps({'task_id': task.id, 'client_ids': ['bad', -5, self.client_profile.id]}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.client_ids, [self.client_profile.id])
        mock_start_backup.assert_called_once_with(task.id)

    @mock.patch('panel.services.backup_service.start_backup')
    def test_backup_start_rejects_bool_client_ids(self, mock_start_backup):
        self.client.login(username='panel-super@test.com', password='pass1234')
        task = BackupTask.objects.create(
            created_by=self.super_admin,
            confirmation_code='1234567890',
            status='pending',
        )

        response = self.client.post(
            '/panel/api/backup/start/',
            data=json.dumps({'task_id': task.id, 'client_ids': [True, False]}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
        mock_start_backup.assert_not_called()

    @mock.patch('panel.services.backup_service.start_backup')
    def test_backup_start_rejects_when_another_backup_is_active(self, mock_start_backup):
        self.client.login(username='panel-super@test.com', password='pass1234')
        task = BackupTask.objects.create(
            created_by=self.super_admin,
            confirmation_code='1234567890',
            status='pending',
        )
        BackupTask.objects.create(
            created_by=self.super_admin,
            confirmation_code='9999999999',
            status='processing',
        )

        response = self.client.post(
            '/panel/api/backup/start/',
            data=json.dumps({'task_id': task.id, 'client_ids': [self.client_profile.id]}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 429)
        self.assertFalse(response.json()['success'])
        mock_start_backup.assert_not_called()

    def test_backup_start_rejects_fully_invalid_client_ids(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        task = BackupTask.objects.create(
            created_by=self.super_admin,
            confirmation_code='1234567890',
            status='pending',
        )

        response = self.client.post(
            '/panel/api/backup/start/',
            data=json.dumps({'task_id': task.id, 'client_ids': ['bad', '  ', None]}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    @mock.patch('panel.services.backup_service.delete_backup_files')
    def test_backup_delete_now_calls_service_for_completed_task(self, mock_delete):
        self.client.login(username='panel-super@test.com', password='pass1234')
        task = BackupTask.objects.create(
            created_by=self.super_admin,
            confirmation_code='1234567890',
            status='completed',
            zip_files={'combined': {'path': 'temp/backups/x.zip', 'filename': 'x.zip', 'size': 1}},
        )

        response = self.client.post(f'/panel/api/backup/{task.id}/delete-now/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        mock_delete.assert_called_once_with(task.id)

    def test_backup_list_and_status_return_payload(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        task = BackupTask.objects.create(
            created_by=self.super_admin,
            confirmation_code='1234567890',
            status='pending',
            progress=0,
            total=1,
            client_names={str(self.client_profile.id): self.client_profile.name},
        )

        list_response = self.client.get('/panel/api/backup/list/')
        self.assertEqual(list_response.status_code, 200)
        self.assertTrue(list_response.json()['success'])

        status_response = self.client.get(f'/panel/api/backup/status/{task.id}/')
        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.json()
        self.assertTrue(status_payload['success'])
        self.assertEqual(status_payload['id'], task.id)

    def test_backup_download_rejects_invalid_path_escape(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        task = BackupTask.objects.create(
            created_by=self.super_admin,
            confirmation_code='1234567890',
            status='completed',
            zip_files={'combined': {'path': '../secrets.txt', 'filename': 'x.zip', 'size': 1}},
        )

        response = self.client.get(f'/panel/api/backup/download/{task.id}/')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()['success'])

    def test_backup_download_sanitizes_attachment_filename(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        with tempfile.TemporaryDirectory() as media_root:
            rel_zip = os.path.join('temp', 'backups', 'safe.zip').replace('\\', '/')
            abs_zip = os.path.join(media_root, 'temp', 'backups', 'safe.zip')
            os.makedirs(os.path.dirname(abs_zip), exist_ok=True)
            with open(abs_zip, 'wb') as fh:
                fh.write(b'PK\x03\x04')

            task = BackupTask.objects.create(
                created_by=self.super_admin,
                confirmation_code='1234567890',
                status='completed',
                zip_files={'combined': {'path': rel_zip, 'filename': 'safe.zip\r\nX-Injected: 1', 'size': 4}},
            )

            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.get(f'/panel/api/backup/download/{task.id}/')
                self.assertEqual(response.status_code, 200)
                content_disposition = response.get('Content-Disposition', '')
                self.assertNotIn('\r', content_disposition)
                self.assertNotIn('\n', content_disposition)
                response.close()

    @mock.patch('panel.services.backup_service._build_client_in_zip', return_value=False)
    def test_backup_service_does_not_deactivate_clients_during_processing(self, _mock_build):
        from panel.services import backup_service

        task = BackupTask.objects.create(
            created_by=self.super_admin,
            confirmation_code='1234567890',
            status='pending',
            client_ids=[self.client_profile.id],
            client_names={str(self.client_profile.id): self.client_profile.name},
        )

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                backup_service._process_backup(task.id)

        self.client_profile.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual(self.client_profile.status, 'active')
        self.assertEqual(task.status, 'completed')


class PanelMonitoringApiTests(PanelBaseTestCase):
    def test_client_errors_requires_authentication(self):
        response = self.client.post(
            '/panel/api/client-errors/',
            data=json.dumps({'errors': [{'type': 'error', 'message': 'x'}]}),
            content_type='application/json',
        )
        self.assertIn(response.status_code, (302, 401))
        if response.status_code == 401:
            self.assertFalse(response.json().get('success'))

    def test_client_errors_rejects_invalid_json(self):
        self.client.login(username='panel-client@test.com', password='pass1234')
        response = self.client.post(
            '/panel/api/client-errors/',
            data='not-json',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'bad_request')

    def test_client_errors_rate_limit_enforced(self):
        self.client.login(username='panel-client@test.com', password='pass1234')
        payload = json.dumps({'errors': [{'type': 'error', 'message': 'x'}]})

        for _ in range(10):
            response = self.client.post('/panel/api/client-errors/', data=payload, content_type='application/json')
            self.assertEqual(response.status_code, 200)

        response = self.client.post('/panel/api/client-errors/', data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()['status'], 'rate_limited')

    def test_monitoring_data_requires_super_admin(self):
        self.client.login(username='panel-client@test.com', password='pass1234')
        denied = self.client.get('/panel/api/monitoring/')
        self.assertEqual(denied.status_code, 403)

        self.client.login(username='panel-super@test.com', password='pass1234')
        allowed = self.client.get('/panel/api/monitoring/')
        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(allowed.json()['success'])

    def test_server_info_snapshot_uses_cache_when_available(self):
        from panel.views.monitoring_views import _SERVER_INFO_CACHE_KEY

        self.client.login(username='panel-super@test.com', password='pass1234')
        cache.set(_SERVER_INFO_CACHE_KEY, {'host': 'cached-host'}, 300)

        response = self.client.get('/panel/api/server-info/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertTrue(payload['cached'])
        self.assertEqual(payload['snapshot']['host'], 'cached-host')

    def test_operations_feed_requires_super_admin(self):
        self.client.login(username='panel-client@test.com', password='pass1234')
        denied = self.client.get('/panel/api/operations-feed/')
        self.assertEqual(denied.status_code, 403)

        self.client.login(username='panel-super@test.com', password='pass1234')
        allowed = self.client.get('/panel/api/operations-feed/')
        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(allowed.json()['success'])

    @override_settings(ACTIVITY_LOG_MANUAL_CLEAR_ENABLED=True)
    def test_clear_activity_logs_super_admin_creates_pending_request(self):
        ActivityLog.objects.create(
            user=self.super_admin,
            action='login',
            description='Safety test log',
        )

        self.client.login(username='panel-super@test.com', password='pass1234')
        code_response = self.client.get('/panel/api/activity-logs/clear/generate-code/')
        self.assertEqual(code_response.status_code, 200)
        confirmation_code = code_response.json().get('code')
        self.assertTrue(confirmation_code)

        response = self.client.post(
            '/panel/api/activity-logs/clear/',
            data=json.dumps({'confirmation_code': confirmation_code}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertTrue(payload.get('pending_pro_user_confirmation'))
        self.assertEqual(payload.get('state', {}).get('status'), 'pending_pro_user_confirmation')
        self.assertEqual(ActivityLog.objects.count(), 1)

    @override_settings(ACTIVITY_LOG_MANUAL_CLEAR_ENABLED=True)
    def test_clear_activity_logs_pro_user_requires_pending_request(self):
        pro_user = User.objects.create_user(
            username='panel-pro-clear@test.com',
            email='panel-pro-clear@test.com',
            password='pass1234',
            role='pro_user',
        )
        ActivityLog.objects.create(
            user=self.super_admin,
            action='login',
            description='Pending request required',
        )

        self.client.login(username=pro_user.username, password='pass1234')
        code_response = self.client.get('/panel/api/activity-logs/clear/generate-code/')
        self.assertEqual(code_response.status_code, 200)
        confirmation_code = code_response.json().get('code')

        response = self.client.post(
            '/panel/api/activity-logs/clear/',
            data=json.dumps({'confirmation_code': confirmation_code}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertFalse(payload.get('success'))
        self.assertEqual(payload.get('code'), 'no_pending_request')
        self.assertEqual(ActivityLog.objects.count(), 1)

    @override_settings(ACTIVITY_LOG_MANUAL_CLEAR_ENABLED=True)
    def test_clear_activity_logs_pro_user_confirms_and_archives(self):
        pro_user = User.objects.create_user(
            username='panel-pro-confirm@test.com',
            email='panel-pro-confirm@test.com',
            password='pass1234',
            role='pro_user',
        )
        ActivityLog.objects.create(
            user=self.super_admin,
            action='login',
            description='Archive me first',
        )
        ActivityLog.objects.create(
            user=self.super_admin,
            action='settings_update',
            description='Archive me second',
        )

        self.client.login(username='panel-super@test.com', password='pass1234')
        admin_code_response = self.client.get('/panel/api/activity-logs/clear/generate-code/')
        self.assertEqual(admin_code_response.status_code, 200)
        admin_code = admin_code_response.json().get('code')
        self.assertTrue(admin_code)
        request_response = self.client.post(
            '/panel/api/activity-logs/clear/',
            data=json.dumps({'confirmation_code': admin_code}),
            content_type='application/json',
        )
        self.assertEqual(request_response.status_code, 200)
        self.assertTrue(request_response.json().get('pending_pro_user_confirmation'))

        self.client.login(username=pro_user.username, password='pass1234')
        pro_code_response = self.client.get('/panel/api/activity-logs/clear/generate-code/')
        self.assertEqual(pro_code_response.status_code, 200)
        pro_code = pro_code_response.json().get('code')
        self.assertTrue(pro_code)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    '/panel/api/activity-logs/clear/',
                    data=json.dumps({'confirmation_code': pro_code}),
                    content_type='application/json',
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload.get('success'))
            self.assertGreaterEqual(payload.get('deleted_count', 0), 2)
            self.assertEqual(ActivityLog.objects.count(), 0)

            archive_rel = payload.get('archive_relative_path')
            self.assertTrue(archive_rel)
            archive_abs = os.path.join(media_root, *archive_rel.split('/'))
            self.assertTrue(os.path.exists(archive_abs))

            with open(archive_abs, 'r', encoding='utf-8') as archive_file:
                lines = [line.strip() for line in archive_file if line.strip()]

            self.assertGreaterEqual(len(lines), 3)
            self.assertIn('activity_log_archive', lines[0])
            self.assertTrue(any('Archive me first' in line for line in lines[1:]))
            self.assertTrue(any('Archive me second' in line for line in lines[1:]))

        state_response = self.client.get('/panel/api/activity-logs/clear/state/')
        self.assertEqual(state_response.status_code, 200)
        state_payload = state_response.json()
        self.assertEqual(state_payload.get('state', {}).get('status'), 'idle')
        self.assertEqual(state_payload.get('state', {}).get('last_completed_by'), pro_user.username)

    def test_clear_activity_logs_disabled_returns_403(self):
        ActivityLog.objects.create(
            user=self.super_admin,
            action='login',
            description='Guard disabled safety test',
        )

        self.client.login(username='panel-super@test.com', password='pass1234')

        state_response = self.client.get('/panel/api/activity-logs/clear/state/')
        self.assertEqual(state_response.status_code, 403)
        self.assertEqual(state_response.json().get('code'), 'log_clear_disabled')

        code_response = self.client.get('/panel/api/activity-logs/clear/generate-code/')
        self.assertEqual(code_response.status_code, 403)
        self.assertEqual(code_response.json().get('code'), 'log_clear_disabled')

        response = self.client.post(
            '/panel/api/activity-logs/clear/',
            data=json.dumps({'confirmation_code': '1234567890'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get('code'), 'log_clear_disabled')
        self.assertEqual(ActivityLog.objects.count(), 1)

    def test_operations_feed_filters_and_recent_first(self):
        from datetime import timedelta
        from django.utils import timezone

        older_task = BackgroundTask.objects.create(
            user=self.client_user,
            task_type='export_pdf',
            status='completed',
            progress=10,
            total=10,
        )
        processing_task = BackgroundTask.objects.create(
            user=self.super_admin,
            task_type='bulk_upload',
            status='processing',
            progress=1,
            total=10,
        )
        latest_log = ActivityLog.objects.create(
            user=self.super_admin,
            action='settings_update',
            description='Updated export settings',
            target_model='SystemSettings',
            target_name='Export Settings',
            ip_address='127.0.0.1',
        )

        now = timezone.now()
        BackgroundTask.objects.filter(pk=older_task.pk).update(created_at=now - timedelta(hours=3))
        BackgroundTask.objects.filter(pk=processing_task.pk).update(created_at=now - timedelta(hours=2))
        ActivityLog.objects.filter(pk=latest_log.pk).update(created_at=now - timedelta(hours=1))

        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.get('/panel/api/operations-feed/', {'limit': 20, 'source': 'all'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertGreaterEqual(payload['total'], 3)
        self.assertEqual(payload['items'][0]['source_type'], 'activity_log')
        self.assertIn('source_counts', payload)
        self.assertGreaterEqual(payload['source_counts'].get('background_task', 0), 2)
        self.assertGreaterEqual(payload['source_counts'].get('activity_log', 0), 1)

        task_filtered = self.client.get('/panel/api/operations-feed/', {
            'source': 'tasks',
            'task_status': 'processing',
            'limit': 20,
        })
        self.assertEqual(task_filtered.status_code, 200)
        task_items = task_filtered.json()['items']
        self.assertTrue(all(item['source_type'] in ('background_task', 'backup_task') for item in task_items))
        self.assertTrue(all(item['status'] == 'processing' for item in task_items))

        role_filtered = self.client.get('/panel/api/operations-feed/', {
            'source': 'tasks',
            'user_role': 'client',
            'limit': 20,
        })
        self.assertEqual(role_filtered.status_code, 200)
        role_items = role_filtered.json()['items']
        self.assertTrue(any(item['user'] == self.client_user.username for item in role_items))

    def test_operations_feed_logs_respects_user_and_action_filters(self):
        ActivityLog.objects.create(
            user=self.client_user,
            action='login',
            description='Panel Client login',
            ip_address='127.0.0.1',
        )
        ActivityLog.objects.create(
            user=self.client_user,
            action='settings_update',
            description='Panel Client settings update',
            ip_address='127.0.0.1',
        )
        ActivityLog.objects.create(
            user=self.super_admin,
            action='login',
            description='Super admin login',
            ip_address='127.0.0.1',
        )

        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.get('/panel/api/operations-feed/', {
            'source': 'logs',
            'user_role': 'client',
            'action': 'login',
            'limit': 50,
        })
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertNotIn('clients', payload)
        self.assertGreaterEqual(payload['source_counts'].get('activity_log', 0), 1)

        items = payload['items']
        self.assertTrue(items)
        self.assertTrue(all(item['source_type'] == 'activity_log' for item in items))
        self.assertTrue(all(item['action'] == 'login' for item in items))
        self.assertTrue(all(item['user'] == self.client_user.username for item in items))

    def test_operations_feed_logs_supports_deep_pagination_without_cap(self):
        for i in range(450):
            ActivityLog.objects.create(
                user=self.super_admin,
                action='other',
                description=f'deep-log-{i:03d}',
            )

        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.get('/panel/api/operations-feed/', {
            'source': 'logs',
            'limit': 25,
            'offset': 350,
        })
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertGreaterEqual(payload.get('total', 0), 450)

        items = payload.get('items', [])
        self.assertEqual(len(items), 25)
        self.assertTrue(all(item.get('source_type') == 'activity_log' for item in items))
        self.assertGreaterEqual(payload.get('source_counts', {}).get('activity_log', 0), 450)

    def test_operations_feed_rejects_removed_client_logs_source(self):
        self.client.login(username='panel-super@test.com', password='pass1234')
        response = self.client.get('/panel/api/operations-feed/', {
            'source': 'client_logs',
            'limit': 20,
        })
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload.get('success'))
        self.assertIn('Invalid source filter', payload.get('message', ''))

    def test_operations_feed_marks_only_latest_active_task_cancellable_for_pro_user(self):
        from datetime import timedelta
        from django.utils import timezone

        pro_user = User.objects.create_user(
            username='panel-pro@test.com',
            email='panel-pro@test.com',
            password='pass1234',
            role='pro_user',
        )

        older_active = BackgroundTask.objects.create(
            user=self.client_user,
            task_type='export_pdf',
            status='processing',
            progress=1,
            total=10,
        )
        latest_active = BackgroundTask.objects.create(
            user=self.super_admin,
            task_type='export_docx',
            status='pending',
            progress=0,
            total=0,
        )
        completed_task = BackgroundTask.objects.create(
            user=self.super_admin,
            task_type='export_excel',
            status='completed',
            progress=4,
            total=4,
        )

        now = timezone.now()
        BackgroundTask.objects.filter(pk=older_active.pk).update(created_at=now - timedelta(hours=2))
        BackgroundTask.objects.filter(pk=latest_active.pk).update(created_at=now - timedelta(minutes=5))
        BackgroundTask.objects.filter(pk=completed_task.pk).update(created_at=now - timedelta(minutes=2))

        self.client.login(username=pro_user.username, password='pass1234')
        response = self.client.get('/panel/api/operations-feed/', {'source': 'tasks', 'limit': 50})
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload.get('success'))

        background_items = [
            item for item in payload.get('items', [])
            if item.get('source_type') == 'background_task'
        ]
        self.assertTrue(background_items)

        cancelable_ids = [item.get('task_id') for item in background_items if item.get('can_cancel')]
        self.assertEqual(cancelable_ids, [latest_active.id])

        by_id = {item.get('task_id'): item for item in background_items}
        self.assertEqual(by_id[older_active.id].get('can_cancel'), False)
        self.assertEqual(by_id[completed_task.id].get('can_cancel'), False)

    def test_latest_only_cancel_requires_pro_user(self):
        task = BackgroundTask.objects.create(
            user=self.client_user,
            task_type='export_pdf',
            status='processing',
            progress=2,
            total=10,
        )

        self.client.login(username='panel-client@test.com', password='pass1234')
        response = self.client.post(
            f'/panel/api/task-cancel/{task.id}/',
            data=json.dumps({'latest_only': True}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json().get('success'))

    def test_pro_user_latest_only_cancel_allows_only_latest_active_task(self):
        from datetime import timedelta
        from django.utils import timezone

        pro_user = User.objects.create_user(
            username='panel-pro-cancel@test.com',
            email='panel-pro-cancel@test.com',
            password='pass1234',
            role='pro_user',
        )

        older_active = BackgroundTask.objects.create(
            user=self.client_user,
            task_type='export_pdf',
            status='processing',
            progress=3,
            total=10,
        )
        latest_active = BackgroundTask.objects.create(
            user=self.super_admin,
            task_type='export_docx',
            status='pending',
            progress=0,
            total=0,
        )

        now = timezone.now()
        BackgroundTask.objects.filter(pk=older_active.pk).update(created_at=now - timedelta(hours=1))
        BackgroundTask.objects.filter(pk=latest_active.pk).update(created_at=now - timedelta(minutes=1))

        self.client.login(username=pro_user.username, password='pass1234')

        wrong_response = self.client.post(
            f'/panel/api/task-cancel/{older_active.id}/',
            data=json.dumps({'latest_only': True}),
            content_type='application/json',
        )
        self.assertEqual(wrong_response.status_code, 400)
        self.assertFalse(wrong_response.json().get('success'))

        ok_response = self.client.post(
            f'/panel/api/task-cancel/{latest_active.id}/',
            data=json.dumps({'latest_only': True}),
            content_type='application/json',
        )
        self.assertEqual(ok_response.status_code, 200)
        self.assertTrue(ok_response.json().get('success'))

        latest_active.refresh_from_db()
        older_active.refresh_from_db()
        self.assertEqual(latest_active.status, 'cancelled')
        self.assertEqual(older_active.status, 'processing')

        cancel_log = (
            ActivityLog.objects
            .filter(action='other', target_model='BackgroundTask', target_id=latest_active.id)
            .order_by('-created_at')
            .first()
        )
        self.assertIsNotNone(cancel_log)
        self.assertEqual(cancel_log.user, pro_user)
        self.assertIn('cancelled', (cancel_log.description or '').lower())

