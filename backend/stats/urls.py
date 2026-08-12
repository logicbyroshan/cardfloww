from django.urls import path
from . import views

urlpatterns = [
    path('', views.statistics_page, name='pro_user_statistics'),
    path('api/data/', views.api_statistics_data, name='api_statistics_data'),
    path('api/check-load/', views.api_check_server_load, name='api_check_server_load'),
]
