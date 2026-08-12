
"""
Django admin integration removed for this project.
This file is intentionally left empty to avoid importing Django's admin.
Use the project's custom panel under `/panel/` instead.
"""

from .models import ReprintRequest


@admin.register(ReprintRequest)
class ReprintRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'card', 'table', 'status', 'reason', 'requested_by', 'created_at', 'updated_at')
    list_filter = ('status', 'table')
    search_fields = ('card__field_data', 'card__id', 'reason')
    raw_id_fields = ('card', 'table', 'requested_by')
    readonly_fields = ('created_at', 'updated_at')
