"""
Operators App URL Configuration
"""
from django.urls import path

from .views import (
    # Page views
    operators_management_page,
    operator_dashboard,
    
    # Operator CRUD API
    api_operator_list_create,
    api_operator_detail,
    api_operator_toggle_status,
    api_operator_reset_password,
    api_operator_delete,
    
    # Permission & Client listing API
    api_available_permissions,
    api_available_clients,
    
    # Self-service API (for operators)
    api_my_permissions,
    api_my_clients,
    
    # Client-scoped data examples
    api_scoped_clients,
    api_client_idcard_groups,
)

app_name = 'operators'

urlpatterns = [
    # ==========================================================================
    # PAGE VIEWS
    # ==========================================================================
    path('manage/', operators_management_page, name='manage'),
    path('dashboard/', operator_dashboard, name='dashboard'),
    
    # ==========================================================================
    # OPERATOR CRUD API (Super Admin only)
    # ==========================================================================
    path('api/operator/', api_operator_list_create, name='api_operator_list_create'),
    path('api/operator/<int:operator_id>/', api_operator_detail, name='api_operator_detail'),
    path('api/operator/<int:operator_id>/toggle-status/', api_operator_toggle_status, name='api_operator_toggle_status'),
    path('api/operator/<int:operator_id>/reset-password/', api_operator_reset_password, name='api_operator_reset_password'),
    path('api/operator/<int:operator_id>/delete/', api_operator_delete, name='api_operator_delete'),
    
    # ==========================================================================
    # PERMISSION & CLIENT LISTING API (Super Admin only)
    # ==========================================================================
    path('api/permissions/available/', api_available_permissions, name='api_available_permissions'),
    path('api/clients/available/', api_available_clients, name='api_available_clients'),
    
    # ==========================================================================
    # SELF-SERVICE API (Operators)
    # ==========================================================================
    path('api/my/permissions/', api_my_permissions, name='api_my_permissions'),
    path('api/my/clients/', api_my_clients, name='api_my_clients'),
    
    # ==========================================================================
    # CLIENT-SCOPED DATA EXAMPLES
    # ==========================================================================
    path('api/clients/', api_scoped_clients, name='api_scoped_clients'),
    path('api/clients/<int:client_id>/idcard-groups/', api_client_idcard_groups, name='api_client_idcard_groups'),
]
