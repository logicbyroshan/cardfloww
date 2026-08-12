from django.db import models
from django.utils import timezone

class StatsSnapshot(models.Model):
    """
    Stores aggregated statistics snapshots over time.
    Allows plotting historical active client/assistant user activities, 
    batch job stats, and peak usage counters.
    """
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    active_clients = models.IntegerField(default=0)
    active_assistants = models.IntegerField(default=0)
    active_desktop_users = models.IntegerField(default=0)
    active_mobile_users = models.IntegerField(default=0)
    peak_active_users = models.IntegerField(default=0)
    total_cards_created = models.IntegerField(default=0)
    total_cards_approved = models.IntegerField(default=0)
    batch_jobs_count = models.IntegerField(default=0)

    class Meta:
        verbose_name = "Stats Snapshot"
        verbose_name_plural = "Stats Snapshots"
        ordering = ['-timestamp']

    def __str__(self):
        return f"StatsSnapshot at {self.timestamp} (Desktop: {self.active_desktop_users}, Mobile: {self.active_mobile_users})"


class ServerLoadAlert(models.Model):
    """
    Tracks the last time each load-level alert email was sent so we can
    enforce a cooldown period and avoid spamming admins.

    Levels:
      'warning'  — 50+ concurrent users  (server is slow)
      'critical' — 75+ concurrent users  (server is struggling)
      'danger'   — 100+ concurrent users (server will crash)
    """
    LEVEL_WARNING  = 'warning'
    LEVEL_CRITICAL = 'critical'
    LEVEL_DANGER   = 'danger'
    LEVEL_CHOICES  = [
        (LEVEL_WARNING,  'Warning (50+)'),
        (LEVEL_CRITICAL, 'Critical (75+)'),
        (LEVEL_DANGER,   'Danger (100+)'),
    ]

    level       = models.CharField(max_length=16, choices=LEVEL_CHOICES, unique=True)
    last_sent   = models.DateTimeField(null=True, blank=True)
    last_count  = models.IntegerField(default=0, help_text='Concurrent users when the alert was last triggered')

    class Meta:
        verbose_name = "Server Load Alert"
        verbose_name_plural = "Server Load Alerts"

    def __str__(self):
        return f"ServerLoadAlert [{self.level}] last_sent={self.last_sent}"
