"""
PDF Export Module

Handles PDF file generation for ID card data using WeasyPrint.
This module is READ-ONLY - it never mutates data.

Features:
- Landscape A4 format
- Dynamic column widths based on content
- Supports text + image fields
- Repeating header/footer on every page via CSS @page margin boxes
- UPPERCASE text for printing clarity
- Images rendered at fixed subtype dimensions (photo: 1.9×2.5cm, etc.)
- 0.5cm left/right, 2.0cm top / 1.2cm bottom page margins
- Exactly 6 rows per page (class-break aware) via CSS page-break
- CSS overflow-wrap / word-break / hyphens for proper Unicode wrapping
"""
import os
import io
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from django.utils import timezone as django_tz
from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.db.models import QuerySet

from mediafiles.services import ImageService
from core.utils.template_rich_text import rich_text_to_plain_text

from .utils import (
    separate_fields_by_type,
    generate_export_filename,
    format_field_value,
    is_valid_image_path,
    sort_cards_for_export,
    get_class_field_name,
    get_section_field_name,
    stream_file_response,
    humanize_label,
)

from .column_spec import get_column_spec, classify_column, is_nowrap_column

logger = logging.getLogger(__name__)

# Absolute path to the placeholder image shown when a record has no photo
_PLACEHOLDER_IMAGE_PATH = os.path.join(
    settings.BASE_DIR, 'static', 'assets', 'no-image-placeholder.png'
)

# Tiny 1x1 transparent PNG as base64 data URI fallback when placeholder file missing
_TRANSPARENT_PNG_DATA_URI = (
    'data:image/png;base64,'
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA'
    'ASsJTYQAAAAASUVORK5CYII='
)


_STATUS_LIST_LABELS = {
    'pending': 'Pending List',
    'verified': 'Verified List',
    'approved': 'Approved List',
    'download': 'Download List',
    'pool': 'Pool List',
}


def _path_to_file_uri(abs_path: str) -> str:
    """Convert an absolute filesystem path to a file:// URI for WeasyPrint."""
    from pathlib import Path
    return Path(abs_path).as_uri()


def _resolve_safe_media_path(img_path: str) -> Optional[str]:
    """Resolve a media-relative image path while blocking traversal/absolute escapes."""
    raw = str(img_path or '').strip().replace('\\', '/')
    if not raw:
        return None
    if raw.startswith('/') or os.path.isabs(raw):
        return None

    parts = [part for part in raw.split('/') if part]
    if not parts or any(part in ('.', '..') for part in parts):
        return None

    media_root = os.path.abspath(settings.MEDIA_ROOT)
    candidate = os.path.abspath(os.path.join(media_root, *parts))
    try:
        if os.path.commonpath([media_root, candidate]) != media_root:
            return None
    except ValueError:
        return None
    return candidate


@dataclass
class PdfExportResult:
    """Result of a PDF export operation."""
    success: bool
    message: str = ''
    response: Optional[HttpResponse] = None
    filename: str = ''
    card_count: int = 0


# ── Font-mode presets ───────────────────────────────────────────────
# Data font is ALWAYS 9pt regardless of mode (no font-size shrinking).
# Compact/condensed modes only reduce cell padding and tighten column budgets.
_FONT_MODES = {
    'normal': {
        'font_family': 'Arial, Helvetica, sans-serif',
        'header_pt': '9pt',
        'data_pt': '9pt',
        'char_width_cm': 0.18,   # ~9pt bold uppercase Arial
        'header_line_cm': 0.28,
        'header_base_cm': 0.10,
        'is_compact': False,
        'cell_padding': '1px',
    },
    'compact': {
        'font_family': 'Arial, Helvetica, sans-serif',
        'header_pt': '9pt',
        'data_pt': '9pt',
        'char_width_cm': 0.18,
        'header_line_cm': 0.28,
        'header_base_cm': 0.10,
        'is_compact': True,
        'cell_padding': '1px',
    },
    'condensed': {
        'font_family': 'SairaSemiCondensed, Arial, Helvetica, sans-serif',
        'header_pt': '9pt',
        'data_pt': '9pt',
        'char_width_cm': 0.14,   # condensed variant — narrower glyph width
        'header_line_cm': 0.24,
        'header_base_cm': 0.10,
        'is_compact': True,
        'cell_padding': '1px',
    },
}

# ── Column title shortening map ──────────────────────────────────────────────
# Keys must be UPPER-CASE (labels have already been humanised + upper-cased).
# Applied only when the caller passes shorten_titles=True.
TITLE_SHORTENING_MAP: dict = {
    # Date / identifier fields
    'DATE OF BIRTH':        'DOB',
    'D O B':                'DOB',
    # Blood / medical
    'BLOOD GROUP':          'BLD GRP',
    # National fields
    'NATIONALITY':          'NATNL.',
    'RELIGION':             'REL.',
    # Parent / guardian names
    "FATHER NAME":          "F. NAME",
    "FATHER S NAME":        "F. NAME",
    "FATHERS NAME":         "F. NAME",
    "MOTHER NAME":          "M. NAME",
    "MOTHER S NAME":        "M. NAME",
    "MOTHERS NAME":         "M. NAME",
    "GUARDIAN NAME":        "GUARD. NAME",
    # Contact
    'MOBILE NUMBER':        'MOB.',
    'MOBILE NO':            'MOB.',
    'MOBILE':               'MOB.',
    'CONTACT NUMBER':       'CONT. NO.',
    'CONTACT NO':           'CONT. NO.',
    'PHONE NUMBER':         'PHONE',
    'PHONE NO':             'PHONE',
    # Address variants
    'PERMANENT ADDRESS':    'PERM. ADDR.',
    'PRESENT ADDRESS':      'PRES. ADDR.',
    'RESIDENTIAL ADDRESS':  'RES. ADDR.',
    'TEMPORARY ADDRESS':    'TEMP. ADDR.',
    'CORRESPONDENCE ADDRESS': 'CORR. ADDR.',
    'ADDRESS':              'ADDR.',
    # Academic
    'SECTION':              'SEC.',
    'ENROLLMENT NUMBER':    'ENR. NO.',
    'ENROLLMENT NO':        'ENR. NO.',
    'REGISTRATION NUMBER':  'REG. NO.',
    'REGISTRATION NO':      'REG. NO.',
    'ROLL NUMBER':          'ROLL NO.',
    # Professional
    'DESIGNATION':          'DESIG.',
    'QUALIFICATION':        'QUAL.',
    'OCCUPATION':           'OCC.',
    'DEPARTMENT':           'DEPT.',
    # Aadhaar / PAN (already short, but standardise spacing)
    'AADHAR NUMBER':        'AADHAAR',
    'AADHAAR NUMBER':       'AADHAAR',
    'PAN NUMBER':           'PAN',
    # Category / caste
    'CATEGORY':             'CATG.',
    # Academic / institutional
    'ADMISSION NUMBER':     'ADM. NO.',
    'ADMISSION NO':         'ADM. NO.',
    'DATE OF JOINING':      'DOJ',
    'DATE OF JOIN':         'DOJ',
    'YEAR OF PASSING':      'YOP',
    'ACADEMIC YEAR':        'ACAD. YR.',
    'STUDENT NAME':         'STD. NAME',
    'EMPLOYEE NAME':        'EMP. NAME',
    'EMPLOYEE CODE':        'EMP. CODE',
    'EMPLOYEE ID':          'EMP. ID',
    'STAFF ID':             'STAFF ID',
    # Identification
    'VOTER ID':             'VOTER ID',
    'VOTER ID NUMBER':      'VOTER ID',
    'VOTER ID NO':          'VOTER ID',
    'DRIVING LICENSE':      'DL NO.',
    'DRIVING LICENCE':      'DL NO.',
    'PASSPORT NUMBER':      'PASSPORT',
    'SCHOLARSHIP NUMBER':   'SCH. NO.',
    'SCHOLARSHIP NO':       'SCH. NO.',
    # Personal
    'MARITAL STATUS':       'MAR. STS.',
    'MOTHER TONGUE':        'MTH. TNGUE.',
    'EMERGENCY CONTACT':    'EMER. CONT.',
    'EMERGENCY CONTACT NO': 'EMER. CONT. NO.',
    'EMERGENCY CONTACT NUMBER': 'EMER. CONT. NO.',
    'EMERG CONT NO':        'EMER. CONT. NO.',
    'EMERG. CONT. NO':      'EMER. CONT. NO.',
    'DRIVER MOBILE':        'DRIVER MOB.',
    'DRIVER MOB':           'DRIVER MOB.',
    'TRANSPORT MODE':       'TRANSPORT',
    'TRANSPORT TYPE':       'TRANSPORT',
    'ALTERNATE MOBILE':     'ALT. MOB.',
    'ALTERNATE NUMBER':     'ALT. NO.',
    'ALTERNATE NO':         'ALT. NO.',
    # Financial
    'BANK ACCOUNT NUMBER':  'A/C NO.',
    'BANK ACCOUNT NO':      'A/C NO.',
    'ANNUAL INCOME':        'INCOME',
    'IFSC CODE':            'IFSC',
    # Address extras
    'HOME ADDRESS':         'HOME ADDR.',
    'OFFICE ADDRESS':       'OFFICE ADDR.',
    'HOUSE NUMBER':         'HOUSE NO.',
    'HOUSE NO':             'HOUSE NO.',
    'WARD NUMBER':          'WARD NO.',
    'BLOCK NUMBER':         'BLOCK NO.',
    'OFFICIAL EMAIL':       'OFF. EMAIL',
}


class PdfExporter:
    """
    Handles PDF export operations using WeasyPrint.

    Features:
    - Landscape A4 with dynamic column widths
    - Text fields + image fields rendered side by side
    - Repeating header and footer on every page via CSS @page margin boxes
    - UPPERCASE text for printing clarity
    - Image dimensions fixed per subtype (photo: 1.9×2.5cm, signature: 1.9×0.5cm, etc.)
    - 0.5cm left/right, 1.5cm top/bottom page margins
    - Exactly 6 rows per page (class-break aware) using CSS page-break

    Usage:
        exporter = PdfExporter()
        result = exporter.export_cards(table, cards)
        if result.success:
            return result.response
    """

    # Column width bounds (percentage)
    MIN_COL_WIDTH = 4.0
    MAX_COL_WIDTH = 30.0
    # Minimum width for non-wrappable fields (mobile, DOB, Aadhar, etc.)
    MIN_NOWRAP_COL_WIDTH = 5.5
    # Landscape A4 content width (29.7cm page - 0.5cm left - 0.5cm right margins)
    PAGE_CONTENT_WIDTH_CM = 28.7
    # Maximum image height so that exactly 6 data rows fit on one A4 landscape page.
    # A4 landscape body height = 210mm - 20mm (top) - 12mm (bottom) = 178mm = 17.8cm
    # header row ≈ 0.5cm; available for 6 rows = 17.3cm; per row = 2.88cm
    # subtract vertical cell-padding (2pt × 2 ≈ 0.14cm) and border ≈ 0.04cm → safe cap.
    MAX_IMAGE_HEIGHT_CM = 2.6

    # ── Dense-table threshold ──
    # total_cols includes SR NO column.  Data columns = total_cols - 1.
    # Compact mode triggers only when DATA columns > 15, i.e. total_cols > 16.
    DENSE_COLUMN_THRESHOLD = 16

    @staticmethod
    def _build_center_header_title(table_name: str, status: str) -> str:
        """Return center header title as list label, with table fallback."""
        label = _STATUS_LIST_LABELS.get((status or '').strip().lower())
        if label:
            return f'{table_name} - {label}'
        return table_name

    def export_cards(
        self,
        table,
        cards: QuerySet,
        status: str = '',
        template_id: int = None,
        font_mode: str = 'auto',
        shorten_titles: bool = False,
        break_mode: str = 'class_section',
        progress_callback=None,
        user=None,
        cancel_check=None,
    ) -> PdfExportResult:
        """
        Export cards to PDF format.

        Args:
            table: Table instance
            cards: QuerySet of IDCard instances
            status: Status label for filename
            template_id: Optional ExportTemplate ID for footer text
            font_mode: 'auto' | 'normal' | 'compact' | 'condensed'
                       'auto' uses normal for ≤15 cols, compact for >15
            shorten_titles: When True, long column headings are replaced with
                            short abbreviations (e.g. "Date Of Birth" → "DOB").
            break_mode: 'class_only' or 'class_section' page grouping mode.

        Returns:
            PdfExportResult with HttpResponse if successful
        """
        _weasyprint_available = False
        _xhtml2pdf_available = False
        WeasyHTML = None
        
        try:
            from weasyprint import HTML as WeasyHTML
            _weasyprint_available = True
        except (ImportError, OSError) as _wp_err:
            # ImportError: weasyprint not installed
            # OSError: native libraries not found (GTK/Pango missing)
            _wp_msg = str(_wp_err)
            logger.warning("WeasyPrint not available: %s. Trying xhtml2pdf fallback.", _wp_msg[:100])
        
        # Try xhtml2pdf as fallback
        if not _weasyprint_available:
            try:
                from xhtml2pdf import pisa
                _xhtml2pdf_available = True
            except ImportError:
                pass
        
        # If neither is available, return helpful error
        if not _weasyprint_available and not _xhtml2pdf_available:
            import sys as _sys
            if _sys.platform == 'win32':
                return PdfExportResult(
                    success=False,
                    message=(
                        'PDF export requires GTK runtime on Windows or xhtml2pdf. '
                        'Please install xhtml2pdf: pip install xhtml2pdf'
                    )
                )
            else:
                return PdfExportResult(
                    success=False,
                    message=(
                        'PDF export requires WeasyPrint or xhtml2pdf. Please install one: '
                        'pip install weasyprint xhtml2pdf'
                    )
                )

        if not cards.exists():
            return PdfExportResult(
                success=False,
                message='No cards to export!'
            )

        try:
            # Get all fields (text + image)
            all_fields = table.fields or []
            field_info = separate_fields_by_type(all_fields)
            text_fields = field_info['text']
            image_fields = field_info['image']
            ordered_fields = text_fields + image_fields

            if not ordered_fields:
                return PdfExportResult(
                    success=False,
                    message='No fields found in table configuration!'
                )

            # Column count guard — beyond 25 the layout becomes unreadable
            MAX_PDF_COLUMNS = 25
            if len(ordered_fields) > MAX_PDF_COLUMNS:
                return PdfExportResult(
                    success=False,
                    message=(
                        f'PDF export supports a maximum of {MAX_PDF_COLUMNS} columns '
                        f'({len(ordered_fields)} selected). Remove some fields from the '
                        f'table configuration to proceed, or use Excel export instead.'
                    )
                )

            # Sort cards for export (Class → Section → Name)
            cards_list = sort_cards_for_export(cards, table.fields)
            column_configs = self._build_column_configs(ordered_fields, cards_list, shorten_titles=shorten_titles)

            # ── Resolve font mode ────────────────────────────────
            total_cols = len(column_configs)  # includes SR NO
            resolved_font_mode = font_mode
            if resolved_font_mode == 'auto':
                if total_cols > 20:  # >20 data cols: SairaSemiCondensed saves ~22% width
                    resolved_font_mode = 'condensed'
                elif total_cols > self.DENSE_COLUMN_THRESHOLD:
                    resolved_font_mode = 'compact'
                else:
                    resolved_font_mode = 'normal'
            if resolved_font_mode not in _FONT_MODES:
                resolved_font_mode = 'normal'
            font_preset = _FONT_MODES[resolved_font_mode]

            # ── Auto-tiered font size based on column count ──────
            # >23 cols → 6.5pt, >20 cols → 7pt, >15 cols → 7.5pt, ≤15 → 8pt
            if total_cols > 23:
                _auto_pt = '6.5pt'
            elif total_cols > 20:
                _auto_pt = '7pt'
            elif total_cols > 15:
                _auto_pt = '7.5pt'
            else:
                _auto_pt = '8pt'
            data_font_size = _auto_pt

            # Compute dynamic row height from tallest image column
            max_img_h = 0
            for cfg in column_configs:
                if cfg.get('is_image') and 'image_height_cm' in cfg:
                    max_img_h = max(max_img_h, cfg['image_height_cm'])
            row_height_cm = round(max_img_h + 0.15, 2) if max_img_h > 0 else 0.8

            # Build row data (file:// image URIs for WeasyPrint)
            rows = self._build_rows(
                ordered_fields,
                cards_list,
                column_configs,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )

            if rows is None:
                return PdfExportResult(success=False, message='Export cancelled')

            # Get institution name
            institution_name = "Institution"
            if getattr(table, 'organisation', None):
                institution_name = table.organisation.name

            # Fetch template footer text if template_id provided
            from core.models import ExportTemplate
            template_footer_text = ''
            template_font = 'arial'
            template_use_abbasi = False
            template_bold = False
            if template_id:
                try:
                    tpl = ExportTemplate.objects.get(id=template_id)
                    template_footer_text = rich_text_to_plain_text(tpl.instructions or '').strip()
                    template_font = str(tpl.font_name or 'arial').strip().lower()
                    template_use_abbasi = template_font in {'hindi', 'abbasi', 'abbasinatraj', 'abbasi_natraj'}
                    template_bold = tpl.is_bold
                except ExportTemplate.DoesNotExist:
                    pass

            # Group rows into pages (fixed 6 rows per page, class-break aware)
            class_field_name = get_class_field_name(table.fields)
            resolved_break_mode = str(break_mode or 'class_section').strip().lower()
            if resolved_break_mode not in ('class_only', 'class_section'):
                resolved_break_mode = 'class_section'
            section_field_name = (
                get_section_field_name(table.fields)
                if resolved_break_mode == 'class_section'
                else None
            )
            pages = self._group_rows_into_pages(
                rows,
                cards_list,
                class_field_name,
                section_field_name,
                records_per_page=6,
            )

            # Build font dir path for @font-face in CSS
            font_dir = _path_to_file_uri(
                os.path.join(settings.BASE_DIR, 'static', 'fonts')
            )

            # Render HTML
            _now = django_tz.localtime(django_tz.now())
            context = {
                'columns': column_configs,
                'pages': pages,
                'total_pages': len(pages),
                'institution_name': institution_name,
                'table_name': table.name,
                'center_list_name': self._build_center_header_title(table.name, status),
                'current_date': _now.strftime('%d-%m-%Y'),
                'template_footer_text': template_footer_text,
                'template_font': template_font,
                'template_use_abbasi': template_use_abbasi,
                'template_bold': template_bold,
                'row_height_cm': row_height_cm,
                # Font-mode context for template
                'font_family': font_preset['font_family'],
                'header_font_size': data_font_size,
                'data_font_size': data_font_size,
                'font_mode': resolved_font_mode,
                'font_dir': font_dir,
                # Layout-mode flags (compact = >15 data columns)
                'is_compact': font_preset['is_compact'],
                'cell_padding': font_preset['cell_padding'],
                'use_pisa_fallback': (not _weasyprint_available),
            }

            html_string = render_to_string('exports/pdf_report.html', context)
            filename = generate_export_filename(table.name, 'pdf', client_name=institution_name, status=status)

            # Generate PDF using WeasyPrint or xhtml2pdf fallback
            # Write directly to a temp file on disk to avoid large in-memory blobs.
            import tempfile as _tempfile
            import os as _os
            from django.http import StreamingHttpResponse

            tmpf = _tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            tmpf_path = tmpf.name
            tmpf.close()

            try:
                if _weasyprint_available and WeasyHTML:
                    # WeasyPrint — write directly to file path
                    base_url = _path_to_file_uri(str(settings.BASE_DIR))
                    WeasyHTML(string=html_string, base_url=base_url).write_pdf(target=tmpf_path)
                else:
                    # xhtml2pdf fallback — write to file-like object
                    from xhtml2pdf import pisa

                    def link_callback(uri, rel):
                        """Convert relative paths to absolute paths for xhtml2pdf.
                        Validates resolved path stays inside BASE_DIR to prevent traversal.
                        """
                        if uri.startswith('file://'):
                            path = uri[7:]
                            if path.startswith('/') and len(path) > 2 and path[2] == ':':
                                path = path[1:]
                            return path.replace('/', _os.sep)
                        if uri.startswith('/'):
                            base = _os.path.realpath(str(settings.BASE_DIR))
                            resolved = _os.path.realpath(_os.path.join(base, uri.lstrip('/')))
                            if not resolved.startswith(base + _os.sep) and resolved != base:
                                logger.warning('link_callback: blocked path traversal attempt: %r', uri)
                                return _os.path.join(base, 'static', 'assets', 'no-image-placeholder.png')
                            return resolved
                        return uri

                    # xhtml2pdf fallback — write to file-like object
                    import datetime
                    _pisa_start = datetime.datetime.utcnow()
                    with open(tmpf_path, 'wb') as _out:
                        pisa_status = pisa.CreatePDF(
                            io.BytesIO(html_string.encode('utf-8')),
                            dest=_out,
                            link_callback=link_callback
                        )
                    _pisa_end = datetime.datetime.utcnow()
                    logger.info('xhtml2pdf.render duration_seconds=%.2f', (_pisa_end - _pisa_start).total_seconds())
                    if pisa_status.err:
                        logger.error("xhtml2pdf errors: %s", pisa_status.err)
                        try:
                            _os.unlink(tmpf_path)
                        except Exception:
                            pass
                        return PdfExportResult(success=False, message='PDF generation failed. Please try again.')

                # Stream the temp file as a StreamingHttpResponse and clean up after
                file_size = 0
                try:
                    file_size = int(_os.path.getsize(tmpf_path) or 0)
                except Exception:
                    file_size = 0

                def _iter_file(chunk_size=1024 * 1024):
                    try:
                        with open(tmpf_path, 'rb') as fh:
                            while True:
                                chunk = fh.read(chunk_size)
                                if not chunk:
                                    break
                                yield chunk
                    finally:
                        try:
                            _os.unlink(tmpf_path)
                        except Exception:
                            pass

                response = StreamingHttpResponse(_iter_file(), content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                if file_size:
                    response['Content-Length'] = str(file_size)

                return PdfExportResult(
                    success=True,
                    response=response,
                    filename=filename,
                    card_count=len(cards_list)
                )
            except Exception as e:
                # Cleanup temp file on unexpected error
                try:
                    if _os.path.exists(tmpf_path):
                        _os.unlink(tmpf_path)
                except Exception:
                    pass
                logger.exception("PDF export failed: %s", e)
                return PdfExportResult(success=False, message='PDF export failed. Please try again or contact support.')

        except Exception as e:
            logger.error("PDF export failed: %s", e, exc_info=True)
            return PdfExportResult(
                success=False,
                message='PDF export failed. Please try again or contact support.'
            )


    @classmethod
    def _is_nowrap_field(cls, field_name: str) -> bool:
        """Check if a field contains non-wrappable data (phone, DOB, ID numbers, etc.)."""
        return is_nowrap_column(field_name)

    @classmethod
    def _looks_numeric_or_date(cls, value: str) -> bool:
        """Check if a value is primarily numeric/date-like (shouldn't be wrapped)."""
        if not value:
            return False
        digits_seps = sum(1 for c in value if c.isdigit() or c in '/-.:+ ')
        return digits_seps >= len(value) * 0.6



    def _build_column_configs(
        self,
        ordered_fields: List[Dict[str, Any]],
        cards: list,
        shorten_titles: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Calculate dynamic column widths based on field semantics + data content.

        Uses ``column_spec`` intelligence to determine min/max bounds, nowrap
        behaviour, and alignment for every field category.  Then distributes
        remaining page width proportionally (P90 content length).

        Algorithm:
        - Image columns: fixed percentage from subtype dimensions.
        - Text columns: share remaining width proportionally, clamped by
          semantic min/max from ``column_spec``.
        """
        from .column_spec import get_column_spec, classify_column

        # ── Sr No column ────────────────────────────────────────
        sr_spec = get_column_spec('SR NO')
        configs = [{
            'label': 'SR NO',
            'width': 0,
            'align': sr_spec.align,
            'is_image': False,
            'nowrap': not sr_spec.wrap,
        }]

        for field in ordered_fields:
            name = field['name']
            ftype = field.get('type', 'text')
            is_image = field.get('is_image', False)
            spec = get_column_spec(name, ftype)
            humanized = humanize_label(name.upper())
            if shorten_titles:
                humanized = TITLE_SHORTENING_MAP.get(humanized, humanized)
            # Short single-word headers should not wrap
            header_nowrap = ' ' not in humanized.strip() and len(humanized) <= 12
            configs.append({
                'label': humanized,
                'width': 0,
                'align': spec.align,
                'is_image': is_image,
                'nowrap': not spec.wrap,
                'header_nowrap': header_nowrap,
                '_spec': spec,  # carry spec for clamping later
            })

        # ── Auto-detect nowrap from data (safety net) ───────────
        for i, cfg in enumerate(configs):
            if cfg['is_image'] or cfg['nowrap'] or i == 0:
                continue
            # Respect spec's explicit wrap=True (e.g. phone columns that may
            # carry slash-joined double numbers must remain wrappable)
            _spec_hint = cfg.get('_spec')
            if _spec_hint and _spec_hint.wrap:
                continue
            field = ordered_fields[i - 1]
            name = field['name']
            sample_count = min(len(cards), 20)
            if sample_count == 0:
                continue
            numeric_count = 0
            for card in cards[:sample_count]:
                fd = card.field_data or {}
                val = str(fd.get(name, '') or '').strip()
                if val and self._looks_numeric_or_date(val):
                    numeric_count += 1
            if numeric_count >= sample_count * 0.7:
                cfg['nowrap'] = True

        # ── Step 1: Fix image column percentages ────────────────
        IMAGE_CELL_PADDING_CM = 0.1
        image_indices = set()
        for i, cfg in enumerate(configs):
            if cfg['is_image']:
                image_indices.add(i)
                field = ordered_fields[i - 1]
                render_w = field.get('image_width_cm', 1.9)
                render_h = field.get('image_height_cm', 2.5)
                # Cap image height so 6 rows always fit on one A4 landscape page.
                if render_h > self.MAX_IMAGE_HEIGHT_CM:
                    scale = self.MAX_IMAGE_HEIGHT_CM / render_h
                    render_w = round(render_w * scale, 2)
                    render_h = self.MAX_IMAGE_HEIGHT_CM
                cfg['width'] = ((render_w + IMAGE_CELL_PADDING_CM) / self.PAGE_CONTENT_WIDTH_CM) * 100
                cfg['image_width_cm'] = render_w
                cfg['image_height_cm'] = render_h

        # ── Step 2: Remaining percentage for text columns ───────
        image_pct = sum(configs[i]['width'] for i in image_indices)
        remaining_pct = max(100.0 - image_pct, 20.0)

        # ── Step 3: Compute proportional weights (P90 + text density) ──────
        # For sparse tables we can safely allocate more width to verbose text
        # columns (address/email/name) while keeping short numeric fields tight.
        text_indices = [i for i in range(len(configs)) if i not in image_indices]
        text_weights = []
        text_score_meta = {}

        def _category_weight_boost(category: str, nowrap: bool) -> float:
            if nowrap:
                return 0.88
            boosts = {
                'address': 1.45,
                'email': 1.30,
                'full_name': 1.22,
                'parent_name': 1.16,
                'guardian_name': 1.16,
                'spouse_name': 1.16,
            }
            return boosts.get(category, 1.0)

        for i in text_indices:
            if i == 0:
                # Sr No — use spec pref_chars
                text_weights.append(max(sr_spec.pref_chars, 4))
                text_score_meta[i] = {
                    'category': 'sr_no',
                    'nowrap': True,
                    'density_score': 1.0,
                    'boost': 1.0,
                }
                continue

            field = ordered_fields[i - 1]
            name = field['name']
            spec = configs[i].get('_spec', get_column_spec(name))

            # Collect value lengths
            lengths = [len(name.upper())]
            for card in cards:
                fd = card.field_data or {}
                val = fd.get(name, '')
                raw_len = len(str(val)) if val else 0
                if raw_len > 0:
                    lengths.append(raw_len)

            # 90th percentile
            lengths.sort()
            p90_idx = max(0, int(len(lengths) * 0.9) - 1)
            representative = lengths[p90_idx] if lengths else spec.pref_chars

            # Clamp to spec's preferred range (semantic intelligence)
            representative = max(representative, spec.min_chars)
            representative = min(representative, spec.max_chars) if spec.max_chars > 0 else representative

            # ── Longest-single-word floor ─────────────────────────────────
            # Guarantee the column is at least as wide as its longest
            # unbreakable word, so text is never clipped mid-character.
            # Sample up to 100 cards; cap at spec.max_chars to prevent runaway.
            max_word_len = max((len(w) for w in name.split()), default=len(name))
            for _card in cards[:min(len(cards), 100)]:
                _fd = _card.field_data or {}
                _val = str(_fd.get(name, '') or '').strip()
                for _word in _val.split():
                    if len(_word) > max_word_len:
                        max_word_len = len(_word)
            if spec.max_chars > 0:
                max_word_len = min(max_word_len, spec.max_chars)
            representative = max(representative, max_word_len)

            # Density score: gives more weight when real values are longer than
            # the category's preferred width (safe upper bound avoids extremes).
            density_score = 1.0
            if spec.pref_chars > 0:
                density_score = max(1.0, min(representative / float(spec.pref_chars), 1.55))

            category = getattr(spec, 'category', '')
            nowrap = configs[i].get('nowrap', False)
            boost = _category_weight_boost(category, nowrap)
            final_weight = max(representative * density_score * boost, 3)

            text_weights.append(final_weight)
            text_score_meta[i] = {
                'category': category,
                'nowrap': nowrap,
                'density_score': density_score,
                'boost': boost,
            }

        total_tw = sum(text_weights) or 1

        # ── Dense-table pdf_max_pct overrides (>20 data columns) ───
        # When the table is dense, tighten wide-column caps so one column
        # cannot dominate the layout at the expense of narrow columns.
        _DENSE_PDF_MAX: dict = {
            'full_name': 10.0,
            'parent_name': 9.0,
            'guardian_name': 9.0,
            'spouse_name': 9.0,
            'reporting_manager': 7.0,
            'email': 8.0,
            'address': 6.8,
            'allergies': 6.0,
            'medical_condition': 6.0,
            'department': 7.0,
            'designation': 7.0,
            'course': 6.0,
            'branch': 6.0,
        }
        total_cols = len(configs)
        _dense_pdf = total_cols > 20  # >20 data columns
        _sparse_pdf = total_cols <= 10

        # ── Step 4: Distribute width, clamp by spec bounds ──────
        for idx, i in enumerate(text_indices):
            raw_pct = (text_weights[idx] / total_tw) * remaining_pct
            spec = configs[i].get('_spec', sr_spec if i == 0 else get_column_spec(''))
            # Effective max: tighter cap in dense-table mode; slightly wider
            # cap for verbose text in sparse tables for better readability.
            eff_max_pct = spec.pdf_max_pct
            if _dense_pdf and spec.category in _DENSE_PDF_MAX:
                eff_max_pct = min(eff_max_pct, _DENSE_PDF_MAX[spec.category])
            if _sparse_pdf and spec.category in ('address', 'email', 'full_name', 'parent_name', 'guardian_name', 'spouse_name'):
                eff_max_pct = min(max(eff_max_pct, spec.pdf_max_pct * 1.25), 28.0)
            # Clamp to semantic min/max from column_spec
            clamped = max(spec.pdf_min_pct, min(raw_pct, eff_max_pct))
            configs[i]['width'] = clamped

        # ── Step 5: Normalise so text + image = 100% ────────────
        text_actual = sum(configs[i]['width'] for i in text_indices) or 1
        for i in text_indices:
            configs[i]['width'] = round((configs[i]['width'] / text_actual) * remaining_pct, 2)

        # Clean up internal helper key
        for cfg in configs:
            cfg.pop('_spec', None)

        return configs

    def _build_rows(
        self,
        ordered_fields: List[Dict[str, Any]],
        cards: list,
        column_configs: List[Dict[str, Any]] = None,
        progress_callback=None,
        cancel_check=None,
    ) -> List[List[Dict[str, Any]] | None]:
        """
        Build row data for the template.
        Each cell: { align, is_image, content, nowrap, image_width_cm, image_height_cm }

        Image cells carry file:// URIs so WeasyPrint can resolve them directly.
        Text cells carry plain escaped text; CSS handles overflow-wrap / hyphens.
        Missing images fall back to the placeholder image.
        """
        # Build dimension maps: field_index → width/height from column_configs
        # column_configs[0] = Sr No, column_configs[1..] = fields
        image_width_map = {}
        image_height_map = {}
        if column_configs:
            for i, cfg in enumerate(column_configs):
                if cfg.get('is_image'):
                    if 'image_width_cm' in cfg:
                        image_width_map[i - 1] = cfg['image_width_cm']
                    if 'image_height_cm' in cfg:
                        image_height_map[i - 1] = cfg['image_height_cm']

        rows = []

        for sr_no, card in enumerate(cards, start=1):
            # Abort early if requested by caller.
            if callable(cancel_check) and cancel_check():
                return None
            fd = card.field_data or {}
            row_cells = []

            # Sr No cell
            row_cells.append({
                'align': 'center',
                'is_image': False,
                'nowrap': True,
                'content': str(sr_no),
            })

            for field_idx, field in enumerate(ordered_fields):
                name = field['name']
                is_image = field.get('is_image', False)
                val = fd.get(name, '')
                ftype = field.get('type', 'text')
                column_category = classify_column(name, ftype)

                spec = get_column_spec(name, ftype)
                col_cfg_idx = field_idx + 1  # +1 because configs[0] = Sr No
                is_nowrap = column_configs[col_cfg_idx].get('nowrap', False) if column_configs and col_cfg_idx < len(column_configs) else False
                if column_category == 'bus_route':
                    is_nowrap = False

                is_email_cell = (column_category == 'email')
                is_phone_cell = (column_category == 'mobile')
                cell = {
                    'align': spec.align,
                    'is_image': is_image,
                    'is_placeholder': False,
                    'image_category': column_category if is_image else '',
                    'nowrap': is_nowrap,
                    'is_phone_cell': is_phone_cell,
                    'is_email_cell': is_email_cell,
                    'content': '',
                }

                if is_image:
                    cell['image_width_cm'] = image_width_map.get(field_idx, 1.9)
                    cell['image_height_cm'] = image_height_map.get(field_idx, 2.5)

                    # Use thumbnail if available (Phase 4 optimisation)
                    img_path = ImageService.get_image_path_for_export(
                        card=card,
                        field_name=name,
                        prefer_thumbnail=True,
                        fallback_to_field_data=True
                    )
                    if img_path and is_valid_image_path(img_path):
                        abs_path = _resolve_safe_media_path(img_path)
                        if abs_path and os.path.isfile(abs_path):
                            cell['content'] = _path_to_file_uri(abs_path)
                        else:
                            if os.path.isfile(_PLACEHOLDER_IMAGE_PATH):
                                cell['content'] = _path_to_file_uri(_PLACEHOLDER_IMAGE_PATH)
                            else:
                                cell['content'] = _TRANSPARENT_PNG_DATA_URI
                            cell['is_placeholder'] = True
                    else:
                        if os.path.isfile(_PLACEHOLDER_IMAGE_PATH):
                            cell['content'] = _path_to_file_uri(_PLACEHOLDER_IMAGE_PATH)
                        else:
                            cell['content'] = _TRANSPARENT_PNG_DATA_URI
                        cell['is_placeholder'] = True
                else:
                    # WeasyPrint handles wrapping via CSS — store plain text;
                    # Django template auto-escaping handles XSS prevention.
                    cell['content'] = format_field_value(val, uppercase=True)

                row_cells.append(cell)

            rows.append(row_cells)

            if callable(progress_callback) and ((sr_no % 20 == 0) or (sr_no == len(cards))):
                try:
                    progress_callback(sr_no, len(cards))
                except Exception:
                    pass

        return rows

    @staticmethod
    def _get_card_field_value(field_data: Dict[str, Any], field_name: Optional[str]) -> str:
        """
        Read a card field value using exact key first, then normalized-key fallback.

        This guards against case/spacing variations such as "SECTION" vs "Section".
        """
        if not field_name or not isinstance(field_data, dict):
            return ''

        direct = field_data.get(field_name)
        if direct not in (None, ''):
            return str(direct).strip()

        target_key = ''.join(ch for ch in str(field_name).upper() if ch.isalnum())
        if not target_key:
            return ''

        for key, value in field_data.items():
            normalized_key = ''.join(ch for ch in str(key).upper() if ch.isalnum())
            if normalized_key == target_key and value not in (None, ''):
                return str(value).strip()

        return ''


    def _group_rows_into_pages(
        self,
        rows: List[List[Dict[str, Any]]],
        cards_list: list,
        class_field_name: Optional[str],
        section_field_name: Optional[str],
        records_per_page: int = 6,
    ) -> List[List[List[Dict[str, Any]]]]:
        """
        Group rows into pages (sublists).

        Rules:
          1. Max *records_per_page* rows per page.
          2. When CLASS or SECTION value changes -> force new page.

        Args:
            rows:             Flat list of row data (one per card)
            cards_list:       Matching list of card instances
            class_field_name: Name of the CLASS field, or None
            section_field_name: Name of the SECTION field, or None
            records_per_page: Fixed rows per page

        Returns:
            List of pages, where each page is a list of rows.
        """
        if not rows:
            return []

        pages: List[List[List[Dict[str, Any]]]] = []
        current_page: List[List[Dict[str, Any]]] = []
        prev_group_key = None

        for idx, row in enumerate(rows):
            card = cards_list[idx]
            fd = card.field_data or {}
            cur_class_val = (
                self._get_card_field_value(fd, class_field_name).upper()
                if class_field_name else None
            )
            cur_section_val = (
                self._get_card_field_value(fd, section_field_name).upper()
                if section_field_name else None
            )
            cur_group_key = (cur_class_val, cur_section_val)

            # Check if we need a new page
            need_new_page = False
            if not current_page:
                need_new_page = False  # first row always goes to first page
            elif len(current_page) >= records_per_page:
                need_new_page = True
            elif prev_group_key is not None and cur_group_key != prev_group_key:
                need_new_page = True

            if need_new_page and current_page:
                pages.append(current_page)
                current_page = []

            current_page.append(row)
            prev_group_key = cur_group_key

        # Don't forget the last page
        if current_page:
            pages.append(current_page)

        return pages

