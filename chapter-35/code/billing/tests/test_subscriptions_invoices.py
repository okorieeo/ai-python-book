from django.core.exceptions import ValidationError

from billing.invoices import (build_proration_invoice, build_renewal_invoice, describe, finalize,
                              record_payment, void)
from billing.models import Invoice, Payment, Subscription
from billing.subscriptions import (AlreadySubscribed, InvalidTransition, apply_plan_change, cancel, expire,
                                   mark_past_due, preview_plan_change, renew, transition, undo_cancel,
                                   start_subscription)
from billing.usage import record_usage

from .base import BillingTestCase, at


class SubscriptionLifecycleTests(BillingTestCase):
    def test_start_creates_an_active_subscription_with_one_period(self):
        sub = start_subscription(self.alice, self.price("starter"), now=at(2026, 3, 10))
        self.assertEqual((sub.status, sub.period_number), ("active", 1))
        self.assertEqual((sub.current_period_start, sub.current_period_end), (at(2026, 3, 10), at(2026, 4, 10)))

    def test_a_second_live_subscription_is_refused_by_the_service(self):
        start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 1))
        with self.assertRaises(AlreadySubscribed):
            start_subscription(self.alice, self.price("pro"), now=at(2026, 1, 2))

    def test_trials_start_trialing_and_bill_from_the_trial_end(self):
        sub = start_subscription(self.alice, self.price("pro"), trial_days=14, now=at(2026, 1, 1))
        self.assertEqual((sub.status, sub.period_number, sub.billing_anchor), ("trialing", 0, at(2026, 1, 15)))
        renew(sub)  # the first payment succeeded
        self.assertEqual((sub.status, sub.period_number), ("active", 1))
        self.assertEqual((sub.current_period_start, sub.current_period_end), (at(2026, 1, 15), at(2026, 2, 15)))

    def test_renewals_count_from_the_anchor_so_month_ends_do_not_drift(self):
        sub = start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 31))
        ends = []
        for _ in range(4):
            ends.append(sub.current_period_end)
            renew(sub)
        ends.append(sub.current_period_end)
        self.assertEqual(ends, [at(2026, 2, 28), at(2026, 3, 31), at(2026, 4, 30), at(2026, 5, 31), at(2026, 6, 30)])

    def test_past_due_recovers_to_active_on_a_successful_payment(self):
        sub = start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 1))
        mark_past_due(sub)
        renew(sub)
        self.assertEqual((sub.status, sub.period_number), ("active", 2))

    def test_impossible_transitions_are_refused(self):
        sub = start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 1))
        expire(sub)
        with self.assertRaises(InvalidTransition):
            transition(sub, Subscription.Status.ACTIVE)
        with self.assertRaises(InvalidTransition):
            mark_past_due(sub)

    def test_cancel_at_period_end_keeps_access_until_the_renewal_that_never_comes(self):
        sub = start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 1))
        cancel(sub)
        self.assertEqual(sub.status, "active")  # still paid up
        renew(sub, now=at(2026, 2, 1))          # the period ends: instead of renewing, it cancels
        self.assertEqual(sub.status, "canceled")
        self.assertEqual(sub.canceled_at, at(2026, 2, 1))

    def test_a_cancellation_can_be_undone_before_the_period_ends(self):
        sub = start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 1))
        cancel(sub)
        undo_cancel(sub)
        renew(sub)
        self.assertEqual((sub.status, sub.period_number), ("active", 2))

    def test_cancel_now_ends_it_immediately(self):
        sub = start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 1))
        cancel(sub, at_period_end=False, now=at(2026, 1, 5))
        self.assertEqual(sub.status, "canceled")


class PlanChangeTests(BillingTestCase):
    def test_an_upgrade_starts_now_and_is_prorated(self):
        sub = start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 1, 0))  # 31-day period
        change = apply_plan_change(sub, self.price("pro"), now=at(2026, 1, 16, 12))          # exactly half left
        self.assertEqual((change.direction, change.effective), ("upgrade", "now"))
        self.assertEqual((change.proration.credit_minor, change.proration.charge_minor), (250, 1450))
        sub.refresh_from_db()
        self.assertEqual(sub.plan.code, "pro")

    def test_a_downgrade_waits_for_the_next_renewal_without_a_refund(self):
        sub = start_subscription(self.alice, self.price("pro"), now=at(2026, 1, 1))
        change = apply_plan_change(sub, self.price("starter"), now=at(2026, 1, 10))
        self.assertEqual((change.direction, change.effective, change.proration), ("downgrade", "next_renewal", None))
        sub.refresh_from_db()
        self.assertEqual((sub.plan.code, sub.pending_plan.code), ("pro", "starter"))  # still Pro for now
        renew(sub)
        sub.refresh_from_db()
        self.assertEqual((sub.plan.code, sub.price.amount_minor, sub.pending_plan), ("starter", 500, None))

    def test_changing_currency_is_not_a_plan_change(self):
        sub = start_subscription(self.alice, self.price("starter", "USD"), now=at(2026, 1, 1))
        with self.assertRaises(ValueError):
            preview_plan_change(sub, self.price("pro", "NGN"))

    def test_same_tier_is_a_no_op(self):
        sub = start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 1))
        self.assertEqual(preview_plan_change(sub, self.price("starter")).direction, "same")


class InvoiceTests(BillingTestCase):
    def pro_sub(self, **kw):
        return start_subscription(self.alice, self.price("pro", kw.pop("currency", "USD")), now=at(2026, 1, 1))

    def test_a_renewal_invoice_without_overage_has_one_line(self):
        sub = self.pro_sub()
        inv = build_renewal_invoice(sub)
        self.assertEqual([(l.kind, l.amount_minor) for l in inv.lines.all()], [("subscription", 2900)])
        self.assertEqual(inv.total_minor, 2900)

    def test_overage_is_billed_in_started_blocks(self):
        sub = self.pro_sub()
        record_usage(self.alice, "ai.message", 1650, "big", now=at(2026, 1, 20))  # 150 over the 1,500 allowance
        inv = build_renewal_invoice(sub)
        kinds = {l.kind: l for l in inv.lines.all()}
        self.assertEqual((kinds["usage_overage"].quantity, kinds["usage_overage"].unit_amount_minor), (2, 150))
        self.assertEqual(inv.total_minor, 2900 + 300)

    def test_usage_outside_the_period_is_not_billed(self):
        sub = self.pro_sub()
        record_usage(self.alice, "ai.message", 2000, "december", now=at(2025, 12, 20))
        self.assertEqual(build_renewal_invoice(sub).total_minor, 2900)

    def test_nigerian_naira_invoice_with_tax(self):
        sub = self.pro_sub(currency="NGN")
        inv = build_renewal_invoice(sub, tax_rate_bps=750)
        self.assertEqual((inv.currency, inv.subtotal_minor, inv.tax_minor, inv.total_minor),
                         ("NGN", 4_500_000, 337_500, 4_837_500))

    def test_finalize_numbers_and_locks_the_invoice(self):
        inv = build_renewal_invoice(self.pro_sub())
        finalize(inv, now=at(2026, 2, 1))
        self.assertEqual(inv.status, "open")
        self.assertEqual(inv.number, f"INV-2026-{inv.pk:06d}")
        with self.assertRaises(ValidationError):
            finalize(inv)
        self.assertIn("Total: $29.00", describe(inv)[-1])

    def test_proration_invoice_nets_to_the_difference(self):
        sub = start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 1, 0))
        change = apply_plan_change(sub, self.price("pro"), now=at(2026, 1, 16, 12))
        inv = build_proration_invoice(sub, change.proration, old_name="Starter", new_name="Pro")
        self.assertEqual(sorted(l.amount_minor for l in inv.lines.all()), [-250, 1450])
        self.assertEqual(inv.total_minor, change.proration.net_minor)

    def test_payments_are_recorded_once_and_mark_the_invoice_paid(self):
        inv = finalize(build_renewal_invoice(self.pro_sub()), now=at(2026, 2, 1))
        p1, created1 = record_payment(inv, provider="stripe", provider_payment_id="pi_1", amount_minor=2900,
                                      currency="USD", now=at(2026, 2, 1))
        p2, created2 = record_payment(inv, provider="stripe", provider_payment_id="pi_1", amount_minor=2900,
                                      currency="USD")
        inv.refresh_from_db()
        self.assertEqual((created1, created2, p1.pk == p2.pk), (True, False, True))
        self.assertEqual((inv.status, inv.paid_at), ("paid", at(2026, 2, 1)))
        self.assertEqual(Payment.objects.count(), 1)

    def test_a_partial_or_failed_payment_does_not_mark_it_paid(self):
        inv = finalize(build_renewal_invoice(self.pro_sub()))
        record_payment(inv, provider="stripe", provider_payment_id="pi_a", amount_minor=1000, currency="USD")
        record_payment(inv, provider="stripe", provider_payment_id="pi_b", amount_minor=2900, currency="USD",
                       status="failed")
        inv.refresh_from_db()
        self.assertEqual(inv.status, "open")

    def test_a_payment_in_the_wrong_currency_is_refused(self):
        inv = finalize(build_renewal_invoice(self.pro_sub()))
        with self.assertRaises(ValidationError):
            record_payment(inv, provider="paystack", provider_payment_id="ps_1", amount_minor=2900, currency="NGN")

    def test_only_unpaid_invoices_can_be_voided(self):
        inv = finalize(build_renewal_invoice(self.pro_sub()))
        record_payment(inv, provider="stripe", provider_payment_id="pi_9", amount_minor=2900, currency="USD")
        inv.refresh_from_db()
        with self.assertRaises(ValidationError):
            void(inv)
        other = build_renewal_invoice(start_subscription(self.bob, self.price("starter"), now=at(2026, 1, 1)))
        self.assertEqual(void(other).status, Invoice.Status.VOID)
