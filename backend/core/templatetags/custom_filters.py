from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe
import json
import re

# Import canonical constants from mediafiles
from mediafiles.constants import IMAGE_FIELD_TYPES, IMAGE_FIELD_NAME_PATTERNS

register = template.Library()

# ---------------------------------------------------------------------------
# safe_html filter — whitelist-based HTML sanitiser (no external deps)
# ---------------------------------------------------------------------------
_SAFE_TAGS = frozenset([
    'span', 'br', 'b', 'i', 'em', 'strong', 'u', 'small', 'mark', 'sub', 'sup',
])
# Matches any HTML tag (opening, closing, self-closing)
_TAG_RE = re.compile(r'<(/?)(\w+)([^>]*)(/?)>', re.IGNORECASE | re.DOTALL)
# Dangerous attribute patterns (event handlers, javascript: URIs)
_BAD_ATTR_RE = re.compile(r'\bon\w+\s*=|javascript\s*:', re.IGNORECASE)


def _sanitize_tag(match):
    """Keep whitelisted tags, strip dangerous attributes, escape others."""
    slash_open, tag_name, attrs, slash_close = match.groups()
    if tag_name.lower() not in _SAFE_TAGS:
        return ''  # strip non-whitelisted tag entirely
    # Strip dangerous attributes (onclick=, onerror=, javascript:, etc.)
    if _BAD_ATTR_RE.search(attrs):
        # Only keep class="..." and style="..." attribute pairs
        safe_attrs = re.findall(r'\b(?:class|style)\s*=\s*"[^"]*"', attrs, re.IGNORECASE)
        attrs = (' ' + ' '.join(safe_attrs)) if safe_attrs else ''
    return f'<{slash_open}{tag_name}{attrs}{slash_close}>'


@register.filter(name='safe_html')
def safe_html(value):
    """
    Allow only whitelisted inline HTML tags; strip everything else.
    Usage: {{ business.hero_title|safe_html }}
    """
    if not value:
        return ''
    result = _TAG_RE.sub(_sanitize_tag, str(value))
    return mark_safe(result)

# Canonical image column order (for consistent display)
IMAGE_COLUMN_ORDER = ['photo', 'father photo', 'f photo', 'mother photo', 'm photo', 'signature', 'sign', 'barcode', 'qr code', 'qr_code', 'qr']


def is_image_field_by_name(field_name):
    """
    Check if a field name contains any image-related patterns.
    This helps detect fields like 'PHOTO', 'F PHOTO', 'M PHOTO', 'SIGN', etc.
    Uses word boundary matching to avoid false positives like 'designation' matching 'sign'.
    """
    if not field_name:
        return False
    if str(field_name).lower().endswith('path'):
        return False
    name_lower = field_name.lower()
    normalized_name = re.sub(r'[\s_-]+', ' ', name_lower).strip()

    if re.search(r'\b(?:rel(?:ation)?)\s*(?:1|one|2|two)\s*(?:photo|image|pic|picture)\b', normalized_name):
        return True

    for pattern in IMAGE_FIELD_NAME_PATTERNS:
        # Use word boundary regex to avoid false positives
        if re.search(r'\b' + re.escape(pattern) + r'\b', name_lower):
            return True
    return False


def _is_image_field(field):
    """Helper to check if field dict is an image field"""
    if isinstance(field, dict):
        field_type = field.get('type', '')
        field_name = field.get('name', '')
        return field_type in IMAGE_FIELD_TYPES or is_image_field_by_name(field_name)


@register.filter
def is_show_path_enabled(field):
    """Template filter to safely check if show_path is enabled for a field config dict."""
    if not isinstance(field, dict):
        return False
    val = field.get('show_path')
    if isinstance(val, str):
        return val.strip().lower() in ('true', '1', 'yes', 'on')
    return bool(val)
    return False


def _get_image_sort_key(field_name):
    """
    Get sort order for image fields based on canonical display order.
    Photo(0) → Father Photo(1) → Mother Photo(2) → Signature(3) → Barcode(4) → QR(5)
    
    Must stay in sync with BaseService._get_image_sort_key in core/services/base.py.
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


@register.filter
def get_field(field_data, key):
    """
    Get a value from a dictionary by key.
    Usage: {{ card.field_data|get_field:field.key }}
    """
    if field_data is None:
        return ''
    if isinstance(field_data, str):
        try:
            field_data = json.loads(field_data)
        except (json.JSONDecodeError, TypeError):
            return ''
    if isinstance(field_data, dict):
        return field_data.get(key, '')
    return ''

@register.filter
def json_encode(value):
    """
    Convert a Python object to JSON string.
    Usage: {{ table.fields|json_encode }}
    """
    import json
    if value is None:
        return '[]'
    return json.dumps(value)

@register.filter
def is_image_field(field_type):
    """
    Check if a field type is an image field.
    Usage: {% if field.type|is_image_field %}
    """
    return field_type in IMAGE_FIELD_TYPES


@register.filter
def is_image_field_or_name(field):
    """
    Check if a field is an image field by type OR by name pattern.
    Accepts a field dict with 'type' and 'name' keys.
    Usage: {% if field|is_image_field_or_name %}
    """
    if isinstance(field, dict):
        field_type = field.get('type', '')
        field_name = field.get('name', '')
        return field_type in IMAGE_FIELD_TYPES or is_image_field_by_name(field_name)
    return False


@register.simple_tag
def is_image_type(field_type):
    """
    Check if a field type is an image field (for use in templates).
    Usage: {% is_image_type field.type as is_img %}
    """
    return field_type in IMAGE_FIELD_TYPES


@register.filter
def get_image_class(field_name):
    """
    Get CSS class based on field name for different image types.
    Returns: 'photo-type', 'signature-type', 'qr-type', 'barcode-type'
    Uses word boundary matching to avoid 'designation' matching 'sign'.
    Usage: {{ field.name|get_image_class }}
    """
    if not field_name:
        return 'photo-type'
    name_lower = field_name.lower()
    # Use word boundary matching to prevent false positives
    if re.search(r'\bsign\b|\bsignature\b', name_lower):
        return 'signature-type'
    elif re.search(r'\bqr\b', name_lower):
        return 'qr-type'
    elif re.search(r'\bbarcode\b', name_lower):
        return 'barcode-type'
    else:
        return 'photo-type'


@register.filter
def expand_field_name(field_name):
    """
    Expand short field names to full descriptive names.
    E.g., 'F PHOTO' -> 'FATHER PHOTO', 'M PHOTO' -> 'MOTHER PHOTO'
    Usage: {{ field.name|expand_field_name }}
    """
    if not field_name:
        return field_name
    
    name_upper = field_name.upper().strip()
    
    # Map of short names to full names
    expansions = {
        'F PHOTO': 'FATHER PHOTO',
        'M PHOTO': 'MOTHER PHOTO',
        'F_PHOTO': 'FATHER PHOTO',
        'M_PHOTO': 'MOTHER PHOTO',
        'FPHOTO': 'FATHER PHOTO',
        'MPHOTO': 'MOTHER PHOTO',
        'F SIGN': 'FATHER SIGN',
        'M SIGN': 'MOTHER SIGN',
        'SIGN': 'SIGNATURE',
    }
    
    return expansions.get(name_upper, field_name)


@register.simple_tag
def check_image_field(field_type, field_name):
    """
    Check if a field is an image field by type OR by name pattern.
    Usage: {% check_image_field field.type field.name as is_img %}
    """
    return field_type in IMAGE_FIELD_TYPES or is_image_field_by_name(field_name)


@register.filter
def get_thumbnail_path(image_path):
    """
    Convert an image path to its thumbnail path.
    Inserts '/thumbs/' after the base folder to match server storage structure.
    
    Usage: {{ field.value|get_thumbnail_path }}
    
    Example:
        Input:  'adarshimg/ABCDE12345/14325123456101.jpg'
        Output: 'adarshimg/thumbs/ABCDE12345/14325123456101.jpg'
    
    Returns original path if conversion fails (fallback safe).
    """
    if not image_path or image_path == '' or image_path == 'NOT_FOUND':
        return image_path
    
    # Handle PENDING: prefix - return as-is (no thumbnail for pending)
    if isinstance(image_path, str) and image_path.startswith('PENDING:'):
        return image_path
    
    # Split path and insert 'thumbs' after the base folder, use .webp extension
    try:
        parts = image_path.replace('\\', '/').split('/')
        if len(parts) >= 2:
            # e.g. adarshimg/CLIENT/file.jpg -> adarshimg/thumbs/CLIENT/file.webp
            base_folder = parts[0]
            rest = '/'.join(parts[1:])
            name, _ext = rest.rsplit('.', 1) if '.' in rest else (rest, '')
            rest = f"{name}.webp"
            return f"{base_folder}/thumbs/{rest}"
        else:
            # Just a filename
            name, _ext = image_path.rsplit('.', 1) if '.' in image_path else (image_path, '')
            return f"thumbs/{name}.webp"
    except Exception:
        pass
    
    # Fallback to original path
    return image_path


@register.simple_tag
def cache_bust():
    """
    Generate a cache-busting timestamp for image URLs.
    Usage: {% cache_bust as cb %}
           <img src="/media/{{ path }}?t={{ cb }}">
    """
    import time
    return int(time.time())


@register.filter
def reorder_fields_for_display(fields):
    """
    Preserve configured field order for table display.
    
    Usage: {% for field in table.fields|reorder_fields_for_display %}
    """
    return fields


@register.filter
def get_image_icon_name(field_name):
    """
    Get Font Awesome icon name based on field name for image types.
    Uses word boundary matching to avoid 'designation' matching 'sign'.
    Returns: 'user', 'signature', 'qrcode', 'barcode', or 'image'
    Usage: {{ field.name|get_image_icon_name }}
    """
    if not field_name:
        return 'image'
    name_lower = field_name.lower()
    name_upper = field_name.upper()
    
    if name_upper == 'PHOTO':
        return 'user'
    elif re.search(r'\bsign\b|\bsignature\b', name_lower):
        return 'signature'
    elif re.search(r'\bqr\b', name_lower):
        return 'qrcode'
    elif re.search(r'\bbarcode\b', name_lower):
        return 'barcode'
    else:
        return 'image'


@register.filter
def reorder_card_fields_for_display(ordered_fields):
    """
    Preserve card field order as provided by the table configuration.
    
    Usage: {% for field in card.ordered_fields|reorder_card_fields_for_display %}
    """
    return ordered_fields

@register.filter
def getattr_filter(obj, attr):
    """
    Get an attribute of an object dynamically.
    Usage: {{ object|getattr:"field_name" }}
    """
    if obj is None:
        return None
    try:
        return getattr(obj, attr, None)
    except Exception:
        return None

# Alias so templates can use |getattr:
register.filter('getattr', getattr_filter)


@register.filter
def concat(value, arg):
    """
    Concatenate two strings.
    Usage: {{ "hero_image"|concat:idx }}  →  "hero_image1"
    """
    return str(value) + str(arg)


@register.filter
def make_range(value):
    """
    Return a range list [1 .. value].
    Usage: {% for i in 5|make_range %}  →  [1, 2, 3, 4, 5]
    """
    try:
        return range(1, int(value) + 1)
    except (ValueError, TypeError):
        return []


@register.filter(is_safe=True)
def wrap_header(value):
    """
    Insert <br> between words in column headers so they wrap
    inside narrow table columns instead of being cut off.
    Also humanizes concatenated field names first.
    Usage: {{ field.name|wrap_header }}  →  "MOTHER<br>PHOTO"
    """
    if not value:
        return value
    from django.utils.html import escape
    # First humanize concatenated names
    humanized = _humanize_field_name(str(value))
    parts = humanized.split()
    if len(parts) <= 1:
        return escape(humanized)
    return mark_safe('<br>'.join(escape(p) for p in parts))


# ─────────────────────────────────────────────────────────────────────
# humanize_header — insert spaces into concatenated field names
# ─────────────────────────────────────────────────────────────────────
# Known words for splitting ALL-CAPS concatenated field names.
# Sorted longest-first so greedy matching picks the longest token.
_HEADER_KNOWN_WORDS = sorted([
    'STUDENT', 'ADMISSION', 'PRIMARY', 'SECONDARY', 'ALTERNATE',
    'MOBILE', 'CONTACT', 'FATHER', 'MOTHER', 'GUARDIAN', 'PARENT', 'SPOUSE',
    'ADDRESS', 'PERMANENT', 'CURRENT', 'PRESENT', 'TEMPORARY', 'RESIDENTIAL',
    'DATE', 'BIRTH', 'JOINING', 'EXPIRY', 'VALIDITY', 'ISSUE',
    'NUMBER', 'NAME', 'CLASS', 'SECTION', 'ROLL', 'DIVISION',
    'EMPLOYEE', 'CODE', 'DESIGNATION', 'DEPARTMENT', 'BRANCH', 'COMPANY',
    'EMAIL', 'PHONE', 'BLOOD', 'GROUP', 'TYPE',
    'GENDER', 'AGE', 'PHOTO', 'SIGNATURE', 'IMAGE', 'PICTURE',
    'CITY', 'STATE', 'DISTRICT', 'PINCODE', 'COUNTRY', 'VILLAGE', 'TOWN',
    'HOUSE', 'HOSTEL', 'ROOM', 'BUS', 'ROUTE', 'LIBRARY', 'LAB',
    'FIRST', 'MIDDLE', 'LAST', 'FULL', 'SUR',
    'UID', 'UUID', 'UDISE',
    'AADHAAR', 'AADHAR', 'PAN', 'VOTER', 'PASSPORT', 'RATION',
    'CARD', 'DRIVING', 'LICENSE', 'LICENCE',
    'NATIONALITY', 'RELIGION', 'CASTE', 'CATEGORY', 'MARITAL', 'STATUS',
    'BATCH', 'SEMESTER', 'STREAM', 'COURSE', 'YEAR',
    'EMERGENCY', 'OFFICE', 'WORK', 'LOCATION', 'POSTING',
    'RANK', 'SERVICE', 'ACCESS', 'LEVEL', 'GRADE', 'PAY',
    'SHIFT', 'TIMING', 'REPORTING', 'MANAGER',
    'MEDICAL', 'CONDITION', 'HEALTH', 'ALLERGY', 'ALLERGIES',
    'DISABILITY', 'HANDICAP',
    'REQUESTED', 'CREATED', 'UPDATED', 'MODIFIED',
    'OF', 'NO', 'ID', 'AT', 'BY', 'FOR', 'THE',
], key=len, reverse=True)


def _split_all_caps(s):
    """Split an ALL-CAPS concatenated string into words using known boundaries."""
    words = []
    remaining = s
    while remaining:
        matched = False
        for word in _HEADER_KNOWN_WORDS:
            if remaining.startswith(word):
                words.append(word)
                remaining = remaining[len(word):]
                matched = True
                break
        if not matched:
            # No direct known-word match.
            # Keep acronym prefixes intact by splitting only at a later known-word boundary.
            boundary = -1
            for idx in range(2, len(remaining)):
                suffix = remaining[idx:]
                if any(suffix.startswith(word) for word in _HEADER_KNOWN_WORDS):
                    boundary = idx
                    break

            if boundary == -1:
                words.append(remaining)
                break

            words.append(remaining[:boundary])
            remaining = remaining[boundary:]

    return ' '.join(words)


def _humanize_field_name(value):
    """
    Convert concatenated/camelCase/underscore field names to human-readable.
    'STUDENTNAME' → 'STUDENT NAME'
    'dateOfBirth' → 'DATE OF BIRTH'
    'father_name' → 'FATHER NAME'
    'Student Name' → 'STUDENT NAME'
    """
    s = str(value).strip()
    if not s:
        return s

    # If already has spaces → just uppercase
    if ' ' in s:
        return s.upper()

    # Replace underscores / dots / hyphens with spaces
    spaced = re.sub(r'[_.\-]+', ' ', s)
    if ' ' in spaced:
        return spaced.upper()

    # camelCase / PascalCase — insert space before uppercase following lowercase
    camel = re.sub(r'([a-z])([A-Z])', r'\1 \2', s)
    if ' ' in camel:
        return camel.upper()

    # ALL-CAPS concatenated — greedy word matching
    return _split_all_caps(s.upper())


@register.filter(is_safe=True)
def humanize_header(value):
    """
    Convert field names like 'STUDENTNAME', 'dateOfBirth', 'father_name'
    to human-readable uppercase headers: 'STUDENT NAME', 'DATE OF BIRTH', etc.
    Usage: {{ field.name|humanize_header }}
    """
    if not value:
        return value
    return _humanize_field_name(str(value))


@register.filter
def get_column_width_class(field):
    """
    Return Tailwind width class for a dynamic column based on field name/type.
    Delegates to the central column_spec intelligence module.
    Usage: {{ field|get_column_width_class }}
    """
    if not isinstance(field, dict):
        return 'min-w-[70px]'

    from exports.column_spec import get_column_spec
    field_name = field.get('name', '') or ''
    field_type = field.get('type', '') or ''
    spec = get_column_spec(field_name, field_type)
    return spec.html_th_class


@register.filter
def get_td_width_class(field):
    """
    Return the td width/wrap/alignment classes for a dynamic field.
    Delegates to the central column_spec intelligence module.
    Usage: {{ field|get_td_width_class }}
    """
    if not isinstance(field, dict):
        return 'min-w-[70px] whitespace-normal break-words'

    from exports.column_spec import get_column_spec
    field_name = field.get('name', '') or ''
    field_type = field.get('type', '') or ''
    spec = get_column_spec(field_name, field_type)
    return spec.html_td_class


@register.filter
def get_column_align_class(field):
    """
    Return alignment class for <th> headings.
    Delegates to the central column_spec intelligence module.
    Usage: {{ field|get_column_align_class }}
    """
    if not isinstance(field, dict):
        return 'text-center'

    from exports.column_spec import get_column_spec
    field_name = field.get('name', '') or ''
    field_type = field.get('type', '') or ''
    spec = get_column_spec(field_name, field_type)
    return f'text-{spec.align}'


# ---------------------------------------------------------------------------
# phone_break / email_break — controlled word-break for table cells
# ---------------------------------------------------------------------------
@register.filter(name='phone_break')
def phone_break(value):
    """
    Insert a <wbr> word-break opportunity at the centre of a phone number.
    10 digits → break after 5th, 12 digits → after 6th, etc.
    Usage: {{ staff.user.phone|phone_break }}
    """
    if not value:
        return ''
    val = str(value)
    digits = re.sub(r'[^0-9]', '', val)
    if len(digits) < 6:
        return escape(val)
    mid = len(digits) // 2
    count = 0
    for i, ch in enumerate(val):
        if ch.isdigit():
            count += 1
        if count == mid:
            return mark_safe(escape(val[:i + 1]) + '<wbr>' + escape(val[i + 1:]))
    return escape(val)


@register.filter(name='email_break')
def email_break(value):
    """
    Insert a <wbr> word-break opportunity before the @ in an email address.
    Browser will only break the line at @ when the cell is too narrow.
    Usage: {{ staff.user.email|email_break }}
    """
    if not value:
        return ''
    val = str(value)
    idx = val.find('@')
    if idx > 0:
        return mark_safe(escape(val[:idx]) + '<wbr>' + escape(val[idx:]))
    return escape(val)