"""
Maintenance Mode API views
===========================
- GET  api/maintenance/status/     — current maintenance status (public)
- POST api/maintenance/toggle/     — enable / disable (super_admin only)
- GET  maintenance/system/         — maintenance page for blocked users
"""

import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.services.maintenance_service import MaintenanceService
from core.services.permission_service import PermissionService
from core.services.permission_service import require_super_admin

logger = logging.getLogger(__name__)


# ── Public status endpoint (polled by maintenance page) ──────────────

@login_required
@require_http_methods(['GET'])
def api_system_maintenance_check(request):
    """Lightweight poll with role-aware payload."""
    status = MaintenanceService.get_status()
    if not PermissionService.is_any_admin(request.user):
        return JsonResponse({'enabled': bool(status.get('enabled', False))})
    return JsonResponse(status)


# ── Admin toggle ─────────────────────────────────────────────────────

@require_super_admin
@require_http_methods(['POST'])
def api_maintenance_toggle(request):
    """Enable or disable maintenance mode."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    action = data.get('action', '')

    if action == 'enable':
        end_time = data.get('end_time', '')  # ISO string
        message = data.get('message', '')
        duration = data.get('duration_minutes')
        MaintenanceService.activate(
            end_time=end_time or None,
            message=message,
            duration_minutes=duration,
            user=request.user,
        )
        return JsonResponse({
            'success': True,
            'message': 'Maintenance mode enabled. All users have been notified.',
            'status': MaintenanceService.get_status(),
        })

    elif action == 'disable':
        MaintenanceService.deactivate(user=request.user)
        return JsonResponse({
            'success': True,
            'message': 'Maintenance mode disabled. Users have been notified.',
            'status': MaintenanceService.get_status(),
        })

    return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)


# ── Maintenance page shown to blocked users ──────────────────────────

@login_required
def system_maintenance_page(request):
    """Full-screen maintenance page with countdown timer."""
    import json as _json
    status = MaintenanceService.get_status()
    redirect_url = reverse('dashboard')
    if not status.get('enabled'):
        return redirect(redirect_url)
    end_time_json = _json.dumps(status['end_time']) if status['end_time'] else 'null'
    return render(request, 'index.html', {
        'message': status['message'],
        'end_time_json': end_time_json,
        'redirect_url': redirect_url,
    })
