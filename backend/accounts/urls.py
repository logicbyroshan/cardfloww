"""
Accounts URL Configuration

URL patterns for authentication and password reset.

NOTE: The primary auth API routes are in core/urls.py (/panel/api/auth/...)
which are the ones used by the login template. These accounts/ routes are
kept only for the login/logout page views and the dashboard redirect.
"""
from django.urls import path
from . import views
from .session_refresh import api_session_refresh

app_name = 'accounts'

urlpatterns = [
    # ==========================================================================
    # PAGE VIEWS (Template-based)
    # ==========================================================================
    
    # Login page (multi-step: email → password)
    path('login/', views.LoginPageView.as_view(), name='login'),
    
    # CSRF token acquisition
    path('csrf/', views.GetCSRFTokenView.as_view(), name='get_csrf_token'),
    
    # Logout
    path('logout/', views.LogoutView.as_view(), name='logout'),
    
    # Redirect to appropriate dashboard
    path('dashboard/', views.redirect_to_dashboard, name='dashboard_redirect'),
    
    # Secure Credential Vault (opened via email link)
    path('secure-view/<str:token>/', views.SecureCredentialVaultView.as_view(), name='secure_credential_vault'),
    
    
    # ==========================================================================
    # API ENDPOINTS (JSON responses for AJAX)
    # Canonical routes are at /panel/api/auth/ via core/urls.py
    # These /panel/auth/api/auth/ aliases kept for backward compatibility.
    # ==========================================================================
    
    path('api/auth/check-email/', views.CheckEmailAPIView.as_view(), name='api_check_email'),
    path('api/auth/login/', views.LoginAPIView.as_view(), name='api_login'),
    path('api/auth/me/', views.AuthMeAPIView.as_view(), name='api_auth_me'),
    path('api/auth/forgot-password/', views.ForgotPasswordAPIView.as_view(), name='api_forgot_password'),
    path('api/auth/verify-otp/', views.VerifyOTPAPIView.as_view(), name='api_verify_otp'),
    path('api/auth/reset-password/', views.ResetPasswordAPIView.as_view(), name='api_reset_password'),

    # Profile management endpoints
    path('api/profile/', views.ProfileAPIView.as_view(), name='api_profile'),
    path('api/profile/update/', views.ProfileUpdateAPIView.as_view(), name='api_profile_update'),
    path('api/profile/change-password/', views.ProfileChangePasswordAPIView.as_view(), name='api_profile_change_password'),
    path('api/profile/upload-image/', views.ProfileUploadImageAPIView.as_view(), name='api_profile_upload_image'),
    path('api/profile/remove-image/', views.ProfileRemoveImageAPIView.as_view(), name='api_profile_remove_image'),

    # Impersonation endpoints (Pro User only)
    path('api/auth/impersonate/start/', views.ImpersonateStartAPIView.as_view(), name='api_impersonate_start'),
    path('api/auth/impersonate/stop/', views.ImpersonateStopAPIView.as_view(), name='api_impersonate_stop'),
    path('api/auth/impersonate/users/', views.ImpersonateListAPIView.as_view(), name='api_impersonate_users'),

    # Pro User audit endpoints (deep user history)
    path('api/auth/user-audit/users/', views.ProUserAuditUsersAPIView.as_view(), name='api_user_audit_users'),
    path('api/auth/user-audit/history/', views.ProUserAuditHistoryAPIView.as_view(), name='api_user_audit_history'),
    path('api/auth/user-audit/actions/', views.ProUserAuditActionsAPIView.as_view(), name='api_user_audit_actions'),

    # Session refresh (silent keepalive for active users)
    path('api/auth/session-refresh/', api_session_refresh, name='api_session_refresh'),
]

