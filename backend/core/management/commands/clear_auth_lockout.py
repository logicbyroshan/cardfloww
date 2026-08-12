"""
Management command to clear rate-lock for a login identifier.
Allows admins to unlock users who are blocked due to too many failed login attempts.
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache
import sys

from accounts.services import _auth_fail_cache_key, _auth_fail_notify_cache_key

class Command(BaseCommand):
    help = "Clear rate-lock for a login identifier (email/username/phone)."

    def add_arguments(self, parser):
        parser.add_argument(
            'identifier',
            type=str,
            help='Email, username, or phone number to unlock',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Clear ALL auth failure locks (use with caution)',
        )

    def handle(self, *args, **options):
        identifier = options.get('identifier', '').strip()
        clear_all = options.get('all', False)

        if clear_all:
            # Dangerous but useful in emergencies
            try:
                # Only works if cache backend supports keys iteration
                if hasattr(cache, 'client'):
                    redis_client = cache.client.get_client()
                    pattern = f"auth_fail:*"
                    keys = list(redis_client.scan_iter(match=pattern, count=1000))
                    count = len(keys)
                    if count > 0:
                        for key in keys:
                            redis_client.delete(key)
                        self.stdout.write(self.style.SUCCESS(f"Cleared {count} auth_fail lockouts"))
                    else:
                        self.stdout.write("No auth_fail lockouts found")
                else:
                    self.stderr.write(self.style.ERROR("Cannot clear all: cache backend does not support key iteration. Use Redis in production."))
                    sys.exit(1)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error clearing all locks: {e}"))
                sys.exit(1)
        else:
            if not identifier:
                self.stderr.write(self.style.ERROR("Identifier is required (or use --all)"))
                sys.exit(1)

            key = _auth_fail_cache_key(identifier)
            notify_key = _auth_fail_notify_cache_key(identifier)
            deleted1 = cache.delete(key)
            deleted2 = cache.delete(notify_key)
            self.stdout.write(self.style.SUCCESS(f"Cleared lockout for '{identifier}'"))
            self.stdout.write(f"  auth_fail key deleted: {deleted1}")
            self.stdout.write(f"  notify key deleted: {deleted2}")
