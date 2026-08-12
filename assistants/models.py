from django.db import models
from django.conf import settings
from organisation.models import Organisation


class Assistant(models.Model):
    """
    Assistant model — a sub-account created under an Organisation.
    Role: 'assistant' (unchanged — not the same as 'manager')
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assistant_profile',
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='assistants',
    )

    # Tables this assistant can access (empty = all tables in the organisation)
    assigned_groups = models.ManyToManyField(
        'tables.Table',
        blank=True,
        related_name='assigned_assistants',
        help_text='Tables this assistant can manage. Empty = all tables.',
    )
    assigned_table_ids = models.JSONField(default=list, blank=True)

    allowed_classes = models.JSONField(default=list, blank=True)
    allowed_sections = models.JSONField(default=list, blank=True)
    allowed_branches = models.JSONField(default=list, blank=True)
    assignment_scopes = models.JSONField(default=list, blank=True)

    department = models.CharField(max_length=100, blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True, null=True)

    # ── Permissions ─────────────────────────────────────────
    perm_organisation_list = models.BooleanField(default=False)
    perm_manage_assistants = models.BooleanField(default=False)

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
    perm_idcard_clear_pending_path = models.BooleanField(default=False)
    perm_reupload_idcard_image = models.BooleanField(default=False)
    perm_idcard_retrieve = models.BooleanField(default=False)

    perm_idcard_bulk_upload = models.BooleanField(default=False)
    perm_idcard_bulk_download = models.BooleanField(default=False)
    perm_idcard_download_image_rename_mode = models.BooleanField(default=False)
    perm_idcard_download_image_generate_mode = models.BooleanField(default=False)
    perm_idcard_bulk_reupload = models.BooleanField(default=False)
    perm_idcard_upgrade_all = models.BooleanField(default=False)

    perm_mobile_app = models.BooleanField(default=False)
    perm_manage_panel_backup = models.BooleanField(default=False)
    perm_manage_panel_email = models.BooleanField(default=False)

    perm_pro_user_options = models.BooleanField(default=False)
    perm_pro_log_deletion_guard = models.BooleanField(default=False)
    perm_pro_data_deletion_guard = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Legacy compat ──────────────────────────────────────
    @property
    def client(self):
        return self.organisation

    @client.setter
    def client(self, value):
        self.organisation = value

    @property
    def perm_idcard_client_list(self):
        return self.perm_organisation_list

    @perm_idcard_client_list.setter
    def perm_idcard_client_list(self, value):
        self.perm_organisation_list = value

    @property
    def perm_manage_client_staff(self):
        return self.perm_manage_assistants

    @perm_manage_client_staff.setter
    def perm_manage_client_staff(self, value):
        self.perm_manage_assistants = value

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} — Assistant"
