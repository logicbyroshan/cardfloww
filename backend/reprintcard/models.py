"""
Reprint Card Models
====================
ReprintRequest — tracks reprint requests for ID cards.

NOTE: app_label stays 'core' so the existing DB table (core_reprintrequest)
and all existing migrations remain valid. No data migration needed.
"""
from django.conf import settings
from django.db import models

from tables.models import IDCard, Table


class ReprintRequest(models.Model):
    """
    Tracks reprint requests for ID cards.
    References the original card without modifying it.
    Workflow: requested → confirmed → downloaded → pool
    """
    REPRINT_STATUS_CHOICES = [
        ('requested', 'Requested'),
        ('confirmed', 'Confirmed'),
        ('downloaded', 'Downloaded'),
        ('pool', 'Pool'),
    ]

    card = models.ForeignKey(IDCard, on_delete=models.CASCADE, related_name='reprint_requests')
    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name='reprint_requests')
    status = models.CharField(max_length=20, choices=REPRINT_STATUS_CHOICES, default='requested', db_index=True)
    reason = models.TextField(blank=True, default='')
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reprint_requests',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Reprint #{self.id} — Card #{self.card_id} ({self.status})"

    class Meta:
        app_label = 'core'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['table', 'status']),
            models.Index(fields=['table', 'status', '-created_at']),
            models.Index(fields=['card']),
            models.Index(fields=['created_at']),
        ]
