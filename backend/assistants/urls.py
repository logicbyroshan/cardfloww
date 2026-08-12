from django.urls import path
from . import views

app_name = 'assistants'

urlpatterns = [
    # Page view
    path('', views.manage_assistants, name='manage_assistants'),
    
    # API endpoints
    path('api/staff/', views.api_staff_list_create, name='api_staff_list'),
    path('api/staff/bulk-delete/', views.api_staff_bulk_delete, name='api_staff_bulk_delete'),
    path('api/staff/<int:staff_id>/', views.api_staff_detail, name='api_staff_detail'),
    path('api/staff/<int:staff_id>/toggle-status/', views.api_staff_toggle_status, name='api_staff_toggle_status'),
    path('api/staff/<int:staff_id>/set-temp-password/', views.api_staff_set_temp_password, name='api_staff_set_temp_password'),
    path('api/groups/active/', views.api_client_groups_list, name='api_groups_active'),
    path('api/class-section-options/', views.api_class_section_options, name='api_class_section_options'),
    path('api/staff/bulk-upload/', views.api_staff_bulk_upload_xlsx, name='api_staff_bulk_upload_xlsx'),
    path('api/staff/auto-create/', views.api_staff_auto_create, name='api_staff_auto_create'),
]
