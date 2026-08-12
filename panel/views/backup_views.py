"""
Backup views  (panel app)
==========================

Endpoints for the backup modal, client-selection page, and Manage Panel
backup tab.  Logic is identical to what was in core/views/backup_api.py;
the file just lives here now so it's co-located with panel features.

All destructive actions require a 10-digit confirmation code.
"""

import json
import logging
import os
import secrets
import string
from typing import List

from django.conf import settings as django_settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse, FileResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods

from core.models import BackupTask
from core.services.activity_service import ActivityService
from core.services.permission_service import require_permission, api_require_permission, PermissionService
from organisation.models import Organisation

logger = logging.getLogger(__name__)


# ─── Helpers ─────────────────────────────────────────────────────────────

def _generate_code() -> str:
    return ''.join(secrets.choice(string.digits) for _ in range(10))


def _json_error(msg, status=400):
    return JsonResponse({'success': False, 'message': msg}, status=status)


def _normalize_id_list(values) -> List[int]:
    """Normalize a JSON list to unique positive integer IDs."""
    if not isinstance(values, list):
        return []

    out: List[int] = []
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
        if len(out) >= 1000:
            break
    return out


def _resolve_media_file(file_path: str):
    """Resolve a media-relative backup path and reject traversal attempts."""
    if not file_path:
        return None

    media_root = os.path.abspath(django_settings.MEDIA_ROOT)
    candidate = os.path.abspath(os.path.join(media_root, str(file_path)))
    try:
        if os.path.commonpath([media_root, candidate]) != media_root:
            return None
    except ValueError:
        return None
    return candidate


# ─── Page views ──────────────────────────────────────────────────────────

@login_required
@require_permission('perm_manage_panel_backup', redirect_url='/panel/')
def backup_select_clients(request):
    """Page: shows all clients with sort/filter for backup selection."""
    task_id = request.GET.get('task')
    if not task_id:
        return render(request, 'index.html', {'error': 'No backup task specified.'})

    task = get_object_or_404(BackupTask, pk=task_id, created_by=request.user, status='pending')

    sort = request.GET.get('sort', 'most_data')
    clients_qs = Organisation.objects.filter(status='active').annotate(
        total_cards=Count('id_card_groups__tables__id_cards'),
        total_tables=Count('id_card_groups__tables', distinct=True),
    )

    if sort == 'most_data':
        clients_qs = clients_qs.order_by('-total_cards', '-created_at')
    elif sort == 'latest':
        clients_qs = clients_qs.order_by('-created_at')
    elif sort == 'oldest':
        clients_qs = clients_qs.order_by('created_at')
    elif sort == 'name':
        clients_qs = clients_qs.order_by('name')
    else:
        clients_qs = clients_qs.order_by('-total_cards')

    return render(request, 'index.html', {
        'task': task,
        'clients': clients_qs,
        'current_sort': sort,
        'is_super_admin': PermissionService.is_super_admin(request.user),
    })


# ─── API endpoints ───────────────────────────────────────────────────────

@login_required
@api_require_permission('perm_manage_panel_backup')
@require_http_methods(['POST'])
def api_backup_initiate(request):
    """Step 1 — modal submits the 10-digit code; creates pending BackupTask."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return _json_error('Invalid request body.')

    code = str(body.get('code', '')).strip()
    if len(code) != 10 or not code.isdigit():
        return _json_error('Please enter a valid 10-digit confirmation code.')

    # Delete any abandoned pending backup tasks first to avoid database clutter
    BackupTask.objects.filter(status='pending').delete()

    task = BackupTask.objects.create(
        created_by=request.user,
        confirmation_code=code,
        status='pending',
    )
    ActivityService.log(
        'backup_initiate',
        f'Backup task initiated (#{task.pk})',
        request=request,
        target_model='BackupTask',
        target_id=task.pk,
        target_name=f'Backup #{task.pk}',
    )
    return JsonResponse({
        'success': True,
        'task_id': task.pk,
        'redirect_url': f'/panel/backup/select-clients/?task={task.pk}',
    })


@login_required
@api_require_permission('perm_manage_panel_backup')
@require_http_methods(['POST'])
def api_backup_start(request):
    """Step 2 — client-selection page submits chosen client IDs."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return _json_error('Invalid request body.')

    task_id_raw = body.get('task_id')
    client_ids_raw = body.get('client_ids', [])

    try:
        task_id = int(task_id_raw)
    except (TypeError, ValueError):
        task_id = 0

    if task_id <= 0:
        return _json_error('Missing task_id.')
    client_ids = _normalize_id_list(client_ids_raw)
    if not client_ids:
        return _json_error('Please select at least one client.')

    task = get_object_or_404(BackupTask, pk=task_id, created_by=request.user)
    if task.status != 'pending':
        return _json_error('This backup task has already been started.')

    # Heavy I/O safety: allow only one active backup at a time.
    if BackupTask.objects.filter(status='processing').exists():
        return _json_error('Another backup is already running. Please wait for it to finish.', status=429)

    valid_clients = list(Organisation.objects.filter(pk__in=client_ids, status='active').only('pk', 'name'))
    if not valid_clients:
        return _json_error('No valid active clients selected.')
    valid_client_count = len(valid_clients)

    names = {str(c.pk): c.name for c in valid_clients}
    task.client_ids = [c.pk for c in valid_clients]
    task.client_names = names
    task.total = valid_client_count
    task.save(update_fields=['client_ids', 'client_names', 'total'])

    from panel.services.backup_service import start_backup
    start_backup(task.pk)

    ActivityService.log_backup_start(
        request,
        task_id=task.pk,
        client_names_dict=task.client_names,
    )

    return JsonResponse({
        'success': True,
        'message': f'Backup started for {valid_client_count} school(s). You can track progress in the Manage Panel.',
    })


@login_required
@api_require_permission('perm_manage_panel_backup')
@require_http_methods(['GET'])
def api_backup_status(request, task_id):
    """Poll backup progress."""
    task = get_object_or_404(BackupTask, pk=task_id)
    return JsonResponse({
        'success': True,
        'id': task.pk,
        'status': task.status,
        'progress': task.progress,
        'total': task.total,
        'progress_pct': task.progress_percentage,
        'current_client': task.current_client,
        'error_message': task.error_message,
        'auto_delete_at': task.auto_delete_at.isoformat() if task.auto_delete_at else None,
        'is_auto_delete_cancelled': task.is_auto_delete_cancelled,
        'time_remaining': task.time_remaining_seconds,
        'client_names': task.client_names,
        'created_at': task.created_at.isoformat(),
        'combined_zip': (task.zip_files or {}).get('combined'),
    })


@login_required
@api_require_permission('perm_manage_panel_backup')
@require_http_methods(['GET'])
def api_backup_list(request):
    """List all backup tasks (recent first) for the Manage Panel."""
    tasks = BackupTask.objects.order_by('-created_at')[:20]
    result = []
    for t in tasks:
        combined_zip = (t.zip_files or {}).get('combined')
        result.append({
            'id': t.pk,
            'status': t.status,
            'progress': t.progress,
            'total': t.total,
            'progress_pct': t.progress_percentage,
            'current_client': t.current_client,
            'client_names': t.client_names,
            'created_at': t.created_at.isoformat(),
            'combined_zip': combined_zip,
            'error_message': t.error_message,
        })
    return JsonResponse({'success': True, 'backups': result})


@login_required
@api_require_permission('perm_manage_panel_backup')
@require_http_methods(['POST'])
def api_backup_delete_now(request, task_id):
    """Immediately delete backup files."""
    if PermissionService.is_super_admin(request.user):
        task = get_object_or_404(BackupTask, pk=task_id)
    else:
        task = get_object_or_404(BackupTask, pk=task_id, created_by=request.user)

    if task.status not in ('completed', 'failed'):
        return _json_error('Cannot delete an active or already deleted backup.')

    from panel.services.backup_service import delete_backup_files
    delete_backup_files(task.pk)
    ActivityService.log_backup_delete(
        request,
        task_id=task.pk,
        client_names_dict=task.client_names,
    )
    return JsonResponse({'success': True, 'message': 'Backup files deleted successfully.'})


@login_required
@api_require_permission('perm_manage_panel_backup')
@require_http_methods(['GET'])
def api_backup_download(request, task_id):
    """Download the combined backup ZIP."""
    task = get_object_or_404(BackupTask, pk=task_id, status='completed')
    info = (task.zip_files or {}).get('combined')
    if not info:
        return _json_error('Combined ZIP file not found for this backup.', 404)

    file_path = info.get('path', '')
    abs_path = _resolve_media_file(file_path)
    if not abs_path:
        return _json_error('Backup ZIP path is invalid.', 404)
    if not os.path.isfile(abs_path):
        return _json_error('Backup ZIP file no longer exists on disk.', 404)

    filename = os.path.basename(str(info.get('filename') or 'Adarsh Backup.zip')).replace('\r', '').replace('\n', '')
    if not filename:
        filename = 'Adarsh Backup.zip'

    # Log the download
    try:
        ActivityService.log_backup_download(
            request,
            task_id=task_id,
            client_names_dict=task.client_names,
        )
    except Exception:
        pass

    response = FileResponse(
        open(abs_path, 'rb'),
        as_attachment=True,
        filename=filename,
    )
    return response


@login_required
@api_require_permission('perm_manage_panel_backup')
@require_http_methods(['GET'])
def api_backup_generate_code(request):
    """Generate a 10-digit code for the backup confirmation modal."""
    return JsonResponse({'success': True, 'code': _generate_code()})
