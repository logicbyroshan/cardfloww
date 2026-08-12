# =============================================================================
# MEDIAFILES APP - Media and Image Handling
# =============================================================================
#
# This app is responsible for ALL media/image-related operations:
# - Image storage and retrieval
# - Thumbnail generation
# - Client folder management
# - Image validation and processing
# - Filename generation
#
# Other apps should import from here:
#   from mediafiles.services import ImageService
#   from mediafiles.constants import VALID_IMAGE_EXTENSIONS
# =============================================================================

from .services import ImageService, MediaResult

__all__ = [
    'ImageService',
    'MediaResult',
]
