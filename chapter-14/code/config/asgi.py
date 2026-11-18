"""ASGI entry point: plain HTTP goes to Django, WebSockets go to Channels."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django_asgi_app = get_asgi_application()          # must be created BEFORE importing code that uses models

from channels.auth import AuthMiddlewareStack               # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.conf import settings                             # noqa: E402

from chat.routing import websocket_urlpatterns               # noqa: E402
from chat.ws_auth import OptionalOriginValidator, TicketAuthMiddleware   # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": OptionalOriginValidator(                     # reject browsers on unknown websites
        AuthMiddlewareStack(                                  # session cookie -> scope["user"]
            TicketAuthMiddleware(                             # ?ticket=... -> scope["user"] (mobile and Next.js)
                URLRouter(websocket_urlpatterns)
            )
        ),
        settings.WS_ALLOWED_ORIGINS,
    ),
})
