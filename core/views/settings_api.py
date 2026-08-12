"""
Settings API Views
==================
Profile management views for all user roles.

Architecture rule: Views are ULTRA-THIN.
  - Validate request (parse POST/FILES/JSON)
  - Call UserProfileService method
  - Return JsonResponse
  - NO .save(), .set_password(), os.remove() — all in service layer
"""
import json
import logging
import time
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash

from core.services.user_profile_service import UserProfileService
from core.services.permission_service import api_require_any_authenticated
from accounts.rate_limit import rate_limit

logger = logging.getLogger(__name__)


@api_require_any_authenticated
@require_http_methods(["GET"])
def api_get_profile(request):
    """Get current user's profile data."""
    user = request.user
    profile = UserProfileService.get_profile(user, request)
    security_settings = UserProfileService.get_security_settings(user)
    super_mode = {}
    profile['security_settings'] = security_settings
    profile['super_mode'] = super_mode
    return JsonResponse({'success': True, 'profile': profile})


@api_require_any_authenticated
@require_http_methods(["POST"])
def api_update_profile(request):
    """Update current user's profile data."""
    try:
        data = json.loads(request.body)
        success, message, profile_data = UserProfileService.update_profile(request.user, data, request=request)
        if not success:
            return JsonResponse({'success': False, 'message': message})
        return JsonResponse({
            'success': True,
            'message': message,
            'profile': profile_data,
        })
    except Exception as e:
        logger.exception("Settings API error (update_profile): %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'})


@api_require_any_authenticated
@require_http_methods(["POST"])
@rate_limit(max_requests=5, window_seconds=300, key_prefix='password_change')
def api_change_password(request):
    """Change current user's password."""
    try:
        data = json.loads(request.body)
        success, message = UserProfileService.change_password(
            request.user,
            data.get('current_password'),
            data.get('new_password'),
            current_session_key=request.session.session_key,
        )
        if success:
            update_session_auth_hash(request, request.user)
        return JsonResponse({'success': success, 'message': message})
    except Exception as e:
        logger.exception("Settings API error (change_password): %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'})


@api_require_any_authenticated
@require_http_methods(["POST"])
@rate_limit(max_requests=20, window_seconds=60, key_prefix='security_settings')
def api_update_security_settings(request):
    """Persist current user's security preference toggles."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    try:
        success, message, security_settings = UserProfileService.update_security_settings(request.user, data)
        if not success:
            return JsonResponse({'success': False, 'message': message}, status=400)

        timeout_minutes = int(security_settings.get('session_timeout_minutes') or 0)
        request.session['_user_idle_timeout_seconds'] = max(timeout_minutes, 0) * 60
        request.session['_last_activity'] = time.time()

        return JsonResponse({
            'success': True,
            'message': message,
            'security_settings': security_settings,
        })
    except Exception as e:
        logger.exception("Settings API error (update_security_settings): %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'})


@api_require_any_authenticated
@require_http_methods(["POST"])
@rate_limit(max_requests=30, window_seconds=60, key_prefix='super_mode_toggle')
def api_toggle_super_mode(request):
    """Toggle runtime Super Mode state for the currently authenticated user."""
    try:
        data = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)

    enabled = False

    try:
        status_payload = {}
        return JsonResponse({
            'success': True,
            'message': 'Super Mode updated successfully.',
            'super_mode': status_payload,
        })
    except PermissionError as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=403)
    except ValueError as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=400)
    except Exception as e:
        logger.exception("Settings API error (toggle_super_mode): %s", e)
        return JsonResponse({'success': False, 'message': 'Failed to update Super Mode'}, status=500)


@api_require_any_authenticated
@require_http_methods(["POST"])
@rate_limit(max_requests=10, window_seconds=60, key_prefix='profile_image')
def api_upload_profile_image(request):
    """Upload profile image."""
    try:
        success, message, image_url = UserProfileService.upload_profile_image(
            request.user,
            request.FILES.get('profile_image'),
        )
        response = {'success': success, 'message': message}
        if image_url:
            response['image_url'] = image_url
        return JsonResponse(response)
    except Exception as e:
        logger.exception("Settings API error (upload_profile_image): %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'})


@api_require_any_authenticated
@require_http_methods(["POST"])
def api_remove_profile_image(request):
    """Remove profile image."""
    try:
        success, message = UserProfileService.remove_profile_image(request.user)
        return JsonResponse({'success': success, 'message': message})
    except Exception as e:
        logger.exception("Settings API error (remove_profile_image): %s", e)
        return JsonResponse({'success': False, 'message': 'An error occurred'})



__all__ = [
    'api_get_profile',
    'api_update_profile',
    'api_change_password',
    'api_update_security_settings',
    'api_toggle_super_mode',
    'api_upload_profile_image',
    'api_remove_profile_image',
]

