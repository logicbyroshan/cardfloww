"""
Reprint URL Configuration
=========================
Routes for the 3-step reprint workflow:
  1. Reprint List -> 2. Requested List -> 3. Confirmed List
"""
from django.urls import path
from . import views

app_name = 'reprint'

urlpatterns = [
    # Step counts
    path('api/table/<int:table_id>/step-counts/', views.api_reprint_step_counts, name='api_reprint_step_counts'),

    # Step 1: Reprint List (Downloaded source cards)
    path('api/table/<int:table_id>/reprint-list/', views.api_reprint_list, name='api_reprint_list'),
    path('api/table/<int:table_id>/request/', views.api_reprint_request_create, name='api_reprint_request_create'),

    # Step 2: Requested List
    path('api/table/<int:table_id>/request-list/', views.api_request_list, name='api_request_list'),
    path('api/table/<int:table_id>/confirm/', views.api_reprint_confirm, name='api_reprint_confirm'),
    path('api/table/<int:table_id>/reject/', views.api_reprint_reject, name='api_reprint_reject'),

    # Step 3: Confirmed List
    path('api/table/<int:table_id>/confirmed-list/', views.api_confirmed_list, name='api_confirmed_list'),
    path('api/table/<int:table_id>/retrieve/', views.api_reprint_retrieve, name='api_reprint_retrieve'),
    path('api/table/<int:table_id>/mark-downloaded/', views.api_reprint_mark_downloaded, name='api_reprint_mark_downloaded'),

    # Card specific history
    path('api/card/<int:card_id>/history/', views.api_reprint_card_history, name='api_reprint_card_history'),
]
