"""
Management command to list users without usable passwords.
These users exist in the database but cannot authenticate because:
- password field is empty, or
- password is set to unusable marker ("!"), or
- user.is_active=False

Useful for onboarding audit and fixing broken signup flows.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

class Command(BaseCommand):
    help = "List users without usable passwords (cannot login)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--include-active',
            action='store_true',
            help='Include active users who nonetheless have no/unusable password',
        )
        parser.add_argument(
            '--role',
            type=str,
            choices=['pro_user', 'super_admin', 'operator'],
            help='Filter by role',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Generate random passwords for users without (dry-run by default)',
        )
        parser.add_argument(
            '--execute',
            action='store_true',
            help='Actually execute the fixes (only works with --fix)',
        )

    def handle(self, *args, **options):
        include_active = options.get('include_active', False)
        role_filter = options.get('role')
        fix_mode = options.get('fix', False)
        execute = options.get('execute', False)

        # Query users with empty or unusable password
        base_qs = User.objects.filter(
            Q(password="") | Q(password="!") | Q(password__startswith="!")
        )
        if not include_active:
            # By default, focus on users who are inactive too (likely never activated)
            base_qs = base_qs.filter(is_active=False)

        if role_filter:
            if role_filter == 'super_admin':
                base_qs = base_qs.filter(Q(role='super_admin') | Q(role='pro_user'))
            else:
                base_qs = base_qs.filter(role=role_filter)

        users = base_qs.order_by('role', 'username')

        if not users.exists():
            self.stdout.write(self.style.SUCCESS("[OK] No users found without usable passwords."))
            return

        self.stdout.write(self.style.ERROR(f"[!] Found {users.count()} user(s) without usable passwords:\n"))
        for u in users:
            status = "ACTIVE" if u.is_active else "INACTIVE"
            color = self.style.SUCCESS if u.is_active else self.style.ERROR
            self.stdout.write(
                f"ID: {u.id} | {u.role:<12} | {color(status)} | {u.username} | {u.email or 'no email'} | {u.phone or 'no phone'}"
            )

        if fix_mode:
            self.stdout.write("\n" + self.style.WARNING("Fix mode: generate secure random passwords for these users."))
            if not execute:
                self.stdout.write(self.style.WARNING("  DRY RUN — passwords will NOT be saved. Add --execute to apply."))
            else:
                self.stdout.write(self.style.ERROR("  EXECUTE mode — passwords will be saved and emails will be sent!"))
                confirm = input("Type 'yes' to confirm: ").strip().lower()
                if confirm != 'yes':
                    self.stdout.write("Aborted.")
                    return

                from django.contrib.auth.tokens import default_token_generator
                from core.utils.email_utils import send_welcome_email
                from django.utils import timezone
                import secrets
                import string

                fixed = 0
                for user in users:
                    # Generate a secure random 12-char password
                    alphabet = string.ascii_letters + string.digits
                    new_password = ''.join(secrets.choice(alphabet) for _ in range(12))
                    user.set_password(new_password)
                    user.save()
                    fixed += 1
                    self.stdout.write(f"  ✓ Set new password for {user.username}")

                    # Send welcome email if email exists
                    if user.email and '@' in user.email and not user.email.endswith('@noemail.local'):
                        try:
                            send_welcome_email(
                                name=user.get_full_name() or user.username,
                                email=user.email,
                                password=new_password,
                                role=user.role,
                                phone=user.phone or '',
                            )
                            self.stdout.write(f"    → Welcome email sent to {user.email}")
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"    → Failed to send email: {e}"))

                self.stdout.write(self.style.SUCCESS(f"\n✅ Fixed {fixed} user(s) successfully."))

        self.stdout.write("\n" + self.style.MIGRATE_LABEL("Recommendations:"))
        self.stdout.write("  • To fix: run with --fix --execute to generate and set random passwords")
        self.stdout.write("  • To activate: update is_active=True via Django admin or a data migration")
        self.stdout.write("  • To see full user audit: python manage.py audit_user_auth")
        self.stdout.write("  • Check auth lockouts: python manage.py check_auth_lockout '<identifier>'")
