"""
Reupload Images Processor

Memory-efficient image reupload processing from ZIP files.

CRITICAL DESIGN RULES:
1. NEVER extract entire ZIP into memory
2. Process ONE image at a time
3. Update progress after each image
4. Cleanup temp files on completion/failure

Usage:
    # Called from background worker
    from core.services.reupload_processor import process_reupload_images
    process_reupload_images(task)
"""
import os
import logging
import re
import time
import zipfile
import unicodedata

from django.conf import settings

logger = logging.getLogger(__name__)

_NAME_BASE_RE = re.compile(r'^(?:[ac]\d{14}|\d{14})$')

# Keep strict stem matching as primary behavior.
# Fallback is intentionally permissive and matches any non-empty filename stem.
REUPLOAD_ALLOW_LEGACY_FALLBACK = True


def _extract_stem_exact(value):
    """Extract filename stem without fuzzy normalization."""
    raw_value = str(value or '').strip()
    if not raw_value:
        return ''
    base_name = re.split(r'[\\/]+', raw_value)[-1]
    stem, _ = os.path.splitext(base_name)
    return stem.strip()


def _normalize_reupload_path_key(value):
    """Normalize a path-like identifier for robust ZIP/PENDING matching."""
    raw_value = str(value or '').strip()
    if not raw_value:
        return ''

    if raw_value.startswith('PENDING:'):
        raw_value = raw_value[8:]

    raw_value = unicodedata.normalize('NFKC', raw_value)
    raw_value = raw_value.replace('\\', '/')
    raw_value = raw_value.split('?', 1)[0].split('#', 1)[0]
    raw_value = raw_value.strip().strip('"\'')

    parts = [segment.strip() for segment in raw_value.split('/') if segment and segment.strip() not in ('.',)]
    if not parts:
        return ''

    stem = _extract_stem_exact(parts[-1])
    if not stem:
        return ''

    parts[-1] = stem
    normalized_path = '/'.join(parts).strip('/').strip()
    return normalized_path.casefold()


def _build_reupload_path_candidates(value):
    """Build full-path and suffix path candidates for PENDING/path matching."""
    normalized_path = _normalize_reupload_path_key(value)
    if not normalized_path:
        return []

    segments = [segment for segment in normalized_path.split('/') if segment]
    if not segments:
        return []

    # Prefer longest/specific path first, then suffixes.
    candidates = []
    for idx in range(len(segments)):
        candidate = '/'.join(segments[idx:])
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _is_strict_reupload_stem(stem):
    """Strict canonical stems from system-generated image names."""
    return bool(_NAME_BASE_RE.match(stem))


def _is_fallback_reupload_stem(stem):
    """Fallback accepts any non-empty exact stem from DB/ZIP names."""
    return bool(str(stem or '').strip())


def _is_supported_reupload_stem(stem):
    """Validation used while indexing ZIP entries."""
    if _is_strict_reupload_stem(stem):
        return True
    return bool(REUPLOAD_ALLOW_LEGACY_FALLBACK and _is_fallback_reupload_stem(stem))


def _resolve_reupload_zip_entry(stem, zip_index, path_candidates=None, path_index=None):
    """Resolve match with path-aware fallback and strict-first stem behavior."""
    if path_index and path_candidates:
        for candidate in path_candidates:
            matched_entry = path_index.get(candidate)
            if matched_entry:
                return matched_entry

    if not stem:
        return None
    if _is_strict_reupload_stem(stem) and stem in zip_index:
        return zip_index.get(stem)
    if REUPLOAD_ALLOW_LEGACY_FALLBACK and _is_fallback_reupload_stem(stem):
        return zip_index.get(stem)
    return None


def _db_retry(fn, max_retries=5, base_delay=1.0):
    """
    Retry a callable that does DB writes.

    Handles:
    - SQLite  : 'database is locked' (single-writer contention)
    - PostgreSQL: stale / dropped connections
        - InterfaceError  ('connection already closed')
        - OperationalError('server closed the connection unexpectedly')
    - PostgreSQL transient write conflicts
        - deadlock detected (40P01)
        - serialization failure (40001)
        - lock not available / lock timeout (55P03)

    On a connection-level error we call close_old_connections() so Django
    opens a fresh connection on the next attempt.
    """
    from django.db.utils import OperationalError, InterfaceError
    last_err = None
    for attempt in range(max_retries):
        try:
            return fn()
        except (OperationalError, InterfaceError) as e:
            err_str = str(e).lower()
            is_lock = 'database is locked' in err_str
            pg_code = (
                getattr(e, 'pgcode', None)
                or getattr(getattr(e, '__cause__', None), 'pgcode', None)
            )
            is_pg_transient = pg_code in {'40001', '40P01', '55P03'}
            is_pg_lock_text = (
                'deadlock detected' in err_str
                or 'could not serialize access' in err_str
                or 'lock timeout' in err_str
                or 'could not obtain lock on row' in err_str
                or 'lock not available' in err_str
            )
            is_conn = (
                isinstance(e, InterfaceError)
                or 'server closed the connection' in err_str
                or 'connection already closed' in err_str
                or 'could not connect to server' in err_str
                or 'ssl connection has been closed' in err_str
            )
            if not (is_lock or is_conn or is_pg_transient or is_pg_lock_text):
                raise  # not a transient issue — propagate immediately
            last_err = e
            delay = base_delay * (2 ** attempt)  # 1, 2, 4, 8, 16 s
            logger.warning(
                "DB transient error (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1, max_retries, delay, e,
            )
            if is_conn or is_pg_transient:
                try:
                    from django.db import close_old_connections
                    close_old_connections()
                except Exception:
                    pass
            time.sleep(delay)
    # All retries exhausted
    raise last_err


def process_reupload_images(task):
    """
    Process image reupload from ZIP on disk.
    
    CRITICAL:
    - ZIP is opened from disk, not loaded into memory
    - Images are matched and processed one at a time
    - Progress is updated after each successful match
    
    Args:
        task: BackgroundTask instance with:
            - file_path: Path to saved ZIP file
            - metadata: {
                'table_id': int,
                'target_field': str (optional; when omitted, all image fields are processed),
                'card_ids': list (optional),
                'status_filter': str (optional)
            }
    """
    from tables.models import Table, IDCard
    from core.services.base import BaseService
    from mediafiles.services import ImageService
    from core.utils.field_utils import validate_image_bytes
    
    metadata = task.metadata or {}
    table_id = metadata.get('table_id')
    task_user = getattr(task, 'user', None)
    
    if not table_id:
        task.mark_failed("Missing table_id in metadata")
        return
    
    try:
        table = Table.objects.select_related('group__client').get(id=table_id)
        client = table.group.client
    except Table.DoesNotExist:
        task.mark_failed(f"Table {table_id} not found")
        return
    
    # Get full path to ZIP file
    zip_path = os.path.join(settings.MEDIA_ROOT, task.file_path) if task.file_path else None
    if not zip_path or not os.path.exists(zip_path):
        task.mark_failed(f"ZIP file not found: {task.file_path}")
        return
    
    # Get image field names
    image_field_names = BaseService.get_image_field_names(table.fields)
    if not image_field_names:
        task.mark_failed("No image fields defined in table")
        return
    
    # Target field resolution:
    # - explicit target_field (single-field mode)
    # - optional target_fields list (multi-field mode)
    # - default: process all image fields
    requested_target_fields = []

    raw_target_fields = metadata.get('target_fields')
    if isinstance(raw_target_fields, (list, tuple)):
        for candidate in raw_target_fields:
            field_name = str(candidate or '').strip()
            if field_name and field_name in image_field_names and field_name not in requested_target_fields:
                requested_target_fields.append(field_name)

    raw_target_field = str(metadata.get('target_field', '') or '').strip()
    if raw_target_field and raw_target_field in image_field_names and raw_target_field not in requested_target_fields:
        requested_target_fields.append(raw_target_field)

    target_image_fields = requested_target_fields or list(image_field_names)
    
    if not target_image_fields:
        task.mark_failed("No valid image fields to process. Check target_field configuration.")
        return
    
    # Get cards to process
    card_ids = metadata.get('card_ids', [])
    status_filter = metadata.get('status_filter', '')
    
    if card_ids:
        cards_qs = IDCard.objects.filter(table=table, id__in=card_ids).order_by('id')
    elif status_filter and status_filter in BaseService.VALID_STATUSES:
        cards_qs = IDCard.objects.filter(table=table, status=status_filter).order_by('id')
    else:
        cards_qs = IDCard.objects.filter(table=table).order_by('id')
    
    # Count total cards for progress
    total_cards = cards_qs.count()
    if total_cards == 0:
        task.mark_failed("No cards found to reupload images")
        return
    
    _db_retry(lambda: task.update_progress(0, total_cards))
    _open_zip = None  # Kept open for entire card loop; closed in finally

    try:
        # First, build index of available images in ZIP (just names, not content)
        # This is memory efficient - only stores filenames
        try:
            zip_image_index, zip_path_index, zip_stats = _build_zip_image_index(zip_path)
            zip_image_total = zip_stats.get('indexed_path_count', len(zip_image_index))
            logger.info("ZIP index built: %d images found", zip_image_total)
        except Exception as e:
            logger.exception("Failed to read ZIP for reupload task_id=%s", task.id)
            task.mark_failed("Failed to read ZIP file. Please verify the ZIP and try again.")
            return

        # If duplicates exist at the path-key level, treat this as an error
        # condition: duplicate path keys make deterministic matching impossible
        # for some images, so fail-fast and instruct the user to provide a
        # ZIP without ambiguous path entries.
        if zip_stats.get('duplicate_name_keys', 0) > 0:
            logger.warning(
                "Reupload ZIP has %d duplicate stem keys; falling back to path-aware matching where possible.",
                zip_stats.get('duplicate_name_keys', 0),
            )

        if zip_stats.get('duplicate_path_keys', 0) > 0:
            # Reject when duplicate path keys exist — safer than picking
            # a random file and silently producing wrong images.
            logger.error(
                "Reupload ZIP has %d duplicate path keys; aborting reupload.",
                zip_stats.get('duplicate_path_keys', 0),
            )
            task.mark_failed(
                "Reupload ZIP contains multiple files with the same normalized path; please deduplicate the ZIP and try again."
            )
            return

        preflight = _run_reupload_preflight(
            cards_qs=cards_qs,
            image_field_names=target_image_fields,
            zip_image_index=zip_image_index,
            zip_path_index=zip_path_index,
        )

        metadata['preflight'] = preflight
        task.metadata = metadata
        _db_retry(lambda: task.save(update_fields=['metadata']))

        if not zip_image_index and not zip_path_index:
            task.mark_failed("No valid images found in ZIP file")
            return

        # Open the ZIP once for the entire card loop.
        # Avoids reopening (and re-reading the central directory) for every
        # single image — was N open/close calls, now exactly 1.
        _open_zip = zipfile.ZipFile(zip_path, 'r')
        zip_name_set = set(_open_zip.namelist())

        # Process cards one at a time
        updated_count = 0
        matched_count = 0
        unchanged_count = 0
        errors = []
        batch_counter = 0
        pending_updates = []  # Accumulated cards for bulk_update; flushed every FLUSH_EVERY
        pending_media_deletes = []  # (card_pk, field_name) tuples for batch CardMedia cleanup
        pending_media_creates = []  # kwargs dicts for batch CardMedia creation
        FLUSH_EVERY = 100  # larger batches → fewer DB writes → less lock contention

        for idx, card in enumerate(cards_qs.iterator(chunk_size=200)):
            try:
                field_data = card.field_data or {}
                card_updated = False
                
                for img_field in target_image_fields:
                    current_value = field_data.get(img_field) or ''
                    
                    # ── Determine what to match against ──────────────────
                    # Reupload matching uses the CURRENT DB filename stem
                    # (or PENDING reference), not __ref metadata.
                    match_key = None
                    existing_path = None
                    
                    if current_value.startswith('PENDING:'):
                        # Strategy 1: PENDING:reference  (always works)
                        match_key = _extract_stem_exact(current_value[8:])
                    elif current_value and current_value not in ('NOT_FOUND', ''):
                        # Has existing saved image
                        existing_path = current_value
                        # Strategy 2: current saved filename stem
                        # (ensures DB name is the matching source of truth).
                        match_key = _extract_stem_exact(current_value)
                    else:
                        continue
                    
                    if not match_key:
                        continue

                    path_candidates = _build_reupload_path_candidates(current_value)

                    zip_entry = _resolve_reupload_zip_entry(
                        match_key,
                        zip_image_index,
                        path_candidates=path_candidates,
                        path_index=zip_path_index,
                    )
                    if not zip_entry:
                        continue
                    matched_count += 1
                    
                    try:
                        batch_counter += 1
                        
                        # Extract image using the already-open ZIP handle
                        image_bytes = _extract_single_image(_open_zip, zip_entry['zip_path'])
                        if not image_bytes:
                            errors.append(f"Card {card.pk}: Failed to extract image")
                            continue
                        
                        # Validate image
                        is_valid, error_msg = validate_image_bytes(image_bytes)
                        if not is_valid:
                            errors.append(f"Card {card.pk}: Invalid image - {error_msg}")
                            continue
                        
                        # Save image FILE to disk (no DB writes yet)
                        # Pass card=None so replace_image/save_new_image
                        # skip the per-card CardMedia atomic() block.
                        if existing_path:
                            result = ImageService.replace_image(
                                image_bytes=image_bytes,
                                client=client,
                                field_name=img_field,
                                existing_path=existing_path,
                                card=None,  # defer CardMedia to batch
                                batch_counter=batch_counter,
                                original_ext=zip_entry['ext'],
                                delete_old_after_save=True,
                                uploaded_by=task_user,
                            )
                        else:
                            result = ImageService.save_new_image(
                                image_bytes=image_bytes,
                                client=client,
                                field_name=img_field,
                                card=None,  # defer CardMedia to batch
                                batch_counter=batch_counter,
                                original_ext=zip_entry['ext'],
                                uploaded_by=task_user,
                            )
                        
                        if result.success and result.data.get('final_value'):
                            saved_path = result.data['final_value']

                            field_data[img_field] = saved_path
                            card_updated = True
                            # Queue CardMedia ops for batch flush
                            if existing_path:
                                pending_media_deletes.append((card.pk, img_field))
                            pending_media_creates.append({
                                'card': card,
                                'client': Organisation,
                                'saved_path': saved_path,
                                'field_name': img_field,
                            })
                            logger.debug("Reupload: Card %s field %s updated", card.pk, img_field)
                        else:
                            errors.append(f"Card {card.pk}: Failed to save - {result.message}")
                            
                    except Exception as save_err:
                        errors.append(f"Card {card.pk}: Error - {str(save_err)}")
                
                # Queue card for bulk update instead of saving individually
                if card_updated:
                    card.field_data = field_data
                    pending_updates.append(card)
                    updated_count += 1
                
            except Exception as card_err:
                errors.append(f"Card {card.pk}: {str(card_err)}")
                logger.error("Error processing card %d: %s", card.pk, card_err)
            
            # Flush bulk updates + CardMedia + progress every FLUSH_EVERY cards
            # Flush when modulo matches OR when we've reached the last known
            # card index. Using both checks prevents losing the final batch
            # if the queryset iterator yields fewer rows than the original
            # `total_cards` count due to concurrent deletes.
            if (idx + 1) % FLUSH_EVERY == 0 or idx == total_cards - 1:
                _flush_batch(
                    pending_updates, pending_media_deletes,
                    pending_media_creates,
                    IDCard, ImageService, client,
                )
                pending_updates = []
                pending_media_deletes = []
                pending_media_creates = []
                _db_retry(lambda _idx=idx: task.update_progress(_idx + 1))

        # Safety flush: if the iterator returned fewer rows than total_cards
        # (e.g. cards deleted mid-iteration), the in-loop condition
        # `idx == total_cards - 1` never fires and the last batch is lost.
        if pending_updates or pending_media_creates:
            _flush_batch(
                pending_updates, pending_media_deletes,
                pending_media_creates,
                IDCard, ImageService, client,
            )
            pending_updates = []
            pending_media_deletes = []
            pending_media_creates = []

        # Build result
        result_msg = f"Updated {updated_count} cards with {matched_count} images matched"
        if zip_stats.get('duplicate_name_keys', 0) > 0 or zip_stats.get('duplicate_path_keys', 0) > 0:
            result_msg += f" (skipped {zip_stats.get('duplicate_name_keys', 0) + zip_stats.get('duplicate_path_keys', 0)} duplicates)"

        # Store results in metadata (with retry)
        task.metadata['result'] = {
            'updated_count': updated_count,
            'matched_count': matched_count,
            'unchanged_count': unchanged_count,
            'zip_images_count': zip_image_total,
            'duplicates_skipped_stems': zip_stats.get('duplicate_name_keys', 0),
            'duplicates_skipped_paths': zip_stats.get('duplicate_path_keys', 0),
            'preflight': preflight,
            'error_count': len(errors),
            'errors': errors[:10] if errors else []
        }
        _db_retry(lambda: task.save(update_fields=['metadata']))

        # Mark completed (with retry)
        _db_retry(lambda: task.mark_completed())
        logger.info(
            "REUPLOAD_DONE task_id=%d matched=%d updated=%d unchanged=%d zip_images=%d errors=%d",
            task.id, matched_count, updated_count, unchanged_count, zip_image_total, len(errors),
        )

    except Exception as e:
        logger.exception("Reupload processing failed: %s", e)
        try:
            _db_retry(lambda: task.mark_failed("Reupload processing failed due to an internal error."))
        except Exception:
            logger.error("Could not mark task %d as failed (DB still locked)", task.id)
    finally:
        if _open_zip is not None:
            try:
                _open_zip.close()
            except Exception:
                pass
        # Cleanup
        _cleanup_task_files(task)


def _flush_batch(
    pending_updates,
    pending_media_deletes,
    pending_media_creates,
    IDCard,
    ImageService,
    client,
):
    """
    Flush accumulated DB writes in a single retried transaction.

    Groups IDCard bulk_update + CardMedia delete/create into one write.
    """
    if not pending_updates and not pending_media_creates:
        return

    def _do_flush():
        from django.db import transaction
        from django.utils import timezone as _tz
        from mediafiles.models import CardMedia

        with transaction.atomic():
            # 1. Bulk-update IDCard field_data FIRST (safest operation)
            if pending_updates:
                _now = _tz.now()
                for _c in pending_updates:
                    _c.updated_at = _now
                IDCard.objects.bulk_update(
                    pending_updates, ['field_data', 'updated_at'], batch_size=100
                )

            # 2. Delete old CardMedia first, then create NEW CardMedia.
            # This ordering ensures we do not temporarily exceed storage
            # quotas or duplicate logical ownership rows when DB-level
            # uniqueness constraints exist on (card, field_name, file).
            if pending_media_deletes:
                from django.db.models import Q
                q = Q()
                for card_pk, field_name in pending_media_deletes:
                    q |= Q(card_id=card_pk, field_name=field_name)
                deleted_count, _ = CardMedia.objects.filter(q).delete()
                if deleted_count != len(pending_media_deletes):
                    logger.warning(
                        "CardMedia delete count mismatch: expected %d, deleted %d. Possible orphaned records.",
                        len(pending_media_deletes), deleted_count
                    )

            # 3. Create new CardMedia records after old ones removed
            if pending_media_creates:
                objs = []
                for item in pending_media_creates:
                    objs.append(CardMedia(
                        card=item['card'],
                        client=item['client'],
                        file=item['saved_path'],
                        media_type='photo',
                        field_name=item['field_name'],
                    ))
                CardMedia.objects.bulk_create(objs, batch_size=100)

    try:
        _db_retry(_do_flush)
    except Exception:
        # DB failed: rollback saved files from this batch so paths don't drift.
        rollback_paths = {
            item.get('saved_path')
            for item in pending_media_creates
            if item.get('saved_path')
        }
        for saved_path in rollback_paths:
            try:
                ImageService.delete_image(saved_path)
            except Exception as cleanup_err:
                logger.warning(
                    "Reupload rollback cleanup failed for new file %s: %s",
                    saved_path,
                    cleanup_err,
                )
        raise

def _build_zip_image_index(zip_path):
    """
    Build an index of images in a ZIP file.
    
        CRITICAL: Only stores filenames and metadata, not image content.

        Returns:
                tuple:
                    - dict: {normalized_key: {'zip_path': str, 'ext': str, 'original_name': str}}
                    - dict: empty placeholder for backward compatibility
                    - dict: zip_stats
    """
    index = {}
    path_index = {}
    path_suffix_index = {}
    duplicate_name_keys = 0
    duplicate_path_keys = 0
    duplicate_path_suffix_keys = 0
    duplicate_stems = set()
    duplicate_paths = set()
    duplicate_suffixes = set()
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for zip_info in zf.infolist():
            if zip_info.is_dir():
                continue
            
            # Skip very large files
            if zip_info.file_size > 20 * 1024 * 1024:  # 20MB
                continue
            
            base_name = os.path.basename(zip_info.filename)
            name_without_ext = os.path.splitext(base_name)[0]
            ext = os.path.splitext(base_name)[1].lower()
            
            if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                continue
            
            exact_key = _extract_stem_exact(name_without_ext)
            normalized_path_key = _normalize_reupload_path_key(zip_info.filename)

            if not exact_key or not _is_supported_reupload_stem(exact_key):
                continue

            if not normalized_path_key:
                continue

            existing = index.get(exact_key)
            if existing is None:
                index[exact_key] = {
                    'zip_path': zip_info.filename,
                    'ext': ext,
                    'original_name': base_name
                }
            else:
                duplicate_name_keys += 1
                duplicate_stems.add(exact_key)

            entry = {
                'zip_path': zip_info.filename,
                'ext': ext,
                'original_name': base_name
            }

            existing_path = path_index.get(normalized_path_key)
            if existing_path is None:
                path_index[normalized_path_key] = entry
            else:
                duplicate_path_keys += 1
                duplicate_paths.add(normalized_path_key)

            path_segments = [segment for segment in normalized_path_key.split('/') if segment]
            for idx in range(len(path_segments)):
                suffix_key = '/'.join(path_segments[idx:])
                existing_suffix = path_suffix_index.get(suffix_key)
                if existing_suffix is None:
                    path_suffix_index[suffix_key] = entry
                elif existing_suffix.get('zip_path') != entry.get('zip_path'):
                    duplicate_path_suffix_keys += 1
                    duplicate_suffixes.add(suffix_key)

    for key in duplicate_stems:
        index.pop(key, None)

    for key in duplicate_paths:
        path_index.pop(key, None)

    for key in duplicate_suffixes:
        path_suffix_index.pop(key, None)

    path_lookup_index = dict(path_index)
    for suffix_key, entry in path_suffix_index.items():
        if suffix_key not in path_lookup_index:
            path_lookup_index[suffix_key] = entry

    zip_stats = {
        'duplicate_name_keys': duplicate_name_keys,
        'duplicate_path_keys': duplicate_path_keys,
        'duplicate_path_suffix_keys': duplicate_path_suffix_keys,
        'indexed_stem_count': len(index),
        'indexed_path_count': len(path_index),
    }

    return index, path_lookup_index, zip_stats


def _run_reupload_preflight(
    cards_qs,
    image_field_names,
    zip_image_index,
    zip_path_index=None,
):
    """Compute match diagnostics before any writes occur."""
    expected_targets = 0
    matched_targets = 0
    missing_targets = 0
    missing_samples = []

    for card in cards_qs.iterator(chunk_size=500):
        field_data = card.field_data or {}
        for img_field in image_field_names:
            current_value = field_data.get(img_field) or ''
            match_key = None

            if current_value.startswith('PENDING:'):
                match_key = _extract_stem_exact(current_value[8:])
            elif current_value and current_value not in ('NOT_FOUND', ''):
                match_key = _extract_stem_exact(current_value)
            else:
                continue

            expected_targets += 1
            path_candidates = _build_reupload_path_candidates(current_value)
            has_fallback_hit = bool(
                _resolve_reupload_zip_entry(
                    match_key,
                    zip_image_index,
                    path_candidates=path_candidates,
                    path_index=zip_path_index,
                )
            )

            if has_fallback_hit:
                matched_targets += 1
            else:
                missing_targets += 1
                if len(missing_samples) < 20:
                    missing_samples.append({'card_id': card.pk, 'field_name': img_field})

    return {
        'expected_targets': expected_targets,
        'matched_targets': matched_targets,
        'missing_targets': missing_targets,
        'ambiguous_matches': 0,
        'missing_samples': missing_samples,
    }


def _extract_single_image(zf_or_path, internal_path):
    """
    Extract a single image from a ZIP file.

    Accepts an already-open ZipFile object (fast path — zero open/close overhead)
    or a path string (fallback that opens and closes the ZIP itself).

    Returns:
        bytes: Image content, or None if extraction failed
    """
    try:
        if isinstance(zf_or_path, zipfile.ZipFile):
            return zf_or_path.read(internal_path)
        with zipfile.ZipFile(zf_or_path, 'r') as zf:
            return zf.read(internal_path)
    except Exception as e:
        logger.error("Failed to extract %s: %s", internal_path, e)
        return None


def _cleanup_task_files(task):
    """Clean up temporary files."""
    from core.services.background_worker import cleanup_temp_file
    
    if task.file_path:
        cleanup_temp_file(task.file_path)
