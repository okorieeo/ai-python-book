from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from billing.models import (AppendOnlyError, EntitlementOverride, Invoice, InvoiceLine, Payment, Plan,
                            PlanEntitlement, Price, Subscription, UsageEvent, WebhookEvent)
from billing.subscriptions import start_subscription

from .base import BillingTestCase, at


class PriceConstraintTests(BillingTestCase):
    def test_only_one_active_price_per_plan_currency_interval(self):
        plan = Plan.objects.get(code="starter")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Price.objects.create(plan=plan, currency="USD", interval="month", amount_minor=999)

    def test_an_old_price_can_be_retired_and_replaced(self):
        old = self.price("starter")
        old.is_active = False
        old.save()
        new = Price.objects.create(plan=old.plan, currency="USD", interval="month", amount_minor=600)
        self.assertEqual(Price.objects.filter(plan=old.plan, currency="USD", is_active=True).get(), new)

    def test_overage_size_and_price_must_come_together(self):
        plan = Plan.objects.get(code="starter")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Price.objects.create(plan=plan, currency="USD", interval="year", amount_minor=5000,
                                 overage_unit_size=100)

    def test_amounts_cannot_be_negative(self):
        plan = Plan.objects.get(code="starter")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Price.objects.create(plan=plan, currency="USD", interval="year", amount_minor=-1)


class EntitlementValidationTests(BillingTestCase):
    def test_unknown_keys_are_refused(self):
        with self.assertRaises(KeyError):
            PlanEntitlement.objects.create(plan=Plan.objects.get(code="free"), key="ai.teleport")

    def test_a_feature_cannot_have_a_limit_and_a_limit_cannot_be_switched_off(self):
        free = Plan.objects.get(code="free")
        with self.assertRaises(ValidationError):
            PlanEntitlement(plan=free, key="ai.agent_tools", limit=5).save()
        with self.assertRaises(ValidationError):
            PlanEntitlement(plan=free, key="ai.messages_per_month", enabled=False).save()

    def test_one_row_per_plan_and_key(self):
        with self.assertRaises((IntegrityError, ValidationError)), transaction.atomic():
            PlanEntitlement.objects.create(plan=Plan.objects.get(code="free"), key="ai.chat")

    def test_override_keys_are_validated_too(self):
        with self.assertRaises(KeyError):
            EntitlementOverride.objects.create(user=self.alice, key="nope", reason="x")


class SubscriptionConstraintTests(BillingTestCase):
    def test_the_database_refuses_a_second_live_subscription(self):
        sub = start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 1))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subscription.objects.create(
                user=self.alice, plan=sub.plan, price=sub.price, status="active", billing_anchor=sub.billing_anchor,
                current_period_start=sub.current_period_start, current_period_end=sub.current_period_end, provider="manual")

    def test_an_ended_subscription_does_not_block_a_new_one(self):
        sub = start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 1))
        sub.status = "expired"
        sub.save()
        start_subscription(self.alice, self.price("pro"), now=at(2026, 3, 1))  # no error

    def test_a_period_must_end_after_it_starts(self):
        sub = start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 1))
        sub.current_period_end = sub.current_period_start
        with self.assertRaises(IntegrityError), transaction.atomic():
            sub.save()

    def test_provider_subscription_ids_are_unique_per_provider(self):
        start_subscription(self.alice, self.price("starter"), provider="stripe",
                           provider_subscription_id="sub_1", now=at(2026, 1, 1))
        with self.assertRaises(IntegrityError), transaction.atomic():
            start_subscription(self.bob, self.price("starter"), provider="stripe",
                               provider_subscription_id="sub_1", now=at(2026, 1, 1))


class UsageEventTests(BillingTestCase):
    def test_usage_events_are_append_only(self):
        e = UsageEvent.objects.create(user=self.alice, key="ai.message", occurred_at=at(2026, 1, 1),
                                      idempotency_key="k1")
        e.quantity = 99
        with self.assertRaises(AppendOnlyError):
            e.save()
        with self.assertRaises(AppendOnlyError):
            e.delete()
        self.assertEqual(UsageEvent.objects.get(pk=e.pk).quantity, 1)

    def test_idempotency_keys_are_unique(self):
        UsageEvent.objects.create(user=self.alice, key="ai.message", occurred_at=at(2026, 1, 1), idempotency_key="k")
        with self.assertRaises(IntegrityError), transaction.atomic():
            UsageEvent.objects.create(user=self.bob, key="ai.message", occurred_at=at(2026, 1, 1), idempotency_key="k")


class InvoiceModelTests(BillingTestCase):
    def draft(self):
        return Invoice.objects.create(user=self.alice, currency="USD", tax_rate_bps=750)

    def test_line_amounts_are_quantity_times_unit_price(self):
        inv = self.draft()
        line = InvoiceLine.objects.create(invoice=inv, kind="adjustment", description="x", quantity=3,
                                          unit_amount_minor=250)
        self.assertEqual(line.amount_minor, 750)

    def test_totals_include_tax_rounded_half_up(self):
        inv = self.draft()
        InvoiceLine.objects.create(invoice=inv, kind="subscription", description="Pro", unit_amount_minor=2900)
        inv.recalculate()
        self.assertEqual((inv.subtotal_minor, inv.tax_minor, inv.total_minor), (2900, 218, 3118))  # 217.5 -> 218

    def test_credits_reduce_the_subtotal_and_never_create_negative_tax(self):
        inv = self.draft()
        InvoiceLine.objects.create(invoice=inv, kind="proration_credit", description="credit", unit_amount_minor=-500)
        inv.recalculate()
        self.assertEqual((inv.subtotal_minor, inv.tax_minor, inv.total_minor), (-500, 0, -500))

    def test_the_database_rejects_a_total_that_does_not_add_up(self):
        inv = self.draft()
        inv.total_minor = 5
        with self.assertRaises(IntegrityError), transaction.atomic():
            inv.save()

    def test_an_issued_invoice_cannot_be_recalculated_or_have_lines_changed(self):
        inv = self.draft()
        line = InvoiceLine.objects.create(invoice=inv, kind="subscription", description="Pro", unit_amount_minor=2900)
        inv.recalculate()
        inv.status = Invoice.Status.OPEN
        inv.save()
        with self.assertRaises(ValidationError):
            inv.recalculate()
        with self.assertRaises(ValidationError):
            InvoiceLine.objects.create(invoice=inv, kind="adjustment", description="sneaky", unit_amount_minor=1)
        with self.assertRaises(ValidationError):
            line.delete()


class PaymentAndWebhookModelTests(BillingTestCase):
    def test_a_provider_payment_id_is_stored_once(self):
        inv = Invoice.objects.create(user=self.alice, currency="USD")
        Payment.objects.create(invoice=inv, amount_minor=1, currency="USD", status="succeeded",
                               provider="stripe", provider_payment_id="pi_1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payment.objects.create(invoice=inv, amount_minor=1, currency="USD", status="succeeded",
                                   provider="stripe", provider_payment_id="pi_1")
        # the same id from a different provider is a different payment
        Payment.objects.create(invoice=inv, amount_minor=1, currency="NGN", status="succeeded",
                               provider="paystack", provider_payment_id="pi_1")

    def test_a_webhook_event_id_is_unique_per_provider(self):
        WebhookEvent.objects.create(provider="stripe", event_id="evt_1", event_type="x", payload={})
        with self.assertRaises(IntegrityError), transaction.atomic():
            WebhookEvent.objects.create(provider="stripe", event_id="evt_1", event_type="x", payload={})
