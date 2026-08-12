"""
Mediafiles Utilities Module

Contains helper functions for media file handling:
- Folder code generation
- Filename generation (delegated to services.image_rename)
- Path utilities

NO STUBS. Real implementations only.
"""
import os
import re
import random
import string
import logging
from io import BytesIO
from typing import Optional, Tuple, Iterable

from django.core.files.uploadedfile import SimpleUploadedFile

from .constants import VALID_IMAGE_EXTENSIONS

logger = logging.getLogger(__name__)

# Common iPhone formats that need conversion for broad browser preview support.
HEIF_EXTENSIONS = frozenset({'.heic', '.heif', '.hei'})
HEIF_MIME_TYPES = frozenset({
    'image/heic',
    'image/heif',
    'image/heic-sequence',
    'image/heif-sequence',
})

_HEIF_REGISTER_ATTEMPTED = False
_HEIF_REGISTERED = False


def register_heif_opener() -> bool:
    """Register HEIF/HEIC decoder with Pillow when pillow-heif is available."""
    global _HEIF_REGISTER_ATTEMPTED, _HEIF_REGISTERED
    if _HEIF_REGISTER_ATTEMPTED:
        return _HEIF_REGISTERED

    _HEIF_REGISTER_ATTEMPTED = True
    try:
        from pillow_heif import register_heif_opener as _register_heif_opener

        _register_heif_opener()
        _HEIF_REGISTERED = True
    except Exception as exc:
        logger.debug('HEIF opener registration skipped: %s', exc)
        _HEIF_REGISTERED = False

    return _HEIF_REGISTERED


def _content_type_base(content_type: Optional[str]) -> str:
    if not content_type:
        return ''
    return str(content_type).lower().split(';', 1)[0].strip()


def _extension_to_content_type(ext: str) -> str:
    ext = (ext or '').lower()
    mapping = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.heic': 'image/heic',
        '.heif': 'image/heif',
        '.hei': 'image/heic',
    }
    return mapping.get(ext, 'application/octet-stream')


def normalize_image_bytes_for_storage(
    image_bytes: bytes,
    suggested_ext: str = '.jpg',
) -> Tuple[bytes, str, Optional[str]]:
    """Validate image bytes and transcode all supported formats to JPEG."""
    if not image_bytes:
        return image_bytes, _normalize_extension(suggested_ext), 'Image data is empty'

    try:
        from PIL import Image, ImageOps

        # Allow ultra-high-resolution photos/scans (up to 250 MP)
        Image.MAX_IMAGE_PIXELS = 250_000_000

        register_heif_opener()

        with Image.open(BytesIO(image_bytes)) as verify_img:
            verify_img.verify()

        # Canonical storage rule: every uploaded image is stored as JPG.
        # Also cap dimensions + adaptive quality so large phone photos remain lightweight.
        with Image.open(BytesIO(image_bytes)) as src_img:
            working_img = ImageOps.exif_transpose(src_img)
            try:
                if working_img.mode in ('RGBA', 'LA', 'P'):
                    if working_img.mode == 'P':
                        converted = working_img.convert('RGBA')
                        if working_img is not src_img:
                            working_img.close()
                        working_img = converted
                    background = Image.new('RGB', working_img.size, (255, 255, 255))
                    background.paste(working_img, mask=working_img.split()[-1] if 'A' in working_img.mode else None)
                    if working_img is not src_img:
                        working_img.close()
                    working_img = background
                elif working_img.mode != 'RGB':
                    converted = working_img.convert('RGB')
                    if working_img is not src_img:
                        working_img.close()
                    working_img = converted

                max_side = 2400
                min_side = 900
                target_max_bytes = 500_000  # < 500 KB target
                quality_steps = (90, 84, 78, 72, 65, 58, 50, 42)
                resample_filter = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS', Image.LANCZOS)

                def _fit_size(img):
                    width, height = img.size
                    current_max = max(width, height)
                    if current_max <= max_side:
                        return img
                    ratio = max_side / float(current_max)
                    new_w = max(1, int(width * ratio))
                    new_h = max(1, int(height * ratio))
                    return img.resize((new_w, new_h), resample_filter)

                candidate = _fit_size(working_img)
                if candidate is not working_img:
                    working_img.close()
                    working_img = candidate

                compressed = None
                while True:
                    for quality in quality_steps:
                        out = BytesIO()
                        working_img.save(out, format='JPEG', quality=quality, optimize=True, progressive=True)
                        payload = out.getvalue()
                        if compressed is None or len(payload) < len(compressed):
                            compressed = payload
                        if len(payload) <= target_max_bytes:
                            return payload, '.jpg', None

                    width, height = working_img.size
                    if min(width, height) <= min_side:
                        break

                    next_w = max(min_side, int(width * 0.85))
                    next_h = max(min_side, int(height * 0.85))
                    if next_w == width and next_h == height:
                        break
                    resized = working_img.resize((next_w, next_h), resample_filter)
                    if working_img is not src_img:
                        working_img.close()
                    working_img = resized

                return compressed or image_bytes, '.jpg', None
            finally:
                if working_img is not src_img:
                    working_img.close()
    except Exception as exc:
        return image_bytes, _normalize_extension(suggested_ext), f'Invalid image: {exc}'


def normalize_uploaded_image(
    uploaded_file,
    *,
    max_bytes: int,
    allowed_extensions: Iterable[str],
    allowed_mime_types: Iterable[str],
) -> Tuple[Optional[object], Optional[str]]:
    """Validate upload and convert HEIC/HEIF to JPEG when needed."""
    if not uploaded_file:
        return None, None

    size = getattr(uploaded_file, 'size', 0) or 0
    if size > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        return None, f'Image must be {max_mb} MB or smaller'

    name = str(getattr(uploaded_file, 'name', '') or '').strip()
    ext = os.path.splitext(name)[1].lower()
    ct = _content_type_base(getattr(uploaded_file, 'content_type', '') or '')

    # Normalize non-standard but common MIME aliases sent by Android camera
    if ct == 'image/jpg':
        ct = 'image/jpeg'

    allowed_exts = {str(v).lower() for v in (allowed_extensions or [])}
    allowed_mimes = {str(v).lower() for v in (allowed_mime_types or [])}

    if ext and ext not in allowed_exts:
        return None, 'Only JPG, PNG, WEBP, GIF, HEIC, and HEIF images are allowed'
    # Allow application/octet-stream or image/octet-stream (generic Android binary) if ext is a valid image ext
    if ct in ('application/octet-stream', 'image/octet-stream') and ext in allowed_exts:
        ct = ''  # treat as unspecified so we skip MIME check
    if ct and ct not in allowed_mimes:
        return None, 'Unsupported image content type'

    try:
        uploaded_file.seek(0)
        image_bytes = uploaded_file.read()
        uploaded_file.seek(0)
    except Exception:
        return None, 'Unable to read uploaded image'

    normalized_bytes, normalized_ext, err = normalize_image_bytes_for_storage(
        image_bytes,
        suggested_ext=ext or '.jpg',
    )
    if err:
        if ext in HEIF_EXTENSIONS or ct in HEIF_MIME_TYPES:
            return None, 'HEIC image could not be decoded. Please try JPG/PNG or enable HEIC decoder support.'
        return None, 'Uploaded file is not a valid image.'

    should_convert = (
        normalized_ext != (ext or normalized_ext)
        or normalized_bytes != image_bytes
    )
    if not should_convert:
        return uploaded_file, None

    stem = os.path.splitext(name)[0].strip() or 'image'
    normalized_name = f'{stem}{normalized_ext}'
    normalized_ct = _extension_to_content_type(normalized_ext)

    return SimpleUploadedFile(
        normalized_name,
        normalized_bytes,
        content_type=normalized_ct,
    ), None


# =============================================================================
# FOLDER CODE GENERATION
# =============================================================================

def generate_folder_code_from_name(name: str) -> str:
    """Generate a 5-character code from client name."""
    if not name:
        return generate_unique_suffix()
    words = re.sub(r'[^a-zA-Z0-9\s]', '', name).split()
    words = [w for w in words if w]
    if not words:
        return generate_unique_suffix()
    code = ''
    if len(words) >= 3:
        for word in words[:5]:
            if word:
                code += word[0].upper()
    elif len(words) == 2:
        code = words[0][:3].upper() + words[1][:2].upper()
    else:
        code = words[0][:5].upper()
    code = code[:5].ljust(5, 'X')
    return code


def generate_unique_suffix(length: int = 5) -> str:
    """Generate random alphanumeric suffix for folder codes."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


# =============================================================================
# FILENAME GENERATION (restored from backup — critical for unique filenames)
# =============================================================================

def generate_image_filename(batch_counter: int = 1, extension: str = '.jpg', upload_prefix: str = 'a') -> str:
    """
    Generate a unique filename for newly uploaded images.
    Format: {a|c}{HHMMSSmmmuuuCC}.ext (15 chars before extension)
    
    Args:
        batch_counter: Sequential number within current upload batch (1-99)
        extension: File extension including dot
    
    Returns:
        New filename string (role prefix + 14 digits + extension)
    """
    from .services.image_rename import ImageRenamer

    return ImageRenamer.generate_filename(
        batch_counter=batch_counter,
        extension=extension,
        upload_prefix=upload_prefix,
    )


def generate_updated_filename(existing_path: str, new_extension: Optional[str] = None, upload_prefix: str = 'a') -> str:
    """
    Generate updated filename for existing images (update/reupload).
    Keeps the ORIGINAL base token and adds underscore + 6-digit HHMMSS.
    Base token can be either legacy 14-digit or new prefixed (a/c + 14-digit).
    """
    from .services.image_rename import ImageRenamer

    return ImageRenamer.generate_updated_filename(
        existing_path=existing_path,
        new_extension=new_extension,
        upload_prefix=upload_prefix,
    )


def _normalize_extension(ext: str) -> str:
    """Normalize file extension to lowercase with leading dot."""
    if not ext:
        return '.jpg'
    ext = ext.lower()
    if not ext.startswith('.'):
        ext = '.' + ext
    if ext not in VALID_IMAGE_EXTENSIONS:
        return '.jpg'
    return ext


# =============================================================================
# PATH UTILITIES
# =============================================================================

def get_client_folder_path(folder_code: str) -> str:
    """Get the folder path for client images."""
    from .constants import CLIENT_IMAGE_BASE_FOLDER
    return f"{CLIENT_IMAGE_BASE_FOLDER}/{folder_code}"


def normalize_image_identifier(identifier: str) -> str:
    """Normalize an image identifier for consistent matching."""
    if not identifier:
        return ''
    result = str(identifier).strip()
    for ext in VALID_IMAGE_EXTENSIONS:
        if result.lower().endswith(ext):
            result = result[:-len(ext)]
            break
    try:
        num = float(result)
        if num == int(num):
            result = str(int(num))
    except (ValueError, TypeError):
        pass
    result = ' '.join(result.split()).upper()
    return result


def is_valid_image_path(path: Optional[str]) -> bool:
    """Check if a path represents a valid image path (not a placeholder)."""
    if not path:
        return False
    if path in ['NOT_FOUND', '', 'PENDING', None]:
        return False
    if path.startswith('PENDING:'):
        return False
    return True


def get_card_photo_url(card, field_data: Optional[dict] = None) -> Optional[str]:
    """
    Get the display photo URL for an IDCard, checking field_data first
    then falling back to the deprecated card.photo ImageField.

    Returns a URL string like '/media/adarshimg/...' or None.
    """
    from django.conf import settings
    from .constants import IMAGE_FIELD_TYPES

    fd = field_data if field_data is not None else (card.field_data or {})

    def _looks_like_image_field_key(key: str) -> bool:
        normalized = re.sub(r'[^A-Z0-9]+', '', str(key or '').upper())
        if not normalized:
            return False
        return any(token in normalized for token in (
            'PHOTO', 'IMAGE', 'PICTURE', 'PIC', 'SIGNATURE', 'BARCODE', 'QRCODE'
        ))

    # 1. Check image fields in field_data (canonical source)
    #    Try well-known photo field names first
    main_photo_keys = ('PHOTO', 'Photo', 'photo', 'student_photo', 'student photo', 'image')
    has_photo_key = False
    for key in fd.keys():
        if str(key).strip().lower() in [k.lower() for k in main_photo_keys]:
            has_photo_key = True
            val = fd.get(key, '')
            if val and is_valid_image_path(val):
                return _ensure_media_url(val, settings.MEDIA_URL)

    if has_photo_key:
        return None

    # If the card explicitly carries image-like field keys, prefer their values
    # when present; otherwise treat explicit blank values as a deliberate
    # removal instead of falling back to the legacy ImageField.
    image_keys = [k for k in fd.keys() if _looks_like_image_field_key(k)]
    if image_keys:
        for k in image_keys:
            val = fd.get(k, '')
            if isinstance(val, str) and is_valid_image_path(val):
                return _ensure_media_url(val, settings.MEDIA_URL)
        return None

    # Scan remaining fields for image-like paths
    for val in fd.values():
        if isinstance(val, str) and is_valid_image_path(val):
            if 'adarshimg/' in val or val.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                return _ensure_media_url(val, settings.MEDIA_URL)

    # 2. Legacy fallback: deprecated photo ImageField
    if card.photo:
        try:
            return card.photo.url
        except Exception as exc:
            logger.debug('Failed resolving legacy card.photo URL: %s', exc)

    return None


def _ensure_media_url(path: str, media_url: str = '/media/') -> str:
    """Ensure a relative media path has the proper /media/ prefix."""
    if path.startswith(('/', 'http://', 'https://')):
        return path
    return f'{media_url}{path}'
