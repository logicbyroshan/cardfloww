from django.urls import path

from . import views

app_name = 'desktop_app'

urlpatterns = [
    path('register/', views.register_device, name='register_device'),
    path('revoke/', views.revoke_device, name='revoke_device'),
    path('status/', views.status, name='status'),
    path('clients/', views.clients_manifest, name='clients_manifest'),
    path('export/', views.export_archive, name='export_archive'),
    path('export-images/', views.export_images, name='export_images'),
    path('download/<path:file_path>/', views.download_original_file, name='download_original_file'),
]
