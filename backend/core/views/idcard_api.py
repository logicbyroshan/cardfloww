"""
ID Card API — barrel re-export.

Split into:
- idcard_helpers: shared helpers, scoping, field utilities
- idcard_table_api: table CRUD + XLSX import
- idcard_card_api: card CRUD, status, search, filter
- idcard_bulk_api: bulk upload, reupload, modals
"""
from .idcard_helpers import (
    _safe_error,
    _build_class_filter_q,
    _get_class_section_field_names,
    _get_class_variant_map,
    invalidate_class_variant_cache,
    _access_denied_response,
    _check_client_scope_by_group,
    _check_client_scope_by_table,
    _check_client_scope_by_card,
    _CLIENT_READONLY_STATUSES,
    _client_readonly_response,
    _is_client_readonly,
    validate_image_bytes,
    NUMERIC_TO_ROMAN,
    VALID_CLASS_VALUES,
    CLASS_UPGRADE_MAP,
)

from .idcard_table_api import (
    api_idcard_table_create,
    api_idcard_table_get,
    api_idcard_table_update,
    api_idcard_table_delete,
    api_generate_table_delete_code,
    api_idcard_table_toggle_status,
    api_idcard_table_list,
    api_create_table_from_xlsx,
)

from .idcard_card_api import (
    api_image_preview_convert,
    api_idcard_list,
    api_idcard_cards_json,
    api_idcard_all_ids,
    api_idcard_filter_options,
    api_idcard_class_counts,
    api_idcard_create,
    api_idcard_get,
    api_idcard_history,
    api_idcard_update,
    api_idcard_delete,
    api_idcard_update_field,
    api_idcard_undo_image,
    api_idcard_redo_image,
    api_idcard_change_status,
    api_idcard_bulk_status,
    api_idcard_bulk_delete,
    api_clear_pending_paths,
    api_generate_delete_code,
    api_generate_upgrade_code,
    api_upgrade_all_classes,
    api_idcard_search,
    api_table_status_counts,
)

from .idcard_bulk_api import (
    api_idcard_bulk_upload,
    api_idcard_reupload_images,
    api_idcard_modals_html,
)
