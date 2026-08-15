from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.db import models


def office_work_shared_file_upload_to(instance, filename):
    """Migration-compatibility shim for historical core migration imports."""
    import os
    from django.utils import timezone

    safe_name = os.path.basename(str(filename or '').strip()) or 'shared-file'
    return f'office-work/shared/{timezone.now():%Y/%m/%d}/{safe_name}'


class CustomUserManager(UserManager):
    """
    Custom user manager that ensures superuser and super_admin role are synchronized.
    """
    
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        """
        Create a superuser with role='super_admin' automatically.
        """
        extra_fields.setdefault('role', 'super_admin')
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom user model with role support
    
    NOTE: This model remains in core for database/migration compatibility.
    Views and business logic have been moved to apps.accounts.
    
    IMPORTANT: superuser (is_superuser=True) and super_admin (role='super_admin')
    are now synchronized. Setting one will automatically set the other.
    """
    ROLE_CHOICES = [
        ('pro_user', 'Pro User'),
        ('super_admin', 'Super Admin'),
        ('operator', 'Operator'),
        ('prime_manager', 'Prime Manager'),     # org owner — auto-created with Organisation
        ('manager', 'Manager'),                  # regular manager under org (up to 4)
        ('guest_prime_manager', 'Guest Prime Manager'),  # guest version of prime_manager
        ('assistant', 'Assistant'),
        ('photographer', 'Photographer'),
    ]

    phone = models.CharField(max_length=15, blank=True, null=True)
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='prime_manager', db_index=True)
    # DEPRECATED: profile_image removed - use frontend placeholder avatars instead
    # profile_image field removed in Phase 1 refactor
    is_active = models.BooleanField(default=True)
    # Tracks whether the welcome email has been sent (set True on first activation)
    welcome_email_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = CustomUserManager()

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    @property
    def staff_profile(self):
        from staff.models import StaffCompatWrapper
        try:
            if hasattr(self, 'operator_profile') and self.operator_profile:
                return StaffCompatWrapper(self.operator_profile, 'operator')
        except Exception:
            pass
        try:
            if hasattr(self, 'manager_profile') and self.manager_profile:
                return StaffCompatWrapper(self.manager_profile, 'manager')
        except Exception:
            pass
        try:
            if hasattr(self, 'photographer_profile') and self.photographer_profile:
                return StaffCompatWrapper(self.photographer_profile, 'photographer')
        except Exception:
            pass
        return None

    @property
    def client_profile(self):
        try:
            profile = getattr(self, '_organisation_profile_cache', None)
            if profile is not None:
                return profile
            return self.organisation_profile
        except Exception:
            try:
                from organisation.models import Organisation
                return Organisation.objects.filter(user=self).first()
            except Exception:
                return None

    @property
    def staff_profile(self):
        try:
            if hasattr(self, 'assistant_profile') and self.assistant_profile is not None:
                from staff.models import StaffCompatWrapper
                return StaffCompatWrapper(self.assistant_profile, 'assistant')
            if hasattr(self, 'operator_profile') and self.operator_profile is not None:
                from staff.models import StaffCompatWrapper
                return StaffCompatWrapper(self.operator_profile, 'operator')
            if hasattr(self, 'photographer_profile') and self.photographer_profile is not None:
                from staff.models import StaffCompatWrapper
                return StaffCompatWrapper(self.photographer_profile, 'photographer')
            from assistants.models import Assistant
            ast = Assistant.objects.filter(user=self).first()
            if ast:
                from staff.models import StaffCompatWrapper
                return StaffCompatWrapper(ast, 'assistant')
        except Exception:
            pass
        return None
    
    def save(self, *args, **kwargs):
        """
        Override save to synchronize is_superuser and role.
        Both directions are enforced:
        - is_superuser=True  ↔  role='super_admin' (or 'pro_user')
        - role='super_admin'/'pro_user'  →  is_superuser=True, is_staff=True
        - role != 'super_admin'/'pro_user'  →  clear is_superuser
        """
        if self.role == 'pro_user':
            # Pro user always gets superuser + staff
            self.is_superuser = True
            self.is_staff = True
        elif self.is_superuser and self.role != 'pro_user':
            self.role = 'super_admin'
            self.is_staff = True
        elif self.role == 'super_admin':
            self.is_superuser = True
            self.is_staff = True
        else:
            # Role is not super_admin/pro_user — make sure is_superuser is cleared
            self.is_superuser = False

        # Enforce max limits
        self._enforce_role_limits()

        super().save(*args, **kwargs)

    def _enforce_role_limits(self):
        """Enforce max 1 pro_user and max 3 super_admin accounts."""
        from django.core.exceptions import ValidationError
        if self.role == 'pro_user':
            qs = User.objects.filter(role='pro_user')
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError('Only one Pro User account is allowed.')
        elif self.role == 'super_admin':
            qs = User.objects.filter(role='super_admin')
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.count() >= 3:
                raise ValidationError('Maximum 3 Super Admin accounts are allowed.')
    
    class Meta:
        indexes = [
            # email index is auto-created by unique=True constraint below
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['email'],
                name='unique_user_email',
            ),
        ]

    @property
    def is_pro_user(self):
        return self.role == 'pro_user'

    @property
    def is_super_admin(self):
        """
        Check if user is super admin (or pro_user, which has all super_admin powers).
        """
        return self.is_superuser or self.role in ('super_admin', 'pro_user')
    
    @property
    def is_operator(self):
        return self.role == 'operator'

    @property
    def is_photographer(self):
        return self.role == 'photographer'

    @property
    def is_prime_manager(self):
        """True for org owners — the single account created with the Organisation."""
        return self.role in ('prime_manager', 'guest_prime_manager')

    @property
    def is_guest_prime_manager(self):
        return self.role == 'guest_prime_manager'

    @property
    def is_manager(self):
        """True for regular managers under an org (up to 4 per org)."""
        return self.role == 'manager'

    @property
    def is_any_manager(self):
        """True for both prime_manager and manager roles."""
        return self.role in ('prime_manager', 'manager', 'guest_prime_manager')

    @property
    def is_assistant(self):
        return self.role == 'assistant'

    @property
    def is_admin_staff(self):
        return self.is_operator

    # ── Legacy compat aliases ──────────────────────
    @property
    def is_client(self):
        """Deprecated: use is_prime_manager"""
        return self.is_prime_manager

    @property
    def is_guest_user(self):
        """Deprecated: use is_guest_prime_manager"""
        return self.is_guest_prime_manager

    @property
    def is_client_staff(self):
        """Deprecated: use is_assistant or is_manager"""
        return self.is_assistant


class SystemSettings(models.Model):
    """
    System/Application Settings
    """
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.CharField(max_length=255, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Default export footer messages
    EXPORT_DEFAULTS = {
        'export_note_line': 'Note: This document is computer generated. Please verify all details before printing ID cards.',
        'export_copyright_line': '© Adarsh ID Cards Management System - All Rights Reserved',
    }

    def __str__(self):
        return self.key

    class Meta:
        verbose_name = "System Setting"
        verbose_name_plural = "System Settings"

    @classmethod
    def get_value(cls, key, default=None):
        """Get a setting value by key, returning default if not found. Cached 5 min."""
        from django.core.cache import cache
        cache_key = f'sys_setting:{key}'
        value = cache.get(cache_key)
        if value is not None:
            return value
        try:
            value = cls.objects.get(key=key).value
            cache.set(cache_key, value, 300)
            return value
        except cls.DoesNotExist:
            fallback = default if default is not None else cls.EXPORT_DEFAULTS.get(key, '')
            return fallback

    @classmethod
    def set_value(cls, key, value, description=None):
        """Set a setting value, creating or updating. Invalidates cache."""
        from django.core.cache import cache
        obj, created = cls.objects.update_or_create(
            key=key,
            defaults={'value': value}
        )
        cache.delete(f'sys_setting:{key}')
        if description and (created or not obj.description):
            obj.description = description
            obj.save(update_fields=['description'])
        return obj

    @classmethod
    def get_export_settings(cls):
        """Return dict of all export-related settings."""
        keys = list(cls.EXPORT_DEFAULTS.keys())
        db_settings = {s.key: s.value for s in cls.objects.filter(key__in=keys)}
        return {key: db_settings.get(key, default_val) for key, default_val in cls.EXPORT_DEFAULTS.items()}



class ExportTemplate(models.Model):
    """
    User-defined export templates with custom footer text.
    Admins create templates in Settings → Export Templates, then choose
    one when downloading PDF or Word files.
    """
    FONT_CHOICES = [
        ('arial', 'English (Arial)'),
        ('hindi', 'Hindi (Abbasi)'),
    ]
    name = models.CharField(max_length=100, unique=True, help_text='Template name shown in the download dropdown')
    instructions = models.TextField(
        help_text='Footer text printed on each PDF/Word page when this template is selected'
    )
    font_name = models.CharField(
        max_length=10, choices=FONT_CHOICES, default='arial',
        help_text='Font used for instructions: arial (English) or hindi (Abbasi)',
    )
    is_bold = models.BooleanField(default=False, help_text='Render instructions in bold')
    is_default = models.BooleanField(default=False, help_text='Mark as default selection in download modals')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Export Template'
        verbose_name_plural = 'Export Templates'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Ensure only one default template
        if self.is_default:
            ExportTemplate.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_default(cls):
        """Return the default template or None."""
        return cls.objects.filter(is_default=True).first()

    @classmethod
    def get_all_as_choices(cls):
        """Return list of dicts for JSON serialisation."""
        templates = list(cls.objects.values('id', 'name', 'instructions', 'font_name', 'is_bold', 'is_default'))
        return templates


class ActivityLog(models.Model):
    """
    Tracks user activity across the system for the dashboard activity feed.
    Designed for lightweight, append-only logging of key actions.
    """

    # Action type choices grouped by category
    ACTION_CHOICES = [
        # Auth
        ('login', 'Logged in'),
        ('logout', 'Logged out'),
        ('password_reset', 'Password reset completed'),
        # Client management
        ('client_create', 'Client created'),
        ('client_update', 'Client updated'),
        ('client_delete', 'Client deleted'),
        ('client_status', 'Client status changed'),
        # Staff management
        ('staff_create', 'Staff created'),
        ('staff_update', 'Staff updated'),
        ('staff_assignment', 'Staff assignment updated'),
        ('staff_delete', 'Staff deleted'),
        ('staff_status', 'Staff status changed'),
        ('staff_password_reset', 'Staff password reset'),
        # ID Card operations
        ('card_create', 'ID cards added'),
        ('card_update', 'ID card updated'),
        ('card_delete', 'ID card deleted'),
        ('card_status', 'Card status changed'),
        ('card_bulk_status', 'Bulk card status change'),
        ('card_bulk_upload', 'Bulk card upload'),
        ('card_bulk_download', 'Bulk card download'),
        # Image operations
        ('image_upload', 'Images uploaded'),
        ('image_reupload', 'Images re-uploaded'),
        ('card_image_delete', 'Card image removed'),
        ('card_export', 'Cards exported'),
        # ID Card group/table
        ('group_create', 'Group created'),
        ('group_update', 'Group updated'),
        ('group_delete', 'Group deleted'),
        ('table_create', 'Table created'),
        ('table_update', 'Table updated'),
        ('table_delete', 'Table deleted'),
        # Bulk operations
        ('bulk_delete', 'Bulk delete'),
        ('bulk_upgrade', 'Bulk upgrade'),
        ('notification_create', 'Notification created'),
        ('notification_delete', 'Notification deleted'),
        ('email_send', 'Email sent'),
        ('email_resend', 'Email resent'),
        ('backup_initiate', 'Backup initiated'),
        ('backup_start', 'Backup started'),
        ('backup_delete', 'Backup deleted'),
        ('backup_download', 'Backup downloaded'),
        # Reprint
        ('reprint_request', 'Reprint requested'),
        ('reprint_status', 'Reprint status changed'),
        ('reprint_reject', 'Reprint request rejected'),
        # Communication
        ('client_message_send', 'Client message sent'),
        # Settings
        ('settings_update', 'Settings updated'),
        # Other
        ('other', 'Other action'),
    ]

    # Icon mapping for action types (used in templates)
    ACTION_ICONS = {
        'login': ('fa-right-to-bracket', 'verify'),
        'logout': ('fa-right-from-bracket', 'edit'),
        'password_reset': ('fa-key', 'approve'),
        'client_create': ('fa-user-plus', 'add'),
        'client_update': ('fa-user-pen', 'edit'),
        'client_delete': ('fa-user-minus', 'delete'),
        'client_status': ('fa-user-check', 'verify'),
        'staff_create': ('fa-user-plus', 'add'),
        'staff_update': ('fa-user-pen', 'edit'),
        'staff_assignment': ('fa-list-check', 'verify'),
        'staff_delete': ('fa-user-minus', 'delete'),
        'staff_status': ('fa-user-check', 'verify'),
        'staff_password_reset': ('fa-key', 'approve'),
        'card_create': ('fa-plus', 'add'),
        'card_update': ('fa-pen', 'edit'),
        'card_delete': ('fa-trash', 'delete'),
        'card_status': ('fa-check', 'verify'),
        'card_bulk_status': ('fa-check-double', 'approve'),
        'card_bulk_upload': ('fa-upload', 'add'),
        'card_bulk_download': ('fa-download', 'approve'),
        'image_upload': ('fa-image', 'add'),
        'image_reupload': ('fa-images', 'edit'),
        'card_image_delete': ('fa-image', 'delete'),
        'card_export': ('fa-file-export', 'approve'),
        'group_create': ('fa-folder-plus', 'add'),
        'group_update': ('fa-folder-open', 'edit'),
        'group_delete': ('fa-folder-minus', 'delete'),
        'table_create': ('fa-table', 'add'),
        'table_update': ('fa-table', 'edit'),
        'table_delete': ('fa-table', 'delete'),
        'bulk_delete': ('fa-trash-can', 'delete'),
        'bulk_upgrade': ('fa-arrow-up', 'approve'),
        'notification_create': ('fa-bell', 'add'),
        'notification_delete': ('fa-bell-slash', 'delete'),
        'email_send': ('fa-envelope-circle-check', 'approve'),
        'email_resend': ('fa-envelope-open-text', 'edit'),
        'backup_initiate': ('fa-database', 'edit'),
        'backup_start': ('fa-vault', 'approve'),
        'backup_delete': ('fa-trash-can', 'delete'),
        'backup_download': ('fa-cloud-arrow-down', 'approve'),
        'reprint_request': ('fa-print', 'add'),
        'reprint_status': ('fa-print', 'verify'),
        'reprint_reject': ('fa-ban', 'delete'),
        'client_message_send': ('fa-comment-dots', 'approve'),
        'settings_update': ('fa-gear', 'edit'),
        'other': ('fa-circle-info', 'edit'),
    }

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
        db_index=True,
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, db_index=True)
    description = models.CharField(max_length=500)
    target_model = models.CharField(max_length=50, blank=True, default='')
    target_id = models.PositiveIntegerField(null=True, blank=True)
    target_name = models.CharField(max_length=200, blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Activity Log'
        verbose_name_plural = 'Activity Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at', 'action'], name='actlog_time_action_idx'),
            models.Index(fields=['user', '-created_at'], name='actlog_user_time_idx'),
        ]

    def __str__(self):
        actor = self.user.get_full_name() or self.user.username if self.user else 'System'
        return f"{actor} — {self.description}"

    @property
    def icon_class(self):
        """Returns FA icon class for this action type."""
        return self.ACTION_ICONS.get(self.action, ('fa-circle-info', 'edit'))[0]

    @property
    def icon_color(self):
        """Returns CSS class (add/edit/delete/verify/approve) for this action type."""
        return self.ACTION_ICONS.get(self.action, ('fa-circle-info', 'edit'))[1]


# ============================================================================
# NOTIFICATION SYSTEM
# ============================================================================

class Notification(models.Model):
    """
    Notification model for sending messages to users.
    
    Supports:
    - Broadcast to all users / all of a role
    - Targeted to specific users
    - Priority levels and categories
    - Read/unread tracking per-user via NotificationRead
    """
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    CATEGORY_CHOICES = [
        ('general', 'General'),
        ('announcement', 'Announcement'),
        ('update', 'System Update'),
        ('maintenance', 'Maintenance'),
        ('alert', 'Alert'),
    ]
    TARGET_CHOICES = [
        ('all', 'All Users'),
        ('super_admin', 'Super Admins'),
        ('operator', 'Admin Staff / Operators'),
        ('prime_manager', 'Prime Managers'),
        ('manager', 'Managers'),
        ('assistant', 'Assistants'),
        ('selected', 'Selected Users'),
    ]
    CATEGORY_ICONS = {
        'general': 'fa-circle-info',
        'announcement': 'fa-bullhorn',
        'update': 'fa-arrow-up-right-dots',
        'maintenance': 'fa-wrench',
        'alert': 'fa-triangle-exclamation',
    }
    PRIORITY_COLORS = {
        'low': '#94a3b8',
        'normal': '#667eea',
        'high': '#f59e0b',
        'urgent': '#ef4444',
    }

    title = models.CharField(max_length=200)
    message = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal', db_index=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='general', db_index=True)
    target = models.CharField(max_length=20, choices=TARGET_CHOICES, default='all')

    # For target='selected', track which users were selected
    target_users = models.ManyToManyField(User, blank=True, related_name='targeted_notifications')

    # Sender
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sent_notifications')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Visibility controls
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at', 'target'], name='notif_time_target_idx'),
            models.Index(fields=['is_active', '-created_at'], name='notif_active_time_idx'),
            models.Index(fields=['is_active', 'expires_at'], name='notif_active_exp_idx'),
        ]

    def __str__(self):
        return f"[{self.get_priority_display()}] {self.title}"

    @property
    def icon_class(self):
        return self.CATEGORY_ICONS.get(self.category, 'fa-circle-info')

    @property
    def priority_color(self):
        return self.PRIORITY_COLORS.get(self.priority, '#667eea')


class NotificationRead(models.Model):
    """
    Tracks which users have read which notifications.
    One row per (user, notification) pair.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notification_reads')
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='reads')
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'notification')
        indexes = [
            models.Index(fields=['user', '-read_at'], name='notifread_user_time_idx'),
        ]

    def __str__(self):
        return f"{self.user} read {self.notification}"


class ClientMessage(models.Model):
    """
    One-way admin/admin-staff message stream per client.

    Messages are delivered through Notification records so recipients can
    dismiss/read them globally while preserving sender history in Manage Clients.
    """
    SCOPE_CHOICES = [
        ('client_only', 'Client Only'),
        ('client_and_staff', 'Client + Staff'),
    ]
    VISIBILITY_CHOICES = [
        ('permanent', 'Permanent'),
        ('temporary', 'Temporary'),
    ]

    client = models.ForeignKey('core.Organisation', on_delete=models.CASCADE, related_name='org_messages')
    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sent_client_messages')
    message = models.TextField()
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='client_only', db_index=True)
    visibility = models.CharField(
        max_length=12,
        choices=VISIBILITY_CHOICES,
        default='permanent',
        db_index=True,
    )
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    notification = models.OneToOneField(
        Notification,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='client_message',
    )
    recipient_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', '-created_at'], name='climsg_client_time_idx'),
            models.Index(fields=['scope', '-created_at'], name='climsg_scope_time_idx'),
            models.Index(fields=['visibility', 'expires_at'], name='climsg_visibility_exp_idx'),
        ]

    def __str__(self):
        return f"OrgMessage(organisation={self.client_id}, scope={self.scope})"

    @property
    def is_temporary(self):
        return self.visibility == 'temporary'

    @property
    def is_expired(self):
        if not self.is_temporary or not self.expires_at:
            return False
        from django.utils import timezone
        return self.expires_at <= timezone.now()


class BackgroundTask(models.Model):
    """
    Tracks background tasks for async processing.
    
    CRITICAL: Only ONE heavy task per user at a time to prevent RAM exhaustion.
    """
    TASK_TYPES = [
        ("bulk_upload", "Bulk Upload"),
        ("reupload_images", "Reupload Images"),
        ("export_zip", "Export Zip"),
        ("export_pdf", "Export PDF"),
        ("export_docx", "Export DOCX"),
        ("export_excel", "Export Excel"),
    ]
    
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='background_tasks'
    )
    task_type = models.CharField(max_length=30, choices=TASK_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    
    # Progress tracking
    progress = models.IntegerField(default=0)
    total = models.IntegerField(default=0)
    
    # File paths (relative to MEDIA_ROOT)
    file_path = models.CharField(max_length=500, blank=True, null=True)  # Input file
    result_path = models.CharField(max_length=500, blank=True, null=True)  # Output file
    
    # Additional metadata stored as JSON
    metadata = models.JSONField(default=dict, blank=True)
    
    # Error message if failed
    error_message = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['task_type', 'status']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['completed_at']),
        ]
    
    def __str__(self):
        return f"{self.get_task_type_display()} - {self.get_status_display()} ({self.progress}/{self.total})"
    
    @property
    def progress_percentage(self):
        """Get progress as percentage (0-100)"""
        if self.total <= 0:
            return 0
        return min(100, int((self.progress / self.total) * 100))
    
    @property
    def is_active(self):
        """Check if task is currently running"""
        return self.status in ("pending", "processing")
    
    @property
    def is_done(self):
        """Check if task has finished (completed, failed, or cancelled)"""
        return self.status in ("completed", "failed", "cancelled")
    
    def cleanup_files(self):
        """
        Remove temporary files associated with this task.
        Call this after task completion or on failure.
        
        Cleans up:
        - Main input file (file_path)
        - Field-specific ZIP files (metadata['zip_paths'])
        - Unified ZIP files (metadata['unified_zip_paths'])
        """
        import os
        import logging
        from django.conf import settings
        
        logger = logging.getLogger(__name__)
        
        def safe_delete(file_path):
            """Safely delete a file by relative or absolute path."""
            if not file_path:
                return
            try:
                # Convert relative path to absolute if needed
                if not os.path.isabs(file_path):
                    full_path = os.path.join(settings.MEDIA_ROOT, file_path)
                else:
                    full_path = file_path
                
                if os.path.exists(full_path):
                    os.remove(full_path)
                    logger.info("Cleaned up file: %s", file_path)
            except Exception as e:
                logger.warning("Failed to cleanup file %s: %s", file_path, e)
        
        # Cleanup main input file
        if self.file_path:
            safe_delete(self.file_path)
        
        # Cleanup ZIP files from metadata
        metadata = self.metadata or {}
        
        # Field-specific ZIPs: {'field_name': 'relative/path.zip', ...}
        zip_paths = metadata.get('zip_paths', {})
        for field_name, zip_path in zip_paths.items():
            safe_delete(zip_path)
        
        # Unified ZIPs: ['relative/path1.zip', 'relative/path2.zip', ...]
        unified_zip_paths = metadata.get('unified_zip_paths', [])
        for zip_path in unified_zip_paths:
            safe_delete(zip_path)
    
    def mark_started(self):
        """Mark task as started processing.
        Uses atomic conditional update to prevent double-start races.
        """
        from django.utils import timezone
        from django.db import transaction
        with transaction.atomic():
            updated = type(self).objects.filter(
                pk=self.pk, status='pending'
            ).update(status='processing', started_at=timezone.now())
            if updated == 0:
                raise RuntimeError(
                    f'Task {self.pk} is no longer pending (current status may have changed)'
                )
        self.refresh_from_db(fields=['status', 'started_at'])
    
    def mark_completed(self, result_path=None):
        """Mark task as successfully completed"""
        from django.utils import timezone
        self.status = "completed"
        self.completed_at = timezone.now()
        if result_path:
            self.result_path = result_path
        self.save(update_fields=["status", "completed_at", "result_path", "updated_at"])
    
    def mark_failed(self, error_message):
        """Mark task as failed with error message"""
        from django.utils import timezone
        self.status = "failed"
        self.error_message = str(error_message)[:2000]  # Truncate long errors
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "error_message", "completed_at", "updated_at"])
        self.cleanup_files()
        try:
            if self.task_type in ("export_zip", "export_pdf", "export_docx", "export_excel"):
                from core.services.activity_service import ActivityService
                from tables.models import Table

                table_id = None
                table_name = ''
                metadata = self.metadata or {}
                if isinstance(metadata, dict):
                    table_id = metadata.get('table_id')
                if table_id:
                    table_name = (
                        Table.objects.filter(id=table_id)
                        .values_list('name', flat=True)
                        .first()
                    ) or ''

                ActivityService.log_export_failed(
                    request=None,
                    user=self.user,
                    export_type=self.task_type,
                    message=self.error_message,
                    table_id=table_id,
                    table_name=table_name,
                    source='async',
                )
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Failed to log export failure activity')
    
    def update_progress(self, progress, total=None):
        """Update progress counter efficiently"""
        update_fields = ["progress", "updated_at"]
        if total is not None:
            try:
                total = int(total)
            except (TypeError, ValueError):
                total = None
        try:
            progress = int(progress)
        except (TypeError, ValueError):
            progress = 0

        if total is not None and total > 0:
            progress = max(0, min(progress, total))
        else:
            progress = max(0, progress)

        self.progress = progress
        if total is not None:
            self.total = total
            update_fields.append("total")
        self.save(update_fields=update_fields)
    
    @classmethod
    def has_active_task(cls, user, task_type=None):
        """
        Check if user has an active (pending/processing) task.
        Used to prevent multiple concurrent heavy operations.
        
        Args:
            user: User instance
            task_type: Optional task type to filter by
            
        Returns:
            BackgroundTask instance if active task exists, None otherwise
        """
        qs = cls.objects.filter(user=user, status__in=["pending", "processing"])
        if task_type:
            qs = qs.filter(task_type=task_type)
        return qs.first()
    
    @classmethod
    def create_if_no_active(cls, user, task_type, **kwargs):
        """
        Atomically create a task only if user is within active task slot limits
        AND the system-wide queue is not full.
        
        Args:
            user: User instance
            task_type: Task type string
            **kwargs: Additional fields for BackgroundTask
            
        Returns:
            tuple: (task, error_message) - task is None if creation failed
        """
        from django.db import transaction
        
        MAX_QUEUED_TASKS = 10  # system-wide limit
        
        with transaction.atomic():
            # Lock the user's active tasks for update
            active_qs = cls.objects.select_for_update().filter(
                user=user,
                status__in=["pending", "processing"]
            ).order_by('-created_at', '-id')

            active_count = active_qs.count()
            active = active_qs.first()

            allowed_slots = 1
            try:

                allowed_slots = 1
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Failed resolving Super Mode task slot allowance for user=%s', getattr(user, 'id', None))

            if active_count >= allowed_slots:
                if allowed_slots <= 1 and active is not None:
                    return None, f"You already have an active task ({active.get_task_type_display()}). Please wait for it to complete."
                return None, (
                    f"You already have {active_count} active task(s). "
                    f"Your current limit is {allowed_slots}. Please wait for one to finish."
                )
            
            # Check system-wide queue depth
            pending_count = cls.objects.filter(
                status__in=["pending", "processing"]
            ).count()
            if pending_count >= MAX_QUEUED_TASKS:
                return None, f"System is busy ({pending_count} tasks queued). Please try again later."
            
            # Safe to create new task
            task = cls.objects.create(
                user=user,
                task_type=task_type,
                status='pending',
                **kwargs
            )
            return task, None
    
    @classmethod
    def cleanup_stale_tasks(cls, hours=24):
        """
        Mark stale tasks (stuck in processing for too long) as failed.
        Should be called periodically (e.g., on server startup).
        
        Args:
            hours: Number of hours after which a processing task is considered stale
        """
        import logging
        from django.utils import timezone
        from datetime import timedelta
        
        logger = logging.getLogger(__name__)
        stale_threshold = timezone.now() - timedelta(hours=hours)
        stale_tasks = cls.objects.filter(
            status="processing",
            started_at__lt=stale_threshold
        )
        
        count = 0
        for task in stale_tasks:
            task.mark_failed(f"Task timed out after {hours} hours")
            count += 1
        
        if count:
            logger.info("Cleaned up %d stale background tasks", count)
        
        return count
    
    @classmethod
    def cleanup_old_results(cls, days=7):
        """
        Delete old completed task records and their result files.
        Should be called periodically.
        
        Args:
            days: Number of days to keep completed tasks
        """
        import logging
        from django.conf import settings
        from django.utils import timezone
        from datetime import timedelta
        from django.core.files.storage import default_storage
        
        logger = logging.getLogger(__name__)
        min_days = max(int(getattr(settings, 'BACKGROUND_TASK_RESULT_MIN_RETENTION_DAYS', 7) or 7), 1)
        try:
            requested_days = int(days)
        except (TypeError, ValueError):
            requested_days = min_days
        safe_days = max(requested_days, min_days)

        if safe_days != requested_days:
            logger.warning(
                "BackgroundTask.cleanup_old_results days=%s below minimum=%s; clamped to %s",
                requested_days,
                min_days,
                safe_days,
            )

        old_threshold = timezone.now() - timedelta(days=safe_days)
        old_tasks = cls.objects.filter(
            status__in=["completed", "failed", "cancelled"],
            completed_at__lt=old_threshold
        )
        
        count = 0
        for task in old_tasks:
            # Clean up result file if exists
            if task.result_path:
                try:
                    if default_storage.exists(task.result_path):
                        default_storage.delete(task.result_path)
                except Exception as e:
                    logger.warning("Failed to cleanup result file %s: %s", task.result_path, e)
            
            task.delete()
            count += 1
        
        if count:
            logger.info("Cleaned up %d old background task records", count)
        
        return count




# ═══════════════════════════════════════════════════════════════════════════
#  Backup System — Tracks client data backup requests
# ═══════════════════════════════════════════════════════════════════════════

class BackupTask(models.Model):
    """
    Tracks a backup request that exports client data as a single combined ZIP.

    Lifecycle:
        1. Super admin enters 10-digit code → BackupTask created (pending)
        2. Selects schools → task starts processing in background thread
        3. One combined "Adarsh Backup {date}.zip" created with per-school folders
           (XLSX per status + images/ folder inside each school folder)
        4. On completion → auto_delete_at set to 24 hrs from now;
           ZIP is deleted automatically after 24 hrs
        5. Admin can cancel auto-delete or trigger immediate file deletion;
           history record (BackupTask) is always kept for audit purposes
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),           # Created, awaiting client selection
        ('processing', 'Processing'),     # Background thread running
        ('completed', 'Completed'),       # All ZIPs ready for download
        ('failed', 'Failed'),             # Error during processing
        ('deleted', 'Deleted'),           # Files manually or auto-deleted
    ]

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='backup_tasks',
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True,
    )

    # 10-digit confirmation code (verified on creation & destructive actions)
    confirmation_code = models.CharField(max_length=10)

    # Which clients are included (list of client IDs)
    client_ids = models.JSONField(default=list, blank=True)

    # Human-readable client names snapshot (for display after clients may be deleted)
    client_names = models.JSONField(default=dict, blank=True)

    # Progress tracking
    progress = models.IntegerField(default=0, help_text='Number of clients processed')
    total = models.IntegerField(default=0, help_text='Total number of clients to process')
    current_client = models.CharField(max_length=200, blank=True, default='')

    # Generated ZIP file (relative to MEDIA_ROOT).
    # Format: { "combined": {"path": "...", "filename": "...", "size": 12345} }
    # A single combined ZIP named "Adarsh Backup {date}.zip" containing all
    # selected schools as sub-folders.
    zip_files = models.JSONField(default=dict, blank=True)

    # Auto-delete timer
    auto_delete_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the backup files will be automatically deleted',
    )
    is_auto_delete_cancelled = models.BooleanField(default=False)

    # Error info
    error_message = models.TextField(blank=True, default='')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['auto_delete_at']),
        ]
        verbose_name = 'Backup Task'
        verbose_name_plural = 'Backup Tasks'

    def __str__(self):
        return f"Backup #{self.pk} — {self.get_status_display()} ({self.progress}/{self.total})"

    @property
    def progress_percentage(self):
        if self.total <= 0:
            return 0
        return min(100, int((self.progress / self.total) * 100))

    @property
    def is_active(self):
        return self.status in ('pending', 'processing')

    @property
    def time_remaining_seconds(self):
        """Seconds until auto-delete (None if cancelled or no timer)."""
        if self.is_auto_delete_cancelled or not self.auto_delete_at:
            return None
        from django.utils import timezone
        delta = (self.auto_delete_at - timezone.now()).total_seconds()
        return max(0, int(delta))

    def cleanup_files(self):
        """Delete all generated ZIP files from disk."""
        import os
        from django.conf import settings as _s
        for cid, info in (self.zip_files or {}).items():
            fpath = info.get('path', '')
            if not fpath:
                continue
            full = os.path.join(_s.MEDIA_ROOT, fpath) if not os.path.isabs(fpath) else fpath
            try:
                if os.path.exists(full):
                    os.remove(full)
            except Exception:
                pass
        # Also try to remove the backup directory
        backup_dir = os.path.join(_s.MEDIA_ROOT, 'temp', 'backups', str(self.pk))
        try:
            if os.path.isdir(backup_dir):
                import shutil
                shutil.rmtree(backup_dir, ignore_errors=True)
        except Exception:
            pass


# =============================================================================
# EMAIL LOG
# =============================================================================

class EmailLog(models.Model):
    """
    Log record for every outbound email.
    status values:
      on_hold  – created but not sent (account not yet activated)
      pending  – queued but not yet delivered
      sent     – successfully delivered
      failed   – delivery attempt failed
    """
    STATUS_ON_HOLD = 'on_hold'
    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_ON_HOLD, 'On Hold'),
        (STATUS_PENDING, 'Pending'),
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
    ]

    EMAIL_TYPE_WELCOME = 'welcome'
    EMAIL_TYPE_TEMP_PASSWORD = 'temp_password'
    EMAIL_TYPE_PASSWORD_CHANGE = 'password_change'
    EMAIL_TYPE_OTP_RESET = 'otp_reset'
    EMAIL_TYPE_SYSTEM = 'system'

    TYPE_CHOICES = [
        (EMAIL_TYPE_WELCOME, 'Welcome / Activation'),
        (EMAIL_TYPE_TEMP_PASSWORD, 'Temp Password'),
        (EMAIL_TYPE_PASSWORD_CHANGE, 'Password Change Notice'),
        (EMAIL_TYPE_OTP_RESET, 'Password Reset OTP'),
        (EMAIL_TYPE_SYSTEM, 'System / Custom'),
    ]

    recipient_name = models.CharField(max_length=200)
    recipient_email = models.EmailField(db_index=True)
    subject = models.CharField(max_length=300)
    body_text = models.TextField(blank=True, default='')
    body_html = models.TextField(blank=True, default='')
    email_type = models.CharField(max_length=30, choices=TYPE_CHOICES, db_index=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES,
        default=STATUS_PENDING, db_index=True
    )
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Email Log'
        verbose_name_plural = 'Email Logs'

    def __str__(self):
        return f'[{self.status}] {self.email_type} → {self.recipient_email}'


class ClientPresenceSession(models.Model):
    """
    Tracks per-tab presence for client/client_staff sessions.

    A row remains "live" while:
    - closed_at is NULL
    - last_seen_at is within the configured live window
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='presence_sessions',
        db_index=True,
    )
    client = models.ForeignKey(
        'core.Organisation',
        on_delete=models.CASCADE,
        related_name='presence_sessions',
        db_index=True,
    )
    session_key = models.CharField(max_length=64, db_index=True)
    tab_id = models.CharField(max_length=80, db_index=True)
    user_role = models.CharField(max_length=20, blank=True, default='', db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = 'Organisation Presence Session'
        verbose_name_plural = 'Organisation Presence Sessions'
        unique_together = ('session_key', 'tab_id')
        indexes = [
            models.Index(fields=['client', 'closed_at', 'last_seen_at'], name='clpres_client_live_idx'),
            models.Index(fields=['user', 'closed_at', 'last_seen_at'], name='clpres_user_live_idx'),
            models.Index(fields=['closed_at', 'last_seen_at'], name='clpres_closed_seen_idx'),
        ]

    def __str__(self):
        state = 'closed' if self.closed_at else 'live'
        return f'Presence(user={self.user_id}, client={self.client_id}, tab={self.tab_id}, {state})'


class Photographer(models.Model):
    """
    Photographer profile model
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='photographer_profile')
    department = models.CharField(max_length=100, blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True, null=True)
    
    # Photographer-specific permissions mapped directly
    perm_idcard_pending_list = models.BooleanField(default=False)
    perm_idcard_verified_list = models.BooleanField(default=False)
    perm_idcard_add = models.BooleanField(default=False)
    perm_idcard_info = models.BooleanField(default=False)
    perm_mobile_app = models.BooleanField(default=True)
    perm_idcard_bulk_download = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Photographer"
        verbose_name_plural = "Photographers"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - Photographer"

    @property
    def active_assignments(self):
        from django.utils import timezone
        from django.db.models import Q
        return self.photographer_assignments.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        )


class PhotographerAssignment(models.Model):
    photographer = models.ForeignKey(Photographer, on_delete=models.CASCADE, related_name='photographer_assignments')
    client = models.ForeignKey('core.Organisation', on_delete=models.CASCADE, related_name='photographer_assignments')
    expires_at = models.DateTimeField(null=True, blank=True)
    # Specific table IDs this photographer can see for this client.
    # Empty list = all tables are accessible (default / unrestricted).
    allowed_table_ids = models.JSONField(
        default=list,
        blank=True,
        help_text='Table IDs this photographer can see for this client. Empty = all tables.'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('photographer', 'client')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.photographer.user.get_full_name()} -> {self.client.name}"

    @property
    def is_expired(self):
        from django.utils import timezone
        if self.expires_at:
            return self.expires_at <= timezone.now()
        return False

