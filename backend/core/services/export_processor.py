"""
Backward-compatible shim.
Canonical location: exports/processor.py

New code should import directly from exports.processor.
"""
# -- noqa: F401 (all imports are intentionally re-exported)
from exports.processor import (
    process_export_zip,
    process_export_pdf,
    process_export_docx,
    process_export_excel,
)
