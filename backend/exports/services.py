"""
Export Services Module

Main orchestration layer for all export operations.
This module is READ-ONLY - it never mutates data.

Features:
- Permission checking integration
- Client scoping for admin staff
- Delegates to specialized exporters (excel, word, zip)
- Clean interface for views
"""
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from tables.models import Table, IDCard
from core.services.permission_service import PermissionService

from .excel import ExcelExporter, ExcelExportResult
from .word import WordExporter, WordExportResult
from .pdf import PdfExporter, PdfExportResult
from .zip import ZipExporter, ZipExportResult
from .utils import get_text_fields, get_image_fields


@dataclass
class ExportContext:
    """
    Context for an export operation.
    
    Contains user, table, and scoped cards based on permissions.
    cards may be a QuerySet or SortedCardList (sorted by class/section/name).
    """
    user: Any
    table: Table
    cards: Any  # QuerySet or SortedCardList
    has_permission: bool = True
    error_message: str = ''


class ExportService:
    """
    Main service for export operations.
    
    Responsibilities:
    - Permission checking
    - Client scoping
    - Delegating to specialized exporters
    
    Usage:
        service = ExportService(request.user)
        
        # Excel export
        result = service.export_excel(table_id, card_ids)
        if result.success:
            return result.response
        
        # Word export
        result = service.export_word(table_id, card_ids)
        if result.success:
            return result.response
        
        # Image ZIP export  
        result = service.export_images(table_id, card_ids)
        if result.success:
            return JsonResponse(zip_result_to_dict(result))
    """
    
    def __init__(self, user):
        self.user = user
        self._excel_exporter = ExcelExporter()
        self._word_exporter = WordExporter()
        self._pdf_exporter = PdfExporter()
        self._zip_exporter = ZipExporter()
    
    # =========================================================================
    # PERMISSION & SCOPING
    # =========================================================================
    
    def can_export(self) -> bool:
        """Check if user has permission to export (bulk download)."""
        return PermissionService.can_bulk_download(self.user)
    
    def can_view_download_list(self) -> bool:
        """Check if user can view download list."""
        return PermissionService.has(self.user, 'perm_idcard_download_list')

    @staticmethod
    def _normalize_positive_int_ids(raw_ids: Any) -> List[int]:
        """Normalize mixed payload IDs into unique positive integers."""
        if not isinstance(raw_ids, (list, tuple, set)):
            return []

        normalized: List[int] = []
        seen = set()
        for value in raw_ids:
            if isinstance(value, bool):
                continue
            try:
                parsed = int(str(value).strip())
            except (TypeError, ValueError):
                continue
            if parsed <= 0 or parsed in seen:
                continue
            seen.add(parsed)
            normalized.append(parsed)
        return normalized
    
    def get_scoped_cards(
        self,
        table: Table,
        card_ids: Optional[List[int]] = None
    ) -> QuerySet:
        """
        Get cards scoped to user's access level.
        Delegates role-based filtering to PermissionService.
        """
        # Base queryset
        if card_ids:
            normalized_ids = self._normalize_positive_int_ids(card_ids)
            if not normalized_ids:
                return IDCard.objects.none()
            cards = IDCard.objects.filter(table=table, id__in=normalized_ids)
        else:
            cards = IDCard.objects.filter(table=table)
        
        # Super admin sees all
        if PermissionService.is_super_admin(self.user):
            return cards.order_by('-id')

        table_org_id = getattr(table, 'organisation_id', None) or getattr(getattr(table, 'group', None), 'client_id', None) or getattr(table, 'client_id', None)
        if table_org_id and not PermissionService.can_access_organisation(self.user, table_org_id):
            return IDCard.objects.none()

        if PermissionService.is_assistant(self.user) or PermissionService.is_client_staff(self.user):
            from core.views.idcard_helpers import _apply_client_staff_row_scope
            cards = _apply_client_staff_row_scope(cards, self.user, table)

        return cards.order_by('-id')
    
    def _prepare_context(
        self,
        table_id: int,
        card_ids: Optional[List[int]] = None,
        require_export_permission: bool = True
    ) -> ExportContext:
        """
        Prepare export context with permissions and scoping.
        
        Args:
            table_id: ID of the table
            card_ids: Optional list of card IDs
            require_export_permission: Whether to check bulk download permission
            
        Returns:
            ExportContext with scoped cards or error
        """
        # Check permission if required
        if require_export_permission and not self.can_export():
            return ExportContext(
                user=self.user,
                table=None,
                cards=IDCard.objects.none(),
                has_permission=False,
                error_message='Permission denied: You do not have export access'
            )
        
        try:
            table = get_object_or_404(Table.objects.select_related('organisation'), id=table_id)
        except Exception:
            return ExportContext(
                user=self.user,
                table=None,
                cards=IDCard.objects.none(),
                has_permission=False,
                error_message=f'Table not found: {table_id}'
            )
        
        # Get scoped cards
        cards = self.get_scoped_cards(table, card_ids)

        if not cards.exists():
            return ExportContext(
                user=self.user,
                table=table,
                cards=cards,
                has_permission=True,
                error_message='No cards available for export'
            )
        
        return ExportContext(
            user=self.user,
            table=table,
            cards=cards,
            has_permission=True
        )
    
    # =========================================================================
    # EXCEL EXPORT
    # =========================================================================
    
    def export_excel(
        self,
        table_id: int,
        card_ids: Optional[List[int]] = None,
        status: str = ''
    ) -> ExcelExportResult:
        """
        Export cards to Excel format.
        
        Args:
            table_id: ID of the table to export
            card_ids: Optional list of specific card IDs
            status: Current status tab label
            
        Returns:
            ExcelExportResult with HttpResponse if successful
        """
        context = self._prepare_context(table_id, card_ids)
        
        if not context.has_permission or context.error_message:
            return ExcelExportResult(
                success=False,
                message=context.error_message or 'Permission denied'
            )
        
        return self._excel_exporter.export_cards(
            context.table,
            context.cards,
            status=status,
            user=self.user,
        )
    
    # =========================================================================
    # WORD EXPORT
    # =========================================================================
    
    def export_word(
        self,
        table_id: int,
        card_ids: Optional[List[int]] = None,
        doc_format: str = 'docx',
        status: str = '',
        template_id: Optional[int] = None,
        allow_large: Optional[bool] = None,
        break_enabled: bool = False,
        break_pages: int = 0,
        break_mode: str = 'class_section',
    ) -> WordExportResult:
        """
        Export cards to Word format.
        
        Args:
            table_id: ID of the table to export
            card_ids: Optional list of specific card IDs
            doc_format: 'docx' or 'doc'
            status: Current status tab label
            template_id: Optional ExportTemplate ID for footer text
            
        Returns:
            WordExportResult with HttpResponse if successful
        """
        context = self._prepare_context(table_id, card_ids)
        
        if not context.has_permission or context.error_message:
            return WordExportResult(
                success=False,
                message=context.error_message or 'Permission denied'
            )
        
        if allow_large is None:
            allow_large = PermissionService.is_super_admin(self.user)

        return self._word_exporter.export_cards(
            context.table, context.cards, doc_format=doc_format, status=status,
            template_id=template_id, allow_large=allow_large, user=self.user,
            break_enabled=break_enabled, break_pages=break_pages,
            break_mode=break_mode
        )
    
    # =========================================================================
    # PDF EXPORT
    # =========================================================================
    
    def export_pdf(
        self,
        table_id: int,
        card_ids: Optional[List[int]] = None,
        status: str = '',
        template_id: Optional[int] = None,
        font_mode: str = 'auto',
        shorten_titles: bool = False,
        break_mode: str = 'class_section',
    ) -> PdfExportResult:
        """
        Export cards to PDF format.
        
        Args:
            table_id: ID of the table to export
            card_ids: Optional list of specific card IDs
            status: Current status tab label
            template_id: Optional ExportTemplate ID for footer text
            font_mode: 'auto' | 'normal' | 'compact' | 'condensed'
            shorten_titles: Replace long column headings with short abbreviations
            break_mode: 'class_section' | 'class_only' page grouping mode
            
        Returns:
            PdfExportResult with HttpResponse if successful
        """
        context = self._prepare_context(table_id, card_ids)
        
        if not context.has_permission or context.error_message:
            return PdfExportResult(
                success=False,
                message=context.error_message or 'Permission denied'
            )
        
        return self._pdf_exporter.export_cards(
            context.table, context.cards, status=status,
            template_id=template_id, font_mode=font_mode,
            shorten_titles=shorten_titles,
            break_mode=break_mode,
            user=self.user,
        )
    
    # =========================================================================
    # IMAGE ZIP EXPORT
    # =========================================================================
    
    def export_images(
        self,
        table_id: int,
        card_ids: Optional[List[int]] = None,
        status: str = '',
        rename_options: Optional[Dict[str, Any]] = None,
        allow_large_base64: Optional[bool] = None,
    ) -> ZipExportResult:
        """
        Export images as ZIP files (one per image field).
        
        Args:
            table_id: ID of the table to export
            card_ids: Optional list of specific card IDs
            status: Current status tab label
            
        Returns:
            ZipExportResult with base64-encoded ZIP files
        """
        context = self._prepare_context(table_id, card_ids)
        
        if not context.has_permission or context.error_message:
            return ZipExportResult(
                success=False,
                message=context.error_message or 'Permission denied'
            )
        
        if allow_large_base64 is None:
            allow_large_base64 = PermissionService.is_super_admin(self.user)

        return self._zip_exporter.export_images(
            context.table,
            context.cards,
            status=status,
            rename_options=rename_options,
            allow_large_base64=allow_large_base64,
        )
    
    # =========================================================================
    # COMBINED EXPORT (for download list page)
    # =========================================================================
    
    def get_export_preview(
        self,
        table_id: int,
        card_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Get preview information for export (counts, available formats).
        
        Args:
            table_id: ID of the table
            card_ids: Optional list of specific card IDs
            
        Returns:
            Dictionary with export information
        """
        context = self._prepare_context(table_id, card_ids, require_export_permission=False)
        
        if not context.has_permission or context.error_message:
            return {
                'success': False,
                'message': context.error_message or 'Permission denied'
            }
        
        card_count = context.cards.count()
        text_fields = get_text_fields(context.table.fields or [])
        image_fields = get_image_fields(context.table.fields or [])
        
        return {
            'success': True,
            'table_name': context.table.name,
            'card_count': card_count,
            'text_field_count': len(text_fields),
            'image_field_count': len(image_fields),
            'available_formats': {
                'xlsx': len(text_fields) > 0,
                'docx': True,
                'doc': True,
                'zip': len(image_fields) > 0
            },
            'can_export': self.can_export()
        }


