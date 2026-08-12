"""
Image Compress — image compression mixin.

Provides: ImageCompressMixin (compress_to_target_size).

Part of the ImageService mixin split.
"""
import logging
from io import BytesIO

logger = logging.getLogger(__name__)


class ImageCompressMixin:
    """
    Image compression: quality-only JPEG compression to meet a target file size.
    """

    # Target size for stored images (500 KB)
    MAX_STORED_IMAGE_SIZE = 500 * 1024

    @classmethod
    def compress_to_target_size(
        cls,
        image_bytes: bytes,
        target_size: int = None,
        min_quality: int = 10,
    ) -> bytes:
        """
        Compress image to *target_size* bytes by reducing JPEG quality only.

        RULES:
          - Dimensions are NEVER reduced.
          - Only JPEG quality is adjusted.
          - If already <= target_size, returns original bytes unchanged.
          - Uses a temporary file to avoid memory spikes on very large images.

        Returns:
            Compressed (or original) image bytes.
        """
        import tempfile
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 250_000_000

        target_size = target_size or cls.MAX_STORED_IMAGE_SIZE

        if len(image_bytes) <= target_size:
            return image_bytes

        try:
            img = Image.open(BytesIO(image_bytes))
            try:
                # Preserve original dimensions — never resize
                if img.mode in ('RGBA', 'LA', 'P'):
                    bg = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    bg.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                    img.close()
                    img = bg
                elif img.mode != 'RGB':
                    img_c = img.convert('RGB')
                    img.close()
                    img = img_c

                # Handle EXIF orientation
                try:
                    from PIL import ImageOps
                    img = ImageOps.exif_transpose(img)
                except Exception as exc:
                    logger.debug('EXIF transpose skipped during compression: %s', exc)

                # Binary-search for best quality that meets target
                lo, hi = min_quality, 95
                best_bytes = None

                while lo <= hi:
                    mid = (lo + hi) // 2
                    tmp = tempfile.SpooledTemporaryFile(max_size=target_size)
                    try:
                        img.save(tmp, format='JPEG', quality=mid, optimize=True)
                        size = tmp.tell()
                        tmp.seek(0)
                        if size <= target_size:
                            best_bytes = tmp.read()
                            lo = mid + 1  # try higher quality
                        else:
                            hi = mid - 1  # need lower quality
                    finally:
                        tmp.close()

                if best_bytes is not None:
                    logger.info(
                        "Compressed image from %d KB to %d KB (quality binary-search)",
                        len(image_bytes) // 1024, len(best_bytes) // 1024,
                    )
                    return best_bytes

                # Fallback: save at min_quality
                buf = BytesIO()
                img.save(buf, format='JPEG', quality=min_quality, optimize=True)
                result = buf.getvalue()
                logger.warning(
                    "Image compressed to %d KB at minimum quality %d (target was %d KB)",
                    len(result) // 1024, min_quality, target_size // 1024,
                )
                return result
            finally:
                img.close()
        except Exception as e:
            logger.error("compress_to_target_size failed: %s", e)
            return image_bytes  # return original on error
