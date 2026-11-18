from django.conf import settings
from django.core.cache import cache
from rest_framework.throttling import BaseThrottle

from .security.client_ip import get_client_ip
from .security.ratelimit import RateLimiter


class BurstThrottle(BaseThrottle):
    """At most `limit` requests per `window` seconds per user (per IP if anonymous)."""

    scope = "burst"
    limit = 20
    window = 60

    def allow_request(self, request, view):
        if request.user and request.user.is_authenticated:
            identity = f"user:{request.user.pk}"
        else:
            ip = get_client_ip(
                request.META, trusted_proxies=settings.TRUSTED_PROXY_COUNT
            )
            identity = f"ip:{ip or 'unknown'}"
        self.result = RateLimiter(cache).hit(
            self.scope, identity, limit=self.limit, window=self.window
        )
        return self.result.allowed

    def wait(self):
        # DRF turns this into the Retry-After header of the 429 response
        return self.result.retry_after or None


class ChatBurstThrottle(BurstThrottle):
    scope = "chat_burst"
    limit = 10   # plenty for a person, far too slow for a script
    window = 60
