from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import stripe
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from billing.entitlements import current_plan
from billing.gateways import registry
from billing.gateways.base import GatewayError
from billing.gateways.paystack_gateway import API, PaystackGateway
from billing.gateways.stripe_gateway import StripeGateway
from billing.models import Subscription
from testing import ensure_plans, make_user


class CheckoutTests(TestCase):
    def setUp(self):
        self.free, self.pro = ensure_plans()
        self.user = make_user()
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def fake_stripe(self):
        client = MagicMock()
        client.v1.checkout.sessions.create.return_value = SimpleNamespace(url="https://checkout.stripe.test/c/1", id="cs_1")
        return client

    def test_pricing_page_is_public(self):
        r = APIClient().get("/api/v1/billing/plans/")
        self.assertEqual([p["code"] for p in r.json()], ["free", "pro"])

    def test_stripe_checkout_sends_the_user_and_plan_in_metadata(self):
        client = self.fake_stripe()
        with patch.dict(registry._FACTORIES, {"stripe": lambda: StripeGateway(client=client)}):
            r = self.api.post("/api/v1/billing/checkout/", {"plan": "pro", "gateway": "stripe"}, format="json")
        self.assertEqual((r.status_code, r.json()["url"]), (200, "https://checkout.stripe.test/c/1"))
        params = client.v1.checkout.sessions.create.call_args.kwargs["params"]
        self.assertEqual(params["mode"], "subscription")
        self.assertEqual(params["line_items"], [{"price": "price_pro_123", "quantity": 1}])
        self.assertEqual(params["client_reference_id"], str(self.user.public_id))
        self.assertEqual(params["subscription_data"]["metadata"]["plan_code"], "pro")
        self.assertNotIn("amount", params)  # the price comes from Stripe, never from the browser

    def test_client_cannot_choose_the_price_or_an_unknown_plan(self):
        self.assertEqual(self.api.post("/api/v1/billing/checkout/", {"plan": "free", "gateway": "stripe"},
                                       format="json").status_code, 404)
        self.assertEqual(self.api.post("/api/v1/billing/checkout/", {"plan": "enterprise", "gateway": "stripe"},
                                       format="json").status_code, 404)
        self.assertEqual(self.api.post("/api/v1/billing/checkout/", {"plan": "pro", "gateway": "bitcoin"},
                                       format="json").status_code, 400)

    @override_settings(BILLING_GATEWAYS_ENABLED=["paystack"])
    def test_a_gateway_switched_off_in_settings_is_unavailable(self):
        r = self.api.post("/api/v1/billing/checkout/", {"plan": "pro", "gateway": "stripe"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_paid_users_cannot_start_a_second_subscription(self):
        Subscription.objects.create(user=self.user, plan=self.pro, status="active", gateway="stripe",
                                    current_period_end=timezone.now() + timedelta(days=5))
        r = self.api.post("/api/v1/billing/checkout/", {"plan": "pro", "gateway": "stripe"}, format="json")
        self.assertEqual(r.status_code, 409)

    def test_gateway_failure_becomes_a_clean_502(self):
        client = MagicMock()
        client.v1.checkout.sessions.create.side_effect = stripe.APIConnectionError("boom")
        with patch.dict(registry._FACTORIES, {"stripe": lambda: StripeGateway(client=client)}):
            r = self.api.post("/api/v1/billing/checkout/", {"plan": "pro", "gateway": "stripe"}, format="json")
        self.assertEqual(r.status_code, 502)
        self.assertNotIn("boom", r.content.decode())

    def test_checkout_requires_login(self):
        self.assertEqual(APIClient().post("/api/v1/billing/checkout/", {}, format="json").status_code, 401)

    def test_paystack_initialize_request_has_the_plan_metadata_and_a_bearer_key(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"], seen["body"] = request.headers["authorization"], request.read()
            return httpx.Response(200, json={"status": True, "data": {
                "authorization_url": "https://checkout.paystack.test/abc", "reference": "ref_1"}})

        gw = PaystackGateway(client=httpx.Client(base_url=API, transport=httpx.MockTransport(handler)))
        session = gw.create_checkout(user=self.user, plan=self.pro, success_url="https://app/ok", cancel_url="https://app/no")
        import json
        body = json.loads(seen["body"])
        self.assertEqual(session.url, "https://checkout.paystack.test/abc")
        self.assertEqual(seen["auth"], "Bearer sk_test_paystack_secret")
        self.assertEqual((body["plan"], body["email"]), ("PLN_pro_123", "ada@example.com"))
        self.assertEqual(body["metadata"], {"user_public_id": str(self.user.public_id), "plan_code": "pro"})

    def test_paystack_errors_become_gateway_errors(self):
        gw = PaystackGateway(client=httpx.Client(base_url=API, transport=httpx.MockTransport(
            lambda r: httpx.Response(500, json={"status": False}))))
        with self.assertRaises(GatewayError):
            gw.create_checkout(user=self.user, plan=self.pro, success_url="x", cancel_url="y")

    def test_subscription_endpoint_reports_plan_status_and_usage(self):
        r = self.api.get("/api/v1/billing/subscription/").json()
        self.assertEqual((r["plan"]["code"], r["status"], r["usage"]), ("free", "none", {"used": 0, "limit": 3}))

    def test_portal_needs_a_subscription(self):
        self.assertEqual(self.api.post("/api/v1/billing/portal/").status_code, 404)


class EntitlementTests(TestCase):
    def setUp(self):
        self.free, self.pro = ensure_plans()
        self.user = make_user()

    def sub(self, **kw):
        defaults = dict(user=self.user, plan=self.pro, status="active", gateway="stripe",
                        current_period_end=timezone.now() + timedelta(days=10))
        return Subscription.objects.create(**{**defaults, **kw})

    def test_no_subscription_means_free(self):
        self.assertEqual(current_plan(self.user).code, "free")

    def test_active_subscription_means_pro(self):
        self.sub()
        self.assertEqual(current_plan(self.user).code, "pro")

    def test_canceled_and_expired_mean_free(self):
        self.sub(status="canceled")
        self.assertEqual(current_plan(self.user).code, "free")

    def test_cancelled_at_period_end_and_past_end_means_free(self):
        self.sub(cancel_at_period_end=True, current_period_end=timezone.now() - timedelta(minutes=1))
        self.assertEqual(current_plan(self.user).code, "free")

    def test_missing_free_plan_row_fails_closed_to_a_small_limit(self):
        from billing.models import Plan
        Plan.objects.filter(code="free").delete()
        self.assertEqual(current_plan(self.user).daily_message_limit, 5)
