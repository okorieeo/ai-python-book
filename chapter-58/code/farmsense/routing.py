from django.urls import path

from .consumers import DashboardConsumer

# In asgi.py wrap like the chat routes of Chapter 14: AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns)))
websocket_urlpatterns = [path("ws/farms/<int:farm_id>/live/", DashboardConsumer.as_asgi())]
