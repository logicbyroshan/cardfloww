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
    CheckPinStatusAPIView,
    LoginWithPinAPIView,
    CreatePinAPIView,
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
api_pin_status = CheckPinStatusAPIView.as_view()
api_login_pin = LoginWithPinAPIView.as_view()
api_create_pin = CreatePinAPIView.as_view()
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

    role = getattr(user, 'role', None) or ('super_admin' if user.is_superuser else 'prime_manager')

    ROLE_LABELS = {
        'prime_admin': 'Prime Admin',
        'super_admin': 'Super Admin',
        'operator': 'Operator',
        'prime_manager': 'Organisation (Prime Manager)',
        'super_manager': 'Super Manager',
        'assistant': 'Assistant',
        'photographer': 'Photographer',
    }
    role_label = ROLE_LABELS.get(role, role)

    # Resolve org context for non-admin users
    org_id = None
    org_name = None
    if role in ('prime_manager', 'super_manager', 'manager'):
        try:
            from organisation.models import Organisation
            org = Organisation.objects.filter(user=user).first()
            if org:
                org_id = org.id
                org_name = org.name
        except Exception:
            pass
    elif role == 'assistant':
        try:
            from assistants.models import Assistant
            ast = Assistant.objects.filter(user=user).select_related('client').first()
            if ast and ast.client:
                org_id = ast.client.id
                org_name = ast.client.name
        except Exception:
            pass

    full_name = ' '.join(filter(None, [
        getattr(user, 'first_name', ''),
        getattr(user, 'last_name', ''),
    ])).strip() or user.username

    is_impersonating = bool(request.session.get('_pro_original_user_id') or request.session.get('_impersonator_id'))
    impersonator_id = request.session.get('_pro_original_user_id') or request.session.get('_impersonator_id')
    impersonator_name = request.session.get('_pro_original_user_name') or request.session.get('_impersonator_name') or 'Super Admin'

    return JsonResponse({
        'authenticated': True,
        'is_impersonating': is_impersonating,
        'impersonator': {
            'id': impersonator_id,
            'name': impersonator_name,
        } if is_impersonating else None,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': getattr(user, 'email', ''),
            'first_name': getattr(user, 'first_name', ''),
            'last_name': getattr(user, 'last_name', ''),
            'full_name': full_name,
            'role': role,
            'role_label': role_label,
            'is_superuser': user.is_superuser,
            'org_id': org_id,
            'org_name': org_name,
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

    from accounts.services_impersonate import ImpersonateService
    if request.user.is_authenticated and ImpersonateService.is_impersonating(request):
        next_url = request.POST.get('next', '') or request.GET.get('next', '')
        result = ImpersonateService.stop(request, next_url=next_url)
        if result.get('success'):
            redirect_url = result.get('redirect_url') or '/'
            return JsonResponse({'success': True, 'redirect': redirect_url})

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

