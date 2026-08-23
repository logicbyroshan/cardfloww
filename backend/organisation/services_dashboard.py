"""
Client Dashboard Service — aggregated statistics for the client dashboard.
"""
import logging
from collections import defaultdict

from django.core.cache import cache
from django.utils.timezone import localtime
from django.db.models import Count, Q

from core.services.activity_service import ActivityService
from core.services.cache_version_service import CacheVersionService
from core.services.session_revalidation import get_user_revalidation_marker
from organisation.models import Organisation
from assistants.models import Assistant
from tables.models import Table, IDCard
from reprint.models import ReprintRequest
from core.services.base import BaseService, ServiceResult
from core.services.permission_service import PermissionService

from .services_access import OrganisationAccessService
from .services_card import OrganisationCardService

logger = logging.getLogger(__name__)


class OrganisationDashboardService(BaseService):
    """
    Service for client dashboard data.
    """

    DASHBOARD_COUNTS_CACHE_TTL = 20
    STAFF_SCOPED_TABLE_COUNTS_CACHE_TTL = 20
    GROUP_COUNTS_CACHE_TTL = 20
    STAFF_COUNT_CACHE_TTL = 60
    


    @staticmethod
    def _unexpected_error_result(action: str, exc: Exception) -> ServiceResult:
        logger.exception('OrganisationDashboardService.%s failed: %s', action, exc)
        return ServiceResult(success=False, message='An unexpected error occurred. Please try again.')

    @staticmethod
    def _to_dashboard_photo_url(raw_path: str) -> str:
        value = str(raw_path or '').strip()
        if not value:
            return ''

        value = value.replace('\\', '/')
        while '//' in value:
            value = value.replace('//', '/')

        lower = value.lower()
        if lower.startswith('http://') or lower.startswith('https://'):
            return value

        mediafiles_marker = '/mediafiles/'
        media_marker = '/media/'

        mediafiles_idx = lower.find(mediafiles_marker)
        if mediafiles_idx >= 0:
            return '/media/mediafiles/' + value[mediafiles_idx + len(mediafiles_marker):].lstrip('/')

        media_idx = lower.find(media_marker)
        if media_idx >= 0:
            remainder = value[media_idx + len(media_marker):].lstrip('/')
            if remainder.lower().startswith('mediafiles/'):
                return '/media/' + remainder
            return '/media/' + remainder

        if lower.startswith('/mediafiles/'):
            return '/media/' + value.lstrip('/')
        if lower.startswith('mediafiles/'):
            return '/media/' + value.lstrip('/')
        if lower.startswith('media/'):
            return '/' + value

        return '/media/' + value.lstrip('/')

    @classmethod
    def _get_accessible_tables_qs(cls, user, client):
        tables = Table.objects.filter(organisation=client, is_active=True)
        return OrganisationAccessService.get_scoped_tables_qs(user, client, tables)

    @staticmethod
    def _status_template():
        return {
            'pending': 0,
            'verified': 0,
            'pool': 0,
            'approved': 0,
            'download': 0,
        }

    @staticmethod
    def _scope_marker(user) -> str:
        return str(get_user_revalidation_marker(getattr(user, 'pk', None)) or '')

    @classmethod
    def _client_card_counts_version(cls, client_id: int) -> int:
        return CacheVersionService.get('client_dash_counts', f'client:{client_id}')

    @classmethod
    def _client_staff_version(cls, client_id: int) -> int:
        return CacheVersionService.get('client_staff', f'client:{client_id}')

    @classmethod
    def _dashboard_counts_cache_key(cls, user, client_id: int, marker: str, counts_version: int) -> str:
        return f'client:dash:counts:v3:{user.pk}:{client_id}:{counts_version}:{marker}'

    @classmethod
    def _dashboard_staff_table_counts_cache_key(cls, user, table_id: int, marker: str, counts_version: int) -> str:
        return f'client:dash:staff_table_counts:v3:{user.pk}:{table_id}:{counts_version}:{marker}'

    @classmethod
    def _groups_counts_cache_key(cls, user, client_id: int, marker: str, counts_version: int) -> str:
        return f'client:dash:groups_counts:v3:{user.pk}:{client_id}:{counts_version}:{marker}'

    @classmethod
    def _group_staff_table_counts_cache_key(cls, user, table_id: int, marker: str, counts_version: int) -> str:
        return f'client:dash:group_staff_table_counts:v3:{user.pk}:{table_id}:{counts_version}:{marker}'

    @classmethod
    def _staff_count_cache_key(cls, client_id: int, staff_version: int) -> str:
        return f'client:dash:staff_count:v2:{client_id}:{staff_version}'

    _staff_assignment_marker = _scope_marker
    _group_counts_cache_key = _groups_counts_cache_key

    @classmethod
    def _accumulate_status_rows(cls, counts: dict, rows):
        for row in rows:
            status = row.get('status')
            if status in counts:
                counts[status] += int(row.get('count', 0) or 0)

    @classmethod
    def _accumulate_status_map(cls, counts: dict, status_map: dict):
        for status, count in (status_map or {}).items():
            if status in counts:
                counts[status] += int(count or 0)

    @classmethod
    def _build_reprint_history_item(cls, request_obj) -> dict:
        card = getattr(request_obj, 'card', None)
        table = getattr(request_obj, 'table', None)
        field_data = card.field_data if card and isinstance(getattr(card, 'field_data', None), dict) else {}

        photo_url = ''
        try:
            from mediafiles.services.image_service import ImageService

            table_fields = getattr(table, 'fields', None) if table else None
            field_names = []
            if isinstance(table_fields, list):
                for field in table_fields:
                    if isinstance(field, dict):
                        field_name = str(field.get('name', '') or '').strip()
                        if field_name:
                            field_names.append(field_name)
                    elif isinstance(field, str) and field.strip():
                        field_names.append(field.strip())

            candidate_names = []
            for field_name in field_names:
                lowered = field_name.lower()
                if 'photo' in lowered or 'image' in lowered or 'avatar' in lowered:
                    candidate_names.append(field_name)
            if not candidate_names:
                candidate_names = field_names

            for field_name in candidate_names:
                try:
                    path = ImageService.get_image_path_for_export(card, field_name)
                except Exception:
                    path = None
                if path:
                    photo_url = cls._to_dashboard_photo_url(path)
                    break
        except Exception:
            logger.debug('Reprint photo resolution failed for request_id=%s', getattr(request_obj, 'id', None), exc_info=True)

        if not photo_url and card:
            try:
                from mediafiles.utils import get_card_photo_url

                photo_url = cls._to_dashboard_photo_url(get_card_photo_url(card, field_data) or '')
            except Exception:
                photo_url = ''

        card_details_parts = []
        if card and isinstance(getattr(card, 'field_data', None), dict):
            field_data = card.field_data
            
            # Find name
            name_val = None
            class_val = None
            sec_val = None
            
            lower_keys = {k.lower().strip(): k for k in field_data.keys()}
            
            name_candidates = ['name', 'student name', 'student_name', 'candidate name', 'candidate_name', 'name of student', 'name of candidate']
            for cand in name_candidates:
                if cand in lower_keys:
                    name_val = field_data[lower_keys[cand]]
                    break
            if not name_val:
                for k_lower, k_orig in lower_keys.items():
                    if 'name' in k_lower and not any(x in k_lower for x in ['father', 'mother', 'parent', 'photo', 'sig', 'file', 'url', 'husband', 'guardian']):
                        name_val = field_data[k_orig]
                        break
                        
            class_candidates = ['class', 'grade', 'standard', 'std']
            for cand in class_candidates:
                if cand in lower_keys:
                    class_val = field_data[lower_keys[cand]]
                    break
            if not class_val:
                for k_lower, k_orig in lower_keys.items():
                    if 'class' in k_lower or 'grade' in k_lower:
                        class_val = field_data[k_orig]
                        break

            sec_candidates = ['sec', 'section']
            for cand in sec_candidates:
                if cand in lower_keys:
                    sec_val = field_data[lower_keys[cand]]
                    break
            if not sec_val:
                for k_lower, k_orig in lower_keys.items():
                    if 'sec' in k_lower or 'section' in k_lower:
                        sec_val = field_data[k_orig]
                        break

            if name_val:
                card_details_parts.append(f"Name: {str(name_val).strip()}")
            if class_val:
                card_details_parts.append(f"Class: {str(class_val).strip()}")
            if sec_val:
                card_details_parts.append(f"Sec: {str(sec_val).strip()}")

            if not card_details_parts:
                count = 0
                for k, v in field_data.items():
                    k_lower = k.lower()
                    if not v or any(x in k_lower for x in ['photo', 'image', 'avatar', 'sig', 'file', 'url']):
                        continue
                    if len(str(v)) < 50:
                        card_details_parts.append(f"{k}: {str(v).strip()}")
                        count += 1
                        if count >= 3:
                            break

        details_str = ""
        table_name = str(table.name).strip() if table and getattr(table, 'name', '') else ""
        
        if table_name:
            details_str = table_name
            if card_details_parts:
                details_str += f" ({', '.join(card_details_parts)})"
        else:
            if card_details_parts:
                details_str = ", ".join(card_details_parts)
            else:
                details_str = f"Card #{card.id}" if card else "Reprint request"

        created_at_formatted = None
        if request_obj.created_at:
            created_at_formatted = localtime(request_obj.created_at).strftime('%d-%m-%Y %H:%M')

        return {
            'id': request_obj.id,
            'status': request_obj.status,
            'status_display': request_obj.get_status_display(),
            'card_id': getattr(card, 'id', None),
            'table_id': getattr(table, 'id', None),
            'table_name': table_name,
            'details': details_str,
            'photo_url': photo_url,
            'created_at': created_at_formatted,
            'updated_at': request_obj.updated_at.isoformat() if request_obj.updated_at else None,
        }

    @classmethod
    def get_reprint_history(cls, user) -> ServiceResult:
        """Return the client's reprint request history."""
        try:
            client = OrganisationAccessService.get_organisation_for_user(user)
            if not client:
                return ServiceResult(success=False, message='Client profile not found')

            reprint_qs = (
                ReprintRequest.objects
                .select_related('card', 'table')
                .filter(table__organisation_id=client.id)
                .order_by('-created_at', '-id')
            )

            items = [cls._build_reprint_history_item(req) for req in reprint_qs]
            stats = reprint_qs.aggregate(
                reprint_requested=Count('id', filter=Q(status='requested')),
                reprint_confirmed=Count('id', filter=Q(status='confirmed')),
                reprint_total=Count('id'),
            )

            return ServiceResult(
                success=True,
                data={
                    'items': items,
                    'total_count': stats['reprint_total'] or 0,
                    'reprint_requested': stats['reprint_requested'] or 0,
                    'reprint_confirmed': stats['reprint_confirmed'] or 0,
                    'reprint_total': stats['reprint_total'] or 0,
                },
            )
        except Exception as e:
            return cls._unexpected_error_result('get_reprint_history', e)

    @classmethod
    def get_reprint_stats(cls, user) -> ServiceResult:
        """Return the client's reprint counts for dashboard summaries."""
        try:
            client = OrganisationAccessService.get_organisation_for_user(user)
            if not client:
                return ServiceResult(success=False, message='Client profile not found')

            counts = (
                ReprintRequest.objects
                .filter(table__organisation_id=client.id)
                .aggregate(
                    reprint_requested=Count('id', filter=Q(status='requested')),
                    reprint_confirmed=Count('id', filter=Q(status='confirmed')),
                    reprint_total=Count('id'),
                )
            )
            return ServiceResult(
                success=True,
                data={
                    'reprint_requested': counts['reprint_requested'] or 0,
                    'reprint_confirmed': counts['reprint_confirmed'] or 0,
                    'reprint_total': counts['reprint_total'] or 0,
                },
            )
        except Exception as e:
            return cls._unexpected_error_result('get_reprint_stats', e)

    @classmethod
    def get_dashboard_data(cls, user, client=None) -> ServiceResult:
        """
        Get dashboard summary data for a client user.
        
        Returns counts of cards by status for all tables belonging to the client.
        Accepts optional *client* override so admin roles (whose
        ``get_client_for_user`` returns ``None``) can view a specific client.
        """
        try:
            if not client:
                client = OrganisationAccessService.get_organisation_for_user(user)
            if not client:
                user_role = getattr(user, 'role', 'unknown')
                client_profile = getattr(user, 'client_profile', None)
                staff_profile = getattr(user, 'staff_profile', None)
                logger.warning(
                    'OrganisationDashboardService.get_dashboard_data: Organisation not found for user_id=%s role=%s has_client_profile=%s has_staff_profile=%s',
                    user.pk, user_role, client_profile is not None, staff_profile is not None
                )
                return ServiceResult(
                    success=False, 
                    message='Client profile not found'
                )

            tables = list(
                cls._get_accessible_tables_qs(user, client)
                .only('id', 'organisation_id', 'fields')
            )
            table_ids = [table.id for table in tables]
            counts = cls._status_template()

            if table_ids:
                if PermissionService.is_client_staff(user):
                    staff = getattr(user, 'staff_profile', None)

                    for table in tables:
                        scoped_qs = OrganisationCardService._apply_client_staff_row_scope(
                            user,
                            table,
                            IDCard.objects.filter(table_id=table.id),
                        )
                        table_status_map = {
                            row['status']: int(row.get('count', 0) or 0)
                            for row in scoped_qs.values('status').annotate(count=Count('id'))
                            if row.get('status')
                        }
                        cls._accumulate_status_map(counts, table_status_map)
                else:
                    status_rows = IDCard.objects.filter(
                        table_id__in=table_ids
                    ).values('status').annotate(count=Count('id'))
                    cls._accumulate_status_rows(counts, status_rows)

            table_count = len(table_ids)
            group_count = len({getattr(table, 'group_id', getattr(getattr(table, 'group', None), 'id', table.id)) for table in tables})
            
            # Total cards - exclude 'pool' status
            total_cards = counts['pending'] + counts['verified'] + counts['approved'] + counts['download']

            # Get staff count (client_staff under this client)
            staff_count = Assistant.objects.filter(
                organisation=client
            ).count()

            # Get recent assistants (for dashboard Recent Assistants panel, Client Admin only)
            recent_staff = []
            if not PermissionService.is_client_staff(user):
                try:
                    recent_staff_qs = (
                        Assistant.objects.filter(organisation=client)
                        .select_related('user')
                        .prefetch_related('assigned_groups')
                        .order_by('-id')[:5]
                    )
                    active_tables = list(Table.objects.filter(organisation=client, is_active=True)[:10])
                    
                    for s in recent_staff_qs:
                        s.user.assistant_profile = s
                        pending_cnt = 0
                        verified_cnt = 0
                        pool_cnt = 0
                        
                        for table in active_tables:
                            cards_qs = IDCard.objects.filter(table_id=table.id)
                            pending_cnt += OrganisationCardService._apply_client_staff_row_scope(
                                s.user, table, cards_qs.filter(status='pending'), ignore_pool_bypass=True
                            ).count()
                            verified_cnt += OrganisationCardService._apply_client_staff_row_scope(
                                s.user, table, cards_qs.filter(status='verified'), ignore_pool_bypass=True
                            ).count()
                            pool_cnt += OrganisationCardService._apply_client_staff_row_scope(
                                s.user, table, cards_qs.filter(status='pool'), ignore_pool_bypass=True
                            ).count()
                        
                        classes = set()
                        sections = set()
                        if isinstance(s.allowed_classes, list):
                            for c in s.allowed_classes:
                                if c: classes.add(str(c))
                        if isinstance(s.allowed_sections, list):
                            for sec in s.allowed_sections:
                                if sec: sections.add(str(sec))
                        if isinstance(s.assignment_scopes, list):
                            for scope in s.assignment_scopes:
                                if isinstance(scope, dict):
                                    for c in scope.get('classes') or []:
                                        if c: classes.add(str(c))
                                    for sec in scope.get('sections') or []:
                                        if sec: sections.add(str(sec))
                        
                        has_group_assign = bool(s.assigned_groups.all())
                        has_table_assign = bool(s.assigned_table_ids)
                        has_scope_assign = False
                        if isinstance(s.assignment_scopes, list):
                            for scope in s.assignment_scopes:
                                if isinstance(scope, dict) and (scope.get('classes') or scope.get('sections') or scope.get('scope_id')):
                                    has_scope_assign = True
                                    break
                        has_legacy_assign = bool(s.allowed_classes) or bool(s.allowed_sections)
                        has_assignments = has_group_assign or has_table_assign or has_scope_assign or has_legacy_assign
     
                        has_list_perms = any([
                            getattr(s, 'perm_idcard_client_list', getattr(s, 'perm_organisation_list', False)),
                            getattr(s, 'perm_idcard_pending_list', False),
                            getattr(s, 'perm_idcard_verified_list', False),
                            getattr(s, 'perm_idcard_pool_list', False),
                            getattr(s, 'perm_idcard_approved_list', False),
                            getattr(s, 'perm_idcard_download_list', False),
                            getattr(s, 'perm_idcard_reprint_list', False),
                            getattr(s, 'perm_reprint_request_list', False),
                            getattr(s, 'perm_confirmed_list', False),
                        ])
     
                        recent_staff.append({
                            'id': s.id,
                            'name': s.user.get_full_name() or s.user.username,
                            'email': s.user.email or '',
                            'is_active': s.user.is_active,
                            'pending': pending_cnt,
                            'verified': verified_cnt,
                            'pool': pool_cnt,
                            'classes': sorted(list(classes)),
                            'sections': sorted(list(sections)),
                            'has_assignments': has_assignments,
                            'has_list_perms': has_list_perms,
                        })
                except Exception as e:
                    logger.exception('Failed to build recent assistants list in client dashboard: %s', e)
                    recent_staff = []

            # Use centralized role-aware activity feed so legacy per-card logs are merged.
            # Keep dashboard counts resilient if the activity feed hits a malformed row.
            try:
                recent_activity = ActivityService.get_recent(limit=6, hours=None, user=user)
            except Exception as activity_exc:
                logger.warning(
                    'OrganisationDashboardService.get_dashboard_data: recent activity load failed for user_id=%s role=%s: %s',
                    user.pk, getattr(user, 'role', 'unknown'), activity_exc
                )
                recent_activity = []

            return ServiceResult(
                success=True,
                data={
                    'organisation': {
                        'id': client.id,
                        'name': client.name,
                        'city': client.city,
                        'state': client.state,
                    },
                    'counts': {
                        'tables': table_count,
                        'groups': group_count,
                        'staff': staff_count,
                        'cards_total': total_cards,
                        'cards_pending': counts['pending'],
                        'cards_verified': counts['verified'],
                        'cards_approved': counts['approved'],
                        'cards_download': counts['download'],
                        'pending': counts['pending'],
                        'verified': counts['verified'],
                        'approved': counts['approved'],
                        'download': counts['download'],
                        'pool': counts['pool'],
                        'total_cards': total_cards,
                    },
                    'group_count': group_count,
                    'table_count': table_count,
                    'staff_count': staff_count,
                    'total_cards': total_cards,
                    'recent_staff': recent_staff,
                    'recent_activity': recent_activity,
                }
            )
            
        except Exception as e:
            logger.exception("OrganisationDashboardService.get_dashboard_data error: %s", e)
            return ServiceResult(success=False, message=str(e))
    
    @classmethod
    def get_groups_with_counts(cls, user) -> ServiceResult:
        """Get tables with status counts."""
        try:
            client = OrganisationAccessService.get_organisation_for_user(user)
            if client is None:
                return ServiceResult(success=False, message='Organisation not found')

            marker = cls._staff_assignment_marker(user)
            counts_version = CacheVersionService.get_version(
                'client_dash_counts',
                f'client:{client.id}',
            )
            cache_key = cls._group_counts_cache_key(user, client.id, marker, counts_version)
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return ServiceResult(success=True, data={'groups': cached_data})

            tables_qs = Table.objects.filter(organisation=client, is_active=True)
            tables_qs = OrganisationAccessService.get_scoped_tables_qs(user, client, base_qs=tables_qs)
            accessible_tables = list(
                tables_qs.only('id', 'name', 'is_active', 'fields')
            )
            if not accessible_tables:
                cache.set(cache_key, [], cls.GROUP_COUNTS_CACHE_TTL)
                return ServiceResult(success=True, data={'groups': []})

            table_ids = [table.id for table in accessible_tables]
            tables = Table.objects.filter(
                organisation=client,
                id__in=table_ids,
            ).only('id', 'name', 'is_active', 'created_at')

            table_card_counts = {}
            group_counts_map = defaultdict(dict)

            if PermissionService.is_client_staff(user):
                for table in accessible_tables:
                    table_cache_key = cls._group_staff_table_counts_cache_key(
                        user,
                        table.id,
                        marker,
                        counts_version,
                    )
                    table_status_map = cache.get(table_cache_key)
                    if table_status_map is None:
                        scoped_qs = OrganisationCardService._apply_client_staff_row_scope(
                            user,
                            table,
                            IDCard.objects.filter(table_id=table.id),
                        )
                        table_status_map = {
                            row['status']: int(row.get('count', 0) or 0)
                            for row in scoped_qs.values('status').annotate(count=Count('id'))
                            if row.get('status')
                        }
                        cache.set(
                            table_cache_key,
                            table_status_map,
                            cls.STAFF_SCOPED_TABLE_COUNTS_CACHE_TTL,
                        )

                    table_card_counts[table.id] = sum(int(v or 0) for v in table_status_map.values())
                    group_bucket = group_counts_map[table.id]
                    for status, count in table_status_map.items():
                        group_bucket[status] = group_bucket.get(status, 0) + int(count or 0)
            else:
                base_table_counts = IDCard.objects.filter(
                    table_id__in=table_ids
                ).values('table_id').annotate(count=Count('id'))
                table_card_counts = {
                    row['table_id']: int(row.get('count', 0) or 0)
                    for row in base_table_counts
                }

                base_group_counts = IDCard.objects.filter(
                    table_id__in=table_ids
                ).values('table_id', 'status').annotate(count=Count('id'))
                for row in base_group_counts:
                    gid = row['table_id']
                    status = row.get('status')
                    if status:
                        group_counts_map[gid][status] = int(row.get('count', 0) or 0)

            tables_by_group = defaultdict(list)
            for table in accessible_tables:
                tables_by_group[table.id].append(table)

            groups_data = []
            for group in tables:
                group_tables = tables_by_group.get(group.id, [])
                counts = group_counts_map.get(group.id, {})
                total = sum(int(v or 0) for v in counts.values())

                tables_data = [{
                    'id': table.id,
                    'name': table.name,
                    'is_active': table.is_active,
                    'card_count': table_card_counts.get(table.id, 0),
                } for table in group_tables]

                groups_data.append({
                    'id': group.id,
                    'name': group.name,
                    'is_active': group.is_active,
                    'created_at': group.created_at.strftime('%Y-%m-%dT%H:%M:%S') if group.created_at else None,
                    'table_count': len(tables_data),
                    'card_count': total,
                    'total_cards': total,
                    'pending_count': counts.get('pending', 0),
                    'pending': counts.get('pending', 0),
                    'verified': counts.get('verified', 0),
                    'pool': counts.get('pool', 0),
                    'approved': counts.get('approved', 0),
                    'download': counts.get('download', 0),
                    'tables': tables_data,
                })

            cache.set(cache_key, groups_data, cls.GROUP_COUNTS_CACHE_TTL)
            return ServiceResult(success=True, data={'groups': groups_data})
            
        except Exception as e:
            return cls._unexpected_error_result('get_groups_with_counts', e)
