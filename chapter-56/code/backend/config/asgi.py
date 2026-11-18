"""ASGI entry point: HTTP goes to Django, WebSockets go to Channels (Chapter 14)."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django_asgi_app = get_asgi_application()  # initialise Django before importing anything that uses models

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from chat.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    # Origin check: a page on another site cannot open a socket for your logged-in user.
    "websocket": AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns)),
})
