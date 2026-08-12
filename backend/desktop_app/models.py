import hashlib
import secrets

from django.db import models
from django.utils import timezone


class DesktopAppDevice(models.Model):
    device_name = models.CharField(max_length=120)
    installation_id = models.CharField(max_length=128, unique=True, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    token_prefix = models.CharField(max_length=12, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_ip_address = models.GenericIPAddressField(null=True, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', 'created_at']),
            models.Index(fields=['installation_id']),
            models.Index(fields=['token_prefix']),
        ]

    def __str__(self):
        return f'{self.device_name} ({self.installation_id})'

    @staticmethod
    def make_token() -> str:
        return secrets.token_urlsafe(48)

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(str(token or '').encode('utf-8')).hexdigest()

    def touch(self, *, ip_address=None):
        self.last_seen_at = timezone.now()
        if ip_address:
            self.last_ip_address = ip_address
        self.save(update_fields=['last_seen_at', 'last_ip_address', 'updated_at'])

    def revoke(self):
        self.is_active = False
        self.revoked_at = timezone.now()
        self.save(update_fields=['is_active', 'revoked_at', 'updated_at'])
