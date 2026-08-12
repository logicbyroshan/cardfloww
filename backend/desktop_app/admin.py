from django.contrib import admin

from .models import DesktopAppDevice


@admin.register(DesktopAppDevice)
class DesktopAppDeviceAdmin(admin.ModelAdmin):
    list_display = ('device_name', 'installation_id', 'is_active', 'last_seen_at', 'last_ip_address', 'created_at')
    list_filter = ('is_active', 'created_at', 'last_seen_at')
    search_fields = ('device_name', 'installation_id', 'token_prefix')
    readonly_fields = ('token_hash', 'token_prefix', 'last_seen_at', 'last_ip_address', 'created_at', 'updated_at', 'revoked_at')
