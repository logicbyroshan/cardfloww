"""
Management command: create_pro_user
====================================
Creates the single Pro User account.
Only one Pro User can exist in the system.

Usage:
    python manage.py create_pro_user --email admin@example.com --password SecurePass123
    python manage.py create_pro_user --email admin@example.com  (prompts for password)
"""
import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Create the single Pro User account (max 1 allowed).'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='Email address for the Pro User')
        parser.add_argument('--username', default=None, help='Username (defaults to email prefix)')
        parser.add_argument('--password', default=None, help='Password (will prompt if not provided)')
        parser.add_argument('--first-name', default='Pro', help='First name')
        parser.add_argument('--last-name', default='User', help='Last name')

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        username = options['username'] or email.split('@')[0]
        first_name = options['first_name']
        last_name = options['last_name']

        # Check if a Pro User already exists
        existing = User.objects.filter(role='pro_user').first()
        if existing:
            raise CommandError(
                f'A Pro User already exists: {existing.username} ({existing.email}). '
                'Only one Pro User is allowed.'
            )

        # Check if email is already taken
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f'A user with email {email} already exists.')

        # Check if username is already taken
        if User.objects.filter(username=username).exists():
            raise CommandError(f'A user with username "{username}" already exists.')

        # Get password
        password = options['password']
        if not password:
            password = getpass.getpass('Password: ')
            password2 = getpass.getpass('Confirm password: ')
            if password != password2:
                raise CommandError('Passwords do not match.')

        if len(password) < 8:
            raise CommandError('Password must be at least 8 characters.')

        # Create the Pro User
        user = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role='pro_user',
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )
        user.set_password(password)
        user.save()

        self.stdout.write(self.style.SUCCESS(
            f'Pro User created successfully:\n'
            f'  Username: {user.username}\n'
            f'  Email:    {user.email}\n'
            f'  Role:     {user.get_role_display()}\n'
            f'\nLogin at the panel using this email and password.'
        ))
