"""
ID Card API — shared helpers, scoping, and field utilities.

Contains:
- Error helpers: _safe_error
- Query helpers: _build_class_filter_q, _get_class_section_field_names, _get_class_section_course_branch_field_names
- Scoping helpers: _access_denied_response, _check_client_scope_by_group/table/card
- Client readonly helpers: _CLIENT_READONLY_STATUSES, _client_readonly_response, _is_client_readonly
- Field utility re-exports from core.utils.field_utils
"""
import json
import logging
import os
import re

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.conf import settings
from django.core.cache import cache as django_cache

from tables.models import Table, IDCard
from ..services import IDCardService
from mediafiles.services import ImageService
from ..services.base import BaseService
from ..services.activity_service import ActivityService
from ..services.permission_service import (
    PermissionService,
    api_require_any_authenticated,
    api_require_permission,
)
from tables.services_workflow import WorkflowService
from ..utils.upload_security import validate_zip_safety

# Logger for this module
logger = logging.getLogger(__name__)


def _normalized_field_tokens(name):
    """Split a field name into lowercase alphanumeric tokens."""
    raw = str(name or '').strip().lower()
    if not raw:
        return set()
    return {tok for tok in re.split(r'[^a-z0-9]+', raw) if tok}


def _normalized_assigned_table_ids(staff):
    """Return sanitized positive integer table IDs from staff assignment."""
    return [
        int(v) for v in (getattr(staff, 'assigned_table_ids', None) or [])
        if str(v).strip().isdigit() and int(v) > 0
    ]


def _dedupe_scope_values(values):
    """Normalize scope filter values preserving first-seen order."""
    out = []
    seen = set()
    for value in values or []:
        text = str(value).strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(text)
    return out


def _assigned_group_ids_for_access(staff):
    """Return group IDs that explicitly grant group-level access."""
    scopes = getattr(staff, 'assignment_scopes', None)
    if isinstance(scopes, list) and scopes:
        group_ids = []
        seen = set()
        has_any_valid_scope = False

        for scope in scopes:
            if not isinstance(scope, dict):
                continue
            stype = str(scope.get('scope_type', '') or '').strip().lower()
            if stype not in ('group', 'table'):
                continue
            has_any_valid_scope = True
            if stype != 'group':
                continue

            sid = scope.get('scope_id')
            try:
                sid_int = int(str(sid).strip())
            except (TypeError, ValueError):
                continue
            if sid_int <= 0 or sid_int in seen:
                continue
            seen.add(sid_int)
            group_ids.append(sid_int)

        if has_any_valid_scope:
            return group_ids

    return list(staff.assigned_groups.values_list('id', flat=True))


def _table_is_assigned_to_staff(staff, table):
    """Allow table if assigned by table ID OR by owning group ID."""
    assigned_table_ids = set(_normalized_assigned_table_ids(staff))
    assigned_group_ids = set(_assigned_group_ids_for_access(staff))

    if not assigned_table_ids and not assigned_group_ids:
        return True
    table_id = int(table.id)
    if assigned_table_ids and table_id in assigned_table_ids:
        return True
    if assigned_group_ids and table_id in assigned_group_ids:
        return True
    return False


def _table_scope_filters_for_staff(staff, table):
    """Return a list of scope groups for the table.
    
    Each group: {'classes': [], 'sections': [], 'branches': []}
    Multiple groups are interpreted as OR-ed filters.
    Within a group, filters are AND-ed.
    """
    scopes = getattr(staff, 'assignment_scopes', None)
    if not isinstance(scopes, list) or not scopes:
        # Fallback to legacy fields (interpreted as a single scope)
        return [{
            'classes': _dedupe_scope_values(staff.allowed_classes or []),
            'sections': _dedupe_scope_values(staff.allowed_sections or []),
            'branches': _dedupe_scope_values(staff.allowed_branches or []),
        }]

    matched = []
    for scope in scopes:
        if not isinstance(scope, dict):
            continue
        stype = str(scope.get('scope_type', '') or '').strip().lower()
        scope_id = scope.get('scope_id')
        try:
            scope_id = int(str(scope_id).strip())
        except (TypeError, ValueError):
            continue

        if stype == 'table' and scope_id == int(table.id):
            matched.append(scope)
        elif stype == 'group' and scope_id == int(table.group_id):
            matched.append(scope)

    if not matched:
        # Fallback to legacy fields
        return [{
            'classes': _dedupe_scope_values(staff.allowed_classes or []),
            'sections': _dedupe_scope_values(staff.allowed_sections or []),
            'branches': _dedupe_scope_values(staff.allowed_branches or []),
        }]

    return [{
        'classes': _dedupe_scope_values(s.get('classes') or []),
        'sections': _dedupe_scope_values(s.get('sections') or []),
        'branches': _dedupe_scope_values(s.get('branches') or []),
    } for s in matched]


def _table_scope_values_for_staff(staff, table, key):
    """Flatten matching scope values for a single scope key across all matched scopes."""
    values = []
    for scope in _table_scope_filters_for_staff(staff, table):
        values.extend(scope.get(key) or [])
    return _dedupe_scope_values(values)


def _safe_error(e, fallback='An error occurred. Please try again.'):
    """Return a safe error message for API responses. Logs the real exception."""
    logger.exception("API error: %s", e)
    return fallback


def _get_class_variant_map(table_id, class_field_name):
    """Build mapping: canonical → [raw_variants] for a table."""
    
    from django.db.models.fields.json import KeyTextTransform
    from django.db.models.functions import Cast
    from django.db.models import CharField
    from core.utils.field_utils import normalize_class_value
    from collections import defaultdict
    
    # Query ALL distinct raw class values from the table (no status filter)
    all_raw = list(
        IDCard.objects.filter(table_id=table_id)
        .annotate(_cv_raw=Cast(KeyTextTransform(class_field_name, 'field_data'), CharField()))
        .exclude(_cv_raw__isnull=True).exclude(_cv_raw='')
        .order_by()
        .values_list('_cv_raw', flat=True).distinct()
    )
    
    # Build canonical → [raw_variants] map
    variant_map = defaultdict(list)
    for raw in all_raw:
        canonical = normalize_class_value(raw)
        variant_map[canonical].append(raw)

    return dict(variant_map)


def invalidate_class_variant_cache(table_id):
    """Best-effort cleanup for legacy class-variant cache keys."""
    # Class variants are now computed live; this keeps backward compatibility
    # with any leftover cache keys from older deployments.
    from tables.models import Table
    try:
        table = Table.objects.select_related().get(id=table_id)
        class_field, _ = _get_class_section_field_names(table)
        if class_field:
            django_cache.delete(f'class_variants_map:{table_id}:{class_field}')
    except Exception:
        pass  # Best effort


def invalidate_filter_options_cache(table_id):
    """Invalidate class/section filter-options cache for a table."""
    try:
        version_key = f'filter_options_version:{table_id}'
        try:
            django_cache.incr(version_key)
        except Exception:
            current = django_cache.get(version_key, 1)
            try:
                current = int(current)
            except Exception:
                current = 1
            django_cache.set(version_key, current + 1, None)

        # Best-effort cleanup for any non-versioned key readers.
        django_cache.delete(f'filter_options:{table_id}')
    except Exception:
        pass  # Best effort


def _build_class_filter_q(qs, class_filter, class_field_name):
    """Apply class filter with canonical normalization.

    Uses cached canonical→raw mapping to avoid scanning distinct values
    on every request. Finds all raw variants that normalize to the same
    canonical value as the filter, then matches them with __in.
    """
    from django.db.models.fields.json import KeyTextTransform
    from django.db.models.functions import Cast
    from django.db.models import CharField
    from django.db.models import Q
    from core.utils.field_utils import normalize_class_value

    norm_filter = normalize_class_value(class_filter)
    
    # Get table_id from the queryset (assumes qs is filtered by table)
    # The queryset is already filtered by table in the calling code
    try:
        table_id = qs.query.where.children[0].rhs  # table_id from filter(table=table)
    except Exception:
        table_id = None
    
    # If we can get table_id, use cached variant map
    if table_id:
        variant_map = _get_class_variant_map(table_id, class_field_name)
        matching_raw = variant_map.get(norm_filter, [])
    else:
        # Fallback: scan distinct values (slow path)
        from django.db.models.functions import Cast
        from django.db.models import CharField
        all_raw = list(
            qs.annotate(_cv_raw=Cast(KeyTextTransform(class_field_name, 'field_data'), CharField()))
            .exclude(_cv_raw__isnull=True).exclude(_cv_raw='')
            .order_by()
            .values_list('_cv_raw', flat=True).distinct()
        )
        matching_raw = [r for r in all_raw if normalize_class_value(r) == norm_filter]

    if not matching_raw:
        return qs.none()

    # Build filter: match any of the raw variants as plain text.
    # Using KeyTextTransform directly can produce JSON_EXTRACT comparisons,
    # which fail on non-JSON literals like roman classes (e.g. "III").
    qs = qs.annotate(_cls=Cast(KeyTextTransform(class_field_name, 'field_data'), CharField()))
    q = Q()
    for raw in matching_raw:
        q |= Q(_cls=raw)
    return qs.filter(q)


def _get_class_section_field_names(table):
    """Extract class and section field names from a table's field definitions.

    Matches by type OR by name (mirrors Table.has_class_field / has_section_field).
    Returns (class_field_name, section_field_name) — either may be None.
    """
    class_field, section_field, _course_field, _branch_field = _get_class_section_course_branch_field_names(table)
    return class_field, section_field


def _get_class_section_course_branch_field_names(table):
    """Extract class, section, course, and branch field names from table fields.

    Matching is based on explicit field types when present, otherwise tokenized
    field-name variants commonly used in school/college datasets.
    """
    class_field = None
    section_field = None
    course_field = None
    branch_field = None

    class_tokens = {'class', 'std', 'standard', 'grade'}
    section_tokens = {'section', 'sec', 'div', 'division'}
    course_tokens = {'course', 'program', 'programme'}
    branch_tokens = {'branch', 'stream', 'dept', 'department'}

    for field in (table.fields or []):
        ftype = str(field.get('type', '') or '').strip().lower()
        fname = str(field.get('name', '') or '').strip()
        tokens = _normalized_field_tokens(fname)

        if not class_field and (ftype == 'class' or bool(tokens & class_tokens)):
            class_field = fname
            continue

        if not section_field and (ftype == 'section' or bool(tokens & section_tokens)):
            section_field = fname
            continue

        if not course_field and (ftype == 'course' or bool(tokens & course_tokens)):
            course_field = fname
            continue

        if not branch_field and (ftype == 'branch' or bool(tokens & branch_tokens)):
            branch_field = fname

    return class_field, section_field, course_field, branch_field


def _get_class_section_branch_field_names(table):
    """Extract class, section, and branch-like field names from table fields.

    Branch-like fields are matched by type='branch' OR common field-name
    variants used by college datasets (branch/stream/course).
    """
    class_field, section_field, course_field, branch_field = _get_class_section_course_branch_field_names(table)

    # Backward compatibility: legacy branch scope may target course-like fields.
    if not branch_field:
        branch_field = course_field

    return class_field, section_field, branch_field


def invalidate_table_distinct_cache(table_id):
    """Invalidate class, section, branch, duplicate, and filter options cache keys for a table."""
    if not table_id:
        return
    from django.core.cache import cache
    cache.delete(f"table_distinct_fields:{table_id}:class")
    cache.delete(f"table_distinct_fields:{table_id}:section")
    cache.delete(f"table_distinct_fields:{table_id}:branch")
    cache.delete(f"tbl_dups:{table_id}")
    cache.delete(f"filter_opts:{table_id}")


def _get_distinct_field_values_cached(table, field_key, variants):
    """Retrieve distinct field values for class, section, or branch using cache."""
    if not table or not table.id or not variants:
        return []
    from django.core.cache import cache
    cache_key = f"table_distinct_fields:{table.id}:{field_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Query distinct values from the database
    from tables.models import IDCard
    from django.db.models.fields.json import KeyTextTransform
    from django.db.models.functions import Cast, Coalesce
    from django.db.models import CharField, Value

    coalesce_annotation = Coalesce(
        *[Cast(KeyTextTransform(v, 'field_data'), CharField()) for v in variants],
        Value(''),
        output_field=CharField()
    )

    raw_values = list(
        IDCard.objects.filter(table=table)
        .annotate(_temp_val=coalesce_annotation)
        .exclude(_temp_val='')
        .order_by()
        .values_list('_temp_val', flat=True)
        .distinct()
    )

    # Cache for 1 hour
    cache.set(cache_key, raw_values, 3600)
    return raw_values


def _apply_client_staff_row_scope(qs, user, table, status_filter=None):
    """Apply client_staff-specific row-level scope to an IDCard queryset.

    Scope rules:
    - Multiple scope entries are OR-ed together.
    - Inside a scope entry, class/section/branch are AND-ed.
    - If a scope entry is empty (no filters), it grants access to the full table.
    - when status_filter='pool', row-level scope is bypassed (shared visibility).
    """
    if not PermissionService.is_client_staff(user):
        return qs

    # Do not bypass scoping for pool status so assistants are strictly restricted to their assigned classes/sections
    # if status_filter == 'pool':
    #     return qs

    from assistants.models import Assistant
    staff = (
        getattr(user, 'assistant_profile', None)
        or getattr(user, 'staff_profile', None)
        or Assistant.objects.filter(user=user).first()
    )
    if not staff:
        return qs.none()

    if not _table_is_assigned_to_staff(staff, table):
        return qs.none()

    scope_groups = _table_scope_filters_for_staff(staff, table)
    
    from django.db.models.fields.json import KeyTextTransform
    from django.db.models.functions import Cast, Coalesce
    from django.db.models import CharField, Q, Value
    from core.utils.field_utils import normalize_class_value, normalize_compact_text_value

    class_field, section_field, branch_field = _get_class_section_branch_field_names(table)

    def _get_case_variants(field_name):
        if not field_name: return []
        variants = [field_name]
        v_low = field_name.lower()
        v_up = field_name.upper()
        v_cap = field_name.capitalize()
        for v in [v_low, v_up, v_cap]:
            if v not in variants: variants.append(v)
        return variants

    # Annotate with case-insensitive variants for robustness
    annotations = {}
    if class_field:
        variants = _get_case_variants(class_field)
        annotations['_scope_cls'] = Coalesce(
            *[Cast(KeyTextTransform(v, 'field_data'), CharField()) for v in variants],
            Value(''),
            output_field=CharField()
        )
    if section_field:
        variants = _get_case_variants(section_field)
        annotations['_scope_sec'] = Coalesce(
            *[Cast(KeyTextTransform(v, 'field_data'), CharField()) for v in variants],
            Value(''),
            output_field=CharField()
        )
    if branch_field:
        variants = _get_case_variants(branch_field)
        annotations['_scope_branch'] = Coalesce(
            *[Cast(KeyTextTransform(v, 'field_data'), CharField()) for v in variants],
            Value(''),
            output_field=CharField()
        )

    if annotations:
        qs = qs.annotate(**annotations)

    final_q = Q()

    for scope in scope_groups:
        scope_q = Q()
        has_any_filter = False
        
        # Classes
        if scope['classes'] and class_field:
            has_any_filter = True
            normalized_allowed = {normalize_class_value(v) for v in scope['classes'] if normalize_class_value(v)}
            if normalized_allowed:
                # Retrieve from cache to avoid heavy JSON distinct query on every request
                raw_values = _get_distinct_field_values_cached(
                    table, 'class', _get_case_variants(class_field)
                )
                matching_raw = [raw for raw in raw_values if normalize_class_value(raw) in normalized_allowed]
                if matching_raw:
                    scope_q &= Q(_scope_cls__in=matching_raw)
                else:
                    scope_q &= Q(id__isnull=True) # Forces empty if no match found for this mandatory filter
            else:
                scope_q &= Q(id__isnull=True)

        # Sections
        if scope['sections'] and section_field:
            has_any_filter = True
            allowed_normalized = {str(s).strip().upper() for s in scope['sections'] if str(s).strip()}
            if allowed_normalized:
                # Retrieve from cache to avoid heavy JSON distinct query on every request
                raw_values = _get_distinct_field_values_cached(
                    table, 'section', _get_case_variants(section_field)
                )
                matching_raw = [raw for raw in raw_values if str(raw).strip().upper() in allowed_normalized]
                if matching_raw:
                    scope_q &= Q(_scope_sec__in=matching_raw)
                else:
                    scope_q &= Q(id__isnull=True)
            else:
                scope_q &= Q(id__isnull=True)

        # Branches
        if scope['branches'] and branch_field:
            has_any_filter = True
            normalized_allowed = {normalize_compact_text_value(v) for v in scope['branches'] if normalize_compact_text_value(v)}
            if normalized_allowed:
                # Retrieve from cache to avoid heavy JSON distinct query on every request
                raw_values = _get_distinct_field_values_cached(
                    table, 'branch', _get_case_variants(branch_field)
                )
                matching_raw = [raw for raw in raw_values if normalize_compact_text_value(raw) in normalized_allowed]
                if matching_raw:
                    scope_q &= Q(_scope_branch__in=matching_raw)
                else:
                    scope_q &= Q(id__isnull=True)
            else:
                scope_q &= Q(id__isnull=True)

        if not has_any_filter:
            # An empty scope entry grants access to the full table.
            scope_q = Q()

        # OR this scope's requirements to the final Q
        final_q |= scope_q

    if not final_q:
        # If we got here and have no Q, it means all scopes were invalid/empty
        return qs.none()

    return qs.filter(final_q)


# ==================== ADMIN STAFF CLIENT SCOPING ====================
# Ensures admin_staff can only access data belonging to their assigned clients.

def _access_denied_response():
    """Factory: return a fresh 403 JsonResponse per request (thread-safe)."""
    return JsonResponse(
        {'success': False, 'message': 'Access denied. You are not assigned to this client.'},
        status=403,
    )

def _check_client_scope_by_group(user, group_id):
    """Check user has access to the client owning this group. Returns (group, error_response).
    
    Delegates to PermissionService.can_access_client() (single authority).
    """
    group = get_object_or_404(Table, id=group_id)
    if not PermissionService.can_access_client(user, group.client_id):
        return None, _access_denied_response()
    if PermissionService.is_client_staff(user):
        staff = getattr(user, 'staff_profile', None)
        if not staff:
            return None, _access_denied_response()
        assigned_table_ids = _normalized_assigned_table_ids(staff)
        assigned_group_ids = set(_assigned_group_ids_for_access(staff))
        has_group_assignment = group.id in assigned_group_ids
        has_group_table = False
        if assigned_table_ids:
            has_group_table = Table.objects.filter(
                id__in=assigned_table_ids,
                deleted_by_manager=False,
            ).exists()

        if (assigned_group_ids or assigned_table_ids) and not (has_group_assignment or has_group_table):
            return None, _access_denied_response()
    return group, None

def _check_client_scope_by_table(user, table_id):
    """Check user has access to the organisation owning this table. Returns (table, error_response).
    
    Delegates to PermissionService.can_access_organisation() (single authority).
    """
    table = get_object_or_404(Table.objects.select_related('organisation'), id=table_id)
    org_id = table.organisation_id or getattr(getattr(table, 'group', None), 'client_id', None)
    if org_id and not PermissionService.can_access_organisation(user, org_id):
        return None, _access_denied_response()
    if PermissionService.is_client_staff(user):
        from assistants.models import Assistant
        staff = getattr(user, 'assistant_profile', None) or getattr(user, 'staff_profile', None) or Assistant.objects.filter(user=user).first()
        if not staff:
            return None, _access_denied_response()
        if not _table_is_assigned_to_staff(staff, table):
            return None, _access_denied_response()
    return table, None

def _check_client_scope_by_card(user, card_id):
    """Check user has access to the organisation owning this card. Returns (card, error_response).
    
    Delegates to PermissionService.can_access_organisation() (single authority).
    """
    card = get_object_or_404(IDCard.objects.select_related('table__organisation'), id=card_id)
    org_id = card.table.organisation_id if card.table else None
    if org_id and not PermissionService.can_access_organisation(user, org_id):
        return None, _access_denied_response()
    if PermissionService.is_client_staff(user):
        from assistants.models import Assistant
        staff = getattr(user, 'assistant_profile', None) or getattr(user, 'staff_profile', None) or Assistant.objects.filter(user=user).first()
        if not staff:
            return None, _access_denied_response()
        if not _table_is_assigned_to_staff(staff, card.table):
            return None, _access_denied_response()
    return card, None


# ==================== CLIENT READONLY ON APPROVED+ ====================
# After cards reach approved/download/reprint, client & client_staff users
# can only VIEW — no edit, delete, status change, or image reupload.

_CLIENT_READONLY_STATUSES = frozenset({'approved', 'download', 'reprint'})
_CLIENT_EDIT_LOCK_STATUSES = frozenset({'approved', 'download', 'reprint'})

def _client_readonly_response():
    """Fresh 403 response for each request."""
    return JsonResponse(
        {'success': False, 'message': 'Cards in approved / download status cannot be modified by client users.'},
        status=403,
    )

def _is_client_readonly(user, card_status):
    """Return True when client/client_staff tries to modify a card in a locked status."""
    return PermissionService.is_client_role(user) and card_status in _CLIENT_READONLY_STATUSES


def _client_edit_locked_response():
    """Fresh 403 response for readonly edit operations."""
    return JsonResponse(
        {'success': False, 'message': 'Cards in approved / download / reprint status cannot be edited by client users.'},
        status=403,
    )


def _is_client_edit_locked(user, card_status):
    """Return True when client/client_staff tries to edit a card in an edit-locked status."""
    return PermissionService.is_client_role(user) and card_status in _CLIENT_EDIT_LOCK_STATUSES


# ==================== FIELD HELPERS (canonical: core.utils.field_utils) ====================
# Re-exported for backward compatibility within this view module.
# All new code should import directly from core.utils.field_utils.
from core.utils.field_utils import (
    validate_image_bytes,
    NUMERIC_TO_ROMAN,
    VALID_CLASS_VALUES,
    CLASS_UPGRADE_MAP,
)
