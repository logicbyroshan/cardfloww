import json

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from functools import wraps

from accounts.rate_limit import _get_client_ip, rate_limit
from core.services.permission_service import PermissionService

from .services import DesktopAppService


def _json_body(request):
    if request.content_type and 'application/json' in request.content_type.lower():
        try:
            payload = json.loads(request.body or b'{}')
            if isinstance(payload, dict):
                return payload
        except Exception:
            return {}
    return request.POST.dict()


def _get_token(request):
    auth_header = (request.META.get('HTTP_AUTHORIZATION') or '').strip()
    if auth_header.lower().startswith('bearer '):
        return auth_header.split(' ', 1)[1].strip()
    header_token = (request.META.get('HTTP_X_DESKTOP_API_KEY') or request.META.get('HTTP_X_DESKTOP_TOKEN') or '').strip()
    if header_token:
        return header_token
    # Support query parameter for <img> tags which cannot pass headers
    return request.GET.get('token', '').strip()


def desktop_api_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        token = _get_token(request)
        installation_id = (request.META.get('HTTP_X_DESKTOP_INSTALLATION_ID') or request.META.get('HTTP_X_INSTALLATION_ID') or '').strip()
        result = DesktopAppService.authenticate_token(token, installation_id=installation_id, ip_address=_get_client_ip(request))
        if not result.success:
            return JsonResponse({'success': False, 'message': result.message}, status=result.status_code)
        request.desktop_device = result.device
        return view_func(request, *args, **kwargs)
    return wrapper


def bootstrap_or_admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        bootstrap = (request.META.get('HTTP_X_DESKTOP_BOOTSTRAP') or request.META.get('HTTP_X_BOOTSTRAP_TOKEN') or '').strip()
        if bootstrap and bootstrap == getattr(settings, 'DESKTOP_APP_BOOTSTRAP_TOKEN', ''):
            return view_func(request, *args, **kwargs)
        if getattr(request, 'user', None) and request.user.is_authenticated and PermissionService.is_super_admin(request.user):
            return view_func(request, *args, **kwargs)
        return JsonResponse({'success': False, 'message': 'Bootstrap token required.'}, status=403)
    return wrapper


@csrf_exempt
@require_POST
@rate_limit(max_requests=50, window_seconds=60, key_prefix='desktop-register')
@bootstrap_or_admin_required
def register_device(request):
    payload = _json_body(request)
    is_admin_session = bool(getattr(request, 'user', None) and request.user.is_authenticated and PermissionService.is_super_admin(request.user))
    result = DesktopAppService.register_device(
        device_name=payload.get('device_name') or payload.get('name') or 'Desktop Device',
        installation_id=payload.get('installation_id') or payload.get('device_id') or '',
        bootstrap_token=(request.META.get('HTTP_X_DESKTOP_BOOTSTRAP') or request.META.get('HTTP_X_BOOTSTRAP_TOKEN') or '').strip(),
        allow_admin=is_admin_session,
        ip_address=_get_client_ip(request),
    )
    if not result.success:
        return JsonResponse({'success': False, 'message': result.message}, status=result.status_code)
    return JsonResponse({
        'success': True,
        'message': result.message,
        'access_token': result.token,
        'token_type': 'Bearer',
        'device': {
            'id': result.device.id,
            'device_name': result.device.device_name,
            'installation_id': result.device.installation_id,
            'token_prefix': result.device.token_prefix,
            'token_expires_at': result.device.token_expires_at.isoformat() if result.device.token_expires_at else None,
        },
    }, status=201)


@csrf_exempt
@require_POST
@desktop_api_required
def revoke_device(request):
    payload = _json_body(request)
    result = DesktopAppService.revoke_device(
        installation_id=payload.get('installation_id') or '',
        token=_get_token(request),
    )
    return JsonResponse({'success': result.success, 'message': result.message}, status=result.status_code)


@require_GET
@desktop_api_required
def status(request):
    device = request.desktop_device
    return JsonResponse({
        'success': True,
        'message': 'Desktop API is ready.',
        'max_connections': getattr(settings, 'DESKTOP_APP_MAX_CONNECTIONS', 5),
        'device': {
            'id': device.id,
            'device_name': device.device_name,
            'installation_id': device.installation_id,
            'last_seen_at': device.last_seen_at.isoformat() if device.last_seen_at else None,
            'token_expires_at': device.token_expires_at.isoformat() if device.token_expires_at else None,
        },
    })


@require_GET
@desktop_api_required
def clients_manifest(request):
    client_id = request.GET.get('client_id')
    table_id = request.GET.get('table_id')
    search_query = request.GET.get('q')
    
    include_data = bool(client_id or table_id)
    
    manifest = DesktopAppService.build_manifest(
        client_id=int(client_id) if client_id and client_id.isdigit() else None,
        table_id=int(table_id) if table_id and table_id.isdigit() else None,
        search_query=search_query,
        request=request,
        include_data=include_data,
    )
    return JsonResponse(manifest, status=200 if manifest.get('success') else 404)


@require_GET
@desktop_api_required
def export_archive(request):
    client_id = request.GET.get('client_id')
    table_id = request.GET.get('table_id')
    result = DesktopAppService.build_archive(
        client_id=int(client_id) if client_id and client_id.isdigit() else None,
        table_id=int(table_id) if table_id and table_id.isdigit() else None,
        request=request,
    )
    if not result.get('success'):
        return JsonResponse({'success': False, 'message': result.get('message', 'Export failed.')}, status=404)
    response = FileResponse(result['archive'], as_attachment=True, filename=result['filename'])
    response['X-Desktop-Export-Count'] = str(result['manifest']['summary']['media_files'])
    return response


@require_GET
@desktop_api_required
def export_images(request):
    client_id = request.GET.get('client_id')
    group_id = request.GET.get('group_id')
    table_id = request.GET.get('table_id')
    status = request.GET.get('status')
    
    result = DesktopAppService.build_images_zip(
        client_id=int(client_id) if client_id and client_id.isdigit() else None,
        group_id=int(group_id) if group_id and group_id.isdigit() else None,
        table_id=int(table_id) if table_id and table_id.isdigit() else None,
        status=status,
        request=request,
    )
    if not result.get('success'):
        return JsonResponse({'success': False, 'message': result.get('message', 'Export failed.')}, status=404)
    response = FileResponse(result['archive'], as_attachment=True, filename=result['filename'])
    response['X-Desktop-Export-Count'] = str(result['media_count'])
    return response


@require_GET
@desktop_api_required
def download_original_file(request, file_path):
    normalized = DesktopAppService.resolve_download_path(file_path)
    if not normalized:
        raise Http404
    file_handle = settings.DEFAULT_FILE_STORAGE if False else None
    file_obj = None
    try:
        from django.core.files.storage import default_storage

        file_obj = default_storage.open(normalized, 'rb')
    except Exception:
        raise Http404
    return FileResponse(file_obj, as_attachment=True, filename=normalized.split('/')[-1])
