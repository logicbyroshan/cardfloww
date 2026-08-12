"""
Client Image Service — image upload and card-matching logic.
"""
import logging
import os
from collections import defaultdict

from organisation.models import Organisation
from tables.models import Table, IDCard
from core.services.base import BaseService, ServiceResult
from core.services.permission_service import PermissionService

from .services_access import OrganisationAccessService

logger = logging.getLogger(__name__)


class OrganisationImageService(BaseService):
    """
    Service for client image uploads.
    Handles image upload and linking to card data.
    """
    
    @classmethod
    def upload_images(cls, user, table_id: int, images) -> ServiceResult:
        """
        Upload images and link them to cards based on filename matching.
        
        Args:
            user: Current user
            table_id: ID of the table
            images: List of uploaded image files
        """
        try:
            client = OrganisationAccessService.get_organisation_for_user(user)
            if not client:
                return ServiceResult(success=False, message='Client profile not found')
            
            # Verify table access
            try:
                table = Table.objects.get(id=table_id)
            except Table.DoesNotExist:
                return ServiceResult(success=False, message='Table not found')
            
            if not OrganisationAccessService.can_access_table(user, table):
                return ServiceResult(success=False, message='Access denied')
            
            # Check upload permission
            if not PermissionService.has_permission(user, 'perm_reupload_idcard_image'):
                return ServiceResult(success=False, message='No permission to upload images')
            
            # Use the mediafiles ImageService for actual processing
            from mediafiles.services import ImageService
            
            matched = 0
            failed = 0

            cards = list(
                IDCard.objects
                .filter(table_id=table_id)
                .only('id', 'field_data', 'updated_at')
            )

            pending_targets = defaultdict(list)
            for card in cards:
                fd = card.field_data or {}
                for key, val in fd.items():
                    if not isinstance(val, str) or not val.startswith('PENDING:'):
                        continue
                    pending_id = val[len('PENDING:'):]
                    normalized_pending = cls.normalize_image_identifier(pending_id)
                    if normalized_pending:
                        pending_targets[normalized_pending].append((card, key))

            dirty_cards = {}
            batch_counter = 1

            for image in images:
                original_name = getattr(image, 'name', '')
                name_without_ext = os.path.splitext(original_name)[0] if original_name else ''
                if not name_without_ext:
                    continue
                
                # Normalize the uploaded filename the same way bulk upload does
                normalized_upload = cls.normalize_image_identifier(name_without_ext)
                if not normalized_upload:
                    continue

                targets = pending_targets.get(normalized_upload, [])
                if not targets:
                    continue

                try:
                    image.seek(0)
                    image_bytes = image.read()
                    image.seek(0)
                except Exception:
                    failed += len(targets)
                    continue

                _, ext = os.path.splitext(original_name)
                original_ext = ext or '.jpg'

                for card, key in targets:
                    fd = card.field_data or {}
                    # Skip if already resolved in this batch by a prior image.
                    current_val = fd.get(key, '')
                    if not isinstance(current_val, str) or not current_val.startswith('PENDING:'):
                        continue

                    try:
                        result = ImageService.save_new_image(
                            image_bytes=image_bytes,
                            client=client,
                            field_name=key,
                            card=card,
                            batch_counter=batch_counter,
                            original_ext=original_ext,
                            original_filename=original_name,
                            uploaded_by=user,
                        )
                        batch_counter += 1

                        if result.success and result.data.get('final_value'):
                            fd[key] = result.data['final_value']
                            card.field_data = fd
                            dirty_cards[card.pk] = card
                            matched += 1
                        else:
                            failed += 1
                    except Exception:
                        failed += 1

            if dirty_cards:
                IDCard.objects.bulk_update(
                    list(dirty_cards.values()),
                    ['field_data', 'updated_at'],
                    batch_size=200,
                )

            success = matched > 0 or failed == 0
            summary = f'Reupload complete: {matched} images matched, {failed} failed.'
            if not success:
                summary = f'No images were matched. {failed} item(s) failed.'
            
            return ServiceResult(
                success=success,
                message=summary,
                data={'matched': matched, 'failed': failed}
            )
            
        except Exception as e:
            logger.exception('OrganisationImageService.upload_images failed: %s', e)
            return ServiceResult(success=False, message='An unexpected error occurred. Please try again.')
