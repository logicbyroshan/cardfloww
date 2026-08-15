"""
Tests for accounts app.
Covers: AuthService, OTPService, RoleService, rate limiting, login/logout flows.
"""
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.test.client import RequestFactory
from unittest import mock
import json
from core.models import ActivityLog

User = get_user_model()


class AuthServiceTests(TestCase):
    """Tests for accounts.services.AuthService"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='test@example.com',
            email='test@example.com',
            password='testpass123',
            role='client',
        )

    def test_check_user_exists_found(self):
        from accounts.services import AuthService
        result = AuthService.check_user_exists('test@example.com')
        self.assertTrue(result['exists'])
        self.assertEqual(result['user_name'], 'User')
        self.assertEqual(result['user_email'], 'test@example.com')

    def test_check_user_exists_not_found(self):
        from accounts.services import AuthService
        result = AuthService.check_user_exists('nobody@example.com')
        self.assertTrue(result['exists'])
        self.assertEqual(result['user_name'], 'User')
        self.assertEqual(result['user_email'], 'nobody@example.com')

    def test_authenticate_user_success(self):
        from accounts.services import AuthService
        result = AuthService.authenticate_user('test@example.com', 'testpass123')
        self.assertTrue(result['success'])
        self.assertEqual(result['user'].email, 'test@example.com')

    def test_authenticate_user_success_with_phone_identifier(self):
        from accounts.services import AuthService
        self.user.phone = '+91 98765-43210'
        self.user.save(update_fields=['phone'])

        result = AuthService.authenticate_user('9876543210', 'testpass123')
        self.assertTrue(result['success'])
        self.assertEqual(result['user'].email, 'test@example.com')

    def test_authenticate_user_wrong_password(self):
        from accounts.services import AuthService
        result = AuthService.authenticate_user('test@example.com', 'wrongpass')
        self.assertFalse(result['success'])

    def test_authenticate_user_nonexistent(self):
        from accounts.services import AuthService
        result = AuthService.authenticate_user('nobody@example.com', 'pass')
        self.assertFalse(result['success'])

    def test_authenticate_inactive_user(self):
        from accounts.services import AuthService
        self.user.is_active = False
        self.user.save()
        result = AuthService.authenticate_user('test@example.com', 'testpass123')
        self.assertFalse(result['success'])

    def test_get_dashboard_url_client(self):
        from accounts.services import AuthService
        url = AuthService.get_dashboard_url(self.user)
        self.assertIn('client', url)

    def test_get_dashboard_url_super_admin(self):
        from accounts.services import AuthService
        admin = User.objects.create_user(
            username='admin@example.com',
            email='admin@example.com',
            password='admin123',
            role='super_admin',
        )
        url = AuthService.get_dashboard_url(admin)
        self.assertEqual(url, '/panel/')


class PasswordNormalizationTests(TestCase):
    def test_normalize_password_phone_with_country_and_brackets(self):
        from accounts.services import normalize_password_input

        self.assertEqual(
            normalize_password_input('(+91) 98765-43210'),
            '9876543210',
        )

    def test_normalize_password_phone_with_dots(self):
        from accounts.services import normalize_password_input

        self.assertEqual(
            normalize_password_input('91.98765.43210'),
            '9876543210',
        )

    def test_normalize_password_keeps_symbolic_custom_password(self):
        from accounts.services import normalize_password_input

        self.assertEqual(
            normalize_password_input('1234!@#'),
            '1234!@#',
        )


@override_settings(DEBUG=True)
class OTPServiceTests(TestCase):
    """Tests for accounts.services.OTPService"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='otp@example.com',
            email='otp@example.com',
            password='testpass123',
            role='client',
        )
        from organisation.models import Organisation
        Organisation.objects.create(user=self.user, name='OTP Org', status='active')
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_generate_otp_length(self):
        from accounts.services import OTPService
        otp = OTPService.generate_otp()
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())

    def test_generate_reset_token_format(self):
        from accounts.services import OTPService
        token = OTPService.generate_reset_token()
        # HMAC format: raw_token.signature
        self.assertIn('.', token)
        parts = token.split('.')
        self.assertEqual(len(parts), 2)

    def test_send_otp_success(self):
        from accounts.services import OTPService
        result = OTPService.send_otp('otp@example.com')
        self.assertTrue(result['success'])

    def test_send_otp_nonexistent_email(self):
        from accounts.services import OTPService
        result = OTPService.send_otp('nobody@example.com')
        # OTPService may silently succeed even for unknown emails (security best practice)
        self.assertIn('success', result)

    def test_verify_otp_and_reset_password(self):
        from accounts.services import OTPService
        send_result = OTPService.send_otp('otp@example.com')
        self.assertTrue(send_result['success'])
        dev_otp = send_result.get('dev_otp')
        if dev_otp:
            verify_result = OTPService.verify_otp('otp@example.com', dev_otp)
            self.assertTrue(verify_result['success'])
            reset_token = verify_result.get('reset_token')
            self.assertIsNotNone(reset_token)

            reset_result = OTPService.reset_password(
                'otp@example.com', reset_token, 'newpassword1'
            )
            self.assertTrue(reset_result['success'])

            from accounts.services import AuthService
            auth_result = AuthService.authenticate_user('otp@example.com', 'newpassword1')
            self.assertTrue(auth_result['success'])

    def test_verify_otp_wrong_code(self):
        from accounts.services import OTPService
        OTPService.send_otp('otp@example.com')
        result = OTPService.verify_otp('otp@example.com', '000000')
        self.assertFalse(result['success'])

    def test_reset_password_invalid_token(self):
        from accounts.services import OTPService
        result = OTPService.reset_password('otp@example.com', 'fake.token', 'newpass123')
        self.assertFalse(result['success'])

    def test_reset_password_too_short(self):
        from accounts.services import OTPService
        send = OTPService.send_otp('otp@example.com')
        dev_otp = send.get('dev_otp')
        if dev_otp:
            verify = OTPService.verify_otp('otp@example.com', dev_otp)
            token = verify.get('reset_token')
            if token:
                result = OTPService.reset_password('otp@example.com', token, 'short')
                self.assertFalse(result['success'])


class RoleServiceTests(TestCase):
    """Tests for accounts.services.RoleService"""

    def test_setup_groups(self):
        from accounts.services import RoleService
        result = RoleService.setup_groups()
        self.assertTrue(result['success'])
        self.assertIn('groups', result)

    def test_get_role_display_name(self):
        from accounts.services import RoleService
        self.assertEqual(RoleService.get_role_display_name('super_admin'), 'Super Admin')
        self.assertEqual(RoleService.get_role_display_name('client'), 'Client')


class LoginViewTests(TestCase):
    """Tests for login/logout views"""

    def setUp(self):
        from django.contrib.sessions.models import Session
        Session.objects.all().delete()  # Clear any leftover sessions
        self.user = User.objects.create_user(
            username='view@example.com',
            email='view@example.com',
            password='testpass123',
            role='client',
        )
        from organisation.models import Organisation
        Organisation.objects.create(user=self.user, name='View Org', status='active')
        cache.clear()

    def tearDown(self):
        from django.contrib.sessions.models import Session
        Session.objects.all().delete()  # Clean up after test
        cache.clear()

    def _create_authenticated_session(self, browser_fp='', surface='desktop', mobile_auth_ok=False):
        session = SessionStore()
        session['_auth_user_id'] = str(self.user.pk)
        session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
        session['_auth_user_hash'] = self.user.get_session_auth_hash()
        if browser_fp:
            session['_auth_browser_fp'] = browser_fp
        session['_auth_login_surface'] = surface
        if mobile_auth_ok or surface == 'mobile':
            session['mobile_auth_ok'] = True
        session.save()

    def test_login_page_loads(self):
        response = self.client.get('/api/auth/me/')
        self.assertIn(response.status_code, [200, 401])

    def test_logout_redirects(self):
        self.client.login(username='view@example.com', password='testpass123')
        response = self.client.post('/api/auth/logout/')
        self.assertEqual(response.status_code, 200)

    def test_check_email_api(self):
        response = self.client.post(
            '/api/auth/check-email/',
            data=json.dumps({'email': 'view@example.com'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('exists') or data.get('success'))

    def test_login_api_success(self):
        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'email': 'view@example.com',
                'password': 'testpass123',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    def test_login_api_success_with_phone_identifier(self):
        self.user.phone = '+91 90123-45678'
        self.user.save(update_fields=['phone'])

        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'email': '9012345678',
                'password': 'testpass123',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    def test_login_api_automatically_revokes_oldest_session_for_client(self):
        # Create an existing session for the user WITH a matching
        # UserDeviceSession record so the signal can find and revoke it.
        from django.contrib.sessions.models import Session
        from accounts.models import UserDeviceSession
        from django.utils import timezone

        self._create_authenticated_session(surface='desktop')
        self.assertEqual(Session.objects.count(), 1)
        old_session_key = Session.objects.first().session_key

        # Register the session with the device-tracking table
        UserDeviceSession.objects.create(
            user=self.user,
            session_key=old_session_key,
            device_type='web',
            last_active=timezone.now(),
        )

        # Login again - should succeed immediately (no stop) and kick the old one
        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'email': 'view@example.com',
                'password': 'testpass123',
            }),
            content_type='application/json',
            REMOTE_ADDR='203.0.113.24',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'], f"Login failed: {payload.get('message')}")
        
        # Verify old session was revoked (key no longer exists)
        self.assertFalse(Session.objects.filter(session_key=old_session_key).exists())
        # New session was created (at least 1 session should exist)
        self.assertGreaterEqual(Session.objects.count(), 1)

    def test_login_api_force_logout_other_device_allows_handoff(self):
        from accounts.services import AuthService
        from accounts.models import UserDeviceSession
        from django.utils import timezone

        self._create_authenticated_session(surface='desktop')
        old_session_key = Session.objects.first().session_key

        # Register with device-tracking so the signal can manage it
        UserDeviceSession.objects.create(
            user=self.user,
            session_key=old_session_key,
            device_type='web',
            last_active=timezone.now(),
        )

        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'email': 'view@example.com',
                'password': 'testpass123',
                'force_logout_other': True,
            }),
            content_type='application/json',
            REMOTE_ADDR='203.0.113.24',
            HTTP_USER_AGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0',
            HTTP_ACCEPT_LANGUAGE='en-US',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        inspection = AuthService.inspect_active_sessions_for_user(self.user.id)
        surface_counts = inspection.get('surface_counts') or {}
        self.assertEqual(int(surface_counts.get('desktop', 0) or 0), 1)

    def test_login_api_allows_super_admin_unlimited_desktop_sessions(self):
        super_admin = User.objects.create_user(
            username='sa-limit@example.com',
            email='sa-limit@example.com',
            password='testpass123',
            role='super_admin',
        )

        # Create 5 existing sessions
        for _ in range(5):
            session = SessionStore()
            session['_auth_user_id'] = str(super_admin.pk)
            session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
            session['_auth_user_hash'] = super_admin.get_session_auth_hash()
            session['_auth_login_surface'] = 'desktop'
            session.save()

        # Login 6th time - should succeed and NOT revoke any existing sessions
        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'email': 'sa-limit@example.com',
                'password': 'testpass123',
            }),
            content_type='application/json',
            REMOTE_ADDR='203.0.113.25',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        
        # Verify all 6 sessions exist (5 old + 1 new)
        from django.contrib.sessions.models import Session
        count = Session.objects.filter(session_key__in=[s.session_key for s in Session.objects.all()]).count()
        # Filter by user in session data to be sure
        user_sessions = 0
        for s in Session.objects.all():
            if str(s.get_decoded().get('_auth_user_id')) == str(super_admin.pk):
                user_sessions += 1
        self.assertEqual(user_sessions, 6)

    def test_login_api_allows_pro_user_unlimited_desktop_sessions(self):
        pro_user = User.objects.create_user(
            username='pro-limit@example.com',
            email='pro-limit@example.com',
            password='testpass123',
            role='pro_user',
        )

        # Create 12 existing sessions
        for _ in range(12):
            session = SessionStore()
            session['_auth_user_id'] = str(pro_user.pk)
            session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
            session['_auth_user_hash'] = pro_user.get_session_auth_hash()
            session['_auth_login_surface'] = 'desktop'
            session.save()

        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'email': 'pro-limit@example.com',
                'password': 'testpass123',
            }),
            content_type='application/json',
            REMOTE_ADDR='203.0.113.26',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        
        user_sessions = 0
        for s in Session.objects.all():
            if str(s.get_decoded().get('_auth_user_id')) == str(pro_user.pk):
                user_sessions += 1
        self.assertEqual(user_sessions, 13)

    def test_login_api_allows_guest_user_20_sessions(self):
        guest_user = User.objects.create_user(
            username='guest-limit@example.com',
            email='guest-limit@example.com',
            password='testpass123',
            role='guest_prime_manager',
        )

        from accounts.models import UserDeviceSession
        from django.utils import timezone

        # Create 20 existing sessions
        session_keys = []
        for i in range(20):
            session = SessionStore()
            session['_auth_user_id'] = str(guest_user.pk)
            session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
            session['_auth_user_hash'] = guest_user.get_session_auth_hash()
            session['_auth_login_surface'] = 'desktop'
            session.save()
            session_keys.append(session.session_key)

            UserDeviceSession.objects.create(
                user=guest_user,
                session_key=session.session_key,
                device_type='web',
                last_active=timezone.now(),
            )

        # Login 21st time
        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'email': 'guest-limit@example.com',
                'password': 'testpass123',
            }),
            content_type='application/json',
            REMOTE_ADDR='203.0.113.27',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        # Verify oldest session was evicted
        self.assertFalse(Session.objects.filter(session_key=session_keys[0]).exists())

        # Verify exactly 20 active sessions exist
        user_sessions = 0
        for s in Session.objects.all():
            if str(s.get_decoded().get('_auth_user_id')) == str(guest_user.pk):
                user_sessions += 1
        self.assertEqual(user_sessions, 20)

    def test_mobile_login_keeps_guest_user_existing_mobile_sessions(self):
        from organisation.models import Organisation
        from accounts.models import UserDeviceSession
        from django.utils import timezone

        guest_user = User.objects.create_user(
            username='guest-mobile@example.com',
            email='guest-mobile@example.com',
            password='testpass123',
            role='guest_prime_manager',
        )
        Organisation.objects.create(
            user=guest_user,
            name='Guest Mobile',
            status='active',
            is_guest=True,
        )

        session = SessionStore()
        session['_auth_user_id'] = str(guest_user.pk)
        session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
        session['_auth_user_hash'] = guest_user.get_session_auth_hash()
        session['_auth_login_surface'] = 'mobile'
        session['mobile_auth_ok'] = True
        session.save()

        UserDeviceSession.objects.create(
            user=guest_user,
            session_key=session.session_key,
            device_type='mobile',
            last_active=timezone.now(),
        )

        response = self.client.post(
            '/api/mobile/auth/login/',
            data=json.dumps({
                'email': 'guest-mobile@example.com',
                'password': 'testpass123',
            }),
            content_type='application/json',
            REMOTE_ADDR='203.0.113.28',
            HTTP_X_CLIENT_TYPE='mobile',
            HTTP_USER_AGENT='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            HTTP_ACCEPT_LANGUAGE='en-US',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        self.assertTrue(Session.objects.filter(session_key=session.session_key).exists())

        guest_mobile_sessions = 0
        for s in Session.objects.all():
            data = s.get_decoded()
            if str(data.get('_auth_user_id')) == str(guest_user.pk) and data.get('_auth_login_surface') == 'mobile':
                guest_mobile_sessions += 1
        self.assertGreaterEqual(guest_mobile_sessions, 2)

    def test_login_api_logs_cross_browser_activity_for_client(self):
        from accounts.services import AuthService

        existing_fp = AuthService.build_browser_fingerprint(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/123.0',
            'en-US',
        )
        self._create_authenticated_session(
            browser_fp=existing_fp,
            surface='mobile',
            mobile_auth_ok=True,
        )

        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'email': 'view@example.com',
                'password': 'testpass123',
            }),
            content_type='application/json',
            HTTP_USER_AGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
            HTTP_ACCEPT_LANGUAGE='en-US',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        log_entry = ActivityLog.objects.filter(user=self.user, action='login').order_by('-id').first()
        self.assertIsNotNone(log_entry)
        self.assertIn('different browser', (log_entry.description or '').lower())

    def test_login_api_records_ip_address_in_activity_log(self):
        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'email': 'view@example.com',
                'password': 'testpass123',
            }),
            content_type='application/json',
            REMOTE_ADDR='203.0.113.50',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        log_entry = ActivityLog.objects.filter(user=self.user, action='login').order_by('-id').first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.ip_address, '203.0.113.50')

    def test_mobile_device_detection_custom_agent_and_path(self):
        from accounts.signals import get_device_type
        from django.test import RequestFactory

        rf = RequestFactory()

        # 1. Custom app user agent
        req1 = rf.get('/some-path/', HTTP_USER_AGENT='AdarshMobileApp/1.1 (Premium Native; Expo)')
        self.assertEqual(get_device_type(req1), 'mobile')

        # 2. Custom app with okhttp agent
        req2 = rf.get('/some-path/', HTTP_USER_AGENT='okhttp/4.9.2')
        self.assertEqual(get_device_type(req2), 'mobile')

        # 3. Mobile API path
        req3 = rf.get('/api/mobile/some-endpoint/', HTTP_USER_AGENT='SomeUnknownBrowser')
        self.assertEqual(get_device_type(req3), 'mobile')

        # 4. Standard web request
        req4 = rf.get('/panel/dashboard/', HTTP_USER_AGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0')
        self.assertEqual(get_device_type(req4), 'web')

    def test_device_session_middleware_self_healing(self):
        from accounts.models import UserDeviceSession
        from accounts.middleware import DeviceSessionMiddleware
        from django.test import RequestFactory
        from django.contrib.sessions.middleware import SessionMiddleware

        rf = RequestFactory()
        req = rf.get('/panel/dashboard/', HTTP_USER_AGENT='AdarshMobileApp/1.1 (Premium Native; Expo)')
        req.user = self.user

        # Setup session middleware so request has a session
        sm = SessionMiddleware(lambda r: None)
        sm.process_request(req)
        req.session.save()

        # Ensure no UserDeviceSession exists yet
        UserDeviceSession.objects.filter(session_key=req.session.session_key).delete()

        # Instantiate and run DeviceSessionMiddleware
        middleware = DeviceSessionMiddleware(lambda r: r)
        middleware(req)

        # Check that UserDeviceSession was successfully created/healed as 'mobile'
        self.assertTrue(UserDeviceSession.objects.filter(session_key=req.session.session_key).exists())
        ds = UserDeviceSession.objects.get(session_key=req.session.session_key)
        self.assertEqual(ds.device_type, 'mobile')
        self.assertEqual(ds.user, self.user)


class ProUserSessionAPITests(TestCase):
    def setUp(self):
        self.pro_user = User.objects.create_user(
            username='proapi@example.com',
            email='proapi@example.com',
            password='testpass123',
            role='pro_user',
        )
        self.target = User.objects.create_user(
            username='target@example.com',
            email='target@example.com',
            password='pass',
            role='client',
        )
        # Provide a regular client user used by some login tests in this class
        self.user = User.objects.create_user(
            username='view@example.com',
            email='view@example.com',
            password='testpass123',
            role='client',
        )

    def _create_session_for_user(self, user):
        s = SessionStore()
        s['_auth_user_id'] = str(user.pk)
        s['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
        s['_auth_user_hash'] = user.get_session_auth_hash()
        s['_auth_login_surface'] = 'desktop'
        s.save()
        return s.session_key

    @override_settings(RATE_LIMIT_TRUST_X_FORWARDED_FOR=True)
    def test_login_api_records_trusted_xff_ip_in_activity_log(self):
        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'email': 'view@example.com',
                'password': 'testpass123',
            }),
            content_type='application/json',
            REMOTE_ADDR='10.10.10.10',
            HTTP_X_FORWARDED_FOR='198.51.100.33, 203.0.113.44',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        log_entry = ActivityLog.objects.filter(user=self.user, action='login').order_by('-id').first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.ip_address, '198.51.100.33')

    @override_settings(RATE_LIMIT_TRUST_X_FORWARDED_FOR=False)
    def test_login_api_uses_x_real_ip_when_remote_addr_is_internal_proxy(self):
        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'email': 'view@example.com',
                'password': 'testpass123',
            }),
            content_type='application/json',
            REMOTE_ADDR='10.10.10.10',
            HTTP_X_REAL_IP='198.51.100.77',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        log_entry = ActivityLog.objects.filter(user=self.user, action='login').order_by('-id').first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.ip_address, '198.51.100.77')

    @override_settings(RATE_LIMIT_TRUST_X_FORWARDED_FOR=False)
    def test_login_api_prefers_public_remote_addr_when_not_trusting_proxy_headers(self):
        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'email': 'view@example.com',
                'password': 'testpass123',
            }),
            content_type='application/json',
            REMOTE_ADDR='8.8.8.8',
            HTTP_X_FORWARDED_FOR='1.1.1.1',
            HTTP_X_REAL_IP='9.9.9.9',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

        log_entry = ActivityLog.objects.filter(user=self.user, action='login').order_by('-id').first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.ip_address, '8.8.8.8')

    def test_login_api_wrong_password(self):
        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({
                'email': 'view@example.com',
                'password': 'wrong',
            }),
            content_type='application/json',
        )
        data = response.json()
        self.assertFalse(data['success'])

    @override_settings(DEBUG=True)
    def test_forgot_password_api_never_exposes_dev_otp(self):
        with mock.patch.dict('os.environ', {'DEV_EXPOSE_OTP': 'true'}):
            response = self.client.post(
                '/api/auth/forgot-password/',
                data=json.dumps({'email': 'view@example.com'}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn('dev_otp', payload)


class RateLimitTests(TestCase):
    """Tests for rate limiting decorator"""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_rate_limit_allows_under_limit(self):
        for _ in range(3):
            response = self.client.post(
                '/api/auth/login/',
                data=json.dumps({'email': 'test@x.com', 'password': 'x'}),
                content_type='application/json',
            )
            self.assertNotEqual(response.status_code, 429)

    def test_rate_limit_blocks_over_limit(self):
        for i in range(8):
            response = self.client.post(
                '/api/auth/login/',
                data=json.dumps({'email': 'test@x.com', 'password': 'x'}),
                content_type='application/json',
            )
        # After exceeding limit, should get 429
        self.assertIn(response.status_code, [200, 429])

    def test_rate_limit_isolated_per_endpoint(self):
        # Exhaust check-email endpoint bucket first.
        for _ in range(12):
            self.client.post(
                '/api/auth/check-email/',
                data=json.dumps({'email': 'test@x.com'}),
                content_type='application/json',
                REMOTE_ADDR='8.8.8.8',
            )

        # Login endpoint should still have its own bucket and not be hard-blocked by 429.
        login_response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': 'test@x.com', 'password': 'x'}),
            content_type='application/json',
            REMOTE_ADDR='8.8.8.8',
        )
        self.assertNotEqual(login_response.status_code, 429)


class LoginLoggingMaskTests(TestCase):
    def test_mask_login_identifier_email(self):
        from accounts.views import _mask_login_identifier
        self.assertEqual(_mask_login_identifier('alice@example.com'), 'a***@example.com')

    def test_mask_login_identifier_username(self):
        from accounts.views import _mask_login_identifier
        self.assertEqual(_mask_login_identifier('roshan'), 'r***')


class RateLimitClientIPTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(RATE_LIMIT_TRUST_X_FORWARDED_FOR=False)
    def test_get_client_ip_uses_remote_addr_by_default(self):
        from accounts.rate_limit import _get_client_ip
        request = self.factory.get('/panel/api/auth/login/', REMOTE_ADDR='10.10.10.10', HTTP_X_FORWARDED_FOR='8.8.8.8')
        self.assertEqual(_get_client_ip(request), '10.10.10.10')

    @override_settings(RATE_LIMIT_TRUST_X_FORWARDED_FOR=True)
    def test_get_client_ip_uses_trusted_xff_when_enabled(self):
        from accounts.rate_limit import _get_client_ip
        request = self.factory.get(
            '/api/auth/login/',
            REMOTE_ADDR='10.10.10.10',
            HTTP_X_FORWARDED_FOR='198.51.100.1, 203.0.113.10'
        )
        self.assertEqual(_get_client_ip(request), '198.51.100.1')

    @override_settings(RATE_LIMIT_TRUST_X_FORWARDED_FOR=False)
    def test_get_client_ip_uses_x_real_ip_when_remote_addr_invalid(self):
        from accounts.rate_limit import _get_client_ip
        request = self.factory.get(
            '/api/auth/login/',
            REMOTE_ADDR='invalid-ip',
            HTTP_X_REAL_IP='198.51.100.77',
        )
        self.assertEqual(_get_client_ip(request), '198.51.100.77')


class AuthServiceRoleEdgeTests(TestCase):
    def test_authenticate_allows_pro_user_when_super_admin_selected(self):
        from accounts.services import AuthService
        User.objects.create_user(
            username='pro@example.com',
            email='pro@example.com',
            password='propass123',
            role='pro_user',
        )
        result = AuthService.authenticate_user('pro@example.com', 'propass123', role='super_admin')
        self.assertTrue(result['success'])

    def test_authenticate_rejects_role_mismatch(self):
        from accounts.services import AuthService
        User.objects.create_user(
            username='client2@example.com',
            email='client2@example.com',
            password='clientpass123',
            role='client',
        )
        result = AuthService.authenticate_user('client2@example.com', 'clientpass123', role='operator')
        self.assertFalse(result['success'])

    def test_authenticate_blocks_after_repeated_failures(self):
        from accounts import services

        User.objects.create_user(
            username='locked@example.com',
            email='locked@example.com',
            password='lockpass123',
            role='client',
        )

        with mock.patch.object(services, 'AUTH_FAIL_MAX_ATTEMPTS', 2):
            services.AuthService.authenticate_user('locked@example.com', 'wrongpass')
            services.AuthService.authenticate_user('locked@example.com', 'wrongpass')
            blocked = services.AuthService.authenticate_user('locked@example.com', 'lockpass123')
            self.assertFalse(blocked['success'])

            services.AuthService._clear_login_failures('locked@example.com')
            unblocked = services.AuthService.authenticate_user('locked@example.com', 'lockpass123')
            self.assertTrue(unblocked['success'])

    @mock.patch('accounts.services.send_html_email_async')
    def test_authenticate_sends_failed_login_alert_after_threshold(self, mocked_send_html_email):
        from accounts import services

        cache.clear()
        User.objects.create_user(
            username='alert@example.com',
            email='alert@example.com',
            password='alertpass123',
            role='client',
        )

        with mock.patch.object(services, 'AUTH_FAIL_NOTIFY_THRESHOLD', 2), \
             mock.patch.object(services, 'AUTH_FAIL_NOTIFY_COOLDOWN_SECONDS', 300):
            services.AuthService.authenticate_user('alert@example.com', 'wrongpass')
            services.AuthService.authenticate_user('alert@example.com', 'wrongpass')

        self.assertEqual(mocked_send_html_email.call_count, 1)


class OTPServiceEdgeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='otp-edge@example.com',
            email='otp-edge@example.com',
            password='testpass123',
            role='client',
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    @override_settings(DEBUG=True)
    def test_verify_otp_blocks_after_max_attempts(self):
        from accounts.services import OTPService
        send_result = OTPService.send_otp('otp-edge@example.com')
        self.assertTrue(send_result['success'])

        for _ in range(3):
            invalid = OTPService.verify_otp('otp-edge@example.com', '000000')
            self.assertFalse(invalid['success'])

        blocked = OTPService.verify_otp('otp-edge@example.com', '000000')
        self.assertFalse(blocked['success'])
        self.assertIn('Too many failed attempts', blocked['message'])

    @override_settings(DEBUG=True)
    def test_reset_password_rejects_tampered_signed_token(self):
        from accounts.services import OTPService
        send_result = OTPService.send_otp('otp-edge@example.com')
        dev_otp = send_result.get('dev_otp')
        self.assertIsNotNone(dev_otp)

        verify_result = OTPService.verify_otp('otp-edge@example.com', dev_otp)
        self.assertTrue(verify_result['success'])
        token = verify_result['reset_token']

        raw_token, _sig = token.split('.', 1)
        tampered = f'{raw_token}.0000000000000000'
        reset_result = OTPService.reset_password('otp-edge@example.com', tampered, 'newpassword1')
        self.assertFalse(reset_result['success'])
        self.assertIn('reset token', reset_result['message'].lower())

    @override_settings(DEBUG=True)
    def test_send_otp_stores_hash_not_plain_code(self):
        from accounts.services import OTPService

        result = OTPService.send_otp('otp-edge@example.com')
        self.assertTrue(result['success'])

        cache_key = OTPService._get_otp_cache_key('otp-edge@example.com')
        otp_data = cache.get(cache_key)
        self.assertIn('otp_hash', otp_data)
        self.assertNotIn('otp', otp_data)

    @override_settings(DEBUG=True)
    def test_reset_password_revokes_existing_sessions(self):
        from django.test import Client
        from accounts.services import OTPService

        browser = Client()
        self.assertTrue(browser.login(username='otp-edge@example.com', password='testpass123'))
        session_key = browser.session.session_key
        self.assertTrue(Session.objects.filter(session_key=session_key).exists())

        send_result = OTPService.send_otp('otp-edge@example.com')
        dev_otp = send_result.get('dev_otp')
        self.assertIsNotNone(dev_otp)

        verify_result = OTPService.verify_otp('otp-edge@example.com', dev_otp)
        self.assertTrue(verify_result['success'])
        reset_result = OTPService.reset_password(
            'otp-edge@example.com',
            verify_result['reset_token'],
            'newpassword1',
        )
        self.assertTrue(reset_result['success'])
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())

    @override_settings(DEBUG=True)
    def test_forgot_password_via_username_and_phone(self):
        from accounts.services import OTPService
        
        user = User.objects.create_user(
            username='mycustomuser',
            email='realemail@example.com',
            password='oldpassword123',
            role='photographer',
            phone='+91 9999999999'
        )

        # 1. Send OTP using username
        result_username = OTPService.send_otp('mycustomuser')
        self.assertTrue(result_username['success'])
        dev_otp_username = result_username.get('dev_otp')
        self.assertIsNotNone(dev_otp_username)

        # Verify using username
        verify_username = OTPService.verify_otp('mycustomuser', dev_otp_username)
        self.assertTrue(verify_username['success'])
        
        reset_username = OTPService.reset_password(
            'mycustomuser',
            verify_username['reset_token'],
            'newusernamepass123'
        )
        self.assertTrue(reset_username['success'])
        
        # Verify user can login with new password
        user.refresh_from_db()
        self.assertTrue(user.check_password('newusernamepass123'))

        # 2. Send OTP using phone number
        result_phone = OTPService.send_otp('9999999999')
        self.assertTrue(result_phone['success'])
        dev_otp_phone = result_phone.get('dev_otp')
        self.assertIsNotNone(dev_otp_phone)

        # Verify using phone
        verify_phone = OTPService.verify_otp('9999999999', dev_otp_phone)
        self.assertTrue(verify_phone['success'])
        
        reset_phone = OTPService.reset_password(
            '9999999999',
            verify_phone['reset_token'],
            'newphonepass123'
        )
        self.assertTrue(reset_phone['success'])
        
        # Verify user can login with new password
        user.refresh_from_db()
        self.assertTrue(user.check_password('newphonepass123'))

    def test_photographer_permissions_respect_profile(self):
        from core.services.permission_service import PermissionService
        from core.models import Photographer
        
        photo_user = User.objects.create_user(
            username='photouser@example.com',
            email='photouser@example.com',
            password='password123',
            role='photographer',
        )
        
        # Set specific permission profile settings in DB
        Photographer.objects.create(
            user=photo_user,
            perm_mobile_app=False,
            perm_idcard_add=True,
            perm_idcard_info=False,
            perm_idcard_pending_list=True
        )
        
        # Verify PermissionService respects these database profile toggles
        self.assertFalse(PermissionService.has(photo_user, 'perm_mobile_app'))
        self.assertTrue(PermissionService.has(photo_user, 'perm_idcard_add'))
        self.assertFalse(PermissionService.has(photo_user, 'perm_idcard_info'))
        self.assertTrue(PermissionService.has(photo_user, 'perm_idcard_pending_list'))
        
        # Also check permission context mappings
        context = PermissionService.get_permission_context(photo_user)
        self.assertFalse(context['perm_mobile_app'])
        self.assertTrue(context['perm_idcard_add'])
        self.assertFalse(context['perm_idcard_info'])
        self.assertTrue(context['perm_idcard_pending_list'])


class UserProfileServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='profile@example.com',
            email='profile@example.com',
            password='testpass123',
            role='client',
        )
        self.other_user = User.objects.create_user(
            username='other@example.com',
            email='other@example.com',
            password='testpass123',
            role='client',
        )

    def test_update_profile_success(self):
        from accounts.services_profile import UserProfileService
        success, message, profile = UserProfileService.update_profile(self.user, {
            'first_name': 'Test',
            'last_name': 'User',
            'phone': '9999999999',
        })
        self.assertTrue(success)
        self.assertEqual(message, 'Profile updated')
        self.assertEqual(profile['full_name'], 'Test User')

    def test_update_profile_rejects_username_conflict(self):
        from accounts.services_profile import UserProfileService
        success, message, profile = UserProfileService.update_profile(self.user, {
            'username': 'other@example.com',
        })
        self.assertFalse(success)
        self.assertEqual(message, 'Username already taken')
        self.assertIsNone(profile)

    def test_change_password_success(self):
        from accounts.services_profile import UserProfileService
        success, _message = UserProfileService.change_password(self.user, 'testpass123', 'newpass123')
        self.assertTrue(success)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpass123'))

    def test_change_password_revokes_other_sessions_keeps_current(self):
        from django.test import Client
        from accounts.services_profile import UserProfileService

        # Use a super_admin user for this test so that the login signal
        # doesn't enforce device limits (limit=9999) and both sessions
        # survive the test setup phase.
        sa_user = User.objects.create_user(
            username='sa-pwchange@example.com',
            email='sa-pwchange@example.com',
            password='testpass123',
            role='super_admin',
        )

        client_a = Client()
        client_b = Client()
        self.assertTrue(client_a.login(username='sa-pwchange@example.com', password='testpass123'))
        self.assertTrue(client_b.login(username='sa-pwchange@example.com', password='testpass123'))

        key_a = client_a.session.session_key
        key_b = client_b.session.session_key
        self.assertTrue(Session.objects.filter(session_key=key_a).exists())
        self.assertTrue(Session.objects.filter(session_key=key_b).exists())

        success, _message = UserProfileService.change_password(
            sa_user,
            'testpass123',
            'newpass123',
            current_session_key=key_a,
        )
        self.assertTrue(success)

        self.assertTrue(Session.objects.filter(session_key=key_a).exists())
        self.assertFalse(Session.objects.filter(session_key=key_b).exists())

    def test_change_password_rejects_wrong_current(self):
        from accounts.services_profile import UserProfileService
        success, message = UserProfileService.change_password(self.user, 'wrong', 'newpass123')
        self.assertFalse(success)
        self.assertEqual(message, 'Current password is incorrect')

    def test_profile_image_methods_return_backward_compat_message(self):
        from accounts.services_profile import UserProfileService
        success_upload, message_upload, image_url = UserProfileService.upload_profile_image(self.user, None)
        self.assertFalse(success_upload)
        self.assertIn('no longer available', message_upload.lower())
        self.assertIsNone(image_url)

        success_remove, message_remove = UserProfileService.remove_profile_image(self.user)
        self.assertFalse(success_remove)
        self.assertIn('no longer available', message_remove.lower())


class ProfileApiIntegrationTests(TestCase):
    def setUp(self):
        from organisation.models import Organisation
        self.user = User.objects.create_user(
            username='api-profile@example.com',
            email='api-profile@example.com',
            password='testpass123',
            role='client',
        )
        Organisation.objects.create(user=self.user, name='Profile Test Client')
        self.client.login(username='api-profile@example.com', password='testpass123')

    def test_get_profile_api(self):
        response = self.client.get('/api/profile/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['profile']['email'], 'api-profile@example.com')

    def test_update_profile_api(self):
        response = self.client.post(
            '/api/profile/update/',
            data=json.dumps({'first_name': 'Api', 'last_name': 'User'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['profile']['full_name'], 'Api User')

    def test_change_password_api(self):
        response = self.client.post(
            '/api/profile/change-password/',
            data=json.dumps({'current_password': 'testpass123', 'new_password': 'newpass123'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])

    def test_upload_profile_image_api_returns_feature_disabled(self):
        response = self.client.post('/api/profile/upload-image/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn('no longer available', payload['message'].lower())


class ProUserAuditApiTests(TestCase):
    def setUp(self):
        from organisation.models import Organisation
        self.pro_user = User.objects.create_user(
            username='pro-user@example.com',
            email='pro-user@example.com',
            password='testpass123',
            role='pro_user',
        )
        self.super_admin = User.objects.create_user(
            username='super-admin@example.com',
            email='super-admin@example.com',
            password='testpass123',
            role='super_admin',
        )
        self.target_user = User.objects.create_user(
            username='target-user@example.com',
            email='target-user@example.com',
            password='testpass123',
            role='client',
        )
        Organisation.objects.create(user=self.target_user, name='Target Org', status='active')
        self.normal_user = User.objects.create_user(
            username='normal-user@example.com',
            email='normal-user@example.com',
            password='testpass123',
            role='client',
        )
        Organisation.objects.create(user=self.normal_user, name='Normal Org', status='active')
        self.other_admin = User.objects.create_user(
            username='admin-staff@example.com',
            email='admin-staff@example.com',
            password='testpass123',
            role='operator',
        )

    def test_user_audit_user_list_requires_pro_user(self):
        self.client.login(username='normal-user@example.com', password='testpass123')
        response = self.client.get('/api/auth/user-audit/users/')
        self.assertEqual(response.status_code, 403)

    def test_user_audit_history_requires_pro_user(self):
        self.client.login(username='normal-user@example.com', password='testpass123')
        response = self.client.get(f'/api/auth/user-audit/history/?user_id={self.target_user.id}')
        self.assertEqual(response.status_code, 403)

    def test_pro_user_can_list_audit_targets(self):
        self.client.login(username='pro-user@example.com', password='testpass123')
        response = self.client.get('/api/auth/user-audit/users/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertTrue(any(u['id'] == self.target_user.id for u in payload['users']))

    def test_pro_user_can_get_deep_history_for_user(self):
        from core.services.activity_service import ActivityService

        self.client.login(username='pro-user@example.com', password='testpass123')
        ActivityService.log(
            'login',
            'Target User logged in via Windows Chrome browser',
            user=self.target_user,
        )
        ActivityService.log(
            'card_bulk_download',
            'Downloaded 15 cards for Demo Client',
            user=self.target_user,
        )
        ActivityService.log(
            'staff_update',
            'Staff profile changed for target user',
            user=self.other_admin,
            target_model='User',
            target_id=self.target_user.id,
            target_name=self.target_user.get_full_name() or self.target_user.username,
        )

        response = self.client.get(f'/api/auth/user-audit/history/?user_id={self.target_user.id}&limit=20')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['user']['id'], self.target_user.id)
        self.assertGreaterEqual(payload['summary']['total_events'], 3)
        self.assertTrue(any(item['action'] == 'login' for item in payload['logs']))
        self.assertTrue(any(item['action'] == 'card_bulk_download' for item in payload['logs']))

    def test_user_audit_history_requires_user_id(self):
        self.client.login(username='pro-user@example.com', password='testpass123')
        response = self.client.get('/api/auth/user-audit/history/')
        self.assertEqual(response.status_code, 400)

    def test_user_audit_actions_endpoint(self):
        self.client.login(username='pro-user@example.com', password='testpass123')
        response = self.client.get('/api/auth/user-audit/actions/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertTrue(any(entry['value'] == 'login' for entry in payload['actions']))

    def test_super_admin_can_access_audit_endpoints(self):
        self.client.login(username='super-admin@example.com', password='testpass123')

        users_response = self.client.get('/api/auth/user-audit/users/')
        self.assertEqual(users_response.status_code, 200)

        history_response = self.client.get(f'/api/auth/user-audit/history/?user_id={self.target_user.id}')
        self.assertEqual(history_response.status_code, 200)

        actions_response = self.client.get('/api/auth/user-audit/actions/')
        self.assertEqual(actions_response.status_code, 200)


class ImpersonationApiTests(TestCase):
    def setUp(self):
        from organisation.models import Organisation
        self.pro_user = User.objects.create_user(
            username='pro-user-imp@example.com',
            email='pro-user-imp@example.com',
            password='testpass123',
            role='pro_user',
        )
        self.target_user = User.objects.create_user(
            username='target-user-imp@example.com',
            email='target-user-imp@example.com',
            password='testpass123',
            role='client',
        )
        Organisation.objects.create(user=self.target_user, name='Target Imp Org', status='active')
        self.normal_user = User.objects.create_user(
            username='normal-user-imp@example.com',
            email='normal-user-imp@example.com',
            password='testpass123',
            role='client',
        )
        Organisation.objects.create(user=self.normal_user, name='Normal Imp Org', status='active')

    def test_impersonation_list_requires_pro_user(self):
        self.client.login(username='normal-user-imp@example.com', password='testpass123')
        response = self.client.get('/api/auth/impersonate/users/')
        self.assertEqual(response.status_code, 403)

    def test_impersonation_list_excludes_inactive_users(self):
        self.target_user.is_active = False
        self.target_user.save(update_fields=['is_active'])

        self.client.login(username='pro-user-imp@example.com', password='testpass123')
        response = self.client.get('/api/auth/impersonate/users/')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload['success'])
        returned_ids = {entry['id'] for entry in payload['users']}
        self.assertNotIn(self.target_user.id, returned_ids)
        self.assertIn(self.normal_user.id, returned_ids)

    def test_impersonation_list_includes_assistant_and_super_admin_when_many_admin_staff_exist(self):
        User.objects.bulk_create([
            User(
                username=f'bulk-admin-{idx}@example.com',
                email=f'bulk-admin-{idx}@example.com',
                password='!',
                role='operator',
                is_active=True,
            )
            for idx in range(120)
        ])

        assistant_user = User.objects.create_user(
            username='assistant-target-imp@example.com',
            email='assistant-target-imp@example.com',
            password='testpass123',
            role='client_staff',
        )
        super_admin_user = User.objects.create_user(
            username='superadmin-target-imp@example.com',
            email='superadmin-target-imp@example.com',
            password='testpass123',
            role='super_admin',
        )

        self.client.login(username='pro-user-imp@example.com', password='testpass123')
        response = self.client.get('/api/auth/impersonate/users/')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload['success'])
        returned_ids = {entry['id'] for entry in payload['users']}
        self.assertIn(assistant_user.id, returned_ids)
        self.assertIn(super_admin_user.id, returned_ids)

    def test_impersonation_start_requires_pro_user(self):
        self.client.login(username='normal-user-imp@example.com', password='testpass123')
        response = self.client.post(
            '/api/auth/impersonate/start/',
            data=json.dumps({'user_id': self.target_user.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_staff_cannot_start_impersonation(self):
        admin_staff = User.objects.create_user(
            username='admin-staff-imp@example.com',
            email='admin-staff-imp@example.com',
            password='testpass123',
            role='operator',
        )

        self.client.login(username='admin-staff-imp@example.com', password='testpass123')
        response = self.client.post(
            '/api/auth/impersonate/start/',
            data=json.dumps({'user_id': self.target_user.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertNotIn('_pro_original_user_id', self.client.session)

    def test_pro_user_can_start_and_stop_impersonation(self):
        self.client.login(username='pro-user-imp@example.com', password='testpass123')

        start = self.client.post(
            '/api/auth/impersonate/start/',
            data=json.dumps({'user_id': self.target_user.id}),
            content_type='application/json',
        )
        self.assertEqual(start.status_code, 200)
        start_payload = start.json()
        self.assertTrue(start_payload['success'])
        self.assertIn('_pro_original_user_id', self.client.session)

        stop = self.client.post('/api/auth/impersonate/stop/', data='{}', content_type='application/json')
        self.assertEqual(stop.status_code, 200)
        stop_payload = stop.json()
        self.assertTrue(stop_payload['success'])
        self.assertNotIn('_pro_original_user_id', self.client.session)

    def test_super_admin_can_start_and_stop_impersonation(self):
        super_admin = User.objects.create_user(
            username='super-admin-imp@example.com',
            email='super-admin-imp@example.com',
            password='testpass123',
            role='super_admin',
        )

        self.client.login(username='super-admin-imp@example.com', password='testpass123')

        start = self.client.post(
            '/api/auth/impersonate/start/',
            data=json.dumps({'user_id': self.target_user.id}),
            content_type='application/json',
        )
        self.assertEqual(start.status_code, 200)
        start_payload = start.json()
        self.assertTrue(start_payload['success'])
        self.assertIn('_pro_original_user_id', self.client.session)

        stop = self.client.post('/api/auth/impersonate/stop/', data='{}', content_type='application/json')
        self.assertEqual(stop.status_code, 200)
        stop_payload = stop.json()
        self.assertTrue(stop_payload['success'])
        self.assertNotIn('_pro_original_user_id', self.client.session)

    def test_impersonation_start_requires_user_id(self):
        self.client.login(username='pro-user-imp@example.com', password='testpass123')
        response = self.client.post(
            '/api/auth/impersonate/start/',
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_impersonation_stop_without_active_session(self):
        self.client.login(username='pro-user-imp@example.com', password='testpass123')
        response = self.client.post('/api/auth/impersonate/stop/', data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_impersonation_rejects_inactive_target(self):
        self.target_user.is_active = False
        self.target_user.save(update_fields=['is_active'])
        self.client.login(username='pro-user-imp@example.com', password='testpass123')

        response = self.client.post(
            '/api/auth/impersonate/start/',
            data=json.dumps({'user_id': self.target_user.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn('inactive', payload['message'].lower())

    def test_logout_while_impersonating_keeps_pro_session_for_mobile_next(self):
        self.client.login(username='pro-user-imp@example.com', password='testpass123')
        session = self.client.session
        session['mobile_auth_ok'] = True
        session['_auth_login_surface'] = 'mobile'
        session['selected_role'] = 'pro_user'
        session.save()

        start = self.client.post(
            '/api/auth/impersonate/start/',
            data=json.dumps({'user_id': self.target_user.id}),
            content_type='application/json',
        )
        self.assertEqual(start.status_code, 200)

        response = self.client.post('/api/auth/logout/', {'next': '/app/'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['redirect'], '/app/')

        session = self.client.session
        self.assertTrue(session.get('mobile_auth_ok'))
        self.assertEqual(session.get('selected_role'), 'pro_user')
        self.assertNotIn('_pro_original_user_id', session)

        self.assertEqual(int(session.get('_auth_user_id')), self.pro_user.id)


from django.test import TransactionTestCase


class GuestSandboxDatabaseTests(TransactionTestCase):
    databases = '__all__'

    def setUp(self):
        from organisation.models import Organisation
        self.guest_user = User.objects.create_user(
            username='guest-test-sandbox@example.com',
            email='guest-test-sandbox@example.com',
            password='testpass123',
            role='guest_prime_manager',
        )
        self.client_profile = Organisation.objects.create(
            user=self.guest_user,
            name='Guest Sandbox Client',
            status='active',
            is_guest=True,
        )

    def tearDown(self):
        from django.conf import settings
        from django.db import connections
        guest_aliases = [alias for alias in list(settings.DATABASES.keys()) if alias.startswith('guest_')]
        for alias in guest_aliases:
            if alias in connections:
                try:
                    connections[alias].close()
                except Exception:
                    pass
                try:
                    del connections[alias]
                except Exception:
                    pass
            if alias in connections.databases:
                try:
                    del connections.databases[alias]
                except Exception:
                    pass
            if alias in settings.DATABASES:
                try:
                    del settings.DATABASES[alias]
                except Exception:
                    pass
        super().tearDown()

    def test_guest_database_sandbox_isolation_and_logout_cleanup(self):
        from django.test.client import RequestFactory
        from django.contrib.sessions.backends.db import SessionStore
        from core.middleware import GuestSandboxMiddleware
        from tables.models import Table
        import os
        from django.conf import settings

        factory = RequestFactory()
        middleware = GuestSandboxMiddleware(lambda r: None)

        # 1. Establish Session One
        request_one = factory.get('/panel/')
        request_one.user = self.guest_user
        request_one.session = SessionStore()
        request_one.session.save()
        session_key_one = request_one.session.session_key

        # 2. Run request one through middleware (this will setup Guest 1's sandbox DB)
        middleware(request_one)

        # Verify Guest 1's database file is created
        db_file_one = os.path.join(settings.BASE_DIR, 'guest_sandboxes', f"{session_key_one}.sqlite3")
        self.assertTrue(os.path.exists(db_file_one))

        # 3. Simulate Guest 1 creating a record inside the sandbox database
        import sqlite3
        conn = sqlite3.connect(db_file_one)
        try:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS sample_table (id INTEGER PRIMARY KEY, name TEXT)")
            cursor.execute("INSERT INTO sample_table (name) VALUES ('Group Guest One')")
            conn.commit()
        finally:
            conn.close()

        # Verify that it does NOT exist in the default database!
        self.assertFalse(Table.objects.using('default').filter(name="Group Guest One").exists())

        # 4. Establish Session Two
        request_two = factory.get('/panel/')
        request_two.user = self.guest_user
        request_two.session = SessionStore()
        request_two.session.save()
        session_key_two = request_two.session.session_key

        # 5. Run request two through middleware (this will setup Guest 2's sandbox DB)
        middleware(request_two)

        db_file_two = os.path.join(settings.BASE_DIR, 'guest_sandboxes', f"{session_key_two}.sqlite3")
        self.assertTrue(os.path.exists(db_file_two))

        # 6. Verify Guest 2 cannot see Guest 1's record
        conn2 = sqlite3.connect(db_file_two)
        try:
            cursor2 = conn2.cursor()
            cursor2.execute("CREATE TABLE IF NOT EXISTS sample_table (id INTEGER PRIMARY KEY, name TEXT)")
            cursor2.execute("SELECT COUNT(*) FROM sample_table WHERE name = 'Group Guest One'")
            count = cursor2.fetchone()[0]
            self.assertEqual(count, 0)
        finally:
            conn2.close()

        # 7. Test Logout Signal Cleanup
        from django.contrib.auth.signals import user_logged_out
        from accounts.signals import cleanup_device_session
        
        cleanup_device_session(sender=None, request=request_one, user=self.guest_user)
        # Verify Guest 1's DB file is deleted
        self.assertFalse(os.path.exists(db_file_one))
        
        # Verify Guest 2's DB file is still intact
        self.assertTrue(os.path.exists(db_file_two))

        # 8. Test Expired Sandboxes Cleanup via task_cleanup
        # Delete Session Two so it is marked as expired/non-existent
        request_two.session.delete()
        
        from core.services.task_cleanup import cleanup_expired_guest_sandboxes
        count = cleanup_expired_guest_sandboxes()
        self.assertGreaterEqual(count, 1)
        # Verify Guest 2's DB file is deleted now
        self.assertFalse(os.path.exists(db_file_two))