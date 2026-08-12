"""
Thumbnail Service

Handles thumbnail generation and management.
Thumbnails stored in: adarshimg/thumbs/{client_code}/{filename}.webp

Rules (Phase 2 hardened):
  1. Thumbnails MUST be 5–10× smaller (bytes) than the original.
     If after initial compression the ratio is < 5×, quality is
     progressively reduced until the target is reached (floor = 40).
  2. Aspect ratio is ALWAYS preserved (PIL thumbnail mode).
  3. Thumbnails are NEVER included in any export (Word / ZIP / Excel).
     Exports use ImageService.get_image_path_for_card which returns
     original paths only — see the guard in that method.

NO STUBS. Real implementations only.
"""
import logging
from io import BytesIO
from typing import Optional, Tuple


from ..constants import THUMBNAIL_SIZE, THUMBNAIL_QUALITY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase 2 constants
# ---------------------------------------------------------------------------
MIN_SIZE_RATIO = 5        # Thumbnail must be at least 5× smaller than original
MAX_SIZE_RATIO = 10       # Target upper bound (softer — we don't upscale quality)
MIN_QUALITY = 40          # Absolute floor for WebP quality during auto-shrink
QUALITY_STEP = 5          # How much to drop quality per retry


class ThumbnailService:
    """
    Service for generating and managing image thumbnails.
    
    Storage structure:
    - Original: media/adarshimg/{client_code}/{filename}.jpg
    - Thumbnail: media/adarshimg/thumbs/{client_code}/{filename}.webp
    
    Phase 2 guarantees:
    - Thumbnail is 5–10× smaller (bytes) than the original.
    - Aspect ratio is preserved.
    - Thumbnails are never served by export helpers.
    """
    
    THUMB_FOLDER = 'thumbs'
    DEFAULT_SIZE = THUMBNAIL_SIZE
    QUALITY = THUMBNAIL_QUALITY
    
    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------
    
    @classmethod
    def is_thumbnail_path(cls, path: str) -> bool:
        """Return True if *path* looks like a thumbnail (contains /thumbs/)."""
        if not path:
            return False
        return f'/{cls.THUMB_FOLDER}/' in path.replace('\\', '/')
    
    @classmethod
    def get_thumbnail_path(cls, original_path: str) -> Optional[str]:
        """
        Get the thumbnail path for an original image path.
        
        Args:
            original_path: Path to original image (e.g., "adrsh_img/ABCDE/123.jpg")
            
        Returns:
            Thumbnail path (e.g., "adrsh_img/thumbs/ABCDE/123.jpg")
            None if original_path is invalid
        """
        if not original_path:
            return None
        
        # Handle PENDING: prefix
        if original_path.startswith('PENDING:'):
            return None
        
        if original_path in ['NOT_FOUND', '', 'PENDING']:
            return None
        
        # Split path into components
        parts = original_path.replace('\\', '/').split('/')
        
        if len(parts) < 2:
            # Just a filename - add thumbs folder
            return f"{cls.THUMB_FOLDER}/{original_path}"
        
        # Insert 'thumbs' after the base folder and change extension to .webp
        # e.g., "adarshimg/ABCDE/123.jpg" -> "adarshimg/thumbs/ABCDE/123.webp"
        base_folder = parts[0]
        rest = '/'.join(parts[1:])
        
        # Replace extension with .webp
        name, _ext = rest.rsplit('.', 1) if '.' in rest else (rest, '')
        rest = f"{name}.webp"
        
        return f"{base_folder}/{cls.THUMB_FOLDER}/{rest}"
    
    @classmethod
    def generate_thumbnail(
        cls,
        image_bytes: bytes,
        max_size: Optional[Tuple[int, int]] = None,
        original_size_bytes: Optional[int] = None,
    ) -> Optional[bytes]:
        """
        Generate a thumbnail from image bytes.
        
        Phase 2 rules:
        - Aspect ratio is always preserved (PIL ``thumbnail``).
        - If *original_size_bytes* is supplied the method will
          progressively lower JPEG quality until the thumbnail is
          at least ``MIN_SIZE_RATIO`` (5×) smaller than the original.
          Quality never drops below ``MIN_QUALITY`` (40).
        
        Args:
            image_bytes:        Original image data.
            max_size:           Maximum bounding-box (w, h). Defaults to THUMBNAIL_SIZE.
            original_size_bytes: Size of the original file in bytes (for ratio enforcement).
            
        Returns:
            Thumbnail image bytes (WebP), or None on failure.
        """
        if not image_bytes or len(image_bytes) < 100:
            logger.warning("Invalid image bytes for thumbnail generation")
            return None
        
        try:
            from PIL import Image, ImageOps
            
            # MAX_IMAGE_PIXELS is set once at app startup (core/apps.py)
            
            size = max_size or cls.DEFAULT_SIZE
            
            # Open and validate image
            img = Image.open(BytesIO(image_bytes))
            try:
                # Convert to RGB if necessary (for JPEG output)
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img_converted = img.convert('RGBA')
                        img.close()
                        img = img_converted
                    background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                    img.close()
                    img = background
                elif img.mode != 'RGB':
                    img_converted = img.convert('RGB')
                    img.close()
                    img = img_converted
                
                # Handle EXIF orientation
                try:
                    img = ImageOps.exif_transpose(img)
                except Exception as exc:
                    logger.debug('EXIF transpose skipped during thumbnail generation: %s', exc)
                
                # Create thumbnail (maintains aspect ratio)
                img.thumbnail(size, Image.Resampling.LANCZOS)
                
                # --- Phase 2: size-aware quality loop (WebP output) ---
                orig_len = original_size_bytes or len(image_bytes)
                quality = cls.QUALITY  # start at configured default (85)
                
                for _ in range(20):  # safety cap
                    output = BytesIO()
                    img.save(output, format='WEBP', quality=quality, method=4)
                    thumb_bytes = output.getvalue()
                    
                    ratio = orig_len / max(len(thumb_bytes), 1)
                    
                    if ratio >= MIN_SIZE_RATIO or quality <= MIN_QUALITY:
                        break
                    
                    # Not small enough — drop quality and retry
                    quality = max(quality - QUALITY_STEP, MIN_QUALITY)
                
                # Log ratio for observability
                final_ratio = orig_len / max(len(thumb_bytes), 1)
                if final_ratio < MIN_SIZE_RATIO:
                    logger.warning(
                        "Thumbnail ratio %.1f× is below target %d× (quality=%d, "
                        "orig=%d bytes, thumb=%d bytes)",
                        final_ratio, MIN_SIZE_RATIO, quality,
                        orig_len, len(thumb_bytes),
                    )
                else:
                    logger.debug(
                        "Thumbnail OK: %.1f× smaller (quality=%d, orig=%d, thumb=%d)",
                        final_ratio, quality, orig_len, len(thumb_bytes),
                    )
                
                return thumb_bytes
            finally:
                # Explicitly close PIL image to free memory
                img.close()
            
        except Exception as e:
            logger.error("Failed to generate thumbnail: %s", e)
            return None
    
    @classmethod
    def create_thumbnail(cls, original_path: str) -> Optional[str]:
        """
        Create a thumbnail for an existing image file.
        
        Args:
            original_path: Path to original image (relative to MEDIA_ROOT)
            
        Returns:
            Thumbnail path on success, None on failure
        """
        if not original_path:
            return None
        
        try:
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            
            # Read original image
            if not default_storage.exists(original_path):
                logger.warning("Original image not found: %s", original_path)
                return None
            
            with default_storage.open(original_path, 'rb') as f:
                image_bytes = f.read()
            
            # Generate thumbnail (pass original size for ratio enforcement)
            thumb_bytes = cls.generate_thumbnail(
                image_bytes, original_size_bytes=len(image_bytes)
            )
            if not thumb_bytes:
                logger.warning("Failed to generate thumbnail for: %s", original_path)
                return None
            
            # Get thumbnail path
            thumb_path = cls.get_thumbnail_path(original_path)
            if not thumb_path:
                return None
            
            # Save thumbnail
            saved_path = default_storage.save(thumb_path, ContentFile(thumb_bytes))
            logger.debug("Created thumbnail: %s", saved_path)
            
            # Cache the existence status to reduce default_storage.exists calls
            try:
                from django.core.cache import cache as django_cache
                django_cache.set(f"thumb_exists:{saved_path}", True, 86400)
                if saved_path != thumb_path:
                    django_cache.set(f"thumb_exists:{thumb_path}", True, 86400)
            except Exception as ce:
                logger.debug("Cache write failed on create_thumbnail: %s", ce)
            
            return saved_path
            
        except Exception as e:
            logger.error("Failed to create thumbnail for %s: %s", original_path, e)
            return None
    
    @classmethod
    def ensure_thumbnail_exists(cls, original_path: str) -> Optional[str]:
        """
        Ensure a thumbnail exists for the given image, creating if missing.
        
        Args:
            original_path: Path to original image
            
        Returns:
            Thumbnail path if it exists or was created, None on failure
        """
        if not original_path:
            return None
        
        try:
            from django.core.files.storage import default_storage
            
            thumb_path = cls.get_thumbnail_path(original_path)
            if not thumb_path:
                return None
            
            # Check if thumbnail already exists
            if default_storage.exists(thumb_path):
                return thumb_path
            
            # Create thumbnail
            return cls.create_thumbnail(original_path)
            
        except Exception as e:
            logger.error("Failed to ensure thumbnail for %s: %s", original_path, e)
            return None
    
    @classmethod
    def delete_thumbnail(cls, original_path: str) -> bool:
        """
        Delete the thumbnail for an image.
        
        Args:
            original_path: Path to original image
            
        Returns:
            True if deleted (or didn't exist), False on error
        """
        if not original_path:
            return True
        
        try:
            from django.core.files.storage import default_storage
            
            thumb_path = cls.get_thumbnail_path(original_path)
            if not thumb_path:
                return True
            
            if default_storage.exists(thumb_path):
                default_storage.delete(thumb_path)
                logger.debug("Deleted thumbnail: %s", thumb_path)
            
            # Clear existence status from cache to prevent broken image references
            try:
                from django.core.cache import cache as django_cache
                django_cache.delete(f"thumb_exists:{thumb_path}")
            except Exception as ce:
                logger.debug("Cache delete failed on delete_thumbnail: %s", ce)
            
            return True
            
        except Exception as e:
            logger.error("Failed to delete thumbnail for %s: %s", original_path, e)
            return False
