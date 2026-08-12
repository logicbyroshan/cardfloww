# Panel views package
# Re-exports all panel views for use by panel/urls.py

from .manage_panel_views import (
    manage_panel,
    api_email_logs,
    api_email_resend,
    api_email_send_new,
    api_email_compose_defaults,
    notifications_page,
)

from .backup_views import (
    backup_select_clients,
    api_backup_generate_code,
    api_backup_initiate,
    api_backup_start,
    api_backup_status,
    api_backup_list,
    api_backup_delete_now,
    api_backup_download,
)

from .notification_views import (
    api_notifications_list,
    api_notifications_unread_count,
    api_notification_mark_read,
    api_notifications_mark_all_read,
    api_panel_notifications_list,
    api_panel_notification_create,
    api_panel_notification_delete,
    api_panel_target_users,
)

from .monitoring_views import (
    api_activity_log_clear_generate_code,
    api_activity_log_clear_state,
    api_client_errors,
    api_clear_activity_logs,
    api_monitoring_data,
    api_operations_feed,
    api_server_info_snapshot,
)
