from django.conf import settings

from .base import PaymentGateway
from .paystack_gateway import PaystackGateway
from .stripe_gateway import StripeGateway

_FACTORIES = {"stripe": StripeGateway, "paystack": PaystackGateway}


class UnknownGateway(Exception):
    pass


def get_gateway(code: str) -> PaymentGateway:
    """Only gateways switched on in settings are available. Turning Stripe off is a config change."""
    if code not in _FACTORIES or code not in settings.BILLING_GATEWAYS_ENABLED:
        raise UnknownGateway(code)
    return _FACTORIES[code]()
