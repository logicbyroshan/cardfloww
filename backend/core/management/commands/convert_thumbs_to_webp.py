"""
Management command to convert existing JPEG thumbnails to WebP format.

The thumbnail system now generates .webp thumbnails, but existing thumbs
on disk are still .jpg. This one-time migration converts them in-place.

Usage:
    python manage.py convert_thumbs_to_webp            # dry-run (report only)
    python manage.py convert_thumbs_to_webp --apply     # actually convert
"""
import os
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

THUMB_EXTENSIONS = ('.jpg', '.jpeg')


class Command(BaseCommand):
    help = 'Convert existing JPEG thumbnails in thumbs/ folders to WebP format.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Actually perform the conversion. Without this flag, only a dry-run report is shown.',
        )
        parser.add_argument(
            '--quality',
            type=int,
            default=85,
            help='WebP quality (1-100). Default: 85.',
        )
        parser.add_argument(
            '--delete-old',
            action='store_true',
            default=True,
            help='Delete original .jpg thumbnail after successful conversion (default: True).',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        quality = options['quality']
        delete_old = options['delete_old']

        media_root = str(settings.MEDIA_ROOT)
        thumbs_base = os.path.join(media_root, 'adarshimg')

        if not os.path.isdir(thumbs_base):
            self.stderr.write(self.style.ERROR(f'Image folder not found: {thumbs_base}'))
            return

        # Collect all .jpg/.jpeg files inside any thumbs/ subfolder
        jpg_thumbs = []
        for dirpath, _dirnames, filenames in os.walk(thumbs_base):
            # Only process files that are inside a /thumbs/ directory
            rel = os.path.relpath(dirpath, thumbs_base).replace('\\', '/')
            if '/thumbs' not in f'/{rel}/' and rel != 'thumbs' and not rel.startswith('thumbs/') and not rel.startswith('thumbs\\'):
                continue
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in THUMB_EXTENSIONS:
                    jpg_thumbs.append(os.path.join(dirpath, fname))

        total = len(jpg_thumbs)
        if total == 0:
            self.stdout.write(self.style.SUCCESS('No JPEG thumbnails found — nothing to convert.'))
            return

        if not apply:
            self.stdout.write(self.style.WARNING(
                f'[DRY RUN] Found {total} JPEG thumbnail(s) to convert. '
                f'Run with --apply to perform the conversion.'
            ))
            for p in jpg_thumbs[:20]:
                self.stdout.write(f'  {os.path.relpath(p, media_root)}')
            if total > 20:
                self.stdout.write(f'  ... and {total - 20} more')
            return

        # Import PIL only when actually converting
        try:
            from PIL import Image
        except ImportError:
            self.stderr.write(self.style.ERROR('Pillow is not installed. Run: pip install Pillow'))
            return

        converted = 0
        skipped = 0
        errors = 0

        for idx, jpg_path in enumerate(jpg_thumbs, 1):
            webp_path = os.path.splitext(jpg_path)[0] + '.webp'

            # Skip if webp already exists
            if os.path.exists(webp_path):
                skipped += 1
                continue

            try:
                with Image.open(jpg_path) as img:
                    if img.mode in ('RGBA', 'LA', 'P'):
                        img = img.convert('RGBA')
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')
                    img.save(webp_path, format='WEBP', quality=quality, method=4)

                # Verify the webp was written
                if os.path.exists(webp_path) and os.path.getsize(webp_path) > 0:
                    converted += 1
                    if delete_old:
                        os.remove(jpg_path)
                else:
                    errors += 1
                    self.stderr.write(self.style.ERROR(f'  WebP file empty/missing: {webp_path}'))

            except Exception as e:
                errors += 1
                logger.error('Failed to convert %s: %s', jpg_path, e)
                self.stderr.write(self.style.ERROR(f'  Error converting {jpg_path}: {e}'))

            # Progress every 100 files
            if idx % 100 == 0:
                self.stdout.write(f'  Progress: {idx}/{total} ...')

        self.stdout.write(self.style.SUCCESS(
            f'Done. Converted: {converted}, Skipped (webp exists): {skipped}, Errors: {errors}'
        ))
