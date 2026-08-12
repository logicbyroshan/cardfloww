"""
Image Service — barrel module.

Composes ImageService from mixins and re-exports MediaResult / ServiceResult.

All external imports remain unchanged:
    from mediafiles.services import ImageService, MediaResult
    from mediafiles.services.image_service import ImageService, MediaResult
"""
from .image_core import MediaResult, ServiceResult, ImageCoreMixin
from .image_compress import ImageCompressMixin
from .image_fields import ImageFieldsMixin
from .image_records import ImageRecordsMixin


class ImageService(ImageCoreMixin, ImageCompressMixin, ImageFieldsMixin, ImageRecordsMixin):
    """
    Service for handling all image operations.

    Responsibilities:
    - Generate unique filenames for images
    - Validate image data
    - Save images to client folders with thumbnails
    - Delete old images when updating
    - Match images from ZIP files to card data

    Storage structure:
    - Original: media/adrsh_img/{client_code}/{filename}.jpg
    - Thumbnail: media/adrsh_img/thumbs/{client_code}/{filename}.jpg
    - Temp: media/temp/ (cleaned after processing)

    Composed from:
      ImageCoreMixin     — filename gen, validation, save/delete, thumbnails
      ImageCompressMixin — quality-only JPEG compression
      ImageFieldsMixin   — field type detection, centralized processor, path retrieval
      ImageRecordsMixin  — single-authority entry points, CardMedia integration
    """
    pass


__all__ = ['ImageService', 'MediaResult', 'ServiceResult']
