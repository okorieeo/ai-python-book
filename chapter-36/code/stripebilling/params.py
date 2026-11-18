"""Building the parameters for Stripe calls as plain dictionaries, so tests can check every one.

Rules that these builders enforce:
  * The price always comes from OUR plan table, never from the browser.
  * Redirect URLs must point at hosts we allow.
  * We never send payment_method_types: current API versions removed it from Checkout, and payment
    methods are managed in the Dashboard.
"""
import hashlib
from typing import Optional
from urllib.parse import urlparse

from .errors import BadRedirectUrl

CHECKOUT_ID_PLACEHOLDER = "{CHECKOUT_SESSION_ID}"


def idempotency_key(*parts) -> str:
    """A key that is the same for the same request and different for a different one.

    Stripe remembers a key for 24 hours. Sending the same key with the same parameters returns the
    original result instead of doing the work twice, and sending it with different parameters is an
    error, so put everything that changes the request into the key.
    """
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return digest[:40]


def check_redirect_url(url: str, allowed_hosts) -> str:
    parsed = urlparse(url.replace(CHECKOUT_ID_PLACEHOLDER, "x"))
    if parsed.scheme not in {"https", "http"} or parsed.hostname not in allowed_hosts:
        raise BadRedirectUrl(f"URL not allowed: {url}")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise BadRedirectUrl("Use https for redirect URLs.")
    return url


def checkout_params(*, plan, user_id: str, customer_id: Optional[str], email: str, success_url: str,
                    cancel_url: str, allowed_hosts, trial_days: Optional[int] = None,
                    embedded: bool = False, allow_promotion_codes: bool = True) -> dict:
    """Parameters for creating a Checkout Session for one plan."""
    check_redirect_url(success_url, allowed_hosts)
    check_redirect_url(cancel_url, allowed_hosts)
    subscribing = plan.interval != "once"
    params = {
        "mode": "subscription" if subscribing else "payment",
        "line_items": [{"price": plan.price_id, "quantity": 1}],
        "client_reference_id": str(user_id),
        "metadata": {"user_id": str(user_id), "plan_key": plan.key},
        "allow_promotion_codes": allow_promotion_codes,
    }
    if embedded:
        params["ui_mode"] = "embedded_page"
        params["return_url"] = success_url          # cancel_url is not allowed with embedded checkout
    else:
        params["success_url"] = success_url          # the default ui_mode is "hosted_page"
        params["cancel_url"] = cancel_url
    if customer_id:
        params["customer"] = customer_id
    elif not subscribing:
        params["customer_email"] = email
    if subscribing:
        # Copy the user id onto the subscription itself, so subscription events can find the user.
        params["subscription_data"] = {"metadata": {"user_id": str(user_id), "plan_key": plan.key}}
        if trial_days:
            params["subscription_data"]["trial_period_days"] = int(trial_days)
            params["payment_method_collection"] = "always"      # collect a card at the start of the trial
    return params


def portal_params(customer_id: str, return_url: str, allowed_hosts) -> dict:
    check_redirect_url(return_url, allowed_hosts)
    return {"customer": customer_id, "return_url": return_url}


def plan_change_params(*, item_id: str, new_price_id: str, direction: str) -> dict:
    """Parameters for switching a subscription to another price.

    direction "up": invoice the prorated difference right away, so the upgrade is paid for now.
    direction "down" or "same": add a credit or charge to the next invoice.
    error_if_incomplete: if the payment for the change fails, the change does not happen.
    """
    proration = "always_invoice" if direction == "up" else "create_prorations"
    return {
        "items": [{"id": item_id, "price": new_price_id}],
        "proration_behavior": proration,
        "payment_behavior": "error_if_incomplete",
    }


def cancel_params(at_period_end: bool = True) -> dict:
    return {"cancel_at_period_end": bool(at_period_end)}


def payment_intent_params(*, amount: int, currency: str, customer_id: str, user_id: str, description: str,
                          max_amount: int = 100_000) -> dict:
    """Parameters for a PaymentIntent that a mobile Payment Sheet will confirm.

    The amount is decided by the server (from your own catalog), never by the app. It is in the smallest
    currency unit: cents for USD, kobo for NGN.
    """
    if not isinstance(amount, int) or isinstance(amount, bool) or not 0 < amount <= max_amount:
        raise ValueError(f"amount must be a whole number between 1 and {max_amount}")
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must be a three-letter code such as 'usd'")
    return {
        "amount": amount,
        "currency": currency.lower(),
        "customer": customer_id,
        "description": description[:200],
        "automatic_payment_methods": {"enabled": True},
        "metadata": {"user_id": str(user_id)},
    }
