"""Builds the billing objects once, from Django settings."""
import logging
from functools import lru_cache

from django.conf import settings

from paystackbilling.config import PaystackConfig, Plan
from paystackbilling.gateway import PaystackGateway
from paystackbilling.handlers import PaystackHandlers
from paystackbilling.money import to_subunit
from paystackbilling.service import PaystackBillingService
from paystackbilling.webhooks import PaystackVerifier, WebhookProcessor

from .store import DjangoBillingStore

log = logging.getLogger("billing")


def livemode() -> bool:
    return settings.PAYSTACK_SECRET_KEY.startswith("sk_live_")       # the key decides the mode


@lru_cache(maxsize=1)
def get_config() -> PaystackConfig:
    plans = {}
    for key, v in settings.PAYSTACK_PLANS.items():
        plans[key] = Plan(key=key, tier=v["tier"], interval=v["interval"], currency=v["currency"],
                          amount=to_subunit(v["amount"], v["currency"]),     # settings hold 5000, not 500000
                          plan_code=v.get("plan_code", ""), credits=v.get("credits", 0), trial_days=v.get("trial_days", 0))
    return PaystackConfig(plans=plans, livemode=livemode(), callback_url=settings.PAYSTACK_CALLBACK_URL,
                          allowed_hosts=frozenset(settings.PAYSTACK_ALLOWED_HOSTS), grace_days=settings.BILLING_GRACE_DAYS)


def notify(kind: str, user_id, **details) -> None:
    log.info("billing_notice kind=%s user=%s", kind, user_id)
    # send_billing_email.delay(kind, user_id, details)    <- your Celery task from Chapter 15


@lru_cache(maxsize=1)
def get_gateway() -> PaystackGateway:
    return PaystackGateway(settings.PAYSTACK_SECRET_KEY)


@lru_cache(maxsize=1)
def get_service() -> PaystackBillingService:
    return PaystackBillingService(get_gateway(), DjangoBillingStore(), get_config(), notify=notify)


@lru_cache(maxsize=1)
def get_processor() -> WebhookProcessor:
    store = DjangoBillingStore()
    handlers = PaystackHandlers(store, get_config(), get_gateway(), notify)
    return WebhookProcessor(PaystackVerifier(settings.PAYSTACK_SECRET_KEY), store, handlers.table(),
                            livemode=livemode(), log=log.warning)
