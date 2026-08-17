"""
CardFlow — Operation & OperationChange Models for Reversible History Engine

Models:
  - Operation: Represents a single logical user action (single edit, multi-field save,
               bulk status update, record create, delete, restore, or media crop).
  - OperationChange: Granular field-level delta (before_value and after_value)
                     enabling conflict-aware multi-user rollback without snapshots.
"""
from django.db import models
from django.conf import settings
from organisation.models import Organisation
from tables.models import Table


class Operation(models.Model):
    """
    Represents a discrete user-triggered mutation.
    Maintains an undoable/redoable state machine scoped to an organisation and table.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('undone', 'Undone'),
        ('partially_undone', 'Partially Undone'),
        ('conflicted', 'Conflicted'),
        ('redone', 'Redone'),
        ('failed', 'Failed'),
    ]

    OPERATION_TYPE_CHOICES = [
        ('card_update', 'Single Card Edit'),
        ('card_create', 'Create Card'),
        ('card_delete', 'Delete Card'),
        ('card_restore', 'Restore Card'),
        ('bulk_update', 'Bulk Card Update'),
        ('bulk_status', 'Bulk Status Change'),
        ('bulk_delete', 'Bulk Delete'),
        ('bulk_restore', 'Bulk Restore'),
        ('media_update', 'Media Upload / Replace'),
        ('crop_update', 'Crop Metadata Change'),
        ('import_data', 'Data Ingestion Import'),
        ('move_cards', 'Move Cards'),
        ('undo_operation', 'Undo Operation'),
        ('redo_operation', 'Redo Operation'),
        ('custom', 'Custom Action'),
    ]

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='operations',
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operations',
    )
    session_id = models.CharField(
        max_length=100,
        blank=True,
        default='',
        db_index=True,
        help_text='Session or device identifier for guest/tab scoping',
    )
    operation_type = models.CharField(
        max_length=50,
        choices=OPERATION_TYPE_CHOICES,
        default='card_update',
        db_index=True,
    )
    target_type = models.CharField(
        max_length=50,
        default='card',
        db_index=True,
        help_text='Primary entity type: card, table, media, batch, import',
    )
    target_table = models.ForeignKey(
        Table,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operations',
        db_index=True,
    )

    description = models.CharField(
        max_length=500,
        help_text='Human-readable summary, e.g. "Changed status for 24 cards"',
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='active',
        db_index=True,
    )

    # Relationships for explicit operation tracking
    undo_of = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='undone_by',
        help_text='The original operation that this undo event reversed',
    )
    redo_of = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='redone_by',
        help_text='The undone operation that this redo event reapplied',
    )
    parent_operation = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_operations',
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Arbitrary operation metadata (job IDs, batch counts, crop boxes)',
    )
    schema_version = models.PositiveIntegerField(
        default=1,
        help_text='Payload schema version for long-term backward compatibility',
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_operation'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organisation', 'status']),
            models.Index(fields=['target_table', 'status']),
            models.Index(fields=['user', 'status', 'created_at']),
            models.Index(fields=['organisation', 'user', 'target_table', 'status']),
        ]

    def __str__(self):
        user_name = self.user.username if self.user else 'System'
        return f"Op #{self.id} [{self.operation_type}] by {user_name}: {self.description}"


class OperationChange(models.Model):
    """
    Granular field-level or entity-level delta.
    Stores before_value and after_value without requiring full-table snapshots.
    """
    STATUS_CHOICES = [
        ('applied', 'Applied'),
        ('undone', 'Undone'),
        ('conflicted', 'Conflicted'),
        ('skipped', 'Skipped'),
    ]

    CHANGE_TYPE_CHOICES = [
        ('field_edit', 'Field Edit'),
        ('status_change', 'Status Change'),
        ('record_create', 'Record Create'),
        ('record_delete', 'Record Delete'),
        ('record_restore', 'Record Restore'),
        ('media_replace', 'Media Replace'),
        ('crop_change', 'Crop Change'),
    ]

    operation = models.ForeignKey(
        Operation,
        on_delete=models.CASCADE,
        related_name='changes',
        db_index=True,
    )
    target_id = models.IntegerField(
        db_index=True,
        help_text='Target entity PK (e.g. card_id, table_id)',
    )
    target_model = models.CharField(
        max_length=50,
        default='idcard',
        db_index=True,
    )
    field_name = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Dynamic field name (e.g. "NAME", "CLASS", "STATUS", "PHOTO")',
    )
    change_type = models.CharField(
        max_length=50,
        choices=CHANGE_TYPE_CHOICES,
        default='field_edit',
        db_index=True,
    )
    before_value = models.JSONField(
        null=True,
        blank=True,
        help_text='Exact state before operation (preserves types, null vs empty)',
    )
    after_value = models.JSONField(
        null=True,
        blank=True,
        help_text='Exact state after operation',
    )
    expected_version = models.PositiveIntegerField(
        default=1,
        help_text='Optimistic concurrency version tag',
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='applied',
        db_index=True,
    )
    conflict_reason = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Reason if rollback encountered a multi-user conflict',
    )

    class Meta:
        db_table = 'core_operationchange'
        ordering = ['id']
        indexes = [
            models.Index(fields=['operation', 'target_id']),
            models.Index(fields=['target_model', 'target_id']),
            models.Index(fields=['target_model', 'target_id', 'field_name']),
        ]

    def __str__(self):
        return f"Change #{self.id} on {self.target_model}:{self.target_id}.{self.field_name} ({self.change_type})"
