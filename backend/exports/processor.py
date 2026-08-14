"""
Export Processor

Memory-efficient export processing for ZIP, PDF, DOCX, and Excel files.

CRITICAL DESIGN RULES:
1. NEVER use BytesIO for large outputs
2. Write directly to temp file on disk
3. Use ZIP_STORED (no compression) for memory efficiency
4. Process images one at a time
5. Stream file response with cleanup callback

Usage:
    # Called from background worker
    from core.services.export_processor import process_export_zip
    process_export_zip(task)
"""
import os
import logging
import tempfile
import zipfile

from django.conf import settings
from django.utils import timezone as django_tz
from django.core.files.storage import default_storage
from django.http import StreamingHttpResponse

logger = logging.getLogger(__name__)


def _task_cancelled(task) -> bool:
    try:
        task.refresh_from_db(fields=['status'])
        return task.status == 'cancelled'
    except Exception:
        return False


def _write_response_to_path(response, destination_path: str) -> int:
    """Write an export HttpResponse/StreamingHttpResponse directly to a file path."""
    if response is None:
        return 0

    bytes_written = 0
    try:
        with open(destination_path, 'wb') as handle:
            if isinstance(response, StreamingHttpResponse):
                for chunk in response.streaming_content:
                    if isinstance(chunk, str):
                        chunk = chunk.encode('utf-8')
                    if not chunk:
                        continue
                    handle.write(chunk)
                    bytes_written += len(chunk)
            elif hasattr(response, 'content') and response.content:
                payload = response.content
                if isinstance(payload, str):
                    payload = payload.encode('utf-8')
                handle.write(payload)
                bytes_written = len(payload)
    finally:
        if hasattr(response, 'close') and callable(response.close):
            try:
                response.close()
            except Exception:
                pass

    return bytes_written


def _safe_file_size(path: str) -> int:
    """Return file size or 0 when file is missing/inaccessible."""
    try:
        return int(os.path.getsize(path))
    except (OSError, TypeError, ValueError):
        return 0


def _safe_remove(path: str, label: str) -> None:
    """Best-effort removal with logging but no hard failure."""
    try:
        os.remove(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.warning('Failed to cleanup %s %s: %s', label, path, exc)


def process_export_zip(task):
    """
    Export images from cards to a ZIP file on disk.
    
    CRITICAL:
    - ZIP is created directly on disk, not in memory
    - Uses ZIP_STORED (no compression) for memory efficiency
    - Images are added one at a time
    
    Args:
        task: BackgroundTask instance with metadata:
            - table_id: int
            - card_ids: list (optional)
            - status: str (optional)
            - image_fields: list (optional, defaults to all)
    """
    from tables.models import Table, IDCard
    from core.services.background_worker import ensure_exports_directory
    from mediafiles.services import ImageService
    from exports.utils import get_image_fields, clean_filename, is_valid_image_path, sort_cards_for_export
    
    metadata = task.metadata or {}
    table_id = metadata.get('table_id')
    
    if not table_id:
        task.mark_failed("Missing table_id in metadata")
        return
    
    try:
        table = Table.objects.select_related('group__client').get(id=table_id)
    except Table.DoesNotExist:
        task.mark_failed(f"Table {table_id} not found")
        return
    
    # Get cards
    card_ids = metadata.get('card_ids', [])
    status_filter = metadata.get('status', '')
    
    if card_ids:
        cards_qs = IDCard.objects.filter(table=table, id__in=card_ids)
    elif status_filter:
        cards_qs = IDCard.objects.filter(table=table, status=status_filter)
    else:
        cards_qs = IDCard.objects.filter(table=table)
    
    # Sort: class → section → name ascending
    cards_qs = sort_cards_for_export(cards_qs, table.fields or [])

    total_cards = cards_qs.count() if hasattr(cards_qs, 'count') else len(cards_qs)
    if total_cards == 0:
        task.mark_failed("No cards to export")
        return
    
    # Get image fields
    image_fields = get_image_fields(table.fields or [])
    if not image_fields:
        task.mark_failed("No image fields found in table")
        return

    # Materialize the queryset once so each image field does not re-run the
    # same database scan. The ZIP writer still streams one file at a time,
    # but the card list itself is now reused across fields.
    cards = list(cards_qs.iterator(chunk_size=100))
    
    task.update_progress(0, total_cards * len(image_fields))
    
    # Get client name for filename
    client_name = table.organisation.name if getattr(table, 'organisation', None) else ''
    clean_client = clean_filename(client_name) if client_name else ''
    clean_table = clean_filename(table.name)
    
    # Create exports directory
    exports_dir = ensure_exports_directory()
    
    # Create a SINGLE ZIP with subdirectories per image field
    from exports.zip import _get_readable_field_name
    
    timestamp = django_tz.localtime(django_tz.now()).strftime('%Y%m%d_%H%M%S')
    zip_filename = f"{clean_client}_{clean_table}_Images_{timestamp}.zip"
    zip_path = os.path.join(exports_dir, zip_filename)
    
    zip_files_created = []
    total_images = 0
    current_progress = 0
    
    try:
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_STORED) as zf:
            for field_info in image_fields:
                if _task_cancelled(task):
                    _safe_remove(zip_path, 'cancelled ZIP')
                    return
                field_name = field_info['name']
                folder_name = _get_readable_field_name(field_name)
                used_names = {}
                
                for card in cards:
                    if _task_cancelled(task):
                        _safe_remove(zip_path, 'cancelled ZIP')
                        return
                    img_path = ImageService.get_image_path_for_card(
                        card=card,
                        field_name=field_name,
                        fallback_to_field_data=True
                    )
                    
                    if not img_path or not is_valid_image_path(img_path):
                        current_progress += 1
                        continue
                    
                    try:
                        try:
                            real_path = default_storage.path(img_path)
                            file_size = os.path.getsize(real_path)
                        except (NotImplementedError, AttributeError, OSError):
                            real_path = None
                            file_size = 0

                        base = os.path.basename(img_path)

                        if base in used_names:
                            used_names[base] += 1
                            name, ext = os.path.splitext(base)
                            download_filename = f"{name}_{used_names[base]}{ext}"
                        else:
                            used_names[base] = 0
                            download_filename = base

                        arcname = f"{folder_name}/{download_filename}"

                        if real_path and file_size >= 100:
                            zf.write(real_path, arcname=arcname)
                            total_images += 1
                        else:
                            with default_storage.open(img_path, 'rb') as img_file:
                                img_data = img_file.read()
                            if img_data and len(img_data) >= 100:
                                zf.writestr(arcname, img_data)
                                total_images += 1
                    except FileNotFoundError:
                        continue
                    except Exception as e:
                        logger.warning("Error adding image to ZIP: %s", e)
                    
                    current_progress += 1
                    
                    if current_progress % 50 == 0:
                        task.update_progress(current_progress)
        
        task.update_progress(current_progress)
        
        if total_images == 0:
            try:
                os.remove(zip_path)
            except Exception as exc:
                logger.debug('Failed to remove empty ZIP %s: %s', zip_path, exc)
            task.mark_failed("No images found to export")
            return
        
        relative_path = os.path.relpath(zip_path, settings.MEDIA_ROOT)
        zip_files_created.append({
            'field_name': 'ALL',
            'filename': zip_filename,
            'path': relative_path,
            'image_count': total_images
        })
        
        # Store results in metadata
        task.metadata['result'] = {
            'zip_files': zip_files_created,
            'total_images': total_images,
            'total_zips': len(zip_files_created)
        }
        task.save(update_fields=['metadata'])
        
        task.mark_completed(result_path=zip_files_created[0]['path'])

        # Determine total file size on disk
        total_bytes = 0
        for zi in zip_files_created:
            full = os.path.join(settings.MEDIA_ROOT, zi['path'])
            total_bytes += _safe_file_size(full)

        logger.info(
            "EXPORT_DONE type=zip task_id=%d cards=%d images=%d zips=%d size_mb=%.2f",
            task.id, total_cards, total_images, len(zip_files_created),
            total_bytes / (1024 * 1024),
        )
        
    except Exception as e:
        # Cleanup current partial ZIP being written
        if 'zip_path' in locals():
            full_zip = os.path.join(settings.MEDIA_ROOT, zip_path)
            _safe_remove(full_zip, 'partial ZIP')
        # Cleanup any fully created ZIPs
        for zip_info in zip_files_created:
            full_path = os.path.join(settings.MEDIA_ROOT, zip_info['path'])
            _safe_remove(full_path, 'ZIP')
        
        logger.exception("ZIP export failed: %s", e)
        task.mark_failed(str(e))


def process_export_pdf(task):
    """
    Export cards to PDF file on disk.
    
    CRITICAL: PDF is generated to a temp file, not in memory.
    """
    from tables.models import Table, IDCard
    from core.services.background_worker import ensure_exports_directory
    from exports.pdf import PdfExporter
    from exports.utils import generate_export_filename, sort_cards_for_export
    
    metadata = task.metadata or {}
    table_id = metadata.get('table_id')
    
    if not table_id:
        task.mark_failed("Missing table_id in metadata")
        return
    
    try:
        table = Table.objects.select_related('group__client').get(id=table_id)
    except Table.DoesNotExist:
        task.mark_failed(f"Table {table_id} not found")
        return
    
    # Get cards
    card_ids = metadata.get('card_ids', [])
    status_filter = metadata.get('status', '')
    
    if card_ids:
        cards_qs = IDCard.objects.filter(table=table, id__in=card_ids)
    elif status_filter:
        cards_qs = IDCard.objects.filter(table=table, status=status_filter)
    else:
        cards_qs = IDCard.objects.filter(table=table)
    
    # Sort: class → section → name ascending
    cards_qs = sort_cards_for_export(cards_qs, table.fields or [])
    
    total_cards = cards_qs.count() if hasattr(cards_qs, 'count') else len(cards_qs)
    if total_cards == 0:
        task.mark_failed("No cards to export")
        return
    
    task.update_progress(0, total_cards)

    template_id = metadata.get('template_id')
    font_mode = metadata.get('font_mode', 'auto') or 'auto'
    shorten_titles = bool(metadata.get('shorten_titles', False))
    break_mode = str(metadata.get('break_mode') or 'class_section').strip().lower()
    if break_mode not in ('class_only', 'class_section'):
        break_mode = 'class_section'

    _last_pdf_progress = 0
    _pdf_emit_step = max(1, total_cards // 40)

    def _pdf_progress_callback(done, _total):
        nonlocal _last_pdf_progress
        if total_cards <= 0:
            return
        safe_done = max(0, min(int(done or 0), total_cards))
        # Keep room for render/write phase by capping row-build progress at ~70%.
        target = int((safe_done / float(total_cards)) * max(1, int(total_cards * 0.70)))
        target = max(_last_pdf_progress, min(target, total_cards))
        if target <= _last_pdf_progress:
            return
        if target < total_cards and (target - _last_pdf_progress) < _pdf_emit_step:
            return
        _last_pdf_progress = target
        task.update_progress(target, total_cards)

    try:
        # Use existing PDF exporter but save to file
        exporter = PdfExporter()
        result = exporter.export_cards(
            table, cards_qs,
            status=status_filter,
            template_id=template_id,
            font_mode=font_mode,
            shorten_titles=shorten_titles,
            break_mode=break_mode,
            progress_callback=_pdf_progress_callback,
            cancel_check=lambda: _task_cancelled(task),
        )

        if not result.success and str(result.message).strip().lower() == 'export cancelled':
            if 'pdf_path' in locals():
                _safe_remove(pdf_path, 'cancelled PDF')
            return
        
        if not result.success:
            task.mark_failed(result.message)
            return
        
        # Stream exporter response directly to disk.
        exports_dir = ensure_exports_directory()
        client_name = table.organisation.name if getattr(table, 'organisation', None) else ''
        filename = generate_export_filename(table.name, 'pdf', client_name=client_name, status=status_filter)

        pdf_path = os.path.join(exports_dir, filename)

        size_bytes = _write_response_to_path(result.response, pdf_path)
        if size_bytes <= 0:
            task.mark_failed("PDF exporter returned empty response")
            return

        pre_complete = max(_last_pdf_progress, int(total_cards * 0.92))
        if pre_complete < total_cards:
            _last_pdf_progress = pre_complete
            task.update_progress(pre_complete, total_cards)

        relative_path = os.path.relpath(pdf_path, settings.MEDIA_ROOT)

        # Store results
        task.metadata['result'] = {
            'filename': filename,
            'path': relative_path,
            'card_count': result.card_count,
            'file_size_bytes': size_bytes,
        }
        task.save(update_fields=['metadata'])
        
        task.update_progress(total_cards)
        task.mark_completed(result_path=relative_path)

        logger.info(
            "EXPORT_DONE type=pdf task_id=%d cards=%d size_mb=%.2f",
            task.id, result.card_count, size_bytes / (1024 * 1024),
        )
        
    except Exception as e:
        # Cleanup partial PDF file on failure (e.g. disk-full)
        if 'pdf_path' in locals():
            _safe_remove(pdf_path, 'partial PDF')
        logger.exception("PDF export failed: %s", e)
        task.mark_failed(str(e))


def process_export_docx(task):
    """
    Export cards to DOCX file on disk.
    """
    from tables.models import Table, IDCard
    from core.services.background_worker import ensure_exports_directory
    from exports.word import WordExporter
    from exports.utils import generate_export_filename, sort_cards_for_export
    
    metadata = task.metadata or {}
    table_id = metadata.get('table_id')
    
    if not table_id:
        task.mark_failed("Missing table_id in metadata")
        return
    
    try:
        table = Table.objects.select_related('group__client').get(id=table_id)
    except Table.DoesNotExist:
        task.mark_failed(f"Table {table_id} not found")
        return
    
    # Get cards
    card_ids = metadata.get('card_ids', [])
    status_filter = metadata.get('status', '')
    doc_format = 'docx'
    template_id = metadata.get('template_id')
    try:
        template_id = int(template_id) if template_id not in (None, '') else None
    except (TypeError, ValueError):
        template_id = None
    
    break_enabled = bool(metadata.get('break_enabled'))
    try:
        break_pages = int(metadata.get('break_pages') or 0)
    except (TypeError, ValueError):
        break_pages = 0
    
    break_mode = str(metadata.get('break_mode') or 'none').strip().lower()
    
    if card_ids:
        cards_qs = IDCard.objects.filter(table=table, id__in=card_ids)
    elif status_filter:
        cards_qs = IDCard.objects.filter(table=table, status=status_filter)
    else:
        cards_qs = IDCard.objects.filter(table=table)
    
    # Sort: class → section → name ascending
    cards_qs = sort_cards_for_export(cards_qs, table.fields or [])
    
    total_cards = cards_qs.count() if hasattr(cards_qs, 'count') else len(cards_qs)
    if total_cards == 0:
        task.mark_failed("No cards to export")
        return
    
    task.update_progress(0, total_cards)
    
    _last_docx_progress = 0
    _docx_emit_step = max(1, total_cards // 35)

    def _docx_progress_callback(done, _total):
        nonlocal _last_docx_progress
        if total_cards <= 0:
            return
        safe_done = max(0, min(int(done or 0), total_cards))
        # Row rendering dominates DOCX time, so map rows to ~88% progress.
        target = int((safe_done / float(total_cards)) * max(1, int(total_cards * 0.88)))
        target = max(_last_docx_progress, min(target, total_cards))
        if target <= _last_docx_progress:
            return
        if target < total_cards and (target - _last_docx_progress) < _docx_emit_step:
            return
        _last_docx_progress = target
        task.update_progress(target, total_cards)

    try:
        # Use existing Word exporter
        from core.services.permission_service import PermissionService
        allow_large = PermissionService.is_super_admin(getattr(task, 'user', None))
        exporter = WordExporter()
        result = exporter.export_cards(
            table,
            cards_qs,
            doc_format=doc_format,
            status=status_filter,
            template_id=template_id,
            allow_large=allow_large,
            progress_callback=_docx_progress_callback,
            cancel_check=lambda: _task_cancelled(task),
            break_enabled=break_enabled,
            break_pages=break_pages,
            break_mode=break_mode,
        )

        if not result.success and str(result.message).strip().lower() == 'export cancelled':
            if 'docx_path' in locals():
                _safe_remove(docx_path, 'cancelled DOCX')
            return
        
        if not result.success:
            task.mark_failed(result.message)
            return
        
        # Stream exporter response directly to disk.
        exports_dir = ensure_exports_directory()
        client_name = table.organisation.name if getattr(table, 'organisation', None) else ''
        is_zip = result.filename.endswith('.zip') if result.filename else False
        extension = 'zip' if is_zip else ('doc' if doc_format == 'doc' else 'docx')
        filename = generate_export_filename(table.name, extension, client_name=client_name, status=status_filter)

        docx_path = os.path.join(exports_dir, filename)

        logger.info(
            "DOCX_WRITE_START task_id=%d path=%s",
            task.id,
            docx_path,
        )
        written = _write_response_to_path(result.response, docx_path)
        logger.info(
            "DOCX_WRITE_DONE task_id=%d bytes=%d path=%s",
            task.id,
            written,
            docx_path,
        )
        if written <= 0:
            task.mark_failed("DOCX exporter returned empty response")
            return

        pre_complete = max(_last_docx_progress, int(total_cards * 0.96))
        if pre_complete < total_cards:
            _last_docx_progress = pre_complete
            task.update_progress(pre_complete, total_cards)

        relative_path = os.path.relpath(docx_path, settings.MEDIA_ROOT)
        
        # Store results
        task.metadata['result'] = {
            'filename': filename,
            'path': relative_path,
            'card_count': result.card_count
        }
        task.save(update_fields=['metadata'])
        
        task.update_progress(total_cards)
        task.mark_completed(result_path=relative_path)

        size_bytes = _safe_file_size(docx_path)
        logger.info(
            "EXPORT_DONE type=docx task_id=%d cards=%d size_mb=%.2f",
            task.id, result.card_count, size_bytes / (1024 * 1024),
        )
        
    except Exception as e:
        # Cleanup partial DOCX file on failure (e.g. disk-full)
        if 'docx_path' in locals():
            _safe_remove(docx_path, 'partial DOCX')
        logger.exception("DOCX export failed: %s", e)
        task.mark_failed(str(e))


def process_export_excel(task):
    """
    Export cards to Excel file on disk.
    """
    from tables.models import Table, IDCard
    from core.services.background_worker import ensure_exports_directory
    from exports.excel import ExcelExporter
    from exports.utils import generate_export_filename, sort_cards_for_export
    
    metadata = task.metadata or {}
    table_id = metadata.get('table_id')
    
    if not table_id:
        task.mark_failed("Missing table_id in metadata")
        return
    
    try:
        table = Table.objects.select_related('group__client').get(id=table_id)
    except Table.DoesNotExist:
        task.mark_failed(f"Table {table_id} not found")
        return
    
    # Get cards
    card_ids = metadata.get('card_ids', [])
    status_filter = metadata.get('status', '')
    
    if card_ids:
        cards_qs = IDCard.objects.filter(table=table, id__in=card_ids)
    elif status_filter:
        cards_qs = IDCard.objects.filter(table=table, status=status_filter)
    else:
        cards_qs = IDCard.objects.filter(table=table)
    
    # Sort: class → section → name ascending
    cards_qs = sort_cards_for_export(cards_qs, table.fields or [])
    
    total_cards = cards_qs.count() if hasattr(cards_qs, 'count') else len(cards_qs)
    if total_cards == 0:
        task.mark_failed("No cards to export")
        return
    
    task.update_progress(0, total_cards)
    
    _last_excel_progress = 0
    _excel_emit_step = max(1, total_cards // 40)

    def _excel_progress_callback(done, _total):
        nonlocal _last_excel_progress
        if total_cards <= 0:
            return
        safe_done = max(0, min(int(done or 0), total_cards))
        target = int((safe_done / float(total_cards)) * max(1, int(total_cards * 0.90)))
        target = max(_last_excel_progress, min(target, total_cards))
        if target <= _last_excel_progress:
            return
        if target < total_cards and (target - _last_excel_progress) < _excel_emit_step:
            return
        _last_excel_progress = target
        task.update_progress(target, total_cards)

    try:
        # Use existing Excel exporter
        exporter = ExcelExporter()
        result = exporter.export_cards(
            table,
            cards_qs,
            progress_callback=_excel_progress_callback,
            cancel_check=lambda: _task_cancelled(task),
        )

        if not result.success and str(result.message).strip().lower() == 'export cancelled':
            if 'excel_path' in locals():
                _safe_remove(excel_path, 'cancelled Excel')
            return
        
        if not result.success:
            task.mark_failed(result.message)
            return
        
        # Stream exporter response directly to disk.
        exports_dir = ensure_exports_directory()
        client_name = table.organisation.name if getattr(table, 'organisation', None) else ''
        filename = generate_export_filename(table.name, 'xlsx', client_name=client_name, status=status_filter)

        excel_path = os.path.join(exports_dir, filename)

        written = _write_response_to_path(result.response, excel_path)
        if written <= 0:
            task.mark_failed("Excel exporter returned empty response")
            return

        pre_complete = max(_last_excel_progress, int(total_cards * 0.96))
        if pre_complete < total_cards:
            _last_excel_progress = pre_complete
            task.update_progress(pre_complete, total_cards)

        relative_path = os.path.relpath(excel_path, settings.MEDIA_ROOT)
        
        # Store results (ExcelExportResult uses row_count instead of card_count)
        task.metadata['result'] = {
            'filename': filename,
            'path': relative_path,
            'card_count': result.row_count
        }
        task.save(update_fields=['metadata'])
        
        task.update_progress(total_cards)
        task.mark_completed(result_path=relative_path)

        size_bytes = _safe_file_size(excel_path)
        logger.info(
            "EXPORT_DONE type=xlsx task_id=%d rows=%d size_mb=%.2f",
            task.id, result.row_count, size_bytes / (1024 * 1024),
        )
        
    except Exception as e:
        # Cleanup partial Excel file on failure (e.g. disk-full)
        if 'excel_path' in locals():
            _safe_remove(excel_path, 'partial Excel')
        logger.exception("Excel export failed: %s", e)
        task.mark_failed(str(e))
