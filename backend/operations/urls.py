from django.urls import path
from .views import UndoView, RedoView, StackStatusView, OperationHistoryView

app_name = 'operations'

urlpatterns = [
    path('undo/', UndoView.as_view(), name='undo'),
    path('redo/', RedoView.as_view(), name='redo'),
    path('stack/', StackStatusView.as_view(), name='stack_status'),
    path('history/', OperationHistoryView.as_view(), name='history'),
]
