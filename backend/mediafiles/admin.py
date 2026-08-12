
"""
Django admin integration removed for this project.
This file is intentionally left empty to avoid importing Django's admin.
Use the project's custom panel under `/panel/` instead.
"""
from django.utils.html import format_html
from .models import CardMedia


@admin.register(CardMedia)
class CardMediaAdmin(admin.ModelAdmin):
    """
    Admin interface for CardMedia model.
    Provides easy browsing and management of media files.
    """
    list_display = [
        'id',
        'media_type',
        'client',
        'card',
        'group',
        'original_filename',
        'thumbnail_preview',
        'uploaded_by',
        'is_migrated',
        'created_at',
    ]
    list_filter = [
        'media_type',
        'is_migrated',
        'created_at',
        'client',
    ]
    search_fields = [
        'original_filename',
        'field_name',
        'legacy_path',
        'client__name',
    ]
    readonly_fields = [
        'thumbnail_preview_large',
        'created_at',
        'updated_at',
    ]
    raw_id_fields = ['card', 'group', 'client', 'uploaded_by']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Relationships', {
            'fields': ('client', 'card', 'group')
        }),
        ('Media', {
            'fields': ('file', 'thumbnail_preview_large', 'media_type', 'field_name')
        }),
        ('Metadata', {
            'fields': ('original_filename', 'uploaded_by')
        }),
        ('Migration Tracking', {
            'fields': ('is_migrated', 'legacy_path'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def thumbnail_preview(self, obj):
        """Small thumbnail for list view"""
        if obj.file:
            return format_html(
                '<img src="{}" style="max-height: 40px; max-width: 60px; object-fit: contain;"/>',
                obj.file.url
            )
        return '-'
    thumbnail_preview.short_description = 'Preview'
    
    def thumbnail_preview_large(self, obj):
        """Larger preview for detail view"""
        if obj.file:
            return format_html(
                '<img src="{}" style="max-height: 200px; max-width: 300px; object-fit: contain;"/>',
                obj.file.url
            )
        return '-'
    thumbnail_preview_large.short_description = 'Image Preview'
