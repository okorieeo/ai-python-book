from django.conf import settings
from django.core.cache import cache
from rest_framework.throttling import BaseThrottle

from core.security.client_ip import get_client_ip
from core.security.ratelimit import RateLimiter


class ShareCreateThrottle(BaseThrottle):
    """20 links per user per day (AC-8). Only POST counts; listing and revoking are free."""

    def allow_request(self, request, view):
        if request.method != "POST":
            return True
        self.result = RateLimiter(cache).hit("share_create_day", f"user:{request.user.pk}", limit=20, window=86_400)
        return self.result.allowed

    def wait(self):
        return self.result.retry_after or None


class PublicReadThrottle(BaseThrottle):
    """60 reads per minute per client address (AC-8). Anonymous callers have no user to count."""

    def allow_request(self, request, view):
        ip = get_client_ip(request.META, trusted_proxies=settings.TRUSTED_PROXY_COUNT) or "unknown"
        self.result = RateLimiter(cache).hit("share_public_min", f"ip:{ip}", limit=60, window=60)
        return self.result.allowed

    def wait(self):
        return self.result.retry_after or None
