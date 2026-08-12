"""
Base Service Module
Contains: ServiceResult dataclass, BaseService class, common utilities
"""
from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List, Union
import os
import re

# Import canonical constants from mediafiles
from mediafiles.constants import (
    IMAGE_FIELD_TYPES,
    IMAGE_FIELD_NAME_PATTERNS,
    VALID_IMAGE_EXTENSIONS,
)


@dataclass
class ServiceResult:
    """
    Standard result object returned by all service methods.
    
    Usage:
        # Success
        return ServiceResult(success=True, data={'client': client_dict}, message='Created!')
        
        # Failure
        return ServiceResult(success=False, message='Email already exists')
        
        # In views
        result = ClientService.create(data)
        if result.success:
            return JsonResponse({'success': True, 'client': result.data['client']})
        return JsonResponse({'success': False, 'message': result.message}, status=400)
    """
    success: bool
    message: str = ''
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
    def to_response_dict(self) -> dict:
        """Convert to dict suitable for JsonResponse"""
        response = {'success': self.success}
        if self.message:
            response['message'] = self.message
        if self.data:
            response.update(self.data)
        if self.errors:
            response['errors'] = self.errors
        return response


class BaseService:
    """
    Base class for all services.
    Provides common utilities and patterns.
    
    NOTE: Uses canonical constants from mediafiles.constants
    """
    
    # Re-export constants as class attributes for backward compatibility
    IMAGE_FIELD_TYPES = IMAGE_FIELD_TYPES
    IMAGE_FIELD_NAME_PATTERNS = IMAGE_FIELD_NAME_PATTERNS
    VALID_IMAGE_EXTENSIONS = VALID_IMAGE_EXTENSIONS
    
    # Valid ID card statuses
    VALID_STATUSES = ['pending', 'verified', 'pool', 'approved', 'download', 'reprint']
    
    # Canonical image column order for consistent display
    # Must stay in sync with core/templatetags/custom_filters.py IMAGE_COLUMN_ORDER
    IMAGE_COLUMN_ORDER = [
        'photo', 'father photo', 'f photo',
        'mother photo', 'm photo',
        'rel photo', 'relation photo', 'rel 1 photo', 'rel 2 photo',
        'signature', 'sign',
        'barcode',
        'qr code', 'qr_code', 'qr',
    ]
    
    @staticmethod
    def parse_bool(value: Any) -> bool:
        """Parse boolean from various input types"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return bool(value)
    
    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalize field names for comparison (remove spaces, underscores, etc.)"""
        if not name:
            return ''
        return re.sub(r'[^a-z0-9]', '', name.lower())
    
    # Common abbreviations used in image field names
    # Maps short form -> canonical form for matching
    IMAGE_FIELD_ABBREVIATIONS = {
        'f': 'father',
        'father': 'father',
        'm': 'mother',
        'mother': 'mother',
        'b': 'back',
        'back': 'back',
        'photo': 'photo',
        'pic': 'photo',
        'img': 'image',
        'image': 'image',
        'sign': 'signature',
        'sig': 'signature',
        'signature': 'signature',
        'qr': 'qr',
        'qrcode': 'qr',
        'barcode': 'barcode',
    }

    # Tokens that describe media type, not semantic field identity.
    _IMAGE_DESCRIPTOR_TOKENS = {'photo', 'image', 'img', 'pic', 'picture'}

    @classmethod
    def normalize_image_field_name(cls, name: str) -> str:
        """
        Normalize an image field name by expanding abbreviations.
        E.g. "F PHOTO" -> "father photo", "M PHOTO" -> "mother photo",
             "B PHOTO" -> "back photo", "SIGN" -> "signature"
        """
        if not name:
            return ''
        # Split into words on spaces, underscores, hyphens, dots
        words = re.split(r'[\s_\-\.]+', name.lower().strip())
        expanded = []
        for word in words:
            word = re.sub(r'[^a-z0-9]', '', word)
            if word:
                expanded.append(cls.IMAGE_FIELD_ABBREVIATIONS.get(word, word))
        return ' '.join(expanded)

    @classmethod
    def find_best_image_field_match(cls, header: str, image_fields: 'List[str]') -> 'Optional[str]':
        """
        Find the best matching image field for an XLSX/CSV header.
        Uses abbreviation expansion + Levenshtein fuzzy matching.

        Returns matched field name or None.
        """
        if not header or not image_fields:
            return None

        # 1. Exact case-insensitive match
        header_upper = header.upper().strip()
        for field in image_fields:
            if field.upper().strip() == header_upper:
                return field

        # 2. Normalized alphanumeric match (existing behavior)
        header_normalized = cls.normalize_name(header)
        for field in image_fields:
            if cls.normalize_name(field) == header_normalized:
                return field

        # 3. Abbreviation-expanded match (F PHOTO == FATHER PHOTO)
        header_expanded = cls.normalize_image_field_name(header)
        for field in image_fields:
            if cls.normalize_image_field_name(field) == header_expanded:
                return field

        # 3b. Relaxed semantic match: ignore generic media tokens so
        # SIGNATURE matches SIGNATURE PHOTO and QR matches QR CODE PHOTO.
        header_semantic = cls._semantic_image_match_key(header_expanded)
        if header_semantic:
            for field in image_fields:
                if cls._semantic_image_match_key(field) == header_semantic:
                    return field

        # 4. Levenshtein distance on expanded names
        best_match = None
        best_distance = float('inf')
        for field in image_fields:
            field_expanded = cls.normalize_image_field_name(field)
            distance = cls.levenshtein_distance(header_expanded, field_expanded)
            max_distance = 2 if len(field_expanded) >= 8 else 1
            if distance <= max_distance and distance < best_distance:
                best_distance = distance
                best_match = field

        return best_match

    @classmethod
    def _semantic_image_match_key(cls, value: str) -> str:
        """
        Build a semantic key for image-field comparison.

        Drops generic media words (photo/image/pic) so headers without suffixes
        still match configured image columns.
        """
        expanded = cls.normalize_image_field_name(value)
        if not expanded:
            return ''

        # Normalize common variants before tokenization.
        normalized = expanded.replace('qr code', 'qr').replace('bar code', 'barcode')
        tokens = [tok for tok in normalized.split(' ') if tok]
        semantic_tokens = [tok for tok in tokens if tok not in cls._IMAGE_DESCRIPTOR_TOKENS]

        return ' '.join(semantic_tokens).strip()

    @staticmethod
    def normalize_image_identifier(identifier: str) -> str:
        """
        Normalize an image identifier for consistent matching.
        
        Handles:
        - Case insensitivity (P1 == p1)
        - Whitespace (leading/trailing/multiple spaces)
        - Numeric formats (1.0 -> 1, 001 -> 1 for pure numbers)
        - Extension removal if present (.jpg, .png, etc.)
        
        Args:
            identifier: Raw identifier from Excel or ZIP filename
            
        Returns:
            Normalized uppercase string for matching
        """
        if not identifier:
            return ''
        
        # Convert to string and strip whitespace
        result = str(identifier).strip()
        
        # Handle numeric types (from Excel: 1.0 -> "1")
        try:
            float_val = float(result)
            if float_val == int(float_val):
                result = str(int(float_val))
        except (ValueError, TypeError):
            pass
        
        # Remove common image extensions if present
        lower_result = result.lower()
        for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
            if lower_result.endswith(ext):
                result = result[:-len(ext)]
                break
        
        # Normalize internal whitespace (multiple spaces -> single)
        result = ' '.join(result.split())
        
        # Convert to uppercase for consistent matching
        return result.upper()
    
    @staticmethod
    def uppercase_dict_values(data: dict) -> dict:
        """Convert all string values in dict to uppercase"""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = value.upper()
            else:
                result[key] = value
        return result
    
    @classmethod
    def is_image_field_by_name(cls, field_name: str) -> bool:
        """Check if field name suggests it's an image field"""
        if not field_name:
            return False
        if str(field_name).lower().endswith('path'):
            return False
        import re
        name_lower = field_name.lower()
        normalized_name = re.sub(r'[\s_-]+', ' ', name_lower).strip()

        if re.search(r'\b(?:rel(?:ation)?)\s*(?:1|one|2|two)\s*(?:photo|image|pic|picture)\b', normalized_name):
            return True

        # Use word boundary matching to avoid false positives like 'designation' matching 'sign'
        for pattern in cls.IMAGE_FIELD_NAME_PATTERNS:
            # Create regex with word boundary for patterns that could be substrings
            if re.search(r'\b' + re.escape(pattern) + r'\b', name_lower):
                return True
            # Also check exact match or if field name starts/ends with pattern
            if name_lower == pattern:
                return True
        return False
    
    @classmethod
    def is_show_path_enabled(cls, field: dict) -> bool:
        """Check if show_path flag is enabled for a field configuration dict."""
        if not isinstance(field, dict):
            return False
        val = field.get('show_path')
        if isinstance(val, str):
            return val.strip().lower() in ('true', '1', 'yes', 'on')
        return bool(val)

    @classmethod
    def extract_photo_path_display_value(cls, card, field_name: str, val: Any = None) -> str:
        """
        Extract the image filename without extension for a photo field.
        Handles PENDING: prefix, Windows/POSIX path separators, file extensions,
        and fallbacks to card.field_data (PATH key) or card.photo.
        """
        import os
        clean_val = val or ''
        if not clean_val and card:
            fd = getattr(card, 'field_data', {}) or {}
            clean_val = fd.get('PATH') or fd.get('path') or fd.get('Path') or ''
            if not clean_val and hasattr(card, 'photo') and card.photo:
                try:
                    clean_val = card.photo.name or ''
                except Exception:
                    pass

        if not clean_val or not isinstance(clean_val, str):
            return ''

        if clean_val.startswith('PENDING:'):
            clean_val = clean_val[8:]

        clean_val = clean_val.strip()
        if not clean_val:
            return ''

        clean_val = clean_val.replace('\\', '/')
        filename = clean_val.split('/')[-1]
        name_without_ext, _ = os.path.splitext(filename)
        return name_without_ext

    @classmethod
    def is_image_field(cls, field: dict) -> bool:
        """Check if a field is an image field by type OR name"""
        if not isinstance(field, dict):
            return False
        field_type = field.get('type', 'text')
        field_name = field.get('name', '')
        return field_type in cls.IMAGE_FIELD_TYPES or cls.is_image_field_by_name(field_name)
    
    @classmethod
    def get_text_fields(cls, table_fields: List[dict]) -> List[dict]:
        """Filter table fields to only text fields (exclude images)"""
        return [f for f in table_fields if not cls.is_image_field(f)]
    
    @classmethod
    def get_image_fields(cls, table_fields: List[dict]) -> List[dict]:
        """Filter table fields to only image fields"""
        return [f for f in table_fields if cls.is_image_field(f)]
    
    @classmethod
    def get_image_field_names(cls, table_fields: List[dict], mandatory_only: bool = False) -> List[str]:
        """Get list of image field names from table fields.
        If mandatory_only=True, only returns image fields marked as mandatory."""
        result = []
        for f in table_fields:
            if cls.is_image_field(f):
                if mandatory_only and not f.get('mandatory', False):
                    continue
                name = f.get('name')
                if name:
                    result.append(name)
        return result
    
    @classmethod
    def _get_image_sort_key(cls, field_name: str) -> int:
        """
        Get sort order for an image field based on canonical display order.
        Photo(0) → Father Photo(1) → Mother Photo(2) → Signature(3) → Barcode(4) → QR(5)
        
        Must stay in sync with _get_image_sort_key in core/templatetags/custom_filters.py.
        """
        name_lower = field_name.lower().strip()
        
        # Check specific qualifiers FIRST (before generic "photo" match)
        if 'father' in name_lower or re.match(r'^f\s+', name_lower):
            return 1   # Father Photo / F Photo
        if 'mother' in name_lower or re.match(r'^m\s+', name_lower):
            return 2   # Mother Photo / M Photo
        if re.search(r'\b(?:rel(?:ation)?)\s*[_-]?\s*(?:1|one|2|two)\s*(?:photo|image|pic|picture)\b', name_lower):
            return 1   # Relation photos (REL_1PHOTO / REL_2PHOTO)
        if re.search(r'\bsign\b|\bsignature\b', name_lower):
            return 3   # Signature / Sign
        if 'barcode' in name_lower:
            return 4   # Barcode
        if 'qr' in name_lower:
            return 5   # QR Code
        if 'photo' in name_lower or 'image' in name_lower or 'pic' in name_lower:
            return 0   # Photo (generic/standalone)
        if 'back' in name_lower:
            return 6   # Back photo
        return 999  # Unknown image types go last
    
    @classmethod
    def reorder_fields_for_display(cls, table_fields: List[dict]) -> List[dict]:
        """
        Preserve configured table field order for display/serialization.
        
        Must mirror reorder_fields_for_display in core/templatetags/custom_filters.py.
        """
        return table_fields
    
    @classmethod
    def is_image_field_name_for_table(cls, field_name: str, table_fields: List[dict]) -> bool:
        """
        Check if a field name is an image field for a specific table.
        Uses case-insensitive matching against the table's field configuration.
        
        Args:
            field_name: The field name to check
            table_fields: List of field configs from Table.fields
            
        Returns:
            True if field_name corresponds to an image field
        """
        if not field_name or not table_fields:
            return False
        
        # Normalize for case-insensitive comparison
        field_name_upper = field_name.upper()
        
        for field in table_fields:
            if not isinstance(field, dict):
                continue
            config_name = field.get('name', '') or ''
            if config_name.upper() == field_name_upper:
                return cls.is_image_field(field)
        
        # Fallback: check by name pattern if field not in table config
        return cls.is_image_field_by_name(field_name)
    
    @classmethod
    def uppercase_field_data_selective(cls, data: dict, table_fields: List[dict]) -> dict:
        """
        Convert text field values to uppercase, preserving image paths as-is.
        
        CRITICAL: Image paths must NOT be uppercased to prevent case-sensitive
        filesystem issues on Linux servers.
        
        Args:
            data: Dict of field_name -> value
            table_fields: List of field configs from Table.fields
            
        Returns:
            Dict with text fields uppercased, image fields preserved
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                # Skip uppercase for image fields - preserve paths exactly
                if cls.is_image_field_name_for_table(key, table_fields):
                    result[key] = value
                else:
                    result[key] = value.upper()
            else:
                result[key] = value
        return result
    
    @staticmethod
    def normalize_image_path(path: str) -> str:
        """
        Normalize an image path to a clean, consistent relative path.
        
        Rules:
        - Convert backslashes to forward slashes (Windows → Linux safe)
        - Remove double slashes
        - Strip leading slashes
        - Strip MEDIA_ROOT prefix if accidentally included
        - Strip absolute HTTP/HTTPS URL host and /media/ prefix if present
        - Strip leading 'media/' prefix if present
        - Preserve PENDING: and NOT_FOUND markers as-is
        - Return empty string for None/empty input
        
        Args:
            path: Raw image path (could be absolute, relative, or mangled)
            
        Returns:
            Clean relative path from MEDIA_ROOT, or marker/empty string
        """
        if not path:
            return ''
        
        path = str(path).strip()
        
        # Preserve special markers
        if path.startswith('PENDING:') or path == 'NOT_FOUND':
            return path
            
        # Strip HTTP/HTTPS host and media prefix if absolute URL
        if '://' in path:
            path = path.split('?', 1)[0].split('#', 1)[0]
            if '/media/' in path:
                path = path[path.find('/media/') + 7:]
            elif 'media/' in path:
                path = path[path.find('media/') + 6:]
        
        # Backslashes → forward slashes
        path = path.replace('\\', '/')
        
        # Remove double slashes
        while '//' in path:
            path = path.replace('//', '/')
        
        # Strip MEDIA_ROOT prefix if accidentally included
        try:
            from django.conf import settings
            import os
            media_root = settings.MEDIA_ROOT.replace('\\', '/')
            if not media_root.endswith('/'):
                media_root += '/'
            if path.startswith(media_root):
                path = path[len(media_root):]
        except Exception:
            pass
        
        # Strip leading /media/ or media/ prefix
        if path.startswith('/media/'):
            path = path[7:]
        elif path.startswith('media/'):
            path = path[6:]
        
        # Strip leading slashes
        path = path.lstrip('/')
        
        return path

    @staticmethod
    def image_path_basename(path: str) -> str:
        """Return only the filename part of an image path or URL-like value."""
        if not path:
            return ''

        raw = str(path).strip()
        if not raw or raw == 'NOT_FOUND' or raw.startswith('PENDING:'):
            return ''

        normalized = raw.replace('\\', '/').split('?', 1)[0].split('#', 1)[0]
        return os.path.basename(normalized).strip()

    @classmethod
    def image_filename_contains_query(cls, path: str, query: str) -> bool:
        """Case-insensitive contains match against image filename basename only."""
        needle = (query or '').strip().lower()
        if not needle:
            return False
        base_name = cls.image_path_basename(path)
        return bool(base_name and needle in base_name.lower())
    
    @staticmethod
    def validate_image_path(path: str, media_root: str = None) -> bool:
        """
        Check if an image path points to an existing file on disk.
        
        Args:
            path: Relative path from MEDIA_ROOT (e.g., 'clients_imgs/example/photo.jpg')
            media_root: Base media directory (defaults to settings.MEDIA_ROOT)
            
        Returns:
            True if file exists, False otherwise
        """
        import os
        from django.conf import settings
        
        if not path:
            return False
        
        # Skip validation for PENDING references
        if path.startswith('PENDING:'):
            return False
        
        # Skip validation for NOT_FOUND markers
        if path == 'NOT_FOUND':
            return False
        
        # Normalize the path first
        clean_path = BaseService.normalize_image_path(path)
        if not clean_path:
            return False
        
        # Build full path
        base = media_root or settings.MEDIA_ROOT
        full_path = os.path.join(base, clean_path)
        
        return os.path.isfile(full_path)
    
    @staticmethod
    def levenshtein_distance(s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings"""
        if len(s1) < len(s2):
            return BaseService.levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]
    
    @classmethod
    def find_best_field_match(cls, header: str, available_fields: List[str]) -> Optional[str]:
        """
        Find best match for a header using fuzzy matching.
        Returns matched field name or None.
        """
        normalized_header = cls.normalize_name(header)
        
        # First try exact match
        for field in available_fields:
            if cls.normalize_name(field) == normalized_header:
                return field
        
        # Then try fuzzy match
        best_match = None
        best_distance = float('inf')
        
        for field in available_fields:
            normalized_field = cls.normalize_name(field)
            distance = cls.levenshtein_distance(normalized_header, normalized_field)
            
            # Allow up to 2 char differences, but for short strings allow only 1
            max_distance = 1 if len(normalized_field) < 5 else 2
            
            if distance <= max_distance and distance < best_distance:
                best_distance = distance
                best_match = field
        
        return best_match
    
    @staticmethod
    def clean_filename_for_export(name: str) -> str:
        """Clean a name for use in export filenames"""
        return re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
    
    @classmethod
    def validate_bulk_upload_data(cls, identifiers_by_field: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Validate bulk upload data for potential issues.
        
        Args:
            identifiers_by_field: Dict mapping field names to list of identifiers
            
        Returns:
            Dict with 'valid' bool, 'warnings' list, and 'duplicates' dict
        """
        warnings = []
        duplicates_by_field = {}
        
        for field_name, identifiers in identifiers_by_field.items():
            # Check for duplicates within same column
            normalized = [cls.normalize_image_identifier(i) for i in identifiers if i]
            seen = set()
            duplicates = set()
            for ident in normalized:
                if ident and ident in seen:
                    duplicates.add(ident)
                seen.add(ident)
            
            if duplicates:
                warnings.append(f"Duplicate identifiers in '{field_name}': {', '.join(list(duplicates)[:5])}")
                duplicates_by_field[field_name] = list(duplicates)
        
        return {
            'valid': len(warnings) == 0,
            'warnings': warnings,
            'duplicates': duplicates_by_field
        }
    
    @classmethod
    def validate_excel_identifiers_early(cls, rows_data: list, image_ref_columns: Dict[str, int]) -> Dict[str, Any]:
        """
        Fail-fast validation: Check for duplicate image identifiers BEFORE processing.
        
        Args:
            rows_data: List of row tuples from Excel
            image_ref_columns: Dict mapping field names to column indices
            
        Returns:
            Dict with 'valid' bool, 'errors' list of duplicate descriptions
        """
        errors = []
        
        for field_name, col_idx in image_ref_columns.items():
            identifiers = []
            for row_num, row in enumerate(rows_data, start=2):
                if col_idx < len(row):
                    cell_value = row[col_idx]
                    if cell_value is not None and str(cell_value).strip():
                        # Handle numeric Excel values
                        if isinstance(cell_value, float) and cell_value == int(cell_value):
                            identifiers.append((str(int(cell_value)), row_num))
                        elif isinstance(cell_value, int):
                            identifiers.append((str(cell_value), row_num))
                        else:
                            identifiers.append((str(cell_value).strip(), row_num))
            
            # Normalize and check for duplicates
            seen = {}  # normalized -> (original, row_num)
            for original, row_num in identifiers:
                normalized = cls.normalize_image_identifier(original)
                if normalized:
                    if normalized in seen:
                        prev_orig, prev_row = seen[normalized]
                        errors.append(
                            f"Duplicate identifier '{original}' in column '{field_name}' "
                            f"at rows {prev_row} and {row_num}"
                        )
                    else:
                        seen[normalized] = (original, row_num)
        
        return {
            'valid': len(errors) == 0,
            'errors': errors[:10]  # Limit to first 10 errors
        }
    
    @classmethod  
    def build_zip_photo_index(cls, zip_photos_dict: Dict[str, bytes]) -> Dict[str, dict]:
        """
        Build a normalized index from ZIP photos for consistent matching.
        
        Args:
            zip_photos_dict: Dict of {filename: image_bytes}
            
        Returns:
            Dict with normalized keys pointing to {bytes, ext, original_name}
        """
        index = {}
        for filename, data in zip_photos_dict.items():
            base_name = filename.split('/')[-1]  # Handle nested paths
            name_without_ext, ext = base_name.rsplit('.', 1) if '.' in base_name else (base_name, 'jpg')
            
            # Normalize the key for matching
            normalized_key = cls.normalize_image_identifier(name_without_ext)
            
            if normalized_key:
                index[normalized_key] = {
                    'bytes': data if isinstance(data, bytes) else data.get('bytes'),
                    'ext': f'.{ext.lower()}' if not ext.startswith('.') else ext.lower(),
                    'original_name': base_name
                }
        
        return index


class StreamingZipIndex:
    """
    A memory-efficient ZIP file handler that builds an index of filenames
    without extracting all content into memory.
    
    Usage:
        with StreamingZipIndex(zip_file_obj) as index:
            # Check if a file exists
            if 'P001' in index:
                # Extract only when needed
                photo_info = index.get_photo('P001')
                image_bytes = photo_info['bytes']
    
    This is preferred over loading entire ZIP into memory for large uploads.
    """
    
    VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    
    def __init__(self, zip_file):
        """
        Initialize with a file-like object or path.
        
        Args:
            zip_file: Django uploaded file, file-like object, or path string
        """
        import zipfile
        
        self._zip_file = zip_file
        self._zf = None
        self._index = {}  # normalized_key -> zip_info
        self._raw_index = {}  # normalized_key -> {ext, original_name, zip_filename}
        
    def __enter__(self):
        import zipfile
        
        # Handle different input types
        if hasattr(self._zip_file, 'temporary_file_path'):
            # Django TemporaryUploadedFile — use disk path directly
            self._zf = zipfile.ZipFile(self._zip_file.temporary_file_path(), 'r')
        elif hasattr(self._zip_file, 'read'):
            # File-like object — read from handle directly (avoids BytesIO copy)
            self._zip_file.seek(0)
            self._zf = zipfile.ZipFile(self._zip_file, 'r')
        else:
            # Assume path string
            self._zf = zipfile.ZipFile(self._zip_file, 'r')
        
        # Build lightweight index (just filenames, no content extraction)
        self._build_index()
        return self
    
    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        if self._zf:
            self._zf.close()
        return False
    
    def _build_index(self):
        """Build the filename index without extracting content."""
        import os
        
        for zip_info in self._zf.infolist():
            if zip_info.is_dir():
                continue
            
            filename = zip_info.filename
            base_name = os.path.basename(filename)
            name_without_ext, ext = os.path.splitext(base_name)
            ext_lower = ext.lower()
            
            if ext_lower not in self.VALID_EXTENSIONS:
                continue
            
            # Normalize for matching
            normalized_key = BaseService.normalize_image_identifier(name_without_ext)
            
            if normalized_key:
                self._index[normalized_key] = zip_info
                self._raw_index[normalized_key] = {
                    'ext': ext_lower,
                    'original_name': base_name,
                    'zip_filename': filename
                }
    
    def __contains__(self, key: str) -> bool:
        """Check if a normalized key exists in the index."""
        normalized = BaseService.normalize_image_identifier(key) if key else None
        return normalized in self._index if normalized else False
    
    def keys(self):
        """Get all normalized keys."""
        return self._index.keys()
    
    def get_photo(self, key: str, validate: bool = True) -> Optional[Dict]:
        """
        Extract and return photo data for a key.
        
        Args:
            key: Identifier to lookup (will be normalized)
            validate: Whether to validate the image bytes
            
        Returns:
            Dict with {bytes, ext, original_name} or None if not found/invalid
        """
        from mediafiles.services import ImageService
        
        normalized = BaseService.normalize_image_identifier(key) if key else None
        if not normalized or normalized not in self._index:
            return None
        
        zip_info = self._index[normalized]
        raw_info = self._raw_index[normalized]
        
        try:
            image_bytes = self._zf.read(zip_info.filename)
            
            if validate:
                is_valid, error_msg = ImageService.validate_image_bytes(image_bytes)
                if not is_valid:
                    return None
            
            return {
                'bytes': image_bytes,
                'ext': raw_info['ext'],
                'original_name': raw_info['original_name']
            }
        except Exception:
            return None
    
    def get_info(self, key: str) -> Optional[Dict]:
        """
        Get metadata about a photo without extracting bytes.
        
        Returns:
            Dict with {ext, original_name, zip_filename} or None
        """
        normalized = BaseService.normalize_image_identifier(key) if key else None
        if not normalized or normalized not in self._raw_index:
            return None
        return self._raw_index[normalized].copy()
