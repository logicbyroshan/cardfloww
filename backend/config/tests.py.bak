from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings
from django.urls import resolve

from core.models import User


class ConfigRootUrlTests(TestCase):
    def test_root_urlconf_exposes_health_check(self):
        match = resolve('/api/health/')
        self.assertEqual(match.url_name, 'health_check')



class ConfigMediaGuardTests(TestCase):
    def setUp(self):
        from config.urls import _protected_media_serve

        self.factory = RequestFactory()
        self._protected_media_serve = _protected_media_serve

    def test_protected_media_redirects_anonymous_user_to_login(self):
        request = self.factory.get('/media/adarshimg/secret.jpg')
        request.user = AnonymousUser()

        response = self._protected_media_serve(request, 'adarshimg/secret.jpg', document_root='.')
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    @override_settings(MEDIA_USE_XACCEL=True)
    def test_protected_media_uses_x_accel_for_authenticated_user(self):
        request = self.factory.get('/media/exports/report.pdf')
        request.user = User.objects.create_user(
            username='config-auth@test.com',
            email='config-auth@test.com',
            password='pass1234',
            role='super_admin',
        )

        response = self._protected_media_serve(request, 'exports/report.pdf', document_root='.')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Accel-Redirect'], '/protected-media/exports/report.pdf')


class PanelMediaGuardTests(TestCase):
    def setUp(self):
        from config.urls_panel import _protected_media_serve

        self.factory = RequestFactory()
        self._protected_media_serve = _protected_media_serve

    def test_panel_protected_exports_rejects_non_owner_authenticated_user(self):
        request = self.factory.get('/media/exports/private.zip')
        request.user = User.objects.create_user(
            username='panel-user@test.com',
            email='panel-user@test.com',
            password='pass1234',
            role='client',
        )

        response = self._protected_media_serve(request, 'exports/private.zip', document_root='.')
        self.assertEqual(response.status_code, 404)

    def test_panel_media_rejects_path_traversal(self):
        request = self.factory.get('/media/../exports/private.zip')
        request.user = User.objects.create_user(
            username='panel-admin@test.com',
            email='panel-admin@test.com',
            password='pass1234',
            role='super_admin',
        )

        response = self._protected_media_serve(request, '../exports/private.zip', document_root='.')
        self.assertEqual(response.status_code, 404)

    @override_settings(MEDIA_USE_XACCEL=True)
    def test_panel_media_allows_super_admin_with_x_accel(self):
        request = self.factory.get('/media/exports/report.pdf')
        request.user = User.objects.create_user(
            username='panel-super@test.com',
            email='panel-super@test.com',
            password='pass1234',
            role='super_admin',
        )

        response = self._protected_media_serve(request, 'exports/report.pdf', document_root='.')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Accel-Redirect'], '/protected-media/exports/report.pdf')


class PanelAndWebsiteUrlconfTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_panel_robots_disallows_all(self):
        from config.urls_panel import panel_robots_txt

        request = self.factory.get('/robots.txt')
        response = panel_robots_txt(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Disallow: /', response.content.decode('utf-8'))

    def test_public_media_serve_blocks_non_public_prefix(self):
        from config.urls_website import _public_media_serve

        request = self.factory.get('/media/exports/private.zip')
        response = _public_media_serve(request, 'exports/private.zip', document_root='.')

        self.assertEqual(response.status_code, 404)

    def test_public_media_serve_allows_public_prefix(self):
        from config.urls_website import _public_media_serve

        request = self.factory.get('/media/adarshimg/photo.jpg')
        with self.assertRaises(Http404):
            _public_media_serve(request, 'adarshimg/photo.jpg', document_root='.')


@override_settings(DEBUG=False)
class CustomErrorPageTests(TestCase):
    def _build_request_with_session(self, path):
        request = RequestFactory().get(path)
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        return request

    def test_unknown_url_uses_custom_404_page(self):
        response = self.client.get('/this-path-does-not-exist-anywhere/')

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Page Not Found', status_code=404)
        self.assertContains(response, 'Go to Home', status_code=404)

    def test_custom_404_home_link_for_client_role(self):
        from core.views.errors import error_404

        request = self._build_request_with_session('/panel/unknown-path/')
        request.user = User.objects.create_user(
            username='client-error@test.com',
            email='client-error@test.com',
            password='pass1234',
            role='client',
        )

        response = error_404(request, Exception('missing'))
        self.assertEqual(response.status_code, 404)
        self.assertIn('href="/panel/client/dashboard/"', response.content.decode('utf-8'))

    def test_custom_404_home_link_for_panel_subdomain_admin(self):
        from core.views.errors import error_404

        request = self._build_request_with_session('/missing-on-panel-subdomain/')
        request.user = User.objects.create_user(
            username='admin-error@test.com',
            email='admin-error@test.com',
            password='pass1234',
            role='admin_staff',
        )
        request.urlconf = 'config.urls_panel'

        response = error_404(request, Exception('missing'))
        self.assertEqual(response.status_code, 404)
        self.assertIn('href="/"', response.content.decode('utf-8'))

    def test_custom_404_uses_mobile_template_for_app_path(self):
        from core.views.errors import error_404

        request = self._build_request_with_session('/app/missing-page/')
        request.user = AnonymousUser()

        response = error_404(request, Exception('missing'))
        body = response.content.decode('utf-8')

        self.assertEqual(response.status_code, 404)
        self.assertIn('Mobile App', body)
        self.assertIn('Error 404', body)
