"""
Management command to list users whose password matches their phone number.
Helps admins audit how many users use phone-as-password (the default when
no custom password is provided during user creation).

Usage:
    python manage.py audit_phone_passwords
    python manage.py audit_phone_passwords --role client
    python manage.py audit_phone_passwords --role admin_staff --only-active
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db.models import Q
from accounts.services import normalize_password_input

User = get_user_model()


class Command(BaseCommand):
    help = "List users whose password matches their phone number."

    def add_arguments(self, parser):
        parser.add_argument(
            '--role',
            type=str,
            choices=['pro_user', 'super_admin', 'operator'],
            help='Filter by role',
        )
        parser.add_argument(
            '--only-active',
            action='store_true',
            help='Show only active users',
        )
        parser.add_argument(
            '--only-inactive',
            action='store_true',
            help='Show only inactive users',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=200,
            help='Limit number of users checked (default: 200)',
        )

    def handle(self, *args, **options):
        role_filter = options.get('role')
        only_active = options.get('only_active', False)
        only_inactive = options.get('only_inactive', False)
        limit = options.get('limit', 200)

        # Base queryset: users that have a phone number
        qs = User.objects.exclude(phone__isnull=True).exclude(phone__exact='')

        if role_filter:
            if role_filter == 'super_admin':
                qs = qs.filter(Q(role='super_admin') | Q(role='pro_user'))
            else:
                qs = qs.filter(role=role_filter)

        if only_active:
            qs = qs.filter(is_active=True)
        elif only_inactive:
            qs = qs.filter(is_active=False)

        total_with_phone = qs.count()
        qs = qs.order_by('role', 'username')[:limit]

        self.stdout.write(self.style.MIGRATE_LABEL("=" * 90))
        self.stdout.write(self.style.MIGRATE_LABEL("PHONE-AS-PASSWORD AUDIT REPORT"))
        self.stdout.write(self.style.MIGRATE_LABEL("=" * 90))
        self.stdout.write(f"\nUsers with phone number: {total_with_phone}")
        self.stdout.write(f"Checking up to {limit} users...\n")

        phone_password_users = []
        custom_password_users = []
        unusable_password_users = []
        invalid_phone_users = []
        checked = 0

        for user in qs:
            checked += 1
            phone = (user.phone or '').strip()
            if not phone:
                continue

            normalized_phone = normalize_password_input(phone)
            if not normalized_phone or len(normalized_phone) < 6:
                invalid_phone_users.append((user, normalized_phone))
                continue

            if not user.has_usable_password():
                unusable_password_users.append(user)
                continue

            # Use normalized phone to match current login/reset behavior.
            if user.check_password(normalized_phone):
                phone_password_users.append(user)
            else:
                custom_password_users.append(user)

        # Summary
        self.stdout.write(self.style.MIGRATE_LABEL("Summary:"))
        self.stdout.write(
            self.style.WARNING(f"  Phone as password:   {len(phone_password_users)} users")
        )
        self.stdout.write(
            self.style.SUCCESS(f"  Custom password:     {len(custom_password_users)} users")
        )
        self.stdout.write(
            self.style.ERROR(f"  Unusable password:   {len(unusable_password_users)} users")
        )
        self.stdout.write(
            self.style.WARNING(f"  Invalid phone data:  {len(invalid_phone_users)} users")
        )
        self.stdout.write(f"  Total checked:       {checked}")

        # Breakdown by role
        self.stdout.write("\n" + self.style.MIGRATE_LABEL("Phone-as-password by role:"))
        role_counts = {}
        for u in phone_password_users:
            role_counts[u.role] = role_counts.get(u.role, 0) + 1
        if role_counts:
            for role, count in sorted(role_counts.items()):
                self.stdout.write(f"  {role}: {count}")
        else:
            self.stdout.write("  (none)")

        # Detail table
        if phone_password_users:
            self.stdout.write("\n" + self.style.MIGRATE_LABEL("Users with phone as password:"))
            header = f"{'ID':<6} {'Username':<22} {'Role':<14} {'Active':<7} {'Phone':<16} {'Email'}"
            self.stdout.write(self.style.WARNING(header))
            self.stdout.write(self.style.WARNING("-" * 90))

            for user in phone_password_users:
                active_str = self.style.SUCCESS("Yes") if user.is_active else self.style.ERROR("No")
                phone_display = (user.phone or '')[:15]
                email_display = (user.email or '')[:30]
                self.stdout.write(
                    f"{str(user.id):<6} "
                    f"{user.username:<22} "
                    f"{user.role:<14} "
                    f"{active_str:<7} "
                    f"{phone_display:<16} "
                    f"{email_display}"
                )

        if unusable_password_users:
            self.stdout.write("\n" + self.style.MIGRATE_LABEL("Users with unusable passwords:"))
            for user in unusable_password_users[:20]:
                self.stdout.write(
                    f"  ID: {user.id} | {user.role:<14} | {user.username} | {user.phone or 'no phone'}"
                )
            if len(unusable_password_users) > 20:
                self.stdout.write(f"  ... and {len(unusable_password_users) - 20} more")

        if invalid_phone_users:
            self.stdout.write("\n" + self.style.MIGRATE_LABEL("Users with invalid phone format for password policy:"))
            for user, normalized_phone in invalid_phone_users[:20]:
                self.stdout.write(
                    f"  ID: {user.id} | {user.role:<14} | {user.username} | raw={user.phone or 'no phone'} | norm={normalized_phone or 'empty'}"
                )
            if len(invalid_phone_users) > 20:
                self.stdout.write(f"  ... and {len(invalid_phone_users) - 20} more")

        if checked >= limit and total_with_phone > limit:
            self.stdout.write(
                f"\n⚠ Only checked {limit} of {total_with_phone} users. "
                f"Use --limit {total_with_phone} to check all."
            )

        self.stdout.write("\n" + self.style.MIGRATE_LABEL("Recommendations:"))
        if phone_password_users:
            self.stdout.write(
                self.style.WARNING(
                    f"  • {len(phone_password_users)} users use their phone number as password. "
                    "Consider notifying them to set a custom password."
                )
            )
        if unusable_password_users:
            self.stdout.write(
                self.style.ERROR(
                    f"  • {len(unusable_password_users)} users cannot login (unusable password). "
                    "Use 'manage.py list_users_without_passwords --fix' to repair."
                )
            )
        if not phone_password_users and not unusable_password_users:
            self.stdout.write(self.style.SUCCESS("  ✓ All checked users have custom passwords."))

        self.stdout.write(self.style.MIGRATE_LABEL("=" * 90))
