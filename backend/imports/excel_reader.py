"""
High-Performance Excel & CSV Reader with Embedded Photo Extraction

Features:
- Reads .xlsx, .xls, and .csv files with streaming row buffers.
- Embedded Cell Photo Extractor: Scans openpyxl worksheet images (ws._images),
  resolves anchor cell positions (row, col), extracts image binary bytes,
  and maps them directly to student rows without needing a separate ZIP file.
"""
import io
import os
import csv
import logging
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExtractedImage:
    """Represents an image extracted from a document cell."""
    row_idx: int          # 0-indexed data row (excluding header)
    col_idx: int          # 0-indexed column
    field_name: str       # Associated column name
    image_bytes: bytes    # Raw binary image payload
    format: str = 'jpeg'  # Image format extension


@dataclass
class ParsedSpreadsheet:
    """Result of parsing an Excel/CSV file."""
    headers: List[str]
    rows: List[List[Any]]
    embedded_images: List[ExtractedImage] = field(default_factory=list)
    total_rows: int = 0
    total_embedded_images: int = 0


def _clean_cell_value(val: Any) -> Any:
    """Clean cell string from carriage returns and Excel formatting tags."""
    if val is None:
        return ''
    if isinstance(val, str):
        return (
            val.strip()
            .replace('_x000D_', '')
            .replace('_X000D_', '')
            .replace('_x000d_', '')
            .replace('\r', '')
        )
    return str(val).strip()


def parse_excel_or_csv(file_bytes: bytes, filename: str) -> ParsedSpreadsheet:
    """
    Parse Excel (.xlsx, .xls) or CSV file and extract data rows + embedded cell photos.
    """
    fn_lower = filename.lower().strip()

    if fn_lower.endswith('.csv'):
        return _parse_csv(file_bytes)
    elif fn_lower.endswith('.xlsx'):
        return _parse_xlsx(file_bytes)
    elif fn_lower.endswith('.xls'):
        return _parse_xls(file_bytes)
    else:
        # Try XLSX first, fallback to CSV
        try:
            return _parse_xlsx(file_bytes)
        except Exception:
            return _parse_csv(file_bytes)


def _parse_csv(file_bytes: bytes) -> ParsedSpreadsheet:
    """Parse CSV text file."""
    try:
        text = file_bytes.decode('utf-8-sig', errors='replace')
    except Exception:
        text = file_bytes.decode('latin-1', errors='replace')

    reader = csv.reader(io.StringIO(text))
    headers = []
    rows = []

    for idx, row in enumerate(reader):
        clean_row = [_clean_cell_value(c) for c in row]
        if idx == 0:
            headers = [str(h).strip() for h in clean_row if str(h).strip()]
        else:
            if any(c != '' for c in clean_row):
                rows.append(clean_row)

    if not headers and rows:
        headers = [f"FIELD_{i+1}" for i in range(len(rows[0]))]

    return ParsedSpreadsheet(
        headers=headers,
        rows=rows,
        embedded_images=[],
        total_rows=len(rows),
        total_embedded_images=0,
    )


def _parse_xls(file_bytes: bytes) -> ParsedSpreadsheet:
    """Parse legacy .xls spreadsheet using xlrd."""
    try:
        import xlrd
        wb = xlrd.open_workbook(file_contents=file_bytes)
        ws = wb.sheet_by_index(0)

        headers = []
        if ws.nrows > 0:
            headers = [_clean_cell_value(ws.cell_value(0, col)) for col in range(ws.ncols)]
            headers = [h for h in headers if h]

        rows = []
        for r_idx in range(1, ws.nrows):
            row = [_clean_cell_value(ws.cell_value(r_idx, c_idx)) for c_idx in range(len(headers))]
            if any(c != '' for c in row):
                rows.append(row)

        return ParsedSpreadsheet(
            headers=headers,
            rows=rows,
            embedded_images=[],
            total_rows=len(rows),
            total_embedded_images=0,
        )
    except Exception as exc:
        logger.warning("xlrd parsing failed, fallback to CSV: %s", exc)
        return _parse_csv(file_bytes)


def _parse_xlsx(file_bytes: bytes) -> ParsedSpreadsheet:
    """
    Parse standard .xlsx file using openpyxl.
    Extracts cell text and scans ws._images for embedded photo drawings.
    """
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active

    headers = []
    rows = []

    for r_idx, row in enumerate(ws.iter_rows(values_only=True)):
        clean_row = [_clean_cell_value(c) for c in row]
        if r_idx == 0:
            headers = [str(h).strip() for h in clean_row if str(h).strip()]
        else:
            if any(c != '' for c in clean_row):
                # Ensure row matches headers length
                trimmed_row = clean_row[:len(headers)]
                while len(trimmed_row) < len(headers):
                    trimmed_row.append('')
                rows.append(trimmed_row)

    if not headers and rows:
        headers = [f"FIELD_{i+1}" for i in range(len(rows[0]))]

    # Extract embedded cell photos
    embedded_images: List[ExtractedImage] = []
    try:
        if hasattr(ws, '_images') and ws._images:
            for img in ws._images:
                try:
                    # Anchor coordinates: _from.row (0-indexed in openpyxl, row 0 is header row)
                    if hasattr(img, 'anchor') and hasattr(img.anchor, '_from'):
                        anchor_row = img.anchor._from.row  # 0 is header, 1 is first data row
                        anchor_col = img.anchor._from.col  # 0-indexed column

                        data_row_idx = anchor_row - 1  # Map to 0-indexed data rows list
                        if 0 <= data_row_idx < len(rows) and 0 <= anchor_col < len(headers):
                            # Extract image binary payload
                            img_data = img._data()
                            if img_data and len(img_data) > 100:
                                field_name = headers[anchor_col]
                                img_fmt = getattr(img, 'format', 'jpeg') or 'jpeg'

                                embedded_images.append(ExtractedImage(
                                    row_idx=data_row_idx,
                                    col_idx=anchor_col,
                                    field_name=field_name,
                                    image_bytes=img_data,
                                    format=img_fmt.lower(),
                                ))
                except Exception as img_err:
                    logger.debug("Failed extracting openpyxl cell image: %s", img_err)
    except Exception as exc:
        logger.warning("Error reading openpyxl embedded images: %s", exc)

    return ParsedSpreadsheet(
        headers=headers,
        rows=rows,
        embedded_images=embedded_images,
        total_rows=len(rows),
        total_embedded_images=len(embedded_images),
    )
