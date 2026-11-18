"""Errors raised by the Paystack billing code."""


class BillingError(Exception):
    """Base class for every billing error."""


class UnknownPlan(BillingError):
    """The plan key is not in the server's plan table. Never trust a price or plan code from the browser."""


class AlreadySubscribed(BillingError):
    """The user already has a subscription that is running or about to run."""


class NoSubscription(BillingError):
    """The user has no subscription to cancel, resume or change."""


class ForbiddenReference(BillingError):
    """A payment reference that belongs to someone else, or one we never created."""


class BadRedirectUrl(BillingError):
    """A callback URL that points outside the hosts we allow."""


class BadAmount(ValueError):
    """An amount that is not a clean number of major units (no floats, no extra decimals)."""


class SignatureError(BillingError):
    """The webhook signature is missing, malformed or wrong."""


class PaystackApiError(BillingError):
    """Paystack answered, and said no (status false or an HTTP error). Retrying will not help."""

    def __init__(self, message: str, http_status: int = 0):
        super().__init__(message)
        self.http_status = http_status


class PaystackNetworkError(BillingError):
    """We could not reach Paystack, or it timed out. Safe to retry later."""


class UnresolvedCustomer(BillingError):
    """An event refers to a customer we cannot connect to a user yet. Paystack will send it again."""
