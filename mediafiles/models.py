"""
Media Files Models

Centralized media storage for the ID Card system.
This module handles all image/file storage, decoupled from workflow models.

PHASE 1: Model introduction only - no behavior changes to existing system.
"""
import os
import re
import logging

from django.db import models
from django.conf import settings
from django.db.models.signals import pre_delete
from django.dispatch import receiver


logger = logging.getLogger(__name__)


def card_media_upload_path(instance, filename):
    """
    Generate upload path for card media files.
    Structure: card_media/{client_id}/{media_type}/{filename}
    """
    client_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(instance.client_id or 'unknown'))
    media_type = re.sub(r'[^a-zA-Z0-9_-]', '', str(instance.media_type or 'other'))

    raw_name = os.path.basename(str(filename or '').replace('\\', '/')).strip()
    name, ext = os.path.splitext(raw_name)

    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', name).strip('._')[:80] or 'upload'
    safe_ext = re.sub(r'[^a-zA-Z0-9.]', '', ext.lower())
    if safe_ext and not safe_ext.startswith('.'):
        safe_ext = f'.{safe_ext}'
    if not safe_ext or len(safe_ext) > 10:
        safe_ext = '.jpg'

    return f'card_media/{client_id}/{media_type}/{safe_name}{safe_ext}'


class CardMedia(models.Model):
    """
    Centralized media storage for ID Card images.
    
    This model stores all images associated with ID cards and templates,
    providing a single source of truth for media files.
    
    Design Notes:
    - card: Optional FK to IDCard (null for template images)
    - group: Optional FK to Table (for template images)
    - client: Required FK for data scoping and organization
    - media_type: Categorizes the image (photo, signature, template, etc.)
    - original_filename: Preserves original name for Excel matching
    
    IMPORTANT: This model uses app_label='mediafiles' - it has its own migrations.
    """
    
    # Media type choices - matches Table.IMAGE_FIELD_TYPES plus templates
    MEDIA_TYPE_CHOICES = [
        # Card image types (from Table.IMAGE_FIELD_TYPES)
        ('photo', 'Photo'),
        ('rel_photo', 'Relation Photo'),
        ('mother_photo', 'Mother Photo (Legacy)'),
        ('father_photo', 'Father Photo (Legacy)'),
        ('barcode', 'Barcode'),
        ('qr_code', 'QR Code'),
        ('signature', 'Signature'),
        # Template image types (from Table)
        ('template_front', 'Template Front'),
        ('template_back', 'Template Back'),
        # Generic/other
        ('other', 'Other'),
    ]
    
    # Core relationships
    # Using string references to avoid circular imports
    card = models.ForeignKey(
        'tables.IDCard',
        on_delete=models.CASCADE,
        related_name='media_files',
        null=True,
        blank=True,
        help_text='Associated ID card (null for template images)'
    )
    group = models.ForeignKey(
        'tables.Table',
        on_delete=models.CASCADE,
        related_name='template_media_files',
        null=True,
        blank=True,
        help_text='Associated Table (for template images)'
    )
    client = models.ForeignKey(
        'core.Organisation',
        on_delete=models.CASCADE,
        related_name='media_files',
        help_text='Organisation owner for data scoping'
    )
    
    # Media file
    file = models.ImageField(
        upload_to=card_media_upload_path,
        help_text='The actual image file'
    )
    
    # Metadata
    media_type = models.CharField(
        max_length=20,
        choices=MEDIA_TYPE_CHOICES,
        default='photo',
        db_index=True,
        help_text='Type/role of this media file'
    )
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text='Original filename from upload/Excel for matching'
    )
    field_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Dynamic field name from Table (e.g., "Photo", "Father Photo")'
    )
    
    # Audit fields
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_media',
        help_text='User who uploaded this file'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Status tracking for migration
    is_migrated = models.BooleanField(
        default=False,
        help_text='True if migrated from legacy storage (field_data/ImageField)'
    )
    legacy_path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text='Original path in legacy storage (for reference/rollback)'
    )
    
    # Architecture fields (Image Rename, Versioning & History Pipeline)
    root_token = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        db_index=True,
        help_text='14-digit root token (HHMMSSmmmuuuCC) created on 1st upload'
    )
    version = models.IntegerField(
        default=0,
        help_text='Incrementing version number (0 for initial upload, 1, 2, 3...)'
    )
    last_edited_by_role = models.CharField(
        max_length=1,
        choices=[('a', 'Admin'), ('c', 'Client'), ('o', 'Operator')],
        default='a',
        help_text='Role of the last uploader/editor'
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Active'),
            ('undo_stack', 'Undo Stack'),
            ('redo_stack', 'Redo Stack'),
            ('expired', 'Expired'),
        ],
        default='active',
        db_index=True,
        help_text='History status of this media version'
    )

    class Meta:
        verbose_name = 'Card Media'
        verbose_name_plural = 'Card Media'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', 'media_type']),
            models.Index(fields=['card', 'media_type']),
            models.Index(fields=['card', 'field_name']),
            models.Index(fields=['card', 'field_name', 'status']),
            models.Index(fields=['root_token', 'version']),
            models.Index(fields=['original_filename']),
            models.Index(fields=['file'], name='mediafiles__file_dbc7f5_idx'),
            models.Index(fields=['created_at']),
            models.Index(fields=['created_at', 'status']),
        ]
    
    def _get_media_type_label(self) -> str:
        """Get human-readable media type label (type-safe alternative to get_media_type_display)"""
        return dict(self.MEDIA_TYPE_CHOICES).get(self.media_type, self.media_type or 'Unknown')
    
    def __str__(self):
        media_label = self._get_media_type_label()
        if self.card:
            return f"{media_label} - Card #{self.card.id}"
        elif self.group:
            return f"{media_label} - Group: {self.group.name}"
        return f"{media_label} - {self.original_filename or 'Unknown'}"
    
    @property
    def url(self):
        """Get the URL for this media file"""
        if self.file:
            return self.file.url
        return None
    
    @property
    def filename(self):
        """Get just the filename from the file path"""
        if self.file:
            import os
            return os.path.basename(self.file.name)
        return self.original_filename
    
    def delete(self, *args, **kwargs):
        """Delete the record. File cleanup is handled by the pre_delete signal."""
        super().delete(*args, **kwargs)


@receiver(pre_delete, sender=CardMedia)
def cleanup_cardmedia_file(sender, instance, **kwargs):
    """Clean up physical file when CardMedia is cascade-deleted (not via instance.delete())"""
    if instance.file:
        try:
            file_name = str(instance.file.name or '').strip()
            if not file_name:
                return

            if CardMedia.objects.filter(file=file_name).exclude(pk=instance.pk).exists():
                logger.debug(
                    "Skipped file delete for shared media path %s (CardMedia id=%s)",
                    file_name,
                    instance.pk,
                )
                return

            storage = instance.file.storage
            if storage.exists(file_name):
                storage.delete(file_name)

            try:
                from .services.image_thumbnail import ThumbnailService

                ThumbnailService.delete_thumbnail(file_name)
            except Exception as thumb_err:
                logger.warning(
                    "Failed to delete thumbnail for %s (CardMedia %s): %s",
                    file_name,
                    instance.pk,
                    thumb_err,
                )
        except Exception as e:
            logger.warning(
                "Failed to delete file %s for CardMedia %s: %s",
                instance.file.name, instance.pk, e
            )
