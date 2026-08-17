"""
Smart Column Type & Semantic Field Detector for Data Ingestion

Features:
- Fast classification of header labels into semantic data types:
  text, number, date, photo, father_photo, mother_photo, sign, class, section
- Normalizes variations across Hindi / English / Common school ERP headers
  (e.g., 'FATHER PIC' -> 'father_photo', 'DOB' -> 'date', 'ROLL NO' -> 'number')
"""
import re
from typing import Dict, Any, List, Tuple

_PHOTO_PATTERNS = [
    re.compile(r'\b(photo|pic|picture|image|student_photo|std_photo|img|student_img)\b', re.IGNORECASE),
]
_FATHER_PHOTO_PATTERNS = [
    re.compile(r'\b(father\s*(photo|pic|picture|image)|f[_\s]*(photo|pic|picture|image)|father_photo|father_pic|fphoto)\b', re.IGNORECASE),
]
_MOTHER_PHOTO_PATTERNS = [
    re.compile(r'\b(mother\s*(photo|pic|picture|image)|m[_\s]*(photo|pic|picture|image)|mother_photo|mother_pic|mphoto)\b', re.IGNORECASE),
]
_SIGN_PATTERNS = [
    re.compile(r'\b(sign|signature|student_sign|std_sign)\b', re.IGNORECASE),
]
_DATE_PATTERNS = [
    re.compile(r'\b(dob|birth|date_of_birth|date of birth|admission_date|doj|date)\b', re.IGNORECASE),
]
_CLASS_PATTERNS = [
    re.compile(r'\b(class|standard|std|grade|course)\b', re.IGNORECASE),
]
_SECTION_PATTERNS = [
    re.compile(r'\b(section|sec|division|div|branch)\b', re.IGNORECASE),
]
_NUMBER_PATTERNS = [
    re.compile(r'\b(roll|roll_no|roll no|sr_no|sr no|sno|adm_no|admission_no|mobile|phone|contact|aadhaar|aadhar)\b', re.IGNORECASE),
]


def detect_field_type(header_name: str, sample_values: List[Any] = None) -> str:
    """
    Detect the optimal field type for a column based on header name and sample cell values.
    Returns one of: 'text', 'number', 'date', 'photo', 'father_photo', 'mother_photo', 'sign'
    """
    raw = str(header_name or '').strip()
    norm = re.sub(r'[^a-zA-Z0-9_ ]', '', raw).lower().strip()

    # 1. Father Photo
    for pat in _FATHER_PHOTO_PATTERNS:
        if pat.search(norm):
            return 'father_photo'

    # 2. Mother Photo
    for pat in _MOTHER_PHOTO_PATTERNS:
        if pat.search(norm):
            return 'mother_photo'

    # 3. Signature
    for pat in _SIGN_PATTERNS:
        if pat.search(norm):
            return 'sign'

    # 4. Main Photo
    for pat in _PHOTO_PATTERNS:
        if pat.search(norm):
            return 'photo'

    # 5. Date
    for pat in _DATE_PATTERNS:
        if pat.search(norm):
            return 'date'

    # 6. Class
    for pat in _CLASS_PATTERNS:
        if pat.search(norm):
            return 'class'

    # 7. Section
    for pat in _SECTION_PATTERNS:
        if pat.search(norm):
            return 'section'

    # 8. Numeric fields
    for pat in _NUMBER_PATTERNS:
        if pat.search(norm):
            return 'number'

    # 9. Value Inspection fallback
    if sample_values:
        clean_vals = [str(v).strip() for v in sample_values if v is not None and str(v).strip()]
        if clean_vals:
            # Check if all samples are pure integers
            if all(v.isdigit() for v in clean_vals):
                return 'number'
            # Check if values look like image filenames (.jpg, .png, etc.)
            img_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
            if any(v.lower().endswith(img_exts) for v in clean_vals):
                return 'photo'

    return 'text'


def detect_table_schema_from_headers(headers: List[str], sample_rows: List[List[Any]] = None) -> List[Dict[str, Any]]:
    """
    Generate table field configurations from parsed headers and sample data rows.
    """
    fields = []
    seen_names = set()

    for col_idx, raw_header in enumerate(headers):
        clean_name = str(raw_header or '').strip()
        if not clean_name:
            clean_name = f"FIELD_{col_idx + 1}"

        # Deduplicate column names
        base_name = clean_name
        counter = 2
        while clean_name.upper() in seen_names:
            clean_name = f"{base_name}_{counter}"
            counter += 1
        seen_names.add(clean_name.upper())

        # Collect sample values for this column
        samples = []
        if sample_rows:
            for r in sample_rows:
                if col_idx < len(r):
                    samples.append(r[col_idx])

        detected_type = detect_field_type(clean_name, samples)

        field_obj = {
            'name': clean_name.upper(),
            'type': detected_type,
            'required': False,
        }
        fields.append(field_obj)

    return fields
