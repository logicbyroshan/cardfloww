# Views Package - Split for better organization and debugging
# Import all views from sub-modules to maintain backward compatibility

from .auth import (
    login_view,
    logout_view,
    inactive_view,
    maintenance_view,
    api_check_maintenance,
    api_check_email,
    api_login,
    api_auth_me,
    api_forgot_password,
    api_verify_otp,
    api_reset_password,
    api_impersonate_start,
    api_impersonate_stop,
    api_impersonate_users,
    api_user_audit_users,
    api_user_audit_history,
    api_user_audit_actions,
    admin_staff_dashboard,
    client_dashboard,
    client_staff_dashboard,
)

from .base import (
    get_user_role,
    super_admin_required,
    login_as_user_page,
    pro_user_activity_logs_page,
    pro_user_activity_logs_detail_page,
    pro_user_guest_users_page,
    pro_user_batch_jobs_page,
    dashboard,
    api_presence_track,
    api_live_client_presence,
    api_global_search,
    api_dashboard_card_stats,
    api_recent_client_updates,
    api_reprint_overview,
    api_recent_activity,
    api_health,
    api_debug_permissions,
    api_debug_workflow,
    api_debug_image_integrity,
    api_card_allowed_transitions,
    manage_staff,
    manage_client_staff,
    manage_clients,
    active_clients,
    active_client_status_redirect,
    api_staff_login_history,
    api_client_login_history,
    api_client_staff_login_history,
    api_staff_assignment_timeline,
    api_client_staff_assignment_timeline,
    idcard_group,
    idcard_actions,
    group_settings,
    manage_panel,
    api_email_logs,
    api_email_resend,
    api_email_send_new,
    api_email_compose_defaults,
    settings,
    tutorial,
    tutorial_personal_guide,
    tutorial_personal_guide_download,
    api_export_settings_get,
    api_export_settings_update,
    api_export_templates_list,
    api_export_template_import_doc,
    api_export_template_create,
    api_export_template_update,
    api_export_template_delete,
    api_activity_logs,
    notifications_page,
)
 

from .client_api import *  # noqa: F401,F403

from .staff_api import (
    api_staff_create,
    api_staff_get,
    api_staff_update,
    api_staff_delete,
    api_staff_toggle_status,
    api_active_clients_list,
    api_all_clients_for_assignment,
    api_staff_set_temp_password,
)

from .idcard_table_api import (
    api_schema_list,
    api_schema_create,
    api_idcard_table_create,
    api_idcard_table_get,
    api_idcard_table_update,
    api_idcard_table_delete,
    api_generate_table_delete_code,
    api_idcard_table_toggle_status,
    api_idcard_table_list,
    api_create_table_from_xlsx,
)

from .idcard_api import (
    api_image_preview_convert,
    api_idcard_list,
    api_idcard_cards_json,
    api_idcard_create,
    api_idcard_get,
    api_idcard_history,
    api_idcard_update,
    api_idcard_update_field,
    api_idcard_undo_image,
    api_idcard_redo_image,
    api_idcard_delete,
    api_idcard_change_status,
    api_idcard_bulk_status,
    api_idcard_bulk_delete,
    api_clear_pending_paths,
    api_generate_delete_code,
    api_generate_upgrade_code,
    api_upgrade_all_classes,
    api_idcard_search,
    api_idcard_all_ids,
    api_idcard_filter_options,
    api_idcard_class_counts,
    api_table_status_counts,
    api_idcard_bulk_upload,
    api_idcard_reupload_images,
    api_idcard_modals_html,
    invalidate_class_variant_cache,
)

from .settings_api import (
    api_get_profile,
    api_update_profile,
    api_change_password,
    api_update_security_settings,
    api_upload_profile_image,
    api_remove_profile_image,
)

# NOTE: Reprint API views moved to 'reprintcard' app

from .task_api import (
    api_task_status,
    api_task_download,
    api_task_cancel,
    api_task_list,
    api_task_active,
    api_task_progress_center,
    api_create_bulk_upload_task,
    api_create_reupload_task,
    api_create_export_task,
)

from .monitoring_api import (
    api_activity_log_clear_generate_code,
    api_activity_log_clear_state,
    api_client_errors,
    api_clear_activity_logs,
    api_monitoring_data,
    api_operations_feed,
    api_server_info_snapshot,
)

from .backup_api import (
    backup_select_clients,
    api_backup_initiate,
    api_backup_start,
    api_backup_status,
    api_backup_list,
    api_backup_delete_now,
    api_backup_download,
    api_backup_generate_code,
)

from .notification_api import (
    api_notifications_list,
    api_notifications_unread_count,
    api_notification_mark_read,
    api_notifications_mark_all_read,
    api_client_message_strip,
    api_panel_notifications_list,
    api_panel_notification_create,
    api_panel_notification_delete,
    api_panel_target_users,
)

from .maintenance_api import (
    api_system_maintenance_check,
    api_maintenance_toggle,
    system_maintenance_page,
)


from .pro_user_guest_users_api import (
    api_pro_user_guest_users,
    api_pro_user_guest_source_clients,
    api_pro_user_guest_user_create,
    api_pro_user_guest_user_convert,
    api_pro_user_guest_user_restore,
)

from .errors import (
    mobile_download_page,
)

from .photographer_api import (
    manage_photographers,
    api_photographer_create,
    api_photographer_get,
    api_photographer_update,
    api_photographer_delete,
    api_photographer_toggle_status,
    api_photographer_assign_clients,
    api_photographer_client_tables,
    api_photographer_set_temp_password,
)

