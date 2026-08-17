from django.urls import path
from . import views

urlpatterns = [
    path('api/imports/preview/', views.api_preview_import_data, name='api_imports_preview'),
    path('api/group/<int:group_id>/table/create-with-data/', views.api_create_table_with_data, name='api_create_table_with_data'),
    path('api/group/<int:group_id>/table/create-from-xlsx/', views.api_create_table_with_data, name='api_create_table_from_xlsx_alias'),
    path('api/table/<int:table_id>/cards/bulk-upload/', views.api_bulk_upload_data, name='api_bulk_upload_data'),
    path('api/table/<int:table_id>/cards/reupload-images/', views.api_reupload_images, name='api_reupload_images'),
]
