"""
Manage Passwords / Temporary Passwords API endpoints for Pro User / Prime Admin.
Allows viewing temporary credentials, resetting/regenerating PIN passwords,
and resending credential emails.
"""
import json
import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from django.utils.timezone import localtime
from django.db.models import Count

from core.models import User, EmailLog
from core.services.auto_password_service import AutoPasswordService
from core.services.permission_service import PermissionService
from core.utils.email_utils import send_welcome_email
from organisation.models import Organisation, OrganisationManager
from assistants.models import Assistant
from operators.models import Operator

logger = logging.getLogger(__name__)


def _require_admin_or_pro(request):
    user = getattr(request, 'user', None)
    if not (PermissionService.is_super_admin(user) or PermissionService.can_manage_pro_features(user)):
        return JsonResponse({'success': False, 'message': 'Admin or Pro User access required.'}, status=403)
    return None


@login_required
@require_http_methods(['GET'])
def api_manage_temp_passwords_list(request):
    """
    List all user accounts with their credentials and temporary password status.
    Filterable by role, search, and temp_password status.
    """
    guard = _require_admin_or_pro(request)
    if guard is not None:
        return guard

    role_filter = request.GET.get('role', '').strip().lower()
    search = request.GET.get('search', '').strip().lower()
    status_filter = request.GET.get('status', '').strip().lower()

    qs = User.objects.all().order_by('-date_joined', '-id')

    if role_filter and role_filter != 'all':
        if role_filter in ('client', 'prime_manager', 'organisation'):
            qs = qs.filter(role__in=['client', 'prime_manager', 'guest_prime_manager'])
        elif role_filter in ('super_manager', 'manager'):
            qs = qs.filter(role__in=['super_manager', 'manager'])
        elif role_filter == 'guest_manager':
            qs = qs.filter(role='guest_manager')
        elif role_filter in ('operator', 'admin_staff'):
            qs = qs.filter(role='operator')
        elif role_filter in ('assistant', 'client_staff'):
            qs = qs.filter(role='assistant')
        else:
            qs = qs.filter(role=role_filter)

    user_list = list(qs)
    user_ids = [u.id for u in user_list]

    # Pre-fetch associations in bulk to prevent N+1 queries
    org_by_user = {org.user_id: org.name for org in Organisation.objects.filter(user_id__in=user_ids)}
    org_mgr_by_user = {
        mgr.user_id: mgr.organisation.name
        for mgr in OrganisationManager.objects.filter(user_id__in=user_ids).select_related('organisation')
    }
    ast_by_user = {
        ast.user_id: ast.organisation.name
        for ast in Assistant.objects.filter(user_id__in=user_ids).select_related('organisation')
    }
    op_counts = {
        row['operator__user_id']: row['cnt']
        for row in Operator.assigned_organisations.through.objects.filter(
            operator__user_id__in=user_ids
        ).values('operator__user_id').annotate(cnt=Count('organisation_id'))
    }
    op_user_ids = set(Operator.objects.filter(user_id__in=user_ids).values_list('user_id', flat=True))

    users_data = []
    for user in user_list:
        # Determine full display name and organisation association
        full_name = user.get_full_name() or user.username
        org_name = ''
        
        if user.role in ('client', 'prime_manager', 'guest_prime_manager'):
            org_name = org_by_user.get(user.id, '')
            if org_name and not user.get_full_name():
                full_name = org_name
        elif user.role in ('super_manager', 'guest_manager', 'manager'):
            org_name = org_mgr_by_user.get(user.id, '')
        elif user.role == 'assistant':
            org_name = ast_by_user.get(user.id, '')
        elif user.role == 'operator':
            if user.id in op_user_ids:
                assigned_count = op_counts.get(user.id, 0)
                org_name = f"{assigned_count} Assigned Org(s)" if assigned_count else 'All Orgs'

        # Match search filter
        if search:
            match_fields = [
                full_name.lower(),
                (user.username or '').lower(),
                (user.email or '').lower(),
                (user.phone or '').lower(),
                org_name.lower(),
            ]
            if not any(search in f for f in match_fields):
                continue

        has_temp = bool(user.temp_password)
        if status_filter == 'temp' and not has_temp:
            continue
        if status_filter == 'changed' and has_temp:
            continue

        role_display = user.get_role_display() if hasattr(user, 'get_role_display') else user.role
        if user.role in ('client', 'prime_manager'):
            role_display = 'Organisation Admin'
        elif user.role == 'guest_prime_manager':
            role_display = 'Guest Prime Manager'
        elif user.role in ('super_manager', 'manager'):
            role_display = 'Super Manager'
        elif user.role == 'guest_manager':
            role_display = 'Guest Manager'
        elif user.role == 'operator':
            role_display = 'Operator'
        elif user.role == 'assistant':
            role_display = 'Assistant'
        elif user.role in ('super_admin', 'pro_user', 'prime_admin'):
            role_display = 'Prime Admin'

        temp_created = ''
        if user.temp_password_created_at:
            temp_created = localtime(user.temp_password_created_at).strftime('%d-%m-%Y %H:%M')

        users_data.append({
            'id': user.id,
            'name': full_name,
            'org_name': org_name,
            'username': user.username,
            'email': user.email if not (user.email or '').endswith('@noemail.local') else '',
            'phone': user.phone or '',
            'role': user.role,
            'role_display': role_display,
            'is_active': user.is_active,
            'temp_password': user.temp_password or '',
            'temp_password_created_at': temp_created,
            'must_change_password': getattr(user, 'must_change_password', False),
            'has_temp_password': has_temp,
            'date_joined': localtime(user.date_joined).strftime('%d-%m-%Y') if user.date_joined else '',
        })

    return JsonResponse({
        'success': True,
        'users': users_data,
        'total': len(users_data),
    })


@login_required
@require_http_methods(['POST'])
def api_manage_temp_password_reset(request):
    """
    Generate and assign a new temporary PIN / password for a user.
    Optionally send credentials to user via email.
    """
    guard = _require_admin_or_pro(request)
    if guard is not None:
        return guard

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'success': False, 'message': 'Invalid JSON body'}, status=400)

    user_id = data.get('user_id')
    if not user_id:
        return JsonResponse({'success': False, 'message': 'user_id is required'}, status=400)

    user = get_object_or_404(User, pk=user_id)

    # Determine name / org for password acronym generation
    name_for_pwd = user.get_full_name() or user.username
    if user.role in ('client', 'prime_manager', 'guest_prime_manager'):
        org = Organisation.objects.filter(user=user).first()
        if org:
            name_for_pwd = org.name

    new_password = AutoPasswordService.generate_auto_password(
        name_or_org=name_for_pwd,
        phone=user.phone or '',
    )

    AutoPasswordService.assign_temp_password(user, new_password, must_change=True)

    # Send credentials email if valid email address exists
    email_sent = False
    if user.email and '@' in user.email and not user.email.endswith('@noemail.local'):
        try:
            send_welcome_email(
                name=user.get_full_name() or user.username,
                email=user.email,
                password=new_password,
                role=user.role,
                phone=user.phone or '',
                email_variant='temp_password',
                request=request,
            )
            email_sent = True
        except Exception as e:
            logger.warning('Failed to send reset email to %s: %s', user.email, e)

    return JsonResponse({
        'success': True,
        'message': f'Temporary PIN generated for "{user.username}".' + (' Email sent.' if email_sent else ''),
        'temp_password': new_password,
        'email_sent': email_sent,
    })


@login_required
@require_http_methods(['POST'])
def api_manage_temp_password_resend_email(request):
    """
    Resend credentials email to the specified user using their current temp password.
    """
    guard = _require_admin_or_pro(request)
    if guard is not None:
        return guard

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'success': False, 'message': 'Invalid JSON body'}, status=400)

    user_id = data.get('user_id')
    if not user_id:
        return JsonResponse({'success': False, 'message': 'user_id is required'}, status=400)

    user = get_object_or_404(User, pk=user_id)

    if not user.email or '@' not in user.email or user.email.endswith('@noemail.local'):
        return JsonResponse({'success': False, 'message': 'User does not have a valid email address'}, status=400)

    pwd_to_send = user.temp_password
    if not pwd_to_send:
        # Generate fresh temporary PIN if none exists
        name_for_pwd = user.get_full_name() or user.username
        if user.role in ('client', 'prime_manager', 'guest_prime_manager'):
            org = Organisation.objects.filter(user=user).first()
            if org:
                name_for_pwd = org.name
        pwd_to_send = AutoPasswordService.generate_auto_password(name_or_org=name_for_pwd, phone=user.phone or '')
        AutoPasswordService.assign_temp_password(user, pwd_to_send, must_change=True)

    try:
        send_welcome_email(
            name=user.get_full_name() or user.username,
            email=user.email,
            password=pwd_to_send,
            role=user.role,
            phone=user.phone or '',
            email_variant='temp_password' if user.temp_password else 'welcome',
            request=request,
        )
        return JsonResponse({
            'success': True,
            'message': f'Credentials email resent to {user.email}.',
            'temp_password': pwd_to_send,
        })
    except Exception as e:
        logger.exception('Failed to resend credentials email: %s', e)
        return JsonResponse({'success': False, 'message': f'Failed to send email: {str(e)}'}, status=500)
