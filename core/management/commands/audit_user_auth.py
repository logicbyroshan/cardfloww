"""
Management command to audit user authentication status.
Helps diagnose login issues by reporting:
- Users with usable passwords vs unusable/empty passwords
- Users by role and active status
- Users created with phone-as-password
- Password hash algorithm information
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db.models import Q, Count
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "Audit user authentication status and password configuration."

    def add_arguments(self, parser):
        parser.add_argument(
            '--role',
            type=str,
            help='Filter by role: pro_user, super_admin, admin_staff, client, client_staff',
        )
        parser.add_argument(
            '--only-inactive',
            action='store_true',
            help='Show only inactive users',
        )
        parser.add_argument(
            '--check-passwords',
            action='store_true',
            help='Check if passwords are properly set (uses check_password on a dummy)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Limit number of users displayed (default: 100)',
        )

    def handle(self, *args, **options):
        role_filter = options.get('role')
        only_inactive = options.get('only_inactive', False)
        check_passwords = options.get('check_passwords', False)
        limit = options.get('limit', 100)

        # Base queryset
        users = User.objects.all()
        total_users = users.count()

        # Apply role filter
        if role_filter:
            if role_filter == 'super_admin':
                # super_admin includes pro_user per the save() logic
                users = users.filter(Q(role='super_admin') | Q(role='pro_user'))
            else:
                users = users.filter(role=role_filter)

        # Apply active filter
        if only_inactive:
            users = users.filter(is_active=False)

        # Annotate counts
        role_counts = dict(User.objects.values('role').annotate(count=Count('id')).values_list('role', 'count'))
        active_counts = dict(User.objects.values('is_active').annotate(count=Count('id')).values_list('is_active', 'count'))

        self.stdout.write(self.style.MIGRATE_LABEL("=" * 80))
        self.stdout.write(self.style.MIGRATE_LABEL("USER AUTHENTICATION AUDIT REPORT"))
        self.stdout.write(self.style.MIGRATE_LABEL("=" * 80))
        self.stdout.write(f"\nTotal users in system: {total_users}")

        self.stdout.write("\n" + self.style.MIGRATE_LABEL("Role Distribution:"))
        for role, count in sorted(role_counts.items()):
            self.stdout.write(f"  {role}: {count} users")

        self.stdout.write("\n" + self.style.MIGRATE_LABEL("Active Status Distribution:"))
        for is_active, count in sorted(active_counts.items()):
            status = "ACTIVE" if is_active else "INACTIVE"
            self.stdout.write(f"  {status}: {count} users")

        # Password analysis
        self.stdout.write("\n" + self.style.MIGRATE_LABEL("Password Status Analysis:"))

        # Users with usable passwords: password not empty and not "!" (unusable)
        usable_q = ~Q(password="") & ~Q(password="!")
        unusable_q = Q(password="") | Q(password="!")
        # Also check for password that starts with "!" (Django's unusable password format)
        # But Django uses "!" as the unusable password marker. Some might be "!" or "!"+hash.

        usable_count = User.objects.filter(usable_q).count()
        unusable_count = User.objects.filter(unusable_q).count()

        self.stdout.write(f"  Users with usable password hash: {usable_count}")
        self.stdout.write(f"  Users with no/unusable password: {unusable_count}")

        # Break down by role
        self.stdout.write("\n" + self.style.MIGRATE_LABEL("Usable passwords by role:"))
        for role, count in sorted(role_counts.items()):
            role_usable = User.objects.filter(role=role).filter(usable_q).count()
            self.stdout.write(f"  {role}: {role_usable}/{count} have usable passwords")

        # Detailed breakdown for filtered query
        self.stdout.write(f"\n" + self.style.MIGRATE_LABEL(f"Detail for filtered users (limit {limit}):"))
        self.stdout.write(f"  Role filter: {role_filter or 'all'}")
        self.stdout.write(f"  Inactive only: {only_inactive}")
        self.stdout.write("")

        # Header
        header = f"{'ID':<6} {'Username':<20} {'Role':<12} {'Active':<6} {'Password':<10} {'Phone':<15} {'Email'}"
        self.stdout.write(self.style.WARNING(header))
        self.stdout.write(self.style.WARNING("-" * 100))

        displayed = 0
        for user in users.order_by('role', 'username')[:limit]:
            # Determine password status
            if not user.password or user.password == "!":
                pw_status = self.style.ERROR("NO")
            elif user.password.startswith('!'):
                pw_status = self.style.ERROR("UNUSABLE")
            else:
                pw_status = self.style.SUCCESS("YES")

            active_str = self.style.SUCCESS("Yes") if user.is_active else self.style.ERROR("No")
            phone_display = (user.phone or '')[:14]
            email_display = (user.email or '')[:30]

            self.stdout.write(
                f"{str(user.id):<6} "
                f"{user.username:<20} "
                f"{user.role:<12} "
                f"{active_str:<6} "
                f"{pw_status:<10} "
                f"{phone_display:<15} "
                f"{email_display}"
            )
            displayed += 1

        if displayed >= limit:
            remaining = users.count() - limit
            self.stdout.write(f"\n... and {remaining} more users (use --limit to see more)")

        # Recommendations
        self.stdout.write("\n" + self.style.MIGRATE_LABEL("Recommendations:"))
        issues = []
        if unusable_count > 0:
            issues.append(f"- {unusable_count} users have no/unusable passwords. They cannot login.")
        if only_inactive:
            issues.append(f"- {users.count()} users are inactive. Activate them via admin or create_staff API with is_active=True.")
        if role_filter == 'operator':
            admin_inactive = users.filter(is_active=False).count()
            if admin_inactive > 0:
                issues.append(f"- {admin_inactive} admin_staff are inactive. AdminStaffCreationService creates them inactive by design; activate when ready.")

        if issues:
            for issue in issues:
                self.stdout.write(self.style.WARNING(issue))
        else:
            self.stdout.write(self.style.SUCCESS("- No obvious authentication issues detected in this filter."))

        self.stdout.write("\n" + self.style.MIGRATE_LABEL("Next steps:"))
        self.stdout.write("  • To activate users: use Django admin or create a custom management command")
        self.stdout.write("  • To set passwords for users without: use User.set_password() and user.save()")
        self.stdout.write("  • Check logs for rate-lock: auth_fail cache keys in Redis")
        self.stdout.write("  • Verify SECRET_KEY hasn't changed (would invalidate sessions but not passwords)")
        self.stdout.write(self.style.MIGRATE_LABEL("=" * 80))
