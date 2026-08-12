"""
Backward-compatible shim.
Canonical location: accounts/services_profile.py

New code should import directly from accounts.services_profile.
"""
from accounts.services_profile import UserProfileService  # noqa: F401
