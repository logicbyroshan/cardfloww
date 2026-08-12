"""
Client app URL configuration

URLs for client-facing features:
- Dashboard
- Staff Management
- Card Data Views
- Image Uploads
- ID Card Group / Actions / Settings / Reprint (shared admin templates)
"""
from django.urls import path
from . import views

app_name = 'client'

urlpatterns = [
    # ==========================================================================
    # PAGE VIEWS
    # ==========================================================================
    
    # Client Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Card Groups (legacy, kept for backward compat)
    path('groups/', views.card_groups, name='groups'),
    
    # Cards in a Table (legacy, kept for backward compat)
    path('table/<int:table_id>/cards/', views.card_table, name='cards'),

    # Print route used by integration tests; redirects to the client group page.
    path('table/<int:table_id>/print/', views.print_table, name='print_table'),
    
    # Staff Management (Client Admin only)
    path('staff/', views.manage_staff, name='staff'),

    # One-way admin messages (read-only for client/client staff)
    path('messages/', views.messages, name='messages'),
    
    # --- Shared admin-template pages (client context) ---
    # ID Card Group (shows all tables with status counts)
    path('idcard-group/', views.client_idcard_group, name='idcard_group'),
    
    # Group Settings (manage tables in the group)
    path('group-settings/', views.client_group_settings, name='group_settings'),
    
    # ID Card Actions (shows cards, status tabs)
    path('table/<int:table_id>/actions/', views.client_idcard_actions, name='idcard_actions'),

    # Shared reprint workflow page used from the download list action bar.
    path('table/<int:table_id>/reprint/', views.reprint_cards, name='reprint_cards'),
    
    # ==========================================================================
    # API ENDPOINTS - Dashboard
    # ==========================================================================
    
    path('api/dashboard/', views.api_dashboard_data, name='api_dashboard'),
    path('api/messages/drawer/', views.api_messages_drawer, name='api_messages_drawer'),
    path('api/groups/', views.api_groups_list, name='api_groups'),
    path('api/reprint-history/', views.api_reprint_history, name='api_reprint_history'),
    
    # ==========================================================================
    # API ENDPOINTS - Staff Management
    # ==========================================================================
    
    # List staff (GET) and Create staff (POST)
    path('api/staff/', views.api_staff_list_create, name='api_staff_list'),
    
    # Get/Update/Delete single staff member
    path('api/staff/<int:staff_id>/', views.api_staff_detail, name='api_staff_detail'),
    
    # Toggle staff active/inactive status
    path('api/staff/<int:staff_id>/toggle-status/', views.api_staff_toggle_status, name='api_staff_toggle_status'),

    # Set temporary password for a staff member
    path('api/staff/<int:staff_id>/set-temp-password/', views.api_staff_set_temp_password, name='api_staff_set_temp_password'),
    
    # Get groups for staff assignment
    path('api/groups/active/', views.api_client_groups_list, name='api_groups_active'),
    
    # Get distinct class/section values for staff filtering
    path('api/class-section-options/', views.api_class_section_options, name='api_class_section_options'),
    
    # ==========================================================================
    # API ENDPOINTS - Card Data
    # ==========================================================================
    
    path('api/tables/', views.api_tables_list, name='api_tables'),
    path('api/table/<int:table_id>/cards/', views.api_cards_list, name='api_cards'),
    path('api/cards/<int:card_id>/', views.api_card_detail, name='api_card_detail'),
    path('api/card/<int:card_id>/status/', views.api_card_change_status, name='api_card_status'),
    path('api/table/<int:table_id>/cards/bulk-status/', views.api_cards_bulk_status, name='api_cards_bulk_status'),
    
    # ==========================================================================
    # API ENDPOINTS - Image Upload
    # ==========================================================================
    
    path('api/table/<int:table_id>/upload-images/', views.api_upload_images, name='api_upload_images'),

    # Create Table from XLSX (reads headers, creates table, imports data)
    path('api/create-from-xlsx/', views.client_api_create_table_from_xlsx, name='api_create_table_from_xlsx'),
]
