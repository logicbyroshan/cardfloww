from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt
from . import views
from exports import views as export_views
from organisation import views_api as client_views_api
from organisation import views_admin as organisation_views
from accounts import views as accounts_views


urlpatterns = [
    # Legacy web / template routes
    path('panel/manage-clients/', organisation_views.manage_clients, name='manage_clients'),
    path('manage-clients/', organisation_views.manage_clients, name='manage_clients_direct'),
    # ==================== AUTHENTICATION API ====================
    # NOTE: login/logout pages are handled by the React SPA at /auth/login, /auth/logout.
    # Django only provides JSON API endpoints here.
    path('api/auth/check-maintenance/', views.api_check_maintenance, name='api_check_maintenance'),
    path('api/maintenance/status/', views.api_system_maintenance_check, name='api_system_maintenance_check'),
    path('api/maintenance/toggle/', views.api_maintenance_toggle, name='api_maintenance_toggle'),
    path('api/auth/check-email/', csrf_exempt(views.api_check_email), name='api_check_email'),
    path('api/auth/login/', csrf_exempt(views.api_login), name='api_login'),
    path('api/auth/csrf/', accounts_views.GetCSRFTokenView.as_view(), name='api_get_csrf_token'),
    path('api/auth/me/', views.api_auth_me, name='api_auth_me'),
    path('api/auth/logout/', views.api_auth_logout, name='api_auth_logout'),
    path('api/auth/forgot-password/', csrf_exempt(views.api_forgot_password), name='api_forgot_password'),
    path('api/auth/verify-otp/', csrf_exempt(views.api_verify_otp), name='api_verify_otp'),
    path('api/auth/reset-password/', csrf_exempt(views.api_reset_password), name='api_reset_password'),
    path('api/auth/impersonate/start/', csrf_exempt(accounts_views.ImpersonateStartAPIView.as_view()), name='api_impersonate_start'),
    path('api/auth/impersonate/stop/', csrf_exempt(accounts_views.ImpersonateStopAPIView.as_view()), name='api_impersonate_stop'),
    path('api/auth/impersonate/users/', csrf_exempt(accounts_views.ImpersonateListAPIView.as_view()), name='api_impersonate_users'),
    path('api/auth/user-audit/users/', csrf_exempt(views.api_user_audit_users), name='api_user_audit_users'),
    path('api/auth/user-audit/history/', csrf_exempt(views.api_user_audit_history), name='api_user_audit_history'),
    path('api/auth/user-audit/actions/', csrf_exempt(views.api_user_audit_actions), name='api_user_audit_actions'),

    # ==================== DASHBOARD API ====================
    path('api/global-search/', views.api_global_search, name='api_global_search'),
    path('api/dashboard-card-stats/', views.api_dashboard_card_stats, name='api_dashboard_card_stats'),
    path('api/recent-client-updates/', views.api_recent_client_updates, name='api_recent_client_updates'),
    path('api/presence/track/', views.api_presence_track, name='api_presence_track'),
    path('api/presence/live-count/', views.api_live_client_presence, name='api_live_client_presence'),
    path('api/recent-activity/', views.api_recent_activity, name='api_recent_activity'),
    path('api/reprint-overview/', views.api_reprint_overview, name='api_reprint_overview'),

    # ==================== EMAIL & PANEL API ====================
    path('api/email-logs/', views.api_email_logs, name='api_email_logs'),
    path('api/email-resend/<int:log_id>/', views.api_email_resend, name='api_email_resend'),
    path('api/email-send/', views.api_email_send_new, name='api_email_send_new'),
    path('api/email-compose-defaults/', views.api_email_compose_defaults, name='api_email_compose_defaults'),

    # ==================== BACKUP API ====================
    path('api/backup/generate-code/', views.api_backup_generate_code, name='api_backup_generate_code'),
    path('api/backup/initiate/', views.api_backup_initiate, name='api_backup_initiate'),
    path('api/backup/start/', views.api_backup_start, name='api_backup_start'),
    path('api/backup/list/', views.api_backup_list, name='api_backup_list'),
    path('api/backup/status/<int:task_id>/', views.api_backup_status, name='api_backup_status'),
    path('api/backup/<int:task_id>/delete-now/', views.api_backup_delete_now, name='api_backup_delete_now'),
    path('api/backup/download/<int:task_id>/', views.api_backup_download, name='api_backup_download'),

    # ==================== NOTIFICATION API ====================
    path('api/notifications/list/', views.api_notifications_list, name='api_notifications_list'),
    path('api/notifications/unread-count/', views.api_notifications_unread_count, name='api_notifications_unread_count'),
    path('api/notifications/<int:notification_id>/read/', views.api_notification_mark_read, name='api_notification_mark_read'),
    path('api/notifications/mark-all-read/', views.api_notifications_mark_all_read, name='api_notifications_mark_all_read'),
    path('api/notifications/client-messages/unread/', views.api_client_message_strip, name='api_client_message_strip'),
    path('api/notifications/admin/list/', views.api_panel_notifications_list, name='api_panel_notifications_list'),
    path('api/notifications/admin/create/', views.api_panel_notification_create, name='api_panel_notification_create'),
    path('api/notifications/admin/<int:notification_id>/delete/', views.api_panel_notification_delete, name='api_panel_notification_delete'),
    path('api/notifications/admin/target-users/', views.api_panel_target_users, name='api_panel_target_users'),

    # ==================== API ENDPOINTS ====================
    # Client App Dashboard, Group, & Staff APIs (for React SPA)

    # ==================== CLIENT & ORGANISATION API ====================
    path('api/dashboard/', client_views_api.api_dashboard_data, name='api_client_dashboard'),
    path('api/reprint-history/', client_views_api.api_reprint_history, name='api_client_reprint_history'),
    path('api/groups/', client_views_api.api_groups_list, name='api_client_groups'),
    path('api/groups/active/', client_views_api.api_client_groups_list, name='api_client_groups_active'),
    path('api/class-section-options/', client_views_api.api_class_section_options, name='api_client_class_section_options'),
    path('api/tables/', client_views_api.api_tables_list, name='api_client_tables'),
    path('api/messages/drawer/', client_views_api.api_messages_drawer, name='api_client_messages_drawer'),

    # Client Staff Management APIs
    path('api/client-staff/', client_views_api.api_staff_list_create, name='api_client_staff_list_create'),
    path('api/client-staff/<int:staff_id>/', client_views_api.api_staff_detail, name='api_client_staff_detail'),
    path('api/client-staff/<int:staff_id>/toggle-status/', client_views_api.api_staff_toggle_status, name='api_client_staff_toggle_status'),
    path('api/client-staff/<int:staff_id>/set-temp-password/', client_views_api.api_staff_set_temp_password, name='api_client_staff_set_temp_password'),

    # Organisation Managers APIs (Prime Manager, Super Managers, Guest Managers)
    path('api/organisation-managers/', client_views_api.api_organisation_managers_list_create, name='api_organisation_managers_list_create'),
    path('api/organisation-managers/<int:manager_id>/', client_views_api.api_organisation_manager_detail, name='api_organisation_manager_detail'),
    path('api/managers/', client_views_api.api_organisation_managers_list_create, name='api_managers_list_create'),
    path('api/managers/<int:manager_id>/', client_views_api.api_organisation_manager_detail, name='api_managers_detail'),

    # Client / Organisation APIs

    path('api/client/create/', views.api_client_create, name='api_client_create'),
    path('api/clients/create/', views.api_client_create, name='api_clients_create'),
    path('api/organisation/create/', views.api_client_create, name='api_organisation_create'),
    path('api/organisations/create/', views.api_client_create, name='api_organisations_create'),
    path('api/client/<int:client_id>/', views.api_client_get, name='api_client_get'),
    path('api/clients/<int:client_id>/', views.api_client_get, name='api_clients_get'),
    path('api/organisation/<int:client_id>/', views.api_client_get, name='api_organisation_get'),
    path('api/organisations/<int:client_id>/', views.api_client_get, name='api_organisations_get'),
    path('api/client/<int:client_id>/update/', views.api_client_update, name='api_client_update'),
    path('api/clients/<int:client_id>/update/', views.api_client_update, name='api_clients_update'),
    path('api/client/<int:client_id>/delete/', views.api_client_delete, name='api_client_delete'),
    path('api/clients/<int:client_id>/delete/', views.api_client_delete, name='api_clients_delete'),
    path('api/client/<int:client_id>/toggle-status/', views.api_client_toggle_status, name='api_client_toggle_status'),
    path('api/clients/<int:client_id>/toggle-status/', views.api_client_toggle_status, name='api_clients_toggle_status'),


    path('api/client/<int:client_id>/staff/', views.api_client_staff, name='api_client_staff'),
    path('api/client/<int:client_id>/staff/<int:staff_id>/toggle-status/', views.api_client_staff_toggle_status, name='api_client_staff_toggle_status'),
    path('api/client/<int:client_id>/staff/<int:staff_id>/permissions/', views.api_client_staff_permissions, name='api_client_staff_permissions'),
    path('api/client/<int:client_id>/set-temp-password/', views.api_client_set_temp_password, name='api_client_set_temp_password'),

    path('api/client/<int:client_id>/messages/', views.api_client_messages, name='api_client_messages'),
    path('api/client/<int:client_id>/messages/send/', views.api_client_message_send, name='api_client_message_send'),
    path('api/client/messages/targets/', views.api_client_message_targets, name='api_client_message_targets'),
    path('api/client/messages/group-send/', views.api_client_messages_group_send, name='api_client_messages_group_send'),
    path('api/client/<int:client_id>/messages/<int:message_id>/delete/', views.api_client_message_delete, name='api_client_message_delete'),
    path('api/client/<int:client_id>/login-history/', views.api_client_login_history, name='api_client_login_history'),
    path('api/client-staff/<int:staff_id>/login-history/', views.api_client_staff_login_history, name='api_client_staff_login_history'),
    path('api/client-staff/<int:staff_id>/assignment-timeline/', views.api_client_staff_assignment_timeline, name='api_client_staff_assignment_timeline'),
    # NOTE: Admin-side Manage Assistant pages and APIs removed — client-side assistant features remain.
    
    # Staff APIs
    path('api/staff/create/', views.api_staff_create, name='api_staff_create'),
    path('api/staff/<int:staff_id>/', views.api_staff_get, name='api_staff_get'),
    path('api/staff/<int:staff_id>/update/', views.api_staff_update, name='api_staff_update'),
    path('api/staff/<int:staff_id>/delete/', views.api_staff_delete, name='api_staff_delete'),
    path('api/staff/<int:staff_id>/toggle-status/', views.api_staff_toggle_status, name='api_staff_toggle_status'),
    path('api/staff/<int:staff_id>/login-history/', views.api_staff_login_history, name='api_staff_login_history'),
    path('api/staff/<int:staff_id>/assignment-timeline/', views.api_staff_assignment_timeline, name='api_staff_assignment_timeline'),
    path('api/clients/active/', views.api_active_clients_list, name='api_active_clients_list'),
    path('api/clients/for-staff-assignment/', views.api_all_clients_for_assignment, name='api_all_clients_for_assignment'),
    path('api/staff/<int:staff_id>/set-temp-password/', views.api_staff_set_temp_password, name='api_staff_set_temp_password'),

    # Photographer APIs
    path('api/photographer/create/', views.api_photographer_create, name='api_photographer_create'),
    path('api/photographer/<int:staff_id>/', views.api_photographer_get, name='api_photographer_get'),
    path('api/photographer/<int:staff_id>/update/', views.api_photographer_update, name='api_photographer_update'),
    path('api/photographer/<int:staff_id>/delete/', views.api_photographer_delete, name='api_photographer_delete'),
    path('api/photographer/<int:staff_id>/toggle-status/', views.api_photographer_toggle_status, name='api_photographer_toggle_status'),
    path('api/photographer/<int:staff_id>/assign-clients/', views.api_photographer_assign_clients, name='api_photographer_assign_clients'),
    path('api/photographer/client/<int:client_id>/tables/', views.api_photographer_client_tables, name='api_photographer_client_tables'),
    path('api/photographer/<int:staff_id>/set-temp-password/', views.api_photographer_set_temp_password, name='api_photographer_set_temp_password'),
    
    # ID Card Table APIs
    path('api/schemas/', views.api_schema_list, name='api_schema_list'),
    path('api/schemas/create/', views.api_schema_create, name='api_schema_create'),
    path('api/group/<int:group_id>/tables/', views.api_idcard_table_list, name='api_idcard_table_list'),
    path('api/group/<int:group_id>/table/create/', views.api_idcard_table_create, name='api_idcard_table_create'),
    path('api/table/<int:table_id>/', views.api_idcard_table_get, name='api_idcard_table_get'),
    path('api/table/<int:table_id>/update/', views.api_idcard_table_update, name='api_idcard_table_update'),
    path('api/table/<int:table_id>/delete/', views.api_idcard_table_delete, name='api_idcard_table_delete'),
    path('api/table/<int:table_id>/generate-delete-code/', views.api_generate_table_delete_code, name='api_generate_table_delete_code'),
    path('api/table/<int:table_id>/shared-managers/', views.api_table_shared_managers_get, name='api_table_shared_managers_get'),
    path('api/table/<int:table_id>/share-managers/', views.api_table_share_managers, name='api_table_share_managers'),
    path('api/group/<int:group_id>/table/create-from-xlsx/', views.api_create_table_from_xlsx, name='api_create_table_from_xlsx'),
    
    # ID Card APIs
    path('api/table/<int:table_id>/cards/', views.api_idcard_list, name='api_idcard_list'),
    path('api/table/<int:table_id>/cards-json/', views.api_idcard_cards_json, name='api_idcard_cards_json'),
    path('api/table/<int:table_id>/cards/all-ids/', views.api_idcard_all_ids, name='api_idcard_all_ids'),
    path('api/table/<int:table_id>/filter-options/', views.api_idcard_filter_options, name='api_idcard_filter_options'),
    path('api/table/<int:table_id>/card/create/', views.api_idcard_create, name='api_idcard_create'),
    path('api/card/<int:card_id>/', views.api_idcard_get, name='api_idcard_get'),
    path('api/card/<int:card_id>/history/', views.api_idcard_history, name='api_idcard_history'),
    path('api/card/<int:card_id>/update/', views.api_idcard_update, name='api_idcard_update'),
    path('api/card/<int:card_id>/update-field/', views.api_idcard_update_field, name='api_idcard_update_field'),
    path('api/card/<int:card_id>/undo-image/', views.api_idcard_undo_image, name='api_idcard_undo_image'),
    path('api/card/<int:card_id>/redo-image/', views.api_idcard_redo_image, name='api_idcard_redo_image'),
    path('api/image/preview-convert/', views.api_image_preview_convert, name='api_image_preview_convert'),
    path('api/card/<int:card_id>/delete/', views.api_idcard_delete, name='api_idcard_delete'),
    path('api/card/<int:card_id>/status/', views.api_idcard_change_status, name='api_idcard_change_status'),
    path('api/table/<int:table_id>/cards/bulk-status/', views.api_idcard_bulk_status, name='api_idcard_bulk_status'),
    path('api/table/<int:table_id>/cards/bulk-delete/', views.api_idcard_bulk_delete, name='api_idcard_bulk_delete'),
    path('api/table/<int:table_id>/cards/clear-pending-paths/', views.api_clear_pending_paths, name='api_clear_pending_paths'),
    path('api/table/<int:table_id>/cards/generate-delete-code/', views.api_generate_delete_code, name='api_generate_delete_code'),
    path('api/table/<int:table_id>/cards/generate-upgrade-code/', views.api_generate_upgrade_code, name='api_generate_upgrade_code'),
    path('api/table/<int:table_id>/cards/upgrade-classes/', views.api_upgrade_all_classes, name='api_upgrade_all_classes'),
    path('api/table/<int:table_id>/cards/bulk-upload/', views.api_idcard_bulk_upload, name='api_idcard_bulk_upload'),
    path('api/table/<int:table_id>/cards/search/', views.api_idcard_search, name='api_idcard_search'),
    path('api/table/<int:table_id>/status-counts/', views.api_table_status_counts, name='api_table_status_counts'),
    path('api/table/<int:table_id>/cards/download-images/', export_views.api_export_images, name='api_idcard_download_images'),
    path('api/table/<int:table_id>/cards/reupload-images/', views.api_idcard_reupload_images, name='api_idcard_reupload_images'),
    path('api/table/<int:table_id>/cards/class-counts/', views.api_idcard_class_counts, name='api_idcard_class_counts'),
    path('api/table/<int:table_id>/modals-html/', views.api_idcard_modals_html, name='api_idcard_modals_html'),
    path('api/table/<int:table_id>/cards/download-docx/', export_views.api_export_docx, name='api_idcard_download_docx'),
    path('api/table/<int:table_id>/cards/download-xlsx/', export_views.api_export_xlsx, name='api_idcard_download_xlsx'),
    path('api/table/<int:table_id>/cards/download-pdf/', export_views.api_export_pdf, name='api_idcard_download_pdf'),
    path('api/table/<int:table_id>/cards/download-pdf-async/', export_views.api_export_pdf_async, name='api_idcard_download_pdf_async'),
    path('api/export/status/<str:task_id>/', export_views.api_export_status, name='api_export_status'),
    path('api/table/<int:table_id>/cards/download-all/', export_views.api_download_all_cards, name='api_idcard_download_all'),
    
    # Background Task APIs (for async bulk operations)
    path('api/task-status/<int:task_id>/', views.api_task_status, name='api_task_status'),
    path('api/task-download/<int:task_id>/', views.api_task_download, name='api_task_download'),
    path('api/task-cancel/<int:task_id>/', views.api_task_cancel, name='api_task_cancel'),
    path('api/tasks/', views.api_task_list, name='api_task_list'),
    path('api/task-active/', views.api_task_active, name='api_task_active'),
    path('api/task-progress-center/', views.api_task_progress_center, name='api_task_progress_center'),
    path('api/table/<int:table_id>/bulk-upload-task/', views.api_create_bulk_upload_task, name='api_create_bulk_upload_task'),
    path('api/table/<int:table_id>/reupload-task/', views.api_create_reupload_task, name='api_create_reupload_task'),
    path('api/table/<int:table_id>/export-task/', views.api_create_export_task, name='api_create_export_task'),
    
    # Export Settings APIs
    path('api/export-settings/', views.api_export_settings_get, name='api_export_settings_get'),
    path('api/export-settings/update/', views.api_export_settings_update, name='api_export_settings_update'),

    # Export Template APIs
    path('api/export-templates/', views.api_export_templates_list, name='api_export_templates_list'),
    path('api/export-templates/import-doc/', views.api_export_template_import_doc, name='api_export_template_import_doc'),
    path('api/export-templates/create/', views.api_export_template_create, name='api_export_template_create'),
    path('api/export-templates/<int:template_id>/update/', views.api_export_template_update, name='api_export_template_update'),
    path('api/export-templates/<int:template_id>/delete/', views.api_export_template_delete, name='api_export_template_delete'),

    # Activity Logs API
    path('api/activity-logs/', views.api_activity_logs, name='api_activity_logs'),
    path('api/activity-logs/clear/state/', views.api_activity_log_clear_state, name='api_activity_log_clear_state'),
    path('api/activity-logs/clear/generate-code/', views.api_activity_log_clear_generate_code, name='api_activity_log_clear_generate_code'),
    path('api/activity-logs/clear/', views.api_clear_activity_logs, name='api_clear_activity_logs'),

    # Pro User data deletion guard API
    path('api/pro-user/guest-users/', views.api_pro_user_guest_users, name='api_pro_user_guest_users'),
    path('api/pro-user/guest-users/clients/', views.api_pro_user_guest_source_clients, name='api_pro_user_guest_source_clients'),
    path('api/pro-user/guest-users/create/', views.api_pro_user_guest_user_create, name='api_pro_user_guest_user_create'),
    path('api/pro-user/guest-users/convert/', views.api_pro_user_guest_user_convert, name='api_pro_user_guest_user_convert'),
    path('api/pro-user/guest-users/restore/', views.api_pro_user_guest_user_restore, name='api_pro_user_guest_user_restore'),

    # Manage Passwords / Temp PIN APIs
    path('api/panel/temp-passwords/', views.api_manage_temp_passwords_list, name='api_manage_temp_passwords_list'),
    path('api/panel/temp-passwords/reset/', views.api_manage_temp_password_reset, name='api_manage_temp_password_reset'),
    path('api/panel/temp-passwords/resend-email/', views.api_manage_temp_password_resend_email, name='api_manage_temp_password_resend_email'),

    # Settings/Profile APIs (for all user types)
    path('api/profile/', views.api_get_profile, name='api_get_profile'),
    path('api/profile/update/', views.api_update_profile, name='api_update_profile'),
    path('api/profile/change-password/', views.api_change_password, name='api_change_password'),
    path('api/profile/security-settings/update/', views.api_update_security_settings, name='api_update_security_settings'),
    path('api/profile/upload-image/', views.api_upload_profile_image, name='api_upload_profile_image'),
    path('api/profile/remove-image/', views.api_remove_profile_image, name='api_remove_profile_image'),

    # Health / Version
    path('api/health/', views.api_health, name='api_health'),

    # Allowed transitions for a card (any authenticated user)
    path('api/card/<int:card_id>/allowed-transitions/', views.api_card_allowed_transitions, name='api_card_allowed_transitions'),

    # Client-side error reporting (from error-monitor.js)
    path('api/client-errors/', views.api_client_errors, name='api_client_errors'),

    # Monitoring dashboard data (super_admin only)
    path('api/monitoring/', views.api_monitoring_data, name='api_monitoring_data'),
    path('api/operations-feed/', views.api_operations_feed, name='api_operations_feed'),
    path('api/server-info/', views.api_server_info_snapshot, name='api_server_info_snapshot'),
    path('', include('stats.urls')),
]

# Debug endpoints — only available when DEBUG=True
from django.conf import settings as _settings
if _settings.DEBUG:
    urlpatterns += [
        path('api/debug/permissions/', views.api_debug_permissions, name='api_debug_permissions'),
        path('api/debug/workflow-check/', views.api_debug_workflow, name='api_debug_workflow'),
        path('api/debug/image-integrity/', views.api_debug_image_integrity, name='api_debug_image_integrity'),
    ]
