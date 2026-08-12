from django.core.management.base import BaseCommand
from django.db.models import Q

from core.models import EmailLog, User
from core.utils import generate_secure_password, send_welcome_email
from staff.models import Staff


class Command(BaseCommand):
    help = (
        'Backfill welcome emails for assistant accounts (client_staff) that have not yet '
        'received credentials email.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Actually send emails and update records. Default is dry-run.',
        )
        parser.add_argument(
            '--include-inactive',
            action='store_true',
            default=False,
            help='Include inactive assistant accounts. Default processes active assistants only.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Process at most N assistants (0 means no limit).',
        )

    def handle(self, *args, **options):
        apply_changes = bool(options.get('apply'))
        include_inactive = bool(options.get('include_inactive'))
        limit = max(int(options.get('limit') or 0), 0)

        mode = 'APPLY' if apply_changes else 'DRY-RUN'
        self.stdout.write(f'\n=== backfill_assistant_welcome_emails ({mode}) ===')

        unsent_qs = Staff.objects.select_related('user').filter(
            staff_type='assistant',
            user__role='client_staff',
            user__welcome_email_sent=False,
        )

        missing_email_filter = (
            Q(user__email__isnull=True)
            | Q(user__email__exact='')
            | Q(user__email__iendswith='@noemail.local')
        )

        total_unsent = unsent_qs.count()
        total_missing_email = unsent_qs.filter(missing_email_filter).count()
        total_inactive = unsent_qs.filter(user__is_active=False).count()

        eligible_qs = unsent_qs.exclude(missing_email_filter)
        if not include_inactive:
            eligible_qs = eligible_qs.filter(user__is_active=True)

        eligible_qs = eligible_qs.order_by('id')
        if limit > 0:
            eligible_qs = eligible_qs[:limit]

        eligible = list(eligible_qs)

        self.stdout.write(f'Unsent assistant accounts: {total_unsent}')
        self.stdout.write(f'Skipped due to missing/placeholder email: {total_missing_email}')
        if not include_inactive:
            self.stdout.write(f'Skipped due to inactive status: {total_inactive}')
        self.stdout.write(f'Eligible to process now: {len(eligible)}')

        if not eligible:
            self.stdout.write(self.style.WARNING('No eligible assistants found.'))
            return

        if not apply_changes:
            self.stdout.write('')
            self.stdout.write('Dry-run preview (first 20):')
            for staff in eligible[:20]:
                user = staff.user
                display_name = user.get_full_name().strip() or user.username
                self.stdout.write(f'  - staff_id={staff.id}, user_id={user.id}, email={user.email}, name={display_name}')
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Dry-run only. Re-run with --apply to send emails.'))
            return

        processed = 0
        sent_count = 0
        failed_count = 0
        restored_password_count = 0

        for staff in eligible:
            processed += 1
            user = staff.user
            display_name = user.get_full_name().strip() or user.username
            original_password_hash = user.password
            new_password = generate_secure_password()

            user.set_password(new_password)
            user.save(update_fields=['password'])

            email_sent, message = send_welcome_email(
                name=display_name,
                email=user.email,
                password=new_password,
                role='client_staff',
                phone=user.phone or '',
                request=None,
                email_variant='temp_password',
            )

            if email_sent:
                User.objects.filter(pk=user.pk).update(welcome_email_sent=True)
                EmailLog.objects.create(
                    recipient_name=display_name,
                    recipient_email=user.email,
                    subject='Your Temporary Password - Adarsh Admin',
                    email_type=EmailLog.EMAIL_TYPE_TEMP_PASSWORD,
                    status=EmailLog.STATUS_SENT,
                    error_message='',
                )
                sent_count += 1
                self.stdout.write(self.style.SUCCESS(f'SENT: {user.email}'))
                continue

            User.objects.filter(pk=user.pk).update(password=original_password_hash)
            restored_password_count += 1
            failed_count += 1

            EmailLog.objects.create(
                recipient_name=display_name,
                recipient_email=user.email,
                subject='Your Temporary Password - Adarsh Admin',
                email_type=EmailLog.EMAIL_TYPE_TEMP_PASSWORD,
                status=EmailLog.STATUS_FAILED,
                error_message=(message or 'Failed to send temporary password email.'),
            )
            self.stdout.write(self.style.ERROR(f'FAILED: {user.email} ({message})'))

        self.stdout.write('')
        self.stdout.write(f'Processed: {processed}')
        self.stdout.write(self.style.SUCCESS(f'Sent: {sent_count}'))
        self.stdout.write(self.style.ERROR(f'Failed: {failed_count}'))
        self.stdout.write(f'Password restored on failure: {restored_password_count}')
