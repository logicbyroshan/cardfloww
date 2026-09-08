"""
Imports API Views Module

Endpoints:
- POST /api/group/<id>/table/create-with-data/  (also alias: create-from-xlsx)
- POST /api/table/<id>/cards/bulk-upload/
- POST /api/table/<id>/cards/reupload-images/
- POST /api/imports/preview/
"""
import json
import logging
from typing import Dict, Any, List

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt

from organisation.models import Organisation
from tables.models import Table
from core.services.permission_service import PermissionService, api_require_any_authenticated, api_require_permission
from core.views.idcard_helpers import _check_client_scope_by_group, _check_client_scope_by_table
from .services import ImportService

logger = logging.getLogger(__name__)


@require_POST
@api_require_any_authenticated
def api_preview_import_data(request) -> JsonResponse:
    """
    POST /api/imports/preview/
    Accepts XLSX, XLS, CSV, or DOCX and returns headers, sample rows, detected schema,
    and count of embedded cell photos.
    """
    if 'file' not in request.FILES:
        return JsonResponse({'success': False, 'message': 'No file uploaded.'}, status=400)

    uploaded_file = request.FILES['file']
    filename = uploaded_file.name
    try:
        file_bytes = uploaded_file.read()
        preview = ImportService.preview_data(file_bytes, filename)
        return JsonResponse(preview)
    except Exception as exc:
        logger.error("Import preview failed: %s", exc)
        return JsonResponse({'success': False, 'message': str(exc)}, status=400)


@require_POST
@api_require_any_authenticated
def api_create_table_with_data(request, group_id: int) -> JsonResponse:
    """
    POST /api/group/<group_id>/table/create-with-data/
    POST /api/group/<group_id>/table/create-from-xlsx/  (legacy alias)
    """
    # Resolve target organisation (group_id can be Org ID or Table ID)
    org = Organisation.objects.filter(id=group_id).first()
    if not org:
        table_ref = Table.objects.filter(id=group_id).first()
        if table_ref:
            org = table_ref.organisation
        else:
            org = Organisation.objects.first()

    if not org:
        return JsonResponse({'success': False, 'message': 'Organisation not found.'}, status=404)

    # Scoping check: user must have access to this organisation
    if not PermissionService.can_access_organisation(request.user, org.id):
        return JsonResponse({
            'success': False,
            'message': 'Access denied. You do not have access to this organisation.'
        }, status=403)

    # Authorization check: only Super Admin, Prime Admin, and Prime Manager can create tables
    # Super Managers, Assistants, and Operators cannot create tables (403 Forbidden).
    if not PermissionService.can_create_table(request.user, org):
        return JsonResponse({
            'success': False,
            'message': 'Permission denied: Super Managers cannot create tables. Only Prime Managers and Admins can create tables.'
        }, status=403)

    if 'file' not in request.FILES:
        return JsonResponse({'success': False, 'message': 'No file uploaded.'}, status=400)

    uploaded_file = request.FILES['file']
    filename = uploaded_file.name
    table_name = request.POST.get('table_name', '')

    # Custom fields if user tweaked schema in wizard
    custom_fields = None
    custom_fields_raw = request.POST.get('fields') or request.POST.get('custom_fields')
    if custom_fields_raw:
        try:
            custom_fields = json.loads(custom_fields_raw)
        except Exception:
            pass

    # Collect any attached ZIP files
    zip_files = []
    if 'photos_zip' in request.FILES:
        zip_files.append(request.FILES['photos_zip'])
    if 'zip_file' in request.FILES:
        zip_files.append(request.FILES['zip_file'])
    for key, f in request.FILES.items():
        if key.startswith(('photos_zip_', 'unified_zip_')):
            zip_files.append(f)

    try:
        file_bytes = uploaded_file.read()
        result = ImportService.create_table_with_data(
            group_id=org.id,
            file_bytes=file_bytes,
            filename=filename,
            table_name=table_name,
            custom_fields=custom_fields,
            zip_files=zip_files,
            user=request.user,
        )
        if result.success:
            return JsonResponse({
                'success': True,
                'message': result.message,
                'table_id': result.table_id,
                'table_name': result.table_name,
                'cards_created': result.cards_created,
                'photos_imported': result.photos_imported,
                'embedded_photos_count': result.embedded_photos_count,
            })
        else:
            return JsonResponse({'success': False, 'message': result.message}, status=400)
    except Exception as exc:
        logger.exception("Create Table with Data failed: %s", exc)
        return JsonResponse({'success': False, 'message': f'Failed to create table: {exc}'}, status=500)


@require_POST
@api_require_any_authenticated
def api_bulk_upload_data(request, table_id: int) -> JsonResponse:
    """
    POST /api/table/<table_id>/cards/bulk-upload/
    """
    _tbl, err = _check_client_scope_by_table(request.user, table_id)
    if err:
        return err

    if 'file' not in request.FILES:
        return JsonResponse({'success': False, 'message': 'No spreadsheet or Word document uploaded.'}, status=400)

    uploaded_file = request.FILES['file']
    filename = uploaded_file.name

    field_mapping = {}
    field_mapping_raw = request.POST.get('field_mapping')
    if field_mapping_raw:
        try:
            field_mapping = json.loads(field_mapping_raw)
        except Exception:
            pass

    # Collect any attached ZIP files
    zip_files = []
    if 'photos_zip' in request.FILES:
        zip_files.append(request.FILES['photos_zip'])
    if 'zip_file' in request.FILES:
        zip_files.append(request.FILES['zip_file'])
    for key, f in request.FILES.items():
        if key.startswith(('photos_zip_', 'unified_zip_')):
            zip_files.append(f)

    try:
        file_bytes = uploaded_file.read()
        result = ImportService.upload_data_to_existing_table(
            table_id=table_id,
            file_bytes=file_bytes,
            filename=filename,
            field_mapping=field_mapping,
            zip_files=zip_files,
            user=request.user,
        )
        if result.success:
            return JsonResponse({
                'success': True,
                'message': result.message,
                'cards_created': result.cards_created,
                'photos_imported': result.photos_imported,
                'embedded_photos_count': result.embedded_photos_count,
            })
        else:
            return JsonResponse({'success': False, 'message': result.message}, status=400)
    except Exception as exc:
        logger.exception("Bulk upload failed: %s", exc)
        return JsonResponse({'success': False, 'message': f'Failed to import data: {exc}'}, status=500)


@require_POST
@api_require_any_authenticated
def api_reupload_images(request, table_id: int) -> JsonResponse:
    """
    POST /api/table/<table_id>/cards/reupload-images/
    """
    _tbl, err = _check_client_scope_by_table(request.user, table_id)
    if err:
        return err

    zip_file = request.FILES.get('photos_zip') or request.FILES.get('zip_file') or request.FILES.get('file')
    if not zip_file:
        return JsonResponse({'success': False, 'message': 'No ZIP file uploaded.'}, status=400)

    target_field = request.POST.get('target_field', '')
    status = request.POST.get('status', '')

    try:
        result = ImportService.reupload_images(
            table_id=table_id,
            zip_file_obj=zip_file,
            target_field=target_field,
            status=status,
            user=request.user,
        )
        if result.errors:
            return JsonResponse({'success': False, 'message': '; '.join(result.errors)}, status=400)

        return JsonResponse({
            'success': True,
            'message': f"Matched {result.matched_cards} cards and updated {result.updated_photos} photos.",
            'matched_cards': result.matched_cards,
            'updated_photos': result.updated_photos,
            'unmatched_files_count': len(result.unmatched_files),
        })
    except Exception as exc:
        logger.exception("Reupload images failed: %s", exc)
        return JsonResponse({'success': False, 'message': f'Failed to reupload photos: {exc}'}, status=500)
