"""
Exports App URL Configuration

Primary export endpoints. These can be included under /api/exports/
or individual endpoints can be mounted directly in core/urls.py
for backwards compatibility with existing JS code.

URL Patterns:
- POST /xlsx/<table_id>/       - Export Excel
- POST /docx/<table_id>/       - Export Word  
- POST /images/<table_id>/     - Export Images as ZIP
- GET  /preview/<table_id>/    - Get export preview/capabilities
"""
from django.urls import path

from . import views

app_name = 'exports'

urlpatterns = [
    # Excel export
    path('xlsx/<int:table_id>/', views.api_export_xlsx, name='xlsx'),
    
    # Word export (DOCX/DOC)
    path('docx/<int:table_id>/', views.api_export_docx, name='docx'),
    
    # PDF export
    path('pdf/<int:table_id>/', views.api_export_pdf, name='pdf'),
    
    # Async PDF export (background generation for large datasets)
    path('pdf-async/<int:table_id>/', views.api_export_pdf_async, name='pdf_async'),
    
    # Export task status (polling endpoint)
    path('status/<str:task_id>/', views.api_export_status, name='export_status'),
    
    # Image ZIP export
    path('images/<int:table_id>/', views.api_export_images, name='images'),
    
    # Export preview/capabilities
    path('preview/<int:table_id>/', views.api_export_preview, name='preview'),
    
    # Download All (bulk export by status)
    path('download-all/<int:table_id>/', views.api_download_all_cards, name='download_all'),
]
