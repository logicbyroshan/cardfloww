from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from organisation.models import Organisation
from core.models import BackgroundTask
from stats.models import StatsSnapshot

User = get_user_model()

class StatisticsTests(TestCase):
    def setUp(self):
        # Create standard test users
        self.super_admin = User.objects.create_superuser(
            username='stats-admin@test.com',
            password='testpass123',
            email='stats-admin@test.com'
        )
        self.super_admin.role = 'super_admin'
        self.super_admin.save()

        self.client_user = User.objects.create_user(
            username='stats-client@test.com',
            password='testpass123',
            email='stats-client@test.com'
        )
        self.client_user.role = 'prime_manager'
        self.client_user.save()

        # Create client profile
        Organisation.objects.create(
            user=self.client_user,
            name='Stats Test Client',
            status='active'
        )

        # Create a pro user
        self.pro_user = User.objects.create_user(
            username='stats-pro@test.com',
            password='testpass123',
            email='stats-pro@test.com'
        )
        self.pro_user.role = 'pro_user'
        # Grant the perm explicitly
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(User)
        perm = Permission.objects.filter(codename='perm_pro_user_options').first()
        if perm:
            self.pro_user.user_permissions.add(perm)
        self.pro_user.save()

    def test_statistics_page_redirects_for_anonymous_user(self):
        response = self.client.get(reverse('pro_user_statistics'))
        self.assertRedirects(response, f'/panel/auth/login/?next={reverse("pro_user_statistics")}')

    def test_statistics_page_redirects_for_non_pro_user(self):
        self.assertTrue(self.client.login(username='stats-client@test.com', password='testpass123'))
        response = self.client.get(reverse('pro_user_statistics'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        self.client.logout()

    def test_statistics_page_accessible_for_super_admin(self):
        self.assertTrue(self.client.login(username='stats-admin@test.com', password='testpass123'))
        response = self.client.get(reverse('pro_user_statistics'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'stats/statistics.html')
        self.client.logout()

    def test_statistics_page_accessible_for_pro_user(self):
        self.assertTrue(self.client.login(username='stats-pro@test.com', password='testpass123'))
        response = self.client.get(reverse('pro_user_statistics'))
        self.assertEqual(response.status_code, 200)
        self.client.logout()

    def test_api_endpoint_denied_for_non_pro_user(self):
        self.assertTrue(self.client.login(username='stats-client@test.com', password='testpass123'))
        response = self.client.get(reverse('api_statistics_data'))
        self.assertEqual(response.status_code, 403)
        self.client.logout()

    def test_api_endpoint_returns_json_data_for_super_admin(self):
        self.assertTrue(self.client.login(username='stats-admin@test.com', password='testpass123'))
        
        # Test different ranges
        for r in ('hourly', 'daily', 'weekly', 'monthly'):
            response = self.client.get(reverse('api_statistics_data') + f'?range={r}')
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['success'])
            self.assertIn('labels', data)
            self.assertIn('client_activity', data)
            self.assertIn('assistant_activity', data)
            self.assertIn('batch_jobs_count', data)
            self.assertIn('summary', data)
            self.assertIn('current_active_users', data['summary'])
            self.assertIn('peak_active_users', data['summary'])
            
        self.client.logout()

    def test_batch_jobs_page_redirects_for_anonymous_user(self):
        response = self.client.get(reverse('pro_user_batch_jobs'))
        self.assertRedirects(response, f'/login/?next={reverse("pro_user_batch_jobs")}')

    def test_batch_jobs_page_redirects_for_non_pro_user(self):
        self.assertTrue(self.client.login(username='stats-client@test.com', password='testpass123'))
        response = self.client.get(reverse('pro_user_batch_jobs'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        self.client.logout()

    def test_batch_jobs_page_accessible_for_super_admin(self):
        self.assertTrue(self.client.login(username='stats-admin@test.com', password='testpass123'))
        response = self.client.get(reverse('pro_user_batch_jobs'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pro_user/batch-jobs.html')
        self.client.logout()

    def test_batch_jobs_page_accessible_for_pro_user(self):
        self.assertTrue(self.client.login(username='stats-pro@test.com', password='testpass123'))
        response = self.client.get(reverse('pro_user_batch_jobs'))
        self.assertEqual(response.status_code, 200)
        self.client.logout()
