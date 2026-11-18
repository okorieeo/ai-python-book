"""Building the parameters for Paystack calls as plain dictionaries, so tests can check every one.

Rules these builders enforce: the amount and plan always come from OUR plan table; the amount is a whole
number of the smallest unit; the callback URL must point at a host we allow; every payment has a
reference we created ourselves.
"""
from typing import Optional
from urllib.parse import urlparse

from .errors import BadRedirectUrl


def check_callback_url(url: str, allowed_hosts) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or parsed.hostname not in allowed_hosts:
        raise BadRedirectUrl(f"URL not allowed: {url}")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise BadRedirectUrl("Use https for callback URLs.")
    return url


def initialize_params(*, email: str, amount: int, currency: str, reference: str, callback_url: str,
                      allowed_hosts, user_id: str, plan_key: str, kind: str,
                      plan_code: Optional[str] = None, channels: Optional[list] = None) -> dict:
    """Parameters for POST /transaction/initialize.

    When plan_code is given, Paystack ignores the amount and charges the plan's amount, and subscribes the
    customer to the plan after the first successful payment. Without it, the payment is a one-time charge.
    """
    check_callback_url(callback_url, allowed_hosts)
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ValueError("amount must be a positive whole number of the smallest currency unit")
    params = {
        "email": email,
        "amount": amount,
        "currency": currency,
        "reference": reference,
        "callback_url": callback_url,
        "metadata": {"user_id": str(user_id), "plan_key": plan_key, "kind": kind},
    }
    if plan_code:
        params["plan"] = plan_code
    if channels:
        params["channels"] = list(channels)
    return params


def subscription_params(*, customer_code: str, plan_code: str, authorization_code: str,
                        start_date: Optional[str] = None) -> dict:
    """Parameters for POST /subscription: subscribe an existing customer to a plan with a saved card.

    start_date (ISO 8601 with a timezone) delays the first charge: that is how free trials and plan
    switches at the end of a period work.
    """
    params = {"customer": customer_code, "plan": plan_code, "authorization": authorization_code}
    if start_date:
        params["start_date"] = start_date
    return params
