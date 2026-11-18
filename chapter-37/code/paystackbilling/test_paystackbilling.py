"""Tests for the Paystack billing code. Plain unittest: no network, no Paystack account, no Django."""
import contextlib
import hashlib
import hmac
import io
import json
from dataclasses import replace
from decimal import Decimal
from unittest import TestCase

from paystackbilling import cli
from paystackbilling.config import PaystackConfig, Plan, new_reference
from paystackbilling.entitlements import DAY, FREE, decide_access
from paystackbilling.errors import (AlreadySubscribed, BadAmount, BadRedirectUrl, ForbiddenReference, NoSubscription,
                                    PaystackApiError, PaystackNetworkError, SignatureError, UnknownPlan)
from paystackbilling.fakes import FakeGateway
from paystackbilling.fixtures import START, body_of, charge_data, event, invoice_data, iso, subscription_obj
from paystackbilling.gateway import BASE_URL, PaystackGateway
from paystackbilling.handlers import PaystackHandlers, apply_charge, place_snapshot
from paystackbilling.money import CURRENCIES, check_currency, format_money, from_subunit, to_subunit
from paystackbilling.params import check_callback_url, initialize_params, subscription_params
from paystackbilling.service import PaystackBillingService, User
from paystackbilling.simulate import SECRET, Clock, build_world, deliver, demo_config, run_simulation
from paystackbilling.snapshots import iso_time, parse_time, subscription_snapshot
from paystackbilling.store import InMemoryBillingStore, PendingTransaction, SubscriptionRecord
from paystackbilling.webhooks import PaystackVerifier, WebhookProcessor, event_key, sign_body, source_ip_allowed

CONFIG = demo_config()
USER = User("user-1", "ada@example.com", "Ada")


def rec(status="active", **kw):
    base = dict(user_id="user-1", customer_code="CUS_001", subscription_code="SUB_001", email_token="tok_001",
                status=status, plan_key="pro_monthly_ngn", tier="pro", next_payment_date=START + 30 * DAY)
    base.update(kw)
    return SubscriptionRecord(**base)


class MoneyTests(TestCase):
    def test_naira_and_dollars_become_whole_smallest_units(self):
        self.assertEqual(to_subunit("5000", "NGN"), 500000)
        self.assertEqual(to_subunit(Decimal("49.99"), "usd"), 4999)
        self.assertEqual(to_subunit(20, "NGN"), 2000)
        self.assertEqual(to_subunit("0.01", "NGN"), 1)

    def test_floats_are_refused_because_they_are_not_exact(self):
        for bad in [0.1, 49.99, 5000.0, True, None]:
            with self.assertRaises(BadAmount):
                to_subunit(bad, "NGN")

    def test_too_many_decimals_is_an_error_not_a_rounding(self):
        with self.assertRaises(BadAmount):
            to_subunit("49.999", "USD")
        self.assertEqual(to_subunit("49.990", "USD"), 4999)

    def test_garbage_and_non_finite_numbers_are_rejected(self):
        for bad in ["abc", "", "1e999999999", "NaN", "Infinity"]:
            with self.assertRaises(BadAmount):
                to_subunit(bad, "NGN")

    def test_only_listed_currencies_are_accepted(self):
        self.assertEqual(check_currency("ngn"), "NGN")
        for bad in ["EUR", "", None, "naira"]:
            with self.assertRaises(ValueError):
                check_currency(bad)
        self.assertEqual(set(CURRENCIES), {"NGN", "GHS", "ZAR", "KES", "USD", "XOF"})

    def test_round_trip_and_formatting(self):
        self.assertEqual(from_subunit(500000, "NGN"), Decimal("5000"))
        self.assertEqual(format_money(500000, "NGN"), "\u20a65,000.00")
        self.assertEqual(format_money(4999, "USD"), "$49.99")
        self.assertEqual(format_money(123456789, "GHS"), "GH\u20b51,234,567.89")
        with self.assertRaises(BadAmount):
            from_subunit(5.5, "NGN")

    def test_the_famous_float_trap_does_not_happen(self):
        self.assertEqual(to_subunit(Decimal("0.1") + Decimal("0.2"), "NGN"), 30)


class ConfigTests(TestCase):
    def test_lookups(self):
        self.assertEqual(CONFIG.plan("pro_monthly_ngn").plan_code, "PLN_pro_m")
        self.assertEqual(CONFIG.plan_for_code("PLN_team_m").key, "team_monthly_ngn")
        self.assertIsNone(CONFIG.plan_for_code("PLN_nope"))
        self.assertIsNone(CONFIG.plan_for_code(""))
        with self.assertRaises(UnknownPlan):
            CONFIG.plan("pro_lifetime")

    def test_a_price_list_per_currency(self):
        self.assertEqual({p.key for p in CONFIG.plans_for_currency("usd")}, {"pro_monthly_usd"})
        self.assertEqual(len(CONFIG.plans_for_currency("NGN")), 4)
        with self.assertRaises(ValueError):
            CONFIG.plans_for_currency("EUR")

    def test_plans_validate_themselves(self):
        with self.assertRaises(ValueError):
            Plan("x", "pro", "monthly", 1000, "NGN")                   # recurring without a plan code
        for amount in [0, -5, 10.5, True]:
            with self.assertRaises(ValueError):
                Plan("x", "pro", "once", amount, "NGN")
        with self.assertRaises(ValueError):
            Plan("x", "pro", "once", 1000, "EUR")

    def test_references_are_unique_and_use_allowed_characters(self):
        refs = {new_reference() for _ in range(200)}
        self.assertEqual(len(refs), 200)
        self.assertTrue(all(all(c.isalnum() or c in "_-.=" for c in r) for r in refs))


class ParamsTests(TestCase):
    HOSTS = frozenset({"app.example.com"})

    def build(self, **kw):
        args = dict(email="ada@example.com", amount=500000, currency="NGN", reference="ref_1",
                    callback_url="https://app.example.com/billing/callback", allowed_hosts=self.HOSTS,
                    user_id="user-1", plan_key="pro_monthly_ngn", kind="subscription")
        args.update(kw)
        return initialize_params(**args)

    def test_a_subscription_payment_carries_the_plan_code(self):
        params = self.build(plan_code="PLN_pro_m")
        self.assertEqual(params["plan"], "PLN_pro_m")
        self.assertEqual(params["metadata"], {"user_id": "user-1", "plan_key": "pro_monthly_ngn", "kind": "subscription"})
        self.assertEqual((params["amount"], params["currency"], params["reference"]), (500000, "NGN", "ref_1"))

    def test_a_one_time_payment_has_no_plan_and_optional_channels(self):
        params = self.build(kind="one_time", channels=["card", "bank_transfer"])
        self.assertNotIn("plan", params)
        self.assertEqual(params["channels"], ["card", "bank_transfer"])
        self.assertNotIn("channels", self.build())

    def test_amounts_must_be_positive_whole_numbers(self):
        for bad in [0, -1, 10.5, "5000", True, None]:
            with self.assertRaises(ValueError):
                self.build(amount=bad)

    def test_callback_urls_must_use_allowed_hosts(self):
        for bad in ["https://evil.example/x", "javascript:alert(1)", "http://app.example.com/x", "//evil.example"]:
            with self.assertRaises(BadRedirectUrl):
                check_callback_url(bad, self.HOSTS)
        check_callback_url("http://localhost:3000/cb", frozenset({"localhost"}))

    def test_subscription_parameters_with_and_without_a_start_date(self):
        base = subscription_params(customer_code="CUS_1", plan_code="PLN_1", authorization_code="AUTH_1")
        self.assertEqual(base, {"customer": "CUS_1", "plan": "PLN_1", "authorization": "AUTH_1"})
        delayed = subscription_params(customer_code="CUS_1", plan_code="PLN_1", authorization_code="AUTH_1", start_date="2027-01-01T00:00:00+00:00")
        self.assertEqual(delayed["start_date"], "2027-01-01T00:00:00+00:00")


class SnapshotTests(TestCase):
    def test_time_parsing(self):
        self.assertEqual(parse_time("2026-12-20T00:00:00.000Z"), parse_time("2026-12-20T00:00:00+00:00"))
        self.assertEqual(parse_time("2026-12-20T01:00:00+01:00"), parse_time("2026-12-20T00:00:00Z"))
        self.assertEqual(parse_time("2026-12-20T00:00:00"), parse_time("2026-12-20T00:00:00Z"))
        self.assertIsNone(parse_time(None))
        self.assertIsNone(parse_time(""))

    def test_iso_round_trip(self):
        self.assertEqual(parse_time(iso_time(START)), START)
        self.assertTrue(iso_time(START).endswith("+00:00"))

    def test_a_subscription_is_read_into_our_shape(self):
        snap = subscription_snapshot(subscription_obj(), CONFIG)
        self.assertEqual((snap.subscription_code, snap.status, snap.plan_key, snap.tier), ("SUB_001", "active", "pro_monthly_ngn", "pro"))
        self.assertEqual((snap.customer_code, snap.authorization_code, snap.card_last4), ("CUS_001", "AUTH_001", "4081"))
        self.assertEqual(snap.next_payment_date, START + 30 * DAY)

    def test_unknown_plans_and_missing_dates(self):
        snap = subscription_snapshot(subscription_obj(plan_code="PLN_mystery", next_payment=None), CONFIG)
        self.assertEqual((snap.plan_key, snap.tier, snap.next_payment_date), (None, "free", None))


class EntitlementTests(TestCase):
    NOW = START + 10 * DAY

    def test_no_record_means_free(self):
        self.assertEqual(decide_access(None, self.NOW), FREE)

    def test_active_is_paid_until_the_next_payment_date(self):
        decision = decide_access(rec(), self.NOW)
        self.assertEqual((decision.paid, decision.reason, decision.until), (True, "active", START + 30 * DAY))

    def test_a_late_renewal_gets_a_grace_period_then_ends(self):
        due = START + 30 * DAY
        self.assertTrue(decide_access(rec(), due + DAY, 3).paid)
        self.assertEqual(decide_access(rec(), due + DAY, 3).reason, "renewal payment pending, in the grace period")
        gone = decide_access(rec(), due + 4 * DAY, 3)
        self.assertEqual((gone.paid, gone.tier), (False, "free"))

    def test_attention_is_paid_until_the_date_then_grace(self):
        due = START + 30 * DAY
        self.assertEqual(decide_access(rec("attention"), self.NOW).reason, "last renewal failed, update your card")
        self.assertTrue(decide_access(rec("attention"), due + 2 * DAY, 3).paid)
        self.assertFalse(decide_access(rec("attention"), due + 4 * DAY, 3).paid)

    def test_non_renewing_is_paid_to_the_date_with_no_grace(self):
        due = START + 30 * DAY
        self.assertTrue(decide_access(rec("non-renewing"), due - 1, 3).paid)
        self.assertFalse(decide_access(rec("non-renewing"), due + 1, 3).paid)
        self.assertFalse(decide_access(rec("non-renewing", next_payment_date=None), self.NOW).paid)

    def test_a_trial_is_reported_as_a_trial(self):
        decision = decide_access(rec(trial_end=START + 14 * DAY), self.NOW)
        self.assertEqual((decision.paid, decision.reason), (True, "free trial"))
        self.assertEqual(decide_access(rec(trial_end=START + 14 * DAY), START + 15 * DAY).reason, "active")

    def test_ended_and_unknown_statuses_get_no_access(self):
        for status in ["cancelled", "completed", "something_new"]:
            self.assertFalse(decide_access(rec(status), self.NOW).paid, status)
        self.assertIn("something_new", decide_access(rec("something_new"), self.NOW).reason)

    def test_active_with_no_date_is_trusted(self):
        self.assertTrue(decide_access(rec(next_payment_date=None), self.NOW).paid)


class WebhookSignatureTests(TestCase):
    def setUp(self):
        self.verifier = PaystackVerifier(SECRET)
        self.body = body_of(event("charge.success", {"reference": "r1", "domain": "test"}))

    def test_a_correct_signature_returns_the_event(self):
        self.assertEqual(self.verifier.verify(self.body, sign_body(self.body, SECRET))["event"], "charge.success")

    def test_wrong_key_changed_body_and_missing_header_are_rejected(self):
        for body, sig in [(self.body, sign_body(self.body, "sk_test_other")), (self.body + b" ", sign_body(self.body, SECRET)),
                          (self.body, ""), (self.body, "garbage")]:
            with self.assertRaises(SignatureError):
                self.verifier.verify(body, sig)

    def test_a_sha256_signature_is_rejected_because_paystack_uses_sha512(self):
        weak = hmac.new(SECRET.encode(), self.body, hashlib.sha256).hexdigest()
        with self.assertRaises(SignatureError):
            self.verifier.verify(self.body, weak)

    def test_uppercase_hex_and_spaces_are_tolerated(self):
        self.verifier.verify(self.body, "  " + sign_body(self.body, SECRET).upper() + " ")

    def test_a_signed_body_must_be_a_json_event(self):
        for body in [b"not json", b'"a string"', b'{"no_event": 1}']:
            with self.assertRaises(SignatureError):
                self.verifier.verify(body, sign_body(body, SECRET))

    def test_the_verifier_needs_the_secret_key_not_the_public_one(self):
        for bad in ["pk_test_123", "whsec_123", ""]:
            with self.assertRaises(ValueError):
                PaystackVerifier(bad)

    def test_events_are_identified_by_their_bytes(self):
        self.assertEqual(event_key(self.body), event_key(self.body))
        self.assertNotEqual(event_key(self.body), event_key(self.body + b" "))
        self.assertEqual(len(event_key(self.body)), 64)

    def test_the_source_ip_check(self):
        self.assertTrue(source_ip_allowed("52.31.139.75"))
        self.assertFalse(source_ip_allowed("1.2.3.4"))
        self.assertFalse(source_ip_allowed("10.0.0.1", "52.31.139.75"))                 # header ignored without a trusted proxy
        self.assertTrue(source_ip_allowed("10.0.0.1", "52.31.139.75, 10.0.0.1", trust_proxy=True))


class ProcessorTests(TestCase):
    def setUp(self):
        self.clock, self.config, self.store, self.gateway, self.service, self.processor, self.sent = build_world()

    def make(self, handlers):
        return WebhookProcessor(PaystackVerifier(SECRET), self.store, handlers, livemode=False, clock=self.clock)

    def test_a_good_event_is_processed_and_logged(self):
        runs = []
        processor = self.make({"x.y": lambda e: runs.append(e["event"])})
        body = body_of(event("x.y", {"domain": "test"}))
        result = processor.handle(body, sign_body(body, SECRET))
        self.assertEqual((result.status, result.outcome, runs), (200, "processed", ["x.y"]))
        self.assertEqual(self.store.event(event_key(body))["status"], "processed")

    def test_the_same_bytes_twice_run_the_handler_once(self):
        runs = []
        processor = self.make({"x.y": lambda e: runs.append(1)})
        body = body_of(event("x.y", {"domain": "test"}))
        first, second = processor.handle(body, sign_body(body, SECRET)), processor.handle(body, sign_body(body, SECRET))
        self.assertEqual((first.outcome, second.outcome, second.status, len(runs)), ("processed", "duplicate", 200, 1))

    def test_a_failing_handler_gets_500_and_succeeds_on_the_retry(self):
        attempts = []

        def flaky(e):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("database down")
        processor = self.make({"x.y": flaky})
        body = body_of(event("x.y", {"domain": "test"}))
        first = processor.handle(body, sign_body(body, SECRET))
        self.assertEqual((first.status, first.outcome), (500, "handler_failed"))
        key = event_key(body)
        self.assertIn("database down", self.store.event(key)["error"])
        self.assertEqual(processor.handle(body, sign_body(body, SECRET)).status, 200)
        self.assertEqual(self.store.event(key)["attempts"], 2)

    def test_busy_events_get_409_until_the_lease_runs_out(self):
        processor = self.make({"x.y": lambda e: None})
        body = body_of(event("x.y", {"domain": "test"}))
        self.store.begin_event(event_key(body), "x.y", self.clock(), 300)
        self.assertEqual(processor.handle(body, sign_body(body, SECRET)).status, 409)
        self.clock.t += 301
        self.assertEqual(processor.handle(body, sign_body(body, SECRET)).status, 200)

    def test_unknown_events_and_the_other_mode_get_200(self):
        processor = self.make({})
        unknown = body_of(event("transfer.success", {"domain": "test"}))
        self.assertEqual(processor.handle(unknown, sign_body(unknown, SECRET)).outcome, "ignored")
        live = body_of(event("charge.success", {"domain": "live"}))
        result = processor.handle(live, sign_body(live, SECRET))
        self.assertEqual((result.status, result.outcome), (200, "ignored_wrong_mode"))
        self.assertIsNone(self.store.event(event_key(live)))

    def test_bad_signatures_get_400_and_run_nothing(self):
        runs = []
        processor = self.make({"x.y": lambda e: runs.append(1)})
        body = body_of(event("x.y", {"domain": "test"}))
        result = processor.handle(body, sign_body(body, "sk_test_wrong"))
        self.assertEqual((result.status, result.outcome, runs), (400, "bad_signature", []))

    def test_a_captured_request_replayed_much_later_does_nothing(self):
        """Paystack signatures have no timestamp, so the event log is the only replay defence."""
        runs = []
        processor = self.make({"x.y": lambda e: runs.append(1)})
        body = body_of(event("x.y", {"domain": "test"}))
        processor.handle(body, sign_body(body, SECRET))
        self.clock.t += 400 * DAY
        self.assertEqual(processor.handle(body, sign_body(body, SECRET)).outcome, "duplicate")
        self.assertEqual(len(runs), 1)


class StubResponse:
    def __init__(self, status_code=200, body=None, text_error=False):
        self.status_code, self._body, self._text_error = status_code, body, text_error

    def json(self):
        if self._text_error:
            raise ValueError("not json")
        return self._body


class StubSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error:
            raise self.error
        return self.response


class GatewayTests(TestCase):
    KEY = "sk_test_secretsecretsecret"

    def gateway(self, response=None, error=None):
        self.session = StubSession(response, error)
        return PaystackGateway(self.KEY, session=self.session)

    def test_calls_send_the_bearer_key_and_return_the_data(self):
        gw = self.gateway(StubResponse(200, {"status": True, "message": "ok", "data": {"reference": "r1"}}))
        self.assertEqual(gw.verify_transaction("r1"), {"reference": "r1"})
        method, url, kwargs = self.session.calls[0]
        self.assertEqual((method, url), ("GET", BASE_URL + "/transaction/verify/r1"))
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer " + self.KEY)
        self.assertEqual(kwargs["timeout"], (5, 30))

    def test_the_paths_and_bodies_of_each_call(self):
        gw = self.gateway(StubResponse(200, {"status": True, "data": {"link": "https://x"}}))
        gw.initialize_transaction({"a": 1})
        gw.create_subscription({"b": 2})
        gw.disable_subscription("SUB_1", "tok")
        gw.enable_subscription("SUB_1", "tok")
        self.assertEqual(gw.manage_link("SUB_1"), "https://x")
        gw.fetch_subscription("SUB_1")
        gw.fetch_customer("CUS_1")
        gw.create_plan({"name": "p"})
        got = [(c[0], c[1].replace(BASE_URL, ""), c[2].get("json")) for c in self.session.calls]
        self.assertEqual(got, [("POST", "/transaction/initialize", {"a": 1}), ("POST", "/subscription", {"b": 2}),
                               ("POST", "/subscription/disable", {"code": "SUB_1", "token": "tok"}),
                               ("POST", "/subscription/enable", {"code": "SUB_1", "token": "tok"}),
                               ("GET", "/subscription/SUB_1/manage/link", None), ("GET", "/subscription/SUB_1", None),
                               ("GET", "/customer/CUS_1", None), ("POST", "/plan", {"name": "p"})])

    def test_status_false_is_an_api_error_with_paystacks_message(self):
        gw = self.gateway(StubResponse(400, {"status": False, "message": "Duplicate Transaction Reference"}))
        with self.assertRaises(PaystackApiError) as ctx:
            gw.initialize_transaction({})
        self.assertIn("Duplicate", str(ctx.exception))
        self.assertEqual(ctx.exception.http_status, 400)

    def test_server_errors_and_connection_problems_are_retryable(self):
        with self.assertRaises(PaystackNetworkError):
            self.gateway(StubResponse(503, {})).verify_transaction("r")
        with self.assertRaises(PaystackNetworkError):
            self.gateway(error=TimeoutError("slow")).verify_transaction("r")

    def test_the_secret_key_never_appears_in_an_error_message(self):
        with self.assertRaises(PaystackNetworkError) as ctx:
            self.gateway(error=ConnectionError(f"failed with {self.KEY}")).verify_transaction("r")
        self.assertNotIn(self.KEY, str(ctx.exception))

    def test_a_non_json_answer_is_an_api_error(self):
        with self.assertRaises(PaystackApiError):
            self.gateway(StubResponse(200, None, text_error=True)).verify_transaction("r")

    def test_only_secret_keys_are_accepted(self):
        for key in ["pk_test_123", "whsec_1", "", "sk"]:
            with self.assertRaises(ValueError):
                PaystackGateway(key, session=StubSession())


class ServiceTests(TestCase):
    def setUp(self):
        self.clock, self.config, self.store, self.gateway, self.service, self.processor, self.sent = build_world()

    # ---- starting payments ----------------------------------------------------------------------
    def test_a_one_time_payment_takes_its_amount_from_the_server_table(self):
        start = self.service.start_payment(USER, "credits_100")
        params = self.gateway.called("initialize_transaction")[0][1]
        self.assertEqual((params["amount"], params["currency"], params["reference"]), (200000, "NGN", start.reference))
        self.assertNotIn("plan", params)
        self.assertTrue(start.authorization_url.startswith("https://checkout.paystack.com/"))

    def test_the_expected_payment_is_saved_before_the_customer_leaves(self):
        start = self.service.start_payment(USER, "credits_100")
        pending = self.store.pending(start.reference)
        self.assertEqual((pending.user_id, pending.plan_key, pending.kind, pending.amount, pending.status),
                         ("user-1", "credits_100", "one_time", 200000, "pending"))

    def test_unknown_and_wrong_kind_plans_are_refused_before_paystack_is_called(self):
        for call in [lambda: self.service.start_payment(USER, "free"), lambda: self.service.start_payment(USER, "pro_monthly_ngn"),
                     lambda: self.service.start_subscription(USER, "credits_100"), lambda: self.service.start_subscription(USER, "plan_PLN_pro_m")]:
            with self.assertRaises(UnknownPlan):
                call()
        self.assertEqual(self.gateway.calls, [])

    def test_a_subscription_with_a_trial_first_saves_a_card(self):
        start = self.service.start_subscription(USER, "pro_monthly_ngn")
        params = self.gateway.called("initialize_transaction")[0][1]
        self.assertEqual((params["amount"], params["metadata"]["kind"]), (5000, "trial_authorization"))
        self.assertNotIn("plan", params)
        self.assertEqual(self.store.pending(start.reference).plan_key, "pro_monthly_ngn")

    def test_a_subscription_without_a_trial_carries_the_plan_code(self):
        self.service.start_subscription(USER, "team_monthly_ngn")
        params = self.gateway.called("initialize_transaction")[0][1]
        self.assertEqual((params["plan"], params["amount"], params["metadata"]["kind"]), ("PLN_team_m", 1500000, "subscription"))

    def test_the_trial_is_offered_once(self):
        self.store.mark_trial_used("user-1")
        self.service.start_subscription(USER, "pro_monthly_ngn")
        params = self.gateway.called("initialize_transaction")[0][1]
        self.assertEqual((params["plan"], params["metadata"]["kind"]), ("PLN_pro_m", "subscription"))

    def test_no_second_subscription_while_one_is_running(self):
        self.store.save_subscription(rec())
        with self.assertRaises(AlreadySubscribed):
            self.service.start_subscription(USER, "team_monthly_ngn")
        self.store.save_subscription(rec("cancelled"))
        self.service.start_subscription(USER, "team_monthly_ngn")

    def test_an_expired_subscription_can_be_replaced(self):
        self.store.save_subscription(rec("non-renewing", next_payment_date=START - DAY))
        self.service.start_subscription(USER, "team_monthly_ngn")

    def test_every_payment_gets_its_own_reference(self):
        a, b = self.service.start_payment(USER, "credits_100"), self.service.start_payment(USER, "credits_100")
        self.assertNotEqual(a.reference, b.reference)

    # ---- the callback page ---------------------------------------------------------------------
    def test_a_paid_one_time_purchase_grants_credits_once_across_callback_and_webhook(self):
        start = self.service.start_payment(USER, "credits_100")
        data = self.gateway.pay(start.reference)
        first = self.service.verify_payment(USER, start.reference)
        second = self.service.verify_payment(USER, start.reference)
        deliver(self.processor, event("charge.success", data))
        self.assertEqual((first["status"], first["credits"], second["credits"]), ("paid", 100, 100))
        self.assertEqual(self.store.credit_balance("user-1"), 100)
        self.assertEqual(len(self.gateway.called("verify_transaction")), 1)      # the second visit did not call Paystack

    def test_someone_elses_or_an_invented_reference_is_refused(self):
        start = self.service.start_payment(USER, "credits_100")
        with self.assertRaises(ForbiddenReference):
            self.service.verify_payment(User("user-2", "b@example.com"), start.reference)
        with self.assertRaises(ForbiddenReference):
            self.service.verify_payment(USER, "made_up")

    def test_abandoned_and_failed_payments_grant_nothing(self):
        start = self.service.start_payment(USER, "credits_100")
        self.assertEqual(self.service.verify_payment(USER, start.reference)["status"], "abandoned")
        start2 = self.service.start_payment(USER, "credits_100")
        self.gateway.pay(start2.reference, status="failed")
        self.assertEqual(self.service.verify_payment(USER, start2.reference)["status"], "failed")
        self.assertEqual(self.store.credit_balance("user-1"), 0)

    def test_a_payment_of_the_wrong_amount_is_flagged_and_grants_nothing(self):
        start = self.service.start_payment(USER, "credits_100")
        self.gateway.pay(start.reference, amount=5000)
        result = self.service.verify_payment(USER, start.reference)
        self.assertEqual((result["status"], result["credits"]), ("mismatch", 0))
        self.assertEqual(self.sent, [("amount_mismatch", "user-1")])

    def test_a_payment_in_the_wrong_currency_is_flagged(self):
        start = self.service.start_payment(USER, "credits_100")
        data = self.gateway.pay(start.reference)
        data["currency"] = "USD"
        self.assertEqual(apply_charge(store=self.store, config=self.config, gateway=self.gateway, data=data,
                                      now=START, notify=lambda *a, **k: None), "mismatch")

    def test_a_subscription_payment_finds_the_new_subscription(self):
        self.store.mark_trial_used("user-1")
        start = self.service.start_subscription(USER, "pro_monthly_ngn")
        self.gateway.pay(start.reference)
        self.service.verify_payment(USER, start.reference)
        record = self.store.subscription_for("user-1")
        self.assertEqual((record.plan_key, record.status, record.tier), ("pro_monthly_ngn", "active", "pro"))
        self.assertTrue(self.service.access("user-1").paid)

    # ---- reconciling pending payments ------------------------------------------------------------
    def test_a_payment_whose_callback_and_webhook_both_got_lost_is_found_later(self):
        start = self.service.start_payment(USER, "credits_100")
        self.gateway.pay(start.reference)
        self.assertEqual(self.service.reconcile_pending(), {"checked": 0, "applied": 0})     # too fresh
        self.clock.t += 16 * 60
        self.assertEqual(self.service.reconcile_pending(), {"checked": 1, "applied": 1})
        self.assertEqual(self.store.credit_balance("user-1"), 100)
        self.assertEqual(self.service.reconcile_pending()["checked"], 0)                        # nothing pending any more

    def test_old_pending_payments_are_given_up_on(self):
        self.service.start_payment(USER, "credits_100")
        self.clock.t += 73 * 3600
        self.assertEqual(self.service.reconcile_pending()["checked"], 0)

    def test_a_payment_that_was_abandoned_is_checked_once_and_a_late_success_still_counts(self):
        start = self.service.start_payment(USER, "credits_100")
        self.clock.t += 16 * 60
        self.assertEqual(self.service.reconcile_pending()["checked"], 1)
        self.assertEqual(self.store.pending(start.reference).status, "failed")
        self.assertEqual(self.service.reconcile_pending()["checked"], 0)          # no longer pending, so no longer checked
        data = self.gateway.pay(start.reference)                                  # the customer finally pays
        deliver(self.processor, event("charge.success", data))
        self.assertEqual(self.store.credit_balance("user-1"), 100)

    def test_a_failed_payment_is_final(self):
        start = self.service.start_payment(USER, "credits_100")
        self.gateway.pay(start.reference, status="failed")
        self.clock.t += 16 * 60
        self.service.reconcile_pending()
        self.assertEqual(self.store.pending(start.reference).status, "failed")

    # ---- managing a subscription ---------------------------------------------------------------
    def subscribe(self, status="active"):
        sub = self.gateway._new_subscription("CUS_001", "PLN_pro_m", "AUTH_001", START + 30 * DAY)
        sub["status"] = status
        self.store.link_customer("user-1", "CUS_001")
        place_snapshot(self.store, subscription_snapshot(sub, self.config), "user-1", START)
        return sub

    def test_cancelling_stops_renewal_but_keeps_access_to_the_end_of_the_period(self):
        sub = self.subscribe()
        decision = self.service.cancel(USER)
        self.assertEqual(self.gateway.called("disable_subscription")[0][1:], (sub["subscription_code"], sub["email_token"]))
        self.assertEqual((decision.paid, decision.reason), (True, "cancelled, active until the end of the period"))
        self.assertEqual(self.store.subscription_for("user-1").status, "non-renewing")

    def test_resuming_turns_renewal_back_on(self):
        self.subscribe()
        self.service.cancel(USER)
        self.assertEqual(self.service.resume(USER).reason, "active")

    def test_nothing_to_cancel_or_resume_without_a_subscription(self):
        for call in [self.service.cancel, self.service.resume, self.service.card_update_link,
                     lambda u: self.service.change_plan(u, "team_monthly_ngn")]:
            with self.assertRaises(NoSubscription):
                call(USER)
        self.store.save_subscription(rec("cancelled"))
        with self.assertRaises(NoSubscription):
            self.service.cancel(USER)

    def test_the_card_update_link_comes_from_paystack(self):
        sub = self.subscribe()
        self.assertTrue(self.service.card_update_link(USER).endswith(sub["subscription_code"]))

    def test_a_plan_change_is_scheduled_for_the_next_payment_date(self):
        old = self.subscribe()
        decision = self.service.change_plan(USER, "team_monthly_ngn")
        created = self.gateway.called("create_subscription")[0][1]
        self.assertEqual((created["plan"], created["authorization"], parse_time(created["start_date"])),
                         ("PLN_team_m", "AUTH_001", START + 30 * DAY))
        self.assertEqual(self.gateway.called("disable_subscription")[0][1], old["subscription_code"])
        record = self.store.subscription_for("user-1")
        self.assertEqual((record.status, record.tier, record.pending_plan_key), ("non-renewing", "pro", "team_monthly_ngn"))
        self.assertTrue(decision.paid)

    def test_changing_to_the_same_plan_does_nothing_and_currencies_cannot_change(self):
        self.subscribe()
        self.service.change_plan(USER, "pro_monthly_ngn")
        self.assertEqual(self.gateway.called("create_subscription"), [])
        with self.assertRaises(UnknownPlan):
            self.service.change_plan(USER, "pro_monthly_usd")
        with self.assertRaises(UnknownPlan):
            self.service.change_plan(USER, "credits_100")


class HandlerFlowTests(TestCase):
    def setUp(self):
        self.clock, self.config, self.store, self.gateway, self.service, self.processor, self.sent = build_world()

    def send(self, evt):
        return deliver(self.processor, evt)

    def start_trial(self):
        start = self.service.start_subscription(USER, "pro_monthly_ngn")
        return start, self.gateway.pay(start.reference)

    def test_a_trial_card_check_starts_the_subscription_for_later(self):
        start, data = self.start_trial()
        self.assertEqual(self.send(event("charge.success", data)).status, 200)
        created = self.gateway.called("create_subscription")
        self.assertEqual(len(created), 1)
        self.assertEqual(parse_time(created[0][1]["start_date"]), START + 14 * DAY)
        record = self.store.subscription_for("user-1")
        self.assertEqual((record.status, record.trial_end), ("active", START + 14 * DAY))
        self.assertTrue(self.store.has_used_trial("user-1"))
        self.assertEqual(self.service.access("user-1").reason, "free trial")

    def test_the_same_trial_event_twice_creates_one_subscription(self):
        start, data = self.start_trial()
        self.send(event("charge.success", data))
        self.service.verify_payment(USER, start.reference)               # the callback page arrives too
        self.assertEqual(len(self.gateway.called("create_subscription")), 1)
        self.assertEqual(len(self.gateway.subscriptions), 1)

    def test_if_creating_the_subscription_fails_the_event_is_retried_and_then_works(self):
        start, data = self.start_trial()
        self.gateway.fail_next = PaystackNetworkError("down")
        first = self.send(event("charge.success", data))
        self.assertEqual((first.status, first.outcome), (500, "handler_failed"))
        self.assertEqual(self.store.pending(start.reference).status, "pending")      # not marked paid: it will be retried
        self.assertIsNone(self.store.subscription_for("user-1"))
        second = self.send(event("charge.success", data))
        self.assertEqual((second.status, second.outcome), (200, "processed"))
        self.assertEqual(len(self.gateway.subscriptions), 1)

    def test_a_card_that_cannot_be_reused_cannot_start_a_trial(self):
        start = self.service.start_subscription(USER, "pro_monthly_ngn")
        data = self.gateway.pay(start.reference, reusable=False)
        self.send(event("charge.success", data))
        self.assertEqual(self.gateway.called("create_subscription"), [])
        self.assertEqual(self.sent, [("card_not_reusable", "user-1")])
        self.assertEqual(self.store.pending(start.reference).status, "failed")

    def test_a_charge_for_a_reference_we_never_started_is_ignored(self):
        result = apply_charge(store=self.store, config=self.config, gateway=self.gateway,
                              data=charge_data(reference="made_up", amount=200000), now=START, notify=lambda *a, **k: None)
        self.assertEqual(result, "ignored_not_ours")
        self.assertEqual(self.store.credit_balance("user-1"), 0)

    def test_an_unsuccessful_charge_changes_nothing(self):
        start = self.service.start_payment(USER, "credits_100")
        data = self.gateway.pay(start.reference, status="failed")
        self.send(event("charge.success", data))
        self.assertEqual(self.store.credit_balance("user-1"), 0)

    def link_with_subscription(self, status="active", next_payment=START + 30 * DAY):
        sub = self.gateway._new_subscription("CUS_001", "PLN_pro_m", "AUTH_001", next_payment)
        sub["status"] = status
        self.store.link_customer("user-1", "CUS_001")
        return sub

    def test_subscription_create_syncs_the_record_from_the_api(self):
        sub = self.link_with_subscription()
        self.send(event("subscription.create", dict(sub, domain="test")))
        record = self.store.subscription_for("user-1")
        self.assertEqual((record.subscription_code, record.email_token, record.tier), (sub["subscription_code"], sub["email_token"], "pro"))

    def test_events_for_an_unknown_customer_are_retried(self):
        sub = self.gateway._new_subscription("CUS_stranger", "PLN_pro_m", "AUTH_9", START + DAY)
        result = self.send(event("subscription.create", dict(sub, domain="test")))
        self.assertEqual((result.status, result.outcome), (500, "retry_unresolved_customer"))

    def test_a_paid_invoice_moves_the_date_and_records_the_payment_once(self):
        sub = self.link_with_subscription()
        self.send(event("subscription.create", dict(sub, domain="test")))
        sub["next_payment_date"] = iso(START + 60 * DAY)
        paid = invoice_data(sub, paid=True, reference="ref_77", amount=500000)
        self.send(event("invoice.update", paid))
        self.send(event("charge.success", charge_data(reference="ref_77", amount=500000, plan={"plan_code": "PLN_pro_m"})))
        self.assertEqual(self.store.subscription_for("user-1").next_payment_date, START + 60 * DAY)
        self.assertEqual(self.store.payment("ref_77").amount, 500000)

    def test_a_failed_invoice_notifies_and_the_status_comes_from_the_api(self):
        sub = self.link_with_subscription()
        sub["status"] = "attention"
        self.send(event("invoice.payment_failed", invoice_data(sub, paid=False)))
        self.assertEqual(self.sent, [("payment_failed", "user-1")])
        self.assertEqual(self.store.subscription_for("user-1").status, "attention")

    def test_an_unpaid_invoice_update_also_notifies(self):
        sub = self.link_with_subscription()
        self.send(event("invoice.update", invoice_data(sub, paid=False)))
        self.assertEqual(self.sent, [("payment_failed", "user-1")])

    def test_the_upcoming_charge_reminder(self):
        sub = self.link_with_subscription()
        self.send(event("invoice.create", invoice_data(sub, paid=False)))
        self.assertEqual(self.sent, [("renewal_upcoming", "user-1")])

    def test_cancelling_and_ending_notify_once(self):
        sub = self.link_with_subscription()
        sub["status"] = "non-renewing"
        self.send(event("subscription.not_renew", {"domain": "test", "subscription_code": sub["subscription_code"], "customer": sub["customer"]}))
        sub["status"] = "cancelled"
        end = event("subscription.disable", {"domain": "test", "subscription_code": sub["subscription_code"], "customer": sub["customer"]})
        self.send(end)
        self.send(event("subscription.disable", {"domain": "test", "subscription_code": sub["subscription_code"], "status": "cancelled", "customer": sub["customer"], "again": True}))
        self.assertEqual([k for k, _ in self.sent], ["cancellation_scheduled", "subscription_ended"])
        self.assertFalse(self.service.access("user-1").paid)

    def test_events_can_arrive_in_any_order_because_state_comes_from_the_api(self):
        sub = self.link_with_subscription()
        sub["status"], sub["next_payment_date"] = "active", iso(START + 60 * DAY)         # the truth right now
        old_failure = invoice_data(dict(sub, status="attention"), paid=False)               # an old event, retried late
        self.send(event("invoice.payment_failed", old_failure))
        self.assertEqual(self.store.subscription_for("user-1").status, "active")             # the live state won

    def test_expiring_cards_notify_each_affected_user(self):
        self.store.link_customer("user-1", "CUS_001")
        items = [{"expiry_date": "2026-12-31", "customer": {"customer_code": "CUS_001"}}, {"customer": {"customer_code": "CUS_x"}}]
        self.send(event("subscription.expiring_cards", items))
        self.assertEqual(self.sent, [("card_expiring", "user-1")])

    def test_renewal_charges_are_recorded_for_known_customers_only(self):
        self.store.link_customer("user-1", "CUS_001")
        renewal = charge_data(reference="renew_1", amount=500000, plan={"plan_code": "PLN_pro_m"})
        self.send(event("charge.success", renewal))
        self.assertEqual(self.store.payment("renew_1").kind, "subscription_charge")
        stranger = charge_data(reference="renew_2", amount=500000, customer="CUS_x", plan={"plan_code": "PLN_pro_m"})
        self.send(event("charge.success", stranger))
        self.assertIsNone(self.store.payment("renew_2"))

    def test_a_full_refund_reverses_credits_and_a_partial_one_does_not(self):
        start = self.service.start_payment(USER, "credits_100")
        data = self.gateway.pay(start.reference)
        self.send(event("charge.success", data))
        self.send(event("refund.processed", {"domain": "test", "transaction_reference": start.reference, "amount": 50000}))
        self.assertEqual(self.store.credit_balance("user-1"), 100)
        self.send(event("refund.processed", {"domain": "test", "transaction_reference": start.reference, "amount": 200000}))
        self.send(event("refund.processed", {"domain": "test", "transaction_reference": start.reference, "amount": 200000, "again": 1}))
        self.assertEqual((self.store.credit_balance("user-1"), self.store.payment(start.reference).status), (0, "refunded"))

    def test_a_dispute_alerts_the_team(self):
        self.send(event("charge.dispute.create", {"domain": "test", "transaction": {"reference": "r1"}}))
        self.assertEqual(self.sent, [("dispute_opened", None)])

    def test_every_handled_event_has_a_handler(self):
        table = PaystackHandlers(self.store, self.config, self.gateway).table()
        for name in ["charge.success", "subscription.create", "subscription.not_renew", "subscription.disable", "invoice.create",
                     "invoice.update", "invoice.payment_failed", "subscription.expiring_cards", "refund.processed", "charge.dispute.create"]:
            self.assertIn(name, table)


class PlacementTests(TestCase):
    def snap(self, code, status="active", next_payment=START + 30 * DAY, plan="PLN_pro_m"):
        return subscription_snapshot(subscription_obj(code=code, status=status, plan_code=plan, next_payment=next_payment), CONFIG)

    def test_the_first_subscription_is_created_and_updates_replace_it(self):
        store = InMemoryBillingStore()
        self.assertEqual(place_snapshot(store, self.snap("SUB_1"), "u", START), "created")
        self.assertEqual(place_snapshot(store, self.snap("SUB_1", "attention"), "u", START), "updated")
        self.assertEqual(store.subscription_for("u").status, "attention")

    def test_a_scheduled_switch_waits_for_the_old_plan_to_end(self):
        store = InMemoryBillingStore()
        place_snapshot(store, self.snap("SUB_old", "non-renewing"), "u", START)
        record = store.subscription_for("u")
        record.pending_subscription_code, record.pending_plan_key = "SUB_new", "team_monthly_ngn"
        store.save_subscription(record)
        new = self.snap("SUB_new", plan="PLN_team_m")
        self.assertEqual(place_snapshot(store, new, "u", START + 10 * DAY), "ignored")
        self.assertEqual(store.subscription_for("u").subscription_code, "SUB_old")
        self.assertEqual(place_snapshot(store, new, "u", START + 31 * DAY), "switched")
        self.assertEqual((store.subscription_for("u").tier, store.subscription_for("u").pending_plan_key), ("team", None))

    def test_a_new_subscription_replaces_one_that_has_ended(self):
        store = InMemoryBillingStore()
        place_snapshot(store, self.snap("SUB_old", "cancelled"), "u", START)
        self.assertEqual(place_snapshot(store, self.snap("SUB_new"), "u", START), "replaced")

    def test_an_unrelated_second_subscription_does_not_take_over_a_running_one(self):
        store = InMemoryBillingStore()
        place_snapshot(store, self.snap("SUB_1"), "u", START)
        self.assertEqual(place_snapshot(store, self.snap("SUB_2"), "u", START), "ignored")


class SimulationTests(TestCase):
    def test_the_lifecycle_walks_through_every_state(self):
        rows, sent = run_simulation()
        self.assertEqual([r[3] for r in rows], ["free", "PAID", "PAID", "PAID", "PAID", "free", "PAID", "PAID", "free"])
        self.assertTrue(all(r[1] == 200 for r in rows))
        self.assertEqual([k for k, _ in sent], ["payment_failed", "cancellation_scheduled", "subscription_ended"])


class CliTests(TestCase):
    def test_commands_run(self):
        for command, expected in [("simulate", "free trial"), ("attacks", "duplicate"), ("plans", "\u20a65,000.00")]:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main([command]), 0)
            self.assertIn(expected, out.getvalue())
