from django.db import models
from django.conf import settings
from organisation.models import Organisation


class Operator(models.Model):
    """
    Operator model (formerly Admin Staff)
    assigned_clients controls which clients this operator can access.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='operator_profile')
    assigned_organisations = models.ManyToManyField(Organisation, blank=True, related_name='assigned_operators')
    
    department = models.CharField(max_length=100, blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True, null=True)
    
    # ID Card Organisation List Permission
    perm_idcard_client_list = models.BooleanField(default=False)  # kept DB name for compat
    perm_manage_assistant = models.BooleanField(default=False)
    perm_manage_photographer_staff = models.BooleanField(default=False)
    
    # ID Card Setting Permissions
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
    perm_idcard_add = models.BooleanField(default=False)
    perm_idcard_edit = models.BooleanField(default=False)
    perm_idcard_delete = models.BooleanField(default=False)
    perm_idcard_info = models.BooleanField(default=False)
    perm_idcard_approve = models.BooleanField(default=False)
    perm_idcard_verify = models.BooleanField(default=False)
    perm_idcard_updated_at = models.BooleanField(default=False)
    perm_idcard_delete_from_pool = models.BooleanField(default=False)
    perm_idcard_clear_pending_path = models.BooleanField(default=False)
    perm_reupload_idcard_image = models.BooleanField(default=False)
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
    
    # ID Card Bulk Action Permissions
    perm_idcard_bulk_upload = models.BooleanField(default=False)
    perm_idcard_bulk_download = models.BooleanField(default=False)
    perm_idcard_download_image_rename_mode = models.BooleanField(default=False)
    perm_idcard_download_image_generate_mode = models.BooleanField(default=False)
    perm_idcard_bulk_reupload = models.BooleanField(default=False)
    perm_idcard_upgrade_all = models.BooleanField(default=False)
    
    # Mobile App (PWA) Permission
    perm_mobile_app = models.BooleanField(default=False)
    
    # Manage Panel Permissions
    perm_manage_panel_backup = models.BooleanField(default=False)
    perm_manage_panel_email = models.BooleanField(default=False)
    
    # Pro Features
    perm_pro_user_options = models.BooleanField(default=False)
    perm_pro_log_deletion_guard = models.BooleanField(default=False)
    perm_pro_data_deletion_guard = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - Operator"
