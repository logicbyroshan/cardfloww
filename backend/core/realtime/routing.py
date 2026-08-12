from django.urls import path

from .consumers import RealtimeHubConsumer

websocket_urlpatterns = [
    path('ws/panel/realtime/', RealtimeHubConsumer.as_asgi()),
]
