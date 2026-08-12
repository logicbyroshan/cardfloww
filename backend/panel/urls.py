"""
Panel app URL configuration
============================

All these routes are mounted at /panel/ via config/urls.py
(path('panel/', include('core.urls')) already covers them).

This file exists so the panel app owns its routes cleanly.
It is included by core/urls.py via include('panel.urls'),
keeping the actual /panel/ prefix unchanged.
"""

from django.urls import path
from panel import views

urlpatterns = [
    # ── Manage Panel page ─────────────────────────────────────────────
    path('manage-panel/', views.manage_panel, name='manage_panel_app'),
    path('api/email-logs/', views.api_email_logs, name='api_email_logs_app'),
    path('api/email-resend/<int:log_id>/', views.api_email_resend, name='api_email_resend_app'),
    path('api/email-send/', views.api_email_send_new, name='api_email_send_new_app'),
    path('api/email-compose-defaults/', views.api_email_compose_defaults, name='api_email_compose_defaults_app'),

    # ── Notifications page (all users) ───────────────────────────────
    path('notifications/', views.notifications_page, name='notifications_page_app'),

    # ── User-facing notification APIs ─────────────────────────────────
    path('api/notifications/list/', views.api_notifications_list, name='api_notifications_list_app'),
    path('api/notifications/unread-count/', views.api_notifications_unread_count, name='api_notifications_unread_count_app'),
    path('api/notifications/<int:notification_id>/read/', views.api_notification_mark_read, name='api_notification_mark_read_app'),
    path('api/notifications/mark-all-read/', views.api_notifications_mark_all_read, name='api_notifications_mark_all_read_app'),

    # ── Admin notification management ─────────────────────────────────
    path('api/notifications/admin/list/', views.api_panel_notifications_list, name='api_panel_notifications_list_app'),
    path('api/notifications/admin/create/', views.api_panel_notification_create, name='api_panel_notification_create_app'),
    path('api/notifications/admin/<int:notification_id>/delete/', views.api_panel_notification_delete, name='api_panel_notification_delete_app'),
    path('api/notifications/admin/target-users/', views.api_panel_target_users, name='api_panel_target_users_app'),

    # ── Backup ────────────────────────────────────────────────────────
    path('backup/select-clients/', views.backup_select_clients, name='backup_select_clients_app'),
    path('api/backup/generate-code/', views.api_backup_generate_code, name='api_backup_generate_code_app'),
    path('api/backup/initiate/', views.api_backup_initiate, name='api_backup_initiate_app'),
    path('api/backup/start/', views.api_backup_start, name='api_backup_start_app'),
    path('api/backup/list/', views.api_backup_list, name='api_backup_list_app'),
    path('api/backup/status/<int:task_id>/', views.api_backup_status, name='api_backup_status_app'),
    path('api/backup/<int:task_id>/delete-now/', views.api_backup_delete_now, name='api_backup_delete_now_app'),
    path('api/backup/download/<int:task_id>/', views.api_backup_download, name='api_backup_download_app'),

    # ── Monitoring ────────────────────────────────────────────────────
    path('api/client-errors/', views.api_client_errors, name='api_client_errors_app'),
    path('api/monitoring/', views.api_monitoring_data, name='api_monitoring_data_app'),
    path('api/operations-feed/', views.api_operations_feed, name='api_operations_feed_app'),
    path('api/activity-logs/clear/state/', views.api_activity_log_clear_state, name='api_activity_log_clear_state_app'),
    path('api/activity-logs/clear/generate-code/', views.api_activity_log_clear_generate_code, name='api_activity_log_clear_generate_code_app'),
    path('api/activity-logs/clear/', views.api_clear_activity_logs, name='api_clear_activity_logs_app'),
    path('api/server-info/', views.api_server_info_snapshot, name='api_server_info_snapshot_app'),
]
