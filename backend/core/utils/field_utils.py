"""
Field Conversion & Validation Utilities
========================================
Canonical location for class/section conversion helpers and image validation.
These are pure utility functions with NO model or view dependencies.

Architecture rule: Services and views import FROM here.
NEVER import these from a views module.
"""

import re

# ==================== CLASS/SECTION CONVERSION CONSTANTS ====================

# Mapping of numeric values to Roman numerals for class field conversion
NUMERIC_TO_ROMAN = {
    '1': 'I', '2': 'II', '3': 'III', '4': 'IV', '5': 'V',
    '6': 'VI', '7': 'VII', '8': 'VIII', '9': 'IX', '10': 'X',
    '11': 'XI', '12': 'XII',
}

_INT_TO_ROMAN = {int(k): v for k, v in NUMERIC_TO_ROMAN.items()}

# Valid class values (preserved as-is during import)
# KG1 = LKG and KG2 = UKG — different schools use different names for the same level.
VALID_CLASS_VALUES = {
    'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII',
    'KG1', 'KG2', 'LKG', 'UKG', 'NURSERY', 'PRE-NURSERY', 'UG',
}

# The 17 canonical class values in progression order.
# normalize_class_value() always returns one of these (or the original if unrecognized).
CANONICAL_CLASSES = [
    'PRE-NURSERY',  # 0
    'NURSERY',      # 1
    'KG1',          # 2  (aliases: LKG, KG-I, KGI, KG-1, K.G.1, etc.)
    'KG2',          # 3  (aliases: UKG, KG-II, KGII, KG-2, etc.)
    'I',            # 4
    'II',           # 5
    'III',          # 6
    'IV',           # 7
    'V',            # 8
    'VI',           # 9
    'VII',          # 10
    'VIII',         # 11
    'IX',           # 12
    'X',            # 13
    'XI',           # 14
    'XII',          # 15
    'UG',           # 16
]

# Level index for each canonical class (used for upgrade: level + 1)
_CANONICAL_LEVEL = {c: i for i, c in enumerate(CANONICAL_CLASSES)}

# Class upgrade progression on canonical forms: current → next
CLASS_UPGRADE_MAP = {c: CANONICAL_CLASSES[i + 1] for i, c in enumerate(CANONICAL_CLASSES) if i < len(CANONICAL_CLASSES) - 1}
# Result: PRE-NURSERY→NURSERY, NURSERY→KG1, KG1→KG2, KG2→I, I→II, ..., XII→UG

# Logical class ordering (lower index = earlier). Used for sorting/filtering.
# Maps BOTH canonical keys and common raw variants for the sorting lambda.
CLASS_ORDER = {c: i for i, c in enumerate(CANONICAL_CLASSES)}
# Add common aliases so sorting works even on un-normalized raw values
_ORDER_ALIASES = {
    'PRE NURSERY': 0, 'PRENURSERY': 0, 'PRE-NUR': 0, 'PRENUR': 0, 'PN': 0,
    'NUR': 1, 'NURS': 1,
    'LKG': 2, 'KG-I': 2, 'KGI': 2, 'KG-1': 2, 'L.K.G': 2, 'L.K.G.': 2,
    'UKG': 3, 'KG-II': 3, 'KGII': 3, 'KG-2': 3, 'U.K.G': 3, 'U.K.G.': 3,
    '1': 4, '1ST': 4,
    '2': 5, '2ND': 5,
    '3': 6, '3RD': 6,
    '4': 7, '4TH': 7,
    '5': 8, '5TH': 8,
    '6': 9, '6TH': 9,
    '7': 10, '7TH': 10,
    '8': 11, '8TH': 11,
    '9': 12, '9TH': 12,
    '10': 13, '10TH': 13,
    '11': 14, '11TH': 14,
    '12': 15, '12TH': 15,
}
CLASS_ORDER.update(_ORDER_ALIASES)
CLASS_ORDER_UNKNOWN = 99


# ==================== ROMAN NUMERAL HELPERS (I–XII only) ====================

# Only I, V, X are needed for classes 1-12.  L (50) is NOT included because
# lowercase 'l' is visually identical to 'I' and must be treated as 'I'.
_ROMAN_DIGIT = {'I': 1, 'V': 5, 'X': 10}


def _roman_to_int(s):
    """Parse a string as a Roman numeral I–XII.

    Handles lowercase 'l' as 'I' (they look identical).
    Returns an integer 1-12 or None if not a valid class Roman numeral.
    """
    if not s:
        return None
    # In class context: uppercase 'L' is treated as 'I' (no class 50)
    s = s.replace('L', 'I').replace('l', 'I').upper()
    if not s or not all(c in _ROMAN_DIGIT for c in s):
        return None
    total = 0
    prev = 0
    for c in reversed(s):
        val = _ROMAN_DIGIT[c]
        if val < prev:
            total -= val
        else:
            total += val
        prev = val
    if 1 <= total <= 12:
        return total
    return None


def _arabic_to_int(s):
    """Parse s as an Arabic class number (1-12), with optional ordinal suffix.

    Handles: '1', '2', …, '12', '1st', '2nd', '3rd', '4th', …, '12th'
    Returns integer 1-12 or None.
    """
    if not s:
        return None
    cleaned = re.sub(r'(?:ST|ND|RD|TH)$', '', s.strip().upper())
    try:
        n = int(cleaned)
        return n if 1 <= n <= 12 else None
    except (ValueError, TypeError):
        return None


# ==================== CORE NORMALIZER ====================

def normalize_class_value(value):
    """Normalize ANY class value to one of the 17 canonical forms.

    Canonical forms:
        PRE-NURSERY, NURSERY, KG1, KG2,
        I, II, III, IV, V, VI, VII, VIII, IX, X, XI, XII, UG

    Handles all common variations:
        - Mixed case, spaces, dots, dashes:  "kg - I", "K.G.1", "Pre Nursery"
        - Lowercase 'l' as Roman 'I':  "kgl" → KG1, "ll" → II
        - Arabic numerals:  "1" → I, "12" → XII
        - Ordinals:  "1st" → I, "2nd" → II, "3rd" → III
        - LKG/UKG aliases:  "LKG" → KG1, "UKG" → KG2
        - Full Roman numerals:  "IV" → IV, "XI" → XI
        - Prefixed forms:  "Grade 5" → V, "Class 10" → X, "Std. IV" → IV

    Returns the canonical form, or the original value uppercased if unrecognized.
    """
    if not value:
        return value
    raw = str(value).strip()
    if not raw:
        return raw

    upper = raw.upper()

    # Remove all whitespace, dots, dashes, underscores for compact matching
    compact = re.sub(r'[\s.\-_/,]+', '', upper)

    # ── Pre-Nursery ──
    if compact in ('PRENURSERY', 'PRENUR', 'PRENNURSERY', 'PNURSERY', 'PN',
                    'PRENURCERY', 'PRENUSERY'):
        return 'PRE-NURSERY'
    # Catch "PRE" + "NURSERY" anywhere in string (handles extra chars between)
    if compact.startswith('PRE') and 'NUR' in compact:
        return 'PRE-NURSERY'

    # ── Nursery ──
    if compact in ('NURSERY', 'NUR', 'NURS', 'NURCERY', 'NUSERY'):
        return 'NURSERY'

    # ── UG (must check before KG to avoid matching "UKG" here) ──
    if compact == 'UG':
        return 'UG'

    # ── LKG / UKG exact ──
    if compact in ('LKG', 'LOWERKINDERGARTEN', 'LOWERKG', 'LKGARTEN'):
        return 'KG1'
    if compact in ('UKG', 'UPPERKINDERGARTEN', 'UPPERKG', 'UKGARTEN'):
        return 'KG2'

    # ── KG prefix patterns: KG1, KG-I, KGI, KGl, KG-1, KG.1, K.G.I, etc. ──
    if compact.startswith('KG') or compact.startswith('KINDER'):
        suffix = compact[2:] if compact.startswith('KG') else re.sub(r'^KINDERGARTEN', '', compact)
        if suffix:
            n = _arabic_to_int(suffix)
            if n == 1:
                return 'KG1'
            if n == 2:
                return 'KG2'
            n = _roman_to_int(suffix)
            if n == 1:
                return 'KG1'
            if n == 2:
                return 'KG2'
            # suffix didn't parse as 1 or 2 — not a valid KG level, fall through

    # ── Strip GRADE / CLASS / STD / STANDARD prefix ──
    for prefix in ('GRADE', 'CLASS', 'STD', 'STANDARD'):
        if compact.startswith(prefix):
            suffix = compact[len(prefix):]
            if suffix:
                n = _arabic_to_int(suffix)
                if n is not None:
                    return _INT_TO_ROMAN[n]
                n = _roman_to_int(suffix)
                if n is not None:
                    return _INT_TO_ROMAN[n]

    # ── Standalone Roman numeral (I – XII) ──
    # Must try BEFORE Arabic because 'X' (Roman 10) should not fall through.
    n = _roman_to_int(compact)
    if n is not None:
        return _INT_TO_ROMAN[n]

    # ── Standalone Arabic numeral (1 – 12, optionally with ordinal) ──
    n = _arabic_to_int(compact)
    if n is not None:
        return _INT_TO_ROMAN[n]

    # ── Already a canonical value? ──
    if upper in VALID_CLASS_VALUES:
        return upper

    # Unrecognized — return uppercased original
    return upper


def get_class_order(value):
    """Return sort order for a class value (normalized first)."""
    if not value:
        return CLASS_ORDER_UNKNOWN
    canonical = normalize_class_value(value)
    return CLASS_ORDER.get(canonical, CLASS_ORDER_UNKNOWN)


# ==================== CONVERSION FUNCTIONS ====================

def validate_image_bytes(image_bytes):
    """Validate that image bytes represent a valid image."""
    from mediafiles.services import ImageService
    return ImageService.validate_image_bytes(image_bytes)


def convert_class_value(value):
    """
    Convert a class value from XLSX import to canonical form.
    Uses the robust normalize_class_value() for all edge cases.
    """
    if not value:
        return value
    return normalize_class_value(value)


def convert_section_value(value):
    """
    Convert a section value from XLSX:
    - Always convert to uppercase
    """
    if not value:
        return value
    return str(value).strip().upper()


def normalize_compact_text_value(value):
    """Normalize free-form course/branch text to a compact comparison key.

    This is intentionally punctuation/whitespace/case-insensitive so values like
    "BTECH", "B.TECH", and "B TECH" are treated as the same logical value.
    """
    if value is None:
        return ''
    raw = str(value).strip()
    if not raw:
        return ''
    return re.sub(r'[^A-Z0-9]+', '', raw.upper())


# ==================== UPGRADE OUTPUT FORMAT HELPERS ====================

# KG naming conventions used by different schools
KG_CONVENTIONS = {
    'lkg':   {'KG1': 'LKG',  'KG2': 'UKG'},
    'dash':  {'KG1': 'KG-I', 'KG2': 'KG-II'},
    'arabic': {'KG1': 'KG1',  'KG2': 'KG2'},
    'roman': {'KG1': 'KGI',  'KG2': 'KGII'},
}


def detect_kg_convention(raw_format_counts):
    """Detect KG naming convention from raw format frequency data.

    Args:
        raw_format_counts: dict of {canonical: {raw_value: count}}
                           e.g. {'KG1': {'KG-I': 100, 'KG1': 10, 'KGI': 5}}

    Returns: one of 'lkg', 'dash', 'arabic', 'roman'
    """
    lkg_total = 0
    dash_total = 0
    arabic_total = 0
    roman_total = 0

    for canonical in ('KG1', 'KG2'):
        for raw_val, cnt in raw_format_counts.get(canonical, {}).items():
            raw_clean = raw_val.upper().replace(' ', '').replace('.', '').replace('-', '').replace('_', '')
            if 'LKG' in raw_clean or 'UKG' in raw_clean:
                lkg_total += cnt
            elif '-' in raw_val:
                dash_total += cnt
            elif any(c.isdigit() for c in raw_val):
                arabic_total += cnt
            else:
                roman_total += cnt

    # Default to dash (KG-I / KG-II) if no data at all
    best = max(lkg_total, dash_total, arabic_total, roman_total)
    if best == 0:
        return 'dash'
    if lkg_total == best:
        return 'lkg'
    if dash_total == best:
        return 'dash'
    if arabic_total == best:
        return 'arabic'
    return 'roman'


def format_class_for_output(canonical, kg_convention='dash'):
    """Convert a canonical class key to the preferred display format.

    For class I-XII, PRE-NURSERY, NURSERY, UG — returns the canonical form.
    For KG1/KG2 — returns the format matching the school's convention.
    """
    if canonical in ('KG1', 'KG2'):
        return KG_CONVENTIONS.get(kg_convention, KG_CONVENTIONS['dash']).get(canonical, canonical)
    return canonical


def get_all_raw_variants_for_canonical(canonical, all_distinct_raw_values):
    """Return all raw values from the list that normalize to the given canonical.

    Used for filter queries: when filtering by canonical 'KG1', match all rows
    where the raw value is 'KG-I', 'KG1', 'KGI', 'LKG', 'kgI', etc.
    """
    return [r for r in all_distinct_raw_values if normalize_class_value(r) == canonical]
