"""
IDCard Bulk Service — bulk status changes, bulk delete, search, class upgrade.

Part of the IDCardService split. Handles:
- bulk_change_status, bulk_delete
- search_cards
- upgrade_all_classes
"""
import logging
from typing import Dict, Any, List

from django.shortcuts import get_object_or_404

from tables.models import Table, IDCard
from .cache_version_service import CacheVersionService
from .base import BaseService, ServiceResult

logger = logging.getLogger(__name__)


class IDCardBulkService(BaseService):
    """Service for bulk ID Card operations."""

    @classmethod
    def bulk_change_status(
        cls,
        table_id: int,
        card_ids: List[int],
        new_status: str,
        user=None,
        request=None,
    ) -> ServiceResult:
        """
        Change status of multiple ID Cards — delegates to WorkflowService.bulk_transition().

        Kept as a thin wrapper so existing callers don't break.
        """
        try:
            from tables.services_workflow import WorkflowService

            table = get_object_or_404(Table, id=table_id)
            return WorkflowService.bulk_transition(
                table, card_ids, new_status,
                user=user, request=request,
                skip_permission=(user is None),
            )
        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def bulk_delete(
        cls,
        table_id: int,
        card_ids: List[int] = None,
        delete_all: bool = False
    ) -> ServiceResult:
        """Delete multiple ID Cards.

        Performance: collects all image paths with a cheap values() query,
        deletes the files outside the transaction (no row locks held during I/O),
        then performs the SQL DELETE in a single atomic statement.
        """
        try:
            table = get_object_or_404(Table, id=table_id)

            # If delete_all is requested, instead of deleting we move all cards
            # to the 'pool' status so they become available for reprint/requests.
            from django.db import transaction

            if delete_all:
                with transaction.atomic():
                    locked_qs = IDCard.objects.select_for_update().filter(table=table)
                    # Update status to 'pool' for all matching cards
                    moved_count = locked_qs.update(status='pool')

                try:
                    CacheVersionService.bump('mob_filter', int(table.id))
                    CacheVersionService.bump('class_section', int(table.group.client_id))
                    CacheVersionService.bump('global_search', 'all')
                except Exception as exc:
                    logger.debug('IDCardBulkService cache version bump failed: %s', exc)

                return ServiceResult(
                    success=True,
                    message=f'{moved_count} cards moved to pool successfully!',
                    data={'moved_count': moved_count}
                )

            # Non-delete_all path: delete selected card ids (legacy behavior)
            target_qs = IDCard.objects.filter(table=table, id__in=card_ids or [])

            # ── Step 1: harvest image paths without loading full model objects ──
            # Only select the two columns we need — avoids fetching field_data JSON
            # for every card.  Use .only() so Django defers the heavy JSONField.
            image_paths: List[str] = []
            legacy_photos: List[str] = []
            for row in target_qs.only('id', 'field_data', 'photo'):
                fd = row.field_data or {}
                for val in fd.values():
                    if val and isinstance(val, str) and val not in ('NOT_FOUND', ''):
                        if 'adarshimg/' in val or 'id_card_images/' in val:
                            image_paths.append(val)
                if row.photo:
                    legacy_photos.append(row.photo.name)

            image_paths = [p for p in set(image_paths) if p]
            legacy_photos = [p for p in set(legacy_photos) if p]

            def _delete_media_after_commit():
                from mediafiles.services import ImageService
                from django.core.files.storage import default_storage

                for path in image_paths:
                    try:
                        ImageService.delete_image(path)
                    except Exception as e:
                        logger.warning("bulk_delete: could not delete image %s: %s", path, e)

                for path in legacy_photos:
                    try:
                        if default_storage.exists(path):
                            default_storage.delete(path)
                    except Exception as e:
                        logger.warning("bulk_delete: could not delete photo %s: %s", path, e)

            # ── Step 2: SQL DELETE inside a short atomic transaction ──
            # Files are removed only after commit to avoid DB/file drift.
            with transaction.atomic():
                locked_qs = IDCard.objects.select_for_update().filter(table=table, id__in=card_ids or [])
                deleted_count = locked_qs.count()
                locked_qs.delete()
                transaction.on_commit(_delete_media_after_commit)

            if deleted_count:
                try:
                    CacheVersionService.bump('mob_filter', int(table.id))
                    CacheVersionService.bump('class_section', int(table.group.client_id))
                    CacheVersionService.bump('global_search', 'all')
                except Exception as exc:
                    logger.debug('IDCardBulkService cache version bump failed: %s', exc)

            return ServiceResult(
                success=True,
                message=f'{deleted_count} cards deleted successfully!',
                data={'deleted_count': deleted_count}
            )
        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def search_cards(cls, table_id: int, query: str) -> ServiceResult:
        """Search ID Cards across all statuses"""
        try:
            if not query or len(query) < 2:
                return ServiceResult(
                    success=True,
                    data={'results': [], 'count': 0},
                    message='Please enter at least 2 characters to search'
                )

            table = get_object_or_404(Table, id=table_id)
            query_upper = query.strip().upper()
            query_int = int(query.strip()) if query.strip().isdigit() else None

            field_type_by_name = {}
            for field in (table.fields or []):
                field_name = str((field or {}).get('name', '')).strip().upper()
                if not field_name:
                    continue
                field_type_by_name[field_name] = str((field or {}).get('type', 'text')).strip().lower()

            MAX_SEARCH_RESULTS = 200
            from .idcard_card_service import IDCardCardService
            cards = (
                IDCardCardService
                ._apply_search_filter(IDCard.objects.filter(table=table), query.strip(), table=table)
                .order_by('-id')[:MAX_SEARCH_RESULTS]
            )

            results = []
            for card in cards:
                field_data = card.field_data or {}
                match_found = False
                matched_field = ''
                matched_value = ''

                if query_int is not None and card.id == query_int:
                    match_found = True
                    matched_field = 'ID'
                    matched_value = str(card.id)

                for field_name, field_value in field_data.items():
                    if not field_value:
                        continue

                    field_name_upper = str(field_name).strip().upper()
                    field_type = field_type_by_name.get(field_name_upper, '')
                    is_image_field = field_type in cls.IMAGE_FIELD_TYPES or (not field_type and cls.is_image_field_by_name(field_name))

                    if is_image_field:
                        base_name = cls.image_path_basename(field_value)
                        if base_name and query_upper in base_name.upper():
                            match_found = True
                            matched_field = field_name
                            matched_value = base_name
                            break
                        continue

                    if query_upper in str(field_value).upper():
                        match_found = True
                        matched_field = field_name
                        matched_value = str(field_value)
                        break

                if match_found:
                    # Get display name from first text field
                    display_name = ''
                    for field in table.fields:
                        if field.get('type') in ['text', 'textarea'] and field.get('name') in field_data:
                            display_name = field_data.get(field.get('name'), '')
                            break

                    results.append({
                        'id': card.id,
                        'display_name': display_name or f'Card #{card.id}',
                        'status': card.status,
                        'status_display': card.get_status_display(),
                        'matched_field': matched_field,
                        'matched_value': matched_value,
                        'photo': (card.field_data or {}).get('PHOTO') or (card.photo.url if card.photo else None),
                        'field_data': card.field_data,
                    })

            return ServiceResult(
                success=True,
                data={
                    'results': results,
                    'count': len(results),
                    'query': query
                }
            )

        except Exception as e:
            return ServiceResult(success=False, message=str(e))

    @classmethod
    def upgrade_all_classes(cls, table_id: int) -> ServiceResult:
        """
        Upgrade the class field value for all download-status cards in a table.
        Each class value is bumped to the next level (e.g. V → VI, XII → UG).

        Uses normalize_class_value() to handle ALL input variants:
        KG-I / KGI / KG1 / kgI / LKG / kg-1 → all recognized as KG1.

        After upgrading:
        - Cards upgraded to UG are moved to 'pool' status.
        - All other upgraded cards are moved to 'pending' status.
        - Cards with unrecognized class values remain in 'download' status.

        Output format respects the school's naming convention (LKG/UKG vs KG-I/KG-II).

        Returns: ServiceResult with data={'upgraded', 'skipped', 'moved_to_pool',
                 'moved_to_pending', 'total'}
        """
        from core.utils.field_utils import (
            CLASS_UPGRADE_MAP, normalize_class_value,
            detect_kg_convention, format_class_for_output,
        )
        try:
            from django.db import transaction
            from django.db.models.fields.json import KeyTextTransform
            from django.db.models.functions import Cast
            from django.db.models import CharField, Count
            from collections import defaultdict

            table = get_object_or_404(Table, id=table_id)
            fields = table.fields or []

            # Find the class field name
            class_field_name = None
            for field in fields:
                if field.get('type') == 'class':
                    class_field_name = field.get('name')
                    break

            if not class_field_name:
                return ServiceResult(
                    success=False,
                    message='No class field found in this table configuration'
                )

            cards = IDCard.objects.filter(table=table, status='download')
            if not cards.exists():
                return ServiceResult(
                    success=False,
                    message='No cards in the Download list to upgrade'
                )

            # ── Phase 1: Pre-scan to detect KG naming convention ──
            raw_values_with_counts = (
                cards.annotate(
                    _cv=Cast(KeyTextTransform(class_field_name, 'field_data'), CharField())
                )
                .exclude(_cv__isnull=True).exclude(_cv='')
                .values('_cv')
                .annotate(cnt=Count('id'))
                .order_by()
            )
            raw_format_counts = defaultdict(lambda: defaultdict(int))
            for entry in raw_values_with_counts:
                raw = entry['_cv'].strip()
                norm = normalize_class_value(raw)
                raw_format_counts[norm][raw] += entry['cnt']

            kg_conv = detect_kg_convention(raw_format_counts)

            # ── Phase 2: Upgrade each card ──
            upgraded = 0
            skipped = 0
            ug_card_ids = []        # Cards upgraded to UG → move to pool
            pending_card_ids = []   # All other upgraded cards → move to pending
            with transaction.atomic():
                BATCH_SIZE = 500
                cards_to_update = []
                for card in cards.iterator(chunk_size=BATCH_SIZE):
                    field_data = card.field_data or {}
                    raw_val = str(field_data.get(class_field_name, '')).strip()

                    # Normalize to canonical form, then look up upgrade
                    canonical = normalize_class_value(raw_val)
                    if canonical in CLASS_UPGRADE_MAP:
                        next_canonical = CLASS_UPGRADE_MAP[canonical]
                        # Format output using the school's convention
                        new_val = format_class_for_output(next_canonical, kg_conv)
                        field_data[class_field_name] = new_val
                        card.field_data = field_data
                        cards_to_update.append(card)
                        upgraded += 1
                        # Track cards by their new class for status moves
                        if next_canonical == 'UG':
                            ug_card_ids.append(card.id)
                        else:
                            pending_card_ids.append(card.id)
                    else:
                        skipped += 1
                    # Flush batch to DB periodically to limit memory
                    if len(cards_to_update) >= BATCH_SIZE:
                        IDCard.objects.bulk_update(cards_to_update, ['field_data', 'updated_at'], batch_size=BATCH_SIZE)
                        cards_to_update = []
                if cards_to_update:
                    IDCard.objects.bulk_update(cards_to_update, ['field_data', 'updated_at'], batch_size=BATCH_SIZE)

                # Move UG students to pool
                moved_to_pool = 0
                if ug_card_ids:
                    moved_to_pool = IDCard.objects.filter(
                        id__in=ug_card_ids
                    ).update(status='pool')

                # Move all other upgraded students to pending
                moved_to_pending = 0
                if pending_card_ids:
                    moved_to_pending = IDCard.objects.filter(
                        id__in=pending_card_ids
                    ).update(status='pending')

            parts = [f'Upgraded {upgraded} card(s).']
            if moved_to_pending:
                parts.append(f'{moved_to_pending} moved to Pending.')
            if moved_to_pool:
                parts.append(f'{moved_to_pool} UG student(s) moved to Pool.')
            if skipped:
                parts.append(f'{skipped} skipped (unrecognized class value).')

            # Invalidate row scope distinct list cache upon completion of class upgrades
            from core.views.idcard_helpers import invalidate_table_distinct_cache
            invalidate_table_distinct_cache(table_id)

            return ServiceResult(
                success=True,
                message=' '.join(parts),
                data={
                    'upgraded': upgraded,
                    'skipped': skipped,
                    'moved_to_pool': moved_to_pool,
                    'moved_to_pending': moved_to_pending,
                    'total': upgraded + skipped,
                    'client_name': getattr(table.group.client, 'name', ''),
                }
            )
        except Exception as e:
            return ServiceResult(success=False, message=str(e))
