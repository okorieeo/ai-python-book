"""Tests for the framework-independent payment code of Chapter 38. Run: python -m unittest core.test_payments -v"""
import hashlib
import hmac
import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from core.payments import normalize, reconciliation as rc, refunds as rf, webhooks as wh
from core.payments.checkout import CheckoutFailed, start_checkout
from core.payments.events import apply_event
from core.payments.fakes import FakeGateway
from core.payments.gateway import EventType, NormalizedEvent, SignatureError
from core.payments.invoices import Line, credit_note_totals, invoice_number, totals_for
from core.payments.memory import MemoryRepo
from core.payments.money import Money, MoneyError
from core.payments.routing import GatewayConfig, GatewayRouter, HealthTracker, NoGatewayError
from core.payments.states import InvalidTransition, PaymentStatus as S, can_transition, transition

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
NGN = lambda major: Money.from_major(str(major), "NGN")  # noqa: E731


class MoneyTests(unittest.TestCase):
    def test_major_to_minor_and_back(self):
        m = Money.from_major("5000.50", "NGN")
        self.assertEqual(m.amount_minor, 500050)
        self.assertEqual(m.to_major(), Decimal("5000.50"))
        self.assertEqual(str(m), "NGN 5,000.50")

    def test_floats_are_rejected(self):
        with self.assertRaises(MoneyError):
            Money.from_major(0.1, "NGN")
        with self.assertRaises(MoneyError):
            Money(10.5, "NGN")
        with self.assertRaises(MoneyError):
            Money(True, "NGN")

    def test_zero_decimal_currency(self):
        self.assertEqual(Money.from_major("1500", "JPY").amount_minor, 1500)
        with self.assertRaises(MoneyError):
            Money.from_major("1500.5", "JPY")

    def test_too_many_decimals_rejected(self):
        with self.assertRaises(MoneyError):
            Money.from_major("1.005", "USD")

    def test_unknown_currency_rejected(self):
        with self.assertRaises(MoneyError):
            Money(100, "XXX")

    def test_arithmetic_and_currency_mixing(self):
        self.assertEqual((NGN(10) + NGN(5)).amount_minor, 1500)
        self.assertEqual((NGN(10) - NGN(12)).amount_minor, -200)
        with self.assertRaises(MoneyError):
            NGN(1) + Money(100, "USD")

    def test_basis_points_rounds_half_up(self):
        self.assertEqual(NGN(1000).basis_points(750).amount_minor, 7500)      # 7.5% of 1,000.00
        self.assertEqual(Money(1, "NGN").basis_points(5000).amount_minor, 1)   # 0.5 rounds up
        self.assertEqual(Money(1, "NGN").basis_points(4999).amount_minor, 0)


class StateTests(unittest.TestCase):
    def test_happy_path(self):
        self.assertEqual(transition(S.PENDING, S.SUCCEEDED), S.SUCCEEDED)
        self.assertEqual(transition(S.SUCCEEDED, S.PARTIALLY_REFUNDED), S.PARTIALLY_REFUNDED)
        self.assertEqual(transition(S.PARTIALLY_REFUNDED, S.REFUNDED), S.REFUNDED)

    def test_success_is_never_undone_by_failure(self):
        for state in (S.SUCCEEDED, S.PARTIALLY_REFUNDED, S.REFUNDED):
            self.assertFalse(can_transition(state, S.FAILED))
            with self.assertRaises(InvalidTransition):
                transition(state, S.FAILED)

    def test_late_success_after_failure_is_allowed(self):
        self.assertTrue(can_transition(S.FAILED, S.SUCCEEDED))

    def test_same_state_is_a_noop(self):
        self.assertEqual(transition(S.SUCCEEDED, S.SUCCEEDED), S.SUCCEEDED)

    def test_cannot_refund_a_pending_payment(self):
        self.assertFalse(can_transition(S.PENDING, S.REFUNDED))


SECRET = "whsec_test_secret"


def stripe_header(body: bytes, ts: int, secret=SECRET):
    sig = hmac.new(secret.encode(), str(ts).encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


class SignatureTests(unittest.TestCase):
    BODY = b'{"id":"evt_1","type":"payment_intent.succeeded"}'
    TS = 1_800_000_000

    def test_valid_stripe_signature(self):
        wh.verify_stripe_signature(self.BODY, stripe_header(self.BODY, self.TS), SECRET, now=self.TS + 10)

    def test_stripe_wrong_secret_body_or_header(self):
        good = stripe_header(self.BODY, self.TS)
        for body, header, secret in ((self.BODY, stripe_header(self.BODY, self.TS, "other"), SECRET),
                                     (self.BODY + b" ", good, SECRET), (self.BODY, "", SECRET),
                                     (self.BODY, "garbage", SECRET), (self.BODY, good, "")):
            with self.subTest(header=header[:12]):
                with self.assertRaises(SignatureError):
                    wh.verify_stripe_signature(body, header, secret, now=self.TS)

    def test_stripe_replay_outside_tolerance(self):
        with self.assertRaises(SignatureError):
            wh.verify_stripe_signature(self.BODY, stripe_header(self.BODY, self.TS), SECRET, now=self.TS + 301)
        wh.verify_stripe_signature(self.BODY, stripe_header(self.BODY, self.TS), SECRET, now=self.TS + 300)

    def test_stripe_accepts_any_matching_v1(self):
        good = stripe_header(self.BODY, self.TS)
        wh.verify_stripe_signature(self.BODY, good + ",v1=" + "0" * 64, SECRET, now=self.TS)

    def test_paystack_signature_is_sha512_of_raw_body(self):
        body = b'{"event":"charge.success","data":{"reference":"pay_1"}}'
        sig = hmac.new(b"sk_test_x", body, hashlib.sha512).hexdigest()
        wh.verify_paystack_signature(body, sig, "sk_test_x")
        with self.assertRaises(SignatureError):
            wh.verify_paystack_signature(body, hmac.new(b"sk_test_x", body, hashlib.sha256).hexdigest(), "sk_test_x")
        with self.assertRaises(SignatureError):
            wh.verify_paystack_signature(json.dumps(json.loads(body), indent=1).encode(), sig, "sk_test_x")  # re-serialized
        with self.assertRaises(SignatureError):
            wh.verify_paystack_signature(body, "", "sk_test_x")

    def test_paystack_ip_allow_list(self):
        self.assertTrue(wh.is_paystack_ip("52.31.139.75"))
        self.assertFalse(wh.is_paystack_ip("203.0.113.9"))


def ev(i="e1", typ=EventType.PAYMENT_SUCCEEDED, **kw):
    return NormalizedEvent(kw.pop("provider", "stripe"), i, typ, kw.pop("reference", "r1"), **kw)


class DedupeTests(unittest.TestCase):
    def test_second_delivery_is_a_duplicate(self):
        d, seen = wh.InMemoryDeduper(), []
        self.assertEqual(wh.process_once(ev(), d, seen.append), "processed")
        self.assertEqual(wh.process_once(ev(), d, seen.append), "duplicate")
        self.assertEqual(len(seen), 1)

    def test_same_id_from_different_providers_is_not_a_duplicate(self):
        d = wh.InMemoryDeduper()
        self.assertEqual(wh.process_once(ev(provider="stripe"), d, lambda e: None), "processed")
        self.assertEqual(wh.process_once(ev(provider="paystack"), d, lambda e: None), "processed")

    def test_failure_releases_the_claim_so_the_retry_works(self):
        d, calls = wh.InMemoryDeduper(), []

        def flaky(event):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("db down")
        with self.assertRaises(RuntimeError):
            wh.process_once(ev(), d, flaky)
        self.assertEqual(wh.process_once(ev(), d, flaky), "processed")
        self.assertEqual(len(calls), 2)


STRIPE_SUCCESS = json.dumps({"id": "evt_1", "type": "payment_intent.succeeded", "created": 1_800_000_000,
    "data": {"object": {"id": "pi_1", "amount": 500000, "currency": "usd",
                        "metadata": {"payment_reference": "pay_abc"}}}}).encode()
STRIPE_REFUND = json.dumps({"id": "evt_2", "type": "charge.refunded",
    "data": {"object": {"id": "ch_1", "payment_intent": "pi_1", "amount": 500000, "amount_refunded": 200000,
                        "currency": "usd", "metadata": {"payment_reference": "pay_abc"}}}}).encode()
PAYSTACK_SUCCESS = json.dumps({"event": "charge.success", "data": {"id": 3050, "status": "success",
    "reference": "pay_abc", "amount": 500000, "currency": "NGN"}}).encode()
PAYSTACK_REFUND = json.dumps({"event": "refund.processed", "data": {"id": 77, "status": "processed",
    "transaction_reference": "pay_abc", "refund_reference": "rfd_9", "amount": 200000, "currency": "NGN"}}).encode()


class NormalizeTests(unittest.TestCase):
    def test_stripe_success(self):
        e = normalize.parse_stripe(STRIPE_SUCCESS)
        self.assertEqual((e.type, e.reference, e.amount_minor, e.currency, e.event_id),
                         (EventType.PAYMENT_SUCCEEDED, "pay_abc", 500000, "USD", "evt_1"))

    def test_stripe_refund_is_cumulative(self):
        e = normalize.parse_stripe(STRIPE_REFUND)
        self.assertEqual((e.type, e.amount_minor, e.amount_is_cumulative), (EventType.REFUND_UPDATED, 200000, True))

    def test_paystack_success_and_event_id(self):
        e = normalize.parse_paystack(PAYSTACK_SUCCESS)
        self.assertEqual((e.type, e.reference, e.amount_minor, e.currency, e.event_id),
                         (EventType.PAYMENT_SUCCEEDED, "pay_abc", 500000, "NGN", "charge.success:3050"))

    def test_paystack_refund_uses_transaction_reference(self):
        e = normalize.parse_paystack(PAYSTACK_REFUND)
        self.assertEqual((e.type, e.reference, e.refund_ref, e.amount_is_cumulative),
                         (EventType.REFUND_UPDATED, "pay_abc", "rfd_9", False))

    def test_unknown_and_unsuccessful_events_are_ignored(self):
        self.assertEqual(normalize.parse_stripe(b'{"id":"e","type":"customer.created","data":{"object":{}}}').type, EventType.IGNORED)
        failed = json.dumps({"event": "charge.success", "data": {"status": "failed", "reference": "x"}}).encode()
        self.assertEqual(normalize.parse_paystack(failed).type, EventType.IGNORED)


def configs():
    return [GatewayConfig("stripe", frozenset({"USD", "EUR", "GBP"}), priority=10),
            GatewayConfig("paystack", frozenset({"NGN", "GHS", "KES", "ZAR", "USD"}),
                          home_countries=frozenset({"NG", "GH", "KE", "ZA"}), priority=20)]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class RoutingTests(unittest.TestCase):
    def router(self):
        self.clock = Clock()
        return GatewayRouter(configs(), HealthTracker(self.clock))

    def test_currency_decides_eligibility(self):
        r = self.router()
        self.assertEqual(r.choose(currency="NGN", country="NG"), ["paystack"])
        self.assertEqual(r.choose(currency="EUR", country="FR"), ["stripe"])

    def test_usd_prefers_local_gateway_for_home_countries(self):
        r = self.router()
        self.assertEqual(r.choose(currency="USD", country="NG"), ["paystack", "stripe"])
        self.assertEqual(r.choose(currency="USD", country="US"), ["stripe", "paystack"])
        self.assertEqual(r.choose(currency="USD", country=None), ["stripe", "paystack"])

    def test_user_preference_wins_among_eligible(self):
        r = self.router()
        self.assertEqual(r.choose(currency="USD", country="NG", preferred="stripe"), ["stripe", "paystack"])
        self.assertEqual(r.choose(currency="NGN", country="NG", preferred="stripe"), ["paystack"])  # not eligible

    def test_no_gateway_for_currency(self):
        with self.assertRaises(NoGatewayError):
            self.router().choose(currency="JPY", country="JP")

    def test_disabled_gateway_is_skipped(self):
        c = configs()
        c[1] = GatewayConfig("paystack", c[1].currencies, c[1].home_countries, enabled=False)
        r = GatewayRouter(c, HealthTracker(Clock()))
        self.assertEqual(r.choose(currency="USD", country="NG"), ["stripe"])

    def test_circuit_opens_after_repeated_failures_and_recovers(self):
        r = self.router()
        for _ in range(3):
            r.health.record_failure("paystack")
        self.assertEqual(r.choose(currency="USD", country="NG"), ["stripe"])
        self.clock.t += 121
        self.assertEqual(r.choose(currency="USD", country="NG"), ["paystack", "stripe"])

    def test_old_failures_age_out_of_the_window(self):
        r = self.router()
        r.health.record_failure("stripe"); r.health.record_failure("stripe")
        self.clock.t += 61
        r.health.record_failure("stripe")
        self.assertFalse(r.health.is_open("stripe"))

    def test_if_everything_is_down_we_still_try(self):
        r = self.router()
        for code in ("stripe", "paystack"):
            for _ in range(3):
                r.health.record_failure(code)
        self.assertEqual(r.choose(currency="USD", country="NG"), ["paystack", "stripe"])


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.stripe = FakeGateway("stripe", {"USD", "EUR"})
        self.paystack = FakeGateway("paystack", {"NGN", "USD"})
        self.repo = MemoryRepo()
        self.router = GatewayRouter(configs(), HealthTracker(Clock()))
        self.gws = {"stripe": self.stripe, "paystack": self.paystack}

    def go(self, amount=None, key="k1", country="NG", **kw):
        return start_checkout(repo=self.repo, router=self.router, gateways=self.gws, user_id="u1", email="a@b.co",
                              amount=amount or NGN(5000), country=country, idempotency_key=key,
                              success_url="https://x/ok", cancel_url="https://x/no", **kw)

    def test_naira_goes_to_paystack_and_the_record_exists_first(self):
        p = self.go()
        self.assertEqual((p.provider, p.status), ("paystack", S.PENDING))
        self.assertTrue(p.reference.startswith("pay_"))
        self.assertIn(p.reference, p.redirect_url)
        self.assertEqual(self.stripe.calls, 0)

    def test_same_key_returns_the_same_checkout_without_a_second_call(self):
        a, b = self.go(), self.go()
        self.assertEqual(a.reference, b.reference)
        self.assertEqual(self.paystack.calls, 1)
        self.assertEqual(len(self.repo.by_ref), 1)

    def test_same_key_different_amount_is_refused(self):
        self.go()
        with self.assertRaises(CheckoutFailed):
            self.go(amount=NGN(9000))

    def test_definite_rejection_fails_over_to_the_next_gateway(self):
        self.paystack.mode = "reject"
        p = self.go(amount=Money(1000, "USD"))
        self.assertEqual(p.provider, "stripe")
        self.assertEqual(p.attempts, ("paystack", "stripe"))

    def test_uncertain_failure_never_fails_over(self):
        self.paystack.mode = "uncertain"
        with self.assertRaises(CheckoutFailed) as ctx:
            self.go(amount=Money(1000, "USD"))
        self.assertTrue(ctx.exception.retry_same_key)
        self.assertEqual(self.stripe.calls, 0)
        self.assertEqual(next(iter(self.repo.by_ref.values())).provider, "paystack")

    def test_everything_rejecting_marks_the_payment_failed(self):
        self.paystack.mode = self.stripe.mode = "reject"
        with self.assertRaises(CheckoutFailed):
            self.go(amount=Money(1000, "USD"))
        self.assertEqual(next(iter(self.repo.by_ref.values())).status, S.FAILED)

    def test_unsupported_currency_and_bad_amounts(self):
        with self.assertRaises(CheckoutFailed):
            self.go(amount=Money(0, "NGN"), key="k8")
        with self.assertRaises(CheckoutFailed):
            self.go(amount=Money(1000, "KRW"), key="k7")


class EventTests(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryRepo()
        from core.payments.checkout import PaymentRecord
        self.repo.create(PaymentRecord("pay_abc", "k", "u1", Money(500000, "NGN"), provider="paystack"))

    def apply(self, event):
        return apply_event(event, self.repo, now=NOW)

    def success(self, **kw):
        return ev("s", reference="pay_abc", amount_minor=kw.get("amount", 500000), currency=kw.get("currency", "NGN"))

    def test_success_fulfils_once(self):
        self.assertEqual(self.apply(self.success()), "fulfilled")
        self.assertEqual(self.repo.get("pay_abc").status, S.SUCCEEDED)
        self.assertEqual(self.repo.get("pay_abc").paid_at, NOW)
        self.assertEqual(self.apply(self.success()), "already_applied")

    def test_wrong_amount_or_currency_is_not_fulfilled(self):
        self.assertEqual(self.apply(self.success(amount=100)), "amount_mismatch")
        self.assertEqual(self.apply(self.success(currency="USD")), "amount_mismatch")
        self.assertEqual(self.repo.get("pay_abc").status, S.PENDING)

    def test_unknown_reference_and_ignored_events(self):
        self.assertEqual(self.apply(ev(reference="nope")), "unknown_reference")
        self.assertEqual(self.apply(ev(typ=EventType.IGNORED)), "ignored")

    def test_late_failure_does_not_undo_success(self):
        self.apply(self.success())
        self.assertEqual(self.apply(ev("f", EventType.PAYMENT_FAILED, reference="pay_abc")), "late_failure_ignored")
        self.assertEqual(self.repo.get("pay_abc").status, S.SUCCEEDED)

    def test_failed_then_late_success(self):
        self.assertEqual(self.apply(ev("f", EventType.PAYMENT_FAILED, reference="pay_abc")), "failed")
        self.assertEqual(self.apply(self.success()), "fulfilled")

    def test_cumulative_refunds_are_idempotent(self):
        self.apply(self.success())
        r = lambda amt: ev("r", EventType.REFUND_UPDATED, reference="pay_abc", amount_minor=amt, amount_is_cumulative=True)  # noqa: E731
        self.assertEqual(self.apply(r(200000)), "refund_recorded")
        self.assertEqual(self.repo.get("pay_abc").status, S.PARTIALLY_REFUNDED)
        self.assertEqual(self.apply(r(200000)), "already_applied")
        self.assertEqual(self.apply(r(500000)), "refund_recorded")
        self.assertEqual(self.repo.get("pay_abc").status, S.REFUNDED)

    def test_incremental_refund_events_add_up_and_cap_at_total(self):
        self.apply(self.success())
        r = lambda i, amt: ev(i, EventType.REFUND_UPDATED, reference="pay_abc", amount_minor=amt)  # noqa: E731
        self.apply(r("a", 200000)); self.apply(r("b", 400000))
        p = self.repo.get("pay_abc")
        self.assertEqual((p.refunded_minor, p.status), (500000, S.REFUNDED))

    def test_refund_before_payment_is_flagged(self):
        out = self.apply(ev("r", EventType.REFUND_UPDATED, reference="pay_abc", amount_minor=100, amount_is_cumulative=True))
        self.assertEqual(out, "refund_on_unpaid_payment")

    def test_dispute(self):
        self.apply(self.success())
        self.assertEqual(self.apply(ev("d", EventType.DISPUTE_OPENED, reference="pay_abc")), "disputed")


class RefundTests(unittest.TestCase):
    def check(self, **kw):
        base = dict(status=S.SUCCEEDED, paid_at=NOW - timedelta(days=3), now=NOW, total=NGN(5000),
                    already_refunded=NGN(0), requested=NGN(5000))
        base.update(kw)
        return rf.validate_refund(**base)

    def code(self, **kw):
        with self.assertRaises(rf.RefundNotAllowed) as ctx:
            self.check(**kw)
        return ctx.exception.code

    def test_full_and_partial_refunds(self):
        self.assertEqual(self.check(), NGN(5000))
        self.assertEqual(self.check(requested=NGN(1200)), NGN(1200))

    def test_cannot_exceed_remaining(self):
        self.assertEqual(self.code(already_refunded=NGN(4000), requested=NGN(1500)), "exceeds_remaining")

    def test_state_and_currency_and_amount_checks(self):
        self.assertEqual(self.code(status=S.PENDING), "not_refundable_state")
        self.assertEqual(self.code(status=S.REFUNDED), "not_refundable_state")
        self.assertEqual(self.code(status=S.DISPUTED), "disputed")
        self.assertEqual(self.code(requested=Money(100, "USD")), "currency_mismatch")
        self.assertEqual(self.code(requested=NGN(0)), "non_positive")

    def test_window_and_staff_override(self):
        old = NOW - timedelta(days=45)
        self.assertEqual(self.code(paid_at=old), "window_closed")
        self.assertEqual(self.check(paid_at=old, staff_override=True), NGN(5000))

    def test_full_only_policy(self):
        pol = rf.RefundPolicy(allow_partial=False)
        self.assertEqual(self.code(requested=NGN(100), policy=pol), "partial_not_allowed")
        self.assertEqual(self.check(policy=pol), NGN(5000))

    def test_status_after_refund(self):
        self.assertEqual(rf.status_after_refund(NGN(100), NGN(100)), S.REFUNDED)
        self.assertEqual(rf.status_after_refund(NGN(100), NGN(40)), S.PARTIALLY_REFUNDED)
        self.assertEqual(rf.status_after_refund(NGN(100), NGN(0)), S.SUCCEEDED)

    def test_refund_key_is_stable_and_changes_with_state(self):
        a = rf.refund_idempotency_key("pay_1", NGN(0), NGN(10))
        self.assertEqual(a, rf.refund_idempotency_key("pay_1", NGN(0), NGN(10)))
        self.assertNotEqual(a, rf.refund_idempotency_key("pay_1", NGN(10), NGN(10)))

    def test_gateway_refund_with_same_key_is_not_repeated(self):
        gw = FakeGateway("paystack", {"NGN"})
        k = rf.refund_idempotency_key("pay_1", NGN(0), NGN(10))
        self.assertEqual(gw.refund(reference="pay_1", provider_ref="x", amount=NGN(10), idempotency_key=k), gw.refund(reference="pay_1", provider_ref="x", amount=NGN(10), idempotency_key=k))
        self.assertEqual(len(gw.refunds), 1)


class InvoiceTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(invoice_number("INV", 2026, 123), "INV-2026-000123")
        with self.assertRaises(ValueError):
            invoice_number("INV", 2026, 0)

    def test_tax_added_on_top(self):
        t = totals_for([Line("Pro plan", 1, NGN(10000))], 750, prices_include_tax=False)
        self.assertEqual((t.net, t.tax, t.gross), (NGN(10000), NGN(750), NGN(10750)))

    def test_tax_inclusive_prices(self):
        t = totals_for([Line("Pro plan", 1, NGN(10750))], 750, prices_include_tax=True)
        self.assertEqual((t.net, t.tax, t.gross), (NGN(10000), NGN(750), NGN(10750)))

    def test_parts_always_add_up_for_awkward_amounts(self):
        for minor in (1, 7, 99, 101, 12345, 99999, 1000001):
            for inclusive in (True, False):
                t = totals_for([Line("x", 1, Money(minor, "NGN"))], 750, prices_include_tax=inclusive)
                self.assertEqual(t.net + t.tax, t.gross, (minor, inclusive))

    def test_multiple_lines_round_once(self):
        lines = [Line("a", 3, Money(333, "NGN")), Line("b", 1, Money(1, "NGN"))]
        t = totals_for(lines, 750, prices_include_tax=False)
        self.assertEqual(t.net.amount_minor, 1000)
        self.assertEqual(t.tax.amount_minor, 75)

    def test_empty_invoice_rejected(self):
        with self.assertRaises(ValueError):
            totals_for([], 750, prices_include_tax=False)

    def test_credit_note_splits_proportionally_and_adds_up(self):
        original = totals_for([Line("Pro", 1, NGN(10000))], 750, prices_include_tax=False)
        for refund_minor in (1, 333, 500000, 1075000):
            c = credit_note_totals(original, Money(refund_minor, "NGN"))
            self.assertEqual(c.net + c.tax, c.gross)
        full = credit_note_totals(original, original.gross)
        self.assertEqual((full.net, full.tax), (original.net, original.tax))
        with self.assertRaises(ValueError):
            credit_note_totals(original, Money(original.gross.amount_minor + 1, "NGN"))


def L(ref, amt=500000, cur="NGN", status="succeeded", refunded=0, fee=0):
    return rc.Line(ref, amt, cur, status, refunded, fee)


class ReconciliationTests(unittest.TestCase):
    def kinds(self, ours, theirs):
        return {d.reference: d.kind for d in rc.reconcile(ours, theirs).discrepancies}

    def test_clean_run(self):
        r = rc.reconcile([L("a"), L("b", 100)], [L("a", fee=7500), L("b", 100)])
        self.assertTrue(r.clean)
        self.assertEqual((r.matched, r.fees), (2, {"NGN": 7500}))

    def test_each_kind_of_discrepancy(self):
        k = self.kinds([L("only_us"), L("amt"), L("cur"), L("st")],
                       [L("only_them"), L("amt", 1), L("cur", cur="USD"), L("st", status="refunded", refunded=500000)])
        self.assertEqual(k, {"only_us": rc.Kind.MISSING_AT_GATEWAY, "only_them": rc.Kind.MISSING_INTERNAL,
                             "amt": rc.Kind.AMOUNT_MISMATCH, "cur": rc.Kind.CURRENCY_MISMATCH, "st": rc.Kind.STATUS_MISMATCH})

    def test_refunded_amount_difference_is_a_status_mismatch(self):
        k = self.kinds([L("a", status="partially_refunded", refunded=100)], [L("a", status="partially_refunded", refunded=200)])
        self.assertEqual(k["a"], rc.Kind.STATUS_MISMATCH)

    def test_duplicates_are_reported(self):
        r = rc.reconcile([L("a"), L("a")], [L("a")])
        self.assertIn(rc.Kind.DUPLICATE_REFERENCE, r.count())

    def test_totals_net_of_refunds_per_currency(self):
        r = rc.reconcile([L("a", 1000, refunded=200), L("b", 50, "USD")], [L("a", 1000, refunded=200), L("b", 50, "USD")])
        self.assertEqual(r.gateway_total, {"NGN": 800, "USD": 50})
        self.assertEqual(r.internal_total, r.gateway_total)


class FakeGatewayWebhookTests(unittest.TestCase):
    def test_signed_fake_webhook_round_trip(self):
        gw = FakeGateway("stripe", {"USD"})
        raw = json.dumps({"id": "e9", "type": "payment_succeeded", "reference": "pay_x", "amount": 5, "currency": "USD"}).encode()
        gw.verify_webhook(raw, {"x-fake-signature": gw.sign(raw)}, now=0)
        self.assertEqual(gw.parse_webhook(raw).reference, "pay_x")
        with self.assertRaises(SignatureError):
            gw.verify_webhook(raw, {"x-fake-signature": "bad"}, now=0)


if __name__ == "__main__":
    unittest.main()
