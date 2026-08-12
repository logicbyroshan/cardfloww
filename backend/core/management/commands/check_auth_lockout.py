"""
Management command to check if an identifier is currently rate-locked from login.
Shows remaining lockout time and failed attempt count.
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.utils import timezone
import hashlib
import sys

from accounts.services import _auth_fail_cache_key, AUTH_FAIL_MAX_ATTEMPTS, AUTH_FAIL_WINDOW_SECONDS

class Command(BaseCommand):
    help = "Check rate-lock status for a login identifier (email/username/phone)."

    def add_arguments(self, parser):
        parser.add_argument(
            'identifier',
            type=str,
            help='Email, username, or phone number to check',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed cache information',
        )

    def handle(self, *args, **options):
        identifier = options['identifier'].strip()
        verbose = options.get('verbose', False)

        if not identifier:
            self.stderr.write(self.style.ERROR("Identifier is required"))
            sys.exit(1)

        key = _auth_fail_cache_key(identifier)
        attempts = cache.get(key, 0)
        max_attempts = max(1, AUTH_FAIL_MAX_ATTEMPTS)
        window = AUTH_FAIL_WINDOW_SECONDS

        self.stdout.write(f"\nChecking lock status for: {identifier}")
        self.stdout.write(f"Cache key (SHA256): {key}")
        self.stdout.write(f"Failed attempts: {attempts} / {max_attempts}")
        self.stdout.write(f"Time window: {window} seconds")

        if attempts >= max_attempts:
            self.stdout.write(self.style.ERROR("STATUS: LOCKED - Too many failed attempts"))
            # Try to get TTL
            try:
                # Redis: use ttl command; LocMem: not easily available
                ttl = cache.client.ttl(key) if hasattr(cache, 'client') else None
                if ttl is not None and ttl > 0:
                    mins = ttl // 60
                    secs = ttl % 60
                    self.stdout.write(f"Remaining lockout time: ~{mins}m {secs}s")
            except Exception:
                pass
        else:
            remaining = max_attempts - attempts
            self.stdout.write(self.style.SUCCESS(f"STATUS: NOT LOCKED - {remaining} attempts remaining"))

        if verbose:
            self.stdout.write("\nCache backend info:")
            self.stdout.write(f"  BACKEND: {cache.__class__.__module__}.{cache.__class__.__name__}")
            # Show all auth_fail keys (if Redis)
            try:
                if hasattr(cache, 'client'):
                    redis_client = cache.client.get_client()
                    pattern = f"auth_fail:*"
                    keys = list(redis_client.scan_iter(match=pattern, count=100))
                    self.stdout.write(f"  Total auth_fail keys in cache: {len(keys)}")
            except Exception:
                pass

        self.stdout.write("\nTo clear lockout for this identifier:")
        self.stdout.write(f"  python manage.py clear_auth_lockout '{identifier}'")
