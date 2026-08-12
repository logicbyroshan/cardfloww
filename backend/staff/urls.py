from django.urls import path
from django.views.generic import RedirectView
from operators import views as operator_views

app_name = 'staff'

urlpatterns = [
    # Page view redirects
    path('manage/', RedirectView.as_view(pattern_name='operators:manage', permanent=True), name='manage'),
    path('dashboard/', RedirectView.as_view(pattern_name='operators:dashboard', permanent=True), name='dashboard'),
    
    # API endpoints forwarded directly to new Operator views to preserve method/payload
    path('api/admin-staff/', operator_views.api_operator_list_create, name='api_admin_staff_list_create'),
    path('api/admin-staff/<int:operator_id>/', operator_views.api_operator_detail, name='api_admin_staff_detail'),
    path('api/admin-staff/<int:operator_id>/toggle-status/', operator_views.api_operator_toggle_status, name='api_admin_staff_toggle_status'),
    path('api/admin-staff/<int:operator_id>/reset-password/', operator_views.api_operator_reset_password, name='api_admin_staff_reset_password'),
]
