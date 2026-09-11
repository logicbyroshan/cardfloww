"""
DEV-ONLY SCRIPT — create_admin.py
==================================
Creates or resets a local admin/super_admin account for development purposes.

WARNING: This script uses a hardcoded password and must NEVER be run in production.
It will refuse to execute if DEBUG=False (production environment).

Usage: python scripts/create_admin.py
"""
import os
import sys
import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# --- Production guard ---
from django.conf import settings as _settings
if not getattr(_settings, 'DEBUG', False):
    print('=' * 60)
    print('ERROR: This script is for DEVELOPMENT use only.')
    print('DEBUG=False detected — refusing to run in production.')
    print('=' * 60)
    sys.exit(1)

print('WARNING: DEV-ONLY script — creating admin account with hardcoded password.')
print('Do NOT use this script in production.\n')

from django.contrib.auth import get_user_model

User = get_user_model()

username = 'admin'
email = 'admin@cardfloww.com'
password = 'admin123'

u = User.objects.filter(username=username).first()
if u:
    u.email = email
    u.is_staff = True
    u.is_superuser = True
    u.role = 'super_admin'
    u.set_password(password)
    u.save()
    print(f'Admin user "{username}" updated successfully with password "{password}".')
else:
    u = User.objects.create_superuser(username, email, password)
    print(f'Admin user "{username}" created successfully with password "{password}".')
