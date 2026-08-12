"""
Authentication Views - BACKWARD COMPATIBILITY
This module re-exports from accounts.views for backward compatibility.
All new code should import directly from accounts.views.
"""
# BACKWARD COMPATIBILITY: Re-export auth API views from accounts app
from accounts.views import (
    LogoutView,
    CheckEmailAPIView,
    LoginAPIView,
    ForgotPasswordAPIView,
    VerifyOTPAPIView,
    ResetPasswordAPIView,
    ImpersonateStartAPIView,
    ImpersonateStopAPIView,
    ImpersonateListAPIView,
    ProUserAuditUsersAPIView,
    ProUserAuditHistoryAPIView,
    ProUserAuditActionsAPIView,
)

# Backward compatible function names (map old names to new implementations)
logout_view = LogoutView.as_view()
api_check_email = CheckEmailAPIView.as_view()
api_login = LoginAPIView.as_view()
api_forgot_password = ForgotPasswordAPIView.as_view()
api_verify_otp = VerifyOTPAPIView.as_view()
api_reset_password = ResetPasswordAPIView.as_view()
api_impersonate_start = ImpersonateStartAPIView.as_view()
api_impersonate_stop = ImpersonateStopAPIView.as_view()
api_impersonate_users = ImpersonateListAPIView.as_view()
api_user_audit_users = ProUserAuditUsersAPIView.as_view()
api_user_audit_history = ProUserAuditHistoryAPIView.as_view()
api_user_audit_actions = ProUserAuditActionsAPIView.as_view()


def inactive_view(request):
    """Return JSON 403 — React handles the inactive account UI screen."""
    from django.http import JsonResponse
    reason = request.GET.get('reason', '')
    return JsonResponse({'success': False, 'message': 'Account inactive.', 'reason': reason}, status=403)


def maintenance_view(request):
    """Return JSON 403 — React handles the maintenance UI screen."""
    from django.http import JsonResponse
    reason = request.GET.get('reason', '')
    return JsonResponse({'success': False, 'message': 'Account in maintenance.', 'reason': reason}, status=403)


def api_check_maintenance(request):
    """
    Lightweight API for the maintenance page to poll whether the client
    account has been reactivated. Returns { active: true/false }.
    """
    from django.http import JsonResponse
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({'active': False})
    
    if user.role in ('prime_manager', 'manager', 'guest_prime_manager'):
        from organisation.models import Organisation
        try:
            org = Organisation.objects.get(user=user)
            return JsonResponse({'active': org.status == 'active'})
        except Organisation.DoesNotExist:
            return JsonResponse({'active': False})
    elif user.role == 'assistant':
        from assistants.models import Assistant
        try:
            assistant = Assistant.objects.select_related('organisation').get(user=user)
            return JsonResponse({'active': assistant.organisation and assistant.organisation.status == 'active'})
        except Assistant.DoesNotExist:
            return JsonResponse({'active': False})

    return JsonResponse({'active': True})


def api_auth_me(request):
    """Return session payload for the currently authenticated user."""
    from django.http import JsonResponse
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({'authenticated': False}, status=200)

    role = getattr(user, 'role', 'admin') or ('admin' if user.is_superuser else 'prime_manager')
    return JsonResponse({
        'authenticated': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': getattr(user, 'email', ''),
            'role': role,
            'is_superuser': user.is_superuser,
        }
    })

def api_auth_logout(request):
    """JSON logout endpoint for the React SPA.

    Always returns JSON so the SPA never gets a redirect/HTML response.
    CSRF-exempt because logout only destroys the caller's own session.
    """
    from django.http import JsonResponse
    from django.contrib.auth import logout as django_logout
    # Support both GET (for quick links) and POST (preferred)
    if request.method not in ('POST', 'GET'):
        return JsonResponse({'success': False, 'message': 'Method not allowed.'}, status=405)
    if request.user.is_authenticated:
        django_logout(request)
    return JsonResponse({'success': True, 'message': 'Logged out successfully.'})

from django.views.decorators.csrf import csrf_exempt as _csrf_exempt
api_auth_logout = _csrf_exempt(api_auth_logout)



__all__ = [
    'login_view',
    'logout_view',
    'api_check_email',
    'api_login',
    'api_auth_me',
    'api_auth_logout',
    'api_forgot_password',
    'api_verify_otp',
    'api_reset_password',
    'admin_staff_dashboard',
    'client_dashboard',
    'client_staff_dashboard',
    'inactive_view',
    'maintenance_view',
    'api_check_maintenance',
    'api_impersonate_start',
    'api_impersonate_stop',
    'api_impersonate_users',
    'api_user_audit_users',
    'api_user_audit_history',
    'api_user_audit_actions',
]

