from django.db import models
from django.conf import settings
from django.utils import timezone

class UserDeviceSession(models.Model):
    DEVICE_TYPES = (
        ('web', 'Web Browser'),
        ('mobile', 'Mobile App/Phone'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='device_sessions')
    session_key = models.CharField(max_length=40, unique=True)
    device_type = models.CharField(max_length=10, choices=DEVICE_TYPES)
    user_agent = models.TextField(blank=True, null=True)
    ip_address = models.CharField(max_length=45, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "User Device Session"
        verbose_name_plural = "User Device Sessions"
        indexes = [
            models.Index(fields=['user', 'device_type']),
            models.Index(fields=['last_active']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.device_type} ({self.session_key[:8]})"
