from django.db import models
from django.conf import settings

class MobileDeviceToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mobile_device_tokens'
    )
    push_token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mobile_device_tokens'
        verbose_name = 'Mobile Device Token'
        verbose_name_plural = 'Mobile Device Tokens'

    def __str__(self):
        return f"{self.user.username} - {self.push_token[:20]}"
