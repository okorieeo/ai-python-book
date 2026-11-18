"""Errors raised by the billing code. Each one says what went wrong in plain words."""


class BillingError(Exception):
    """Base class for every billing error."""


class UnknownPlan(BillingError):
    """The plan key is not in the server's plan table. Never trust a price sent by the browser."""


class AlreadySubscribed(BillingError):
    """The user already has a paid subscription. Send them to the portal or to change_plan."""


class NoCustomer(BillingError):
    """The user has never started a checkout, so there is no Stripe customer to manage."""


class NoSubscription(BillingError):
    """The user has no subscription to change or cancel."""


class ForbiddenSession(BillingError):
    """A checkout session that belongs to someone else, or one that was not made by us."""


class BadRedirectUrl(BillingError):
    """A success, cancel or return URL that points outside the hosts we allow."""


class SignatureError(BillingError):
    """The webhook signature is missing, malformed, wrong or too old."""


class UnresolvedCustomer(BillingError):
    """A Stripe event refers to a customer we cannot connect to a user yet. Stripe will retry."""
