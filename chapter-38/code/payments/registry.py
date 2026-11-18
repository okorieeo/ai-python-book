"""Which gateways exist, how they are configured, and the router that chooses between them."""
import time
from functools import lru_cache

from django.conf import settings

from core.payments.routing import GatewayConfig, GatewayRouter, HealthTracker

_health = HealthTracker(clock=time.monotonic)      # per process; see 38.6 for sharing it through Redis


def gateway_configs() -> list[GatewayConfig]:
    return [
        GatewayConfig("stripe", frozenset({"USD", "EUR", "GBP"}), priority=10,
                      enabled=settings.PAYMENT_GATEWAYS.get("stripe", False)),
        GatewayConfig("paystack", frozenset({"NGN", "GHS", "ZAR", "KES", "USD"}),
                      home_countries=frozenset({"NG", "GH", "ZA", "KE"}), priority=20,
                      enabled=settings.PAYMENT_GATEWAYS.get("paystack", False)),
    ]


def get_router() -> GatewayRouter:
    return GatewayRouter(gateway_configs(), _health)


@lru_cache(maxsize=None)
def get_gateways() -> dict:
    from .gateways.paystack_gw import PaystackGateway
    from .gateways.stripe_gw import StripeGateway
    built = {}
    if settings.PAYMENT_GATEWAYS.get("stripe"):
        built["stripe"] = StripeGateway()
    if settings.PAYMENT_GATEWAYS.get("paystack"):
        built["paystack"] = PaystackGateway()
    return built
