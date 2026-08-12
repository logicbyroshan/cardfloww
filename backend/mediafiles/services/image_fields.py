"""
Image Fields — field utilities, path retrieval, and centralized image field processor.

Provides: ImageFieldsMixin (is_image_field, get_image_field_names,
process_image_field, get_image_path_for_card, get_image_path_for_export,
get_all_images_for_card, get_image_bytes_for_card).

Part of the ImageService mixin split.
"""
import os
import logging
from typing import Optional, List, Dict

from django.core.files.storage import default_storage

from ..constants import IMAGE_FIELD_TYPES, IMAGE_FIELD_NAME_PATTERNS
from .image_rename import ImageRenamer
from .image_thumbnail import ThumbnailService
from .image_core import MediaResult

logger = logging.getLogger(__name__)


class ImageFieldsMixin:
    """
    Image field utilities: type detection, centralized processor, path retrieval.
    """

    # ==================== CENTRALIZED IMAGE FIELD PROCESSOR ====================

    @classmethod
    def process_image_field(
        cls,
        field_name: str,
        new_value,
        existing_value: str,
        client,
        card=None,
        uploaded_file=None,
        batch_counter: int = 1,
        uploaded_by=None,
    ) -> 'MediaResult':
        """
        Centralized handler for ALL image field mutations.
        
        Handles every case:
          1. UPLOAD   – uploaded_file provided → save + thumbnail + CardMedia
          2. REMOVAL  – new_value is '' and existing_value had a path → delete file + thumbnail + CardMedia
          3. REWRITE  – new_value is a different valid path → normalize, validate, return
          4. UNCHANGED – new_value == existing_value → pass through
          5. MISSING   – path provided but file missing on disk → PENDING:{filename}
          6. PENDING   – new_value is PENDING:xxx → pass through
        
        Args:
            field_name:      Name of the image field (e.g. 'PHOTO', 'MOTHER PHOTO')
            new_value:       The incoming value (str path, '' for removal, None for unchanged)
            existing_value:  Current stored value in field_data for this field
            client:          Client model instance (for folder path generation)
            card:            IDCard model instance (optional, for CardMedia linkage)
            uploaded_file:   Django UploadedFile or None
            batch_counter:   Counter for unique filename generation
            uploaded_by:     User who uploaded (for CardMedia record)
            
        Returns:
            MediaResult with:
              data['final_value'] – the value to store in field_data
              data['action']      – one of: 'upload', 'removal', 'rewrite', 'unchanged', 'pending', 'missing'
              data['path']        – saved path (for uploads)
              data['thumbnail_path'] – thumbnail path (for uploads)
        """
        from core.services.base import BaseService
        
        existing_value = existing_value or ''
        
        # ── CASE 1: File upload ──────────────────────────────────────
        # Delegates to save_new_image / replace_image (single authority).
        if uploaded_file is not None:
            try:
                image_bytes = uploaded_file.read()
                uploaded_file.seek(0)
                original_ext = '.jpg'
                if hasattr(uploaded_file, 'name') and uploaded_file.name:
                    _, ext = os.path.splitext(uploaded_file.name)
                    if ext:
                        original_ext = ImageRenamer.normalize_extension(ext)
                
                original_filename = getattr(uploaded_file, 'name', None)
                
                # Determine existing path for replacement
                has_existing = (
                    existing_value
                    and existing_value not in ('', 'NOT_FOUND')
                    and not existing_value.startswith('PENDING:')
                )
                
                if has_existing:
                    result = cls.replace_image(
                        image_bytes=image_bytes,
                        client=client,
                        field_name=field_name,
                        existing_path=existing_value,
                        card=card,
                        batch_counter=batch_counter,
                        original_ext=original_ext,
                        original_filename=original_filename,
                        uploaded_by=uploaded_by,
                    )
                else:
                    result = cls.save_new_image(
                        image_bytes=image_bytes,
                        client=client,
                        field_name=field_name,
                        card=card,
                        batch_counter=batch_counter,
                        original_ext=original_ext,
                        original_filename=original_filename,
                        uploaded_by=uploaded_by,
                    )
                
                return result
            except Exception as e:
                logger.error("process_image_field upload error for %s: %s", field_name, e)
                return MediaResult(success=False, message=str(e))
        
        # Normalize new_value
        if new_value is None:
            # None means "not sent / unchanged"
            return MediaResult(
                success=True,
                data={'final_value': existing_value, 'action': 'unchanged'},
            )
        
        new_value = str(new_value).strip() if new_value else ''

        # Bare filenames are treated as pending references until they are
        # replaced with a real media path by the import/upload pipeline.
        # Guard against double-prefixing when callers accidentally pass
        # an already-prefixed value like 'PENDING:roll_1.jpg'.
        if new_value and '/' not in new_value and '\\' not in new_value:
            if new_value.startswith('PENDING:'):
                return cls.mark_pending(field_name, new_value[8:])
            return cls.mark_pending(field_name, os.path.basename(new_value))
        
        # ── CASE 6: PENDING reference ───────────────────────────────
        if new_value.startswith('PENDING:'):
            return cls.mark_pending(field_name, new_value[8:])
        
        # ── CASE 2: Removal ─────────────────────────────────────────
        # Delegates to remove_image (single authority).
        if new_value == '':
            return cls.remove_image(field_name, existing_value, card=card)
        
        # Normalize the path
        new_value = BaseService.normalize_image_path(new_value)
        
        # ── CASE 4: Unchanged ───────────────────────────────────────
        normalized_existing = BaseService.normalize_image_path(existing_value)
        if new_value == normalized_existing:
            return MediaResult(
                success=True,
                data={'final_value': existing_value, 'action': 'unchanged'},
            )
        
        # ── CASE 3 / 5: Rewrite or missing ──────────────────────────
        if BaseService.validate_image_path(new_value):
            return MediaResult(
                success=True,
                data={'final_value': new_value, 'action': 'rewrite'},
            )
        else:
            # File doesn't exist on disk → mark PENDING
            filename = os.path.basename(new_value) if new_value else ''
            pending_val = f'PENDING:{filename}' if filename else ''
            logger.warning("Image not found for %s: %s → %s", field_name, new_value, pending_val)
            return MediaResult(
                success=True,
                data={'final_value': pending_val, 'action': 'missing'},
            )

    # ==================== FIELD TYPE HELPERS ====================

    @classmethod
    def is_image_field(cls, field_config: dict) -> bool:
        """Check if a field configuration represents an image field."""
        import re
        field_type = field_config.get('type', 'text').lower()
        field_name = field_config.get('name', '').lower()
        
        # Check by type
        if field_type in [t.lower() for t in IMAGE_FIELD_TYPES]:
            return True

        normalized_name = re.sub(r'[\s_-]+', ' ', field_name).strip()
        if re.search(r'\b(?:rel(?:ation)?)\s*(?:1|one|2|two)\s*(?:photo|image|pic|picture)\b', normalized_name):
            return True
        
        # Check by name pattern with word boundary matching
        # This prevents 'designation' from matching 'sign'
        for pattern in IMAGE_FIELD_NAME_PATTERNS:
            pattern_lower = pattern.lower()
            # Use word boundary regex for safer matching
            if re.search(r'\b' + re.escape(pattern_lower) + r'\b', field_name):
                return True
            # Exact match
            if field_name == pattern_lower:
                return True
        
        return False

    @classmethod
    def get_image_field_names(cls, fields: list) -> list:
        """Get names of all image fields from a list of field configurations."""
        return [f.get('name') for f in fields if cls.is_image_field(f)]

    # ==================== IMAGE PATH RETRIEVAL ====================

    @classmethod
    def get_image_path_for_card(
        cls,
        card,
        field_name: str,
        fallback_to_field_data: bool = True
    ) -> Optional[str]:
        """
        Get the image path for a card's field.
        
        Args:
            card: IDCard model instance
            field_name: Name of the image field
            fallback_to_field_data: Whether to check field_data as fallback
            
        Returns:
            Image path if found and valid, None otherwise
        """
        # Check CardMedia first (future implementation)
        # For now, use field_data
        if fallback_to_field_data:
            from core.services.base import BaseService

            field_data = card.field_data or {}
            path = BaseService.normalize_image_path(field_data.get(field_name, ''))
            
            if path and path not in ('NOT_FOUND', '') and not path.startswith('PENDING:'):
                if not cls._is_safe_media_relative_path(path):
                    logger.warning(
                        "Blocked unsafe image path from get_image_path_for_card: %s",
                        path,
                    )
                    return None

                # Phase 2 guard: NEVER return a thumbnail path from this helper.
                # Exports and all read-helpers must always get the original.
                if ThumbnailService.is_thumbnail_path(path):
                    logger.warning(
                        "Blocked thumbnail path from get_image_path_for_card: %s", path
                    )
                    return None

                # Return path anyway for backward compat (callers check existence).
                # Bypassing default_storage.exists check here prevents massive network overhead (N network requests).
                return path
        
        return None

    @classmethod
    def get_image_path_for_export(
        cls,
        card,
        field_name: str,
        prefer_thumbnail: bool = False,
        fallback_to_field_data: bool = True
    ) -> Optional[str]:
        """
        Get image path for export, with optional thumbnail preference.
        
        Phase 4 update: PDF/Word exports should use thumbnails for smaller file size.
        ZIP exports continue using originals.
        
        Args:
            card: IDCard model instance
            field_name: Name of the image field
            prefer_thumbnail: If True, try thumbnail first, fall back to original
            fallback_to_field_data: Whether to check field_data as fallback
            
        Returns:
            Image path (thumbnail if preferred and available, else original)
        """
        # Get original path first
        original_path = cls.get_image_path_for_card(
            card, field_name, fallback_to_field_data
        )
        
        if not original_path:
            return None
        
        if not prefer_thumbnail:
            return original_path
        
        # Try to get/create thumbnail
        thumb_path = ThumbnailService.get_thumbnail_path(original_path)
        if thumb_path:
            try:
                from django.core.cache import cache as django_cache
                
                cache_key = f"thumb_exists:{thumb_path}"
                thumb_exists = django_cache.get(cache_key)
                
                if thumb_exists is None:
                    # On cache miss, query default_storage.exists and cache it
                    # Comments: Optimization D - Caching existence checks reduces redundant storage backend requests during heavy exports
                    thumb_exists = default_storage.exists(thumb_path)
                    django_cache.set(cache_key, thumb_exists, 86400)  # 24 hours TTL
                
                if thumb_exists:
                    return thumb_path
                
                # Thumbnail missing — regenerate automatically (Phase 2)
                created = ThumbnailService.create_thumbnail(original_path)
                if created:
                    # Update cache key to True when created successfully
                    created_cache_key = f"thumb_exists:{created}"
                    django_cache.set(created_cache_key, True, 86400)
                    if created != thumb_path:
                        django_cache.set(cache_key, True, 86400)
                    
                    if default_storage.exists(created):
                        return created
            except Exception as e:
                logger.debug("Thumbnail not available for %s: %s", original_path, e)
        
        # Fall back to original
        return original_path

    @classmethod
    def get_all_images_for_card(
        cls,
        card,
        image_field_names: Optional[List[str]] = None,
        fallback_to_field_data: bool = True
    ) -> Dict[str, Optional[str]]:
        """
        Get all image paths for a card.
        
        Args:
            card: IDCard model instance
            image_field_names: List of field names to check (all if None)
            fallback_to_field_data: Whether to check field_data
            
        Returns:
            Dict mapping field names to image paths (None if no image)
        """
        result = {}
        field_data = card.field_data or {}
        
        fields_to_check = image_field_names or list(field_data.keys())
        
        for field_name in fields_to_check:
            path = field_data.get(field_name, '')
            if path and path not in ('NOT_FOUND', '') and not path.startswith('PENDING:'):
                if cls._is_safe_media_relative_path(path):
                    result[field_name] = path
                else:
                    result[field_name] = None
            else:
                result[field_name] = None
        
        return result

    @classmethod
    def get_image_bytes_for_card(
        cls,
        card,
        field_name: str,
        fallback_to_field_data: bool = True
    ) -> Optional[bytes]:
        """
        Get image bytes for a card's field.
        
        Args:
            card: IDCard model instance
            field_name: Name of the image field
            fallback_to_field_data: Whether to check field_data
            
        Returns:
            Image bytes if found, None otherwise
        """
        path = cls.get_image_path_for_card(card, field_name, fallback_to_field_data)
        if not path:
            return None
        
        try:
            if default_storage.exists(path):
                with default_storage.open(path, 'rb') as f:
                    return f.read()
        except Exception as e:
            logger.warning("Could not read image at %s: %s", path, e)
        
        return None
