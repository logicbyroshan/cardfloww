"""
Client Views — barrel re-export module.

Individual view functions live in their own files for modularity.
Import from here for backward compatibility with urls.py.
"""
from .views_decorators import (
    require_client_user,
    require_client_admin,
)

from .views_pages import (
    dashboard,
    card_groups,
    card_table,
    print_table,
    manage_staff,
    messages,
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
)

from .views_shared_pages import (
    client_idcard_group,
    client_idcard_actions,
    client_group_settings,
    client_api_create_table_from_xlsx,
)

from reprintcard.views import reprint_cards
