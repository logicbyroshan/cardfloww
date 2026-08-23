import logging
import re

from django.conf import settings
from django.db import models
from organisation.models import Organisation

from mediafiles.constants import IMAGE_FIELD_TYPES

logger = logging.getLogger(__name__)


def _field_name_tokens(name):
    """Return normalized alphanumeric tokens from a field label."""
    return {tok for tok in re.split(r'[^a-z0-9]+', str(name or '').strip().lower()) if tok}


# ---------------------------------------------------------------------------
#   Text sanitizer — strips non-Latin-1 characters that cause ■ in PDF
# ---------------------------------------------------------------------------
_MULTI_SPACE_RE = re.compile(r' {2,}')
_IMAGE_PREFIXES = ('PENDING:', 'NOT_FOUND', 'adarshimg/', 'clients_imgs/',
                   'id_card_images/', 'id_photos/', 'staff_imgs/')
_WS_CTRL_RE = re.compile(r'[\t\n\r\x0b\x0c]')
_C0_CTRL_RE = re.compile(r'[\x00-\x1f\x7f]')
_NON_LATIN1_RE = re.compile(r'[\x80-\x9f\u0100-\U0010ffff]')


def sanitize_text_for_storage(value: str) -> str:
    """Strip characters outside Helvetica's renderable range (0x20-0xFF)."""
    if not value or not isinstance(value, str):
        return value
    if '/' in value and any(value.startswith(p) for p in _IMAGE_PREFIXES):
        return value
    for prefix in _IMAGE_PREFIXES:
        if value.startswith(prefix):
            return value
    result = _WS_CTRL_RE.sub(' ', value)
    result = _C0_CTRL_RE.sub('', result)
    result = _NON_LATIN1_RE.sub(' ', result)
    return _MULTI_SPACE_RE.sub(' ', result).strip()


class Table(models.Model):
    """
    Table — the core schema unit belonging to an Organisation.

    Collapses the old Table + Table two-level hierarchy into
    a single flat model. Each Organisation has Tables; each Table defines
    the field configuration (column names & types) for its ID Cards.

    Each Table also carries the status lists (pending, verified, approved,
    downloaded, pool/deleted, reprint) — these are statuses on IDCard records
    within the Table, not separate sub-models.
    """

    TABLE_TYPE_CHOICES = [
        ('school_student', 'School Student'),
        ('college_student', 'College Student'),
        ('staff', 'Staff / Employee'),
        ('custom', 'Custom'),
    ]

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='tables',
        db_column='client_id',
    )
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, null=True)
    table_type = models.CharField(
        max_length=20,
        choices=TABLE_TYPE_CHOICES,
        default='custom',
        help_text='Auto-detected from table name and organisation type.',
    )
    # Field definitions: [{name, type, order}, ...]
    fields = models.JSONField(
        default=list,
        help_text='List of field configurations: [{name, type, order}]. Max 20 fields.',
    )
    is_active = models.BooleanField(default=True)
    deleted_by_manager = models.BooleanField(
        default=False,
        db_column='deleted_by_client',
        help_text='True when the prime manager soft-deletes this table.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __init__(self, *args, **kwargs):
        if 'client' in kwargs:
            kwargs['organisation'] = kwargs.pop('client')
        if 'group' in kwargs:
            group_val = kwargs.pop('group')
            if 'organisation' not in kwargs:
                kwargs['organisation'] = getattr(group_val, 'organisation', getattr(group_val, 'client', group_val))
        super().__init__(*args, **kwargs)

    @property
    def client(self):
        return self.organisation

    @client.setter
    def client(self, value):
        self.organisation = value

    @property
    def client_id(self):
        return self.organisation_id

    @client_id.setter
    def client_id(self, value):
        self.organisation_id = value

    @property
    def group(self):
        return self

    @property
    def group_id(self):
        return self.id

    @property
    def deleted_by_client(self):
        return self.deleted_by_manager

    @deleted_by_client.setter
    def deleted_by_client(self, value):
        self.deleted_by_manager = value

    # ── Field introspection helpers ──────────────────────────

    def has_class_field(self):
        class_tokens = {'class', 'std', 'standard', 'grade'}
        return any(
            f.get('type') == 'class' or bool(_field_name_tokens(f.get('name', '')) & class_tokens)
            for f in self.fields
        )

    def has_section_field(self):
        section_tokens = {'section', 'sec', 'div', 'division'}
        return any(
            f.get('type') == 'section' or bool(_field_name_tokens(f.get('name', '')) & section_tokens)
            for f in self.fields
        )

    def has_course_field(self):
        course_tokens = {'course', 'program', 'programme'}
        return any(
            f.get('type') == 'course' or bool(_field_name_tokens(f.get('name', '')) & course_tokens)
            for f in self.fields
        )

    def has_branch_field(self):
        branch_tokens = {'branch', 'stream', 'dept', 'department'}
        return any(
            f.get('type') == 'branch' or bool(_field_name_tokens(f.get('name', '')) & branch_tokens)
            for f in self.fields
        )

    def has_image_fields(self):
        return any(f.get('type') in IMAGE_FIELD_TYPES for f in self.fields)

    def get_image_fields(self):
        return [f.get('name') for f in self.fields if f.get('type') in IMAGE_FIELD_TYPES]

    def delete_all_card_images(self):
        for card in self.id_cards.all().iterator(chunk_size=200):
            card.delete_images()

    def delete(self, *args, **kwargs):
        self.delete_all_card_images()
        super().delete(*args, **kwargs)

    def clean(self):
        from django.core.exceptions import ValidationError
        if len(self.fields) > 20:
            raise ValidationError('Maximum 20 fields allowed per table.')

    def save(self, *args, **kwargs):
        if len(self.fields) > 20:
            from django.core.exceptions import ValidationError
            raise ValidationError('Maximum 20 fields allowed per table.')
        super().save(*args, **kwargs)

    def __str__(self):
        org_name = self.organisation.name if self.organisation_id else 'No Organisation'
        return f"{self.name} — {org_name}"

    class Meta:
        app_label = 'tables'
        db_table = 'core_idcardtable'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organisation', 'is_active']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at']),
        ]


class IDCard(models.Model):
    """
    Individual ID Card — linked directly to a Table (flat, no group level).

    Status lists on IDCard represent the workflow stages:
    pending → verified → approved → printed/downloaded → (pool if deleted) → reprint
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('approved', 'Approved'),
        ('printed', 'Printed'),
        ('request', 'Requested'),
        ('deleted', 'Deleted'),
        ('download', 'Downloaded'),
        ('pool', 'In Pool'),
        ('reprint', 'Reprint'),
    ]

    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name='id_cards')

    field_data = models.JSONField(
        default=dict,
        help_text='Dynamic field values based on table fields.',
    )
    photo = models.ImageField(
        upload_to='id_photos/',
        blank=True,
        null=True,
        help_text='DEPRECATED: Use CardMedia model for new photos',
    )
    original_photo_name = models.CharField(
        max_length=255, blank=True, null=True, db_index=True,
        help_text='Original photo name from Excel for matching',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    modified_by = models.CharField(max_length=150, blank=True, default='')

    def __str__(self):
        field_data = self.field_data or {}
        name = field_data.get('name', field_data.get('Name', f'Card #{self.id}'))
        table_name = self.table.name if self.table_id else 'Unknown Table'
        return f"{name} — {table_name}"

    @property
    def organisation(self):
        """Convenience: get the organisation this card belongs to."""
        if self.table:
            return self.table.organisation
        return None

    @property
    def client(self):
        """Legacy compat — returns the organisation this card belongs to."""
        return self.organisation

    @property
    def group(self):
        """Legacy compat — returns the Table itself (group level removed)."""
        return self.table

    def delete_images(self):
        """Delete all image files associated with this card (incl. thumbnails)"""
        from mediafiles.services import ImageService
        if self.field_data:
            for field_name, value in self.field_data.items():
                if value and isinstance(value, str) and value not in ['NOT_FOUND', '']:
                    if 'adarshimg/' in value or 'id_card_images/' in value:
                        try:
                            ImageService.delete_image(value)
                        except Exception as e:
                            logger.warning("Could not delete image %s: %s", value, e)
        if self.photo:
            try:
                from django.core.files.storage import default_storage
                if default_storage.exists(self.photo.name):
                    default_storage.delete(self.photo.name)
            except Exception as e:
                logger.warning("Could not delete photo: %s", e)

    def delete(self, *args, **kwargs):
        self.delete_images()
        super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        if self.field_data and isinstance(self.field_data, dict):
            for key, value in self.field_data.items():
                if isinstance(value, str):
                    self.field_data[key] = sanitize_text_for_storage(value)
        super().save(*args, **kwargs)

    class Meta:
        app_label = 'tables'
        db_table = 'core_idcard'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['table', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['table', 'created_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['updated_at']),
            models.Index(fields=['table', 'status', '-id'], name='tbl_status_id_desc'),
            models.Index(fields=['table', 'status', '-status_changed_at', '-id'], name='tbl_st_chg_id_idx'),
            models.Index(fields=['table', 'status', '-downloaded_at', '-id'], name='tbl_st_dld_id_idx'),
            models.Index(fields=['table', 'status', '-deleted_at', '-id'], name='tbl_st_del_id_idx'),
            models.Index(fields=['downloaded_at'], name='tbl_downloaded_at_idx'),
            models.Index(fields=['deleted_at'], name='tbl_deleted_at_idx'),
            models.Index(fields=['status_changed_at'], name='tbl_status_changed_at_idx'),
        ]


class TableAccess(models.Model):
    """
    TableAccess model — relational table delegation between Organisation Tables
    and Super Managers / Guest Managers.
    Enforces that Super Managers only receive access to specific tables delegated by Prime Manager.
    """
    table = models.ForeignKey(
        Table,
        on_delete=models.CASCADE,
        related_name='manager_accesses',
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='table_accesses',
    )
    can_view = models.BooleanField(default=True)
    can_edit_cards = models.BooleanField(default=True)
    can_approve_print = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tables_tableaccess'
        constraints = [
            models.UniqueConstraint(fields=['table', 'manager'], name='unique_table_manager_access')
        ]

    def __str__(self):
        return f"{self.manager.username} -> {self.table.name}"


# ── Cache invalidation signals ──────────────────────────────────────────
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save, sender=IDCard)
@receiver(post_delete, sender=IDCard)
def clear_idcard_distinct_values_cache(sender, instance, **kwargs):
    """Clear distinct values cache when card data changes."""
    table_id = getattr(instance, 'table_id', None)
    if table_id:
        try:
            from core.views.idcard_helpers import invalidate_table_distinct_cache
            invalidate_table_distinct_cache(table_id)
        except Exception:
            pass


# ── Legacy compatibility aliases ────────────────────────────────────────
# Old code importing Table / Table will use Table instead
Table = Table
Table = Table   # single-level now; group = table
