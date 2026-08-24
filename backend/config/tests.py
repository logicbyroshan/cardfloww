from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings
from django.urls import resolve

from core.models import User
from config.urls import _protected_media_serve


class ConfigRootUrlTests(TestCase):
    def test_root_urlconf_exposes_health_check(self):
        match = resolve('/api/health/')
        self.assertEqual(match.url_name, 'health_check')


class ConfigMediaGuardTests(TestCase):
    def setUp(self):
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

    def test_protected_exports_rejects_non_owner_authenticated_user(self):
        request = self.factory.get('/media/exports/private.zip')
        request.user = User.objects.create_user(
            username='panel-user@test.com',
            email='panel-user@test.com',
            password='pass1234',
            role='client',
        )

        response = self._protected_media_serve(request, 'exports/private.zip', document_root='.')
        self.assertEqual(response.status_code, 404)

    def test_media_guard_rejects_path_traversal(self):
        request = self.factory.get('/media/../exports/private.zip')
        request.user = User.objects.create_user(
            username='panel-admin@test.com',
            email='panel-admin@test.com',
            password='pass1234',
            role='super_admin',
        )

        response = self._protected_media_serve(request, '../exports/private.zip', document_root='.')
        self.assertEqual(response.status_code, 404)


@override_settings(DEBUG=False)
class CustomErrorPageTests(TestCase):
    def _build_request_with_session(self, path):
        request = RequestFactory().get(path)
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        return request

    def test_unknown_url_returns_unauthorized_for_anonymous_user(self):
        response = self.client.get('/this-path-does-not-exist-anywhere/')
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data.get('authenticated', True))

    def test_unknown_url_returns_json_404_for_authenticated_user(self):
        user = User.objects.create_user(
            username='auth-error-user@test.com',
            email='auth-error-user@test.com',
            password='pass1234',
            role='super_admin',
        )
        self.client.force_login(user)
        response = self.client.get('/this-path-does-not-exist-anywhere/')
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data.get('success', True))
        self.assertEqual(data.get('status_code'), 404)

    def test_custom_404_json_structure(self):
        import json
        from core.views.errors import error_404

        request = self._build_request_with_session('/api/unknown-endpoint/')
        request.user = AnonymousUser()

        response = error_404(request, Exception('missing'))
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.content.decode('utf-8'))
        self.assertFalse(data['success'])
        self.assertEqual(data['status_code'], 404)
        self.assertEqual(data['title'], 'Page Not Found')
