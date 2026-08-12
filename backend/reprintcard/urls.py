"""
Reprint Card URL Configuration
================================
Reprint List (all IDCards) → Confirmed List → Print
"""
from django.urls import path
from . import views

app_name = 'reprintcard'

urlpatterns = [
    # Page view
    path('table/<int:table_id>/', views.reprint_cards, name='reprint_cards'),

    # API endpoints
    path('api/table/<int:table_id>/request/', views.api_reprint_request_create, name='api_reprint_request_create'),
    path('api/table/<int:table_id>/request-list/', views.api_request_list, name='api_request_list'),
    path('api/table/<int:table_id>/step-counts/', views.api_reprint_step_counts, name='api_reprint_step_counts'),
    path('api/table/<int:table_id>/reprint-list/', views.api_reprint_list, name='api_reprint_list'),
    path('api/table/<int:table_id>/confirm/', views.api_reprint_confirm, name='api_reprint_confirm'),
    path('api/table/<int:table_id>/retrieve/', views.api_reprint_retrieve, name='api_reprint_retrieve'),
    path('api/table/<int:table_id>/reject/', views.api_reprint_reject, name='api_reprint_reject'),
    path('api/table/<int:table_id>/confirmed-list/', views.api_confirmed_list, name='api_confirmed_list'),
    path('api/table/<int:table_id>/mark-downloaded/', views.api_reprint_mark_downloaded, name='api_reprint_mark_downloaded'),
    path('api/table/<int:table_id>/download-list/', views.api_download_list, name='api_download_list'),
    path('api/table/<int:table_id>/send-to-print/', views.api_reprint_send_to_print, name='api_reprint_send_to_print'),
]
