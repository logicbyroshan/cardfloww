"""
Accounts URL Configuration

URL patterns for authentication and password reset API endpoints.
All UI pages (login, logout, password reset) are handled by the React SPA frontend.
Django only provides JSON API endpoints here.
"""
from django.urls import path
from . import views
from .session_refresh import api_session_refresh

app_name = 'accounts'

urlpatterns = [
    # ==========================================================================
    # CSRF token acquisition (sets csrftoken cookie — required before any POST)
    # ==========================================================================
    path('csrf/', views.GetCSRFTokenView.as_view(), name='get_csrf_token'),

    # ==========================================================================
    # API ENDPOINTS (JSON responses)
    # Canonical routes are at /api/auth/ via core/urls.py.
    # These aliases are kept for app namespace routing compatibility.
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
