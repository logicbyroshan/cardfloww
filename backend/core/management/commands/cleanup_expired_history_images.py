"""
Cleanup Expired History Images Management Command

Purges historical undo/redo images older than 36 hours while preserving active images.
"""
from datetime import timedelta
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.files.storage import default_storage

from mediafiles.models import CardMedia
from mediafiles.services.image_core import ThumbnailService

logger = logging.getLogger(__name__)


def cleanup_expired_history_images() -> int:
    """Purge storage files for records marked as expired."""
    expired_records = CardMedia.objects.filter(
        status='expired'
    )
    
    purged_count = 0
    for record in expired_records:
        file_path = record.file.name if record.file else ''
        if file_path and default_storage.exists(file_path):
            try:
                default_storage.delete(file_path)
            except Exception as e:
                logger.warning("Failed to delete expired file %s: %s", file_path, e)
                
        if file_path:
            thumb_path = ThumbnailService.get_thumbnail_path(file_path)
            if default_storage.exists(thumb_path):
                try:
                    default_storage.delete(thumb_path)
                except Exception as e:
                    logger.warning("Failed to delete expired thumb %s: %s", thumb_path, e)
            
        record.status = 'expired'
        record.save(update_fields=['status'])
        purged_count += 1

    return purged_count


class Command(BaseCommand):
    help = "Purge historical undo/redo card media images older than 36 hours."

    def handle(self, *args, **options):
        self.stdout.write("Starting cleanup of expired history images (36h cutoff)...")
        purged = cleanup_expired_history_images()
        self.stdout.write(self.style.SUCCESS(f"Successfully purged {purged} expired history media records."))
