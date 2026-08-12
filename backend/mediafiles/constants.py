"""
Mediafiles Constants Module

Contains all image and media-related constants used across the application.
"""

# =============================================================================
# IMAGE FIELD TYPES
# =============================================================================

# Field types that should be treated as image fields
IMAGE_FIELD_TYPES = [
    'photo',
    'rel_photo',
    # Legacy aliases kept for backward compatibility with older tables
    'mother_photo',
    'father_photo',
    'barcode',
    'qr_code',
    'signature',
    'image',
]

# Field name patterns (for fields that might be labeled as 'text' but are images)
# NOTE: Must stay in sync with static/js/idcard-actions-upload.js IMAGE_FIELD_NAME_PATTERNS
IMAGE_FIELD_NAME_PATTERNS = [
    'photo',
    'f photo',
    'father photo',
    'm photo',
    'mother photo',
    'rel photo',
    'relation photo',
    'relation image',
    'relation pic',
    # Relation-slot image aliases (must include an explicit media keyword)
    'rel 1 photo',
    'rel1photo',
    'rel_1photo',
    'relation 1 photo',
    'relation1photo',
    'relation one photo',
    'rel 2 photo',
    'rel2photo',
    'rel_2photo',
    'relation 2 photo',
    'relation2photo',
    'relation two photo',
    'rel 1 image',
    'rel1image',
    'rel_1image',
    'relation 1 image',
    'relation1image',
    'relation one image',
    'rel 2 image',
    'rel2image',
    'rel_2image',
    'relation 2 image',
    'relation2image',
    'relation two image',
    'rel 1 pic',
    'rel1pic',
    'rel_1pic',
    'relation 1 pic',
    'relation1pic',
    'relation one pic',
    'rel 2 pic',
    'rel2pic',
    'rel_2pic',
    'relation 2 pic',
    'relation2pic',
    'relation two pic',
    'sign',
    'signature',
    'barcode',
    'qr',
    'qr_code',
    'image',
]

# =============================================================================
# FILE EXTENSIONS
# =============================================================================

# Valid image extensions supported for upload
VALID_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic', '.heif']

# =============================================================================
# THUMBNAIL SETTINGS
# =============================================================================

# Default thumbnail dimensions (maintains aspect ratio)
THUMBNAIL_SIZE = (150, 150)

# Suffix added to thumbnail filenames
THUMBNAIL_SUFFIX = '_thumb'

# WebP quality for thumbnails (1-100)
THUMBNAIL_QUALITY = 85

# =============================================================================
# STORAGE PATHS
# =============================================================================

# Base folder for client images (relative to MEDIA_ROOT)
CLIENT_IMAGE_BASE_FOLDER = 'adarshimg'

# Upload paths for specific image types
UPLOAD_PATHS = {
    'staff_images': 'staff_imgs/',
    'client_images': 'clients_imgs/',
    'id_templates': 'id_templates/',
    'id_photos': 'id_photos/',
    'site_assets': 'site/',
}

# =============================================================================
# FILENAME PATTERNS
# =============================================================================

# Pattern for newly uploaded images: role prefix + 14 digits
# Example: a14325123456701.jpg / c14325123456701.jpg
NEW_FILENAME_LENGTH = 15

# Pattern for updated images: original_base + underscore + 6-digit HHMMSS
# New format length: 22  (15 + 1 + 6)
UPDATED_FILENAME_LENGTH = 22

# Legacy compatibility lengths (accepted for existing data)
LEGACY_NEW_FILENAME_LENGTH = 14
LEGACY_UPDATED_FILENAME_LENGTH = 21
LEGACY_FILENAME_LENGTH = 13
