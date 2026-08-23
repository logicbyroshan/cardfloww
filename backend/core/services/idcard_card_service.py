"""
IDCard Card Service — individual card CRUD, status, serialization.

Part of the IDCardService split. Handles:
- IDCard serialization, CRUD, single-field update
- Status change (thin wrapper around WorkflowService)
- Status counts, card-ID listing
- Helper methods for image/mandatory field checks, class/section extraction,
  class filtering, and name-field detection.
"""
import logging
import os
import re
from typing import Dict, Any, List

from django.shortcuts import get_object_or_404
from django.db.models import Count, Q, CharField, Value, IntegerField
from django.db.models import Case, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, Lower
from django.utils.timezone import localtime

from tables.models import Table, IDCard
from .cache_version_service import CacheVersionService
from .base import BaseService, ServiceResult
from mediafiles.services import ImageService

logger = logging.getLogger(__name__)


class IDCardCardService(BaseService):
    """Service for individual ID Card operations."""

    VALID_STATUSES = ['pending', 'verified', 'approved', 'printed', 'download', 'request', 'requested', 'deleted', 'pool', 'reprint']

    # Allowed status transitions: key = current status, value = list of valid target statuses
    VALID_TRANSITIONS = {
        'pending':  ['verified', 'deleted', 'pool'],
        'verified': ['approved', 'pending', 'deleted', 'pool'],
        'approved': ['printed', 'download', 'request', 'verified', 'pending', 'deleted', 'pool'],
        'download': ['printed', 'request', 'approved', 'pending', 'deleted', 'pool'],
        'printed':  ['request', 'approved', 'pending', 'deleted', 'pool'],
        'request':  ['pending', 'approved', 'deleted', 'pool'],
        'pool':     ['pending'],
        'deleted':  ['pending'],
    }

    # Forward transitions that require all image fields to be present
    # key = target status, value = list of source statuses that trigger validation
    FORWARD_IMAGE_CHECK = {
        'verified': ['pending'],       # pending → verified
        'approved': ['verified'],      # verified → approved
    }

    # ==================== Helper Methods ====================

    @classmethod
    def _bump_table_cache_versions(cls, table):
        """Invalidate table-scoped caches affected by card data mutations."""
        try:
            table_id = int(getattr(table, 'id', 0) or 0)
            if table_id > 0:
                CacheVersionService.bump('mob_filter', table_id)
                CacheVersionService.bump('global_search', 'all')

            client_id = int(getattr(getattr(table, 'group', None), 'client_id', 0) or 0)
            if client_id > 0:
                CacheVersionService.bump('class_section', client_id)
                CacheVersionService.bump('client_dash_counts', f'client:{client_id}')
            
            CacheVersionService.bump('admin_dash_counts', 'global')
        except Exception as exc:
            logger.debug('IDCardCardService cache version bump failed: %s', exc)

    @classmethod
    def _get_missing_image_fields(cls, card, image_field_names):
        """Return list of image field names that are missing/pending/not-found on a card."""
        missing = []
        field_data = card.field_data or {}
        for name in image_field_names:
            val = field_data.get(name, '')
            if not val or val == 'NOT_FOUND' or str(val).startswith('PENDING:'):
                missing.append(name)
        return missing

    @classmethod
    def _get_missing_mandatory_fields(cls, card, table_fields):
        """
        Return list of mandatory field names that are empty on a card.
        Checks both text fields and image fields marked as mandatory.
        """
        missing = []
        field_data = card.field_data or {}

        for field in table_fields:
            # Skip if field is not marked as mandatory
            if not field.get('mandatory', False):
                continue

            field_name = field.get('name', '')
            field_type = field.get('type', 'text')

            if not field_name:
                continue

            val = field_data.get(field_name, '')

            # Check if field is empty
            if field_type in cls.IMAGE_FIELD_TYPES:
                # Image field - check for missing/pending/not-found
                if not val or val == 'NOT_FOUND' or str(val).startswith('PENDING:'):
                    missing.append(field_name)
            else:
                # Text field - check for empty value
                if not val or str(val).strip() == '':
                    missing.append(field_name)

        return missing

    @classmethod
    def _get_class_section_field_names(cls, table):
        """Extract class and section field names from table field definitions."""
        class_field, section_field, _course_field, _branch_field = cls._get_class_section_course_branch_field_names(table)
        return class_field, section_field

    @classmethod
    def _get_class_section_course_branch_field_names(cls, table):
        """Extract class, section, course, and branch field names from table definitions."""
        class_field = None
        section_field = None
        course_field = None
        branch_field = None

        class_tokens = {'class', 'std', 'standard', 'grade'}
        section_tokens = {'section', 'sec', 'div', 'division'}
        course_tokens = {'course', 'program', 'programme'}
        branch_tokens = {'branch', 'stream', 'dept', 'department'}

        for field in (table.fields or []):
            if not isinstance(field, dict):
                continue
            fname = str(field.get('name', '') or '').strip()
            ftype = str(field.get('type', '') or '').strip().lower()
            tokens = {
                tok for tok in re.split(r'[^a-z0-9]+', fname.lower())
                if tok
            }

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

    @classmethod
    def normalize_name(cls, name):
        """Normalize field name by removing punctuation and whitespace.
        
        This allows "SCHOLAR NO." to match "SCHOLAR NO" and similar variants.
        Returns a normalized key (alphanumeric only, uppercase) or empty string if name is empty.
        
        Example:
            normalize_name('SCHOLAR NO.') → 'SCHOLARNNO'
            normalize_name('SCHOLAR NO') → 'SCHOLARNNO'
        """
        if not name:
            return ''
        # Remove all non-alphanumeric characters and convert to uppercase
        return re.sub(r'[^A-Z0-9]+', '', str(name).upper())

    @classmethod
    def _apply_class_filter(cls, qs, class_filter, class_field_name, table_id=None):
        """Apply class filter with canonical normalization.

        Finds all raw variants that normalize to the same canonical class
        and matches them all.  E.g. filtering by 'KG1' also finds
        'KG-I', 'KGI', 'LKG', 'kgI', etc.

        table_id scopes the distinct raw-value scan to one table.
        """
        from core.utils.field_utils import normalize_class_value

        norm_filter = normalize_class_value(class_filter)

        base_qs = qs.model.objects.filter(table_id=table_id) if table_id else qs
        all_raw = list(
            base_qs
            .annotate(_cv_raw=Cast(KeyTextTransform(class_field_name, 'field_data'), CharField()))
            .exclude(_cv_raw__isnull=True).exclude(_cv_raw='')
            .order_by()
            .values_list('_cv_raw', flat=True).distinct()
        )

        matching_raw = [r for r in all_raw if normalize_class_value(r) == norm_filter]

        if not matching_raw:
            return qs.none()

        qs = qs.annotate(_cls=KeyTextTransform(class_field_name, 'field_data'))
        q = Q()
        for raw in matching_raw:
            q |= Q(_cls=raw)
        return qs.filter(q)

    @classmethod
    def _apply_compact_text_filter(
        cls,
        qs,
        text_filter,
        field_name,
        *,
        table_id=None,
        alias='_flt_txt',
    ):
        """Apply punctuation/space-insensitive filtering for course/branch text."""
        from core.utils.field_utils import normalize_compact_text_value

        normalized_filter = normalize_compact_text_value(text_filter)
        if not normalized_filter:
            return qs.none()

        base_qs = qs.model.objects.filter(table_id=table_id) if table_id else qs
        all_raw = list(
            base_qs
            .annotate(_fv_raw=Cast(KeyTextTransform(field_name, 'field_data'), CharField()))
            .exclude(_fv_raw__isnull=True).exclude(_fv_raw='')
            .order_by()
            .values_list('_fv_raw', flat=True).distinct()
        )

        matching_raw = [raw for raw in all_raw if normalize_compact_text_value(raw) == normalized_filter]
        if not matching_raw:
            return qs.none()

        qs = qs.annotate(**{alias: Cast(KeyTextTransform(field_name, 'field_data'), CharField())})
        return qs.filter(**{f'{alias}__in': matching_raw})

    @classmethod
    def _get_name_field(cls, table):
        """Get the name/text field from table definitions for sorting."""
        if not table.fields:
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

        for field in (table.fields or []):
            if not isinstance(field, dict):
                continue
            ftype = str(field.get('type', '') or '').strip().lower()
            fname = str(field.get('name', '') or '').strip()
            fname_norm = _norm(fname)
            if ftype == 'name' and fname:
                return fname
            if _is_primary_name_candidate(fname_norm):
                return fname

        # Fallback: first text field
        for field in (table.fields or []):
            if not isinstance(field, dict):
                continue
            ftype = str(field.get('type', '') or '').strip().lower()
            fname = str(field.get('name', '') or '').strip()
            if not fname:
                continue
            if ftype in ('text', 'name', ''):
                return fname
        return None

    @classmethod
    def _apply_search_filter(
        cls,
        queryset,
        search: str,
        table: Table = None,
        json_field: str = 'field_data',
        id_lookup: str = 'id',
    ):
        """Apply a faster, field-aware search filter with safe fallback.

        Behavior is preserved for edge cases by falling back to JSON text
        contains when table metadata is unavailable.
        """
        search = (search or '').strip()
        if not search:
            return queryset

        # Fallback path when we cannot infer searchable keys.
        if not table or not table.fields:
            return queryset.filter(**{f'{json_field}__icontains': search})

        # Split fields so text uses DB filtering and image columns use
        # basename-only matching (filename, not directory path).
        text_fields = []
        image_fields = []
        for field in (table.fields or []):
            fname = (field or {}).get('name', '')
            if not fname or fname.startswith('__'):
                continue
            if cls.is_image_field(field):
                image_fields.append(fname)
                continue
            text_fields.append(fname)

        if not text_fields and not image_fields:
            return queryset.filter(**{f'{json_field}__icontains': search})

        matched_ids = set()

        q = Q()

        # Fast exact PK match for numeric search terms.
        if search.isdigit():
            try:
                q |= Q(**{id_lookup: int(search)})
            except (TypeError, ValueError):
                pass

        annotations = {}
        for idx, field_name in enumerate(text_fields):
            alias = f'_s{idx}'
            annotations[alias] = Cast(KeyTextTransform(field_name, json_field), CharField())
            q |= Q(**{f'{alias}__icontains': search})

        if q:
            text_qs = queryset
            if annotations:
                text_qs = text_qs.annotate(**annotations)
            matched_ids.update(text_qs.filter(q).values_list(id_lookup, flat=True))

        candidate_rows = queryset.values(id_lookup, json_field)
        for row in candidate_rows.iterator(chunk_size=500):
            field_data = row.get(json_field) or {}
            if not isinstance(field_data, dict):
                continue

            if image_fields and any(cls.image_filename_contains_query(field_data.get(fname, ''), search) for fname in image_fields):
                row_id = row.get(id_lookup)
                if row_id is not None:
                    matched_ids.add(row_id)
                continue

            if any(
                isinstance(value, str)
                and (('/' in value) or ('\\' in value) or value.startswith('PENDING:'))
                and cls.image_filename_contains_query(value, search)
                for value in field_data.values()
            ):
                row_id = row.get(id_lookup)
                if row_id is not None:
                    matched_ids.add(row_id)

        if not matched_ids:
            return queryset.none()

        return queryset.filter(**{f'{id_lookup}__in': list(matched_ids)})

    # ==================== Serialization ====================

    @classmethod
    def serialize_card(cls, card: IDCard, sr_no: int = None, table_fields: List[dict] = None) -> Dict[str, Any]:
        """Serialize IDCard to dict"""
        # Strip internal __ref_ keys (used by reupload processor for matching)
        fd = card.field_data or {}
        public_fd = {}
        for k, v in fd.items():
            if isinstance(k, str) and k.startswith('__'):
                continue
            if isinstance(k, str) and isinstance(v, str) and cls.is_image_field_by_name(k):
                value = v.strip()
                if value and '/' not in value and '\\' not in value and not value.startswith('PENDING:'):
                    public_fd[k] = f'PENDING:{os.path.basename(value)}'
                    continue
            public_fd[k] = v
        data = {
            'id': card.id,
            'table_id': card.table_id,
            'field_data': public_fd,
            'photo': fd.get('PHOTO') or (card.photo.url if card.photo else None),
            'status': card.status,
            'status_display': card.get_status_display(),
            'created_at': localtime(card.created_at).strftime('%d-%b-%Y %H:%M'),
            'updated_at': localtime(card.updated_at).strftime('%d-%b-%Y %H:%M'),
            'updated_at_iso': card.updated_at.isoformat() if card.updated_at else None,
            'downloaded_at': localtime(card.downloaded_at).strftime('%d-%b-%Y %H:%M') if card.downloaded_at else None,
            'deleted_at': localtime(card.deleted_at).strftime('%d-%b-%Y %H:%M') if card.deleted_at else None,
            'modified_by': card.modified_by or '',
        }

        if sr_no is not None:
            data['sr_no'] = sr_no

        # Add ordered_fields if table_fields provided
        if table_fields:
            ordered_fields = []
            field_data = card.field_data or {}

            # Create case-insensitive & normalized key lookup dictionaries
            field_data_normalized = {cls.normalize_name(k): v for k, v in field_data.items() if k}

            # Reorder fields: text first, then images in canonical order
            # Must match the template filter reorder_fields_for_display
            reordered_fields = cls.reorder_fields_for_display(table_fields)

            for field in reordered_fields:
                field_name = field['name']
                field_type = field.get('type', 'text')

                # Check if it's an image field
                if cls.is_image_field(field):
                    field_type = 'image'

                # Get value (supports exact, upper, or normalized name lookup)
                norm_name = cls.normalize_name(field_name)
                field_value = field_data.get(field_name)
                if field_value is None or field_value == '':
                    field_value = field_data_normalized.get(norm_name, '')

                # Legacy fallback: if PHOTO field is empty, try card.photo (deprecated ImageField)
                if not field_value and field_name.upper() == 'PHOTO' and card.photo:
                    try:
                        field_value = card.photo.name or card.photo.url
                    except Exception:
                        pass

                ordered_fields.append({
                    'name': field_name,
                    'type': field_type,
                    'value': field_value,
                })

            data['ordered_fields'] = ordered_fields

        return data

    # ==================== List / Query ====================

    @classmethod
    def list_cards(
        cls,
        table_id: int,
        status_filter: str = None,
        offset: int = 0,
        limit: int = 100,
        search: str = '',
        class_filter: str = '',
        section_filter: str = '',
        course_filter: str = '',
        branch_filter: str = '',
        sort_order: str = 'sr-asc',
        image_column: str = '',
        image_condition: str = '',
        from_date: str = '',
        to_date: str = '',
    ) -> ServiceResult:
        """List ID Cards for a table with pagination and server-side filtering."""
        try:
            table = get_object_or_404(Table, id=table_id)

            # Base queryset — use .only() to skip fetching the deprecated photo
            # ImageField and other heavy columns not needed for list serialization.
            cards_query = IDCard.objects.filter(table=table).only(
                'id', 'table_id', 'field_data', 'photo', 'status',
                'created_at', 'updated_at', 'downloaded_at', 'deleted_at',
                'status_changed_at', 'modified_by',
            )

            if status_filter and status_filter in cls.VALID_STATUSES:
                cards_query = cards_query.filter(status=status_filter)

            # --- Server-side search ---
            if search:
                cards_query = cls._apply_search_filter(cards_query, search, table=table)

            # --- Class / Section / Course / Branch filters ---
            if class_filter or section_filter or course_filter or branch_filter:
                class_field_name, section_field_name, course_field_name, branch_field_name = (
                    cls._get_class_section_course_branch_field_names(table)
                )
                if class_filter and class_field_name:
                    cards_query = cls._apply_class_filter(cards_query, class_filter, class_field_name, table_id=table_id)
                if section_filter and section_field_name:
                    cards_query = cards_query.annotate(
                        _sec=KeyTextTransform(section_field_name, 'field_data')
                    ).filter(_sec__iexact=section_filter)
                if course_filter and course_field_name:
                    cards_query = cls._apply_compact_text_filter(
                        cards_query,
                        course_filter,
                        course_field_name,
                        table_id=table_id,
                        alias='_course_cmp',
                    )
                if branch_filter and branch_field_name:
                    cards_query = cls._apply_compact_text_filter(
                        cards_query,
                        branch_filter,
                        branch_field_name,
                        table_id=table_id,
                        alias='_branch_cmp',
                    )

            # --- Image sort filter ---
            # Cast() avoids SQLite crash: JSON_EXTRACT('', '$') is invalid.
            if image_condition:
                if not image_column or image_column == 'all':
                    img_cols = [f['name'] for f in table.fields if f.get('type') == 'image']
                else:
                    img_cols = [c.strip() for c in image_column.split(',') if c.strip()]
                    
                img_conds = [c.strip() for c in image_condition.split(',') if c.strip()]
                
                valid_conds = [c for c in img_conds if c in ('complete', 'pending', 'incomplete')]
                
                if img_cols and valid_conds:
                    main_q = Q()
                    for idx, col in enumerate(img_cols):
                        alias = f'_img_{idx}'
                        cards_query = cards_query.annotate(
                            **{alias: Cast(KeyTextTransform(col, 'field_data'), CharField())}
                        )
                        
                        col_q = Q()
                        for cond in valid_conds:
                            if cond == 'complete':
                                col_q |= Q(**{f'{alias}__isnull': False}) & ~Q(**{f'{alias}': ''}) & ~Q(**{f'{alias}': 'NOT_FOUND'}) & ~Q(**{f'{alias}__startswith': 'PENDING:'})
                            elif cond == 'pending':
                                col_q |= Q(**{f'{alias}__startswith': 'PENDING:'})
                            elif cond == 'incomplete':
                                col_q |= Q(**{f'{alias}__isnull': True}) | Q(**{f'{alias}': ''}) | Q(**{f'{alias}': 'NOT_FOUND'})
                                
                        main_q |= col_q
                        
                    cards_query = cards_query.filter(main_q)

            # --- DateTime range filter (download list) ---
            if status_filter == 'download' and (from_date or to_date):
                from datetime import datetime as dt
                from django.utils.timezone import make_aware, is_naive
                if from_date:
                    try:
                        from_dt = dt.fromisoformat(from_date)
                        from_dt = make_aware(from_dt) if is_naive(from_dt) else from_dt
                        cards_query = cards_query.filter(downloaded_at__gte=from_dt)
                    except (ValueError, TypeError):
                        pass
                if to_date:
                    try:
                        to_dt = dt.fromisoformat(to_date)
                        to_dt = make_aware(to_dt) if is_naive(to_dt) else to_dt
                        cards_query = cards_query.filter(downloaded_at__lte=to_dt)
                    except (ValueError, TypeError):
                        pass

            # --- Sorting ---
            # sr-asc default: newest status movement first (with created_at fallback).
            if sort_order == 'sr-desc':
                cards_query = cards_query.order_by('created_at', '-id')
            elif sort_order in ('name-asc', 'name-desc'):
                # Sort by detected name field, case-insensitive.
                # Case/When pushes NULL/empty names to the end.
                name_field = cls._get_name_field(table)
                if name_field:
                    cards_query = cards_query.annotate(
                        _name_raw=Cast(KeyTextTransform(name_field, 'field_data'), CharField()),
                        _name_sort=Lower(Coalesce(
                            Cast(KeyTextTransform(name_field, 'field_data'), CharField()),
                            Value(''),
                            output_field=CharField(),
                        )),
                        _name_empty=Case(
                            When(
                                Q(_name_raw__isnull=True) | Q(_name_raw=''),
                                then=Value(1),
                            ),
                            default=Value(0),
                            output_field=IntegerField(),
                        ),
                    )
                    if sort_order == 'name-asc':
                        cards_query = cards_query.order_by('_name_empty', '_name_sort', 'id')
                    else:
                        cards_query = cards_query.order_by('_name_empty', '-_name_sort', '-id')
                else:
                    cards_query = cards_query.order_by('id' if sort_order == 'name-asc' else '-id')
            elif sort_order == 'date-new':
                cards_query = cards_query.order_by('-updated_at', '-id')
            elif sort_order == 'date-old':
                cards_query = cards_query.order_by('updated_at', 'id')
            else:
                # Default: sr-asc — newest action first in destination list.
                # Download/pool keep dedicated movement timestamps.
                # Other statuses use status_changed_at with created_at fallback.
                if status_filter == 'download':
                    cards_query = cards_query.order_by('-downloaded_at', '-id')
                elif status_filter == 'pool':
                    cards_query = cards_query.order_by('-deleted_at', '-id')
                else:
                    cards_query = cards_query.annotate(
                        _status_sort_at=Coalesce('status_changed_at', 'created_at')
                    ).order_by('-_status_sort_at', '-id')

            total_count = cards_query.count()
            cards = cards_query[offset:offset + limit]

            # Serialize cards
            card_list = []
            for idx, card in enumerate(cards):
                card_list.append(cls.serialize_card(
                    card,
                    sr_no=offset + idx + 1,
                    table_fields=table.fields
                ))

            # Get status counts
            status_counts = cls.get_status_counts(table)

            return ServiceResult(
                success=True,
                data={
                    'cards': card_list,
                    'total_count': total_count,
                    'offset': offset,
                    'limit': limit,
                    'has_more': offset + limit < total_count,
                    'status_counts': status_counts,
                    'table': cls.serialize_table(table),
                }
            )

        except Exception as e:
            logger.error("list_cards error for table_id=%s: %s", table_id, e, exc_info=True)
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def get_status_counts(cls, table: Table) -> Dict[str, int]:
        """Get count of cards by status for a table"""
        counts = {status: 0 for status in cls.VALID_STATUSES}
        counts['total'] = 0

        # Efficient aggregation — .order_by() strips the model's default
        # ordering so the DB doesn't add a useless ORDER BY to the GROUP BY.
        status_agg = IDCard.objects.filter(table=table).order_by().values('status').annotate(count=Count('id'))

        for item in status_agg:
            counts[item['status']] = item['count']
            counts['total'] += item['count']

        return counts

    @classmethod
    def get_all_card_ids(cls, table_id: int, status_filter: str = None,
                         search: str = '', class_filter: str = '', section_filter: str = '',
                         course_filter: str = '', branch_filter: str = '',
                         from_date: str = '', to_date: str = '',
                         image_column: str = '', image_condition: str = '') -> ServiceResult:
        """Get all card IDs for a table (for Select All). Capped at 50,000."""
        MAX_CARD_IDS = 10000
        try:
            table = get_object_or_404(Table, id=table_id)

            cards_query = IDCard.objects.filter(table=table)
            if status_filter and status_filter in cls.VALID_STATUSES:
                cards_query = cards_query.filter(status=status_filter)

            # Apply search filter
            if search:
                cards_query = cls._apply_search_filter(cards_query, search, table=table)

            # Apply class/section/course/branch filters
            if class_filter or section_filter or course_filter or branch_filter:
                class_field_name, section_field_name, course_field_name, branch_field_name = (
                    cls._get_class_section_course_branch_field_names(table)
                )
                if class_filter and class_field_name:
                    cards_query = cls._apply_class_filter(cards_query, class_filter, class_field_name, table_id=table_id)
                if section_filter and section_field_name:
                    cards_query = cards_query.annotate(
                        _sec=KeyTextTransform(section_field_name, 'field_data')
                    ).filter(_sec__iexact=section_filter)
                if course_filter and course_field_name:
                    cards_query = cls._apply_compact_text_filter(
                        cards_query,
                        course_filter,
                        course_field_name,
                        table_id=table_id,
                        alias='_course_cmp',
                    )
                if branch_filter and branch_field_name:
                    cards_query = cls._apply_compact_text_filter(
                        cards_query,
                        branch_filter,
                        branch_field_name,
                        table_id=table_id,
                        alias='_branch_cmp',
                    )

            # Apply image sort filter
            # Cast() avoids SQLite crash: JSON_EXTRACT('', '$') is invalid.
            if image_column and image_condition in ('complete', 'pending', 'incomplete'):
                cards_query = cards_query.annotate(
                    _img=Cast(KeyTextTransform(image_column, 'field_data'), CharField())
                )
                if image_condition == 'complete':
                    cards_query = cards_query.exclude(_img__isnull=True).exclude(_img='').exclude(_img='NOT_FOUND')
                    cards_query = cards_query.exclude(_img__startswith='PENDING:')
                elif image_condition == 'pending':
                    cards_query = cards_query.filter(_img__startswith='PENDING:')
                elif image_condition == 'incomplete':
                    cards_query = cards_query.filter(Q(_img__isnull=True) | Q(_img='') | Q(_img='NOT_FOUND'))

            # DateTime range filter applies only to download status.
            if status_filter == 'download' and (from_date or to_date):
                if from_date:
                    try:
                        from django.utils.dateparse import parse_datetime
                        dt = parse_datetime(from_date)
                        if dt:
                            cards_query = cards_query.filter(downloaded_at__gte=dt)
                    except (ValueError, TypeError):
                        pass
                if to_date:
                    try:
                        from django.utils.dateparse import parse_datetime
                        dt = parse_datetime(to_date)
                        if dt:
                            cards_query = cards_query.filter(downloaded_at__lte=dt)
                    except (ValueError, TypeError):
                        pass

            card_ids = list(cards_query.order_by('-id').values_list('id', flat=True)[:MAX_CARD_IDS])

            return ServiceResult(
                success=True,
                data={'card_ids': card_ids, 'total_count': len(card_ids)}
            )
        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    # ==================== CRUD ====================

    @classmethod
    def create_card(
        cls,
        table_id: int,
        field_data: Dict[str, Any],
        image_files: Dict[str, Any] = None,
        uploaded_by=None,
        legacy_photo_file=None,
    ) -> ServiceResult:
        """Create a new ID Card.

        Args:
            table_id: Table PK.
            field_data: Dict of field values (text + image paths).
            image_files: Dict of uploaded files keyed by ``image_<field_name>``.
            uploaded_by: User who triggered the upload.
            legacy_photo_file: Optional UploadedFile for the legacy ``photo``
                               key (pre-field-config tables).
        """
        try:
            from django.db import transaction
            table = get_object_or_404(Table, id=table_id)
            client = table.organisation

            # Uppercase text values only — preserve image paths
            field_data = cls.uppercase_field_data_selective(field_data, table.fields)

            # Normalize keys to canonical table field names case-insensitively
            canonical_field_data = {}
            for key, value in field_data.items():
                if not isinstance(key, str):
                    canonical_field_data[key] = value
                    continue
                key_upper = key.strip().upper()
                canonical_key = key
                for field in table.fields:
                    if field.get('name', '').strip().upper() == key_upper:
                        canonical_key = field.get('name')
                        break
                canonical_field_data[canonical_key] = value
            field_data = canonical_field_data

            normalized_field_data = {
                str(k).strip().upper(): v
                for k, v in field_data.items()
                if isinstance(k, str)
            }

            # Track saved images for dual-write (Phase 2)
            saved_images = []

            # Handle image uploads if provided (outside transaction — disk I/O)
            image_counter = 0
            if image_files:
                for field in table.fields:
                    if cls.is_image_field(field):
                        field_name = field['name']
                        file_key = f"image_{field_name}"
                        field_key_upper = str(field_name).strip().upper()

                        if file_key in image_files:
                            image_counter += 1
                            uploaded_file = image_files[file_key]
                            img_bytes = uploaded_file.read()
                            uploaded_file.seek(0)
                            original_ext = '.jpg'
                            if hasattr(uploaded_file, 'name') and uploaded_file.name:
                                _, _ext = __import__('os').path.splitext(uploaded_file.name)
                                if _ext:
                                    original_ext = _ext.lower()
                            result = ImageService.save_new_image(
                                image_bytes=img_bytes,
                                client=client,
                                field_name=field_name,
                                card=None,  # card not yet created
                                batch_counter=image_counter,
                                original_ext=original_ext,
                                original_filename=getattr(uploaded_file, 'name', None),
                                uploaded_by=uploaded_by,
                            )
                            if result.success:
                                field_data[field_name] = result.data['final_value']
                                saved_images.append({
                                    'path': result.data['final_value'],
                                    'field_name': field_name,
                                    'field_type': field.get('type', 'photo'),
                                    'original_filename': getattr(uploaded_file, 'name', None)
                                })

            # Normalize image fields even when the user only typed a filename.
            for field in table.fields:
                if not cls.is_image_field(field):
                    continue

                field_name = field['name']
                field_key_upper = str(field_name).strip().upper()

                uploaded_file = None
                if image_files:
                    uploaded_file = image_files.get(f"image_{field_name}")

                raw_value = field_data.get(field_name)
                if raw_value is None:
                    raw_value = normalized_field_data.get(field_key_upper)

                if uploaded_file is None and raw_value is None:
                    continue

                if uploaded_file is None:
                    raw_text = str(raw_value or '').strip()
                    if raw_text and '/' not in raw_text and '\\' not in raw_text and not raw_text.startswith('PENDING:'):
                        field_data[field_name] = f'PENDING:{os.path.basename(raw_text)}'
                        continue

                    result = ImageService.process_image_field(
                        field_name=field_name,
                        new_value=raw_value,
                        existing_value='',
                        client=client,
                        card=None,
                        uploaded_file=None,
                        batch_counter=1,
                        uploaded_by=uploaded_by,
                    )
                    if result.success:
                        for existing_key in [
                            key for key in list(field_data.keys())
                            if isinstance(key, str) and str(key).strip().upper() == field_key_upper and key != field_name
                        ]:
                            field_data.pop(existing_key, None)
                        field_data[field_name] = result.data.get('final_value', raw_value)

            # Safely handle bare filenames in image fields only (from table schema)
            for field in table.fields:
                if not cls.is_image_field(field):
                    continue
                field_name = field['name']
                value = str(field_data.get(field_name, '') or '').strip()
                if value and '/' not in value and '\\' not in value and not value.startswith('PENDING:'):
                    field_data[field_name] = f'PENDING:{os.path.basename(value)}'

            # Atomic block: card creation + media records together
            with transaction.atomic():
                from tables.services_workflow import WorkflowService
                card = IDCard.objects.create(
                    table=table,
                    field_data=field_data,
                    status=WorkflowService.INITIAL_STATUS
                )

                normalized_after_create = dict(card.field_data or {})
                normalized_after_create_changed = False
                for field in table.fields:
                    if not cls.is_image_field(field):
                        continue

                    field_name = field['name']
                    current_value = str(normalized_after_create.get(field_name, '') or '').strip()
                    if current_value and '/' not in current_value and '\\' not in current_value and not current_value.startswith('PENDING:'):
                        normalized_after_create[field_name] = f'PENDING:{os.path.basename(current_value)}'
                        normalized_after_create_changed = True

                if normalized_after_create_changed:
                    card.field_data = normalized_after_create
                    card.save(update_fields=['field_data'])

                # DUAL-WRITE: Create CardMedia records for saved images
                for img_info in saved_images:
                    try:
                        ImageService.create_media_record(
                            saved_path=img_info['path'],
                            client=client,
                            card=card,
                            field_name=img_info['field_name'],
                            media_type=img_info['field_type'],
                            original_filename=img_info['original_filename'],
                            uploaded_by=uploaded_by
                        )
                    except Exception as media_err:
                        logger.warning("Failed to create CardMedia for %s: %s", img_info['field_name'], media_err)

                # Legacy 'photo' key — old clients may send a separate photo file
                if legacy_photo_file:
                    try:
                        original_ext = '.jpg'
                        if hasattr(legacy_photo_file, 'name') and legacy_photo_file.name:
                            _, _ext = __import__('os').path.splitext(legacy_photo_file.name)
                            if _ext:
                                original_ext = _ext.lower()
                        img_bytes = legacy_photo_file.read()
                        legacy_photo_file.seek(0)
                        image_counter += 1

                        # Dynamically find the exact case of the photo field name from table config
                        image_field_names = cls.get_image_field_names(table.fields)
                        main_photo_field_name = None
                        for name in image_field_names:
                            name_l = name.lower()
                            if name_l in ('photo', 'student_photo', 'student photo', 'image'):
                                main_photo_field_name = name
                                break
                        if not main_photo_field_name:
                            for name in image_field_names:
                                name_l = name.lower()
                                if 'photo' in name_l or 'image' in name_l:
                                    main_photo_field_name = name
                                    break
                        if not main_photo_field_name:
                            main_photo_field_name = 'PHOTO'

                        result = ImageService.save_new_image(
                            image_bytes=img_bytes,
                            client=client,
                            field_name=main_photo_field_name,
                            card=card,
                            batch_counter=image_counter,
                            original_ext=original_ext,
                            original_filename=getattr(legacy_photo_file, 'name', None),
                            uploaded_by=uploaded_by,
                        )
                        if result.success and result.data.get('final_value'):
                            fd = card.field_data or {}
                            fd[main_photo_field_name] = result.data['final_value']
                            # Clean up alternative casing variants to prevent conflicts
                            for variant in (main_photo_field_name, 'PHOTO', 'Photo', 'photo'):
                                if variant in fd and variant != main_photo_field_name:
                                    del fd[variant]
                            card.field_data = fd
                            card.save(update_fields=['field_data'])
                    except Exception as photo_err:
                        logger.error("Error saving legacy photo during create: %s", photo_err)

            cls._bump_table_cache_versions(table)

            return ServiceResult(
                success=True,
                message='ID Card created successfully!',
                data={'card': cls.serialize_card(card, sr_no=1, table_fields=table.fields)}
            )

        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def get_card(cls, card_id: int) -> ServiceResult:
        """Get a single ID Card"""
        try:
            card = get_object_or_404(IDCard.objects.select_related('table'), id=card_id)

            data = cls.serialize_card(card)
            data['table_name'] = card.table.name

            return ServiceResult(success=True, data={'card': data})
        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def update_card(
        cls,
        card_id: int,
        field_data: Dict[str, Any] = None,
        status: str = None,
        image_files: Dict[str, Any] = None,
        uploaded_by=None,
        expected_updated_at: str = None,
        legacy_photo_file=None,
        modified_by: str = None,
        force: bool = False,
        base_field_data: Dict[str, Any] = None,
    ) -> ServiceResult:
        """Update an ID Card with smart 3-way field-level merge.

        Args:
            card_id: IDCard PK.
            field_data: Desired final field_data from the saving user.
            status: Ignored — use WorkflowService.transition().
            image_files: Dict of uploaded files keyed by ``image_<field_name>``.
            uploaded_by: User who triggered the upload.
            expected_updated_at: ISO-8601 timestamp captured when the user
                opened the card. Used to detect concurrent edits so we can
                perform a 3-way merge instead of overwriting blindly.
            legacy_photo_file: Optional UploadedFile for the legacy ``photo``
                               key (pre-field-config tables).
            base_field_data: Snapshot of field_data when the user opened the
                card. Combined with ``expected_updated_at`` this lets us compute
                exactly which fields the user changed so we can merge them
                onto the concurrent DB state without clobbering unrelated edits.
        """
        try:
            from django.db import transaction as db_transaction
            from django.utils.dateparse import parse_datetime

            with db_transaction.atomic():
                card = IDCard.objects.select_for_update().get(id=card_id)
                table = card.table
                client = getattr(table, 'organisation', None) or getattr(getattr(table, 'group', None), 'client', None)

                # ── Smart 3-way field-level merge on concurrent edit ──
                # When two users edit the same card simultaneously:
                #   - Fields only this user changed  → this user's value wins
                #   - Fields only the other user changed → other user's value kept
                #   - Fields changed by both           → this user's value wins (last writer per field)
                #   - Images uploaded                  → always applied
                if expected_updated_at and not force:
                    expected_dt = parse_datetime(expected_updated_at)
                    if expected_dt and card.updated_at:
                        import datetime as _dt
                        from django.utils.timezone import is_naive, make_aware
                        _utc = _dt.timezone.utc
                        dt_expected = make_aware(expected_dt) if is_naive(expected_dt) else expected_dt
                        dt_card = make_aware(card.updated_at) if is_naive(card.updated_at) else card.updated_at
                        if abs((dt_card.astimezone(_utc) - dt_expected.astimezone(_utc)).total_seconds()) > 1:
                            # Concurrent edit detected — perform field-level merge
                            if field_data is not None:
                                db_data = {str(k).strip().upper(): v for k, v in (card.field_data or {}).items()}
                                incoming = {str(k).strip().upper(): v for k, v in field_data.items()}
                                if base_field_data is not None:
                                    # True 3-way merge: only apply fields this user actually changed
                                    base = {str(k).strip().upper(): v for k, v in base_field_data.items()}
                                    merged = dict(db_data)  # start from what's in DB (other user's save)
                                    for key, our_val in incoming.items():
                                        base_val = base.get(key)
                                        # Apply our change if we actually modified this field
                                        # (our value differs from what we saw when we opened the card)
                                        if str(our_val or '').strip() != str(base_val or '').strip():
                                            merged[key] = our_val
                                    field_data = {k: v for k, v in merged.items()}  # normalised to uppercase keys
                                # else: no base provided → use incoming as-is (full overwrite, backward compat)

                existing_data = card.field_data or {}
                image_field_names = cls.get_image_field_names(table.fields)

                # Be tolerant to payload shape/casing differences coming from multipart UI flows.
                if not isinstance(field_data, dict):
                    field_data = {}

                has_any_field_data = bool(field_data)
                normalized_field_data = {
                    str(k).strip().upper(): v
                    for k, v in field_data.items()
                    if isinstance(k, str)
                }
                normalized_image_files = {
                    str(k).strip().upper(): v
                    for k, v in (image_files or {}).items()
                    if isinstance(k, str)
                }

                if has_any_field_data or image_files:
                    if has_any_field_data:
                        field_data = cls.uppercase_field_data_selective(field_data, table.fields)

                    # Build field name lookup maps (exact and normalized) to handle punctuation variants
                    valid_field_map = {}  # lowercase → canonical
                    normalized_field_map = {}  # normalized (no punct) → canonical
                    for table_field in (table.fields or []):
                        if not isinstance(table_field, dict):
                            continue
                        raw_name = str(table_field.get('name', '')).strip()
                        if not raw_name:
                            continue
                        raw_key = raw_name.lower()
                        normalized_key = cls.normalize_name(raw_name)
                        if raw_key not in valid_field_map:
                            valid_field_map[raw_key] = raw_name
                        if normalized_key and normalized_key not in normalized_field_map:
                            normalized_field_map[normalized_key] = raw_name

                    # Merge text (non-image) fields, normalizing field names to canonical
                    for key, value in field_data.items():
                        # Try exact match first, then normalized match
                        canonical_key = None
                        if key.lower() in valid_field_map:
                            canonical_key = valid_field_map[key.lower()]
                        else:
                            normalized_key = cls.normalize_name(key)
                            if normalized_key in normalized_field_map:
                                canonical_key = normalized_field_map[normalized_key]
                        
                        # Use canonical key if found, otherwise use original key
                        if canonical_key is None:
                            canonical_key = key
                        
                        if canonical_key not in image_field_names:
                            existing_data[canonical_key] = value

                    # Process each image field via ImageService.process_image_field
                    image_counter = 0
                    for img_field in image_field_names:
                        uploaded_file = image_files.get(f"image_{img_field}") if image_files else None

                        # Fallback: case-insensitive lookup for multipart keys.
                        if uploaded_file is None and normalized_image_files:
                            exact_key_upper = f"image_{img_field}".strip().upper()
                            uploaded_file = normalized_image_files.get(exact_key_upper)

                        # Fallback: scan image_* keys and compare suffix case-insensitively.
                        if uploaded_file is None and normalized_image_files:
                            img_field_upper = str(img_field).strip().upper()
                            for file_key_upper, file_obj in normalized_image_files.items():
                                if not file_key_upper.startswith('IMAGE_'):
                                    continue
                                key_suffix_upper = file_key_upper[6:].strip().upper()
                                if cls.normalize_name(key_suffix_upper) == cls.normalize_name(img_field_upper):
                                    uploaded_file = file_obj
                                    break

                        # Check if the field was explicitly sent in the payload (casing tolerant)
                        was_sent = False
                        new_value = None

                        if img_field in field_data:
                            was_sent = True
                            new_value = field_data[img_field]
                        else:
                            img_field_upper = str(img_field).strip().upper()
                            if img_field_upper in normalized_field_data:
                                was_sent = True
                                new_value = normalized_field_data[img_field_upper]

                        # If explicitly sent as None/null or empty string, treat it as removal (new_value = "")
                        if was_sent and (new_value is None or new_value == ''):
                            new_value = ''

                        if uploaded_file is not None or was_sent:
                            existing_value = existing_data.get(img_field, '')
                            image_counter += 1
                            result = ImageService.process_image_field(
                                field_name=img_field,
                                new_value=new_value,
                                existing_value=existing_value,
                                client=client,
                                card=card,
                                uploaded_file=uploaded_file,
                                batch_counter=image_counter,
                                uploaded_by=uploaded_by,
                            )
                            if result.success:
                                existing_data[img_field] = result.data.get('final_value', existing_value)
                            else:
                                logger.warning("process_image_field failed for %s: %s", img_field, result.message)

                # Legacy 'photo' key
                if legacy_photo_file:
                    # Dynamically find the exact case of the photo field name from table config
                    image_field_names = cls.get_image_field_names(table.fields)
                    main_photo_field_name = None
                    for name in image_field_names:
                        name_l = name.lower()
                        if name_l in ('photo', 'student_photo', 'student photo', 'image'):
                            main_photo_field_name = name
                            break
                    if not main_photo_field_name:
                        for name in image_field_names:
                            name_l = name.lower()
                            if 'photo' in name_l or 'image' in name_l:
                                main_photo_field_name = name
                                break
                    if not main_photo_field_name:
                        main_photo_field_name = 'PHOTO'

                    existing_photo = existing_data.get(main_photo_field_name, '')
                    if not existing_photo:
                        for variant in ('PHOTO', 'Photo', 'photo'):
                            if existing_data.get(variant):
                                existing_photo = existing_data[variant]
                                break

                    result = ImageService.process_image_field(
                        field_name=main_photo_field_name,
                        new_value=None,  # upload takes precedence
                        existing_value=existing_photo,
                        client=client,
                        card=card,
                        uploaded_file=legacy_photo_file,
                        batch_counter=9,
                        uploaded_by=uploaded_by,
                    )
                    if result.success and result.data.get('action') == 'upload':
                        existing_data[main_photo_field_name] = result.data['final_value']
                        # Clean up alternative casing variants to prevent conflicts
                        for variant in (main_photo_field_name, 'PHOTO', 'Photo', 'photo'):
                            if variant in existing_data and variant != main_photo_field_name:
                                del existing_data[variant]
                    elif not result.success:
                        logger.warning("Could not save legacy photo: %s", result.message)

                card.field_data = existing_data

                # Track who performed the update
                if modified_by:
                    card.modified_by = modified_by
                elif uploaded_by and hasattr(uploaded_by, 'username'):
                    card.modified_by = uploaded_by.username

                # Update modification dates so card bubbles to top on edit
                from django.utils import timezone
                now_dt = timezone.now()
                card.status_changed_at = now_dt
                if card.status == 'download':
                    card.downloaded_at = now_dt
                elif card.status == 'pool':
                    card.deleted_at = now_dt

                # Status changes MUST go through WorkflowService.transition().
                if status:
                    logger.warning(
                        "IDCardService.update_card() called with status=%s for card %s — "
                        "ignored. Use WorkflowService.transition() instead.",
                        status, card_id
                    )

                card.save()

            # Refresh updated_at after commit so the caller can send it
            # back for the next concurrency check.
            card.refresh_from_db(fields=['updated_at'])
            cls._bump_table_cache_versions(table)

            card_data = cls.serialize_card(card)
            # Include ISO updated_at for concurrency round-trip
            card_data['updated_at_iso'] = card.updated_at.isoformat() if card.updated_at else None

            return ServiceResult(
                success=True,
                message='ID Card updated successfully!',
                data={'card': card_data}
            )

        except IDCard.DoesNotExist:
            return ServiceResult(success=False, message='Card not found')
        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def update_single_field(cls, card_id: int, field: str, value: Any, modified_by: str = None) -> ServiceResult:
        """Update a single field on an ID Card (for inline editing)"""
        try:
            from django.db import transaction
            with transaction.atomic():
                card = IDCard.objects.select_for_update().get(id=card_id)
                table = card.table

                if not field:
                    return ServiceResult(success=False, message='Field name is required!')

                field_name = str(field).strip()
                if not field_name:
                    return ServiceResult(success=False, message='Field name is required!')

                is_path_field = False
                # Resolve Photo Path column updates back to the base photo field
                if field_name.lower().endswith(' path'):
                    possible_base = field_name[:-5].strip()
                    for f in (table.fields or []):
                        if not isinstance(f, dict):
                            continue
                        fname = str(f.get('name', '')).strip()
                        ftype = str(f.get('type', 'text')).strip().lower()
                        if ftype in ('photo', 'rel_photo') and fname.lower() == possible_base.lower():
                            field_name = fname
                            is_path_field = True
                            break

                valid_field_map = {}
                normalized_field_map = {}
                for table_field in (table.fields or []):
                    if not isinstance(table_field, dict):
                        continue
                    raw_name = str(table_field.get('name', '')).strip()
                    if not raw_name:
                        continue

                    raw_key = raw_name.lower()
                    normalized_key = cls.normalize_name(raw_name)

                    if raw_key not in valid_field_map:
                        valid_field_map[raw_key] = raw_name
                    if normalized_key and normalized_key not in normalized_field_map:
                        normalized_field_map[normalized_key] = raw_name

                normalized_field = field_name.lower()
                normalized_key = cls.normalize_name(field_name)

                if normalized_field in valid_field_map:
                    canonical_field = valid_field_map[normalized_field]
                elif normalized_key in normalized_field_map:
                    canonical_field = normalized_field_map[normalized_key]
                else:
                    return ServiceResult(success=False, message='Invalid field name')

                field_data = card.field_data or {}
                orig_field_val = field_data.get(canonical_field)

                if cls.is_image_field_name_for_table(canonical_field, table.fields):
                    existing_value = field_data.get(canonical_field, '')
                    new_img_value = '' if (value is None or value == '') else value

                    if is_path_field:
                        import os
                        clean_val = str(new_img_value or '').strip()
                        if clean_val.upper().startswith('PENDING:'):
                            clean_val = clean_val[8:].strip()

                        # Extract base filename (without directory or extension)
                        submitted_filename = os.path.basename(clean_val.replace('\\', '/'))
                        submitted_base = os.path.splitext(submitted_filename)[0].strip()

                        existing_str = str(existing_value or '').strip()
                        existing_filename = os.path.basename(existing_str.replace('PENDING:', '').replace('\\', '/'))
                        existing_base = os.path.splitext(existing_filename)[0].strip()

                        is_existing_real_image = (
                            bool(existing_str)
                            and not existing_str.upper().startswith('PENDING:')
                        )

                        if not submitted_base:
                            # User cleared the path field
                            field_data[canonical_field] = ''
                            card.field_data = field_data
                            card.save()
                            cls._bump_table_cache_versions(table)

                            return ServiceResult(
                                success=True,
                                message='Field updated successfully!',
                                data={
                                    'field': canonical_field,
                                    'value': '',
                                    'is_path_field': True,
                                    'photo_field_name': canonical_field,
                                    'photo_field_value': '',
                                }
                            )

                        if is_existing_real_image and (submitted_base.lower() == existing_base.lower()):
                            # User clicked or re-entered the exact same base path of an existing real image!
                            # PRESERVE existing_value 100% UNTOUCHED!
                            field_data[canonical_field] = existing_value
                            card.field_data = field_data
                            card.save()
                            cls._bump_table_cache_versions(table)

                            return ServiceResult(
                                success=True,
                                message='Field updated successfully!',
                                data={
                                    'field': canonical_field,
                                    'value': existing_value,
                                    'is_path_field': True,
                                    'photo_field_name': canonical_field,
                                    'photo_field_value': existing_value,
                                }
                            )

                        # Check if CardMedia or physical file has an existing real image for submitted_base
                        real_media_path = None
                        try:
                            from mediafiles.models import CardMedia
                            client_for_media = getattr(table, 'organisation', None) or getattr(getattr(table, 'group', None), 'client', None)
                            media_qs = CardMedia.objects.filter(client=client_for_media) if client_for_media else CardMedia.objects.none()
                            for media in media_qs:
                                m_file = str(media.file or '')
                                m_orig = str(media.original_filename or '')
                                m_file_base = os.path.splitext(os.path.basename(m_file.replace('\\', '/')))[0].lower()
                                m_orig_base = os.path.splitext(os.path.basename(m_orig.replace('\\', '/')))[0].lower()
                                if submitted_base.lower() == m_file_base or submitted_base.lower() == m_orig_base:
                                    real_media_path = m_file
                                    break
                        except Exception:
                            pass

                        # Also check physical image file on disk in media_root
                        if not real_media_path:
                            from django.conf import settings
                            media_root = getattr(settings, 'MEDIA_ROOT', '')
                            if media_root:
                                client_id_str = str(table.organisation_id) if getattr(table, 'organisation_id', None) else ''
                                # Check client specific paths first
                                possible_rel_paths = []
                                if client_id_str:
                                    possible_rel_paths.extend([
                                        f"idcard_photos/{client_id_str}/{submitted_base}.jpg",
                                        f"idcard_photos/{client_id_str}/{submitted_base}.jpeg",
                                        f"idcard_photos/{client_id_str}/{submitted_base}.png",
                                        f"card_media/{client_id_str}/photo/{submitted_base}.jpg",
                                        f"card_media/{client_id_str}/photo/{submitted_base}.jpeg",
                                        f"card_media/{client_id_str}/photo/{submitted_base}.png",
                                    ])
                                for rel_p in possible_rel_paths:
                                    full_p = os.path.join(media_root, rel_p.replace('/', os.sep))
                                    if os.path.exists(full_p):
                                        real_media_path = rel_p
                                        break

                                # Fallback: search all media subfolders for submitted_base
                                if not real_media_path:
                                    for sub_folder in ['idcard_photos', 'card_media']:
                                        search_dir = os.path.join(media_root, sub_folder)
                                        if os.path.exists(search_dir):
                                            for root_dir, _, filenames in os.walk(search_dir):
                                                for fn in filenames:
                                                    b_name, b_ext = os.path.splitext(fn)
                                                    if b_name.lower() == submitted_base.lower() and b_ext.lower() in ('.jpg', '.jpeg', '.png', '.webp'):
                                                        real_media_path = os.path.relpath(os.path.join(root_dir, fn), media_root).replace('\\', '/')
                                                        break
                                                if real_media_path:
                                                    break

                        if real_media_path:
                            field_data[canonical_field] = real_media_path
                            card.field_data = field_data
                            if modified_by:
                                card.modified_by = modified_by
                            card.save()
                            cls._bump_table_cache_versions(table)

                            return ServiceResult(
                                success=True,
                                message='Field updated successfully!',
                                data={
                                    'field': canonical_field,
                                    'value': real_media_path,
                                    'is_path_field': True,
                                    'photo_field_name': canonical_field,
                                    'photo_field_value': real_media_path,
                                }
                            )

                        # User changed path to a new path for which no uploaded image file exists:
                        # Set to PENDING:<submitted_base> (old image file stays soft-preserved in storage/CardMedia)
                        _, ext_val = os.path.splitext(submitted_filename)
                        ext = ext_val if ext_val else ''
                        pending_val = f"PENDING:{submitted_base}{ext}" if ext else f"PENDING:{submitted_base}"

                        field_data[canonical_field] = pending_val
                        card.field_data = field_data
                        if modified_by:
                            card.modified_by = modified_by
                        card.save()
                        cls._bump_table_cache_versions(table)

                        return ServiceResult(
                            success=True,
                            message='Field updated successfully!',
                            data={
                                'field': canonical_field,
                                'value': pending_val,
                                'is_path_field': True,
                                'photo_field_name': canonical_field,
                                'photo_field_value': pending_val,
                            }
                        )
                    try:
                        client_for_img = getattr(table, 'organisation', None) or getattr(getattr(table, 'group', None), 'client', None)
                        result = ImageService.process_image_field(
                            field_name=canonical_field,
                            new_value=new_img_value,
                            existing_value=existing_value,
                            client=client_for_img,
                            card=card,
                            uploaded_file=None,
                            batch_counter=1,
                            uploaded_by=None,
                        )
                        if result.success:
                            field_data[canonical_field] = result.data.get('final_value', new_img_value)
                        else:
                            field_data[canonical_field] = new_img_value
                    except Exception:
                        field_data[canonical_field] = new_img_value
                else:
                    if isinstance(value, str):
                        field_data[canonical_field] = value.upper()
                    else:
                        field_data[canonical_field] = value

                card.field_data = field_data
                if modified_by:
                    card.modified_by = modified_by

                # Update modification dates so card bubbles to top on edit
                from django.utils import timezone
                now_dt = timezone.now()
                card.status_changed_at = now_dt
                if card.status == 'download':
                    card.downloaded_at = now_dt
                elif card.status == 'pool':
                    card.deleted_at = now_dt
                card.save()
                cls._bump_table_cache_versions(table)

                # Record structured AuditEvent and Reversible Operation delta
                try:
                    from operations.services import AuditService, OperationEngine
                    final_val = field_data.get(canonical_field, '')
                    org = getattr(table, 'organisation', None) or getattr(getattr(table, 'group', None), 'client', None)
                    if org and orig_field_val != final_val:
                        AuditService.record_event(
                            organisation=org,
                            actor=None,
                            event_type='update',
                            target_type='card',
                            target_id=card.id,
                            target_name=f"Card #{card.id}",
                            target_table=table,
                            field_deltas=[{
                                'field_name': canonical_field,
                                'before_value': orig_field_val,
                                'after_value': final_val,
                                'change_type': 'field_edit',
                            }],
                            visibility_scope='ORGANISATION',
                            source='inline_cell_edit',
                        )
                        OperationEngine.record_operation(
                            organisation=org,
                            user=None,
                            operation_type='card_update',
                            target_table=table,
                            description=f"Edited {canonical_field} for Card #{card.id}: {orig_field_val} -> {final_val}",
                            changes=[{
                                'target_id': card.id,
                                'target_model': 'idcard',
                                'field_name': canonical_field,
                                'change_type': 'field_edit',
                                'before_value': orig_field_val,
                                'after_value': final_val,
                            }],
                        )
                except Exception as audit_err:
                    logger.debug("update_single_field audit log error: %s", audit_err)

                return ServiceResult(
                    success=True,
                    message='Field updated successfully!',
                    data={
                        'field': canonical_field,
                        'value': field_data.get(canonical_field, ''),
                        'is_path_field': is_path_field,
                        'photo_field_name': canonical_field if is_path_field else None,
                        'photo_field_value': field_data.get(canonical_field, '') if is_path_field else None,
                    }
                )


        except IDCard.DoesNotExist:
            return ServiceResult(success=False, message='Card not found')
        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def delete_card(cls, card_id: int) -> ServiceResult:
        """Delete an ID Card"""
        try:
            card = get_object_or_404(IDCard.objects.select_related('table__organisation'), id=card_id)
            table = card.table
            card.delete()
            cls._bump_table_cache_versions(table)

            return ServiceResult(
                success=True,
                message='ID Card deleted successfully!'
            )
        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def change_status(cls, card_id: int, new_status: str, user=None, request=None) -> ServiceResult:
        """
        Change an ID Card's status — delegates to WorkflowService.transition().

        Kept as a thin wrapper so existing callers don't break.
        Permission & activity logging are handled by WorkflowService when
        user/request are supplied.
        """
        try:
            from tables.services_workflow import WorkflowService

            card = get_object_or_404(IDCard, id=card_id)
            return WorkflowService.transition(
                card, new_status, user=user, request=request,
                skip_permission=(user is None),
            )
        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def upload_photo(cls, card, file, user) -> ServiceResult:
        """
        Uploads a photo file for a card. Resolves the primary/preferred image field
        of the card's table, processes the uploaded file via ImageService,
        saves the path to the card's field_data, sets the legacy card.photo field,
        and bumps cache versions.
        """
        from mediafiles.services import ImageService, ThumbnailService
        from django.db import transaction

        try:
            with transaction.atomic():
                card = IDCard.objects.select_for_update().get(id=card.id)
                table = card.table
                client = getattr(table, 'organisation', None) or getattr(getattr(table, 'group', None), 'client', None)
                
                # Identify image fields
                image_field_names = cls.get_image_field_names(table.fields or [])
                
                # Determine primary/preferred field name
                preferred_field_name = None
                for field_name in image_field_names:
                    field_name_lower = str(field_name or '').lower()
                    if field_name_lower in ('photo', 'student_photo', 'student photo', 'image'):
                        preferred_field_name = field_name
                        break
                
                if not preferred_field_name:
                    for field_name in image_field_names:
                        field_name_lower = str(field_name or '').lower()
                        if 'photo' in field_name_lower or 'image' in field_name_lower:
                            preferred_field_name = field_name
                            break
                            
                if not preferred_field_name and image_field_names:
                    preferred_field_name = image_field_names[0]
                    
                if not preferred_field_name:
                    preferred_field_name = 'PHOTO'
                
                # Get existing value
                field_data = card.field_data or {}
                existing_value = field_data.get(preferred_field_name, '')
                
                # Process the image field
                media_result = ImageService.process_image_field(
                    field_name=preferred_field_name,
                    new_value=None,
                    existing_value=existing_value,
                    client=client,
                    card=card,
                    uploaded_file=file,
                    batch_counter=1,
                    uploaded_by=user,
                )
                
                if not media_result.success:
                    return ServiceResult(success=False, message=media_result.message or 'Photo processing failed')
                
                final_value = (media_result.data or {}).get('final_value', existing_value)
                field_data[preferred_field_name] = final_value
                card.field_data = field_data
                card.modified_by = getattr(user, 'username', '') or card.modified_by
                
                if final_value:
                    card.photo = final_value
                    ThumbnailService.ensure_thumbnail_exists(final_value)
                    
                card.save(update_fields=['field_data', 'modified_by', 'photo'])
                
                # Bump cache versions
                cls._bump_table_cache_versions(table)
                
            return ServiceResult(success=True, message='Photo uploaded successfully', data={'photo_url': final_value})
        except Exception as e:
            return ServiceResult(success=False, message=str(e))

