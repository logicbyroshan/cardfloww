"""
Client Views — barrel re-export module for organisation APIs.
"""
from .views_decorators import (
    require_client_user,
    require_client_admin,
)

from .views_api import (
    api_dashboard_data,
    api_messages_drawer,
    api_groups_list,
    api_reprint_history,
    api_staff_list_create,
    api_staff_detail,
    api_staff_toggle_status,
    api_staff_set_temp_password,
    api_client_groups_list,
    api_class_section_options,
    api_tables_list,
    api_cards_list,
    api_card_detail,
    api_card_change_status,
    api_cards_bulk_status,
    api_upload_images,
    client_api_create_table_from_xlsx,
)
