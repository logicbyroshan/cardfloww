"""
Base helpers — shared helper functions, decorators, and constants.
Split from base.py for maintainability.
"""
from functools import wraps
import json
import logging
from django.conf import settings as django_settings
from django.core.cache import cache
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Max, Q
from django.utils import timezone
from organisation.models import Organisation
from tables.models import Table, IDCard
from ..models import User, SystemSettings, Notification, ActivityLog
from ..services import IDCardService
from ..services.activity_service import ActivityService
from ..utils.htmx import is_htmx
from ..services.permission_service import (
    PermissionService,
    require_any_admin,
    require_super_admin as _require_super_admin,
    api_require_any_admin,
    api_require_any_authenticated,
)

logger = logging.getLogger(__name__)

# ============================================================================
# DISPLAY LIMITS
# ============================================================================
ACTIVITY_FEED_MAX = 100
GLOBAL_SEARCH_DB_LIMIT = 100
GLOBAL_SEARCH_RESULT_LIMIT = 50

def get_user_role(user):
    """Helper function to get user role display name"""
    role = user.get_role_display()
    if role == 'Client Staff':
        return 'Assistant'
    return role


def get_page_range(page_obj, window=2):
    """
    Return a list of page numbers (and '...' for gaps) for the paginator.
    e.g. [1, '...', 4, 5, 6, '...', 10] for page 5 of 10 with window=2.
    """
    num_pages = page_obj.paginator.num_pages
    current = page_obj.number
    pages = []
    if num_pages <= (2 * window + 5):
        return list(range(1, num_pages + 1))
    # Always show first page
    pages.append(1)
    if current - window > 2:
        pages.append('...')
    for p in range(max(2, current - window), min(num_pages, current + window + 1)):
        pages.append(p)
    if current + window < num_pages - 1:
        pages.append('...')
    if num_pages not in pages:
        pages.append(num_pages)
    return pages


def enrich_cards(cards, table_fields, start_index=0):
    """
    Enrich a list/queryset of IDCard objects with ordered field values.
    Returns a list of dicts ready for template rendering.
    """
    enriched = []
    for idx, card in enumerate(cards):
        ordered_fields = []
        field_data = card.field_data or {}
        field_data_normalized = {k.upper(): v for k, v in field_data.items()}
        for field in table_fields:
            field_name = field['name']
            field_type = field['type']
            field_value = field_data.get(field_name, '') or field_data_normalized.get(field_name.upper(), '')
            ordered_fields.append({
                'name': field_name,
                'type': field_type,
                'value': field_value,
            })
        enriched.append({
            'id': card.id,
            'sr_no': start_index + idx + 1,
            'photo': card.photo,
            'status': card.status,
            'get_status_display': card.get_status_display(),
            'updated_at': card.updated_at,
            'downloaded_at': card.downloaded_at,
            'deleted_at': card.deleted_at,
            'ordered_fields': ordered_fields,
        })
    return enriched


def super_admin_required(view_func):
    """
    Deprecated — delegates to require_super_admin from permission_service.
    Kept for backward-compatible imports; will be removed in a future version.
    """
    import warnings
    warnings.warn(
        "super_admin_required is deprecated. "
        "Use 'from core.services.permission_service import require_super_admin' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _require_super_admin(view_func)


# ────────────────────────────────────────────────────────────
# Shared constant: status → permission mapping
# Used by admin idcard_actions() and client client_idcard_actions()
# ────────────────────────────────────────────────────────────
_STATUS_LIST_PERM = {
    'pending': 'perm_idcard_pending_list',
    'verified': 'perm_idcard_verified_list',
    'approved': 'perm_idcard_approved_list',
    'download': 'perm_idcard_download_list',
    'reprint': 'perm_idcard_reprint_list',
    'pool': 'perm_idcard_pool_list',
}
_VALID_STATUSES = list(_STATUS_LIST_PERM.keys())
