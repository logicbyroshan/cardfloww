from typing import Dict, Any, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class CompatibilityService:
    @staticmethod
    def get_client_info(request) -> Dict[str, Any]:
        """
        Detect platform and version from headers.
        Expected headers:
          X-App-Platform: 'android' | 'desktop' | 'web'
          X-App-Version: SemVer string (e.g. '1.0.82')
        Also parses User-Agent fallback.
        """
        platform = request.headers.get('X-App-Platform', '').lower()
        if not platform:
            platform = request.META.get('HTTP_X_APP_PLATFORM', '').lower()
            
        version_str = request.headers.get('X-App-Version', '')
        if not version_str:
            version_str = request.META.get('HTTP_X_APP_VERSION', '')

        # Fallback to User-Agent parsing
        user_agent = request.headers.get('User-Agent', '') or request.META.get('HTTP_USER_AGENT', '')
        if not platform:
            ua_lower = user_agent.lower()
            if 'okhttp' in ua_lower or 'android' in ua_lower:
                platform = 'android'
            elif 'electron' in ua_lower or 'desktop-client' in ua_lower:
                platform = 'desktop'
            else:
                platform = 'web'

        # Check if legacy based on version limits
        # For legacy mobile clients: any mobile app that doesn't explicitly send X-App-Version or is < 2.0.0
        is_legacy = True
        if version_str:
            try:
                parts = [int(p) for p in version_str.split('.') if p.isdigit()]
                if parts and parts[0] >= 2:
                    is_legacy = False
            except ValueError:
                pass
        
        return {
            'platform': platform,
            'version': version_str or '1.0.0',
            'is_legacy': is_legacy
        }

    @staticmethod
    def map_role_to_legacy(role: str) -> str:
        """Map new internal roles to legacy client role strings."""
        if role == 'operator':
            return 'admin_staff'
        if role == 'assistant':
            return 'client_staff'
        return role

    @staticmethod
    def map_role_from_legacy(role: str) -> str:
        """Map incoming legacy roles to new internal database role strings."""
        if role == 'admin_staff':
            return 'operator'
        if role == 'client_staff':
            return 'assistant'
        return role

    @staticmethod
    def decode_id(wrapped_id: Any) -> Tuple[str, int]:
        """
        Decodes a wrapped compatibility ID to determine staff_type and real database ID.
        100000+ -> Operator
        200000+ -> Assistant
        """
        try:
            val = int(wrapped_id)
        except (ValueError, TypeError):
            return 'unknown', 0

        if val >= 200000:
            return 'assistant', (val - 200000)
        elif val >= 100000:
            return 'operator', (val - 100000)
        return 'unknown', val

    @staticmethod
    def encode_id(real_id: int, role: str) -> int:
        """Wraps a database ID with offsets to maintain uniqueness for legacy clients."""
        if role in ('operator', 'admin_staff'):
            return real_id + 100000
        if role in ('assistant', 'client_staff'):
            return real_id + 200000
        return real_id

    @classmethod
    def translate_dict(cls, data: Any) -> Any:
        """Recursively translates dictionary roles and IDs for legacy responses."""
        if isinstance(data, dict):
            new_dict = {}
            for k, v in data.items():
                if k == 'role' and isinstance(v, str):
                    new_dict[k] = cls.map_role_to_legacy(v)
                elif k == 'role_display' and isinstance(v, str):
                    if v.lower() == 'operator':
                        new_dict[k] = 'Operator'
                    elif v.lower() == 'assistant':
                        new_dict[k] = 'Assistent'
                    else:
                        new_dict[k] = v
                else:
                    new_dict[k] = cls.translate_dict(v)
            return new_dict
        elif isinstance(data, list):
            return [cls.translate_dict(item) for item in data]
        return data
