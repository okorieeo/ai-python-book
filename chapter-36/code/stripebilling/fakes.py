"""A fake Stripe for tests: it remembers what it was asked and returns believable objects."""
import itertools

from .fixtures import subscription_obj


class FakeGateway:
    def __init__(self, now: int = 1_800_000_000):
        self.now = now
        self.calls = []
        self._ids = itertools.count(1)
        self.customers = {}
        self.sessions = {}
        self.subscriptions = {}
        self._idem = {}

    def _idempotent(self, name, key, make):
        """Same key returns the same answer, as Stripe does for 24 hours."""
        if key in self._idem:
            self.calls.append((name + ":replayed", key))
            return self._idem[key]
        result = make()
        self._idem[key] = result
        return result

    def create_customer(self, *, email, name, metadata, idempotency_key):
        self.calls.append(("create_customer", email))

        def make():
            cid = f"cus_{next(self._ids):03d}"
            self.customers[cid] = {"id": cid, "email": email, "metadata": metadata}
            return self.customers[cid]
        return self._idempotent("create_customer", idempotency_key, make)

    def create_checkout_session(self, params, idempotency_key):
        self.calls.append(("create_checkout_session", params))

        def make():
            sid = f"cs_test_{next(self._ids):03d}"
            session = {"id": sid, "object": "checkout.session", "url": f"https://checkout.stripe.com/c/pay/{sid}",
                       "mode": params["mode"], "client_reference_id": params["client_reference_id"],
                       "customer": params.get("customer"), "metadata": params["metadata"],
                       "payment_status": "unpaid", "subscription": None, "payment_intent": None}
            if params.get("ui_mode") == "embedded_page":
                session["client_secret"] = f"{sid}_secret_x"
                session["url"] = None
            self.sessions[sid] = session
            return session
        return self._idempotent("create_checkout_session", idempotency_key, make)

    def retrieve_checkout_session(self, session_id):
        self.calls.append(("retrieve_checkout_session", session_id))
        return self.sessions[session_id]

    def create_portal_session(self, params):
        self.calls.append(("create_portal_session", params))
        return {"id": "bps_001", "url": "https://billing.stripe.com/p/session/test_abc"}

    def retrieve_subscription(self, subscription_id):
        self.calls.append(("retrieve_subscription", subscription_id))
        return self.subscriptions[subscription_id]

    def update_subscription(self, subscription_id, params, idempotency_key):
        self.calls.append(("update_subscription", subscription_id, params))
        sub = self.subscriptions[subscription_id]
        if "items" in params:
            sub["items"]["data"][0]["price"]["id"] = params["items"][0]["price"]
        if "cancel_at_period_end" in params:
            sub["cancel_at_period_end"] = params["cancel_at_period_end"]
        return sub

    def cancel_subscription(self, subscription_id):
        self.calls.append(("cancel_subscription", subscription_id))
        sub = self.subscriptions[subscription_id]
        sub["status"] = "canceled"
        return sub

    # ---- helpers for tests --------------------------------------------------------------------
    def add_subscription(self, **kwargs):
        sub = subscription_obj(**kwargs)
        self.subscriptions[sub["id"]] = sub
        return sub

    def called(self, name):
        return [c for c in self.calls if c[0] == name]
