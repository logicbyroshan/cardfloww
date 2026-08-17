from django.urls import path
from .views import (
    undo_view,
    redo_view,
    stack_status_view,
    history_view,
    card_timeline_view,
    table_activity_view,
    bulk_transactions_list_view,
    bulk_transaction_detail_view,
    reverse_bulk_transaction_view,
    export_audit_view,
)

app_name = 'operations'

urlpatterns = [
    # Undo / Redo Stack
    path('undo/', undo_view, name='undo'),
    path('redo/', redo_view, name='redo'),
    path('stack/', stack_status_view, name='stack_status'),
    path('history/', history_view, name='history'),

    # Audit & Card Timeline
    path('audit/cards/<int:card_id>/timeline/', card_timeline_view, name='card_timeline'),
    path('audit/tables/<int:table_id>/activity/', table_activity_view, name='table_activity'),
    path('audit/transactions/', bulk_transactions_list_view, name='bulk_transactions_list'),
    path('audit/transactions/<int:transaction_id>/', bulk_transaction_detail_view, name='bulk_transaction_detail'),
    path('audit/transactions/<int:transaction_id>/reverse/', reverse_bulk_transaction_view, name='reverse_bulk_transaction'),
    path('audit/export/', export_audit_view, name='export_audit'),
]
