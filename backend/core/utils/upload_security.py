"""
Upload Security Utilities

Centralized validation for uploaded files: ZIP bomb detection, nested ZIP rejection,
image validation, and XLSX safety checks.

RULES:
- Do NOT change business logic or UI behavior.
- Only provide safety validation helpers.
"""
import os
import logging
import zipfile

logger = logging.getLogger(__name__)

# ==================== ZIP SAFETY CONSTANTS ====================
MAX_ZIP_COMPRESSION_RATIO = 100     # Reject entries with ratio > 100:1
MAX_ZIP_ENTRY_COUNT = 5000          # Max files inside a single ZIP
MAX_ZIP_TOTAL_EXTRACTED = 1 * 1024 * 1024 * 1024  # 1 GB total extracted size
MAX_ZIP_SINGLE_ENTRY = 30 * 1024 * 1024      # 30 MB per single entry (matches image upload limit)
NESTED_ZIP_EXTENSIONS = {'.zip', '.7z', '.rar', '.tar', '.gz', '.bz2'}

# Image extensions allowed in ZIP files
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}


def validate_zip_safety(zip_path_or_file, *, max_entries=None, max_total_bytes=None):
    """
    Validate a ZIP file for safety: bomb detection, nested ZIP rejection.
    
    Args:
        zip_path_or_file: Path string or file-like object to a ZIP file.
        max_entries: Maximum number of entries allowed (default: MAX_ZIP_ENTRY_COUNT).
        max_total_bytes: Maximum total uncompressed bytes (default: MAX_ZIP_TOTAL_EXTRACTED).
    
    Returns:
        (ok: bool, error_message: str|None)
    """
    max_entries = max_entries or MAX_ZIP_ENTRY_COUNT
    max_total_bytes = max_total_bytes or MAX_ZIP_TOTAL_EXTRACTED
    
    try:
        # Open the ZIP
        if isinstance(zip_path_or_file, str):
            zf = zipfile.ZipFile(zip_path_or_file, 'r')
        elif hasattr(zip_path_or_file, 'temporary_file_path'):
            zf = zipfile.ZipFile(zip_path_or_file.temporary_file_path(), 'r')
        else:
            zip_path_or_file.seek(0)
            zf = zipfile.ZipFile(zip_path_or_file, 'r')
        
        with zf:
            entries = zf.infolist()
            
            # Check entry count
            if len(entries) > max_entries:
                return False, f'ZIP contains too many files ({len(entries)}). Maximum: {max_entries}'
            
            total_uncompressed = 0
            for info in entries:
                if info.is_dir():
                    continue
                
                # Check for path traversal (e.g. ../../etc/passwd)
                # Normalize and reject any entry that escapes the extraction root
                clean_name = os.path.normpath(info.filename)
                if clean_name.startswith('..') or os.path.isabs(clean_name):
                    return False, f'ZIP contains path traversal entry: {info.filename}. Upload rejected.'
                
                # Check for nested ZIP files
                entry_ext = os.path.splitext(info.filename)[1].lower()
                if entry_ext in NESTED_ZIP_EXTENSIONS:
                    return False, f'ZIP contains nested archive: {info.filename}. Nested archives are not allowed.'
                
                # Check compression ratio (bomb detection)
                if info.compress_size > 0:
                    ratio = info.file_size / info.compress_size
                    if ratio > MAX_ZIP_COMPRESSION_RATIO:
                        return False, f'Suspicious compression ratio detected ({ratio:.0f}:1). Upload rejected.'
                
                # Accumulate total uncompressed size
                total_uncompressed += info.file_size
                if total_uncompressed > max_total_bytes:
                    max_mb = max_total_bytes / (1024 * 1024)
                    return False, f'ZIP total extracted size exceeds {max_mb:.0f} MB limit.'
                
                # Check single entry size
                if info.file_size > MAX_ZIP_SINGLE_ENTRY:
                    # Don't reject — just skip large entries during extraction.
                    # This is informational; the extraction code handles per-file limits.
                    pass
        
        return True, None
    
    except zipfile.BadZipFile:
        return False, 'Invalid or corrupted ZIP file.'
    except Exception as e:
        logger.warning("ZIP safety validation error: %s", e)
        return False, 'Could not validate ZIP file.'


def validate_image_extension(filename):
    """
    Check if filename has an allowed image extension.
    Returns (ok: bool, ext: str).
    """
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS, ext


def validate_xlsx_safe(file_path_or_bytes):
    """
    Safely validate an XLSX file using openpyxl with read_only mode.
    Returns (ok: bool, error_message: str|None).
    """
    try:
        import openpyxl
        if isinstance(file_path_or_bytes, (str, os.PathLike)):
            wb = openpyxl.load_workbook(file_path_or_bytes, read_only=True, data_only=True)
        else:
            from io import BytesIO
            wb = openpyxl.load_workbook(BytesIO(file_path_or_bytes), read_only=True, data_only=True)
        wb.close()
        return True, None
    except Exception as e:
        return False, f'Invalid XLSX file: {e}'
