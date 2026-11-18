"""Builds the billing objects once, from Django settings."""
import logging
from functools import lru_cache

from django.conf import settings

from stripebilling.config import BillingConfig, Plan
from stripebilling.gateway import StripeGateway
from stripebilling.handlers import StripeHandlers
from stripebilling.service import BillingService
from stripebilling.webhooks import ManualVerifier, WebhookProcessor

from .store import DjangoBillingStore

log = logging.getLogger("billing")


def livemode() -> bool:
    """Derived from the secret key, so the key and the mode can never disagree."""
    return settings.STRIPE_SECRET_KEY.startswith(("sk_live_", "rk_live_"))


@lru_cache(maxsize=1)
def get_config() -> BillingConfig:
    plans = {key: Plan(key, **values) for key, values in settings.BILLING_PLANS.items()}
    return BillingConfig(
        plans=plans, livemode=livemode(), success_url=settings.BILLING_SUCCESS_URL,
        cancel_url=settings.BILLING_CANCEL_URL, return_url=settings.BILLING_RETURN_URL,
        allowed_hosts=frozenset(settings.BILLING_ALLOWED_HOSTS), trial_days=settings.BILLING_TRIAL_DAYS,
        grace_days=settings.BILLING_GRACE_DAYS)


def notify(kind: str, user_id, **details) -> None:
    """Tell the user (an email task from Chapter 15) or the team. Details never include card data."""
    log.info("billing_notice kind=%s user=%s", kind, user_id)
    # send_billing_email.delay(kind, user_id, details)   <- your Celery task


@lru_cache(maxsize=1)
def get_service() -> BillingService:
    return BillingService(StripeGateway(settings.STRIPE_SECRET_KEY), DjangoBillingStore(), get_config())


@lru_cache(maxsize=1)
def get_processor() -> WebhookProcessor:
    store, config = DjangoBillingStore(), get_config()
    return WebhookProcessor(
        ManualVerifier(settings.STRIPE_WEBHOOK_SECRETS), store, StripeHandlers(store, config, notify).table(),
        livemode=livemode(), expected_api_version=config.expected_api_version, log=log.warning)
