"""
Reprint Models
==============
ReprintRequest — tracks reprint requests and history for ID cards.

The model uses db_table='core_reprintrequest' to preserve all existing
database records while operating within the clean dedicated 'reprint' app.
"""
from django.conf import settings
from django.db import models

from tables.models import IDCard, Table


class ReprintRequest(models.Model):
    """
    Tracks reprint requests and history for ID cards.
    References the original IDCard where status='download'.
    
    Workflow:
      1. Reprint List (Downloaded source cards) -> Requested List
      2. Requested List -> Confirmed List (applies any edits in-place to the original card)
      3. Confirmed List -> Downloaded / Printed
    """
    REPRINT_STATUS_CHOICES = [
        ('requested', 'Requested'),
        ('confirmed', 'Confirmed'),
        ('downloaded', 'Downloaded'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    card = models.ForeignKey(IDCard, on_delete=models.CASCADE, related_name='reprint_requests')
    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name='reprint_requests')
    status = models.CharField(max_length=20, choices=REPRINT_STATUS_CHOICES, default='requested', db_index=True)
    reason = models.TextField(blank=True, default='')
    changes = models.JSONField(default=dict, blank=True, help_text="Staged field updates applied upon confirmation")
    reprint_number = models.PositiveIntegerField(default=1, help_text="Sequential reprint number for this card (1=first reprint, 2=second, etc.)")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reprint_requests_created',
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reprint_requests_confirmed',
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Reprint #{self.id} (Card #{self.card_id}, #{self.reprint_number}x) — {self.status}"

    @property
    def has_changes(self) -> bool:
        return bool(self.changes and isinstance(self.changes, dict))

    class Meta:
        app_label = 'core'
        db_table = 'core_reprintrequest'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['table', 'status']),
            models.Index(fields=['table', 'status', '-created_at']),
            models.Index(fields=['card']),
            models.Index(fields=['card', 'status']),
            models.Index(fields=['created_at']),
        ]
