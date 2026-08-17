"""
Exports Utilities Module

Common helper functions used across all export formats.
This module is READ-ONLY - it never mutates data.
"""
import re
import logging
from typing import List, Dict, Any, Optional

# Import canonical constants from mediafiles
from mediafiles.constants import IMAGE_FIELD_TYPES

logger = logging.getLogger(__name__)


# =============================================================================
# FIELD TYPE CONSTANTS (Extended for export name matching)
# =============================================================================

# Keywords checked as substrings in field names (case-insensitive)
_IMAGE_NAME_KEYWORDS = [
    'photo', 'signature', 'sign', 'image', 'pic', 'picture', 'barcode', 'qr',
]

# Fixed dimensions for each image subtype (height × width in cm)
IMAGE_SUBTYPE_DIMENSIONS = {
    'photo':        {'height_cm': 2.5,  'width_cm': 1.9},
    'rel_photo':    {'height_cm': 2.0,  'width_cm': 1.52},
    # Legacy aliases retained for historical exports.
    'mother_photo': {'height_cm': 2.0,  'width_cm': 1.52},
    'father_photo': {'height_cm': 2.0,  'width_cm': 1.52},
    'signature':    {'height_cm': 0.5,  'width_cm': 1.9},
    'qr_code':      {'height_cm': 1.0,  'width_cm': 1.0},
    'barcode':      {'height_cm': 1.0,  'width_cm': 1.5},
}
_DEFAULT_IMAGE_DIMENSIONS = {'height_cm': 2.5, 'width_cm': 1.9}


def _contains_word(text: str, word: str) -> bool:
    """Return True when word appears as a standalone token."""
    if not text or not word:
        return False
    return re.search(r'\b' + re.escape(word) + r'\b', text) is not None


def _looks_like_relation_photo_name(name: str) -> bool:
    """Return True for relation-photo naming patterns like REL_1 / Relation 2 or Relation Photo."""
    if not name:
        return False
    normalized = re.sub(r'[\s_-]+', ' ', str(name).strip().lower())
    if re.match(r'^(?:rel(?:ation)?|relative)\s*(?:1|one|2|two)?\s*(?:photo|image|pic|picture)$', normalized):
        return True
    return bool(re.search(r'\b(?:father|mother)\b\s*(?:photo|image|pic|picture)\b', normalized))


# =============================================================================
# FIELD CLASSIFICATION
# =============================================================================

def is_image_field(field: Dict[str, Any]) -> bool:
    """
    Check if a field is an image field.
    
    Uses two strategies:
        1. Explicit type match (e.g. type='photo', 'rel_photo', 'signature')
      2. Substring match on field name (e.g. 'Student Photo' contains 'photo')
    
    Args:
        field: Field configuration dict with 'name' and 'type' keys
        
    Returns:
        True if field is image type, False otherwise
    """
    field_type = field.get('type', 'text').lower()
    if field_type in IMAGE_FIELD_TYPES:
        return True
    name_lower = field.get('name', '').lower().strip()
    if _looks_like_relation_photo_name(name_lower):
        return True
    return any(
        _contains_word(name_lower, kw) if kw in ('sign', 'qr') else (kw in name_lower)
        for kw in _IMAGE_NAME_KEYWORDS
    )


def classify_image_subtype(field: Dict[str, Any]) -> Optional[str]:
    """
    Classify an image field into a specific subtype.
    
    Returns one of: 'photo', 'rel_photo', 'signature',
                    'qr_code', 'barcode', or None if not an image field.
    
    The subtype determines fixed export dimensions (see IMAGE_SUBTYPE_DIMENSIONS).
    """
    field_type = field.get('type', 'text').lower()
    name_lower = field.get('name', '').lower().strip()
    name_norm = re.sub(r'[\s_]+', ' ', name_lower)

    # 1. Relation photos checking by name - takes precedence over generic 'photo'/'image' types
    if _looks_like_relation_photo_name(name_norm) or name_norm in ('m photo', 'f photo'):
        return 'rel_photo'

    # 2. Check relation keywords if it's generally an image field (but not a signature/barcode/qr)
    is_img = (field_type in ('photo', 'rel_photo', 'image', 'mother_photo', 'father_photo') or
              any(kw in name_lower for kw in ('photo', 'pic', 'picture', 'image')))
    if is_img:
        has_relation_keyword = bool(re.search(r'\b(?:father|mother|parent|guardian|relation|relative|rel)\b', name_norm))
        has_other_media_keyword = any(kw in name_norm for kw in ('signature', 'sign', 'barcode', 'qr'))
        if has_relation_keyword and not has_other_media_keyword:
            return 'rel_photo'

    # Direct type mapping (most reliable — set explicitly in table config)
    _TYPE_MAP = {
        'photo': 'photo', 'rel_photo': 'rel_photo',
        'mother_photo': 'rel_photo', 'father_photo': 'rel_photo',
        'signature': 'signature', 'sign': 'signature',
        'barcode': 'barcode', 'qr_code': 'qr_code', 'qr': 'qr_code', 'image': 'photo',
    }
    if field_type in _TYPE_MAP:
        return _TYPE_MAP[field_type]
    
    # Signature
    if _contains_word(name_lower, 'signature') or _contains_word(name_lower, 'sign'):
        return 'signature'
    # Barcode
    if 'barcode' in name_lower:
        return 'barcode'
    # QR code
    if _contains_word(name_lower, 'qr'):
        return 'qr_code'
    # Generic photo (catch-all)
    if any(kw in name_lower for kw in ('photo', 'pic', 'picture', 'image')):
        return 'photo'
    return None


def get_image_dimensions(field: Dict[str, Any]) -> Dict[str, float]:
    """
    Get fixed height and width dimensions (cm) for an image field.
    
    Returns dict with 'height_cm' and 'width_cm' keys.
    Dimensions are determined by the image subtype (photo, signature, etc.).
    """
    subtype = classify_image_subtype(field)
    if subtype and subtype in IMAGE_SUBTYPE_DIMENSIONS:
        return IMAGE_SUBTYPE_DIMENSIONS[subtype].copy()
    return _DEFAULT_IMAGE_DIMENSIONS.copy()


def get_text_fields(fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter to get only text fields (non-image fields).
    
    Args:
        fields: List of field configurations
        
    Returns:
        List of text-only fields
    """
    return [f for f in fields if not is_image_field(f)]


def get_image_fields(fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter to get only image fields.
    
    Args:
        fields: List of field configurations
        
    Returns:
        List of image fields
    """
    return [f for f in fields if is_image_field(f)]


def get_image_field_names(fields: List[Dict[str, Any]]) -> List[str]:
    """
    Get list of image field names from field configuration.
    
    Args:
        fields: List of field configurations
        
    Returns:
        List of field names that are image fields
    """
    return [f['name'] for f in get_image_fields(fields)]


def separate_fields_by_type(fields: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Separate fields into text and image categories.
    
    Args:
        fields: List of field configurations
        
    Returns:
        Dict with 'text' and 'image' keys containing respective field lists
    """
    text_fields = []
    image_fields = []
    
    for field in fields:
        is_img = is_image_field(field)
        field_info = {
            'name': field.get('name', ''),
            'type': field.get('type', 'text'),
            'is_image': is_img,
        }
        
        if is_img:
            dims = get_image_dimensions(field)
            field_info['image_subtype'] = classify_image_subtype(field)
            field_info['image_height_cm'] = dims['height_cm']
            field_info['image_width_cm'] = dims['width_cm']
            image_fields.append(field_info)
        else:
            text_fields.append(field_info)
    
    return {
        'text': text_fields,
        'image': image_fields
    }


# =============================================================================
# FILENAME GENERATION
# =============================================================================

def generate_export_filename(base_name: str, extension: str, timestamp: bool = True, client_name: str = '', status: str = '') -> str:
    """
    Generate a clean filename for export.
    
    Format: ClientName_TableName_Status.ext
    
    Args:
        base_name: Base name for the file (e.g., table name / list name)
        extension: File extension (e.g., 'xlsx', 'docx', 'zip')
        timestamp: (kept for backward compat, ignored now)
        client_name: Organisation/institution name to prefix
        status: Status label (e.g., 'pending', 'verified', 'approved')
        
    Returns:
        Clean filename string like "RoshanDamor_StudentList_Pending.pdf"
    """
    clean_base = clean_filename(base_name)
    
    parts = []
    if client_name:
        parts.append(clean_filename(client_name))
    parts.append(clean_base)
    if status:
        parts.append(clean_filename(status.capitalize()))
    
    name_part = '_'.join(parts)
    
    # Cap total filename length (without extension) to 150
    if len(name_part) > 150:
        name_part = name_part[:150].rstrip('_.')
    
    return f"{name_part}.{extension.lower()}"


def clean_filename(name: str) -> str:
    """
    Clean a string for use in filenames.
    
    Args:
        name: Raw name string
        
    Returns:
        Cleaned string safe for filenames
    """
    if not name:
        return 'export'
    
    # Strip null bytes and control characters
    clean = re.sub(r'[\x00-\x1f\x7f]', '', name)
    # Remove or replace invalid characters
    clean = re.sub(r'[<>:"/\\|?*]', '', clean)
    # Replace multiple spaces/underscores with single underscore
    clean = re.sub(r'[\s_]+', '_', clean)
    # Remove leading/trailing underscores and dots (Windows issue)
    clean = clean.strip('_.')
    # Truncate if too long
    if len(clean) > 50:
        clean = clean[:50].rstrip('_.')
    # Block Windows reserved device names
    if re.match(r'^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])$', clean, re.IGNORECASE):
        clean = f'_{clean}'
    
    return clean or 'export'


def get_readable_field_name(field_name: str) -> str:
    """
    Convert field name to readable format for filenames.
    
    Args:
        field_name: Original field name
        
    Returns:
        Readable version for use in filenames
    """
    name_upper = field_name.upper().strip()
    
    # Common mappings
    mappings = {
        'F PHOTO': 'FATHER_PHOTO',
        'M PHOTO': 'MOTHER_PHOTO',
        'SIGN': 'SIGNATURE',
    }
    
    return mappings.get(name_upper, name_upper.replace(' ', '_'))


# =============================================================================
# DATA FORMATTING
# =============================================================================

def humanize_label(name: str) -> str:
    """Insert spaces into concatenated field names for readable export headers.

    Examples:
        PERMANENTADDRESS → PERMANENT ADDRESS
        FATHERNAME       → FATHER NAME
        MOTHERMOBILENO   → MOTHER MOBILE NO
        STUDENTNAME      → STUDENT NAME
        DOB              → DOB  (short words unchanged)
    """
    # Step 0: normalise separator characters (_, -, .) to spaces so that
    # e.g. "FATHER_NAME" → "FATHER NAME" and "D.O.B" → "D O B" giving
    # the export engine natural break points in column headers.
    name = re.sub(r'[_\-.]+', ' ', name).strip()
    name = re.sub(r'\s+', ' ', name)
    if ' ' in name:
        return name.upper()   # separators already created word boundaries
    # Common word fragments found in Indian school/ID card field names
    # Order matters: longer fragments first to avoid partial matches
    _KNOWN_WORDS = [
        'ADMISSION', 'PERMANENT', 'TEMPORARY', 'PRESENT', 'RESIDENTIAL',
        'STUDENT', 'FATHER', 'MOTHER', 'GUARDIAN', 'HUSBAND',
        'ADDRESS', 'VILLAGE', 'DISTRICT', 'MOBILE', 'CONTACT', 'PHONE',
        'NUMBER', 'SECTION', 'CLASS', 'NAME', 'EMAIL', 'BIRTH',
        'AADHAR', 'AADHAAR', 'PINCODE', 'STATE', 'CITY', 'COUNTRY',
        'BLOOD', 'GROUP', 'GENDER', 'PHOTO', 'IMAGE', 'DATE',
        'EMERGENCY', 'EMERG', 'CONTACT', 'CONT', 'TRANSPORT', 'DRIVER',
        'JOINING', 'ENROL', 'ROLL', 'CATEGORY', 'CASTE',
        'OCCUPATION', 'QUALIFICATION', 'DESIGNATION', 'RELIGION',
        'NATIONALITY', 'HOUSE', 'WARD', 'BLOCK', 'POST', 'OFFICE',
        'TEHSIL', 'TALUK', 'MANDAL',
        'NEW', 'OLD', 'SR', 'NO', 'ID', 'OF', 'THE',
    ]
    upper = name.upper().strip()
    if len(upper) <= 4:
        return upper
    # Greedy match: repeatedly pull the longest known word from the front
    result_words = []
    remaining = upper
    while remaining:
        matched = False
        for kw in _KNOWN_WORDS:
            if remaining.startswith(kw):
                result_words.append(kw)
                remaining = remaining[len(kw):]
                matched = True
                break
        if not matched:
            # If no known word matches the start, consume one char and try again
            # We group unknown chars together until the next match
            result_words.append(remaining[0])
            remaining = remaining[1:]
    # Merge single leftover characters back into adjacent words
    merged = []
    for w in result_words:
        if len(w) == 1 and merged:
            merged[-1] += w
        else:
            merged.append(w)
    return ' '.join(merged)


def format_field_value(value: Any, uppercase: bool = False) -> str:
    """
    Format a field value for export.
    
    Strips values that look like image paths or pending image references
    so they don't leak into text columns.
    
    Args:
        value: Raw value
        uppercase: Whether to convert to uppercase
        
    Returns:
        Formatted string value
    """
    if value is None:
        return ''
    
    str_value = str(value).strip()
    
    if not str_value:
        return ''
    
    # Strip image-like values that shouldn't appear in text columns
    if _looks_like_image_data(str_value):
        return ''
    
    if uppercase:
        return str_value.upper()
    
    return str_value


# Image file extensions used to detect leaked image paths in text fields
_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg')


def _looks_like_image_data(value: str) -> bool:
    """
    Check if a value looks like image path data that shouldn't appear as text.
    
    Catches:
    - PENDING:filename.jpg references
    - NOT_FOUND markers
    - File paths with image extensions (e.g. adarshimg/client/12345.jpg)
    """
    val_upper = value.upper().strip()
    
    # PENDING:filename or bare PENDING
    if val_upper.startswith('PENDING:') or val_upper == 'PENDING':
        return True
    
    # NOT_FOUND marker
    if val_upper == 'NOT_FOUND':
        return True
    
    # File path with image extension (e.g. adarshimg/XYZ/12345.jpg)
    val_lower = value.lower().strip()
    if '/' in val_lower and val_lower.endswith(_IMAGE_EXTENSIONS):
        return True
    
    return False


def is_valid_image_path(path: Optional[str]) -> bool:
    """
    Check if a path represents a valid image reference.
    
    Args:
        path: Image path string (can be None)
        
    Returns:
        True if path is valid, False if placeholder/empty/traversal
    """
    if not path:
        return False
    
    invalid_values = ['NOT_FOUND', '', 'PENDING', 'null', 'None']
    
    if path in invalid_values:
        return False
    
    if path.startswith('PENDING:'):
        return False
    
    # Path traversal protection
    if '..' in path or path.startswith('/') or path.startswith('\\'):
        return False
    
    return True


# =============================================================================
# EXPORT SORTING
# =============================================================================

# Field name patterns used to detect sort-relevant columns
_CLASS_PATTERNS = ['CLASS']
_SECTION_PATTERNS = ['SECTION', 'SEC', 'SECT', 'DIVISION', 'DIV']
_NAME_PATTERNS = ['NAME', 'STUDENT', 'EMPNAME', 'STUDENT NAME', 'EMP NAME']


def _find_field_name(field_names: List[str], patterns: List[str]) -> Optional[str]:
    """
    Find the first field name that matches any of the given patterns.

    Matching is done on the UPPER-CASED field name:
      1. Exact match first  (e.g. 'CLASS' == 'CLASS')
      2. Substring match    (e.g. 'STUDENT NAME' contains 'NAME')

    Args:
        field_names: List of field names from the table config
        patterns:    List of uppercase patterns to search for

    Returns:
        Matched field name (original casing) or None
    """
    upper_map = {fn.upper(): fn for fn in field_names}

    # 1. Exact match
    for pat in patterns:
        if pat in upper_map:
            return upper_map[pat]

    # 2. Substring match (longer patterns first to prefer specific matches)
    sorted_patterns = sorted(patterns, key=len, reverse=True)
    for pat in sorted_patterns:
        for upper_name, orig_name in upper_map.items():
            if pat in upper_name:
                return orig_name

    return None


def _find_field_name_by_type(
    table_fields: Optional[List[Dict[str, Any]]],
    target_types: List[str],
) -> Optional[str]:
    """
    Return first field name whose configured field type matches target types.

    Args:
        table_fields: Table field configuration list
        target_types: Allowed lowercase field types (e.g. ['class'])

    Returns:
        Field name if found, else None
    """
    if not table_fields:
        return None
    target_set = {str(t).strip().lower() for t in target_types if t}
    for field in table_fields:
        field_type = str((field or {}).get('type', '')).strip().lower()
        field_name = str((field or {}).get('name', '')).strip()
        if field_name and field_type in target_set:
            return field_name
    return None


# sort_cards_for_export is defined below after SortedCardList (Class → Section → Name)


def get_class_field_name(table_fields: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """
    Return the CLASS field name from a table's field config, or None.

    Used by exporters that need class-based page breaks.

    Args:
        table_fields: The table.fields list (list of dicts with 'name' key)

    Returns:
        Matched CLASS field name (original casing) or None
    """
    by_type = _find_field_name_by_type(table_fields, ['class'])
    if by_type:
        return by_type
    if not table_fields:
        return None
    field_names = [f.get('name', '') for f in table_fields]
    return _find_field_name(field_names, _CLASS_PATTERNS)


def get_section_field_name(table_fields: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """
    Return the SECTION field name from a table's field config, or None.

    Used by exporters that need section-based grouping/page breaks.

    Args:
        table_fields: The table.fields list (list of dicts with 'name' key)

    Returns:
        Matched SECTION field name (original casing) or None
    """
    by_type = _find_field_name_by_type(table_fields, ['section'])
    if by_type:
        return by_type
    if not table_fields:
        return None
    field_names = [f.get('name', '') for f in table_fields]
    return _find_field_name(field_names, _SECTION_PATTERNS)


# =============================================================================
# CHUNKED STREAMING DOWNLOAD
# =============================================================================

def stream_file_response(file_bytes, filename, content_type, chunk_size=1024 * 1024, user=None):
    """
    Stream a file download in chunks to keep memory usage low.

    For small files (<10 MB), returns a normal HttpResponse.
    For larger files, writes to a temp file on disk first,
    then streams from disk in ``chunk_size`` (default 1 MB) chunks
    using Django's StreamingHttpResponse.

    Effective Super Mode users use RAM-only streaming for synchronous
    downloads (no temp-file spooling) with chunk size aligned to
    Super Mode download block policy.

    Args:
        file_bytes: The raw bytes of the file (bytes or BytesIO.getvalue()).
        filename:   Suggested download filename.
        content_type: MIME type for the response.
        chunk_size: Size of each chunk in bytes (default 1 MB).
        user: Optional authenticated user for Super Mode-aware streaming.

    Returns:
        HttpResponse or StreamingHttpResponse
    """
    import os
    import tempfile
    from django.http import HttpResponse, StreamingHttpResponse

    size = len(file_bytes)

    stream_chunk_size = int(chunk_size or (1024 * 1024))
    stream_chunk_size = max(128 * 1024, min(stream_chunk_size, 8 * 1024 * 1024))

    # Super Mode: keep synchronous download path RAM-only and skip temp-file I/O.
    super_mode_active = False
    if user is not None:
        try:
            super_mode_active = False
            if super_mode_active:
                stream_chunk_size = max(
                    stream_chunk_size,
                    stream_chunk_size,
                )
        except Exception:
            logger.exception('Failed resolving Super Mode stream settings for %s', filename)
            super_mode_active = False

    if super_mode_active:
        def _iter_mem_chunks():
            view = memoryview(file_bytes)
            for offset in range(0, size, stream_chunk_size):
                yield bytes(view[offset:offset + stream_chunk_size])

        response = StreamingHttpResponse(_iter_mem_chunks(), content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = size
        return response

    # Small files: return directly — no disk I/O
    if size < 10 * 1024 * 1024:  # 10 MB
        response = HttpResponse(file_bytes, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = size
        return response

    # Large files: spool to temp file, then stream in chunks
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1])
    try:
        tmp.write(file_bytes)
        tmp.flush()
        tmp.close()

        def _iter_chunks():
            try:
                with open(tmp.name, 'rb') as fh:
                    while True:
                        chunk = fh.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk
            finally:
                # Clean up temp file after streaming is complete
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

        response = StreamingHttpResponse(_iter_chunks(), content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = size
        return response
    except Exception:
        # Cleanup on error
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise

# =============================================================================
# EXPORT ORDERING — Class → Section → Name ascending
# =============================================================================

class SortedCardList:
    """
    Wraps a sorted list of cards with a QuerySet-compatible interface.
    
    Downstream exporters call .count(), .iterator(), iterate, and slice.
    This wrapper supports all those operations on an in-memory sorted list.
    """

    def __init__(self, cards_list):
        self._cards = list(cards_list)

    def count(self):
        return len(self._cards)

    def exists(self):
        return len(self._cards) > 0

    def iterator(self, chunk_size=None):
        return iter(self._cards)

    def __iter__(self):
        return iter(self._cards)

    def __getitem__(self, key):
        return self._cards[key]

    def __len__(self):
        return len(self._cards)

    def __bool__(self):
        return len(self._cards) > 0


def _detect_sort_fields(table_fields):
    """
    Detect class, section, and name field names from table field config.
    
    Returns:
        (class_field_name, section_field_name, name_field_name)
        Each can be None if not found.
    """
    class_field = None
    section_field = None
    name_field = None

    for f in (table_fields or []):
        ft = f.get('type', 'text').lower()
        fn = f.get('name', '')
        if ft == 'class' and not class_field:
            class_field = fn
        elif ft == 'section' and not section_field:
            section_field = fn

    # Name: prefer first text field with 'name' in its label
    for f in (table_fields or []):
        if f.get('type', 'text').lower() == 'text' and 'name' in f.get('name', '').lower():
            name_field = f.get('name', '')
            break
    # Fallback: first text field
    if not name_field:
        for f in (table_fields or []):
            if f.get('type', 'text').lower() == 'text':
                name_field = f.get('name', '')
                break

    return class_field, section_field, name_field


def _make_sort_key(class_field, section_field, name_field):
    """
    Return a sort-key function for IDCard instances.
    
    Ordering: class (numeric-aware) → section (alpha) → name (alpha).
    Numeric class values (1, 2, 10) sort before text values (LKG, UKG).
    """
    def sort_key(card):
        fd = card.field_data or {}

        # Class: numeric values first, then alphabetical text
        class_val = str(fd.get(class_field, '')).strip() if class_field else ''
        try:
            class_num = int(class_val)
            class_sort = (0, class_num, '')
        except (ValueError, TypeError):
            class_sort = (1, 0, class_val.lower())

        # Section: alphabetical
        section_val = str(fd.get(section_field, '')).strip().lower() if section_field else ''

        # Name: alphabetical, case-insensitive
        name_val = str(fd.get(name_field, '')).strip().lower() if name_field else ''

        return (class_sort, section_val, name_val)

    return sort_key


def sort_cards_for_export(cards_qs, table_fields=None):
    """
    Sort cards by Class → Section → Roll No → Name ascending using high-speed fast_sort engine.
    
    Args:
        cards_qs: QuerySet or iterable of IDCard instances
        table_fields: Optional list of field config dicts from Table.fields
        
    Returns:
        SortedCardList wrapping the pre-sorted card list.
    """
    try:
        from .fast_sort import sort_cards_hierarchical
        sorted_list = sort_cards_hierarchical(cards_qs)
        return SortedCardList(sorted_list)
    except Exception as sort_err:
        logger.warning("fast_sort fallback: %s", sort_err)
        class_field, section_field, name_field = _detect_sort_fields(table_fields)
        if not class_field and not section_field and not name_field:
            return cards_qs
        cards_list = list(cards_qs)
        key_fn = _make_sort_key(class_field, section_field, name_field)
        cards_list.sort(key=key_fn)
        return SortedCardList(cards_list)