"""
CardFlow — Operation, OperationChange, BulkTransaction & AuditEvent Models

Core Subsystems:
  1. Operation & OperationChange: Reversible operations engine with granular field deltas and conflict detection.
  2. BulkTransaction: First-class mass transaction entity grouping bulk movements, imports, and bulk status updates.
  3. AuditEvent: Immutable, append-only historical audit trail with role-based visibility scoping and card timeline linkage.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
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


class BulkTransaction(models.Model):
    """
    First-class mass mutation transaction entity.
    Represents a high-level bulk action (e.g. 2,000 cards moved Pending -> Verified)
    with bidirectional linkage to all affected individual card audit events.
    """
    VISIBILITY_CHOICES = [
        ('ORGANISATION', 'Organisation (Visible to Client & Staff)'),
        ('INTERNAL_ADMIN', 'Internal Admin (Operators & Staff)'),
        ('PRIME_ADMIN', 'Prime Admin Only'),
        ('SUPER_ADMIN', 'Super Admin Only'),
        ('SYSTEM', 'System Internal'),
    ]

    STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('partially_completed', 'Partially Completed'),
        ('reversed', 'Reversed'),
        ('partially_reversed', 'Partially Reversed'),
        ('failed', 'Failed'),
    ]

    ACTION_CHOICES = [
        ('bulk_status', 'Bulk Status Change'),
        ('bulk_update', 'Bulk Card Update'),
        ('bulk_delete', 'Bulk Delete'),
        ('bulk_restore', 'Bulk Restore'),
        ('import_data', 'Data Ingestion Import'),
        ('export_data', 'Data Export'),
        ('media_reupload', 'Bulk Media Reupload'),
        ('reverse_transaction', 'Reverse Transaction'),
    ]

    ACTOR_TYPE_CHOICES = [
        ('user', 'User'),
        ('system', 'System'),
        ('api', 'API Client'),
        ('worker', 'Background Worker'),
        ('ai', 'AI Engine'),
        ('import', 'Import Worker'),
        ('operator', 'Operator'),
    ]

    tx_code = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text='Human-readable transaction reference, e.g. "BT-20260817-001"',
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='bulk_transactions',
        db_index=True,
    )
    table = models.ForeignKey(
        Table,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bulk_transactions',
        db_index=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bulk_transactions',
    )
    actor_name_snapshot = models.CharField(
        max_length=150,
        blank=True,
        default='',
        help_text='Display name snapshot at the time of transaction',
    )
    actor_role_snapshot = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Role snapshot at the time of transaction (e.g. assistant, super_manager)',
    )
    actor_type = models.CharField(
        max_length=30,
        choices=ACTOR_TYPE_CHOICES,
        default='user',
    )
    action = models.CharField(
        max_length=50,
        choices=ACTION_CHOICES,
        default='bulk_status',
        db_index=True,
    )
    source_state = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Initial status/state before transaction (e.g. "pending")',
    )
    destination_state = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Target status/state after transaction (e.g. "verified")',
    )
    requested_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    conflict_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)

    visibility_scope = models.CharField(
        max_length=30,
        choices=VISIBILITY_CHOICES,
        default='ORGANISATION',
        db_index=True,
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='completed',
        db_index=True,
    )
    reversed_by_transaction = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reverses_transaction',
        help_text='New transaction that reversed this historical transaction',
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Supplementary transaction parameters, job IDs, IP address, device',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_bulktransaction'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organisation', 'created_at']),
            models.Index(fields=['table', 'created_at']),
            models.Index(fields=['organisation', 'visibility_scope', 'created_at']),
            models.Index(fields=['actor', 'created_at']),
        ]

    def __str__(self):
        return f"BulkTx {self.tx_code} [{self.action}]: {self.success_count}/{self.requested_count} items by {self.actor_name_snapshot or 'System'}"


class AuditEvent(models.Model):
    """
    Immutable, append-only historical audit event.
    Stores exact who, when, what, before/after values, and role visibility scope.
    """
    VISIBILITY_CHOICES = [
        ('ORGANISATION', 'Organisation'),
        ('INTERNAL_ADMIN', 'Internal Admin'),
        ('PRIME_ADMIN', 'Prime Admin'),
        ('SUPER_ADMIN', 'Super Admin'),
        ('SYSTEM', 'System'),
    ]

    EVENT_TYPE_CHOICES = [
        ('create', 'Record Created'),
        ('update', 'Record Updated'),
        ('delete', 'Record Deleted'),
        ('restore', 'Record Restored'),
        ('status_change', 'Status Changed'),
        ('move', 'Record Moved'),
        ('approve', 'Approved'),
        ('verify', 'Verified'),
        ('unverify', 'Unverified'),
        ('reject', 'Rejected'),
        ('media_upload', 'Media Uploaded'),
        ('media_replace', 'Media Replaced'),
        ('media_delete', 'Media Removed'),
        ('crop_update', 'Crop Box Updated'),
        ('bulk_status', 'Bulk Status Applied'),
        ('bulk_update', 'Bulk Field Update'),
        ('import_data', 'Data Ingestion Import'),
        ('export_data', 'Data Export'),
        ('schema_change', 'Schema Modified'),
        ('user_action', 'User / Role Mutation'),
        ('system_action', 'System Action'),
    ]

    TARGET_TYPE_CHOICES = [
        ('card', 'ID Card'),
        ('table', 'Table'),
        ('field', 'Dynamic Field'),
        ('media', 'Media File'),
        ('user', 'User / Account'),
        ('organisation', 'Organisation'),
        ('import', 'Import Job'),
        ('export', 'Export Job'),
        ('bulk_transaction', 'Bulk Transaction'),
    ]

    event_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text='Unique event identity string, e.g. "EVT-20260817-001234"',
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='audit_events',
        db_index=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_events',
    )
    actor_name_snapshot = models.CharField(
        max_length=150,
        blank=True,
        default='',
        help_text='Display name at time of event',
    )
    actor_role_snapshot = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Role at time of event (assistant, super_manager, prime_admin, etc.)',
    )
    actor_type = models.CharField(
        max_length=30,
        default='user',
        help_text='user, system, api, worker, ai, import',
    )
    event_type = models.CharField(
        max_length=50,
        choices=EVENT_TYPE_CHOICES,
        default='update',
        db_index=True,
    )
    target_type = models.CharField(
        max_length=50,
        choices=TARGET_TYPE_CHOICES,
        default='card',
        db_index=True,
    )
    target_id = models.IntegerField(
        db_index=True,
        help_text='Target entity PK (card_id, table_id, etc.)',
    )
    target_name_snapshot = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Target entity label snapshot (e.g. "Rahul Sharma (Card #1023)")',
    )
    target_table = models.ForeignKey(
        Table,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_events',
        db_index=True,
    )
    bulk_transaction = models.ForeignKey(
        BulkTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_events',
        db_index=True,
        help_text='Parent bulk transaction if event was part of a mass operation',
    )
    operation = models.ForeignKey(
        Operation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_events',
        db_index=True,
    )
    field_deltas = models.JSONField(
        default=list,
        blank=True,
        help_text='Granular field-level changes: [{field_id, field_name, before_value, after_value, change_type}]',
    )
    visibility_scope = models.CharField(
        max_length=30,
        choices=VISIBILITY_CHOICES,
        default='ORGANISATION',
        db_index=True,
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
    )
    session_id = models.CharField(
        max_length=100,
        blank=True,
        default='',
    )
    source = models.CharField(
        max_length=50,
        default='web_panel',
        help_text='Origin client: web_panel, mobile_app, desktop_app, api, worker',
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'core_auditevent'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organisation', 'created_at']),
            models.Index(fields=['target_type', 'target_id', 'created_at']),
            models.Index(fields=['target_table', 'created_at']),
            models.Index(fields=['actor', 'created_at']),
            models.Index(fields=['organisation', 'visibility_scope', 'created_at']),
            models.Index(fields=['bulk_transaction', 'created_at']),
        ]

    def __str__(self):
        return f"Event {self.event_id} [{self.event_type}] on {self.target_type}:{self.target_id} by {self.actor_name_snapshot or 'System'}"
