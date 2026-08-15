"""
IDCard Table Service — table schema CRUD and default-group provisioning.

Part of the IDCardService split. Handles:
- Table serialization, CRUD, toggle, list
- Default Table creation
"""
import logging
from typing import Dict, Any

from django.shortcuts import get_object_or_404
from django.utils.timezone import localtime

from tables.models import Table
from .base import BaseService, ServiceResult

logger = logging.getLogger(__name__)


class IDCardTableService(BaseService):
    """Service for ID Card Table (schema) operations."""

    MAX_FIELDS_PER_TABLE = 30
    VALID_FIELD_TYPES = [
        'text', 'number', 'date', 'email', 'image', 'textarea', 'class', 'section',
        'photo', 'rel_photo', 'mother_photo', 'father_photo', 'barcode', 'qr_code', 'signature',
        'select', 'class_section',
    ]
    LEGACY_REL_PHOTO_ALIASES = {'mother_photo', 'father_photo'}

    VALID_TABLE_TYPES = {'school_student', 'college_student', 'staff', 'custom'}

    @classmethod
    def _normalize_field_type(cls, field_type: str) -> str:
        """Map legacy relation-photo aliases to canonical rel_photo."""
        normalized = str(field_type or 'text').strip().lower()
        if normalized in cls.LEGACY_REL_PHOTO_ALIASES:
            return 'rel_photo'
        return normalized

    @classmethod
    def _infer_table_type(cls, table_name: str, org_name: str = '', org_type: str = '') -> str:
        """Smart-detect table type from table name, organisation name, and org_type.

        Rules (case-insensitive):
        1. Staff / Teacher / Employee / Faculty / HR / Driver -> 'staff'
        2. College keywords (college, university, degree, btech, mtech, bca, mca, semester, sem, branch, dept) -> 'college_student'
        3. School keywords (school, class, std, standard, grade, section, sec) -> 'school_student'
        4. Student / Pupil / List / Data:
           - if org_type == 'college' or org_name contains college keywords -> 'college_student'
           - if org_type == 'company' -> 'staff'
           - default -> 'school_student'
        5. Fallback -> 'custom'
        """
        import re
        name_l = (table_name or '').lower().strip()
        org_l  = (org_name or '').lower().strip()

        staff_kw   = r'\b(staff|teacher|teachers|employee|employees|emp|faculty|personnel|hr|driver|workers|management)\b'
        college_kw = r'\b(college|university|institute|polytechnic|degree|btech|mtech|bca|mca|mba|bsc|msc|ba|ma|bcom|mcom|semester|sem|branch|dept|department)\b'
        school_kw  = r'\b(school|vidyalaya|academy|convent|class|std|standard|grade|section|sec)\b'
        student_kw = r'\b(student|students|pupil|scholars|list|data|records|info|all)\b'

        if re.search(staff_kw, name_l):
            return 'staff'

        if re.search(college_kw, name_l):
            return 'college_student'

        if re.search(school_kw, name_l):
            return 'school_student'

        if re.search(student_kw, name_l):
            if org_type == 'college' or re.search(college_kw, org_l):
                return 'college_student'
            if org_type == 'company':
                return 'staff'
            return 'school_student'

        return 'custom'

    # ==================== Serialization ====================

    @classmethod
    def serialize_table(cls, table: Table) -> Dict[str, Any]:
        """Serialize Table to dict"""
        normalized_fields = []
        for field in (table.fields or []):
            if not isinstance(field, dict):
                continue
            normalized = dict(field)
            normalized['type'] = cls._normalize_field_type(field.get('type', 'text'))
            normalized_fields.append(normalized)

        from tables.models import IDCard
        from django.db.models import Count, Q

        counts = IDCard.objects.filter(table=table).aggregate(
            pending_count=Count('id', filter=Q(status='pending')),
            verified_count=Count('id', filter=Q(status='verified')),
            approved_count=Count('id', filter=Q(status='approved')),
            download_count=Count('id', filter=Q(status='download')),
            pool_count=Count('id', filter=Q(status='pool')),
            reprint_count=Count('id', filter=Q(status='reprint')),
        )

        # Count reprint requests
        rp_req_cnt = 0
        rp_conf_cnt = 0
        try:
            from reprintcard.models import ReprintRequest
            req_counts = ReprintRequest.objects.filter(table=table).aggregate(
                req_c=Count('id', filter=Q(status='requested')),
                conf_c=Count('id', filter=Q(status='confirmed')),
            )
            rp_req_cnt = req_counts['req_c'] or 0
            rp_conf_cnt = req_counts['conf_c'] or 0
        except Exception:
            pass

        p_cnt = counts['pending_count'] or 0
        v_cnt = counts['verified_count'] or 0
        a_cnt = counts['approved_count'] or 0
        d_cnt = counts['download_count'] or 0
        l_cnt = counts['pool_count'] or 0
        r_cnt = counts['reprint_count'] or 0

        client_name = ''
        if hasattr(table, 'group') and table.group and hasattr(table.group, 'client') and table.group.client:
            client_name = table.group.client.name

        return {
            'id': table.id,
            'name': table.name,
            'client_name': client_name,
            'table_type': getattr(table, 'table_type', 'custom') or 'custom',
            'table_type_display': dict([
                ('school_student', 'School Student'),
                ('college_student', 'College Student'),
                ('staff', 'Staff'),
                ('custom', 'Custom'),
            ]).get(getattr(table, 'table_type', 'custom') or 'custom', 'Custom'),
            'fields': normalized_fields,
            'field_count': len(normalized_fields),
            'pending_count': p_cnt,
            'verified_count': v_cnt,
            'approved_count': a_cnt,
            'download_count': d_cnt,
            'pool_count': l_cnt,
            'reprint_count': r_cnt,
            'reprint_request_count': rp_req_cnt,
            'reprint_confirmed_count': rp_conf_cnt,
            'pending': p_cnt,
            'verified': v_cnt,
            'approved': a_cnt,
            'download': d_cnt,
            'downloaded': d_cnt,
            'printed': d_cnt,
            'request': rp_req_cnt,
            'requested': rp_req_cnt,
            'pool': l_cnt,
            'deleted': l_cnt,
            'reprint': r_cnt,
            'confirmed': rp_conf_cnt,
            'total_count': p_cnt + v_cnt + a_cnt + d_cnt + l_cnt + r_cnt,
            'is_active': table.is_active,
            'created_at': localtime(table.created_at).strftime('%d-%b-%Y %H:%M'),
            'updated_at': localtime(table.updated_at).strftime('%d-%b-%Y %H:%M'),
        }

    # ==================== CRUD ====================

    @classmethod
    def create_table(cls, group_id: int, data: Dict[str, Any]) -> ServiceResult:
        """Create a new ID Card Table"""
        try:
            group = get_object_or_404(Table, id=group_id)

            name = str(data.get('name') or data.get('table_name') or '').strip().upper()
            if not name:
                return ServiceResult(success=False, message='Table name is required!')

            fields = data.get('fields', [])
            if len(fields) > cls.MAX_FIELDS_PER_TABLE:
                return ServiceResult(
                    success=False,
                    message=f'Maximum {cls.MAX_FIELDS_PER_TABLE} fields allowed!'
                )

            # Validate and normalize fields
            validated_fields = []
            for idx, field in enumerate(fields):
                field_name = field.get('name', '').strip().upper()
                field_type = cls._normalize_field_type(field.get('type', 'text'))
                field_mandatory = bool(field.get('mandatory', False))
                field_show_path = bool(field.get('show_path', False))

                if not field_name:
                    return ServiceResult(
                        success=False,
                        message=f'Field {idx+1} name is required!'
                    )

                if field_type not in cls.VALID_FIELD_TYPES:
                    field_type = 'text'

                validated_fields.append({
                    'name': field_name,
                    'type': field_type,
                    'order': idx,
                    'mandatory': field_mandatory,
                    'show_path': field_show_path
                })

            # Determine organisation & table type: use explicit value if valid, else auto-detect
            org = getattr(group, 'organisation', None) or (group if hasattr(group, 'org_type') else None)
            org_name = getattr(org, 'name', '') if org else ''
            org_type = getattr(org, 'org_type', '') if org else ''
            raw_type = str(data.get('table_type') or '').strip().lower()
            if raw_type in cls.VALID_TABLE_TYPES:
                table_type = raw_type
            else:
                table_type = cls._infer_table_type(name, org_name, org_type)

            table = Table.objects.create(
                organisation=org,
                name=name,
                table_type=table_type,
                fields=validated_fields,
                is_active=True
            )

            return ServiceResult(
                success=True,
                message='Table created successfully!',
                data={'table': cls.serialize_table(table)}
            )

        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def get_table(cls, table_id: int) -> ServiceResult:
        """Get a single ID Card Table"""
        try:
            table = get_object_or_404(Table, id=table_id)
            return ServiceResult(
                success=True,
                data={'table': cls.serialize_table(table)}
            )
        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def update_table(cls, table_id: int, data: Dict[str, Any]) -> ServiceResult:
        """Update an ID Card Table"""
        try:
            table = get_object_or_404(Table, id=table_id)

            name = data.get('name', '').strip().upper()
            if not name:
                return ServiceResult(success=False, message='Table name is required!')

            fields = data.get('fields', [])
            if len(fields) > cls.MAX_FIELDS_PER_TABLE:
                return ServiceResult(
                    success=False,
                    message=f'Maximum {cls.MAX_FIELDS_PER_TABLE} fields allowed!'
                )

            # Validate fields
            validated_fields = []
            for idx, field in enumerate(fields):
                field_name = field.get('name', '').strip().upper()
                field_type = cls._normalize_field_type(field.get('type', 'text'))
                field_mandatory = bool(field.get('mandatory', False))
                field_show_path = bool(field.get('show_path', False))

                if not field_name:
                    return ServiceResult(
                        success=False,
                        message=f'Field {idx+1} name is required!'
                    )

                if field_type not in cls.VALID_FIELD_TYPES:
                    field_type = 'text'

                validated_fields.append({
                    'name': field_name,
                    'type': field_type,
                    'order': idx,
                    'mandatory': field_mandatory,
                    'show_path': field_show_path
                })

            # Determine / update table type
            org_name = getattr(table.group.client, 'name', '') if table.group.client_id else ''
            org_type = getattr(table.group.client, 'org_type', '') if table.group.client_id else ''
            raw_type = str(data.get('table_type') or '').strip().lower()
            if raw_type in cls.VALID_TABLE_TYPES:
                table_type = raw_type
            else:
                table_type = cls._infer_table_type(name, org_name, org_type)

            table.name = name
            table.table_type = table_type
            table.fields = validated_fields
            table.save()

            return ServiceResult(
                success=True,
                message='Table updated successfully!',
                data={'table': cls.serialize_table(table)}
            )

        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def delete_table(cls, table_id: int) -> ServiceResult:
        """Delete an ID Card Table"""
        try:
            table = get_object_or_404(Table, id=table_id)
            table_name = table.name
            table.delete()

            return ServiceResult(
                success=True,
                message=f'Table "{table_name}" deleted successfully!'
            )
        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def toggle_table_status(cls, table_id: int) -> ServiceResult:
        """Toggle ID Card Table active/inactive status (atomic to prevent lost toggles)"""
        try:
            from django.db import transaction
            with transaction.atomic():
                table = Table.objects.select_for_update().get(id=table_id)
                table.is_active = not table.is_active
                status = 'active' if table.is_active else 'inactive'
                status_display = 'Active' if table.is_active else 'Inactive'
                table.save(update_fields=['is_active', 'updated_at'])

            return ServiceResult(
                success=True,
                message=f'Table status changed to {status_display}!',
                data={'status': status, 'status_display': status_display}
            )
        except Table.DoesNotExist:
            return ServiceResult(success=False, message='Table not found')
        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def list_tables(cls, group_id: int) -> ServiceResult:
        """List all ID Card Tables for a group"""
        try:
            group = get_object_or_404(Table, id=group_id)
            tables = Table.objects.filter(group=group)

            return ServiceResult(
                success=True,
                data={'tables': [cls.serialize_table(t) for t in tables]}
            )
        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def ensure_default_group(cls, client) -> 'Table':
        """Return the first Table for an organisation, creating one if none exists."""
        group = Table.objects.filter(organisation=client).first()
        if not group:
            group = Table.objects.create(
                organisation=client,
                name=f"{client.name} - Default Table",
                is_active=True,
            )
        return group
