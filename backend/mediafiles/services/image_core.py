"""
Image Core — MediaResult dataclass + core image operations.

Provides: MediaResult, ServiceResult, ImageCoreMixin
(filename generation, validation, folder management, save, delete, thumbnail wrappers).

Part of the ImageService mixin split.
"""
import os
import logging
from io import BytesIO
from typing import Tuple, Optional, Dict, Any, List
from dataclasses import dataclass, field

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from ..constants import (
    VALID_IMAGE_EXTENSIONS,
    IMAGE_FIELD_TYPES,
    IMAGE_FIELD_NAME_PATTERNS,
    THUMBNAIL_SIZE,
    THUMBNAIL_SUFFIX,
    CLIENT_IMAGE_BASE_FOLDER,
)
from ..utils import normalize_image_bytes_for_storage, register_heif_opener
from .image_rename import ImageRenamer
from .image_thumbnail import ThumbnailService

logger = logging.getLogger(__name__)

# Process-lifetime cache of confirmed-existing image folders.
# Avoids repeated os.makedirs syscalls during bulk upload
# (5000 images × 2 makedirs = 10 000 redundant filesystem calls).
_confirmed_folders: set = set()


# =============================================================================
# SERVICE RESULT
# =============================================================================

@dataclass
class MediaResult:
    """Standard result object for media service operations."""
    success: bool
    message: str = ''
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict suitable for JSON response."""
        response: Dict[str, Any] = {'success': self.success}
        if self.message:
            response['message'] = self.message
        if self.data:
            response.update(self.data)
        return response


# Backward compatibility alias
ServiceResult = MediaResult


# =============================================================================
# CORE MIXIN
# =============================================================================

class ImageCoreMixin:
    """
    Core image operations: filename generation, validation, save, delete, thumbnails.
    """

    # Re-export constants for backward compatibility
    THUMBNAIL_SIZE = THUMBNAIL_SIZE
    THUMBNAIL_SUFFIX = THUMBNAIL_SUFFIX
    VALID_IMAGE_EXTENSIONS = VALID_IMAGE_EXTENSIONS
    IMAGE_FIELD_TYPES = IMAGE_FIELD_TYPES
    IMAGE_FIELD_NAME_PATTERNS = IMAGE_FIELD_NAME_PATTERNS

    # Temp folder for uploads
    TEMP_FOLDER = 'temp'

    # ==================== FILENAME GENERATION ====================

    @staticmethod
    def _is_safe_media_relative_path(path: Optional[str]) -> bool:
        """Allow only safe relative storage paths (block absolute/traversal/URL forms)."""
        if not path:
            return False

        raw_candidate = str(path)
        if '\x00' in raw_candidate:
            return False
        if any(ord(ch) < 32 for ch in raw_candidate if ch not in ('\t', '\n', '\r')):
            return False

        candidate = raw_candidate.strip().replace('\\', '/')
        if not candidate:
            return False

        lowered = candidate.lower()
        if lowered.startswith(('http://', 'https://', 'file://', 'data:')):
            return False

        if os.path.isabs(candidate) or candidate.startswith('/'):
            return False

        normalized = os.path.normpath(candidate).replace('\\', '/')
        if normalized in ('', '.', '..'):
            return False
        if normalized.startswith('../') or '/..' in f'/{normalized}':
            return False

        # Block Windows drive-like prefixes (e.g., C:/foo)
        first_part = normalized.split('/', 1)[0]
        if ':' in first_part:
            return False

        media_root = os.path.abspath(settings.MEDIA_ROOT)
        resolved = os.path.abspath(os.path.join(media_root, normalized))
        if not (resolved == media_root or resolved.startswith(media_root + os.sep)):
            return False

        return True

    @staticmethod
    def generate_filename(batch_counter: int = 1, original_ext: str = '.jpg', upload_prefix: str = 'a') -> str:
        """Generate a unique prefixed filename for NEW uploaded images."""
        return ImageRenamer.generate_filename(batch_counter, original_ext, upload_prefix=upload_prefix)

    @staticmethod
    def generate_updated_filename(existing_path: str, new_ext: Optional[str] = None, upload_prefix: str = 'a') -> str:
        """Generate updated filename for EXISTING images (preserves original timestamp)."""
        return ImageRenamer.generate_updated_filename(existing_path, new_ext, upload_prefix=upload_prefix)

    # ==================== VALIDATION ====================

    @staticmethod
    def validate_image_bytes(image_bytes: bytes) -> Tuple[bool, Optional[str]]:
        """
        Validate that image bytes represent a valid image.
        
        Args:
            image_bytes: Raw image data
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not image_bytes:
            return False, "Image data is empty"
        
        if len(image_bytes) < 100:
            return False, "Image data is too small"
        
        MAX_IMAGE_SIZE = 30 * 1024 * 1024  # 30MB per image
        if len(image_bytes) > MAX_IMAGE_SIZE:
            return False, f"Image too large ({len(image_bytes) // 1024 // 1024}MB). Maximum is 30MB."
        
        try:
            from PIL import Image

            register_heif_opener()

            # MAX_IMAGE_PIXELS is set once at app startup (core/apps.py)

            # Phase 1: verify file integrity (header + checksum check).
            # img.verify() is fast — it does NOT decode pixels.
            # After verify(), PIL corrupts the internal state, so we must
            # re-open to read the format string.
            with Image.open(BytesIO(image_bytes)) as img:
                img.verify()

            # Phase 2: read format — do NOT call img.load() here.
            # load() would decode the full pixel data (~15 MB for a 5 MP JPEG)
            # just to throw it away. format is populated by open() alone.
            with Image.open(BytesIO(image_bytes)) as img:
                fmt = (img.format or '').lower()
                if fmt and fmt not in ['jpeg', 'jpg', 'png', 'gif', 'bmp', 'webp', 'heic', 'heif']:
                    return False, f"Unsupported image format: {img.format}"

            return True, None
            
        except Exception as e:
            return False, f"Invalid image: {str(e)}"

    # ==================== FOLDER MANAGEMENT ====================

    @staticmethod
    def get_client_image_folder(client) -> str:
        """
        Get or create the image folder path for a client.
        
        Args:
            client: Organisation model instance
            
        Returns:
            Folder path relative to MEDIA_ROOT (e.g., "adrsh_img/ABCDE12345")
        """
        folder_code = getattr(client, 'image_folder_code', None)
        if not folder_code:
            # Generate from client name if not set
            from ..utils import generate_folder_code_from_name, generate_unique_suffix
            folder_code = generate_folder_code_from_name(getattr(client, 'name', 'CLIENT'))
            folder_code += generate_unique_suffix(5)
        
        folder_path = f"{CLIENT_IMAGE_BASE_FOLDER}/{folder_code}"
        
        # Only call makedirs once per folder per process lifetime.
        # During bulk upload every image calls this function; without the
        # guard that means 10 000 redundant makedirs syscalls (already-exists).
        if folder_path not in _confirmed_folders:
            try:
                full_path = os.path.join(settings.MEDIA_ROOT, folder_path)
                os.makedirs(full_path, exist_ok=True)

                thumbs_path = os.path.join(
                    settings.MEDIA_ROOT, CLIENT_IMAGE_BASE_FOLDER, 'thumbs', folder_code
                )
                os.makedirs(thumbs_path, exist_ok=True)

                _confirmed_folders.add(folder_path)
            except Exception as e:
                logger.warning("Could not create folder %s: %s", folder_path, e)
        
        return folder_path

    @classmethod
    def get_temp_folder(cls) -> str:
        """
        Get or create the temp folder path.
        
        Returns:
            Temp folder path relative to MEDIA_ROOT
        """
        temp_path = cls.TEMP_FOLDER
        try:
            full_path = os.path.join(settings.MEDIA_ROOT, temp_path)
            os.makedirs(full_path, exist_ok=True)
        except Exception as e:
            logger.warning("Could not create temp folder: %s", e)
        return temp_path

    # ==================== IMAGE SAVING (internal) ====================

    @classmethod
    def save_image(
        cls,
        file_content,
        client,
        existing_path: Optional[str] = None,
        batch_counter: int = 1,
        delete_existing_on_update: bool = True,
        uploader_prefix: str = 'a',
    ) -> 'MediaResult':
        """
        Save an image file to the client's folder with collision-safe renaming.
        
        On failure: cleans up any partially written files and logs explicit errors.
        
        Args:
            file_content: File content (UploadedFile or bytes)
            client: Organisation model instance
            existing_path: Path of existing image (for updates)
            batch_counter: Counter for unique filename generation
            delete_existing_on_update: If True, remove old file+thumbnail immediately
            
        Returns:
            MediaResult with saved path in data['path']
        """
        saved_path = None
        try:
            # Get image bytes
            if hasattr(file_content, 'read'):
                image_bytes = file_content.read()
                file_content.seek(0)  # Reset for potential re-read
            else:
                image_bytes = file_content
            
            # Validate image
            is_valid, error_msg = cls.validate_image_bytes(image_bytes)
            if not is_valid:
                return MediaResult(success=False, message=error_msg or "Invalid image")
            
            # Get extension from file if possible
            original_ext = '.jpg'
            if hasattr(file_content, 'name') and file_content.name:
                _, ext = os.path.splitext(file_content.name)
                if ext:
                    original_ext = ImageRenamer.normalize_extension(ext)
            
            # Get client folder
            client_folder = cls.get_client_image_folder(client)
            
            # Generate collision-safe filename
            is_update = (
                existing_path
                and existing_path not in ['NOT_FOUND', '', 'PENDING']
                and not existing_path.startswith('PENDING:')
                and cls._is_safe_media_relative_path(existing_path)
            )

            if existing_path and not is_update and existing_path not in ['NOT_FOUND', '', 'PENDING']:
                logger.warning("Blocked unsafe existing_path during image update: %s", existing_path)
            
            if is_update:
                filename = ImageRenamer.generate_updated_filename_safe(
                    client_folder,
                    existing_path,
                    original_ext,
                    upload_prefix=uploader_prefix,
                )
            else:
                filename = ImageRenamer.generate_filename_safe(
                    client_folder,
                    batch_counter,
                    original_ext,
                    upload_prefix=uploader_prefix,
                )
            
            file_path = f"{client_folder}/{filename}"
            
            # Save the image
            saved_path = default_storage.save(file_path, ContentFile(image_bytes))
            
            # Delete old image if this is an update
            if is_update and delete_existing_on_update:
                try:
                    # Only delete the old image if it is a different path than
                    # the file we just saved. Some storage backends may return
                    # the same filename or overwrite on save; deleting in that
                    # case would remove the newly-saved image.
                    if default_storage.exists(existing_path):
                        try:
                            # Normalize both paths before comparison to avoid
                            # accidental deletion when storage returns
                            # semantically-equal but string-different paths.
                            def _norm(p):
                                return os.path.normcase(os.path.normpath(str(p).replace('\\', '/')))

                            saved_norm = _norm(saved_path)
                            existing_norm = _norm(existing_path)
                        except Exception:
                            saved_norm = str(saved_path)
                            existing_norm = str(existing_path)

                        if saved_norm != existing_norm:
                            default_storage.delete(existing_path)
                            logger.debug("Deleted old image: %s", existing_path)
                        else:
                            logger.debug(
                                "Skipped deleting old image because normalized paths match: %s",
                                existing_path,
                            )
                    # Also delete old thumbnail
                    ThumbnailService.delete_thumbnail(existing_path)
                except Exception as del_err:
                    logger.warning("Could not delete old image %s: %s", existing_path, del_err)
            
            return MediaResult(
                success=True,
                message="Image saved successfully",
                data={'path': saved_path, 'filename': filename}
            )
            
        except Exception as e:
            # CLEANUP: remove partially written file if it was saved
            if saved_path:
                try:
                    if default_storage.exists(saved_path):
                        default_storage.delete(saved_path)
                        logger.info("Cleaned up partial file after error: %s", saved_path)
                except Exception as cleanup_err:
                    logger.error("Failed to clean up partial file %s: %s", saved_path, cleanup_err)
            
            logger.error("Failed to save image: %s", e, exc_info=True)
            return MediaResult(success=False, message=f"Failed to save image: {str(e)}")

    @classmethod
    def save_image_with_thumbnail(
        cls,
        image_bytes: bytes,
        client,
        existing_path: Optional[str] = None,
        batch_counter: int = 1,
        original_ext: str = '.jpg',
        delete_existing_on_update: bool = True,
        uploader_prefix: str = 'a',
    ) -> 'MediaResult':
        """
        Save an image and generate its thumbnail.

        Phase 1 rule: If the image exceeds 5 MB it is quality-compressed
        (dimensions preserved) before saving.
        """
        normalized_bytes, normalized_ext, normalize_err = normalize_image_bytes_for_storage(
            image_bytes,
            suggested_ext=original_ext,
        )
        if normalize_err:
            return MediaResult(success=False, message=normalize_err)

        image_bytes = normalized_bytes
        original_ext = normalized_ext

        # Phase 1: compress large images to <= 5 MB (quality only, no resize)
        if len(image_bytes) > cls.MAX_STORED_IMAGE_SIZE:
            compressed_bytes = cls.compress_to_target_size(image_bytes)
            if compressed_bytes != image_bytes:
                image_bytes = compressed_bytes
                # After compression the effective extension is always JPEG
                original_ext = '.jpg'

        # First save the original
        result = cls.save_image(
            ContentFile(image_bytes, name=f'upload{original_ext}'),
            client,
            existing_path,
            batch_counter,
            delete_existing_on_update,
            uploader_prefix,
        )
        
        if not result.success:
            return result
        
        saved_path = result.data.get('path')
        
        # Generate thumbnail
        if saved_path:
            thumb_path = ThumbnailService.create_thumbnail(saved_path)
        else:
            thumb_path = None
        if thumb_path:
            result.data['thumbnail_path'] = thumb_path
        else:
            logger.warning("Failed to create thumbnail for: %s", saved_path)
        
        return result

    # ==================== IMAGE DELETION ====================

    @classmethod
    def delete_image(cls, image_path: str) -> 'MediaResult':
        """
        Delete an image and its thumbnail.
        
        Args:
            image_path: Path to the image
            
        Returns:
            MediaResult indicating success/failure
        """
        if not image_path or image_path in ['NOT_FOUND', '', 'PENDING']:
            return MediaResult(success=True, message="No image to delete")
        
        if image_path.startswith('PENDING:'):
            return MediaResult(success=True, message="Pending reference cleared")

        if not cls._is_safe_media_relative_path(image_path):
            logger.warning("Blocked unsafe image delete path: %s", image_path)
            return MediaResult(success=False, message="Invalid image path")
        
        try:
            # Delete original
            if default_storage.exists(image_path):
                default_storage.delete(image_path)
                logger.debug("Deleted image: %s", image_path)
            
            # Delete thumbnail
            ThumbnailService.delete_thumbnail(image_path)
            
            return MediaResult(success=True, message="Image deleted")
            
        except Exception as e:
            logger.error("Failed to delete image %s: %s", image_path, e)
            return MediaResult(success=False, message=f"Failed to delete: {str(e)}")

    # ==================== THUMBNAIL OPERATIONS ====================

    @classmethod
    def get_thumbnail_path(cls, original_path: Optional[str]) -> Optional[str]:
        """Get the thumbnail path for an original image."""
        if not original_path:
            return None
        return ThumbnailService.get_thumbnail_path(original_path)

    @classmethod
    def generate_thumbnail(cls, image_bytes: bytes, max_size: Optional[tuple] = None) -> Optional[bytes]:
        """Generate thumbnail bytes from image bytes."""
        return ThumbnailService.generate_thumbnail(image_bytes, max_size)

    @classmethod
    def ensure_thumbnail_exists(cls, image_path: str) -> Optional[str]:
        """Ensure thumbnail exists, creating if needed."""
        return ThumbnailService.ensure_thumbnail_exists(image_path)
