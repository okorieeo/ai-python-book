from django.urls import path

from .consumers import AskConsumer

# In asgi.py wrap these like the chat routes of Chapter 14:
#   AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns)))
websocket_urlpatterns = [path("ws/ask/", AskConsumer.as_asgi())]
