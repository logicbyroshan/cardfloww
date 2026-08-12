"""
Accounts Views Module

API views and page views for authentication flow.
"""
import json
import logging
import os
import re
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth import login, logout
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.timezone import localtime
from django.utils.timesince import timesince
from django.db.models import Q, Count, Max
from core.models import ActivityLog
from core.services.activity_service import ActivityService
from core.services.permission_service import PermissionService
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

from .services import AuthService, OTPService, RoleService, DASHBOARD_URLS
from .rate_limit import rate_limit, _get_client_ip

logger = logging.getLogger(__name__)
User = get_user_model()


def _mask_login_identifier(identifier):
    """Mask login identifier before writing to logs."""
    value = str(identifier or '').strip()
    if not value:
        return 'unknown'
    if '@' in value:
        local, domain = value.split('@', 1)
        local_mask = (local[:1] + '***') if local else '***'
        return f'{local_mask}@{domain}'
    return value[:1] + '***'


def _truthy(value):
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


# =============================================================================
# PAGE VIEWS (Template-based)
# =============================================================================

@method_decorator(ensure_csrf_cookie, name='dispatch')
class LoginPageView(View):
    """
    Serve the React SPA shell for the login route.
    @ensure_csrf_cookie ensures the csrftoken cookie is set on GET
    so subsequent AJAX POSTs can read it for the X-CSRFToken header.
    """

    def get(self, request):
        # If user is already authenticated, redirect to dashboard
        if request.user.is_authenticated:
            # Respect ?next= param (e.g. from PWA ÔåÆ login redirect)
            next_url = request.GET.get('next', '')
            # S7: use Django's safe-redirect helper ÔÇö blocks //evil.com, /\evil.com, etc.
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            redirect_url = AuthService.get_dashboard_url(request.user)
            return redirect(redirect_url)

        ua = request.META.get('HTTP_USER_AGENT', '')
        is_mobile_ua = bool(re.search(r'Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini', ua, re.I))
        if is_mobile_ua:
            # Preserve next_url if present so mobile users return to the correct app state
            next_url = request.GET.get('next', '')
            target = '/app/login/?install=1'
            if next_url:
                from urllib.parse import quote
                target += '&next=' + quote(next_url)
            return redirect(target)
        
        return render(request, 'index.html')


@method_decorator(ensure_csrf_cookie, name='dispatch')
class GetCSRFTokenView(View):
    """
    Dedicated endpoint to acquire a fresh CSRF token.
    Useful for PWAs or AJAX-heavy flows that need to recover from expired tokens.
    """
    def get(self, request):
        return JsonResponse({'success': True})


@method_decorator(ensure_csrf_cookie, name='dispatch')
class SecureCredentialVaultView(View):
    """
    Render the React SPA for the Secure Credential Vault page.
    The SPA handles the email prompt and credential reveal flow via POST.
    """

    def get(self, request, token):
        # Serve the SPA shell; the SPA reads ?token= from the URL and handles the vault UI.
        return render(request, 'index.html', {'token': token})
        
    def post(self, request, token):
        try:
            from core.utils.secure_credentials import verify_credential_token
            data = json.loads(request.body)
            email = data.get('email', '').strip()
            
            if not email:
                return JsonResponse({'success': False, 'message': 'Email address is required.'}, status=400)
                
            password = verify_credential_token(token, email)
            
            if not password:
                return JsonResponse({
                    'success': False, 
                    'message': 'Invalid token, incorrect email, or this secure link has already expired.'
                }, status=403)
                
            return JsonResponse({'success': True, 'password': password})
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)
        except Exception as e:
            logger.exception("Secure Vault error: %s", e)
            return JsonResponse({'success': False, 'message': 'An unexpected error occurred.'}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class LogoutView(View):
    """Handle user logout.
    
    CSRF-exempt because logout only destroys the caller's own session.
    This prevents 403 errors when users click 'Logout' with a stale
    CSRF token (the most common user-facing error).
    Django's own LogoutView is also csrf_exempt for the same reason.
    """
    
    def get(self, request):
        # GET requests redirect to login ÔÇö do NOT perform logout on GET
        # (prevents CSRF logout via <img src="/logout/"> attacks)
        return redirect('accounts:login')
    
    def post(self, request):
        from .services_impersonate import ImpersonateService
        # Detect AJAX/fetch requests to return JSON instead of 302
        is_ajax = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
            request.content_type == 'application/json' or
            request.GET.get('format') == 'json'
        )
        next_url = request.POST.get('next', '') or request.GET.get('next', '')

        # If this session is impersonating, stopping logout returns control to Pro User.
        if request.user.is_authenticated and ImpersonateService.is_impersonating(request):
            result = ImpersonateService.stop(request, next_url=next_url)
            if result.get('success'):
                redirect_url = result.get('redirect_url') or '/panel/'
                # Respect safe next URL for mobile surface handoff.
                if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    redirect_url = next_url

                # If we are returning to mobile app after stop-impersonation,
                # keep the mobile auth checkpoint alive for the restored Pro session.
                if redirect_url.startswith('/app/'):
                    request.session['mobile_auth_ok'] = True
                    request.session['_auth_login_surface'] = 'mobile'
                    request.session['_auth_browser_fp'] = AuthService.browser_fingerprint_from_request(request)
                    request.session['selected_role'] = getattr(request.user, 'role', '')

                if is_ajax:
                    return JsonResponse({'success': True, 'redirect': redirect_url})
                return redirect(redirect_url)

        if request.user.is_authenticated:
            # Pro User cannot logout the final active session.
            if getattr(request.user, 'role', '') == 'pro_user':
                active_sessions = AuthService.count_active_sessions_for_user(request.user.id, stop_after=2)
                if active_sessions <= 1:
                    if is_ajax:
                        return JsonResponse({
                            'success': False,
                            'message': 'Pro User must remain logged in on at least one active session.'
                        }, status=400)
                    return redirect('/panel/?pro_logout_blocked=1')

            # Sandbox Cleanup
            if getattr(request.user, 'role', '') == 'guest_user' and request.user.username.startswith('guestclone_'):
                from client.services_sandbox import SandboxService
                SandboxService.cleanup_clone(request.user.id)

            ActivityService.log_logout(request, request.user)
        logout(request)
        # Respect ?next= or POST body next (e.g. from PWA logout)
        # S7: use Django's safe-redirect helper ÔÇö blocks //evil.com, /\evil.com, etc.
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            login_url = reverse('accounts:login') + '?next=' + next_url
            if is_ajax:
                return JsonResponse({'success': True, 'redirect': login_url})
            return redirect(login_url)
        # Redirect back into the panel when no explicit destination is set.
        target_url = reverse('accounts:login')
        if is_ajax:
            return JsonResponse({'success': True, 'redirect': target_url})
        return redirect(target_url)


# =============================================================================
# DASHBOARD VIEWS
# =============================================================================

class BaseDashboardView(LoginRequiredMixin, View):
    """Base dashboard view with login requirement."""
    login_url = '/panel/auth/login/'
    template_name = None
    allowed_roles = []
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(self.login_url)
        
        # Check role access if roles are specified
        if self.allowed_roles and request.user.role not in self.allowed_roles:
            # Redirect to appropriate dashboard
            correct_url = AuthService.get_dashboard_url(request.user)
            return redirect(correct_url)
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self):
        """Get common context data for dashboards."""
        return {
            'user': self.request.user,
            'user_role': RoleService.get_role_display_name(self.request.user.role),
            'dashboard_urls': DASHBOARD_URLS,
            'active_page': 'dashboard',
        }


class StaffDashboardView(BaseDashboardView):
    """DEPRECATED ÔÇö redirects to /panel/."""
    allowed_roles = ['admin_staff']
    def get(self, request):
        return redirect('/panel/')


class ClientAdminDashboardView(BaseDashboardView):
    """DEPRECATED ÔÇö redirects to /panel/client/dashboard/."""
    allowed_roles = ['client']
    def get(self, request):
        return redirect('/panel/client/dashboard/')


class ClientStaffDashboardView(BaseDashboardView):
    """DEPRECATED ÔÇö redirects to /panel/client/dashboard/."""
    allowed_roles = ['client_staff']
    def get(self, request):
        return redirect('/panel/client/dashboard/')


# =============================================================================
# API VIEWS (JSON responses for AJAX calls)
# =============================================================================

@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(rate_limit(max_requests=10, window_seconds=60), name='dispatch')
class CheckEmailAPIView(View):
    """
    API endpoint to check if user email exists.
    POST /api/auth/check-email/
    """
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            identifier = data.get('email', '').strip()
            
            if not identifier:
                return JsonResponse({
                    'success': False,
                    'message': 'Email, username, or phone is required'
                }, status=400)
            
            result = AuthService.check_user_exists(identifier)
            
            return JsonResponse({
                'success': result.get('exists', True),
                'exists': result.get('exists', True),
                'user_name': result.get('user_name', ''),
                'user_email': result.get('user_email', ''),
                'message': result['message']
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            logger.exception("Auth API error: %s", e)
            return JsonResponse({
                'success': False,
                'message': 'An error occurred. Please try again.'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(rate_limit(max_requests=5, window_seconds=60), name='dispatch')
class LoginAPIView(View):
    """
    API endpoint for user login.
    POST /api/auth/login/
    Requires CSRF token for session-based auth security.
    """
    
    def post(self, request):
        identifier = None
        client_ip = _get_client_ip(request)
        try:
            data = json.loads(request.body)
            identifier = data.get('email', '').strip()
            password = data.get('password', '')
            force_logout_other = _truthy(data.get('force_logout_other'))
            
            if not identifier or not password:
                return JsonResponse({
                    'success': False,
                    'message': 'Email/username/phone and password are required'
                }, status=400)
            
            result = AuthService.authenticate_user(identifier, password)
            
            if result['success']:
                user = result['user']
                
                # Clone guest user for strict session sandbox isolation
                if getattr(user, 'role', '') == 'guest_user':
                    from client.services_sandbox import SandboxService
                    user = SandboxService.create_session_clone(user)
                    result['user'] = user

                resolved_role = getattr(user, 'role', '')
                browser_fingerprint = AuthService.browser_fingerprint_from_request(request)
                current_session_key = ''
                if request.user.is_authenticated and getattr(request.user, 'pk', None) == user.pk:
                    current_session_key = request.session.session_key or ''

                # Check for existing sessions (for logging/UI purposes)
                session_inspection = AuthService.inspect_active_sessions_for_user(
                    user.id,
                    browser_fingerprint=browser_fingerprint,
                    exclude_session_key=current_session_key,
                )
                has_different_browser_session = bool(session_inspection.get('has_different_browser'))
                active_sessions = session_inspection.get('count', 0)

                # Log the user in
                login(request, user)
                
                # Seed session fingerprint immediately so the very next
                # request doesn't see a mismatch and force-logout the user.
                from core.middleware import PermissionValidationMiddleware
                PermissionValidationMiddleware.seed_session_fingerprint(request)

                # Reset the absolute max-age clock so a fresh login always
                # starts with a full lifetime instead of inheriting a stale
                # _session_created from a previous session (Django's login()
                # cycles the key but preserves session data).
                import time as _time
                request.session['_session_created'] = _time.time()
                request.session['_last_activity'] = _time.time()

                # Store actual role resolved from user identity (email/username)
                request.session['selected_role'] = resolved_role
                AuthService.apply_session_auth_context(
                    request,
                    surface='desktop',
                    ip_address=client_ip,
                )
                
                # Log activity
                if user.role in ('client', 'client_staff', 'assistant') and has_different_browser_session:
                    display_name = user.get_full_name() or user.username
                    ActivityService.log(
                        'login',
                        f'{display_name} logged in from a different browser while another session is active',
                        user=user,
                        request=request,
                    )
                    logger.warning(
                        "Concurrent cross-browser login detected: user=%s role=%s ip=%s active_sessions=%s",
                        _mask_login_identifier(identifier),
                        resolved_role,
                        client_ip,
                        active_sessions,
                    )
                else:
                    ActivityService.log_login(request, user)
                logger.info("Login success: user=%s role=%s ip=%s", _mask_login_identifier(identifier), resolved_role, client_ip)
                
                return JsonResponse({
                    'success': True,
                    'redirect_url': result['redirect_url'],
                    'message': result['message']
                })
            else:
                logger.warning(
                    "Login failed: identifier=%s role=%s ip=%s reason=%s",
                    _mask_login_identifier(identifier),
                    'inferred',
                    client_ip,
                    result['message'],
                )
                return JsonResponse({
                    'success': False,
                    'message': result['message']
                })
                
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            logger.exception("Login error for user=%s ip=%s", _mask_login_identifier(identifier), client_ip)
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(rate_limit(max_requests=3, window_seconds=60), name='dispatch')
class ForgotPasswordAPIView(View):
    """
    API endpoint to request password reset OTP.
    POST /api/auth/forgot-password/
    """
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            email = data.get('email', '').strip()
            
            if not email:
                return JsonResponse({
                    'success': False,
                    'message': 'Email is required'
                }, status=400)
            
            result = OTPService.send_otp(email)
            logger.info(
                "Password reset requested: email=%s success=%s",
                _mask_login_identifier(email),
                result['success'],
            )
            
            response_data = {
                'success': result['success'],
                'message': result['message']
            }

            return JsonResponse(response_data)
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            logger.exception("Auth API error: %s", e)
            return JsonResponse({
                'success': False,
                'message': 'An error occurred. Please try again.'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(rate_limit(max_requests=5, window_seconds=60), name='dispatch')
class VerifyOTPAPIView(View):
    """
    API endpoint to verify OTP.
    POST /api/auth/verify-otp/
    """
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            email = data.get('email', '').strip()
            otp = data.get('otp', '').strip()
            
            if not email or not otp:
                return JsonResponse({
                    'success': False,
                    'message': 'Email and OTP are required'
                }, status=400)
            
            result = OTPService.verify_otp(email, otp)
            
            response_data = {
                'success': result['success'],
                'message': result['message']
            }
            
            if result.get('reset_token'):
                response_data['reset_token'] = result['reset_token']
            
            return JsonResponse(response_data)
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            logger.exception("Auth API error: %s", e)
            return JsonResponse({
                'success': False,
                'message': 'An error occurred. Please try again.'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(rate_limit(max_requests=5, window_seconds=60), name='dispatch')
class ResetPasswordAPIView(View):
    """
    API endpoint to reset password.
    POST /api/auth/reset-password/
    """
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            email = data.get('email', '').strip()
            reset_token = data.get('reset_token', '').strip()
            new_password = data.get('new_password', '')
            confirm_password = data.get('confirm_password', '')
            
            if not all([email, reset_token, new_password, confirm_password]):
                return JsonResponse({
                    'success': False,
                    'message': 'All fields are required'
                }, status=400)
            
            if new_password != confirm_password:
                return JsonResponse({
                    'success': False,
                    'message': 'Passwords do not match'
                }, status=400)
            
            if len(new_password) < 8:
                return JsonResponse({
                    'success': False,
                    'message': 'Password must be at least 8 characters'
                }, status=400)
            
            result = OTPService.reset_password(email, reset_token, new_password)

            if result.get('success'):
                user = User.objects.filter(email__iexact=email).first()
                full_email = (email or '').strip()
                target_name = ''
                target_id = None
                if user:
                    target_name = user.get_full_name() or user.username
                    target_id = user.pk
                ActivityService.log(
                    'password_reset',
                    f'Password reset completed for {full_email}',
                    user=user,
                    request=request,
                    target_model='User',
                    target_id=target_id,
                    target_name=target_name,
                )
            
            return JsonResponse({
                'success': result['success'],
                'message': result['message']
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            logger.exception("Auth API error: %s", e)
            return JsonResponse({
                'success': False,
                'message': 'An error occurred. Please try again.'
            }, status=500)


# =============================================================================
# UTILITY VIEWS
# =============================================================================

@login_required(login_url='/panel/auth/login/')
def redirect_to_dashboard(request):
    """Redirect authenticated user to their appropriate dashboard."""
    redirect_url = AuthService.get_dashboard_url(request.user)
    return redirect(redirect_url)


# =============================================================================
# IMPERSONATION VIEWS (Pro User only)
# =============================================================================

class APILoginRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Authentication required'}, status=401)
        return super().dispatch(request, *args, **kwargs)


class ImpersonateStartAPIView(APILoginRequiredMixin, View):
    """
    POST /api/auth/impersonate/start/
    Body: { "user_id": <int> }
    """
    login_url = '/panel/auth/login/'

    def post(self, request):
        from .services_impersonate import ImpersonateService
        if not ImpersonateService.can_impersonate(request.user):
            return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)
        try:
            actor_user = request.user
            data = json.loads(request.body)
            target_user_id = data.get('user_id')
            if not target_user_id:
                return JsonResponse({'success': False, 'message': 'user_id is required'}, status=400)

            result = ImpersonateService.start(request, int(target_user_id))
            status = 200 if result['success'] else 403
            return JsonResponse(result, status=status)
        except (json.JSONDecodeError, ValueError, TypeError):
            return JsonResponse({'success': False, 'message': 'Invalid request data'}, status=400)
        except Exception as e:
            logger.exception("Impersonate start error: %s", e)
            return JsonResponse({'success': False, 'message': 'An error occurred.'}, status=500)


class ImpersonateStopAPIView(APILoginRequiredMixin, View):
    """
    POST /api/auth/impersonate/stop/
    Stops impersonation and returns to the Pro User session.
    """
    login_url = '/panel/auth/login/'

    def post(self, request):
        from .services_impersonate import ImpersonateService
        try:
            next_url = ''
            if request.body:
                try:
                    data = json.loads(request.body)
                    next_url = str(data.get('next', '') or '').strip()
                except json.JSONDecodeError:
                    pass

            result = ImpersonateService.stop(request, next_url=next_url)
            status = 200 if result['success'] else 400
            return JsonResponse(result, status=status)
        except Exception as e:
            logger.exception("Impersonate stop error: %s", e)
            return JsonResponse({'success': False, 'message': 'An error occurred.'}, status=500)


class ImpersonateListAPIView(APILoginRequiredMixin, View):
    """
    GET /api/auth/impersonate/users/
    Returns list of users the Pro User can impersonate.
    """
    login_url = '/panel/auth/login/'

    def get(self, request):
        from .services_impersonate import ImpersonateService
        if not ImpersonateService.can_impersonate(request.user):
            return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

        users = ImpersonateService.get_impersonation_targets(request)
        return JsonResponse({'success': True, 'users': users})


# =============================================================================
# PRO USER AUDIT VIEWS (Pro User only)
# =============================================================================

class ProUserAuditUsersAPIView(APILoginRequiredMixin, View):
    """GET /api/auth/user-audit/users/ - list users available for deep history audit."""
    login_url = '/panel/auth/login/'

    def get(self, request):
        if not PermissionService.can_use_pro_user_options(request.user):
            return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

        search = str(request.GET.get('search', '') or '').strip()
        role_filter = str(request.GET.get('role', '') or '').strip()
        users_qs = User.objects.select_related('client_profile', 'assistant_profile__client').all().order_by('role', 'first_name', 'username')

        if role_filter and role_filter in {'pro_user', 'super_admin', 'operator', 'client', 'assistant'}:
            users_qs = users_qs.filter(role=role_filter)
        if search:
            users_qs = users_qs.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        users = []
        for entry in users_qs[:300]:
            client_name = ''
            if entry.role == 'client':
                client_profile = getattr(entry, 'client_profile', None)
                client_name = getattr(client_profile, 'name', '') or ''
            elif entry.role == 'assistant':
                assistant_profile = getattr(entry, 'assistant_profile', None)
                client_name = getattr(getattr(assistant_profile, 'client', None), 'name', '') or ''

            users.append({
                'id': entry.pk,
                'name': entry.get_full_name() or entry.username,
                'username': entry.username,
                'email': entry.email or '',
                'role': entry.role,
                'role_display': dict(User.ROLE_CHOICES).get(entry.role, entry.role),
                'is_active': bool(entry.is_active),
                'last_login': entry.last_login.isoformat() if entry.last_login else None,
                'client_name': client_name,
            })

        return JsonResponse({'success': True, 'users': users})


class ProUserAuditHistoryAPIView(APILoginRequiredMixin, View):
    """GET /api/auth/user-audit/history/ - deep history for a selected user."""
    login_url = '/panel/auth/login/'

    ACTION_DEVICE_HINTS = {
        'login': 'Login Session',
        'logout': 'Logout Session',
        'password_reset': 'Credential Update',
        'card_bulk_download': 'Bulk Download',
        'card_bulk_status': 'Bulk Workflow',
        'card_status': 'Card Workflow',
        'reprint_status': 'Reprint Workflow',
    }

    DEVICE_SURFACE_ICONS = {
        'mobile': 'fa-mobile-screen-button',
        'desktop': 'fa-desktop',
        'unknown': 'fa-circle-question',
    }

    @staticmethod
    def _infer_device_hint(action, description, ip_address):
        desc = str(description or '').lower()
        if 'android' in desc:
            return 'Android Device'
        if 'iphone' in desc or 'ios' in desc:
            return 'iOS Device'
        if 'windows' in desc:
            return 'Windows Desktop'
        if 'mac' in desc:
            return 'Mac Desktop'
        if 'linux' in desc:
            return 'Linux Desktop'
        if 'browser' in desc:
            return 'Web Browser'
        if action in ProUserAuditHistoryAPIView.ACTION_DEVICE_HINTS:
            return ProUserAuditHistoryAPIView.ACTION_DEVICE_HINTS[action]
        if ip_address:
            return f'IP {ip_address}'
        return 'Activity Record'

    @staticmethod
    def _infer_device_surface(action, description):
        desc = f"{action or ''} {description or ''}".lower()
        if any(token in desc for token in ('mobile app', 'android', 'iphone', 'ipad', 'ipod', ' ios ', 'mobile')):
            return 'mobile'
        if any(token in desc for token in ('desktop web', 'desktop', 'browser', 'windows', 'mac', 'linux', 'web app', 'web')):
            return 'desktop'
        return 'unknown'

    @classmethod
    def _device_surface_meta(cls, action, description):
        surface = cls._infer_device_surface(action, description)
        if surface == 'mobile':
            label = 'Mobile'
        elif surface == 'desktop':
            label = 'Desktop'
        else:
            label = 'Unknown'
        return {
            'device_surface': surface,
            'device_surface_label': label,
            'device_surface_icon': cls.DEVICE_SURFACE_ICONS.get(surface, cls.DEVICE_SURFACE_ICONS['unknown']),
        }

    def get(self, request):
        if not PermissionService.can_use_pro_user_options(request.user):
            return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

        try:
            target_user_id = int(request.GET.get('user_id', '0'))
        except (TypeError, ValueError):
            target_user_id = 0
        if target_user_id <= 0:
            return JsonResponse({'success': False, 'message': 'user_id is required.'}, status=400)

        try:
            limit = int(request.GET.get('limit', '80'))
        except (TypeError, ValueError):
            limit = 80
        limit = min(max(limit, 1), 200)

        try:
            offset = int(request.GET.get('offset', '0'))
        except (TypeError, ValueError):
            offset = 0
        offset = max(offset, 0)

        action_filter = str(request.GET.get('action', '') or '').strip()
        search = str(request.GET.get('search', '') or '').strip()

        target_user = User.objects.filter(pk=target_user_id).first()
        if not target_user:
            return JsonResponse({'success': False, 'message': 'User not found.'}, status=404)

        activity_qs = ActivityLog.objects.select_related('user').filter(
            Q(user_id=target_user.pk)
            | Q(target_model='User', target_id=target_user.pk)
        )

        if action_filter:
            activity_qs = activity_qs.filter(action=action_filter)
        if search:
            activity_qs = activity_qs.filter(
                Q(description__icontains=search)
                | Q(target_name__icontains=search)
                | Q(action__icontains=search)
                | Q(user__username__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )

        total = activity_qs.count()
        entries = activity_qs.order_by('-created_at')[offset:offset + limit]

        summary = activity_qs.aggregate(
            total_events=Count('id'),
            login_count=Count('id', filter=Q(action='login')),
            download_count=Count('id', filter=Q(action='card_bulk_download')),
            approve_count=Count(
                'id',
                filter=Q(action__in=['card_status', 'card_bulk_status'], description__icontains='approved')
            ),
            latest_event_at=Max('created_at'),
        )

        action_dict = dict(ActivityLog.ACTION_CHOICES)
        now = timezone.now()
        logs = []
        for entry in entries:
            actor_name = ''
            actor_role = ''
            if entry.user:
                actor_name = entry.user.get_full_name() or entry.user.username
                actor_role = getattr(entry.user, 'role', '')

            event_dt = localtime(entry.created_at)
            log_item = {
                'id': entry.pk,
                'action': entry.action,
                'action_display': action_dict.get(entry.action, entry.action.replace('_', ' ').title()),
                'description': entry.description,
                'target_name': entry.target_name or '',
                'target_model': entry.target_model or '',
                'target_id': entry.target_id,
                'actor_name': actor_name,
                'actor_role': actor_role,
                'ip_address': entry.ip_address or '',
                'device_hint': self._infer_device_hint(entry.action, entry.description, entry.ip_address),
                'icon_class': entry.icon_class,
                'icon_color': entry.icon_color,
                'time_ago': timesince(entry.created_at, now),
                'created_at': entry.created_at.isoformat(),
                'created_date': event_dt.strftime('%d %b %Y'),
                'created_time': event_dt.strftime('%I:%M:%S %p'),
                'scope': 'performed' if entry.user_id == target_user.pk else 'related',
            }
            log_item.update(self._device_surface_meta(entry.action, entry.description))
            logs.append(log_item)

        return JsonResponse({
            'success': True,
            'user': {
                'id': target_user.pk,
                'name': target_user.get_full_name() or target_user.username,
                'username': target_user.username,
                'email': target_user.email or '',
                'role': target_user.role,
                'role_display': dict(User.ROLE_CHOICES).get(target_user.role, target_user.role),
                'is_active': bool(target_user.is_active),
                'last_login': target_user.last_login.isoformat() if target_user.last_login else None,
            },
            'summary': {
                'total_events': int(summary.get('total_events') or 0),
                'login_count': int(summary.get('login_count') or 0),
                'download_count': int(summary.get('download_count') or 0),
                'approve_count': int(summary.get('approve_count') or 0),
                'latest_event_at': summary.get('latest_event_at').isoformat() if summary.get('latest_event_at') else None,
            },
            'logs': logs,
            'total': total,
            'offset': offset,
            'limit': limit,
            'has_more': (offset + limit) < total,
        })


class ProUserAuditActionsAPIView(APILoginRequiredMixin, View):
    """GET /api/auth/user-audit/actions/ - supported action filters."""
    login_url = '/panel/auth/login/'

    def get(self, request):
        if not PermissionService.can_use_pro_user_options(request.user):
            return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

        actions = [
            {'value': key, 'label': label}
            for key, label in ActivityLog.ACTION_CHOICES
        ]
        return JsonResponse({'success': True, 'actions': actions})


# =============================================================================
# AUTH ME & PROFILE API VIEWS
# =============================================================================

class AuthMeAPIView(View):
    """
    GET /api/auth/me/
    Return session & role payload for currently authenticated user.
    """
    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'authenticated': False}, status=200)

        role = getattr(user, 'role', 'admin') or ('admin' if user.is_superuser else 'client')
        is_impersonating = bool(request.session.get('_impersonator_id'))
        impersonator_name = request.session.get('_impersonator_name') or 'Super Admin'

        return JsonResponse({
            'authenticated': True,
            'is_impersonating': is_impersonating,
            'impersonator': {
                'id': request.session.get('_impersonator_id'),
                'name': impersonator_name,
            } if is_impersonating else None,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': getattr(user, 'email', ''),
                'first_name': getattr(user, 'first_name', ''),
                'last_name': getattr(user, 'last_name', ''),
                'full_name': user.get_full_name() or user.username,
                'role': role,
                'is_superuser': user.is_superuser,
                'is_active': user.is_active,
            }
        })


class ProfileAPIView(APILoginRequiredMixin, View):
    """GET /api/profile/"""
    login_url = '/panel/auth/login/'

    def get(self, request):
        from .services_profile import UserProfileService
        profile_data = UserProfileService.get_profile(request.user, request=request)
        return JsonResponse({'success': True, 'profile': profile_data})


class ProfileUpdateAPIView(APILoginRequiredMixin, View):
    """POST /api/profile/update/"""
    login_url = '/panel/auth/login/'

    def post(self, request):
        from .services_profile import UserProfileService
        try:
            data = json.loads(request.body)
            success, message, profile_data = UserProfileService.update_profile(request.user, data, request=request)
            status = 200 if success else 400
            return JsonResponse({'success': success, 'message': message, 'profile': profile_data}, status=status)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)


class ProfileChangePasswordAPIView(APILoginRequiredMixin, View):
    """POST /api/profile/change-password/"""
    login_url = '/panel/auth/login/'

    def post(self, request):
        from .services_profile import UserProfileService
        try:
            data = json.loads(request.body)
            current_pass = data.get('current_password', '')
            new_pass = data.get('new_password', '')
            success, message = UserProfileService.change_password(
                request.user, current_pass, new_pass, current_session_key=request.session.session_key
            )
            status = 200 if success else 400
            return JsonResponse({'success': success, 'message': message}, status=status)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)


class ProfileUploadImageAPIView(APILoginRequiredMixin, View):
    """POST /api/profile/upload-image/"""
    login_url = '/panel/auth/login/'

    def post(self, request):
        from .services_profile import UserProfileService
        image_file = request.FILES.get('image') or request.FILES.get('profile_image')
        success, message, image_url = UserProfileService.upload_profile_image(request.user, image_file)
        status = 200 if success else 400
        return JsonResponse({'success': success, 'message': message, 'image_url': image_url}, status=status)


class ProfileRemoveImageAPIView(APILoginRequiredMixin, View):
    """POST /api/profile/remove-image/"""
    login_url = '/panel/auth/login/'

    def post(self, request):
        from .services_profile import UserProfileService
        success, message = UserProfileService.remove_profile_image(request.user)
        status = 200 if success else 400
        return JsonResponse({'success': success, 'message': message}, status=status)

