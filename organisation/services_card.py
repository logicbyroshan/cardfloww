"""
Client Card Service — read and status-transition operations on ID cards.
"""
from typing import Optional, List, Any, Tuple

from django.utils.timezone import localtime
from django.utils.dateparse import parse_datetime, parse_date
from django.utils.timezone import make_aware, is_naive
from django.db.models import Count, Q
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Lower, Coalesce
from django.db.models import CharField, Value, IntegerField, Case, When

from core.services import IDCardService
from core.models import User
from organisation.models import Organisation
from assistants.models import Assistant
from tables.models import Table, IDCard
from core.services.base import BaseService, ServiceResult
from core.services.permission_service import PermissionService
from mediafiles.utils import get_card_photo_url

from .services_access import OrganisationAccessService


class OrganisationCardService(BaseService):
    """
    Service for client card data access.
    Clients can view and manage cards within their tables.
    """
    
    VALID_STATUSES = ['pending', 'verified', 'pool', 'approved', 'download', 'reprint', 'captured', 'uncaptured']

    @staticmethod
    def _normalize_positive_int_ids(raw_ids) -> List[int]:
        """Normalize mixed input IDs into unique positive integers."""
        if not isinstance(raw_ids, (list, tuple, set)):
            return []

        normalized: List[int] = []
        seen = set()
        for value in raw_ids:
            if isinstance(value, bool):
                continue
            try:
                parsed = int(str(value).strip())
            except (TypeError, ValueError):
                continue
            if parsed <= 0 or parsed in seen:
                continue
            seen.add(parsed)
            normalized.append(parsed)
        return normalized

    @staticmethod
    def _get_class_section_branch_fields(table):
        class_field = None
        section_field = None
        branch_field = None
        for field in (table.fields or []):
            ftype = str(field.get('type', '') or '').strip().lower()
            fname = str(field.get('name', '') or '').strip()
            lower = fname.lower()
            normalized = lower.replace('_', ' ').replace('-', ' ').replace('.', ' ')
            normalized = ' '.join(normalized.split())

            if not class_field and (
                ftype == 'class'
                or normalized in ('class', 'class name', 'std', 'standard', 'designation', 'grade')
            ):
                class_field = fname
                continue
            if not section_field and (
                ftype == 'section'
                or normalized in ('section', 'section name', 'sec', 'division', 'div')
            ):
                section_field = fname
                continue
            if not branch_field and (
                ftype == 'branch' or lower == 'branch' or lower == 'stream' or lower == 'course'
                or 'branch' in lower or 'stream' in lower or 'course' in lower
            ):
                branch_field = fname
        return class_field, section_field, branch_field

    @staticmethod
    def _get_name_field(table):
        if not table or not table.fields:
            return None

        def _norm(text):
            return ' '.join(str(text or '').strip().lower().replace('_', ' ').replace('-', ' ').split())

        def _is_primary_name_candidate(name_norm):
            if not name_norm:
                return False
            exact = {
                'name',
                'student name',
                'employee name',
                'emp name',
                'staff name',
                'full name',
                'candidate name',
            }
            if name_norm in exact:
                return True
            if 'name' not in name_norm:
                return False
            blocked = ('father', 'mother', 'guardian', 'parent', 'relation', 'spouse', 'husband', 'wife')
            return not any(token in name_norm for token in blocked)

        fields_list = table.fields if isinstance(table.fields, list) else []
        for field in fields_list:
            if not isinstance(field, dict):
                continue
            fname = str(field.get('name', '') or '').strip()
            ftype = str(field.get('type', '') or '').strip().lower()
            if ftype == 'name' and fname:
                return fname
            if _is_primary_name_candidate(_norm(fname)):
                return fname
        for field in fields_list:
            if not isinstance(field, dict):
                continue
            fname = str(field.get('name', '') or '').strip()
            ftype = str(field.get('type', '') or '').strip().lower()
            if fname and ftype in ('text', 'name', ''):
                return fname
        return None

    @staticmethod
    def _get_field_value_case_insensitive(field_data, field_name):
        if not isinstance(field_data, dict):
            return ''
        wanted = str(field_name or '').strip().lower()
        if not wanted:
            return ''
        for key, value in field_data.items():
            if str(key or '').strip().lower() == wanted:
                return value
        return ''

    @staticmethod
    def _dedupe_scope_values(values: Any) -> List[str]:
        out: List[str] = []
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

    @staticmethod
    def _matched_assignment_scopes_for_table(staff, table) -> List[dict]:
        scopes = getattr(staff, 'assignment_scopes', None)
        if not isinstance(scopes, list) or not scopes:
            return []

        matched = []
        for scope in scopes:
            if not isinstance(scope, dict):
                continue

            stype = str(scope.get('scope_type', '') or '').strip().lower()
            sid = scope.get('scope_id')
            try:
                sid_int = int(str(sid).strip())
            except (TypeError, ValueError):
                continue

            if stype == 'table' and sid_int == int(table.id):
                matched.append(scope)
            elif stype == 'group' and sid_int == int(table.group_id):
                matched.append(scope)

        return matched

    @classmethod
    def _table_scope_filters(cls, staff, table) -> Tuple[List[str], List[str], List[str]]:
        table_key = (int(table.id), int(table.group_id))
        cached_scopes = getattr(staff, '_cached_table_scope_filters', None)
        if isinstance(cached_scopes, dict) and table_key in cached_scopes:
            return cached_scopes[table_key]

        scopes = getattr(staff, 'assignment_scopes', None)
        if not isinstance(scopes, list) or not scopes:
            result = (
                cls._dedupe_scope_values(staff.allowed_classes or []),
                cls._dedupe_scope_values(staff.allowed_sections or []),
                cls._dedupe_scope_values(staff.allowed_branches or []),
            )
            if not isinstance(cached_scopes, dict):
                cached_scopes = {}
            cached_scopes[table_key] = result
            setattr(staff, '_cached_table_scope_filters', cached_scopes)
            return result

        matched = cls._matched_assignment_scopes_for_table(staff, table)

        if not matched:
            result = (
                cls._dedupe_scope_values(staff.allowed_classes or []),
                cls._dedupe_scope_values(staff.allowed_sections or []),
                cls._dedupe_scope_values(staff.allowed_branches or []),
            )
            if not isinstance(cached_scopes, dict):
                cached_scopes = {}
            cached_scopes[table_key] = result
            setattr(staff, '_cached_table_scope_filters', cached_scopes)
            return result

        classes: List[str] = []
        sections: List[str] = []
        branches: List[str] = []
        for scope in matched:
            classes.extend(scope.get('classes') or [])
            sections.extend(scope.get('sections') or [])
            branches.extend(scope.get('branches') or [])

        result = (
            cls._dedupe_scope_values(classes),
            cls._dedupe_scope_values(sections),
            cls._dedupe_scope_values(branches),
        )
        if not isinstance(cached_scopes, dict):
            cached_scopes = {}
        cached_scopes[table_key] = result
        setattr(staff, '_cached_table_scope_filters', cached_scopes)
        return result

    @staticmethod
    def _assigned_group_ids_for_access(staff) -> List[int]:
        cached_group_ids = getattr(staff, '_cached_assigned_group_ids_for_card_scope', None)
        if cached_group_ids is not None:
            return cached_group_ids

        scopes = getattr(staff, 'assignment_scopes', None)
        if isinstance(scopes, list) and scopes:
            out: List[int] = []
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
                out.append(sid_int)

            if has_any_valid_scope:
                setattr(staff, '_cached_assigned_group_ids_for_card_scope', out)
                return out

        fallback_group_ids = list(staff.assigned_groups.values_list('id', flat=True))
        setattr(staff, '_cached_assigned_group_ids_for_card_scope', fallback_group_ids)
        return fallback_group_ids

    @classmethod
    def _assigned_table_ids_for_access(cls, staff) -> List[int]:
        """Return cached normalized assigned table IDs for client_staff checks.
        Checks both legacy assigned_table_ids field and new assignment_scopes.
        """
        cached_table_ids = getattr(staff, '_cached_assigned_table_ids_for_card_scope', None)
        if cached_table_ids is not None:
            return cached_table_ids

        scopes = getattr(staff, 'assignment_scopes', None)
        if isinstance(scopes, list) and scopes:
            explicit_table_ids = []
            seen = set()
            has_any_valid_scope = False

            for scope in scopes:
                if not isinstance(scope, dict):
                    continue
                stype = str(scope.get('scope_type', '') or '').strip().lower()
                if stype not in ('group', 'table'):
                    continue
                has_any_valid_scope = True
                if stype != 'table':
                    continue

                sid = scope.get('scope_id')
                try:
                    sid_int = int(str(sid).strip())
                except (TypeError, ValueError):
                    continue
                if sid_int <= 0 or sid_int in seen:
                    continue
                seen.add(sid_int)
                explicit_table_ids.append(sid_int)

            if has_any_valid_scope:
                setattr(staff, '_cached_assigned_table_ids_for_card_scope', explicit_table_ids)
                return explicit_table_ids

        assigned_table_ids = cls._normalize_positive_int_ids(staff.assigned_table_ids or [])
        setattr(staff, '_cached_assigned_table_ids_for_card_scope', assigned_table_ids)
        return assigned_table_ids

    @classmethod
    def _table_is_assigned_to_staff(cls, staff, table) -> bool:
        assigned_table_ids = set(cls._assigned_table_ids_for_access(staff))
        assigned_group_ids = set(cls._assigned_group_ids_for_access(staff))

        if assigned_table_ids and assigned_group_ids:
            return (int(table.id) in assigned_table_ids) or (int(table.group_id) in assigned_group_ids)
        if assigned_table_ids:
            return int(table.id) in assigned_table_ids
        if assigned_group_ids:
            return int(table.group_id) in assigned_group_ids
        return False

    @classmethod
    def _apply_client_staff_row_scope(cls, user, table, qs, ignore_pool_bypass=False, status_filter=None):
        """
        Apply client_staff row-level filtering based on assigned classes/sections/branches.
        Supports multiple assignment scopes (OR-ed together).
        """
        if not PermissionService.is_client_staff(user):
            return qs

        # Do not bypass row-level scoping for pool status
        # if not ignore_pool_bypass:
        #     if status_filter == 'pool':
        #         return qs

        staff = getattr(user, 'staff_profile', None)
        if not staff:
            return qs.none()

        if not cls._table_is_assigned_to_staff(staff, table):
            return qs.none()

        # If we reach here, staff has access to this table.
        # Now we apply the class/section/branch row-level restrictions.
        
        # Multiple scope entries are OR-ed together.
        # Inside a scope entry, class/section/branch are AND-ed.
        # An empty scope entry should not widen access.
        
        # 1. Collect all applicable scopes (direct table + parent group)
        scope_entries = cls._matched_assignment_scopes_for_table(staff, table)
        
        # If no explicit assignment_scopes defined, fallback to legacy allowed_* fields
        if not scope_entries:
            legacy_classes, legacy_sections, legacy_branches = cls._table_scope_filters(staff, table)
            if not (legacy_classes or legacy_sections or legacy_branches):
                # No filters at all = full access to assigned table
                return qs
            # Convert legacy into a single scope entry
            scope_entries = [{
                'classes': legacy_classes,
                'sections': legacy_sections,
                'branches': legacy_branches
            }]

        # 2. Build OR query for all scope entries
        from django.db.models import Q
        from core.utils.field_utils import normalize_class_value, normalize_compact_text_value
        
        class_field, section_field, branch_field = cls._get_class_section_branch_fields(table)
        
        # Annotate with field values for filtering
        annotations = {}
        if class_field:
            annotations['_scope_cls'] = Cast(KeyTextTransform(class_field, 'field_data'), CharField())
        if section_field:
            annotations['_scope_sec'] = Cast(KeyTextTransform(section_field, 'field_data'), CharField())
        if branch_field:
            annotations['_scope_branch'] = Cast(KeyTextTransform(branch_field, 'field_data'), CharField())
        
        if annotations:
            qs = qs.annotate(**annotations)

        final_q = Q()
        for scope in scope_entries:
            scope_q = Q()
            has_any_filter = False
            
            # Classes
            if scope.get('classes') and class_field:
                has_any_filter = True
                allowed = {normalize_class_value(v) for v in scope['classes'] if normalize_class_value(v)}
                if allowed:
                    raw_values = list(qs.exclude(_scope_cls='').values_list('_scope_cls', flat=True).distinct())
                    matching_raw = [raw for raw in raw_values if normalize_class_value(raw) in allowed]
                    if matching_raw:
                        scope_q &= Q(_scope_cls__in=matching_raw)
                    else:
                        scope_q &= Q(id__isnull=True)
                else:
                    scope_q &= Q(id__isnull=True)

            # Sections
            if scope.get('sections') and section_field:
                has_any_filter = True
                allowed = {str(s).strip().lower() for s in scope['sections'] if str(s).strip()}
                if allowed:
                    raw_values = list(qs.exclude(_scope_sec='').values_list('_scope_sec', flat=True).distinct())
                    matching_raw = [raw for raw in raw_values if str(raw).strip().lower() in allowed]
                    if matching_raw:
                        scope_q &= Q(_scope_sec__in=matching_raw)
                    else:
                        scope_q &= Q(id__isnull=True)
                else:
                    scope_q &= Q(id__isnull=True)

            # Branches
            if scope.get('branches') and branch_field:
                has_any_filter = True
                allowed = {normalize_compact_text_value(v) for v in scope['branches'] if normalize_compact_text_value(v)}
                if allowed:
                    raw_values = list(qs.exclude(_scope_branch='').values_list('_scope_branch', flat=True).distinct())
                    matching_raw = [raw for raw in raw_values if normalize_compact_text_value(raw) in allowed]
                    if matching_raw:
                        scope_q &= Q(_scope_branch__in=matching_raw)
                    else:
                        scope_q &= Q(id__isnull=True)
                else:
                    scope_q &= Q(id__isnull=True)

            if not has_any_filter:
                if class_field or section_field or branch_field:
                    # Table supports filtering, but scope has no filters selected -> zero access
                    scope_q &= Q(id__isnull=True)
                else:
                    # Table does not support filtering (e.g. Staff list) -> full access
                    return qs

            final_q |= scope_q

        if not final_q:
            if ignore_pool_bypass:
                return qs.none()
            return qs.filter(status='pool')

        # Allow 'pool' cards to bypass row-level filtering unless checking explicitly
        if ignore_pool_bypass:
            return qs.filter(final_q)
        return qs.filter(final_q | Q(status='pool'))
    
    @classmethod
    def get_tables_for_client(cls, user, client=None) -> ServiceResult:
        """
        Get all tables for the client with card counts.
        Accepts optional *client* override for admin roles.
        """
        try:
            if not client:
                client = OrganisationAccessService.get_organisation_for_user(user)
            if not client:
                return ServiceResult(success=False, message='Client profile not found')
            
            tables = Table.objects.filter(
                group__client=client
            ).select_related('group').annotate(
                total_cards=Count('id_cards'),
                pending=Count('id_cards', filter=Q(id_cards__status='pending')),
                verified=Count('id_cards', filter=Q(id_cards__status='verified')),
                pool=Count('id_cards', filter=Q(id_cards__status='pool')),
                approved=Count('id_cards', filter=Q(id_cards__status='approved')),
                download=Count('id_cards', filter=Q(id_cards__status='download')),
                reprint=Count('id_cards', filter=Q(id_cards__status='reprint')),
            )

            if PermissionService.is_client_staff(user):
                staff = getattr(user, 'staff_profile', None)
                if not staff:
                    tables = tables.none()
                else:
                    assigned_table_ids = cls._normalize_positive_int_ids(staff.assigned_table_ids or [])
                    assigned_group_ids = cls._assigned_group_ids_for_access(staff)

                    if assigned_table_ids and assigned_group_ids:
                        tables = tables.filter(Q(id__in=assigned_table_ids) | Q(group_id__in=assigned_group_ids))
                    elif assigned_table_ids:
                        tables = tables.filter(id__in=assigned_table_ids)
                    elif assigned_group_ids:
                        tables = tables.filter(group_id__in=assigned_group_ids)
            
            tables_data = [{
                'id': t.id,
                'name': t.name,
                'group_name': t.group.name,
                'group_id': t.group.id,
                'is_active': t.is_active,
                'total_cards': t.total_cards,
                'pending': t.pending,
                'verified': t.verified,
                'pool': t.pool,
                'approved': t.approved,
                'download': t.download,
                'reprint': t.reprint,
            } for t in tables]
            
            return ServiceResult(success=True, data={'tables': tables_data})
            
        except Exception as e:
            return ServiceResult(success=False, message=str(e))
    
    @classmethod
    def get_cards(
        cls, 
        user, 
        table_id: int, 
        status_filter: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        cursor: int = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        class_filter: Optional[str] = None,
        section_filter: Optional[str] = None,
        course_filter: Optional[str] = None,
        branch_filter: Optional[str] = None,
        photo_filter: Optional[str] = None,
        sort_order: Optional[str] = None,
        image_column: Optional[str] = None,
    ) -> ServiceResult:
        """
        Get cards for a table (with permission checks).
        Supports cursor-based pagination (preferred) and offset (legacy).
        """
        try:
            client = OrganisationAccessService.get_organisation_for_user(user)
            if not client and not PermissionService.is_any_admin(user):
                return ServiceResult(success=False, message='Client profile not found')
            
            # Get table and verify ownership
            try:
                table = Table.objects.get(id=table_id)
            except Table.DoesNotExist:
                return ServiceResult(success=False, message='Table not found')
            
            if not OrganisationAccessService.can_access_table(user, table):
                return ServiceResult(success=False, message='Access denied')
            
            status_filter = (status_filter or '').strip().lower()

            # Enforce status-view permissions for both filtered and unfiltered requests.
            perm_map = {
                'pending': 'perm_idcard_pending_list',
                'verified': 'perm_idcard_verified_list',
                'pool': 'perm_idcard_pool_list',
                'approved': 'perm_idcard_approved_list',
                'download': 'perm_idcard_download_list',
                'reprint': 'perm_idcard_reprint_list',
                'captured': 'perm_idcard_pending_list',
                'uncaptured': 'perm_idcard_pending_list',
            }

            if status_filter and status_filter not in cls.VALID_STATUSES:
                return ServiceResult(success=False, message='Invalid status filter')

            if status_filter:
                perm = perm_map.get(status_filter)
                if perm and not PermissionService.has(user, perm):
                    return ServiceResult(
                        success=False,
                        message=f'No permission to view {status_filter} cards'
                    )

            allowed_statuses = [
                status for status, perm_name in perm_map.items()
                if PermissionService.has(user, perm_name)
            ]
            if not allowed_statuses:
                return ServiceResult(success=False, message='No permission to view cards')
            
            # Build base query — newest batch/action first, Excel order within batch
            if status_filter == 'download':
                cards_query = IDCard.objects.filter(table=table).order_by('-downloaded_at', '-id')
            elif status_filter == 'pool':
                cards_query = IDCard.objects.filter(table=table).order_by('-deleted_at', '-id')
            elif status_filter in ('verified', 'approved'):
                cards_query = IDCard.objects.filter(table=table).order_by('-status_changed_at', '-id')
            else:
                cards_query = IDCard.objects.filter(table=table).annotate(
                    _status_sort_at=Coalesce('status_changed_at', 'created_at')
                ).order_by('-_status_sort_at', '-id')
            
            if status_filter in ('captured', 'uncaptured'):
                cards_query = cards_query.filter(status__in=['pending', 'verified'])
                if status_filter == 'captured':
                    photo_filter = 'complete'
                else:
                    photo_filter = 'incomplete'
            elif status_filter:
                cards_query = cards_query.filter(status=status_filter)
            else:
                cards_query = cards_query.filter(status__in=allowed_statuses)

            cards_query = cls._apply_client_staff_row_scope(user, table, cards_query, status_filter=status_filter)
            
            # Search in field_data (JSONField) using table-aware matcher.
            if search:
                cards_query = IDCardService._apply_search_filter(cards_query, search, table=table)

            # Download list supports date/date-time range filtering by downloaded_at.
            if status_filter == 'download':
                from_value = (from_date or '').strip()
                to_value = (to_date or '').strip()

                if from_value:
                    parsed_from_dt = parse_datetime(from_value)
                    if parsed_from_dt is not None:
                        if is_naive(parsed_from_dt):
                            parsed_from_dt = make_aware(parsed_from_dt)
                        cards_query = cards_query.filter(downloaded_at__gte=parsed_from_dt)
                    else:
                        parsed_from_d = parse_date(from_value)
                        if parsed_from_d is not None:
                            cards_query = cards_query.filter(downloaded_at__date__gte=parsed_from_d)

                if to_value:
                    parsed_to_dt = parse_datetime(to_value)
                    if parsed_to_dt is not None:
                        if is_naive(parsed_to_dt):
                            parsed_to_dt = make_aware(parsed_to_dt)
                        cards_query = cards_query.filter(downloaded_at__lte=parsed_to_dt)
                    else:
                        parsed_to_d = parse_date(to_value)
                        if parsed_to_d is not None:
                            cards_query = cards_query.filter(downloaded_at__date__lte=parsed_to_d)

            class_filter_value = str(class_filter or '').strip()
            section_filter_value = str(section_filter or '').strip()
            course_filter_value = str(course_filter or '').strip()
            branch_filter_value = str(branch_filter or '').strip()
            if class_filter_value or section_filter_value or course_filter_value or branch_filter_value:
                class_field_name, section_field_name, course_field_name, branch_field_name = (
                    IDCardService._get_class_section_course_branch_field_names(table)
                )

                if class_filter_value:
                    if not class_field_name:
                        cards_query = cards_query.none()
                    else:
                        from core.utils.field_utils import normalize_class_value

                        cards_query = cards_query.annotate(
                            _filter_cls=Cast(KeyTextTransform(class_field_name, 'field_data'), CharField())
                        )
                        target_class = normalize_class_value(class_filter_value)
                        if not target_class:
                            cards_query = cards_query.none()
                        else:
                            raw_values = list(
                                cards_query
                                .exclude(_filter_cls__isnull=True)
                                .exclude(_filter_cls='')
                                .values_list('_filter_cls', flat=True)
                                .distinct()
                            )
                            matching_raw = [
                                raw for raw in raw_values
                                if normalize_class_value(raw) == target_class
                            ]
                            if not matching_raw:
                                cards_query = cards_query.none()
                            else:
                                cards_query = cards_query.filter(_filter_cls__in=matching_raw)

                if section_filter_value:
                    if not section_field_name:
                        cards_query = cards_query.none()
                    else:
                        cards_query = cards_query.annotate(
                            _filter_sec=Cast(KeyTextTransform(section_field_name, 'field_data'), CharField())
                        )
                        target_section = section_filter_value.strip().lower()
                        raw_sections = list(
                            cards_query
                            .exclude(_filter_sec__isnull=True)
                            .exclude(_filter_sec='')
                            .values_list('_filter_sec', flat=True)
                            .distinct()
                        )
                        matching_sections = [
                            raw for raw in raw_sections
                            if str(raw).strip().lower() == target_section
                        ]
                        if not matching_sections:
                            cards_query = cards_query.none()
                        else:
                            cards_query = cards_query.filter(_filter_sec__in=matching_sections)

                if course_filter_value and course_field_name:
                    cards_query = IDCardService._apply_compact_text_filter(
                        cards_query,
                        course_filter_value,
                        course_field_name,
                        table_id=table_id,
                        alias='_course_cmp',
                    )

                if branch_filter_value and branch_field_name:
                    cards_query = IDCardService._apply_compact_text_filter(
                        cards_query,
                        branch_filter_value,
                        branch_field_name,
                        table_id=table_id,
                        alias='_branch_cmp',
                    )

            photo_filter_value = str(photo_filter or '').strip().lower()
            if photo_filter_value in ('complete', 'pending', 'incomplete', 'with', 'without'):
                matching_photo_ids: List[int] = []
                target_col = str(image_column or 'photo').strip()
                for _card in cards_query.only('id', 'photo', 'field_data').iterator(chunk_size=500):
                    fd = _card.field_data or {}
                    
                    if target_col:
                        val = fd.get(target_col)
                        if val is None:
                            for k, v in fd.items():
                                if str(k).strip().upper() == target_col.upper():
                                    val = v
                                    break
                        has_valid_photo = bool(val and isinstance(val, str) and not val.startswith('PENDING:') and val not in ('NOT_FOUND', ''))
                        is_pending_placeholder = bool(val and isinstance(val, str) and val.startswith('PENDING:'))
                    else:
                        # 1. Check for valid photo (complete)
                        has_valid_photo = bool(get_card_photo_url(_card, fd))
                        
                        # 2. Check for pending placeholder
                        is_pending_placeholder = False
                        for val in fd.values():
                            if isinstance(val, str) and val.startswith('PENDING:'):
                                is_pending_placeholder = True
                                break
                    
                    matched = False
                    if photo_filter_value in ('complete', 'with'):
                        matched = has_valid_photo
                    elif photo_filter_value == 'pending':
                        matched = is_pending_placeholder
                    elif photo_filter_value in ('incomplete', 'without'):
                        matched = not has_valid_photo and not is_pending_placeholder
                    
                    if matched:
                        matching_photo_ids.append(_card.id)

                if not matching_photo_ids:
                    cards_query = cards_query.none()
                else:
                    cards_query = cards_query.filter(id__in=matching_photo_ids)

            normalized_sort = str(sort_order or '').strip().lower()
            if normalized_sort not in ('sr-asc', 'name-asc', 'name-desc'):
                normalized_sort = 'sr-asc'

            if normalized_sort in ('name-asc', 'name-desc'):
                name_field = cls._get_name_field(table)
                if name_field:
                    cards_query = cards_query.annotate(
                        _name_sort=Lower(Coalesce(
                            Cast(KeyTextTransform(name_field, 'field_data'), CharField()),
                            Value(''),
                            output_field=CharField(),
                        )),
                    )
                    if normalized_sort == 'name-asc':
                        cards_query = cards_query.order_by('_name_sort', 'id')
                    else:
                        cards_query = cards_query.order_by('-_name_sort', '-id')
            else:
                # Default (sr-asc) -> Sort by Class first if class field exists, then by name/id
                class_field_name, _, _, _ = IDCardService._get_class_section_course_branch_field_names(table)
                if class_field_name:
                    cards_query = cards_query.annotate(
                        _class_sort=Lower(Coalesce(
                            Cast(KeyTextTransform(class_field_name, 'field_data'), CharField()),
                            Value(''),
                            output_field=CharField(),
                        ))
                    )
                    name_field = cls._get_name_field(table)
                    if name_field:
                        cards_query = cards_query.annotate(
                            _name_sort=Lower(Coalesce(
                                Cast(KeyTextTransform(name_field, 'field_data'), CharField()),
                                Value(''),
                                output_field=CharField(),
                            )),
                        )
                        cards_query = cards_query.order_by('_class_sort', '_name_sort', 'id')
                    else:
                        cards_query = cards_query.order_by('_class_sort', 'id')
            
            total_count = cards_query.count()

            # Cursor-based pagination (preferred) or offset (legacy)
            if cursor is not None:
                cards = list(cards_query.filter(id__lt=cursor)[:limit + 1])
            else:
                cards = list(cards_query[offset:offset + limit + 1])
            has_more = len(cards) > limit
            if has_more:
                cards = cards[:limit]
            next_cursor = cards[-1].id if cards and has_more else None
            
            # Serialize
            card_list = []
            detected_name_field = cls._get_name_field(table)
            for idx, card in enumerate(cards):
                # Extract common fields from field_data for convenience
                field_data = card.field_data or {}
                name = None
                if detected_name_field:
                    name = cls._get_field_value_case_insensitive(field_data, detected_name_field)
                name = name or field_data.get('NAME') or field_data.get('name') or field_data.get('Name') or f'Card #{card.id}'
                id_number = (
                    field_data.get('ID') or 
                    field_data.get('id') or 
                    field_data.get('ID_NUMBER') or 
                    field_data.get('id_number') or
                    field_data.get('ROLL_NO') or
                    field_data.get('roll_no') or
                    ''
                )
                class_designation = (
                    field_data.get('CLASS') or 
                    field_data.get('class') or 
                    field_data.get('DESIGNATION') or 
                    field_data.get('designation') or
                    ''
                )
                
                # Sanitize field_data: remove PENDING: prefix from non-image fields before exposing to client
                sanitized_field_data = {}
                for key, val in (card.field_data or {}).items():
                    # Check if this is an image field
                    is_image_field = False
                    for field in (table.fields or []):
                        if not isinstance(field, dict):
                            continue
                        fname = field.get('name')
                        if fname is None:
                            continue
                        fname_str = str(fname).strip()
                        if fname_str == key or fname_str.upper() == key.upper():
                            is_image_field = field.get('type') in ['photo', 'image', 'rel_photo', 'mother_photo', 'father_photo', 'barcode', 'qr_code', 'signature', 'image']
                            break
                    # Strip PENDING: prefix from non-image fields
                    if not is_image_field and val and isinstance(val, str) and val.startswith('PENDING:'):
                        sanitized_field_data[key] = ''
                    else:
                        sanitized_field_data[key] = val
                
                card_data = {
                    'id': card.id,
                    'sr_no': offset + idx + 1,
                    'name': name,
                    'id_number': id_number,
                    'class_designation': class_designation,
                    'photo_url': get_card_photo_url(card, field_data),
                    'field_data': sanitized_field_data,
                    'status': card.status,
                    'status_display': card.get_status_display(),
                    'downloaded_date': localtime(card.downloaded_at).strftime('%Y-%m-%d') if card.downloaded_at else '',
                    'created_at': localtime(card.created_at).strftime('%d %b %Y, %H:%M'),
                    'updated_at': localtime(card.updated_at).strftime('%d %b %Y, %H:%M'),
                }
                card_list.append(card_data)
            
            # Status counts for the tab bar
            counts = {
                'pending': IDCard.objects.filter(table=table, status='pending').count(),
                'verified': IDCard.objects.filter(table=table, status='verified').count(),
                'approved': IDCard.objects.filter(table=table, status='approved').count(),
                'download': IDCard.objects.filter(table=table, status='download').count(),
                'pool': IDCard.objects.filter(table=table, status='pool').count(),
            }
            # Apply row-scope if staff
            if PermissionService.is_client_staff(user):
                for s_key in counts:
                    counts[s_key] = cls._apply_client_staff_row_scope(
                        user, table, IDCard.objects.filter(table=table, status=s_key), status_filter=s_key
                    ).count()

            return ServiceResult(
                success=True,
                data={
                    'cards': card_list,
                    'table': {
                        'id': table.id,
                        'name': table.name,
                        'fields': table.fields,
                    },
                    'counts': counts,
                    'total': total_count,
                    'offset': offset,
                    'limit': limit,
                    'has_more': has_more,
                    'next_cursor': next_cursor,
                }
            )
            
        except Exception as e:
            return ServiceResult(success=False, message=str(e))
    
    @classmethod
    def get_card_detail(cls, user, card_id: int) -> ServiceResult:
        """
        Get details of a specific card.
        """
        try:
            client = OrganisationAccessService.get_organisation_for_user(user)
            if not client and not PermissionService.is_any_admin(user):
                return ServiceResult(success=False, message='Client profile not found')

            if not PermissionService.has(user, 'perm_idcard_info'):
                return ServiceResult(success=False, message='Permission denied')
            
            # Get card
            try:
                card = IDCard.objects.select_related('table', 'table__group').get(id=card_id)
            except IDCard.DoesNotExist:
                return ServiceResult(success=False, message='Card not found')
            
            # Verify ownership
            if not OrganisationAccessService.can_access_card(user, card):
                return ServiceResult(success=False, message='Access denied')

            scoped_card = cls._apply_client_staff_row_scope(
                user,
                card.table,
                IDCard.objects.filter(id=card.id, table_id=card.table_id),
                status_filter=card.status,
            )
            if not scoped_card.exists():
                return ServiceResult(success=False, message='Access denied')
            
            field_data = card.field_data or {}
            
            # Extract common fields
            name = (
                field_data.get('NAME') or 
                field_data.get('name') or 
                field_data.get('Name') or 
                f'Card #{card.id}'
            )
            id_number = (
                field_data.get('ID') or 
                field_data.get('id') or 
                field_data.get('ID_NUMBER') or 
                field_data.get('id_number') or
                field_data.get('ROLL_NO') or
                field_data.get('roll_no') or
                ''
            )
            class_designation = (
                field_data.get('CLASS') or 
                field_data.get('class') or 
                field_data.get('DESIGNATION') or 
                field_data.get('designation') or
                ''
            )
            father_name = (
                field_data.get('FATHER_NAME') or 
                field_data.get('father_name') or 
                field_data.get('FATHER') or 
                ''
            )
            mother_name = (
                field_data.get('MOTHER_NAME') or 
                field_data.get('mother_name') or 
                field_data.get('MOTHER') or 
                ''
            )
            dob = (
                field_data.get('DOB') or 
                field_data.get('dob') or 
                field_data.get('DATE_OF_BIRTH') or 
                ''
            )
            blood_group = (
                field_data.get('BLOOD_GROUP') or 
                field_data.get('blood_group') or 
                field_data.get('BLOOD') or 
                ''
            )
            address = (
                field_data.get('ADDRESS') or 
                field_data.get('address') or 
                ''
            )
            contact = (
                field_data.get('CONTACT') or 
                field_data.get('contact') or 
                field_data.get('PHONE') or 
                field_data.get('phone') or 
                field_data.get('MOBILE') or 
                ''
            )
            session = (
                field_data.get('SESSION') or 
                field_data.get('session') or 
                field_data.get('VALIDITY') or 
                field_data.get('validity') or 
                ''
            )
            
            return ServiceResult(
                success=True,
                data={
                    'id': card.id,
                    'name': name,
                    'id_number': id_number,
                    'class_designation': class_designation,
                    'father_name': father_name,
                    'mother_name': mother_name,
                    'dob': dob,
                    'blood_group': blood_group,
                    'address': address,
                    'contact': contact,
                    'session': session,
                    'photo_url': get_card_photo_url(card, field_data),
                    'field_data': field_data,
                    'status': card.status,
                    'status_display': card.get_status_display(),
                    'table_name': card.table.name,
                    'group_name': card.table.group.name,
                    'created_at': localtime(card.created_at).strftime('%d %b %Y, %H:%M'),
                    'updated_at': localtime(card.updated_at).strftime('%d %b %Y, %H:%M'),
                }
            )
            
        except Exception as e:
            return ServiceResult(success=False, message=str(e))
    
    @classmethod
    def change_card_status(
        cls, user, card_id: int, new_status: str, request=None,
        apply_class_change: bool = False, updated_class: str = '', updated_section: str = ''
    ) -> ServiceResult:
        """
        Change a card's status — delegates to WorkflowService.transition().

        WorkflowService enforces: transition matrix, permissions, mandatory
        fields, image gate, client-readonly guard, activity logging.
        """
        try:
            client = OrganisationAccessService.get_organisation_for_user(user)
            if not client and not PermissionService.is_any_admin(user):
                return ServiceResult(success=False, message='Client profile not found')
            
            # Get card
            try:
                card = IDCard.objects.select_related('table__group').get(id=card_id)
            except IDCard.DoesNotExist:
                return ServiceResult(success=False, message='Card not found')
            
            # Verify ownership
            if not OrganisationAccessService.can_access_card(user, card):
                return ServiceResult(success=False, message='Access denied')

            is_pool_retrieve = (
                PermissionService.is_client_staff(user)
                and str(card.status or '').strip().lower() == 'pool'
                and str(new_status or '').strip().lower() == 'pending'
            )

            if PermissionService.is_client_staff(user) and not is_pool_retrieve:
                scoped_card = cls._apply_client_staff_row_scope(
                    user,
                    card.table,
                    IDCard.objects.filter(id=card.id, table_id=card.table_id),
                    status_filter=card.status,
                )
                if not scoped_card.exists():
                    return ServiceResult(success=False, message='Access denied')

            if is_pool_retrieve:
                scoped_card = cls._apply_client_staff_row_scope(
                    user,
                    card.table,
                    IDCard.objects.filter(id=card.id, table_id=card.table_id),
                    ignore_pool_bypass=True
                )
                
                # If out of scope, check if they requested a class change
                if not scoped_card.exists():
                    from core.views.idcard_card_api import _apply_pool_retrieve_class_change, _pool_retrieve_scope_payload, _pool_retrieve_requires_class_change, _POOL_RETRIEVE_SCOPE_MESSAGE
                    
                    if apply_class_change:
                        ok, error_message = _apply_pool_retrieve_class_change(user, card, updated_class, updated_section)
                        if not ok:
                            payload = _pool_retrieve_scope_payload(user, card)
                            return ServiceResult(
                                success=False,
                                message=error_message,
                                data={
                                    'requires_class_change': True,
                                    'retrieve_scope': 'pool_to_pending',
                                    'card_id': card.id,
                                    **payload
                                }
                            )
                        card.refresh_from_db()
                    else:
                        payload = _pool_retrieve_scope_payload(user, card)
                        if _pool_retrieve_requires_class_change(user, card):
                            return ServiceResult(
                                success=False,
                                message=_POOL_RETRIEVE_SCOPE_MESSAGE,
                                data={
                                    'requires_class_change': True,
                                    'retrieve_scope': 'pool_to_pending',
                                    'card_id': card.id,
                                    **payload
                                }
                            )
                        return ServiceResult(success=False, message=_POOL_RETRIEVE_SCOPE_MESSAGE)
            
            # Delegate entirely to WorkflowService (handles permissions + all guards)
            from tables.services_workflow import WorkflowService
            return WorkflowService.transition(card, new_status, user=user, request=request)
            
        except Exception as e:
            return ServiceResult(success=False, message=str(e))
    
    @classmethod
    def bulk_change_status(
        cls, user, table_id: int, card_ids: List[int], new_status: str, request=None,
        apply_class_change: bool = False, pool_retrieve_class_updates: dict = None
    ) -> ServiceResult:
        """
        Change status for multiple cards — delegates to WorkflowService.bulk_transition().

        WorkflowService enforces: transition matrix, permissions, mandatory
        fields, image gate, client-readonly guard, activity logging.
        """
        try:
            client = OrganisationAccessService.get_organisation_for_user(user)
            if not client and not PermissionService.is_any_admin(user):
                return ServiceResult(success=False, message='Client profile not found')
            
            # Verify table ownership
            try:
                table = Table.objects.get(id=table_id)
            except Table.DoesNotExist:
                return ServiceResult(success=False, message='Table not found')
            
            if not OrganisationAccessService.can_access_table(user, table):
                return ServiceResult(success=False, message='Access denied')

            is_pool_retrieve = (
                PermissionService.is_client_staff(user)
                and str(new_status or '').strip().lower() == 'pending'
            )

            forbidden_ids = []
            if PermissionService.is_client_staff(user):
                normalized_ids = cls._normalize_positive_int_ids(card_ids or [])
                scoped_ids = set(
                    cls._apply_client_staff_row_scope(
                        user,
                        table,
                        IDCard.objects.filter(table=table, id__in=normalized_ids),
                        ignore_pool_bypass=True
                    ).values_list('id', flat=True)
                )
                forbidden_ids = [cid for cid in normalized_ids if cid not in scoped_ids]

                if forbidden_ids and is_pool_retrieve:
                    from core.views.idcard_card_api import (
                        _apply_pool_retrieve_class_change,
                        _pool_retrieve_scope_payload,
                        _pool_retrieve_requires_class_change,
                        _POOL_RETRIEVE_SCOPE_MESSAGE,
                    )

                    class_updates = pool_retrieve_class_updates if isinstance(pool_retrieve_class_updates, dict) else {}

                    if apply_class_change and class_updates:
                        candidate_cards = list(
                            IDCard.objects.select_related('table__group').filter(
                                table=table,
                                id__in=forbidden_ids,
                                status='pool',
                            )
                        )
                        for pool_card in candidate_cards:
                            requested_class = class_updates.get(str(pool_card.id), class_updates.get(pool_card.id))
                            if requested_class is None:
                                continue
                            ok, error_message = _apply_pool_retrieve_class_change(
                                user,
                                pool_card,
                                requested_class,
                            )
                            if not ok:
                                payload = _pool_retrieve_scope_payload(user, pool_card)
                                payload['card_id'] = pool_card.id
                                return ServiceResult(
                                    success=False,
                                    message=error_message,
                                    data={
                                        'requires_class_change': True,
                                        'retrieve_scope': 'pool_to_pending',
                                        'cards': [payload],
                                    }
                                )

                        # Recheck forbidden IDs after class updates
                        scoped_ids = set(
                            cls._apply_client_staff_row_scope(
                                user,
                                table,
                                IDCard.objects.filter(table=table, id__in=normalized_ids),
                                ignore_pool_bypass=True
                            ).values_list('id', flat=True)
                        )
                        forbidden_ids = [cid for cid in normalized_ids if cid not in scoped_ids]

                    if forbidden_ids:
                        has_pool_mismatch = IDCard.objects.filter(
                            table=table,
                            id__in=forbidden_ids,
                            status='pool',
                        ).exists()
                        if has_pool_mismatch:
                            pool_cards = list(
                                IDCard.objects.select_related('table__group').filter(
                                    table=table,
                                    id__in=forbidden_ids,
                                    status='pool',
                                )[:5]
                            )
                            payload_cards = []
                            for pool_card in pool_cards:
                                if _pool_retrieve_requires_class_change(user, pool_card):
                                    pc_payload = _pool_retrieve_scope_payload(user, pool_card)
                                    pc_payload['card_id'] = pool_card.id
                                    payload_cards.append(pc_payload)
                                    
                            if payload_cards:
                                return ServiceResult(
                                    success=False,
                                    message=_POOL_RETRIEVE_SCOPE_MESSAGE,
                                    data={
                                        'requires_class_change': True,
                                        'retrieve_scope': 'pool_to_pending',
                                        'cards': payload_cards,
                                    }
                                )
                            return ServiceResult(
                                success=False,
                                message=_POOL_RETRIEVE_SCOPE_MESSAGE,
                            )

            if forbidden_ids:
                return ServiceResult(success=False, message='Some selected cards are outside assigned scope')
            
            # Delegate entirely to WorkflowService (handles permissions + all guards)
            from tables.services_workflow import WorkflowService
            return WorkflowService.bulk_transition(table, card_ids, new_status, user=user, request=request)
            
        except Exception as e:
            return ServiceResult(success=False, message=str(e))
