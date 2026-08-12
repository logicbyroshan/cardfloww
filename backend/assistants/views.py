import json
import logging
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from organisation.models import Organisation
from assistants.models import Assistant
from assistants.services import AssistantService
from tables.models import Table
from core.services.activity_service import ActivityService
from core.services.permission_service import require_super_admin, api_require_super_admin, PermissionService
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from functools import wraps

def api_require_assistant_manager(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Authentication required'}, status=401)
        if not (PermissionService.is_super_admin(request.user) or PermissionService.has(request.user, 'perm_manage_assistant')):
            return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper

logger = logging.getLogger(__name__)


def _normalize_positive_int_ids(values, max_items: int = 500):
    """Normalize mixed payload IDs to unique positive integers with a cap."""
    if not isinstance(values, list):
        return []

    out = []
    seen = set()
    for value in values:
        if isinstance(value, bool):
            continue
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if number <= 0 or number in seen:
            continue
        seen.add(number)
        out.append(number)
        if len(out) >= max_items:
            break
    return out


def _normalize_assignment_scopes(values, max_items: int = 500):
    """Keep assignment scopes as a bounded list of dicts."""
    if not isinstance(values, list):
        return []

    out = []
    for item in values:
        if not isinstance(item, dict):
            continue
        out.append(item)
        if len(out) >= max_items:
            break
    return out


def _normalize_staff_assignment_payload(data):
    """Normalize and cap assignment-related payload fields for stability."""
    if not isinstance(data, dict):
        return data

    if 'assigned_groups' in data:
        data['assigned_groups'] = _normalize_positive_int_ids(data.get('assigned_groups'), max_items=500)

    if 'assignment_scopes' in data:
        data['assignment_scopes'] = _normalize_assignment_scopes(data.get('assignment_scopes'), max_items=500)

    return data


def _client_staff_assignment_snapshot(staff_obj):
    """Return normalized assignment state used for timeline diff logging."""
    if not staff_obj:
        return {
            'client_ids': [],
            'group_ids': [],
            'table_ids': [],
            'classes': [],
            'sections': [],
            'branches': [],
            'scope_count': 0,
        }

    table_ids = []
    for value in (staff_obj.assigned_table_ids or []):
        try:
            num = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if num > 0:
            table_ids.append(num)

    return {
        'client_ids': [int(staff_obj.client_id)] if getattr(staff_obj, 'client_id', None) else [],
        'group_ids': list(staff_obj.assigned_groups.values_list('id', flat=True)),
        'table_ids': table_ids,
        'classes': list(staff_obj.allowed_classes or []),
        'sections': list(staff_obj.allowed_sections or []),
        'branches': list(staff_obj.allowed_branches or []),
        'scope_count': len(staff_obj.assignment_scopes or []),
    }


def _result_error_status(message: str, fallback: int = 400) -> int:
    """Map service error messages to HTTP status without case-sensitive checks."""
    text = str(message or '').strip().lower()
    if 'permission' in text or 'access denied' in text or 'access' in text:
        return 403
    return fallback


@login_required
@require_http_methods(["GET"])
def manage_assistants(request):
    """
    Render the admin-side assistant management page.
    """
    user = request.user
    can_manage = PermissionService.is_super_admin(user) or PermissionService.has(user, 'perm_manage_assistant')
    if not can_manage:
        return HttpResponseForbidden("Access Denied")

    # Heal missing assistant profiles
    from core.models import User as CoreUser
    users_without_profile = CoreUser.objects.filter(role__in=['assistant'], assistant_profile__isnull=True)
    if users_without_profile.exists():
        default_client = Organisation.objects.first()
        for u in users_without_profile:
            Assistant.objects.get_or_create(user=u, defaults={'client': default_client})

    if PermissionService.is_super_admin(user):
        clients = Organisation.objects.all().order_by('name')
        staff_list = Assistant.objects.all().select_related('user', 'client').order_by('-created_at')
    else:
        operator = getattr(user, 'operator_profile', None)
        if operator:
            clients = operator.assigned_organisations.all().order_by('name')
            staff_list = Assistant.objects.filter(client__in=clients).select_related('user', 'client').order_by('-created_at')
        else:
            clients = Organisation.objects.none()
            staff_list = Assistant.objects.none()
    
    context = {
        'active_page': 'manage_assistants',
        'breadcrumb_label': 'Manage Assistant',
        'clients': clients,
        'staff_list': staff_list,
        'is_super_admin': PermissionService.is_super_admin(user),
        'perm_idcard_client_list': True,
        'perm_manage_assistant': True,
        'perm_idcard_pending_list': True,
        'perm_idcard_verified_list': True,
        'perm_idcard_approved_list': True,
        'perm_idcard_download_list': True,
        'perm_idcard_pool_list': True,
        'perm_idcard_bulk_download': True,
        'perm_idcard_add': True,
        'perm_idcard_edit': True,
        'perm_idcard_delete': True,
        'perm_idcard_info': True,
        'perm_idcard_verify': True,
        'perm_idcard_created_at': True,
        'perm_idcard_updated_at': True,
        'perm_idcard_retrieve': True,
        'perm_mobile_app': True,
    }
    return render(request, 'index.html', context)



@api_require_assistant_manager
@require_http_methods(["GET", "POST"])
def api_staff_list_create(request):
    """
    API: List assistants (GET) or Create new assistant (POST) on the admin side.
    """
    if request.method == 'GET':
        # Retrieve optional target client:
        client_id = request.GET.get('client_id')
        target_client = None
        if client_id:
            target_client = Organisation.objects.filter(id=client_id).first()
            if not target_client:
                return JsonResponse({'success': False, 'error': 'Selected client not found'}, status=404)

        result = AssistantService.list_assistants(request.user, target_client=target_client)
        if result.success:
            return JsonResponse({
                'success': True,
                'data': {'staff': result.data.get('staff', [])}
            })

        return JsonResponse({
            'success': False,
            'error': result.message
        }, status=400 if 'Permission' not in result.message else 403)

    # POST - Create new staff
    content_type = request.content_type or ''
    if 'multipart/form-data' in content_type:
        data = request.POST.dict()
        if 'assigned_groups' in data:
            try:
                data['assigned_groups'] = json.loads(data['assigned_groups'])
            except (json.JSONDecodeError, TypeError):
                data['assigned_groups'] = []
        if 'assignment_scopes' in data:
            try:
                data['assignment_scopes'] = json.loads(data['assignment_scopes'])
            except (json.JSONDecodeError, TypeError):
                data['assignment_scopes'] = []
        # Parse boolean strings
        for key in list(data.keys()):
            if data[key] in ('true', 'True'):
                data[key] = True
            elif data[key] in ('false', 'False'):
                data[key] = False
    else:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data'
            }, status=400)

    # Validate that client_id is provided in data
    client_id = data.get('client_id')
    if not client_id:
        return JsonResponse({
            'success': False,
            'error': 'Please select a client to create an assistant.'
        }, status=400)

    target_client = Organisation.objects.filter(id=client_id).first()
    if not target_client:
        return JsonResponse({
            'success': False,
            'error': 'Client not found.'
        }, status=404)

    data = _normalize_staff_assignment_payload(data)
    result = AssistantService.create_assistant(request.user, data, target_client=target_client)
    
    if result.success:
        staff_id = (result.data or {}).get('staff_id')
        if staff_id:
            try:
                staff = (
                    Assistant.objects
                    .select_related('user')
                    .prefetch_related('assigned_groups')
                    .filter(id=staff_id)
                    .first()
                )
                if staff:
                    ActivityService.log_staff_create(request, staff)
                    ActivityService.log_staff_assignment_change(
                        request,
                        staff,
                        before_snapshot={},
                        after_snapshot=_client_staff_assignment_snapshot(staff),
                        reason='created',
                    )
            except Exception:
                logger.exception('Failed to log staff create activity for staff_id=%s', staff_id)
        return JsonResponse({
            'success': True,
            'message': result.message,
            'data': {'staff_id': result.data.get('staff_id')}
        })

    status_code = _result_error_status(result.message, fallback=400)
    return JsonResponse({
        'success': False,
        'error': result.message
    }, status=status_code)


@api_require_assistant_manager
@require_http_methods(["GET", "PUT", "DELETE"])
def api_staff_detail(request, staff_id):
    """
    API: Get, Update, or Delete a specific assistant on the admin side.
    """
    # Heal missing profile if queried directly
    try:
        from core.models import User as CoreUser
        ast = Assistant.objects.filter(id=staff_id).first()
        if not ast:
            usr = CoreUser.objects.filter(id=staff_id, role__in=['assistant']).first()
            if usr:
                default_client = Organisation.objects.first()
                Assistant.objects.get_or_create(user=usr, defaults={'client': default_client})
    except Exception:
        pass

    if request.method == 'GET':
        result = AssistantService.get_assistant_detail(request.user, staff_id)
        if result.success:
            return JsonResponse({
                'success': True,
                'data': result.data
            })
        
        return JsonResponse({
            'success': False,
            'error': result.message
        }, status=404 if 'found' in result.message.lower() else 403)
    
    if request.method == 'PUT':
        before_staff = (
            Assistant.objects
            .select_related('user')
            .prefetch_related('assigned_groups')
            .filter(id=staff_id)
            .first()
        )
        if not before_staff:
            return JsonResponse({'success': False, 'error': 'Assistant not found'}, status=404)
        
        before_assignment_snapshot = _client_staff_assignment_snapshot(before_staff)

        content_type = request.content_type or ''
        if 'multipart/form-data' in content_type:
            from django.http.multipartparser import MultiPartParser
            try:
                parser = MultiPartParser(request.META, request, request.upload_handlers)
                post_data, files = parser.parse()
            except Exception:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid multipart form data'
                }, status=400)
            data = post_data.dict()
            if 'assigned_groups' in data:
                try:
                    data['assigned_groups'] = json.loads(data['assigned_groups'])
                except (json.JSONDecodeError, TypeError):
                    data['assigned_groups'] = []
            if 'assignment_scopes' in data:
                try:
                    data['assignment_scopes'] = json.loads(data['assignment_scopes'])
                except (json.JSONDecodeError, TypeError):
                    data['assignment_scopes'] = []
            # Parse boolean strings
            for key in list(data.keys()):
                if data[key] in ('true', 'True'):
                    data[key] = True
                elif data[key] in ('false', 'False'):
                    data[key] = False
        else:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid JSON data'
                }, status=400)

        data = _normalize_staff_assignment_payload(data)
        
        # Admin side updates always run under the scope of the assistant's own client
        result = AssistantService.update_assistant(request.user, staff_id, data, target_client=before_staff.client)
        
        if result.success:
            try:
                staff = (
                    Assistant.objects
                    .select_related('user')
                    .prefetch_related('assigned_groups')
                    .filter(id=staff_id)
                    .first()
                )
                if staff:
                    ActivityService.log_staff_update(request, staff)
                    ActivityService.log_staff_assignment_change(
                        request,
                        staff,
                        before_snapshot=before_assignment_snapshot,
                        after_snapshot=_client_staff_assignment_snapshot(staff),
                        reason='updated',
                    )
            except Exception:
                logger.exception('Failed to log staff update activity for staff_id=%s', staff_id)
            return JsonResponse({
                'success': True,
                'message': result.message
            })
        
        status_code = _result_error_status(result.message, fallback=400)
        return JsonResponse({
            'success': False,
            'error': result.message
        }, status=status_code)
    
    # DELETE
    staff_name = f'Manager #{staff_id}'
    last_active_str = 'never active'
    try:
        existing_staff = Assistant.objects.select_related('user').filter(id=staff_id).first()
        if existing_staff:
            staff_name = existing_staff.user.get_full_name() or existing_staff.user.username
            last_active_str = ActivityService._format_last_active(existing_staff.user)
    except Exception:
        logger.exception('Failed to resolve staff name before delete for staff_id=%s', staff_id)

    result = AssistantService.delete_assistant(request.user, staff_id)
    
    if result.success:
        try:
            ActivityService.log_staff_delete(request, staff_name, last_active_str, staff_id, user_type='Assistant')
        except Exception:
            logger.exception('Failed to log staff delete activity for staff_id=%s', staff_id)
        return JsonResponse({
            'success': True,
            'message': result.message
        })
    
    status_code = _result_error_status(result.message, fallback=400)
    return JsonResponse({
        'success': False,
        'error': result.message
    }, status=status_code)


@api_require_assistant_manager
@require_http_methods(["POST"])
def api_staff_toggle_status(request, staff_id):
    """
    API: Toggle assistant active/inactive status on the admin side.
    """
    try:
        result = AssistantService.toggle_assistant_status(request.user, staff_id)
        if result.success:
            is_active = result.data.get('is_active', False)
            try:
                staff = Assistant.objects.select_related('user').filter(id=staff_id).first()
                if staff:
                    ActivityService.log_staff_status(request, staff, is_active)
                else:
                    ActivityService.log(
                        'staff_status',
                        f'Staff "#{staff_id}" marked as {"active" if is_active else "inactive"}',
                        request=request,
                        target_model='Staff',
                        target_id=staff_id,
                        target_name=f'Manager #{staff_id}',
                    )
            except Exception:
                logger.exception('Failed to log staff status activity for staff_id=%s', staff_id)
            return JsonResponse({
                'success': True,
                'message': result.message,
                'status': 'active' if is_active else 'inactive',
                'status_display': 'Active' if is_active else 'Inactive',
            })
        
        status_code = _result_error_status(result.message, fallback=400)
        return JsonResponse({
            'success': False,
            'message': result.message
        }, status=status_code)
    except Exception:
        logger.exception('Staff toggle status error')
        return JsonResponse({'success': False, 'message': 'An error occurred. Please try again.'}, status=500)


@api_require_assistant_manager
@require_http_methods(["POST"])
def api_staff_set_temp_password(request, staff_id):
    """API: Set temporary password for an assistant on the admin side."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON data'}, status=400)

    new_password = (data.get('password') or '').strip()
    if not new_password:
        return JsonResponse({'success': False, 'message': 'Password is required'}, status=400)
    if len(new_password) < 8:
        return JsonResponse({'success': False, 'message': 'Password must be at least 8 characters'}, status=400)

    from django.contrib.auth.password_validation import validate_password
    try:
        validate_password(new_password)
    except Exception as validation_error:
        return JsonResponse({'success': False, 'message': '; '.join(validation_error.messages)}, status=400)

    result = AssistantService.set_temp_password(
        request.user,
        staff_id,
        new_password,
        request=request,
    )

    if result.success:
        try:
            staff = Assistant.objects.select_related('user').filter(id=staff_id).first()
            staff_name = f'Manager #{staff_id}'
            if staff:
                staff_name = staff.user.get_full_name() or staff.user.username
            ActivityService.log(
                'staff_password_reset',
                f'Temporary password reset for client staff "{staff_name}"',
                request=request,
                target_model='Staff',
                target_id=staff_id,
                target_name=staff_name,
            )
        except Exception:
            logger.exception('Failed to log staff temp-password activity for staff_id=%s', staff_id)
        return JsonResponse(result.to_response_dict(), status=200)

    msg = (result.message or '').lower()
    if 'permission' in msg:
        status_code = 403
    elif 'not found' in msg:
        status_code = 404
    else:
        status_code = 400
    return JsonResponse(result.to_response_dict(), status=status_code)


@api_require_assistant_manager
@require_http_methods(["GET"])
def api_client_groups_list(request):
    """
    API: Get list of assignable containers for a selected client's assistants.
    Requires client_id query param.
    """
    client_id = request.GET.get('client_id')
    if not client_id:
        return JsonResponse({'success': False, 'message': 'client_id is required'}, status=400)

    client = Organisation.objects.filter(id=client_id).first()
    if not client:
        return JsonResponse({'success': False, 'message': 'Client not found'}, status=404)
    
    groups_qs = Table.objects.filter(client=client).order_by('name')
    group_count = groups_qs.count()

    if group_count <= 1:
        # Single-group client: show individual tables so the user can pick
        # which list (Student List, Staff List, etc.) to use.
        # This applies both for the assignment drawer AND for the auto-create
        # modal — previously for_auto_create=true bypassed this, hiding tables.
        tables_qs = Table.objects.filter(
            group__client=client,
            deleted_by_client=False,
        ).order_by('name').values('id', 'name', 'group_id')
        groups_data = [
            {
                'id': t['id'],
                'name': t['name'],
                'group_id': t['group_id'],
                'source': 'table',
            }
            for t in tables_qs
        ]
    else:
        groups_data = [
            {
                'id': g.id,
                'name': g.name,
                'group_id': g.id,
                'source': 'group',
            }
            for g in groups_qs
        ]
    
    return JsonResponse({
        'success': True,
        'groups': groups_data
    })


@api_require_assistant_manager
@require_http_methods(["GET"])
def api_class_section_options(request):
    """
    API: Get distinct class and section values from all cards of a selected client.
    Requires client_id query param.
    """
    from tables.models import IDCard, Table
    from tables.models import Table

    client_id = request.GET.get('client_id')
    if not client_id:
        return JsonResponse({'success': False, 'message': 'client_id is required'}, status=400)

    client = Organisation.objects.filter(id=client_id).first()
    if not client:
        return JsonResponse({'success': False, 'message': 'Client not found'}, status=404)

    raw_group_ids = request.GET.get('group_ids', '').strip()
    id_source = (request.GET.get('id_source', '') or '').strip().lower()
    if id_source not in ('group', 'table'):
        id_source = 'auto'

    resolved_id_source = id_source
    if resolved_id_source == 'auto':
        group_count = Table.objects.filter(client=client).count()
        resolved_id_source = 'table' if group_count <= 1 else 'group'

    group_ids = []
    if raw_group_ids:
        try:
            group_ids = sorted({int(x) for x in raw_group_ids.split(',') if str(x).strip().isdigit()})
        except Exception:
            group_ids = []

    # Resolve effective tables.
    tables_qs = Table.objects.filter(group__client=client, deleted_by_client=False)

    if group_ids:
        valid_group_ids = set(
            Table.objects.filter(client=client, id__in=group_ids).values_list('id', flat=True)
        )
        valid_table_ids = set(
            Table.objects.filter(group__client=client, id__in=group_ids).values_list('id', flat=True)
        )

        if resolved_id_source == 'table':
            if valid_table_ids:
                tables_qs = tables_qs.filter(id__in=list(valid_table_ids))
            elif valid_group_ids:
                tables_qs = tables_qs.filter(group_id__in=list(valid_group_ids))
            else:
                tables_qs = tables_qs.none()
        elif resolved_id_source == 'group':
            if valid_group_ids:
                tables_qs = tables_qs.filter(group_id__in=list(valid_group_ids))
            elif valid_table_ids:
                tables_qs = tables_qs.filter(id__in=list(valid_table_ids))
            else:
                tables_qs = tables_qs.none()

    tables = list(tables_qs.values('id', 'fields'))

    classes = set()
    sections = set()
    branches = set()
    class_sections = {}
    class_counts = {}
    section_counts = {}
    class_section_counts = {}
    table_field_map = {}
    has_class_field = False
    has_section_field = False
    has_branch_field = False

    for table in tables:
        class_field = None
        section_field = None
        branch_field = None
        for field in (table.get('fields') or []):
            ft = field.get('type', '').lower()
            fn = field.get('name', '')
            fn_lower = fn.lower()
            if ft == 'class' or fn_lower == 'class':
                class_field = fn
            elif ft == 'section' or fn_lower == 'section':
                section_field = fn
            elif (
                ft == 'branch'
                or fn_lower == 'branch'
                or fn_lower == 'stream'
                or fn_lower == 'course'
                or 'branch' in fn_lower
                or 'stream' in fn_lower
                or 'course' in fn_lower
            ):
                branch_field = fn

        if class_field:
            has_class_field = True
        if section_field:
            has_section_field = True
        if branch_field:
            has_branch_field = True

        if class_field or section_field or branch_field:
            table_field_map[table['id']] = (class_field, section_field, branch_field)

    table_ids = list(table_field_map.keys())
    if table_ids:
        cards = IDCard.objects.filter(table_id__in=table_ids).values_list('table_id', 'field_data').iterator(chunk_size=1000)
    else:
        cards = []

    for table_id, fd in cards:
        if not fd:
            continue

        class_field, section_field, branch_field = table_field_map.get(table_id, (None, None, None))
        class_val = ''
        section_val = ''
        if class_field:
            val = fd.get(class_field, '') or fd.get(class_field.upper(), '') or fd.get(class_field.lower(), '')
            if val:
                class_val = str(val).strip()
                if class_val:
                    classes.add(class_val)
        if section_field:
            val = fd.get(section_field, '') or fd.get(section_field.upper(), '') or fd.get(section_field.lower(), '')
            if val:
                section_val = str(val).strip()
                if section_val:
                    sections.add(section_val)
        if branch_field:
            val = fd.get(branch_field, '') or fd.get(branch_field.upper(), '') or fd.get(branch_field.lower(), '')
            if val:
                branch_val = str(val).strip()
                if branch_val:
                    branches.add(branch_val)

        if class_val:
            if class_val not in class_sections:
                class_sections[class_val] = set()
            if section_val:
                class_sections[class_val].add(section_val)

            class_counts[class_val] = class_counts.get(class_val, 0) + 1

        if section_val:
            section_counts[section_val] = section_counts.get(section_val, 0) + 1

        if class_val and section_val:
            class_section_counts.setdefault(class_val, {})
            class_section_counts[class_val][section_val] = (
                class_section_counts[class_val].get(section_val, 0) + 1
            )

    # ── Normalize class values ──
    from core.utils.field_utils import normalize_class_value, CLASS_ORDER, CLASS_ORDER_UNKNOWN
    from collections import defaultdict

    class_groups = defaultdict(list)
    for raw_cls, count in class_counts.items():
        canonical = normalize_class_value(raw_cls)
        if canonical:
            class_groups[canonical].append((raw_cls, count))

    raw_class_to_best = {}
    best_classes = set()
    best_class_counts = {}
    best_class_sections = {}
    best_class_section_counts = {}

    for canonical, variants in class_groups.items():
        best_raw = max(variants, key=lambda x: x[1])[0]
        best_classes.add(best_raw)
        for raw_cls, _ in variants:
            raw_class_to_best[raw_cls] = best_raw

    for raw_cls, count in class_counts.items():
        best_cls = raw_class_to_best.get(raw_cls, raw_cls)
        best_class_counts[best_cls] = best_class_counts.get(best_cls, 0) + count

    for raw_cls, secs in class_sections.items():
        best_cls = raw_class_to_best.get(raw_cls, raw_cls)
        if best_cls not in best_class_sections:
            best_class_sections[best_cls] = set()
        best_class_sections[best_cls].update(secs)

    for raw_cls, sec_cnts in class_section_counts.items():
        best_cls = raw_class_to_best.get(raw_cls, raw_cls)
        if best_cls not in best_class_section_counts:
            best_class_section_counts[best_cls] = {}
        for sec, count in sec_cnts.items():
            best_class_section_counts[best_cls][sec] = (
                best_class_section_counts[best_cls].get(sec, 0) + count
            )

    classes = best_classes
    class_counts = best_class_counts
    class_sections = best_class_sections
    class_section_counts = best_class_section_counts

    payload = {
        'success': True,
        'resolved_id_source': resolved_id_source,
        'classes': sorted(
            classes,
            key=lambda x: (CLASS_ORDER.get(normalize_class_value(x), CLASS_ORDER_UNKNOWN), normalize_class_value(x))
        ),
        'sections': sorted(sections),
        'branches': sorted(branches),
        'has_class_field': has_class_field,
        'has_section_field': has_section_field,
        'has_branch_field': has_branch_field,
        'class_sections': {
            cls_name: sorted(sec_values)
            for cls_name, sec_values in sorted(class_sections.items(), key=lambda x: (CLASS_ORDER.get(normalize_class_value(x[0]), CLASS_ORDER_UNKNOWN), normalize_class_value(x[0])))
        },
        'class_counts': {
            cls_name: int(count)
            for cls_name, count in sorted(class_counts.items(), key=lambda x: (CLASS_ORDER.get(normalize_class_value(x[0]), CLASS_ORDER_UNKNOWN), normalize_class_value(x[0])))
        },
        'section_counts': {
            sec_name: int(count)
            for sec_name, count in sorted(section_counts.items(), key=lambda x: x[0])
        },
        'class_section_counts': {
            cls_name: {
                sec_name: int(sec_count)
                for sec_name, sec_count in sorted(sec_counts.items(), key=lambda x: x[0])
            }
            for cls_name, sec_counts in sorted(class_section_counts.items(), key=lambda x: (CLASS_ORDER.get(normalize_class_value(x[0]), CLASS_ORDER_UNKNOWN), normalize_class_value(x[0])))
        },
    }
    return JsonResponse(payload)


@api_require_super_admin
@require_http_methods(["POST"])
def api_staff_bulk_upload_xlsx(request):
    """
    API: Bulk upload assistants from an XLSX file for a specific client.
    """
    client_id = request.POST.get('client_id')
    if not client_id:
        return JsonResponse({'success': False, 'message': 'client_id is required'}, status=400)

    target_client = Organisation.objects.filter(id=client_id).first()
    if not target_client:
        return JsonResponse({'success': False, 'message': 'Client not found'}, status=404)

    file_obj = request.FILES.get('file')
    if not file_obj:
        return JsonResponse({'success': False, 'message': 'No file uploaded'}, status=400)

    if not file_obj.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'success': False, 'message': 'Please upload a valid Excel file (.xlsx or .xls)'}, status=400)

    result = AssistantService.bulk_create_from_excel(request.user, target_client, file_obj)

    if result.success:
        try:
            # Optionally log this activity
            ActivityService.log(
                'staff_bulk_upload',
                f'Bulk uploaded assistants for client "{target_client.name}"',
                request=request,
                target_model='Client',
                target_id=target_client.id,
                target_name=target_client.name,
            )
        except Exception:
            logger.exception('Failed to log staff bulk upload activity')
            
        return JsonResponse(result.to_response_dict())

    return JsonResponse(result.to_response_dict(), status=400)


@api_require_super_admin
@require_http_methods(["POST"])
def api_staff_auto_create(request):
    """
    API: Auto create assistants based on classes or sections.

    Accepts either:
      - group_id + id_source='group'  → filter all tables inside that group
      - table_id + id_source='table'  → filter only that specific table

    For backward compatibility, a bare group_id with no id_source is still
    treated as id_source='group'.
    """
    client_id = request.POST.get('client_id')
    acronym = request.POST.get('acronym')
    mode = request.POST.get('mode')  # 'class' or 'section'
    auto_assign = request.POST.get('assign') == 'true'
    id_source = (request.POST.get('id_source') or '').strip().lower()  # 'group' or 'table'

    # Accept either group_id or table_id depending on id_source
    group_id = request.POST.get('group_id')
    table_id = request.POST.get('table_id')
    # Resolve the primary selection id
    selection_id = table_id if id_source == 'table' else group_id

    if not client_id or not selection_id or not acronym or not mode:
        return JsonResponse({'success': False, 'message': 'client_id, a group or table selection, acronym, and mode are required'}, status=400)

    target_client = Organisation.objects.filter(id=client_id).first()
    if not target_client:
        return JsonResponse({'success': False, 'message': 'Client not found'}, status=404)

    target_group = None
    target_table = None

    if id_source == 'table':
        target_table = Table.objects.filter(id=selection_id, group__client=target_client, deleted_by_client=False).first()
        if not target_table:
            return JsonResponse({'success': False, 'message': 'List/Table not found'}, status=404)
        target_group = target_table.group  # also carry the parent group for assignment
    else:
        target_group = Table.objects.filter(id=selection_id, client=target_client).first()
        if not target_group:
            return JsonResponse({'success': False, 'message': 'Group/List not found'}, status=404)

    result = AssistantService.auto_create_assistants(
        request.user, target_client, acronym, mode, auto_assign,
        group=target_group, table=target_table,
    )

    if result.success:
        try:
            ActivityService.log(
                'staff_auto_create',
                f'Auto created {result.data["count"]} assistants for client "{target_client.name}" (mode: {mode})',
                request=request,
                target_model='Client',
                target_id=target_client.id,
                target_name=target_client.name,
            )
        except Exception:
            logger.exception('Failed to log staff auto create activity')
            
        buffer = result.data['buffer'].getvalue()
        response = HttpResponse(buffer, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="assistants_{acronym.strip().lower()}.xlsx"'
        return response

    return JsonResponse(result.to_response_dict(), status=400)


@api_require_assistant_manager
@require_http_methods(["DELETE"])
def api_staff_bulk_delete(request):
    """
    API: Bulk delete assistants.
    Expects JSON body: {"ids": [1, 2, 3]}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)

    staff_ids = data.get('ids', [])
    if not staff_ids:
        return JsonResponse({'success': False, 'error': 'No assistant IDs provided'}, status=400)

    deleted_names = []
    failed_ids = []

    for staff_id in staff_ids:
        staff_name = f'Staff #{staff_id}'
        last_active_str = 'never active'
        try:
            existing_staff = Assistant.objects.select_related('user').filter(id=staff_id).first()
            if existing_staff:
                staff_name = existing_staff.user.get_full_name() or existing_staff.user.username
                last_active_str = ActivityService._format_last_active(existing_staff.user)
        except Exception:
            pass

        result = AssistantService.delete_assistant(request.user, staff_id)
        if result.success:
            deleted_names.append(staff_name)
            try:
                ActivityService.log_staff_delete(request, staff_name, last_active_str, staff_id, user_type='Assistant')
            except Exception:
                logger.exception('Failed to log staff delete activity for staff_id=%s', staff_id)
        else:
            failed_ids.append(staff_id)

    if failed_ids:
        if len(deleted_names) > 0:
            msg = f'Deleted {len(deleted_names)} assistants, but failed to delete {len(failed_ids)}.'
            return JsonResponse({'success': True, 'message': msg})
        else:
            return JsonResponse({'success': False, 'error': 'Failed to delete selected assistants'}, status=400)

    return JsonResponse({
        'success': True,
        'message': f'Successfully deleted {len(deleted_names)} assistant(s)!'
    })
