from django.urls import path
from . import views

app_name = 'web_app'

urlpatterns = [
    path('clients/', views.api_public_clients_list, name='api_public_clients_list'),
]
