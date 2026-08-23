import os
import sys
import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

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
