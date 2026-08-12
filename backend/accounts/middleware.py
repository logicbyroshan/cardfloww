import logging
from django.utils import timezone
from .models import UserDeviceSession

logger = logging.getLogger(__name__)

class DeviceSessionMiddleware:
    """
    Middleware to keep UserDeviceSession records in sync with user activity.
    Updates 'last_active' timestamp on every authenticated request.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # We only care about authenticated users with active sessions
        if request.user.is_authenticated and request.session.session_key:
            now = timezone.now()
            last_update = request.session.get('_last_device_session_update')

            # IMPROVED: Throttle updates to once every 60 seconds to reduce DB load
            if not last_update or (now.timestamp() - float(last_update)) > 60:
                try:
                    session_key = request.session.session_key
                    from accounts.signals import get_device_type, get_client_ip
                    device_type = get_device_type(request)

                    updated = UserDeviceSession.objects.filter(
                        session_key=session_key
                    ).update(
                        last_active=now,
                        device_type=device_type,
                        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                        ip_address=get_client_ip(request)
                    )
                    
                    if not updated:
                        # Re-create/heal the UserDeviceSession record if it doesn't exist
                        UserDeviceSession.objects.update_or_create(
                            session_key=session_key,
                            defaults={
                                'user': request.user,
                                'device_type': device_type,
                                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
                                'ip_address': get_client_ip(request),
                                'last_active': now
                            }
                        )
                    
                    request.session['_last_device_session_update'] = now.timestamp()

                    # Track mobile presence if it's a mobile client/assistant request
                    is_mobile = (
                        request.session.get('mobile_auth_ok') or
                        request.path.startswith('/api/mobile/') or
                        request.headers.get('X-Mobile-App') == 'true'
                    )
                    if is_mobile:
                        try:
                            from core.services.live_presence_service import LiveClientPresenceService
                            LiveClientPresenceService.record_event(
                                user=request.user,
                                session_key=request.session.session_key,
                                tab_id='mobile_app',
                                action='heartbeat'
                            )
                        except Exception as presence_err:
                            logger.error(f"Error updating mobile client presence session: {presence_err}")
                except Exception as e:
                    logger.error(f"Error updating device session activity: {e}")

        response = self.get_response(request)
        return response
