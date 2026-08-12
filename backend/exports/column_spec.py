"""
Column Width Intelligence Module
=================================
SINGLE SOURCE OF TRUTH for column sizing across PDF, Word, and HTML tables.

Given a column heading (field name), this module determines:
  - The canonical field category (e.g. ``full_name``, ``blood_group``, ``mobile``)
  - Minimum / preferred / maximum character widths
  - Whether the column content should wrap or stay on one line
  - Text alignment (left / center / right)

The recognition engine understands 90+ field-name variations commonly
found in Indian ID-card / school / HR systems (see ``FIELD_ALIASES``).

Usage::

    from exports.column_spec import classify_column, get_column_spec

    spec = get_column_spec("Father's Name")
    # => ColumnSpec(category='parent_name', min_chars=8, pref_chars=18,
    #              max_chars=28, wrap=True, align='left', ...)

    spec = get_column_spec("BG")   # Blood Group alias
    # => ColumnSpec(category='blood_group', min_chars=2, pref_chars=4, ...)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

__all__ = [
    'ColumnSpec', 'classify_column', 'get_column_spec',
    'get_pdf_width_percent', 'get_word_width_cm', 'get_html_classes',
]


# ─────────────────────────────────────────────────────────────────────
# 1. Column specifications — one entry per canonical category
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ColumnSpec:
    """Describes sizing & behaviour for a column category."""
    category: str
    # Character-count hints (for proportional width calculation)
    min_chars: int      # absolute minimum chars to display
    pref_chars: int     # preferred / typical content length
    max_chars: int      # beyond this, content MUST wrap
    # Behaviour
    wrap: bool          # True → word-wrap allowed; False → nowrap (numeric/date)
    align: str          # 'left' | 'center' | 'right'
    # PDF-specific (percent of page width)
    pdf_min_pct: float  # minimum column width in %
    pdf_max_pct: float  # maximum column width in %
    # Word-specific (cm)
    word_min_cm: float
    word_max_cm: float
    # HTML Tailwind classes
    html_th_class: str  # width/min-width classes for <th>
    html_td_class: str  # width/wrap/align classes for <td>


# ── Canonical column specs ──────────────────────────────────────────

_SPECS: Dict[str, ColumnSpec] = {}


def _s(category, min_c, pref_c, max_c, wrap, align,
       pdf_min, pdf_max, w_min, w_max, th_cls, td_cls):
    """Shorthand helper to register a ColumnSpec."""
    _SPECS[category] = ColumnSpec(
        category=category,
        min_chars=min_c, pref_chars=pref_c, max_chars=max_c,
        wrap=wrap, align=align,
        pdf_min_pct=pdf_min, pdf_max_pct=pdf_max,
        word_min_cm=w_min, word_max_cm=w_max,
        html_th_class=th_cls, html_td_class=td_cls,
    )


# ── Serial / Row number ─────────────────────────────────────────────
_s('sr_no', 2, 4, 5, False, 'center',
   2.5, 4.0, 0.8, 1.2,
   'w-[36px] min-w-[36px]',
   'w-[36px] text-center whitespace-nowrap')

# ── Names ────────────────────────────────────────────────────────────
_s('full_name', 8, 20, 35, True, 'left',
   6.0, 22.0, 2.5, 8.0,
   'min-w-[90px] max-w-[160px]',
   'min-w-[90px] max-w-[160px] text-left whitespace-normal break-words')

_s('parent_name', 8, 18, 30, True, 'left',
   5.5, 18.0, 2.0, 7.0,
   'min-w-[90px] max-w-[150px]',
   'min-w-[90px] max-w-[150px] text-left whitespace-normal break-words')

_s('guardian_name', 8, 18, 30, True, 'left',
   5.5, 18.0, 2.0, 7.0,
   'min-w-[90px] max-w-[150px]',
   'min-w-[90px] max-w-[150px] text-left whitespace-normal break-words')

_s('spouse_name', 8, 18, 30, True, 'left',
   5.5, 18.0, 2.0, 7.0,
   'min-w-[90px] max-w-[150px]',
   'min-w-[90px] max-w-[150px] text-left whitespace-normal break-words')

# ── Date fields ──────────────────────────────────────────────────────
_s('date', 10, 10, 12, False, 'center',
   6.0, 9.0, 2.4, 3.2,
   'w-[85px] min-w-[85px]',
   'w-[85px] text-center whitespace-nowrap')

# ── Age ──────────────────────────────────────────────────────────────
_s('age', 2, 3, 4, False, 'center',
   2.0, 4.0, 0.7, 1.2,
   'w-[38px] min-w-[38px]',
   'w-[38px] text-center whitespace-nowrap')

# ── Gender ───────────────────────────────────────────────────────────
_s('gender', 1, 6, 12, False, 'center',
   3.0, 5.5, 1.0, 1.8,
   'w-[52px] min-w-[52px]',
   'w-[52px] text-center whitespace-nowrap')

# ── Blood Group ──────────────────────────────────────────────────────
_s('blood_group', 2, 4, 6, False, 'center',
   2.0, 4.5, 0.7, 1.4,
   'w-[44px] min-w-[44px]',
   'w-[44px] text-center whitespace-nowrap')

# ── Nationality / Religion / Caste ───────────────────────────────────
_s('nationality', 4, 8, 15, True, 'center',
   3.5, 8.0, 1.2, 3.0,
   'min-w-[60px]',
   'min-w-[60px] text-center whitespace-normal break-words')

_s('religion', 4, 8, 15, True, 'center',
   3.0, 7.0, 1.0, 2.5,
   'min-w-[55px]',
   'min-w-[55px] text-center whitespace-normal break-words')

_s('caste_category', 3, 5, 10, False, 'center',
   2.5, 5.5, 0.8, 2.0,
   'w-[50px] min-w-[50px]',
   'w-[50px] text-center whitespace-nowrap')

_s('marital_status', 4, 8, 12, False, 'center',
   3.0, 6.0, 1.0, 2.2,
   'w-[55px] min-w-[55px]',
   'w-[55px] text-center whitespace-nowrap')

# ── Relationship (REL 1, REL 2, relation type, etc.) ─────────────────
# Values range from short (FATHER / MOTHER / NANA) to long
# (MATERNAL GRAND MOTHER / PATERNAL GRAND FATHER).  wrap=True so long
# multi-word values break at spaces rather than overflowing the cell.
# max_chars raised to 22 to accommodate the longest known values.
_s('relationship', 3, 12, 22, True, 'center',
   4.5, 9.0, 0.8, 3.0,
   'min-w-[62px] max-w-[120px]',
   'min-w-[62px] max-w-[120px] text-center whitespace-normal break-words')

# ── Images ───────────────────────────────────────────────────────────
_s('photo', 0, 0, 0, False, 'center',
   5.0, 9.0, 1.5, 2.5,
   'w-[60px] min-w-[60px]',
   'w-[60px] text-center')

_s('signature', 0, 0, 0, False, 'center',
   5.0, 9.0, 1.5, 2.5,
   'w-[60px] min-w-[60px]',
   'w-[60px] text-center')

_s('qr_barcode', 0, 0, 0, False, 'center',
   4.0, 7.0, 1.2, 2.0,
   'w-[50px] min-w-[50px]',
   'w-[50px] text-center')

# ── ID Numbers ───────────────────────────────────────────────────────
_s('id_number', 5, 11, 21, False, 'center',
   5.0, 10.5, 1.8, 3.8,
   'min-w-[85px]',
   'min-w-[85px] text-center whitespace-nowrap id-number-col')

_s('aadhaar', 13, 15, 17, False, 'center',
   6.0, 9.5, 2.3, 3.8,
   'w-[110px] min-w-[110px]',
   'w-[110px] text-center whitespace-nowrap id-number-col')

_s('pan', 11, 11, 11, False, 'center',
   5.0, 7.5, 2.0, 3.2,
   'w-[90px] min-w-[90px]',
   'w-[90px] text-center whitespace-nowrap id-number-col')

_s('voter_id', 9, 13, 17, False, 'center',
   5.0, 8.5, 2.0, 3.4,
   'w-[95px] min-w-[95px]',
   'w-[95px] text-center whitespace-nowrap id-number-col')

_s('driving_license', 9, 17, 21, False, 'center',
   5.5, 10.5, 2.2, 3.8,
   'min-w-[100px]',
   'min-w-[100px] text-center whitespace-nowrap id-number-col')

_s('passport_number', 9, 11, 13, False, 'center',
   5.0, 7.5, 2.0, 3.2,
   'w-[90px] min-w-[90px]',
   'w-[90px] text-center whitespace-nowrap id-number-col')

_s('health_id', 9, 15, 21, False, 'center',
   5.0, 8.5, 2.0, 3.4,
   'min-w-[90px]',
   'min-w-[90px] text-center whitespace-nowrap id-number-col')

# ── Phone / Mobile ───────────────────────────────────────────────────
# Allow wrapping so multiple numbers in one field (2-3 contacts) can flow
# to the next line instead of stretching or clipping the row.
_s('mobile', 10, 10, 22, True, 'center',
   6.5, 12.5, 2.4, 4.8,
   'min-w-[105px] max-w-[145px]',
   'min-w-[105px] max-w-[145px] text-center whitespace-normal break-words phone-col')

# Emergency contact numbers are typically a single mobile number and should
# remain on one line in table/PDF cells.
_s('emergency_mobile', 10, 10, 18, False, 'center',
   7.0, 13.0, 2.6, 5.0,
   'min-w-[110px] max-w-[150px]',
   'min-w-[110px] max-w-[150px] text-center whitespace-nowrap phone-col')

# ── Email ────────────────────────────────────────────────────────────
_s('email', 10, 22, 40, True, 'left',
   6.0, 16.0, 2.5, 6.0,
   'min-w-[110px]',
   'min-w-[110px] text-left whitespace-normal break-all')

# ── Address ──────────────────────────────────────────────────────────
# Address columns get a wider min-width so they don't become too narrow on
# small screens.  Vertical wrapping handles long values.
_s('address', 8, 20, 30, True, 'left',
   5.0, 11.5, 2.2, 5.2,
   'min-w-[130px] max-w-[220px]',
   'min-w-[130px] max-w-[220px] text-left whitespace-normal break-words address-col')

_s('city', 4, 10, 20, True, 'center',
   3.0, 7.0, 1.0, 3.0,
   'min-w-[60px]',
   'min-w-[60px] text-center whitespace-normal break-words')

_s('district', 4, 12, 20, True, 'center',
   3.5, 8.0, 1.2, 3.2,
   'min-w-[65px]',
   'min-w-[65px] text-center whitespace-normal break-words')

_s('state', 4, 12, 25, True, 'center',
   3.5, 8.0, 1.2, 3.5,
   'min-w-[65px]',
   'min-w-[65px] text-center whitespace-normal break-words')

_s('pincode', 5, 6, 8, False, 'center',
   3.0, 5.0, 1.0, 2.0,
   'w-[60px] min-w-[60px]',
   'w-[60px] text-center whitespace-nowrap pincode-col')

_s('country', 3, 6, 15, False, 'center',
   3.0, 6.0, 1.0, 2.5,
   'min-w-[55px]',
   'min-w-[55px] text-center whitespace-nowrap')

# ── Organisation / Education ─────────────────────────────────────────
_s('branch', 4, 12, 25, True, 'center',
   3.5, 10.0, 1.2, 4.0,
   'min-w-[65px]',
   'min-w-[65px] text-center whitespace-normal break-words')

_s('department', 4, 14, 25, True, 'center',
   4.0, 12.0, 1.5, 4.5,
   'min-w-[70px]',
   'min-w-[70px] text-center whitespace-normal break-words')

_s('designation', 4, 14, 25, True, 'center',
   4.0, 12.0, 1.5, 4.5,
   'min-w-[70px]',
   'min-w-[70px] text-center whitespace-normal break-words')

_s('course', 4, 12, 30, True, 'center',
   3.5, 10.0, 1.2, 4.0,
   'min-w-[65px]',
   'min-w-[65px] text-center whitespace-normal break-words')

# pdf_min raised to 5.0 % (≈1.43 cm) so the header text "CLASS" / "SECTION"
# fits without breaking mid-character in a fixed-layout table.
_s('class_section', 2, 5, 10, False, 'center',
   5.0, 7.0, 0.7, 1.8,
   'w-[52px] min-w-[52px]',
   'w-[52px] text-center whitespace-nowrap')

_s('batch', 3, 8, 12, False, 'center',
   3.0, 6.0, 1.0, 2.2,
   'w-[55px] min-w-[55px]',
   'w-[55px] text-center whitespace-nowrap')

_s('semester', 2, 4, 6, False, 'center',
   2.0, 4.0, 0.7, 1.5,
   'w-[45px] min-w-[45px]',
   'w-[45px] text-center whitespace-nowrap')

_s('stream', 3, 8, 15, False, 'center',
   3.0, 6.0, 1.0, 2.5,
   'min-w-[55px]',
   'min-w-[55px] text-center whitespace-nowrap')

# ── Employment ───────────────────────────────────────────────────────
_s('employee_type', 4, 10, 15, False, 'center',
   3.5, 8.0, 1.2, 3.0,
   'min-w-[60px]',
   'min-w-[60px] text-center whitespace-nowrap')

_s('grade_level', 2, 5, 10, False, 'center',
   2.5, 5.0, 0.8, 2.0,
   'w-[50px] min-w-[50px]',
   'w-[50px] text-center whitespace-nowrap')

_s('shift_timing', 4, 12, 20, False, 'center',
   4.0, 8.0, 1.2, 3.0,
   'min-w-[65px]',
   'min-w-[65px] text-center whitespace-nowrap')

_s('access_level', 3, 8, 15, False, 'center',
   3.0, 6.0, 1.0, 2.5,
   'min-w-[55px]',
   'min-w-[55px] text-center whitespace-nowrap')

_s('work_location', 4, 14, 25, True, 'center',
   4.0, 10.0, 1.5, 4.0,
   'min-w-[65px]',
   'min-w-[65px] text-center whitespace-normal break-words')

_s('employee_status', 4, 8, 12, False, 'center',
   3.0, 6.0, 1.0, 2.2,
   'w-[55px] min-w-[55px]',
   'w-[55px] text-center whitespace-nowrap')

# ── Defence / Police ─────────────────────────────────────────────────
_s('rank', 3, 10, 20, True, 'center',
   3.5, 8.0, 1.2, 3.5,
   'min-w-[55px]',
   'min-w-[55px] text-center whitespace-normal break-words')

_s('service_number', 5, 10, 16, False, 'center',
   4.0, 8.0, 1.5, 3.0,
   'min-w-[80px]',
   'min-w-[80px] text-center whitespace-nowrap id-number-col')

_s('posting_location', 5, 14, 25, True, 'center',
   4.0, 10.0, 1.5, 4.0,
   'min-w-[65px]',
   'min-w-[65px] text-center whitespace-normal break-words')

_s('validity_period', 6, 12, 20, False, 'center',
   4.5, 8.0, 1.5, 3.0,
   'min-w-[75px]',
   'min-w-[75px] text-center whitespace-nowrap')

# ── Medical ──────────────────────────────────────────────────────────
_s('allergies', 4, 15, 40, True, 'left',
   4.0, 14.0, 1.5, 5.0,
   'min-w-[70px]',
   'min-w-[70px] text-left whitespace-normal break-words')

_s('medical_condition', 4, 15, 40, True, 'left',
   4.0, 14.0, 1.5, 5.0,
   'min-w-[70px]',
   'min-w-[70px] text-left whitespace-normal break-words')

_s('disability', 4, 12, 30, True, 'left',
   3.5, 10.0, 1.2, 4.0,
   'min-w-[65px]',
   'min-w-[65px] text-left whitespace-normal break-words')

# ── Misc short fields ───────────────────────────────────────────────
_s('hostel_room', 3, 6, 10, False, 'center',
   3.0, 5.0, 0.8, 2.0,
   'w-[50px] min-w-[50px]',
   'w-[50px] text-center whitespace-nowrap')

_s('bus_route', 3, 8, 12, False, 'center',
   3.0, 6.0, 1.0, 2.5,
   'w-[55px] min-w-[55px]',
   'w-[55px] text-center whitespace-nowrap')

_s('library_card', 4, 10, 16, False, 'center',
   3.5, 7.0, 1.2, 3.0,
   'min-w-[60px]',
   'min-w-[60px] text-center whitespace-nowrap')

_s('lab_access', 4, 8, 14, False, 'center',
   3.0, 6.0, 1.0, 2.5,
   'w-[55px] min-w-[55px]',
   'w-[55px] text-center whitespace-nowrap')

_s('reporting_manager', 6, 18, 30, True, 'left',
   5.0, 14.0, 2.0, 5.5,
   'min-w-[90px]',
   'min-w-[90px] text-left whitespace-normal break-words')

# ── Fallback (unknown fields) ───────────────────────────────────────
_s('_default', 3, 10, 30, True, 'center',
   3.5, 15.0, 1.2, 5.0,
   'min-w-[70px]',
   'min-w-[70px] text-center whitespace-normal break-words')


# ─────────────────────────────────────────────────────────────────────
# 2. Alias map — maps regex patterns → canonical category
# ─────────────────────────────────────────────────────────────────────
# Order matters: first match wins.  More specific patterns come first.
# Patterns are matched against NORMALISED field name (lowercase,
# whitespace/underscores/dots/apostrophes stripped).

FIELD_ALIASES: List[Tuple[str, str]] = [
    # ── Serial / row ─────────────────────────────────────────────
    # sr no, s.no, sl no, sr.no., serial number, sno, slno
    (r'^sr\.?\s?no\.?$|^s\.?\s?no\.?$|^sl\.?\s?no\.?$|^serial|^sno$|^slno$', 'sr_no'),

    # ── Images (checked early so they don't false-match text rules)
    (r'thumb\s*imp|thumb\s*print', 'photo'),
    (r'photograph|passport\s*size|photo|pic|picture|image|img', 'photo'),
    (r'signature|\bsign\b', 'signature'),   # \bsign\b avoids matching inside 'designation'
    (r'qr\s*code|barcode|rfid|nfc|smart\s*chip|hologram', 'qr_barcode'),

    # ── Parent/guardian phone numbers (checked BEFORE parent name patterns)
    # "FATHER NO", "MOTHER NO", "FATHER MOBILE", "GUARDIAN PHONE" etc.
    (r'fa?the?r\s*(mo?bi?le?|pho?ne?|no\.?|num\b|tell?|cell|contact)\b'
     r'|mothe?r\s*(mo?bi?le?|pho?ne?|no\.?|num\b|tell?|cell|contact)\b'
     r'|parent\s*(mo?bi?le?|pho?ne?|no\.?|num\b|tell?|cell|contact)\b'
     r'|guardian\s*(mo?bi?le?|pho?ne?|no\.?|num\b|tell?|cell|contact)\b', 'mobile'),

    # ── Names (misspellings: fathrs, fathr, mothr, gardian, etc.) ─
    (r'husband|wife|spouse', 'spouse_name'),
    (r'gu?a?rdi?a?n', 'guardian_name'),
    (r'fa?the?r|mothe?r|parent|papa|maa|mata|pita', 'parent_name'),
    (r'full\s*n(a?me?)?|first\s*n(a?me?)?|middle\s*n(a?me?)?'
     r'|last\s*n(a?me?)?|sur\s*n(a?me?)?'
     r'|student\s*n(a?me?)?|emp\s*n(a?me?)?|employee\s*n(a?me?)?'
     r'|^name$|^nm$|^nme$', 'full_name'),
    (r'reporting\s*manager|manager\s*n(a?me?)?', 'reporting_manager'),
    (r'emergency\s*contact\s*person', 'full_name'),
    # Driver / conductor names (checked after guardian/parent so those win first)
    (r'driver\s*(?:full\s*)?name|conductor\s*name', 'full_name'),

    # ── Dates (dob, d.o.b, date of birth, birthdate, joining dt) ─
    (r'd\.?\s*o\.?\s*b\.?|date\s*of\s*birth|birth\s*date|b\.?date', 'date'),
    (r'date\s*of\s*join|join(ing)?\s*date|d\.?o\.?j\.?|join\s*dt', 'date'),
    (r'valid\s*(from|till|upto)|validity|expiry|expire', 'validity_period'),
    (r'\bdate\b|\bdt\b', 'date'),

   # ── Age ──────────────────────────────────────────────────────
   (r'^age$|^umar$', 'age'),

   # ── Gender (sex, gndr, gendr, gen der) ───────────────────────
   (r'gender|gen\s*der|^sex$|^gndr$|^gendr$', 'gender'),

    # ── Blood Group (blood gr, bg, bgroup, b.g., bld gr, blood_grup,
    #    bloodgrp, blod, blood grp, blud, blod group, b grp) ──────
    (r'blo?o?d\s*gr|blo?o?d\s*gro?u?p|^bg$|^bgroup$|^b\.?g\.?$'
     r'|^bld\s*gr|^blud|^blod|blo+d\s*grp|b\s*grp', 'blood_group'),
    # ── Relationship / Relation type (REL 1, REL 2, relation, etc.) ──
    # Must come BEFORE religion to avoid 'relation' → 'religion' clash.
    (r'^rel\s*\d*$|^relati?v|^relati?o?n|guardian\s*rel|parent\s*rel|relative\s*of', 'relationship'),
    # ── Nationality / Religion / Caste ───────────────────────────
    (r'nat[io]+na?li?ty?|^nation$', 'nationality'),
    (r'religi?o?n|^rlgn$', 'religion'),
    (r'caste|catego?r?y?|^cat$|gen.*obc.*sc|sc.*st|^obc$|^gen$', 'caste_category'),
    (r'marita?l|marri?e?d|unmarri?e?d', 'marital_status'),

    # ── Aadhaar (aadhar, aadhaar, adhar, adhaar, aadhr, aadar,
    #    aadhar no, adhar number, uid no) ─────────────────────────
    (r'a+dh?a+r|a+dhr|uidai|uid\s*no', 'aadhaar'),

   # ── PAN (include common typo "PEN") ─────────────────────────
   (r'^p[ae]n$|p[ae]n\s*no|p[ae]n\s*num|p[ae]n\s*card', 'pan'),

    # ── Voter ID ─────────────────────────────────────────────────
    (r'voter\s*id|epic\s*no|votr', 'voter_id'),

    # ── Driving License (driving lisence, licence, licnse, dl no) ─
    (r'driv\w*\s*li[cs]?en[cs]?e?|^dl$|dl\s*no|dl\s*num', 'driving_license'),

    # ── Passport ─────────────────────────────────────────────────
    (r'passport\s*no|passport\s*num|^ppn$', 'passport_number'),

    # ── Ration Card ──────────────────────────────────────────────
    (r'ration\s*card', 'id_number'),

    # ── Health IDs ───────────────────────────────────────────────
    (r'abha|ayushman|health\s*id', 'health_id'),

    # ── ESIC / PF / UAN ─────────────────────────────────────────
    (r'esic|\bpf\b|uan\s*no|uan\s*num|\buan\b|\bepf\b', 'id_number'),

    # ── Generic ID numbers ───────────────────────────────────────
    (r'id\s*card\s*no|id\s*card\s*num|id\s*no|idno|^id$', 'id_number'),
    (r'roll\s*no|roll\s*num|^roll$', 'id_number'),
    (r'emp\s*code|employee\s*code|emp\s*id|staff\s*id', 'id_number'),
    (r'admis?si?on\s*(?:no|num\w*)|adm\s*no', 'id_number'),
    (r'reg\s*no|registra?ti?on|enrol', 'id_number'),
    (r'service\s*no|service\s*num', 'service_number'),
    # Extra ID types common in Indian schools / organisations
    (r'scholar\s*(?:no|num|id|code)?\b|^scholar$', 'id_number'),
    (r'unique\s*(?:no|num|id|code)|^unique$', 'id_number'),
    (r'teacher\s*(?:code|id|no)|^sch\s*no$|\bsch\s*no\b|school\s*(?:no|num|id)', 'id_number'),

      # ── Misc short (BEFORE phone to prevent false matches) ─────
      (r'hostel|room\s*no', 'hostel_room'),
      # House / Route labels in school sheets (including common typo: RUTE)
      (r'^house$|house\s*(?:no|num|number)$', 'class_section'),
      (r'^route$|^rute$|route\s*(?:no|num|number|code|name)$', 'bus_route'),
      (r'^transport$|^transpor$|trans\s*port|tran\s*sport|transport\s*(?:mode|type|detail)?', 'bus_route'),
      (r'bus\s*route|bus\s*stop|\bbus\s*no\b', 'bus_route'),
      (r'stop\s*name|stop\s*no|stop\s*num|route\s*(?:no|num|name)', 'bus_route'),
      (r'library\s*card|library\s*no', 'library_card'),
      (r'lab\s*access|lab\s*code', 'lab_access'),
      # Bus / vehicle staff contact (put BEFORE general phone pattern)
      (r'driver\s*(?:no\b|numb?\w*|mob|pho?ne?|cell|contact|tel)', 'mobile'),

      # ── Emergency contact number (abbreviated + full forms) ──────
      (r'emerg(?:ency)?\s*cont(?:act)?\s*'
       r'(?:no\.?|num(?:ber)?|mob(?:ile)?|pho?ne?|tel|cell)?', 'emergency_mobile'),

      # ── Phone / Mobile (mob, mob no, ph no, fone, contact num) ───
      (r'mobi?le?|pho?ne?|cell\b|tel\b|whatsapp|^mob\b|^ph\b|fone'
       r'|emergency\s*contact\s*num'
       r'|office\s*contact|alternate\s*mob|alt\s*mob'
       r'|contact\s*no|contact\s*num', 'mobile'),

      # ── Email (e-mail, email id, mail id, emailid) ──────────────
      (r'e?\s*mail|mail\s*id', 'email'),

    # ── Address (addr, addrs, adress, adrs, permanent address, residence) ──
    (r'addr|adre?s|residen|location|locality|village|town|city|distt?|state|province|landmark|sector|block|area', 'address'),
    (r'^city$|^town$|^village$|^vill$', 'city'),
    (r'^district$|^dist$|^distt$', 'district'),
    (r'^state$|^province$', 'state'),
    (r'pin\s*code|^pin$|^zip$|postal\s*code|^pincode$', 'pincode'),
    (r'^country$', 'country'),

    # ── Organisation / Education ─────────────────────────────────
    # Institution / school / college names (before branch to be more specific)
    (r'college\s*name|^college$|school\s*name|^school$'
     r'|institu\w*\s*name|^institute$|^institution$|^university$', 'branch'),
    (r'^branch$|branch\s*name', 'branch'),
    (r'^depart?me?nt$|^dept$|depart?me?nt\s*name', 'department'),
    # Designation: no strict anchors so 'post/designation' matches too
    (r'designa?ti?on|\bdesig\b|\bpost\b', 'designation'),
    (r'course\s*n(a?me?)?|^course$|course\s*dur', 'course'),
    # House names (colour/badge): checked BEFORE general class/section
    (r'school\s*house|house\s*(?:name|col|badge|colour|color)', 'class_section'),
    # Class/section — compound form ('Class / Section') and simple
    (r'class\s*section|class\s*sec\b|^class$|^section$|^sec$|^div$|^division$|^cls$', 'class_section'),
    (r'^batch$|^batch\s*no', 'batch'),
    (r'^semester$|^sem$', 'semester'),
    (r'^stream$|science.*commerce.*arts|^strm$', 'stream'),

    # ── Employment ───────────────────────────────────────────────
    (r'emp\s*type|employee\s*type|permanent.*contract|contract.*intern', 'employee_type'),
    (r'grade\s*level|^grade$|pay\s*grade', 'grade_level'),
    (r'shift|timing', 'shift_timing'),
    (r'access\s*level|security\s*level', 'access_level'),
    (r'work\s*loc|office\s*loc|posting\s*loc|posted\s*at', 'posting_location'),
    (r'emp\s*status|employee\s*status|^status$', 'employee_status'),

    # ── Defence / Police ─────────────────────────────────────────
    (r'\brank\b', 'rank'),   # word-boundary: catches 'Rank (Police/Defense)' too

    # ── Medical ──────────────────────────────────────────────────
    (r'allerg', 'allergies'),
    (r'medical\s*cond|medical\s*hist|health\s*cond', 'medical_condition'),
    (r'disabilit|handicap|divyang', 'disability'),

    (r'year\s*of\s*join', 'date'),
]

# Compile patterns once
_COMPILED_ALIASES: List[Tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), category)
    for pattern, category in FIELD_ALIASES
]


# ─────────────────────────────────────────────────────────────────────
# 3. Public API
# ─────────────────────────────────────────────────────────────────────

def _normalise_name(name: str) -> str:
    """Normalise a field/column name for matching.

    Strips whitespace, underscores, dots, apostrophes, hyphens;
    collapses to single-spaced lowercase.
    """
    s = name.strip()
    # Replace separators with space
    s = re.sub(r"[_.\-'\"()/]+", ' ', s)
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip().lower()
    return s


def classify_column(field_name: str, field_type: str = '') -> str:
    """
    Classify a column heading into a canonical category.

    Args:
        field_name: The column heading (e.g. "Father's Name", "BG", "Mob No")
        field_type: Optional explicit field type from table config
                    (e.g. 'photo', 'signature', 'date', 'textarea')

    Returns:
        Canonical category string (e.g. 'full_name', 'blood_group', 'mobile')
    """
    ft = (field_type or '').lower().strip()

    # Explicit type shortcuts
    if ft in ('photo', 'rel_photo', 'image', 'mother_photo', 'father_photo'):
        return 'photo'
    if ft == 'signature':
        return 'signature'
    if ft in ('barcode', 'qr_code', 'qr'):
        return 'qr_barcode'
    if ft == 'date':
        return 'date'
    if ft == 'textarea':
        return 'address'

    norm = _normalise_name(field_name)
    if not norm:
        return '_default'

    for pattern, category in _COMPILED_ALIASES:
        if pattern.search(norm):
            return category

    return '_default'


def get_column_spec(field_name: str, field_type: str = '') -> ColumnSpec:
    """
    Get the full ColumnSpec for a field.

    Args:
        field_name: Column heading
        field_type: Optional explicit type

    Returns:
        ColumnSpec dataclass with all sizing / behaviour info
    """
    category = classify_column(field_name, field_type)
    return _SPECS.get(category, _SPECS['_default'])


def get_pdf_width_percent(field_name: str, field_type: str = '') -> Tuple[float, float]:
    """Return (min_pct, max_pct) for PDF column width."""
    spec = get_column_spec(field_name, field_type)
    return spec.pdf_min_pct, spec.pdf_max_pct


def get_word_width_cm(field_name: str, field_type: str = '') -> Tuple[float, float]:
    """Return (min_cm, max_cm) for Word column width."""
    spec = get_column_spec(field_name, field_type)
    return spec.word_min_cm, spec.word_max_cm


def get_html_classes(field_name: str, field_type: str = '') -> Tuple[str, str]:
    """Return (th_class, td_class) for HTML table columns."""
    spec = get_column_spec(field_name, field_type)
    return spec.html_th_class, spec.html_td_class


def is_nowrap_column(field_name: str, field_type: str = '') -> bool:
    """Check if a column should not wrap its content."""
    return not get_column_spec(field_name, field_type).wrap


def get_column_align(field_name: str, field_type: str = '') -> str:
    """Return 'left', 'center', or 'right'."""
    return get_column_spec(field_name, field_type).align
