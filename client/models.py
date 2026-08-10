import logging
import os
import random
import re
import shutil
import string
import uuid

from django.db import models
from django.conf import settings

logger = logging.getLogger(__name__)


def generate_folder_code_from_name(name):
    """
    Generate a 5-character code from client name:
    - If 3+ words: use first char of each word (up to 5)
    - If 2 or fewer words: use first 2-3 chars of each word
    Always returns exactly 5 uppercase characters (padded with X if needed)
    """
    if not name:
        return generate_unique_suffix()
    
    # Remove special characters and split into words
    words = re.sub(r'[^a-zA-Z0-9\s]', '', name).split()
    words = [w for w in words if w]  # Remove empty strings
    
    if not words:
        return generate_unique_suffix()
    
    code = ''
    if len(words) >= 3:
        # 3+ words: use first char of each word
        for word in words[:5]:
            if word:
                code += word[0].upper()
    elif len(words) == 2:
        # 2 words: use first 2-3 chars of each
        code = words[0][:3].upper() + words[1][:2].upper()
    else:
        # 1 word: use first 5 chars
        code = words[0][:5].upper()
    
    # Ensure exactly 5 characters
    code = code[:5].ljust(5, 'X')
    return code


def generate_unique_suffix():
    """Generate 5 random alphanumeric characters"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))


class Client(models.Model):
    """
    Client model - managed by principals/management
    
    NOTE: app_label='core' preserved for migration compatibility.
    Model code moved from core/models.py to client/models.py
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    ]
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='client_profile')
    
    # Unique folder ID for storing images (never changes even if client name changes)
    image_folder_uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    
    # Image folder code: 5 chars from name + 5 unique chars = 10 chars max
    # Format: {ABCDE}{12345} where ABCDE is from client name, 12345 is unique suffix
    image_folder_code = models.CharField(max_length=10, blank=True, null=True, unique=True)
    # Store the unique suffix separately (never changes)
    image_folder_suffix = models.CharField(max_length=5, blank=True, null=True)
    
    ORG_TYPE_CHOICES = [
        ('school', 'School'),
        ('college', 'College'),
        ('company', 'Company / Corporate'),
        ('other', 'Other'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200, db_index=True)
    org_type = models.CharField(
        max_length=20,
        choices=ORG_TYPE_CHOICES,
        default='school',
        db_index=True,
        help_text='Type of organisation: school, college, company, or other'
    )
    is_guest = models.BooleanField(default=False, db_index=True)
    is_default = models.BooleanField(default=False, help_text='System default organisation')
    client_type = models.CharField(max_length=50, default='organisation', help_text='primary, organisation, or manager')
    # Icon class for panel branding (FontAwesome class name)
    icon = models.CharField(max_length=100, default='fa-solid fa-building')
    
    # Address
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    pincode = models.CharField(max_length=10, blank=True, null=True)
    
    # ID Card Client List Permission
    perm_idcard_client_list = models.BooleanField(default=False)
    
    # ID Card Setting Permissions (sensitive — default OFF)
    perm_idcard_setting_list = models.BooleanField(default=False)
    perm_idcard_setting_add = models.BooleanField(default=False)
    perm_idcard_setting_edit = models.BooleanField(default=False)
    perm_idcard_setting_delete = models.BooleanField(default=False)
    perm_idcard_setting_status = models.BooleanField(default=False)
    
    
    # ID Card List Permissions
    perm_idcard_pending_list = models.BooleanField(default=False)
    perm_idcard_verified_list = models.BooleanField(default=False)
    perm_idcard_pool_list = models.BooleanField(default=False)
    perm_idcard_approved_list = models.BooleanField(default=False)
    perm_idcard_download_list = models.BooleanField(default=False)
    perm_idcard_reprint_list = models.BooleanField(default=False)
    perm_reprint_request_list = models.BooleanField(default=False)
    perm_confirmed_list = models.BooleanField(default=False)

    
    # ID Card Action Permissions
    # Note: Actions only work in Pending and Verified lists
    perm_idcard_add = models.BooleanField(default=False)
    perm_idcard_edit = models.BooleanField(default=False)
    perm_idcard_delete = models.BooleanField(default=False)
    perm_idcard_info = models.BooleanField(default=False)
    perm_idcard_approve = models.BooleanField(default=False)
    perm_idcard_verify = models.BooleanField(default=False)
    perm_idcard_updated_at = models.BooleanField(default=False)
    perm_idcard_delete_from_pool = models.BooleanField(default=False)
    perm_reupload_idcard_image = models.BooleanField(default=False)  # Single card reupload
    perm_idcard_retrieve = models.BooleanField(default=False)

    @property
    def perm_idcard_deleted_list(self):
        return self.perm_idcard_pool_list

    @perm_idcard_deleted_list.setter
    def perm_idcard_deleted_list(self, value):
        self.perm_idcard_pool_list = value

    @property
    def perm_idcard_delete_from_deleted(self):
        return self.perm_idcard_delete_from_pool

    @perm_idcard_delete_from_deleted.setter
    def perm_idcard_delete_from_deleted(self, value):
        self.perm_idcard_delete_from_pool = value
    
    # ID Card Bulk Action Permissions (work across all lists)
    perm_idcard_bulk_upload = models.BooleanField(default=False)
    perm_idcard_bulk_download = models.BooleanField(default=False)
    perm_idcard_download_image_rename_mode = models.BooleanField(default=False)
    perm_idcard_download_image_generate_mode = models.BooleanField(default=False)
    perm_idcard_bulk_reupload = models.BooleanField(default=False)  # Bulk reupload for all lists
    perm_delete_all_idcard = models.BooleanField(default=False)
    perm_idcard_upgrade_all = models.BooleanField(default=False)  # Upgrade All Class
    
    # Mobile App (PWA) Permission
    perm_mobile_app = models.BooleanField(default=False, help_text='Allow access to mobile PWA app')

    # Account Security Permissions
    perm_set_temp_password = models.BooleanField(
        default=False,
        help_text='Allow client to set temporary passwords for own staff accounts'
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_or_infer_org_type(self):
        """Return explicit org_type if set to non-other, else infer from client name."""
        if self.org_type and self.org_type != 'other':
            return self.org_type

        name_l = (self.name or '').lower()
        if re.search(r'\b(college|university|institute|polytechnic|degree|campus)\b', name_l):
            return 'college'
        if re.search(r'\b(school|vidyalaya|academy|convent|bal|patshala|gurukul)\b', name_l):
            return 'school'
        if re.search(r'\b(ltd|pvt|corp|inc|tech|technologies|company|services|solutions|enterprise|firm)\b', name_l):
            return 'company'

        return self.org_type or 'school'

    def __str__(self):
        return self.name
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cache original name to detect changes without an extra DB query in save()
        self._original_name = self.__dict__.get('name') if self.pk else None
    
    def generate_folder_code(self):
        """Generate and set the image folder code based on client name"""
        name_part = generate_folder_code_from_name(self.name)
        
        # Generate unique suffix if not already set
        if not self.image_folder_suffix:
            self.image_folder_suffix = generate_unique_suffix()
        
        self.image_folder_code = f"{name_part}{self.image_folder_suffix}"
        return self.image_folder_code
    
    def get_image_folder_path(self):
        """Get the full folder path for this client's images"""
        if not self.image_folder_code:
            self.generate_folder_code()
            self.save(update_fields=['image_folder_code', 'image_folder_suffix'])
        return f"adarshimg/{self.image_folder_code}"
    
    def ensure_image_folder_exists(self):
        """Create the image folder if it doesn't exist"""
        from django.conf import settings
        folder_path = os.path.join(settings.MEDIA_ROOT, self.get_image_folder_path())
        os.makedirs(folder_path, exist_ok=True)
        return folder_path
    
    def rename_image_folder(self):
        """
        Rename the image folder when client name changes.
        Only updates the first 5 chars (name part), suffix stays same.
        Also updates all card field_data paths, thumbnail folder, and CardMedia records.
        """
        from django.conf import settings

        if not self.image_folder_suffix:
            # No folder exists yet
            return

        old_code = self.image_folder_code
        old_folder_path = os.path.join(settings.MEDIA_ROOT, f"adarshimg/{old_code}")

        # Generate new code with updated name
        new_name_part = generate_folder_code_from_name(self.name)
        new_code = f"{new_name_part}{self.image_folder_suffix}"
        new_folder_path = os.path.join(settings.MEDIA_ROOT, f"adarshimg/{new_code}")

        # Rename folder if it exists and codes are different
        if old_code != new_code and os.path.exists(old_folder_path):
            try:
                os.rename(old_folder_path, new_folder_path)
                logger.debug("Renamed folder: %s -> %s", old_code, new_code)

                # Also rename thumbnail folder
                old_thumbs_path = os.path.join(settings.MEDIA_ROOT, f"adarshimg/thumbs/{old_code}")
                new_thumbs_path = os.path.join(settings.MEDIA_ROOT, f"adarshimg/thumbs/{new_code}")
                if os.path.exists(old_thumbs_path):
                    try:
                        os.rename(old_thumbs_path, new_thumbs_path)
                        logger.debug("Renamed thumbs folder: %s -> %s", old_code, new_code)
                    except Exception as e:
                        logger.warning("Could not rename thumbs folder %s to %s: %s", old_code, new_code, e)

                # Update all card field_data paths (batch update for safety)
                from idcards.models import IDCard
                from django.db import transaction
                old_prefix = f'adarshimg/{old_code}'
                new_prefix = f'adarshimg/{new_code}'
                batch = []
                BATCH_SIZE = 500
                for card in IDCard.objects.filter(table__group__client=self).iterator(chunk_size=BATCH_SIZE):
                    fd = card.field_data or {}
                    updated = False
                    for key, val in fd.items():
                        if isinstance(val, str) and old_prefix in val:
                            fd[key] = val.replace(old_prefix, new_prefix)
                            updated = True
                    if updated:
                        card.field_data = fd
                        batch.append(card)
                    if len(batch) >= BATCH_SIZE:
                        with transaction.atomic():
                            IDCard.objects.bulk_update(batch, ['field_data'], batch_size=BATCH_SIZE)
                        batch = []
                if batch:
                    with transaction.atomic():
                        IDCard.objects.bulk_update(batch, ['field_data'], batch_size=BATCH_SIZE)

                # Update CardMedia file paths
                from mediafiles.models import CardMedia
                from django.db.models import Value
                from django.db.models.functions import Replace
                CardMedia.objects.filter(
                    client=self,
                    file__contains=old_prefix
                ).update(file=Replace('file', Value(old_prefix), Value(new_prefix)))

            except Exception as e:
                logger.warning("Could not rename folder %s to %s: %s", old_code, new_code, e)

        self.image_folder_code = new_code
    
    def delete_image_folder(self):
        """Delete the entire image folder, thumbnail folder, and all contents"""
        from django.conf import settings

        if not self.image_folder_code:
            return

        media_root = os.path.realpath(settings.MEDIA_ROOT)

        folder_path = os.path.realpath(os.path.join(settings.MEDIA_ROOT, f"adarshimg/{self.image_folder_code}"))
        # Path traversal protection: ensure resolved path is within MEDIA_ROOT
        if not folder_path.startswith(media_root + os.sep):
            logger.error("Path traversal blocked in delete_image_folder: %s", folder_path)
            return
        if os.path.exists(folder_path):
            try:
                shutil.rmtree(folder_path)
                logger.debug("Deleted folder: %s", self.image_folder_code)
            except Exception as e:
                logger.warning("Could not delete folder %s: %s", self.image_folder_code, e)

        # Also delete thumbnail folder
        thumbs_path = os.path.realpath(os.path.join(settings.MEDIA_ROOT, f"adarshimg/thumbs/{self.image_folder_code}"))
        if not thumbs_path.startswith(media_root + os.sep):
            logger.error("Path traversal blocked in delete_image_folder (thumbs): %s", thumbs_path)
            return
        if os.path.exists(thumbs_path):
            try:
                shutil.rmtree(thumbs_path)
                logger.debug("Deleted thumbs folder: %s", self.image_folder_code)
            except Exception as e:
                logger.warning("Could not delete thumbs folder %s: %s", self.image_folder_code, e)
    def save(self, *args, **kwargs):
        # Check if this is an update and name changed
        # Uses cached _original_name from __init__ to avoid extra DB query
        if self.pk and (not kwargs.get('update_fields') or 'name' in (kwargs.get('update_fields') or [])):
            if self._original_name and self._original_name != self.name and self.image_folder_code:
                self.rename_image_folder()
        
        # Generate folder code if not set
        if not self.image_folder_code:
            self.generate_folder_code()
        
        super().save(*args, **kwargs)
        # Update cached name after save
        self._original_name = self.name
    
    def delete(self, *args, **kwargs):
        # Delete image folder when client is deleted
        self.delete_image_folder()
        super().delete(*args, **kwargs)
    
    class Meta:
        app_label = 'core'  # Keep migration compatibility - model stays in core migrations
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['status', 'created_at'], name='core_client_status_created_idx'),
        ]
