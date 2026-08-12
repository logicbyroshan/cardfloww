import uuid
import json
from django.core.cache import cache

def create_credential_token(email, password, role):
    """
    Creates a secure, one-time token for viewing credentials.
    Stores the data in cache for 24 hours.
    """
    token = str(uuid.uuid4())
    cache_key = f"secure_cred_{token}"
    
    data = {
        'email': email.lower().strip(),
        'password': password,
        'role': role
    }
    
    # Store for 24 hours (86400 seconds)
    cache.set(cache_key, json.dumps(data), timeout=86400)
    return token

def verify_credential_token(token, user_email):
    """
    Verifies the token and email.
    If valid, returns the password and burns the token (one-time use).
    Returns None if invalid.
    """
    if not token or not user_email:
        return None
        
    cache_key = f"secure_cred_{token}"
    data_json = cache.get(cache_key)
    
    if not data_json:
        return None
        
    try:
        data = json.loads(data_json)
        # Check if email matches (case insensitive)
        if data.get('email') == user_email.lower().strip():
            # Burn the token after successful view
            cache.delete(cache_key)
            return data.get('password')
    except Exception:
        pass
        
    return None
