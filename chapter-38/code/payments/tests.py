"""Django tests for the payments app. They need Django, DRF and a database (see section 38.13)."""
import hashlib
import hmac
import json
import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from core.payments.fakes import FakeGateway
from core.payments.money import Money
from payments import registry, services
from payments.models import Invoice, Payment, WebhookEvent

User = get_user_model()
PS_SECRET = "sk_test_secret"


def ps_body(reference, amount=500000, event_id=3050):
    return json.dumps({"event": "charge.success", "data": {"id": event_id, "status": "success", "reference": reference,
                                                           "amount": amount, "currency": "NGN"}}).encode()


def ps_headers(body):
    return {"x-paystack-signature": hmac.new(PS_SECRET.encode(), body, hashlib.sha512).hexdigest()}


@override_settings(PAYMENT_GATEWAYS={"paystack": True}, PAYSTACK_SECRET_KEY=PS_SECRET, PAYSTACK_CHECK_WEBHOOK_IP=False,
                   INVOICE_PREFIX="INV", SELLER_DETAILS={"name": "Acme Ltd"}, TAX_RATE_BP=750, PRICES_INCLUDE_TAX=False)
class WebhookTests(TestCase):
    def setUp(self):
        registry.get_gateways.cache_clear()
        self.user = User.objects.create_user(email="ada@example.com", password="a-long-test-password")
        self.payment = Payment.objects.create(reference="pay_abc", user=self.user, idempotency_key="key-12345", amount_minor=500000,
                                              currency="NGN", provider="paystack")

    def post(self, body, headers):
        return services.handle_webhook("paystack", body, headers)

    @mock.patch("payments.services.after_payment_succeeded_task")
    def test_valid_webhook_fulfils_once_even_if_delivered_twice(self, task):
        body = ps_body("pay_abc")
        self.assertEqual(self.post(body, ps_headers(body)), (200, "fulfilled"))
        self.assertEqual(self.post(body, ps_headers(body)), (200, "duplicate"))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "succeeded")
        self.assertEqual(task.call_count, 1)
        self.assertEqual(WebhookEvent.objects.count(), 1)

    def test_bad_signature_is_rejected_and_changes_nothing(self):
        body = ps_body("pay_abc")
        self.assertEqual(self.post(body, {"x-paystack-signature": "00"}), (400, "bad_signature"))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_wrong_amount_does_not_fulfil(self):
        body = ps_body("pay_abc", amount=100)
        self.assertEqual(self.post(body, ps_headers(body)), (200, "amount_mismatch"))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")

    def test_unknown_reference_is_acknowledged_and_stored(self):
        body = ps_body("pay_nope", event_id=9)
        self.assertEqual(self.post(body, ps_headers(body)), (200, "unknown_reference"))
        self.assertEqual(WebhookEvent.objects.filter(outcome="unknown_reference").count(), 1)


@override_settings(PAYMENT_GATEWAYS={"paystack": True, "stripe": True})
class CheckoutApiTests(APITestCase):
    def setUp(self):
        registry.get_gateways.cache_clear()
        self.fakes = {"stripe": FakeGateway("stripe", {"USD"}), "paystack": FakeGateway("paystack", {"NGN", "USD"})}
        patcher = mock.patch("payments.services.get_gateways", return_value=self.fakes)
        patcher.start(); self.addCleanup(patcher.stop)
        price = mock.patch("billing.services.price_for", return_value=Money(500000, "NGN"), create=True)
        price.start(); self.addCleanup(price.stop)
        self.ada = User.objects.create_user(email="ada@example.com", password="a-long-test-password")
        self.bo = User.objects.create_user(email="bo@example.com", password="a-long-test-password")

    def checkout(self, key="idem-key-0001", user=None):
        self.client.force_authenticate(user or self.ada)
        return self.client.post("/api/v1/payments/checkout/", {"plan_code": "pro", "currency": "NGN", "country": "NG"},
                                format="json", HTTP_IDEMPOTENCY_KEY=key)

    def test_requires_idempotency_key(self):
        self.client.force_authenticate(self.ada)
        r = self.client.post("/api/v1/payments/checkout/", {"plan_code": "pro", "currency": "NGN"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_same_key_twice_creates_one_payment(self):
        a, b = self.checkout(), self.checkout()
        self.assertEqual(a.status_code, 201)
        self.assertEqual(a.data["payment_id"], b.data["payment_id"])
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(a.data["provider"], "paystack")

    def test_status_endpoint_is_owner_scoped(self):
        ref = self.checkout().data["payment_id"]
        self.client.force_authenticate(self.bo)
        self.assertEqual(self.client.get(f"/api/v1/payments/{ref}/").status_code, 404)
        self.client.force_authenticate(self.ada)
        self.assertEqual(self.client.get(f"/api/v1/payments/{ref}/").status_code, 200)


class InvoiceTests(TestCase):
    def test_issued_invoices_cannot_be_edited(self):
        user = User.objects.create_user(email="ada@example.com", password="a-long-test-password")
        p = Payment.objects.create(reference="pay_1", user=user, idempotency_key="key-12345", amount_minor=1075000,
                                   currency="NGN", status="succeeded")
        inv = Invoice.objects.create(number="INV-2026-000001", payment=p, currency="NGN", net_minor=1000000, tax_minor=75000,
                                     gross_minor=1075000, tax_rate_bp=750, lines=[], seller_snapshot={}, buyer_snapshot={},
                                     issued_at="2026-11-06T00:00:00Z")
        inv.gross_minor = 1
        with self.assertRaises(PermissionError):
            inv.save()

    def test_payment_database_rejects_refund_above_amount(self):
        from django.db import IntegrityError, transaction
        user = User.objects.create_user(email="ada@example.com", password="a-long-test-password")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payment.objects.create(reference="pay_2", user=user, idempotency_key="key-67890", amount_minor=100,
                                   currency="NGN", refunded_minor=101)
