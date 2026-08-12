"""Helpers to ingest image folders by converting them into temporary ZIP files.

These helpers are intentionally additive: existing ZIP-based upload/reupload
pipelines can continue unchanged by consuming the generated ZIP path.
"""

import os
import shutil
import uuid
import zipfile

from django.conf import settings

from core.services.background_worker import ensure_temp_directory, cleanup_temp_file
from core.utils.upload_security import validate_zip_safety


ALLOWED_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic', '.heif', '.hei')
MAX_SINGLE_IMAGE_BYTES = 30 * 1024 * 1024  # 30 MB
MAX_FOLDER_IMAGE_COUNT = 100000


def _normalize_archive_name(name):
    raw_name = str(name or '').replace('\\', '/').strip().lstrip('/')
    if not raw_name:
        return ''

    parts = []
    for segment in raw_name.split('/'):
        segment = segment.strip()
        if not segment or segment in ('.', '..'):
            continue
        parts.append(segment)

    if not parts:
        return ''

    return '/'.join(parts)


def _is_allowed_image_name(name):
    lower_name = str(name or '').lower()
    return lower_name.endswith(ALLOWED_IMAGE_EXTENSIONS)


def _make_temp_zip_path(prefix='folder_images'):
    temp_dir = ensure_temp_directory()
    file_name = f"{uuid.uuid4().hex[:8]}_{prefix}.zip"
    return os.path.join(temp_dir, file_name)


def _finalize_temp_zip(zip_full_path):
    if not os.path.exists(zip_full_path):
        return None, 'Failed to create temporary ZIP file.'

    ok, err = validate_zip_safety(zip_full_path)
    if not ok:
        cleanup_temp_file(zip_full_path)
        return None, err

    return os.path.relpath(zip_full_path, settings.MEDIA_ROOT), None


def build_zip_from_uploaded_folder_files(uploaded_files, *, chunk_size_bytes=4 * 1024 * 1024):
    """Build a temporary ZIP from uploaded folder files.

    Returns:
        tuple(relative_zip_path|None, image_count:int, error_message|None)
    """
    files = list(uploaded_files or [])
    if not files:
        return None, 0, 'No folder images were provided.'

    zip_full_path = _make_temp_zip_path('folder_upload')
    image_count = 0
    seen_entries = set()

    try:
        with zipfile.ZipFile(zip_full_path, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            for uploaded in files:
                raw_name = getattr(uploaded, 'name', '')
                archive_name = _normalize_archive_name(raw_name)
                if not archive_name:
                    continue
                if not _is_allowed_image_name(archive_name):
                    continue

                file_size = int(getattr(uploaded, 'size', 0) or 0)
                if file_size <= 0 or file_size > MAX_SINGLE_IMAGE_BYTES:
                    continue

                if archive_name in seen_entries:
                    continue
                seen_entries.add(archive_name)

                if hasattr(uploaded, 'seek'):
                    uploaded.seek(0)

                with zf.open(archive_name, 'w') as dst:
                    for chunk in uploaded.chunks(chunk_size=chunk_size_bytes):
                        dst.write(chunk)

                image_count += 1
                if image_count >= MAX_FOLDER_IMAGE_COUNT:
                    break
    except Exception as exc:
        cleanup_temp_file(zip_full_path)
        return None, 0, f'Failed to read folder upload files: {exc}'

    if image_count <= 0:
        cleanup_temp_file(zip_full_path)
        return None, 0, 'No valid image files found in selected folder.'

    relative_zip_path, err = _finalize_temp_zip(zip_full_path)
    if err:
        return None, 0, err

    return relative_zip_path, image_count, None


def build_zip_from_folder_path(folder_path, *, chunk_size_bytes=4 * 1024 * 1024):
    """Build a temporary ZIP by scanning a server-side folder path.

    Returns:
        tuple(relative_zip_path|None, image_count:int, error_message|None)
    """
    raw_path = str(folder_path or '').strip().strip('"').strip("'")
    if not raw_path:
        return None, 0, 'Folder path is empty.'

    normalized_path = os.path.abspath(os.path.expandvars(os.path.expanduser(raw_path)))
    if not os.path.exists(normalized_path):
        return None, 0, 'Folder path does not exist on server.'
    if not os.path.isdir(normalized_path):
        return None, 0, 'Provided path is not a folder.'

    zip_full_path = _make_temp_zip_path('folder_path')
    image_count = 0
    seen_entries = set()

    try:
        with zipfile.ZipFile(zip_full_path, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            for root_dir, _, file_names in os.walk(normalized_path):
                for file_name in file_names:
                    if image_count >= MAX_FOLDER_IMAGE_COUNT:
                        break

                    if not _is_allowed_image_name(file_name):
                        continue

                    file_path = os.path.join(root_dir, file_name)
                    try:
                        file_size = os.path.getsize(file_path)
                    except OSError:
                        continue

                    if file_size <= 0 or file_size > MAX_SINGLE_IMAGE_BYTES:
                        continue

                    relative_name = os.path.relpath(file_path, normalized_path)
                    archive_name = _normalize_archive_name(relative_name)
                    if not archive_name:
                        continue
                    if archive_name in seen_entries:
                        continue
                    seen_entries.add(archive_name)

                    with open(file_path, 'rb') as src, zf.open(archive_name, 'w') as dst:
                        shutil.copyfileobj(src, dst, length=chunk_size_bytes)

                    image_count += 1
                if image_count >= MAX_FOLDER_IMAGE_COUNT:
                    break
    except Exception as exc:
        cleanup_temp_file(zip_full_path)
        return None, 0, f'Failed reading folder path: {exc}'

    if image_count <= 0:
        cleanup_temp_file(zip_full_path)
        return None, 0, 'No valid image files found in folder path.'

    relative_zip_path, err = _finalize_temp_zip(zip_full_path)
    if err:
        return None, 0, err

    return relative_zip_path, image_count, None
