import os
import sys
import django

# Setup django environment
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction
from organisation.models import Organisation
from operators.models import Operator
from assistants.models import Assistant
from core.models import Photographer, PhotographerAssignment

User = get_user_model()


def seed_database():
    print("=== Seeding Clean Database ===")
    with transaction.atomic():
        # 1. Super Admin Account
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@cardfloww.com',
                'first_name': 'Super',
                'last_name': 'Admin',
                'role': 'super_admin',
                'is_staff': True,
                'is_superuser': True,
                'is_active': True,
            }
        )
        admin_user.email = 'admin@cardfloww.com'
        admin_user.role = 'super_admin'
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.is_active = True
        admin_user.set_password('admin123')
        admin_user.save()
        print(f"[{'CREATED' if created else 'UPDATED'}] Super Admin: admin (admin@cardfloww.com) / admin123")

        # 2. Demo Organisation & Prime Manager
        org_user, created = User.objects.get_or_create(
            username='org_admin',
            defaults={
                'email': 'org@cardfloww.com',
                'first_name': 'Apex',
                'last_name': 'Academy',
                'role': 'prime_manager',
                'is_active': True,
            }
        )
        org_user.email = 'org@cardfloww.com'
        org_user.role = 'prime_manager'
        org_user.is_active = True
        org_user.set_password('password123')
        org_user.save()
        print(f"[{'CREATED' if created else 'UPDATED'}] Prime Manager: org_admin (org@cardfloww.com) / password123")

        org, org_created = Organisation.objects.get_or_create(
            user=org_user,
            defaults={
                'name': 'Apex International Academy',
                'image_folder_code': 'APEXI',
                'status': 'active',
                'city': 'Bhopal',
                'state': 'Madhya Pradesh',
                'pincode': '462001',
                'org_type': 'school',
            }
        )
        print(f"[{'CREATED' if org_created else 'EXISTS'}] Organisation: {org.name} (Code: {org.image_folder_code})")

        # 3. Demo Staff Operator
        op_user, created = User.objects.get_or_create(
            username='operator',
            defaults={
                'email': 'operator@cardfloww.com',
                'first_name': 'Staff',
                'last_name': 'Operator',
                'role': 'operator',
                'is_active': True,
            }
        )
        op_user.email = 'operator@cardfloww.com'
        op_user.role = 'operator'
        op_user.is_active = True
        op_user.set_password('password123')
        op_user.save()

        op_profile, _ = Operator.objects.get_or_create(
            user=op_user,
            defaults={
                'designation': 'Senior Production Operator',
                'department': 'Card Production',
                'perm_idcard_client_list': True,
                'perm_manage_assistant': True,
                'perm_manage_photographer_staff': True,
                'perm_idcard_setting_list': True,
                'perm_idcard_setting_add': True,
                'perm_idcard_setting_edit': True,
                'perm_idcard_setting_delete': True,
                'perm_idcard_setting_status': True,
                'perm_idcard_pending_list': True,
                'perm_idcard_verified_list': True,
                'perm_idcard_pool_list': True,
                'perm_idcard_approved_list': True,
                'perm_idcard_download_list': True,
                'perm_idcard_reprint_list': True,
                'perm_reprint_request_list': True,
                'perm_confirmed_list': True,
                'perm_idcard_add': True,
                'perm_idcard_edit': True,
                'perm_idcard_delete': True,
                'perm_idcard_info': True,
                'perm_idcard_approve': True,
                'perm_idcard_verify': True,
                'perm_idcard_updated_at': True,
                'perm_idcard_delete_from_pool': True,
                'perm_idcard_clear_pending_path': True,
                'perm_reupload_idcard_image': True,
                'perm_idcard_retrieve': True,
            }
        )
        op_profile.assigned_organisations.add(org)
        print(f"[{'CREATED' if created else 'UPDATED'}] Operator: operator (operator@cardfloww.com) / password123")

        # 4. Demo Assistant
        ast_user, created = User.objects.get_or_create(
            username='assistant',
            defaults={
                'email': 'assistant@cardfloww.com',
                'first_name': 'Data',
                'last_name': 'Assistant',
                'role': 'assistant',
                'is_active': True,
            }
        )
        ast_user.email = 'assistant@cardfloww.com'
        ast_user.role = 'assistant'
        ast_user.is_active = True
        ast_user.set_password('password123')
        ast_user.save()

        ast_profile, _ = Assistant.objects.get_or_create(
            user=ast_user,
            defaults={
                'organisation': org,
                'manager': org_user,
            }
        )
        print(f"[{'CREATED' if created else 'UPDATED'}] Assistant: assistant (assistant@cardfloww.com) / password123")

        # 5. Demo Photographer
        photo_user, created = User.objects.get_or_create(
            username='photographer',
            defaults={
                'email': 'photographer@cardfloww.com',
                'first_name': 'Studio',
                'last_name': 'Photographer',
                'role': 'photographer',
                'is_active': True,
            }
        )
        photo_user.email = 'photographer@cardfloww.com'
        photo_user.role = 'photographer'
        photo_user.is_active = True
        photo_user.set_password('password123')
        photo_user.save()

        photo_profile, _ = Photographer.objects.get_or_create(
            user=photo_user,
            defaults={
                'department': 'Photography',
                'designation': 'Field Photographer',
                'perm_mobile_app': True,
            }
        )
        PhotographerAssignment.objects.get_or_create(
            photographer=photo_profile,
            client=org,
        )
        print(f"[{'CREATED' if created else 'UPDATED'}] Photographer: photographer (photographer@cardfloww.com) / password123")

    print("\n=== All clean seed accounts created successfully! ===")


if __name__ == '__main__':
    seed_database()
