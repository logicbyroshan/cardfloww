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
    Generate a 5-character code from organisation name.
    - If 3+ words: use first char of each word (up to 5)
    - If 2 or fewer words: use first 2-3 chars of each word
    Always returns exactly 5 uppercase characters (padded with X if needed)
    """
    if not name:
        return generate_unique_suffix()

    words = re.sub(r'[^a-zA-Z0-9\s]', '', name).split()
    words = [w for w in words if w]

    if not words:
        return generate_unique_suffix()

    code = ''
    if len(words) >= 3:
        for word in words[:5]:
            if word:
                code += word[0].upper()
    elif len(words) == 2:
        code = words[0][:3].upper() + words[1][:2].upper()
    else:
        code = words[0][:5].upper()

    code = code[:5].ljust(5, 'X')
    return code


def generate_unique_suffix():
    """Generate 5 random alphanumeric characters"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))


class Organisation(models.Model):
    """
    Organisation model — represents a School, College, Office or Institution.
    Owned by a Prime Manager (user with role='prime_manager').

    NOTE: db_table='core_client' preserved for migration compatibility.
    Replaces the old Client model — zero destructive DB migration required.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    ]

    ORG_TYPE_CHOICES = [
        ('school', 'School'),
        ('college', 'College'),
        ('company', 'Company / Corporate'),
        ('other', 'Other'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organisation_profile',
        null=True,
        blank=True,
    )

    # Unique folder ID for storing images (never changes)
    image_folder_uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    image_folder_code = models.CharField(max_length=10, blank=True, null=True, unique=True)
    image_folder_suffix = models.CharField(max_length=5, blank=True, null=True)

    # Basic Information
    name = models.CharField(max_length=200, db_index=True)
    max_super_managers = models.PositiveIntegerField(
        default=4,
        help_text='Configurable maximum number of Super Managers allowed for this organisation',
    )
    org_type = models.CharField(
        max_length=20,
        choices=ORG_TYPE_CHOICES,
        default='school',
        db_column='client_type',
        db_index=True,
        help_text='Type of organisation: school, college, company, or other',
    )
    is_guest = models.BooleanField(default=False, db_index=True)
    is_default = models.BooleanField(default=False, help_text='System default organisation')
    org_role = models.CharField(
        max_length=50,
        default='organisation',
        help_text='primary, organisation, or manager',
    )
    icon = models.CharField(max_length=100, default='fa-solid fa-building')

    # Address
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    pincode = models.CharField(max_length=10, blank=True, null=True)

    perm_organisation_list = models.BooleanField(default=False, db_column='perm_idcard_client_list')

    perm_idcard_setting_list = models.BooleanField(default=False)
    perm_idcard_setting_add = models.BooleanField(default=False)
    perm_idcard_setting_edit = models.BooleanField(default=False)
    perm_idcard_setting_delete = models.BooleanField(default=False)
    perm_idcard_setting_status = models.BooleanField(default=False)

    perm_idcard_pending_list = models.BooleanField(default=False)
    perm_idcard_verified_list = models.BooleanField(default=False)
    perm_idcard_pool_list = models.BooleanField(default=False)
    perm_idcard_approved_list = models.BooleanField(default=False)
    perm_idcard_download_list = models.BooleanField(default=False)
    perm_idcard_reprint_list = models.BooleanField(default=False)
    perm_reprint_request_list = models.BooleanField(default=False)
    perm_confirmed_list = models.BooleanField(default=False)

    perm_idcard_add = models.BooleanField(default=False)
    perm_idcard_edit = models.BooleanField(default=False)
    perm_idcard_delete = models.BooleanField(default=False)
    perm_idcard_info = models.BooleanField(default=False)
    perm_idcard_approve = models.BooleanField(default=False)
    perm_idcard_verify = models.BooleanField(default=False)
    perm_idcard_updated_at = models.BooleanField(default=False)
    perm_idcard_delete_from_pool = models.BooleanField(default=False)
    perm_reupload_idcard_image = models.BooleanField(default=False)
    perm_idcard_retrieve = models.BooleanField(default=False)

    perm_idcard_bulk_upload = models.BooleanField(default=False)
    perm_idcard_bulk_download = models.BooleanField(default=False)
    perm_idcard_download_image_rename_mode = models.BooleanField(default=False)
    perm_idcard_download_image_generate_mode = models.BooleanField(default=False)
    perm_idcard_bulk_reupload = models.BooleanField(default=False)
    perm_delete_all_idcard = models.BooleanField(default=False)
    perm_idcard_upgrade_all = models.BooleanField(default=False)

    perm_mobile_app = models.BooleanField(default=False, help_text='Allow access to mobile PWA app')
    perm_set_temp_password = models.BooleanField(
        default=False,
        help_text='Allow prime manager to set temporary passwords for own manager accounts',
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Legacy compatibility properties ──────────────────────
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

    # Legacy compat: old code accessed perm_idcard_client_list
    @property
    def perm_idcard_client_list(self):
        return self.perm_organisation_list

    @perm_idcard_client_list.setter
    def perm_idcard_client_list(self, value):
        self.perm_organisation_list = value

    def get_or_infer_org_type(self):
        """Return explicit org_type if set to non-other, else infer from organisation name."""
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
        self._original_name = self.__dict__.get('name') if self.pk else None

    def generate_folder_code(self):
        """Generate and set the image folder code based on organisation name"""
        name_part = generate_folder_code_from_name(self.name)
        if not self.image_folder_suffix:
            self.image_folder_suffix = generate_unique_suffix()
        self.image_folder_code = f"{name_part}{self.image_folder_suffix}"
        return self.image_folder_code

    def get_image_folder_path(self):
        """Get the full folder path for this organisation's images"""
        if not self.image_folder_code:
            self.generate_folder_code()
            self.save(update_fields=['image_folder_code', 'image_folder_suffix'])
        return f"adarshimg/{self.image_folder_code}"

    def ensure_image_folder_exists(self):
        """Create the image folder if it doesn't exist"""
        folder_path = os.path.join(settings.MEDIA_ROOT, self.get_image_folder_path())
        os.makedirs(folder_path, exist_ok=True)
        return folder_path

    def rename_image_folder(self):
        """Rename image folder when organisation name changes."""
        if not self.image_folder_suffix:
            return

        old_code = self.image_folder_code
        old_folder_path = os.path.join(settings.MEDIA_ROOT, f"adarshimg/{old_code}")
        new_name_part = generate_folder_code_from_name(self.name)
        new_code = f"{new_name_part}{self.image_folder_suffix}"
        new_folder_path = os.path.join(settings.MEDIA_ROOT, f"adarshimg/{new_code}")

        if old_code != new_code and os.path.exists(old_folder_path):
            try:
                os.rename(old_folder_path, new_folder_path)
                logger.debug("Renamed folder: %s -> %s", old_code, new_code)

                old_thumbs = os.path.join(settings.MEDIA_ROOT, f"adarshimg/thumbs/{old_code}")
                new_thumbs = os.path.join(settings.MEDIA_ROOT, f"adarshimg/thumbs/{new_code}")
                if os.path.exists(old_thumbs):
                    try:
                        os.rename(old_thumbs, new_thumbs)
                    except Exception as e:
                        logger.warning("Could not rename thumbs folder: %s", e)

                from tables.models import IDCard
                from django.db import transaction
                old_prefix = f'adarshimg/{old_code}'
                new_prefix = f'adarshimg/{new_code}'
                batch = []
                BATCH_SIZE = 500
                for card in IDCard.objects.filter(table__organisation=self).iterator(chunk_size=BATCH_SIZE):
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

                from mediafiles.models import CardMedia
                from django.db.models import Value
                from django.db.models.functions import Replace
                CardMedia.objects.filter(
                    client=self,
                    file__contains=old_prefix,
                ).update(file=Replace('file', Value(old_prefix), Value(new_prefix)))

            except Exception as e:
                logger.warning("Could not rename folder %s to %s: %s", old_code, new_code, e)

        self.image_folder_code = new_code

    def delete_image_folder(self):
        """Delete the entire image folder and thumbnails"""
        if not self.image_folder_code:
            return

        media_root = os.path.realpath(settings.MEDIA_ROOT)
        folder_path = os.path.realpath(
            os.path.join(settings.MEDIA_ROOT, f"adarshimg/{self.image_folder_code}")
        )
        if not folder_path.startswith(media_root + os.sep):
            logger.error("Path traversal blocked in delete_image_folder: %s", folder_path)
            return
        if os.path.exists(folder_path):
            try:
                shutil.rmtree(folder_path)
            except Exception as e:
                logger.warning("Could not delete folder %s: %s", self.image_folder_code, e)

        thumbs_path = os.path.realpath(
            os.path.join(settings.MEDIA_ROOT, f"adarshimg/thumbs/{self.image_folder_code}")
        )
        if not thumbs_path.startswith(media_root + os.sep):
            logger.error("Path traversal blocked in delete_image_folder (thumbs): %s", thumbs_path)
            return
        if os.path.exists(thumbs_path):
            try:
                shutil.rmtree(thumbs_path)
            except Exception as e:
                logger.warning("Could not delete thumbs folder %s: %s", self.image_folder_code, e)

    def save(self, *args, **kwargs):
        if 'update_fields' in kwargs and kwargs['update_fields'] is not None:
            mapped_fields = []
            for f in kwargs['update_fields']:
                if f == 'perm_idcard_client_list':
                    mapped_fields.append('perm_organisation_list')
                elif f in ('perm_manage_client_staff', 'perm_manage_staff'):
                    mapped_fields.append('perm_manage_assistants')
                else:
                    mapped_fields.append(f)
            kwargs['update_fields'] = mapped_fields

        if self.pk and (not kwargs.get('update_fields') or 'name' in (kwargs.get('update_fields') or [])):
            if self._original_name and self._original_name != self.name and self.image_folder_code:
                self.rename_image_folder()
        if not self.image_folder_code:
            self.generate_folder_code()
        super().save(*args, **kwargs)
        self._original_name = self.name

    def delete(self, *args, **kwargs):
        self.delete_image_folder()
        super().delete(*args, **kwargs)

    class Meta:
        app_label = 'core'          # Keep core migration compatibility
        db_table = 'core_client'    # Reuse existing DB table — no destructive migration
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['status', 'created_at'], name='core_client_status_created_idx'),
        ]


class OrganisationManager(models.Model):
    """
    OrganisationManager model — represents independent Organisation-level managers
    (Prime Manager, Super Managers, Guest Managers) belonging directly to an Organisation.
    Super Managers are peers at Organisation level, NOT subordinates/children of the Prime Manager.
    """
    MANAGER_TYPE_CHOICES = [
        ('prime_manager', 'Prime Manager'),
        ('super_manager', 'Super Manager'),
        ('guest_manager', 'Guest Manager'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='org_manager_profile',
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='managers',
        db_column='client_id',
    )
    manager_type = models.CharField(
        max_length=20,
        choices=MANAGER_TYPE_CHOICES,
        default='super_manager',
        db_index=True,
    )
    department = models.CharField(max_length=100, blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    # Granular permission flags (inherits from Organisation by default)
    perm_organisation_list = models.BooleanField(default=False)
    perm_manage_assistants = models.BooleanField(default=True)
    perm_idcard_setting_list = models.BooleanField(default=True)
    perm_idcard_setting_add = models.BooleanField(default=False)  # Only Prime Manager can create tables!
    perm_idcard_setting_edit = models.BooleanField(default=True)
    perm_idcard_setting_delete = models.BooleanField(default=False)
    perm_idcard_setting_status = models.BooleanField(default=True)

    perm_idcard_pending_list = models.BooleanField(default=True)
    perm_idcard_verified_list = models.BooleanField(default=True)
    perm_idcard_pool_list = models.BooleanField(default=True)
    perm_idcard_approved_list = models.BooleanField(default=True)
    perm_idcard_download_list = models.BooleanField(default=True)
    perm_idcard_reprint_list = models.BooleanField(default=True)
    perm_reprint_request_list = models.BooleanField(default=True)
    perm_confirmed_list = models.BooleanField(default=True)

    perm_idcard_add = models.BooleanField(default=True)
    perm_idcard_edit = models.BooleanField(default=True)
    perm_idcard_delete = models.BooleanField(default=True)
    perm_idcard_info = models.BooleanField(default=True)
    perm_idcard_approve = models.BooleanField(default=True)
    perm_idcard_verify = models.BooleanField(default=True)
    perm_idcard_updated_at = models.BooleanField(default=True)
    perm_idcard_delete_from_pool = models.BooleanField(default=False)
    perm_reupload_idcard_image = models.BooleanField(default=True)
    perm_idcard_retrieve = models.BooleanField(default=True)

    perm_idcard_bulk_upload = models.BooleanField(default=True)
    perm_idcard_bulk_download = models.BooleanField(default=True)
    perm_idcard_download_image_rename_mode = models.BooleanField(default=True)
    perm_idcard_download_image_generate_mode = models.BooleanField(default=True)
    perm_idcard_bulk_reupload = models.BooleanField(default=False)
    perm_delete_all_idcard = models.BooleanField(default=False)
    perm_idcard_upgrade_all = models.BooleanField(default=False)
    perm_mobile_app = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organisation_manager'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organisation', 'manager_type']),
            models.Index(fields=['manager_type', 'is_active']),
        ]

    def __str__(self):
        return f"{self.user.username} ({self.get_manager_type_display()}) - {self.organisation.name}"


# ── Backward compatibility aliases ─────────────────────────────────────
# Old code that references `Client` or `from organisation.models import Organisation`
# will continue to work during the transition period.
Client = Organisation
