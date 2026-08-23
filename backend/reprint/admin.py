from django.contrib import admin
from .models import ReprintRequest


@admin.register(ReprintRequest)
class ReprintRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'card', 'table', 'status', 'reprint_number', 'requested_by', 'confirmed_by', 'created_at')
    list_filter = ('status', 'table', 'created_at')
    search_fields = ('card__id', 'reason')
    readonly_fields = ('created_at', 'updated_at', 'confirmed_at')
