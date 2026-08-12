"""
Exports App

Provides all export functionality for ID cards:
- Excel (XLSX) export
- Word (DOCX/DOC) export
- Image ZIP export

Usage:
    from exports.services import ExportService
    
    service = ExportService(request.user)
    result = service.export_excel(table_id, card_ids)
    if result.success:
        return result.response
"""

# Lazy imports to avoid circular dependencies at app loading time
# Import directly when needed:
# from exports.services import ExportService

