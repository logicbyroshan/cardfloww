"""
Crop Service — Prepare selected card images for the Face Cropper engine
and re-upload cropped results back to the cards.

Flow:
  1. prepare_images()  — copy selected card images to a temp batch folder
  2. Engine processes the folder (via existing process-folder proxy)
  3. reupload_cropped() — read cropped images, replace in card field_data

Naming convention inside batch folder:
  {card_pk}___{field_name}.{ext}
  The triple-underscore separator is safe because neither PK nor field
  names can contain it.
"""
import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

# Separator between card PK and field name in temp filenames
_SEP = "___"

# Allowed image extensions
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}


class CropService:
    """Stateless service methods for the crop-selected-images feature."""

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _batch_dir(batch_id: str) -> Path:
        """Absolute path to a crop-batch folder.

        If a pointer file exists (written when a custom output_path was given),
        returns the custom path stored in it.  Otherwise defaults to
        MEDIA_ROOT/temp/crop_batch_{batch_id}.
        """
        ptr_file = Path(settings.MEDIA_ROOT) / "temp" / f"batch_ptr_{batch_id}.json"
        if ptr_file.is_file():
            try:
                data = json.loads(ptr_file.read_text(encoding="utf-8"))
                return Path(data["custom_path"])
            except Exception:
                pass  # fall through to default
        return Path(settings.MEDIA_ROOT) / "temp" / f"crop_batch_{batch_id}"

    @staticmethod
    def _cropped_dir(batch_dir: Path) -> Path:
        """Engine places cropped images in <folder>/cropped/ (engine v2.2.0+)."""
        return batch_dir / "cropped"

    @staticmethod
    def _failed_dir(batch_dir: Path) -> Path:
        """Engine places failed images in <folder>/failed/ (engine v2.2.0+)."""
        return batch_dir / "failed"

    @staticmethod
    def _edited_dir(batch_dir: Path) -> Path:
        """Edited images sit in <folder>/edited/ ."""
        return batch_dir / "edited"

    @staticmethod
    def _meta_file(batch_dir: Path) -> Path:
        """Metadata file for lightweight scope checks across crop endpoints."""
        return batch_dir / "_batch_meta.json"

    @classmethod
    def _read_batch_meta(cls, batch_id: str) -> dict:
        """Read batch metadata if present; return empty dict on parse/read errors."""
        batch_dir = cls._batch_dir(batch_id)
        if not batch_dir.is_dir():
            return {}
        meta_file = cls._meta_file(batch_dir)
        if not meta_file.is_file():
            return {}
        try:
            with open(meta_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @classmethod
    def get_batch_table_id(cls, batch_id: str):
        """Return table_id recorded for a batch, if available."""
        data = cls._read_batch_meta(batch_id)
        table_id = data.get("table_id")
        if table_id is None:
            return None
        try:
            return int(table_id)
        except (TypeError, ValueError):
            return None

    @classmethod
    def get_batch_client_id(cls, batch_id: str):
        """Return client_id recorded for a batch, if available."""
        data = cls._read_batch_meta(batch_id)
        client_id = data.get("client_id")
        if client_id is None:
            return None
        try:
            return int(client_id)
        except (TypeError, ValueError):
            return None

    # ── 1. Prepare images ────────────────────────────────────────────

    @classmethod
    def prepare_images(cls, table_id: int, card_ids: list, output_path: str = None) -> dict:
        """
        Copy images from selected cards into a temp batch folder.

        Returns dict:
            {
              "batch_id": "abc123",
              "batch_folder": "C:\\...\\temp\\crop_batch_abc123",
              "total_cards": 12,
              "images_copied": 10,
              "skipped": 2,
              "image_map": {
                  "45___PHOTO.jpg": {"card_id": 45, "field": "PHOTO"},
                  ...
              }
            }
        """
        from tables.models import Table, IDCard
        from mediafiles.constants import IMAGE_FIELD_TYPES

        # Validate table
        try:
            table = Table.objects.select_related("group__client").get(id=table_id)
        except Table.DoesNotExist:
            return {"success": False, "message": f"Table {table_id} not found"}

        # Get image fields from table definition
        image_fields = [
            f["name"] for f in table.fields if f.get("type") in IMAGE_FIELD_TYPES
        ]
        if not image_fields:
            return {"success": False, "message": "This table has no image fields"}

        # Get cards
        cards = IDCard.objects.filter(table_id=table_id, id__in=card_ids).only(
            "id", "field_data"
        )
        if not cards.exists():
            return {"success": False, "message": "No cards found for the given IDs"}

        # Create batch folder
        batch_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"

        if output_path and output_path.strip():
            # Use the user-specified path; write a pointer file so _batch_dir
            # can resolve it later (preview / cleanup calls only have batch_id).
            batch_dir = Path(output_path.strip())
            temp_dir = Path(settings.MEDIA_ROOT) / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            ptr_file = temp_dir / f"batch_ptr_{batch_id}.json"
            ptr_file.write_text(
                json.dumps({"custom_path": str(batch_dir), "batch_id": batch_id}),
                encoding="utf-8",
            )
        else:
            batch_dir = Path(settings.MEDIA_ROOT) / "temp" / f"crop_batch_{batch_id}"

        batch_dir.mkdir(parents=True, exist_ok=True)

        # Persist table/client context so batch-based endpoints can enforce scope.
        try:
            meta = {
                "batch_id": batch_id,
                "table_id": int(table.id),
                "client_id": int(table.group.client_id),
                "created_at": int(time.time()),
            }
            with open(cls._meta_file(batch_dir), "w", encoding="utf-8") as fh:
                json.dump(meta, fh, ensure_ascii=False)
        except Exception as exc:
            logger.warning("Failed to persist crop batch metadata for %s: %s", batch_id, exc)

        images_copied = 0
        skipped = 0
        image_map = {}
        media_root = Path(settings.MEDIA_ROOT)

        for card in cards.iterator(chunk_size=200):
            field_data = card.field_data or {}
            card_has_image = False

            for img_field in image_fields:
                value = field_data.get(img_field, "")
                if not value or not isinstance(value, str):
                    continue
                # Skip placeholders
                if value.startswith("PENDING:") or value == "NOT_FOUND":
                    continue

                # Resolve the source file
                src = media_root / value
                if not src.is_file():
                    logger.debug("Image not found on disk: %s", src)
                    continue

                # Build dest filename:  {card_pk}___{FIELD_NAME}{ext}
                ext = src.suffix.lower() or ".jpg"
                dest_name = f"{card.pk}{_SEP}{img_field}{ext}"
                dest = batch_dir / dest_name

                try:
                    shutil.copy2(str(src), str(dest))
                    images_copied += 1
                    card_has_image = True
                    image_map[dest_name] = {
                        "card_id": card.pk,
                        "field": img_field,
                        "original_path": value,
                    }
                except Exception as exc:
                    logger.warning("Failed to copy %s → %s: %s", src, dest, exc)

            if not card_has_image:
                skipped += 1

        if images_copied == 0:
            # Clean up empty folder
            shutil.rmtree(str(batch_dir), ignore_errors=True)
            return {
                "success": False,
                "message": "No images found in the selected cards",
            }

        # Persist the image_map as a JSON file inside the batch folder for
        # later use during re-upload (avoids passing large payloads around)
        map_file = batch_dir / "_image_map.json"
        with open(map_file, "w", encoding="utf-8") as f:
            json.dump(image_map, f, ensure_ascii=False)

        return {
            "success": True,
            "batch_id": batch_id,
            "batch_folder": str(batch_dir),
            "total_cards": len(card_ids),
            "images_copied": images_copied,
            "skipped": skipped,
        }

    # ── 2. List cropped / failed images ──────────────────────────────

    @classmethod
    def list_batch_images(cls, batch_id: str) -> dict:
        """
        Return lists of original, cropped, and failed images for a batch.
        """
        batch_dir = cls._batch_dir(batch_id)
        if not batch_dir.is_dir():
            return {"success": False, "message": "Batch not found"}

        def _list_images(folder: Path) -> list:
            if not folder.is_dir():
                return []
            return sorted(
                f.name
                for f in folder.iterdir()
                if f.is_file() and f.suffix.lower() in _IMG_EXTS
            )

        cropped_dir = cls._cropped_dir(batch_dir)
        failed_dir = cls._failed_dir(batch_dir)
        edited_dir = cls._edited_dir(batch_dir)

        return {
            "success": True,
            "batch_id": batch_id,
            "original": _list_images(batch_dir),
            "cropped": _list_images(cropped_dir),
            "failed": _list_images(failed_dir),
            "edited": _list_images(edited_dir),
            "batch_folder": str(batch_dir),
            "cropped_folder": str(cropped_dir),
            "failed_folder": str(failed_dir),
            "edited_folder": str(edited_dir),
        }

    # ── 3. Re-upload cropped images back to cards ────────────────────

    @classmethod
    def reupload_cropped(
        cls, 
        table_id: int, 
        batch_id: str, 
        use_edited: bool = False,
        user=None,
        request=None
    ) -> dict:
        """
        Read cropped (or edited) images from the batch folder and write
        them back to the corresponding cards, replacing the original images.

        Args:
            table_id:   The Table PK (for permission verification)
            batch_id:   The crop batch identifier
            use_edited: If True, prefer images from the /edited/ folder
            user:       The user making the request (for logging)
            request:    The HTTP request (for logging)

        Returns dict with updated_count, error_count, errors[]
        """
        import json

        from tables.models import Table, IDCard
        from mediafiles.services import ImageService

        batch_dir = cls._batch_dir(batch_id)
        if not batch_dir.is_dir():
            return {"success": False, "message": "Batch folder not found"}

        # Load image map
        map_file = batch_dir / "_image_map.json"
        if not map_file.is_file():
            return {"success": False, "message": "Image map not found in batch"}

        with open(map_file, "r") as f:
            image_map = json.load(f)

        # Validate table
        try:
            table = Table.objects.select_related("group__client").get(id=table_id)
        except Table.DoesNotExist:
            return {"success": False, "message": f"Table {table_id} not found"}

        client = table.group.client

        # Determine source folder: prefer edited > cropped > original
        cropped_dir = cls._cropped_dir(batch_dir)
        edited_dir = cls._edited_dir(batch_dir)

        # Build a lookup:  original_filename → actual_file_path
        # The engine may keep or change filenames.  For cropped, filenames
        # are preserved.  For edited, filenames get a suffix.
        # We try exact match first, then stem-based match.
        source_files = {}

        if use_edited and edited_dir.is_dir():
            for f in edited_dir.iterdir():
                if f.is_file() and f.suffix.lower() in _IMG_EXTS:
                    source_files[f.stem] = f
            # Also add cropped as fallback
            if cropped_dir.is_dir():
                for f in cropped_dir.iterdir():
                    if f.is_file() and f.suffix.lower() in _IMG_EXTS:
                        key = f.stem
                        if key not in source_files:
                            source_files[key] = f
        elif cropped_dir.is_dir():
            for f in cropped_dir.iterdir():
                if f.is_file() and f.suffix.lower() in _IMG_EXTS:
                    source_files[f.stem] = f

        if not source_files:
            return {
                "success": False,
                "message": "No cropped images found to re-upload",
            }

        updated_count = 0
        error_count = 0
        errors = []

        for orig_filename, info in image_map.items():
            card_id = info["card_id"]
            field_name = info["field"]
            original_path = info["original_path"]

            # Find the cropped file.  Try exact stem first (engine preserves
            # the input filename).
            orig_stem = Path(orig_filename).stem
            source_path = source_files.get(orig_stem)

            # Fallback: find by card_id prefix
            if source_path is None:
                prefix = f"{card_id}{_SEP}"
                for stem, fp in source_files.items():
                    if stem.startswith(prefix):
                        source_path = fp
                        break

            if source_path is None:
                # This image was not cropped (possibly failed) — skip
                continue

            # Read the cropped image bytes
            try:
                image_bytes = source_path.read_bytes()
            except Exception as exc:
                error_count += 1
                errors.append(f"Card {card_id}: cannot read {source_path.name}: {exc}")
                continue

            # Get the card
            try:
                card = IDCard.objects.get(id=card_id, table_id=table_id)
            except IDCard.DoesNotExist:
                error_count += 1
                errors.append(f"Card {card_id}: not found in table")
                continue

            # Replace image via ImageService
            result = None
            try:
                result = ImageService.replace_image(
                    image_bytes=image_bytes,
                    client=client,
                    field_name=field_name,
                    existing_path=original_path,
                    card=card,
                    batch_counter=updated_count + 1,
                    original_ext=source_path.suffix,
                    delete_old_after_save=False,
                )
                if result.success and result.data.get("final_value"):
                    saved_path = result.data["final_value"]
                    card.field_data[field_name] = saved_path
                    card.save(update_fields=["field_data", "updated_at"])

                    old_path = result.data.get('old_path_to_delete')
                    if old_path and old_path != saved_path:
                        from mediafiles.models import CardMedia
                        if not CardMedia.objects.filter(file=old_path).exists():
                            ImageService.delete_image(old_path)

                    try:
                        from core.services.activity_service import ActivityService
                        action_type = "edited" if use_edited else "cropped"
                        ActivityService.log(
                            'card_update',
                            f'Image "{field_name}" {action_type} via Face Cropper',
                            user=user,
                            request=request,
                            target_model='IDCard',
                            target_id=card_id,
                            target_name=f'Card #{card_id}',
                        )
                    except Exception as _e:
                        pass

                    updated_count += 1
                else:
                    error_count += 1
                    errors.append(
                        f"Card {card_id}: ImageService error — {result.message}"
                    )
            except Exception as exc:
                try:
                    rollback_path = result.data.get("final_value") if result is not None else None
                    if rollback_path:
                        ImageService.delete_image(rollback_path)
                except Exception:
                    pass
                error_count += 1
                errors.append(f"Card {card_id}: {exc}")
                logger.exception("Reupload cropped error for card %d", card_id)

        # Cleanup batch folder (cropped/failed/edited are subdirs inside batch_dir,
        # so rmtree on batch_dir removes everything).
        try:
            shutil.rmtree(str(batch_dir), ignore_errors=True)
        except Exception:
            pass

        return {
            "success": True,
            "updated_count": updated_count,
            "error_count": error_count,
            "errors": errors[:20],
        }

    # ── 4. Cleanup a batch (discard without re-uploading) ────────────

    @classmethod
    def cleanup_batch(cls, batch_id: str) -> dict:
        """Remove all temp files for a batch."""
        batch_dir = cls._batch_dir(batch_id)
        cropped_dir = cls._cropped_dir(batch_dir)
        failed_dir = cls._failed_dir(batch_dir)
        edited_dir = cls._edited_dir(batch_dir)

        removed = 0
        for d in (batch_dir, cropped_dir, failed_dir, edited_dir):
            if d.is_dir():
                shutil.rmtree(str(d), ignore_errors=True)
                removed += 1

        # Clean up pointer file if one was written for this batch
        ptr_file = Path(settings.MEDIA_ROOT) / "temp" / f"batch_ptr_{batch_id}.json"
        if ptr_file.is_file():
            ptr_file.unlink(missing_ok=True)

        return {"success": True, "folders_removed": removed}
