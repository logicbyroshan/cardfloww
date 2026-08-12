"""
Image Records — single-authority entry points + CardMedia integration.

Provides: ImageRecordsMixin (save_new_image, replace_image, mark_pending,
remove_image, create_media_record, save_image_with_media_record).

Part of the ImageService mixin split.
"""
import os
import logging
from typing import Optional

from django.core.files.base import ContentFile

from .image_rename import ImageRenamer
from .image_core import MediaResult

logger = logging.getLogger(__name__)


class ImageRecordsMixin:
    """
    Single-authority image mutation entry points and CardMedia record management.
    """

    # ==================== SINGLE-AUTHORITY ENTRY POINTS ====================
    # All image mutations MUST go through one of these four methods.
    # They guarantee: save + thumbnail + CardMedia + return final_value.
    # Callers store the returned data['final_value'] in field_data — nothing else.

    @staticmethod
    def _resolve_uploader_prefix(uploaded_by=None) -> str:
        """Map uploader role to filename prefix: admin='a', client='c', operator='o'."""
        role = str(getattr(uploaded_by, 'role', '') or '').strip().lower()
        if role in ('assistant'):
            return 'c'
        if role in ('operator', 'operator_staff', 'photographer'):
            return 'o'
        return 'a'

    @classmethod
    def save_new_image(
        cls,
        image_bytes: bytes,
        client,
        field_name: str,
        card=None,
        batch_counter: int = 1,
        original_ext: str = '.jpg',
        original_filename: str = None,
        uploaded_by=None,
    ) -> 'MediaResult':
        """
        Single entry point for saving a NEW image (no existing path).
        """
        uploader_prefix = cls._resolve_uploader_prefix(uploaded_by)
        result = cls.save_image_with_thumbnail(
            image_bytes=image_bytes,
            client=client,
            existing_path=None,
            batch_counter=batch_counter,
            original_ext=original_ext,
            uploader_prefix=uploader_prefix,
        )
        if not result.success:
            return result

        saved_path = result.data.get('path', '')

        if card and saved_path:
            try:
                parsed = ImageRenamer.parse_filename(saved_path)
                root_token = parsed['root_token'] if parsed else None
                version = parsed['edit_count'] if parsed else 0

                cls.create_media_record(
                    saved_path=saved_path,
                    client=client,
                    card=card,
                    field_name=field_name,
                    media_type='photo',
                    original_filename=original_filename,
                    uploaded_by=uploaded_by,
                    root_token=root_token,
                    version=version,
                    last_edited_by_role=uploader_prefix,
                    status='active',
                )
            except Exception as cm_err:
                logger.warning("CardMedia create failed in save_new_image for %s: %s", field_name, cm_err)

        result.data['final_value'] = saved_path
        result.data['action'] = 'upload'
        return result

    @classmethod
    def check_old_version_warning(cls, card, field_name: str, incoming_filename_or_path: str, confirm_overwrite: bool = False) -> Optional[dict]:
        """
        Check if incoming image is an older version than current active image.
        Returns warning dict if incoming_version < current_active_version and not confirmed.
        """
        if confirm_overwrite or not card or not field_name:
            return None
        
        parsed = ImageRenamer.parse_filename(incoming_filename_or_path)
        if not parsed:
            return None
        
        from ..models import CardMedia
        active_record = CardMedia.objects.filter(
            card=card,
            field_name=field_name,
            status='active'
        ).order_by('-created_at').first()
        
        if not active_record:
            return None
        
        active_parsed = ImageRenamer.parse_filename(active_record.file.name)
        current_version = active_record.version or (active_parsed['edit_count'] if active_parsed else 0)
        incoming_version = parsed['edit_count']
        
        if incoming_version < current_version:
            return {
                'success': False,
                'warning_code': 'OLD_VERSION_DETECTED',
                'message': f'The uploaded image is version {incoming_version}, but current active image is version {current_version}.',
                'data': {
                    'incoming_version': incoming_version,
                    'current_version': current_version,
                    'root_token': parsed['root_token'],
                    'require_confirmation': True
                }
            }
        return None

    @classmethod
    def update_history_stack_on_save(cls, card, field_name: str, new_media_record):
        """
        Maintain 5-slot window: 1 Active + Max 2 Undo + Max 2 Redo.
        
        Transitions on new edit/save:
        - Move previous active record to undo_stack
        - Purge any redo_stack records
        - Prune undo_stack to max 2 items (purging storage files for expired items)
        """
        if not card or not field_name or not new_media_record:
            return
        
        from ..models import CardMedia
        from django.core.files.storage import default_storage
        
        # 1. Move previous active records to undo_stack
        CardMedia.objects.filter(
            card=card,
            field_name=field_name,
            status='active'
        ).exclude(pk=new_media_record.pk).update(status='undo_stack')
        
        # 2. Clear redo stack (purge files + set status expired)
        redo_records = CardMedia.objects.filter(
            card=card,
            field_name=field_name,
            status='redo_stack'
        )
        for rec in redo_records:
            if rec.file and default_storage.exists(rec.file.name):
                try:
                    default_storage.delete(rec.file.name)
                except Exception as del_err:
                    logger.warning("Failed to delete redo stack file %s: %s", rec.file.name, del_err)
            rec.status = 'expired'
            rec.save(update_fields=['status'])
        
        # 3. Prune undo stack to max 2 items (keep 2 newest)
        undo_qs = CardMedia.objects.filter(
            card=card,
            field_name=field_name,
            status='undo_stack'
        ).order_by('-created_at')
        
        if undo_qs.count() > 2:
            overflow = undo_qs[2:]
            for rec in overflow:
                if rec.file and default_storage.exists(rec.file.name):
                    try:
                        default_storage.delete(rec.file.name)
                    except Exception as del_err:
                        logger.warning("Failed to delete expired undo file %s: %s", rec.file.name, del_err)
                rec.status = 'expired'
                rec.save(update_fields=['status'])

    @classmethod
    def undo_image_version(cls, card, field_name: str) -> dict:
        """
        Undo image version: Move active -> redo_stack, move latest undo_stack -> active.
        Updates card's field_data with restored image path.
        """
        if not card or not field_name:
            return {'success': False, 'message': 'Card and field_name required'}
        
        from ..models import CardMedia
        active_rec = CardMedia.objects.filter(card=card, field_name=field_name, status='active').order_by('-created_at').first()
        undo_rec = CardMedia.objects.filter(card=card, field_name=field_name, status='undo_stack').order_by('-created_at').first()
        
        if not undo_rec:
            return {'success': False, 'message': 'No undo history available'}
        
        if active_rec:
            active_rec.status = 'redo_stack'
            active_rec.save(update_fields=['status'])
        
        undo_rec.status = 'active'
        undo_rec.save(update_fields=['status'])
        
        restored_path = undo_rec.file.name
        
        # Update field_data on card
        if hasattr(card, 'field_data') and isinstance(card.field_data, dict):
            card.field_data[field_name] = restored_path
            card.save(update_fields=['field_data'])
        
        return {'success': True, 'restored_path': restored_path, 'version': undo_rec.version}

    @classmethod
    def redo_image_version(cls, card, field_name: str) -> dict:
        """
        Redo image version: Move active -> undo_stack, move latest redo_stack -> active.
        Updates card's field_data with restored image path.
        """
        if not card or not field_name:
            return {'success': False, 'message': 'Card and field_name required'}
        
        from ..models import CardMedia
        active_rec = CardMedia.objects.filter(card=card, field_name=field_name, status='active').order_by('-created_at').first()
        redo_rec = CardMedia.objects.filter(card=card, field_name=field_name, status='redo_stack').order_by('-created_at').first()
        
        if not redo_rec:
            return {'success': False, 'message': 'No redo history available'}
        
        if active_rec:
            active_rec.status = 'undo_stack'
            active_rec.save(update_fields=['status'])
        
        redo_rec.status = 'active'
        redo_rec.save(update_fields=['status'])
        
        restored_path = redo_rec.file.name
        
        if hasattr(card, 'field_data') and isinstance(card.field_data, dict):
            card.field_data[field_name] = restored_path
            card.save(update_fields=['field_data'])
        
        return {'success': True, 'restored_path': restored_path, 'version': redo_rec.version}

    @classmethod
    def replace_image(
        cls,
        image_bytes: bytes,
        client,
        field_name: str,
        existing_path: str,
        card=None,
        batch_counter: int = 1,
        original_ext: str = '.jpg',
        original_filename: str = None,
        uploaded_by=None,
        delete_old_after_save: bool = False,
        confirm_overwrite: bool = False,
    ) -> 'MediaResult':
        """
        Single entry point for REPLACING an existing image with Undo history support.
        """
        if not existing_path or existing_path in ('NOT_FOUND', '') or existing_path.startswith('PENDING:'):
            return cls.save_new_image(
                image_bytes=image_bytes,
                client=client,
                field_name=field_name,
                card=card,
                batch_counter=batch_counter,
                original_ext=original_ext,
                original_filename=original_filename,
                uploaded_by=uploaded_by,
            )

        # Check stale version warning
        warning = cls.check_old_version_warning(card, field_name, existing_path, confirm_overwrite=confirm_overwrite)
        if warning:
            return MediaResult(success=False, message=warning['message'], data=warning['data'])

        uploader_prefix = cls._resolve_uploader_prefix(uploaded_by)

        # Save new image version without instantly deleting old image file (enables undo)
        result = cls.save_image_with_thumbnail(
            image_bytes=image_bytes,
            client=client,
            existing_path=existing_path,
            batch_counter=batch_counter,
            original_ext=original_ext,
            delete_existing_on_update=delete_old_after_save,
            uploader_prefix=uploader_prefix,
        )
        if not result.success:
            return result

        saved_path = result.data.get('path', '')

        if card and saved_path:
            try:
                from django.db import transaction
                with transaction.atomic():
                    parsed = ImageRenamer.parse_filename(saved_path)
                    root_token = parsed['root_token'] if parsed else None
                    version = parsed['edit_count'] if parsed else 1
                    
                    new_media = cls.create_media_record(
                        saved_path=saved_path,
                        client=client,
                        card=card,
                        field_name=field_name,
                        media_type='photo',
                        original_filename=original_filename,
                        uploaded_by=uploaded_by,
                        root_token=root_token,
                        version=version,
                        last_edited_by_role=uploader_prefix,
                        status='active',
                    ).data.get('media')

                    cls.update_history_stack_on_save(card, field_name, new_media)
            except Exception as cm_err:
                logger.warning("CardMedia update failed in replace_image for %s: %s", field_name, cm_err)

        result.data['final_value'] = saved_path
        result.data['action'] = 'upload'
        return result

    @classmethod
    def mark_pending(cls, field_name: str, reference: str) -> 'MediaResult':
        """
        Mark an image field as pending — no image available yet.

        Returns:
            MediaResult with data['final_value'] = 'PENDING:{reference}' or ''.
        """
        if reference:
            final_value = f'PENDING:{reference}'
        else:
            final_value = ''
        return MediaResult(
            success=True,
            data={'final_value': final_value, 'action': 'pending'},
        )

    @classmethod
    def remove_image(cls, field_name: str, current_path: str, card=None) -> 'MediaResult':
        """
        Remove an image — deletes file, thumbnail, and CardMedia.

        Returns:
            MediaResult with data['final_value'] = ''.
        """
        if current_path and current_path not in ('', 'NOT_FOUND') and not current_path.startswith('PENDING:'):
            try:
                cls.delete_image(current_path)
            except Exception as del_err:
                logger.warning("Failed to delete image for %s: %s", field_name, del_err)

            if card:
                try:
                    from ..models import CardMedia
                    CardMedia.objects.filter(card=card, field_name=field_name).delete()
                except Exception as cm_err:
                    logger.warning("Failed to delete CardMedia for %s: %s", field_name, cm_err)

                # Clear legacy photo ImageField if primary photo is being removed
                if field_name.upper() == 'PHOTO' and hasattr(card, 'photo') and card.photo:
                    try:
                        card.photo.delete(save=False)
                    except Exception as photo_err:
                        logger.warning("Failed to delete legacy card.photo: %s", photo_err)

        return MediaResult(
            success=True,
            data={'final_value': '', 'action': 'removal'},
        )

    # ==================== CARDMEDIA INTEGRATION ====================

    @classmethod
    def create_media_record(
        cls,
        saved_path: str,
        client,
        card=None,
        group=None,
        media_type: Optional[str] = 'photo',
        field_name: Optional[str] = None,
        original_filename: Optional[str] = None,
        uploaded_by=None,
        root_token: Optional[str] = None,
        version: int = 0,
        last_edited_by_role: str = 'a',
        status: str = 'active',
    ) -> 'MediaResult':
        """
        Create a CardMedia record for a saved image.
        """
        try:
            from ..models import CardMedia
            
            if not root_token:
                parsed = ImageRenamer.parse_filename(saved_path)
                if parsed:
                    root_token = parsed['root_token']
                    version = parsed['edit_count']
                    last_edited_by_role = parsed['role']
            
            media = CardMedia.objects.create(
                card=card,
                group=group,
                client=client,
                file=saved_path,
                media_type=media_type or 'photo',
                field_name=field_name,
                original_filename=original_filename,
                uploaded_by=uploaded_by,
                root_token=root_token,
                version=version,
                last_edited_by_role=last_edited_by_role,
                status=status,
            )
            
            return MediaResult(
                success=True,
                message="Media record created",
                data={'media': media, 'media_id': media.pk}
            )
            
        except Exception as e:
            logger.warning("Failed to create CardMedia record: %s", e)
            return MediaResult(success=False, message=str(e), data={'media': None})

    @classmethod
    def save_image_with_media_record(
        cls,
        file_content,
        client,
        card=None,
        group=None,
        field_name: Optional[str] = None,
        media_type: Optional[str] = None,
        existing_path: Optional[str] = None,
        batch_counter: int = 1,
        uploaded_by=None,
        original_filename: Optional[str] = None
    ) -> 'MediaResult':
        """
        Save image and create CardMedia record in one operation.
        """
        # Save the image with thumbnail
        if hasattr(file_content, 'read'):
            image_bytes = file_content.read()
            file_content.seek(0)
        else:
            image_bytes = file_content
        
        # Get extension
        original_ext = '.jpg'
        if original_filename:
            _, ext = os.path.splitext(original_filename)
            if ext:
                original_ext = ImageRenamer.normalize_extension(ext)
        
        result = cls.save_image_with_thumbnail(
            image_bytes,
            client,
            existing_path,
            batch_counter,
            original_ext
        )
        
        if not result.success:
            return result
        
        # Create media record
        saved_path = result.data.get('path')
        if not saved_path:
            return result  # No path to record
        
        media_result = cls.create_media_record(
            saved_path=saved_path,
            client=client,
            card=card,
            group=group,
            media_type=media_type or field_name or 'photo',
            field_name=field_name,
            original_filename=original_filename,
            uploaded_by=uploaded_by
        )
        
        # Merge results
        result.data.update(media_result.data)
        
        return result
