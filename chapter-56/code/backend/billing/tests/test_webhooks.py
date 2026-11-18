import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone as dt_tz
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from billing.models import Subscription, WebhookEvent
from testing import ensure_plans, make_user

STRIPE_SECRET = "whsec_test_secret"
PAYSTACK_SECRET = "sk_test_paystack_secret"


def stripe_post(client, event: dict, *, secret=STRIPE_SECRET, ts=None, body=None):
    body = body or json.dumps(event).encode()
    ts = ts or int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return client.post("/api/v1/billing/webhooks/stripe/", data=body, content_type="application/json",
                       HTTP_STRIPE_SIGNATURE=f"t={ts},v1={sig}")


def paystack_post(client, event: dict, *, secret=PAYSTACK_SECRET, body=None):
    body = body or json.dumps(event).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    return client.post("/api/v1/billing/webhooks/paystack/", data=body, content_type="application/json",
                       HTTP_X_PAYSTACK_SIGNATURE=sig)


def unix(dt: datetime) -> int:
    return int(dt.timestamp())


class StripeWebhookTests(TestCase):
    def setUp(self):
        self.free, self.pro = ensure_plans()
        self.user = make_user()
        self.period_end = timezone.now() + timedelta(days=30)

    def checkout_completed(self, event_id="evt_1"):
        return {"id": event_id, "type": "checkout.session.completed", "created": int(time.time()), "data": {"object": {
            "id": "cs_1", "mode": "subscription", "payment_status": "paid", "customer": "cus_1",
            "subscription": "sub_1", "client_reference_id": str(self.user.public_id),
            "metadata": {"plan_code": "pro", "user_public_id": str(self.user.public_id)},
            "customer_details": {"email": self.user.email}}}}

    def sub_updated(self, event_id="evt_2", status="active", created=None, cancel=False, etype="customer.subscription.updated"):
        return {"id": event_id, "type": etype, "created": created or int(time.time()), "data": {"object": {
            "id": "sub_1", "customer": "cus_1", "status": status, "cancel_at_period_end": cancel,
            "metadata": {"user_public_id": str(self.user.public_id), "plan_code": "pro"},
            "items": {"data": [{"current_period_end": unix(self.period_end), "price": {"id": "price_pro_123"}}]}}}}

    # ---- signatures ------------------------------------------------------------------------------
    def test_valid_signature_is_accepted(self):
        self.assertEqual(stripe_post(self.client, self.checkout_completed()).status_code, 200)

    def test_wrong_secret_is_rejected_and_changes_nothing(self):
        r = stripe_post(self.client, self.checkout_completed(), secret="whsec_attacker")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Subscription.objects.exists())
        self.assertFalse(WebhookEvent.objects.exists())

    def test_tampered_body_is_rejected(self):
        body = json.dumps(self.checkout_completed()).encode()
        ts = int(time.time())
        sig = hmac.new(STRIPE_SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        r = self.client.post("/api/v1/billing/webhooks/stripe/", data=body.replace(b"pro", b"max"),
                             content_type="application/json", HTTP_STRIPE_SIGNATURE=f"t={ts},v1={sig}")
        self.assertEqual(r.status_code, 400)

    def test_old_timestamps_are_rejected_to_stop_replays(self):
        r = stripe_post(self.client, self.checkout_completed(), ts=int(time.time()) - 3600)
        self.assertEqual(r.status_code, 400)

    def test_missing_signature_header_is_rejected(self):
        r = self.client.post("/api/v1/billing/webhooks/stripe/", data="{}", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_unknown_provider_is_404_and_get_is_405(self):
        self.assertEqual(self.client.post("/api/v1/billing/webhooks/evil/", data="{}",
                                          content_type="application/json").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/billing/webhooks/stripe/").status_code, 405)

    # ---- behaviour ---------------------------------------------------------------------------------
    def test_checkout_then_subscription_update_grants_pro_until_the_period_end(self):
        stripe_post(self.client, self.checkout_completed())
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual((sub.plan.code, sub.status, sub.gateway, sub.external_customer_id),
                         ("pro", "active", "stripe", "cus_1"))
        self.assertTrue(sub.is_entitled())  # provisional period from the plan until Stripe sends the real one
        stripe_post(self.client, self.sub_updated())
        sub.refresh_from_db()
        self.assertEqual(unix(sub.current_period_end), unix(self.period_end))

    def test_the_same_event_delivered_twice_is_applied_once(self):
        self.assertEqual(stripe_post(self.client, self.checkout_completed()).json()["outcome"], "applied")
        before = Subscription.objects.get(user=self.user).updated_at
        self.assertEqual(stripe_post(self.client, self.checkout_completed()).json()["outcome"], "duplicate")
        self.assertEqual(WebhookEvent.objects.count(), 1)
        self.assertEqual(Subscription.objects.get(user=self.user).updated_at, before)

    def test_unpaid_checkout_does_not_grant_access(self):
        event = self.checkout_completed()
        event["data"]["object"]["payment_status"] = "unpaid"
        self.assertEqual(stripe_post(self.client, event).status_code, 200)
        self.assertFalse(Subscription.objects.exists())

    def test_failed_payment_keeps_access_during_the_grace_period_then_ends_it(self):
        stripe_post(self.client, self.checkout_completed())
        stripe_post(self.client, self.sub_updated("evt_3", status="past_due"))
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.status, "past_due")
        self.assertTrue(sub.is_entitled(now=self.period_end + timedelta(days=2)))
        self.assertFalse(sub.is_entitled(now=self.period_end + timedelta(days=4)))

    def test_cancelling_at_period_end_keeps_access_until_then(self):
        stripe_post(self.client, self.checkout_completed())
        stripe_post(self.client, self.sub_updated("evt_4", cancel=True))
        sub = Subscription.objects.get(user=self.user)
        self.assertTrue(sub.cancel_at_period_end)
        self.assertTrue(sub.is_entitled(now=self.period_end - timedelta(hours=1)))
        self.assertFalse(sub.is_entitled(now=self.period_end + timedelta(hours=1)))

    def test_subscription_deleted_ends_access_immediately(self):
        stripe_post(self.client, self.checkout_completed())
        stripe_post(self.client, self.sub_updated("evt_5", status="canceled", etype="customer.subscription.deleted"))
        self.assertFalse(Subscription.objects.get(user=self.user).is_entitled())

    def test_an_older_event_arriving_late_cannot_undo_a_newer_one(self):
        now = int(time.time())
        stripe_post(self.client, self.checkout_completed())
        stripe_post(self.client, self.sub_updated("evt_new", status="canceled", created=now + 100,
                                                  etype="customer.subscription.deleted"))
        late = stripe_post(self.client, self.sub_updated("evt_old", status="active", created=now + 50))
        self.assertEqual(late.json()["outcome"], "stale")
        self.assertEqual(Subscription.objects.get(user=self.user).status, "canceled")

    def test_payment_failed_invoice_is_matched_by_customer_id(self):
        stripe_post(self.client, self.checkout_completed())
        invoice = {"id": "evt_inv", "type": "invoice.payment_failed", "created": int(time.time()) + 5,
                   "data": {"object": {"customer": "cus_1", "parent": {"subscription_details": {"subscription": "sub_1"}}}}}
        self.assertEqual(stripe_post(self.client, invoice).json()["outcome"], "applied")
        self.assertEqual(Subscription.objects.get(user=self.user).status, "past_due")

    def test_period_end_is_read_from_the_item_or_from_the_subscription_for_older_api_versions(self):
        old_style = self.sub_updated("evt_old_api")
        obj = old_style["data"]["object"]
        obj["current_period_end"] = unix(self.period_end) + 1000
        obj["items"]["data"][0].pop("current_period_end")
        stripe_post(self.client, self.checkout_completed())
        stripe_post(self.client, old_style)
        self.assertEqual(unix(Subscription.objects.get().current_period_end), unix(self.period_end) + 1000)

    def test_events_for_unknown_users_are_recorded_but_change_nothing(self):
        event = self.checkout_completed("evt_ghost")
        obj = event["data"]["object"]
        obj["client_reference_id"] = "00000000-0000-0000-0000-000000000000"
        obj["metadata"], obj["customer_details"] = {"plan_code": "pro"}, {"email": "nobody@example.com"}
        self.assertEqual(stripe_post(self.client, event).json()["outcome"], "unmatched_user")
        self.assertFalse(Subscription.objects.exists())

    def test_unhandled_event_types_are_acknowledged(self):
        event = {"id": "evt_x", "type": "customer.created", "created": int(time.time()), "data": {"object": {}}}
        self.assertEqual(stripe_post(self.client, event).status_code, 200)

    def test_a_crash_while_applying_returns_500_and_leaves_no_seen_marker_so_the_retry_works(self):
        with patch("billing.services._apply", side_effect=RuntimeError("database hiccup")):
            self.assertEqual(stripe_post(self.client, self.checkout_completed()).status_code, 500)
        self.assertFalse(WebhookEvent.objects.exists())
        self.assertEqual(stripe_post(self.client, self.checkout_completed()).json()["outcome"], "applied")


class PaystackWebhookTests(TestCase):
    def setUp(self):
        self.free, self.pro = ensure_plans()
        self.user = make_user()

    def charge(self, *, amount=500000, tx_id=111, meta=True, plan=None, currency="NGN"):
        data = {"id": tx_id, "status": "success", "reference": f"ref_{tx_id}", "amount": amount, "currency": currency,
                "paid_at": "2026-11-11T10:00:00.000Z",
                "customer": {"email": "ada@example.com", "customer_code": "CUS_abc"}}
        if meta:
            data["metadata"] = {"user_public_id": str(self.user.public_id), "plan_code": "pro"}
        if plan:
            data["plan"] = {"plan_code": plan}
        return {"event": "charge.success", "data": data}

    def test_signature_uses_sha512_of_the_raw_body(self):
        self.assertEqual(paystack_post(self.client, self.charge()).status_code, 200)
        self.assertEqual(paystack_post(self.client, self.charge(tx_id=2), secret="sk_test_wrong").status_code, 400)
        body = json.dumps(self.charge(tx_id=3)).encode()
        sha256 = hmac.new(PAYSTACK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        wrong_algorithm = self.client.post("/api/v1/billing/webhooks/paystack/", data=body,
                                           content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=sha256)
        self.assertEqual(wrong_algorithm.status_code, 400)

    def test_successful_charge_activates_pro_for_one_billing_period(self):
        paystack_post(self.client, self.charge())
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual((sub.plan.code, sub.status, sub.gateway, sub.external_customer_id), ("pro", "active", "paystack", "CUS_abc"))
        self.assertAlmostEqual((sub.current_period_end - timezone.now()).days, 30, delta=1)

    def test_renewal_charge_without_metadata_is_matched_by_customer_and_extends_the_period(self):
        paystack_post(self.client, self.charge(tx_id=1))
        first_end = Subscription.objects.get().current_period_end
        paystack_post(self.client, self.charge(tx_id=2, meta=False, plan="PLN_pro_123"))
        self.assertGreater(Subscription.objects.get().current_period_end, first_end)

    def test_a_charge_for_the_wrong_amount_does_not_grant_access(self):
        r = paystack_post(self.client, self.charge(amount=100))
        self.assertEqual(r.json()["outcome"], "rejected")
        self.assertFalse(Subscription.objects.exists())

    def test_delivering_the_same_charge_twice_extends_the_period_only_once(self):
        paystack_post(self.client, self.charge(tx_id=9))
        end = Subscription.objects.get().current_period_end
        self.assertEqual(paystack_post(self.client, self.charge(tx_id=9)).json()["outcome"], "duplicate")
        self.assertEqual(Subscription.objects.get().current_period_end, end)

    def test_subscription_create_stores_the_code_and_the_next_payment_date(self):
        paystack_post(self.client, self.charge())
        event = {"event": "subscription.create", "data": {
            "subscription_code": "SUB_xyz", "next_payment_date": "2026-12-11T10:00:00.000Z",
            "plan": {"plan_code": "PLN_pro_123"}, "customer": {"email": "ada@example.com", "customer_code": "CUS_abc"}}}
        paystack_post(self.client, event)
        sub = Subscription.objects.get()
        self.assertEqual(sub.external_subscription_id, "SUB_xyz")
        self.assertEqual(sub.current_period_end, datetime(2026, 12, 11, 10, 0, tzinfo=dt_tz.utc))

    def test_payment_failure_and_non_renewal(self):
        paystack_post(self.client, self.charge())
        paystack_post(self.client, {"event": "subscription.create", "data": {
            "subscription_code": "SUB_xyz", "next_payment_date": "2026-12-11T10:00:00.000Z",
            "plan": {"plan_code": "PLN_pro_123"}, "customer": {"email": "ada@example.com", "customer_code": "CUS_abc"}}})
        paystack_post(self.client, {"event": "invoice.payment_failed", "data": {
            "subscription": {"subscription_code": "SUB_xyz"}, "customer": {"customer_code": "CUS_abc"}}})
        self.assertEqual(Subscription.objects.get().status, "past_due")
        paystack_post(self.client, self.charge(tx_id=77, meta=False, plan="PLN_pro_123"))
        paystack_post(self.client, {"event": "subscription.not_renew", "data": {
            "subscription_code": "SUB_xyz", "customer": {"customer_code": "CUS_abc"}}})
        sub = Subscription.objects.get()
        self.assertEqual((sub.status, sub.cancel_at_period_end), ("active", True))

    def test_unrelated_charges_do_not_create_subscriptions(self):
        r = paystack_post(self.client, {"event": "charge.success", "data": {
            "id": 5, "status": "success", "amount": 1000, "currency": "NGN",
            "customer": {"email": "stranger@example.com", "customer_code": "CUS_zzz"}}})
        self.assertEqual(r.json()["outcome"], "unmatched_user")
        self.assertFalse(Subscription.objects.exists())
