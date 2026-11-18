"""The only file that talks to Stripe. Everything else works with plain dictionaries.

Needs: pip install "stripe>=16" (the SDK pins the API version, section 36.2). Not executed in this
chapter's tests (no network and no keys when it was written); the tests use FakeGateway instead.
"""
from typing import Optional


def _plain(obj) -> dict:
    """Stripe SDK objects behave like dictionaries; return a plain dict for our code."""
    return obj.to_dict() if hasattr(obj, "to_dict") else dict(obj)


class StripeGateway:
    def __init__(self, api_key: str):
        if not api_key.startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_")):
            raise ValueError("Use a secret key (sk_...) or a restricted key (rk_...) on the server.")
        from stripe import StripeClient  # imported here so the rest of the package needs no SDK

        self.client = StripeClient(api_key)

    def create_customer(self, *, email: str, name: str, metadata: dict, idempotency_key: str) -> dict:
        return _plain(self.client.v1.customers.create(
            params={"email": email, "name": name, "metadata": metadata},
            options={"idempotency_key": idempotency_key}))

    def create_checkout_session(self, params: dict, idempotency_key: str) -> dict:
        return _plain(self.client.v1.checkout.sessions.create(
            params=params, options={"idempotency_key": idempotency_key}))

    def retrieve_checkout_session(self, session_id: str) -> dict:
        return _plain(self.client.v1.checkout.sessions.retrieve(
            session_id, params={"expand": ["subscription"]}))

    def create_portal_session(self, params: dict) -> dict:
        return _plain(self.client.v1.billing_portal.sessions.create(params=params))

    def retrieve_subscription(self, subscription_id: str) -> dict:
        return _plain(self.client.v1.subscriptions.retrieve(subscription_id))

    def update_subscription(self, subscription_id: str, params: dict, idempotency_key: str) -> dict:
        return _plain(self.client.v1.subscriptions.update(
            subscription_id, params=params, options={"idempotency_key": idempotency_key}))

    def cancel_subscription(self, subscription_id: str) -> dict:
        return _plain(self.client.v1.subscriptions.cancel(subscription_id))

    def retrieve_event(self, event_id: str) -> dict:
        return _plain(self.client.v1.events.retrieve(event_id))

    def create_payment_intent(self, params: dict, idempotency_key: str) -> dict:
        return _plain(self.client.v1.payment_intents.create(
            params=params, options={"idempotency_key": idempotency_key}))

    def create_ephemeral_key(self, customer_id: str, stripe_version: str) -> dict:
        """The mobile SDK needs a short-lived key. It must be created with the API version the SDK uses."""
        return _plain(self.client.v1.ephemeral_keys.create(
            params={"customer": customer_id}, options={"stripe_version": stripe_version}))
