"""Tests for the Stripe billing code. Plain unittest: no network, no Stripe account, no Django."""
import json
from dataclasses import replace
from unittest import TestCase

from stripebilling import cli
from stripebilling.config import BillingConfig, Plan
from stripebilling.entitlements import DAY, FREE, decide_access
from stripebilling.errors import (AlreadySubscribed, BadRedirectUrl, ForbiddenSession, NoCustomer, NoSubscription,
                                  SignatureError, UnknownPlan, UnresolvedCustomer)
from stripebilling.fakes import FakeGateway
from stripebilling.fixtures import (START, charge_obj, checkout_session_obj, invoice_obj, make_event, payload_of,
                                    subscription_obj)
from stripebilling.gateway import StripeGateway
from stripebilling.handlers import StripeHandlers, apply_snapshot, fulfil_payment_session
from stripebilling.params import (cancel_params, check_redirect_url, checkout_params, idempotency_key,
                                  payment_intent_params, plan_change_params, portal_params)
from stripebilling.service import BillingService, User
from stripebilling.simulate import SECRET, Clock, build_world, deliver, demo_config, run_simulation
from stripebilling.snapshots import invoice_subscription_id, subscription_snapshot
from stripebilling.store import InMemoryBillingStore, SubscriptionRecord
from stripebilling.webhooks import ManualVerifier, WebhookProcessor, sign_payload

CONFIG = demo_config()
USER = User("user-1", "ada@example.com", "Ada")


def record(status="active", **kw):
    base = dict(user_id="user-1", customer_id="cus_001", subscription_id="sub_001", status=status, tier="pro",
                plan_key="pro_monthly", period_end=START + 30 * DAY)
    base.update(kw)
    return SubscriptionRecord(**base)


class SignatureTests(TestCase):
    def setUp(self):
        self.clock = Clock(START)
        self.verifier = ManualVerifier(SECRET, clock=self.clock)
        self.payload = payload_of(make_event("invoice.paid", {"id": "in_1"}))

    def header(self, **kw):
        return sign_payload(self.payload, kw.get("secret", SECRET), kw.get("t", START))

    def test_a_correct_signature_returns_the_event(self):
        self.assertEqual(self.verifier.verify(self.payload, self.header())["type"], "invoice.paid")

    def test_a_wrong_secret_is_rejected(self):
        with self.assertRaises(SignatureError):
            self.verifier.verify(self.payload, self.header(secret="whsec_other"))

    def test_a_changed_payload_is_rejected(self):
        with self.assertRaises(SignatureError):
            self.verifier.verify(self.payload + b" ", self.header())

    def test_old_and_future_timestamps_are_rejected(self):
        for t in (START - 301, START + 301):
            with self.assertRaises(SignatureError):
                self.verifier.verify(self.payload, self.header(t=t))
        self.verifier.verify(self.payload, self.header(t=START - 299))     # inside the tolerance

    def test_a_replayed_old_request_fails_even_with_a_valid_signature(self):
        old = self.header(t=START - 3600)
        with self.assertRaises(SignatureError):
            self.verifier.verify(self.payload, old)

    def test_missing_or_malformed_headers_are_rejected(self):
        for bad in ["", "garbage", "t=abc,v1=00", f"t={START}", "v1=deadbeef", f"t={START},v0=deadbeef"]:
            with self.assertRaises(SignatureError):
                self.verifier.verify(self.payload, bad)

    def test_several_signatures_during_secret_rotation(self):
        good = self.header().split(",v1=")[1]
        header = f"t={START},v1={'0' * 64},v1={good}"
        self.assertEqual(self.verifier.verify(self.payload, header)["id"], json.loads(self.payload)["id"])

    def test_the_old_and_new_secret_are_both_accepted_while_rotating(self):
        both = ManualVerifier(["whsec_new_secret_value", SECRET], clock=self.clock)
        both.verify(self.payload, self.header())
        both.verify(self.payload, self.header(secret="whsec_new_secret_value"))

    def test_secrets_must_look_like_webhook_secrets(self):
        for bad in ["sk_test_123", "", []]:
            with self.assertRaises(ValueError):
                ManualVerifier(bad)

    def test_a_signed_body_that_is_not_json_is_rejected(self):
        body = b"not json"
        with self.assertRaises(SignatureError):
            self.verifier.verify(body, sign_payload(body, SECRET, START))


class EntitlementTests(TestCase):
    NOW = START + 10 * DAY

    def test_no_record_means_free(self):
        self.assertEqual(decide_access(None, self.NOW), FREE)

    def test_active_and_trialing_are_paid(self):
        self.assertTrue(decide_access(record("active"), self.NOW).paid)
        decision = decide_access(record("trialing", trial_end=START + 14 * DAY), self.NOW)
        self.assertEqual((decision.paid, decision.reason), (True, "free trial"))

    def test_a_scheduled_cancellation_keeps_access_until_the_period_end(self):
        decision = decide_access(record(cancel_at_period_end=True), self.NOW)
        self.assertTrue(decision.paid)
        self.assertEqual(decision.until, START + 30 * DAY)

    def test_an_ended_fixed_term_cancellation_removes_access(self):
        self.assertFalse(decide_access(record(cancel_at=START + 5 * DAY), self.NOW).paid)

    def test_past_due_has_a_grace_period(self):
        r = record("past_due", past_due_since=START + 9 * DAY)
        self.assertTrue(decide_access(r, START + 11 * DAY, grace_days=3).paid)
        decision = decide_access(r, START + 13 * DAY, grace_days=3)
        self.assertFalse(decision.paid)
        self.assertEqual(decision.tier, "free")

    def test_past_due_without_a_start_time_gets_the_full_grace(self):
        self.assertTrue(decide_access(record("past_due"), self.NOW).paid)

    def test_every_other_status_has_no_access(self):
        for status in ["canceled", "unpaid", "incomplete", "incomplete_expired", "paused"]:
            self.assertFalse(decide_access(record(status), self.NOW).paid, status)

    def test_unknown_statuses_deny_access(self):
        decision = decide_access(record("something_new"), self.NOW)
        self.assertFalse(decision.paid)
        self.assertIn("something_new", decision.reason)

    def test_the_tier_comes_from_the_record(self):
        self.assertEqual(decide_access(record(tier="team"), self.NOW).tier, "team")


class SnapshotTests(TestCase):
    def test_reads_the_period_from_the_item(self):
        snap = subscription_snapshot(subscription_obj(period_end=START + 99), CONFIG)
        self.assertEqual((snap.period_end, snap.plan_key, snap.tier, snap.item_id), (START + 99, "pro_monthly", "pro", "si_001"))

    def test_falls_back_to_the_old_top_level_period(self):
        snap = subscription_snapshot(subscription_obj(period_end=START + 77, legacy_period=True), CONFIG)
        self.assertEqual(snap.period_end, START + 77)

    def test_unknown_prices_map_to_no_plan(self):
        snap = subscription_snapshot(subscription_obj(price_id="price_mystery"), CONFIG)
        self.assertEqual((snap.plan_key, snap.tier), (None, "free"))

    def test_an_expanded_customer_is_flattened(self):
        obj = subscription_obj()
        obj["customer"] = {"id": "cus_777", "object": "customer"}
        self.assertEqual(subscription_snapshot(obj, CONFIG).customer_id, "cus_777")

    def test_metadata_trial_and_cancellation_fields(self):
        snap = subscription_snapshot(subscription_obj(user_id="u9", trial_end=5, cancel_at_period_end=True, cancel_at=9), CONFIG)
        self.assertEqual((snap.user_id, snap.trial_end, snap.cancel_at_period_end, snap.cancel_at), ("u9", 5, True, 9))

    def test_extra_items_are_flagged_and_empty_ones_rejected(self):
        obj = subscription_obj()
        obj["items"]["data"].append(dict(obj["items"]["data"][0], id="si_002"))
        self.assertTrue(subscription_snapshot(obj, CONFIG).multiple_items)
        obj["items"]["data"] = []
        with self.assertRaises(ValueError):
            subscription_snapshot(obj, CONFIG)

    def test_the_invoice_subscription_in_both_shapes(self):
        self.assertEqual(invoice_subscription_id(invoice_obj(subscription="sub_9")), "sub_9")
        self.assertEqual(invoice_subscription_id({"subscription": "sub_old"}), "sub_old")
        self.assertIsNone(invoice_subscription_id({}))


class ParamsTests(TestCase):
    HOSTS = frozenset({"app.example.com"})
    OK = "https://app.example.com/billing"

    def build(self, plan_key="pro_monthly", **kw):
        args = dict(plan=CONFIG.plan(plan_key), user_id="user-1", customer_id="cus_001", email="ada@example.com",
                    success_url=CONFIG.success_url, cancel_url=CONFIG.cancel_url, allowed_hosts=self.HOSTS)
        args.update(kw)
        return checkout_params(**args)

    def test_subscription_checkout_parameters(self):
        params = self.build(trial_days=14)
        self.assertEqual(params["mode"], "subscription")
        self.assertEqual(params["line_items"], [{"price": "price_pro_month", "quantity": 1}])
        self.assertEqual(params["client_reference_id"], "user-1")
        self.assertEqual(params["subscription_data"]["trial_period_days"], 14)
        self.assertEqual(params["subscription_data"]["metadata"]["user_id"], "user-1")
        self.assertEqual(params["customer"], "cus_001")

    def test_no_trial_by_default_and_never_payment_method_types(self):
        params = self.build()
        self.assertNotIn("trial_period_days", params["subscription_data"])
        self.assertNotIn("payment_method_types", params)
        self.assertNotIn("ui_mode", params)           # the default is the hosted page

    def test_one_time_purchase_parameters(self):
        params = self.build("credits_100", customer_id=None)
        self.assertEqual(params["mode"], "payment")
        self.assertEqual(params["customer_email"], "ada@example.com")
        self.assertNotIn("subscription_data", params)

    def test_embedded_checkout_uses_return_url_and_no_cancel_url(self):
        params = self.build(embedded=True)
        self.assertEqual(params["ui_mode"], "embedded_page")
        self.assertIn("return_url", params)
        self.assertNotIn("cancel_url", params)
        self.assertNotIn("success_url", params)

    def test_redirect_urls_must_use_allowed_hosts(self):
        for bad in ["https://evil.example/x", "javascript:alert(1)", "//evil.example", "http://app.example.com/x"]:
            with self.assertRaises(BadRedirectUrl):
                check_redirect_url(bad, self.HOSTS)
        self.assertEqual(check_redirect_url(self.OK, self.HOSTS), self.OK)
        check_redirect_url("http://localhost:3000/x", frozenset({"localhost"}))

    def test_the_checkout_placeholder_survives_url_checks(self):
        self.assertIn("{CHECKOUT_SESSION_ID}", self.build()["success_url"])

    def test_idempotency_keys_are_stable_and_sensitive_to_every_part(self):
        a = idempotency_key("checkout", "u1", "pro", 14)
        self.assertEqual(a, idempotency_key("checkout", "u1", "pro", 14))
        for other in [("checkout", "u2", "pro", 14), ("checkout", "u1", "team", 14), ("checkout", "u1", "pro", None)]:
            self.assertNotEqual(a, idempotency_key(*other))
        self.assertLessEqual(len(a), 255)

    def test_plan_change_proration_depends_on_direction(self):
        up = plan_change_params(item_id="si_1", new_price_id="price_x", direction="up")
        down = plan_change_params(item_id="si_1", new_price_id="price_x", direction="down")
        self.assertEqual(up["proration_behavior"], "always_invoice")
        self.assertEqual(down["proration_behavior"], "create_prorations")
        self.assertEqual(up["items"], [{"id": "si_1", "price": "price_x"}])
        self.assertEqual(up["payment_behavior"], "error_if_incomplete")

    def test_portal_and_cancel_parameters(self):
        self.assertEqual(portal_params("cus_1", self.OK, self.HOSTS), {"customer": "cus_1", "return_url": self.OK})
        with self.assertRaises(BadRedirectUrl):
            portal_params("cus_1", "https://evil.example", self.HOSTS)
        self.assertEqual(cancel_params(), {"cancel_at_period_end": True})
        self.assertEqual(cancel_params(False), {"cancel_at_period_end": False})

    def test_the_plan_table_rejects_unknown_keys(self):
        with self.assertRaises(UnknownPlan):
            CONFIG.plan("pro_lifetime_hack")
        self.assertEqual(CONFIG.plan_for_price("price_team_month").key, "team_monthly")
        self.assertIsNone(CONFIG.plan_for_price("nope"))


class PaymentIntentParamsTests(TestCase):
    def build(self, **kw):
        args = dict(amount=500, currency="USD", customer_id="cus_1", user_id="u1", description="Tip")
        args.update(kw)
        return payment_intent_params(**args)

    def test_a_valid_intent(self):
        params = self.build()
        self.assertEqual((params["amount"], params["currency"], params["customer"]), (500, "usd", "cus_1"))
        self.assertEqual(params["automatic_payment_methods"], {"enabled": True})
        self.assertEqual(params["metadata"], {"user_id": "u1"})

    def test_amounts_must_be_whole_positive_and_capped(self):
        for bad in [0, -5, 12.5, True, 100_001, "500"]:
            with self.assertRaises(ValueError):
                self.build(amount=bad)

    def test_currency_must_be_a_three_letter_code(self):
        for bad in ["", "us", "dollars", "u5d"]:
            with self.assertRaises(ValueError):
                self.build(currency=bad)


class ReplayTests(TestCase):
    def test_a_replayed_event_is_processed_once_without_a_signature(self):
        clock, config, store, gateway, service, processor, sent = build_world()
        event = make_event("customer.subscription.updated", subscription_obj(status="active"), event_id="evt_replay")
        self.assertEqual(processor.process_verified(event).outcome, "processed")
        self.assertEqual(processor.process_verified(event).outcome, "duplicate")
        self.assertTrue(service.access("user-1").paid)


class ServiceTests(TestCase):
    def setUp(self):
        self.clock, self.config, self.store, self.gateway, self.service, self.processor, self.sent = build_world()

    def test_checkout_creates_one_customer_and_one_session(self):
        start = self.service.start_checkout(USER, "pro_monthly")
        self.assertTrue(start.url.startswith("https://checkout.stripe.com/"))
        self.assertEqual(len(self.gateway.called("create_customer")), 1)
        self.assertEqual(self.store.customer_id_for("user-1"), "cus_001")
        params = self.gateway.called("create_checkout_session")[0][1]
        self.assertEqual(params["customer"], "cus_001")
        self.assertEqual(params["subscription_data"]["trial_period_days"], 14)

    def test_a_second_checkout_reuses_the_customer(self):
        self.service.start_checkout(USER, "pro_monthly")
        self.service.start_checkout(USER, "team_monthly")
        self.assertEqual(len(self.gateway.called("create_customer")), 1)

    def test_a_double_click_does_not_create_two_sessions(self):
        first = self.service.start_checkout(USER, "pro_monthly")
        second = self.service.start_checkout(USER, "pro_monthly")
        self.assertEqual(first.session_id, second.session_id)
        self.assertEqual(len(self.gateway.sessions), 1)

    def test_embedded_checkout_returns_a_client_secret(self):
        start = self.service.start_checkout(USER, "pro_monthly", embedded=True)
        self.assertIsNone(start.url)
        self.assertTrue(start.client_secret)

    def test_unknown_plans_never_reach_stripe(self):
        with self.assertRaises(UnknownPlan):
            self.service.start_checkout(USER, "free_forever")
        self.assertEqual(self.gateway.calls, [])

    def test_the_browser_cannot_choose_the_price(self):
        with self.assertRaises(UnknownPlan):
            self.service.start_checkout(USER, "price_pro_month")

    def test_no_second_subscription_while_one_is_active(self):
        for status in ["active", "trialing", "past_due", "incomplete", "paused"]:
            self.store.save_subscription(record(status))
            with self.assertRaises(AlreadySubscribed):
                self.service.start_checkout(USER, "team_monthly")
        self.store.save_subscription(record("canceled"))
        self.service.start_checkout(USER, "team_monthly")      # allowed again after cancellation

    def test_the_free_trial_is_offered_only_once(self):
        self.store.mark_trial_used("user-1")
        self.service.start_checkout(USER, "pro_monthly")
        params = self.gateway.called("create_checkout_session")[0][1]
        self.assertNotIn("trial_period_days", params["subscription_data"])

    def test_one_time_purchases_have_no_trial_and_are_allowed_while_subscribed(self):
        self.store.save_subscription(record("active"))
        self.service.start_checkout(USER, "credits_100")
        params = self.gateway.called("create_checkout_session")[0][1]
        self.assertEqual(params["mode"], "payment")

    def test_the_portal_needs_a_customer(self):
        with self.assertRaises(NoCustomer):
            self.service.open_portal(USER)
        self.store.link_customer("user-1", "cus_001")
        self.assertTrue(self.service.open_portal(USER).startswith("https://billing.stripe.com/"))
        self.assertEqual(self.gateway.called("create_portal_session")[0][1]["customer"], "cus_001")

    def setup_subscription(self, **kw):
        sub = self.gateway.add_subscription(**kw)
        self.store.link_customer("user-1", "cus_001")
        apply_snapshot(self.store, subscription_snapshot(sub, self.config), "user-1", START)
        return sub

    def test_an_upgrade_is_invoiced_immediately(self):
        self.setup_subscription()
        decision = self.service.change_plan(USER, "team_monthly")
        sent = self.gateway.called("update_subscription")[0]
        self.assertEqual(sent[2]["proration_behavior"], "always_invoice")
        self.assertEqual(sent[2]["items"][0]["price"], "price_team_month")
        self.assertEqual(decision.tier, "team")
        self.assertEqual(self.store.subscription_for("user-1").plan_key, "team_monthly")

    def test_a_downgrade_adds_a_credit_to_the_next_invoice(self):
        self.setup_subscription(price_id="price_team_month")
        self.store.save_subscription(replace(self.store.subscription_for("user-1"), tier="team"))
        decision = self.service.change_plan(USER, "pro_monthly")
        self.assertEqual(self.gateway.called("update_subscription")[0][2]["proration_behavior"], "create_prorations")
        self.assertEqual(decision.tier, "pro")

    def test_changing_to_the_same_plan_does_nothing(self):
        self.setup_subscription()
        self.service.change_plan(USER, "pro_monthly")
        self.assertEqual(self.gateway.called("update_subscription"), [])

    def test_changes_need_a_subscription_and_a_subscription_plan(self):
        with self.assertRaises(NoSubscription):
            self.service.change_plan(USER, "team_monthly")
        self.setup_subscription()
        with self.assertRaises(NoSubscription):
            self.service.change_plan(USER, "credits_100")
        self.store.save_subscription(record("canceled"))
        with self.assertRaises(NoSubscription):
            self.service.cancel(USER)

    def test_cancelling_keeps_access_until_the_period_ends(self):
        self.setup_subscription()
        decision = self.service.cancel(USER)
        self.assertEqual(self.gateway.called("update_subscription")[0][2], {"cancel_at_period_end": True})
        self.assertTrue(decision.paid)
        self.assertEqual(decision.reason, "cancels at the end of the period")

    def test_cancelling_immediately_ends_access(self):
        self.setup_subscription()
        decision = self.service.cancel(USER, immediately=True)
        self.assertFalse(decision.paid)
        self.assertEqual(len(self.gateway.called("cancel_subscription")), 1)

    def test_resuming_undoes_a_scheduled_cancellation(self):
        self.setup_subscription()
        self.service.cancel(USER)
        decision = self.service.resume(USER)
        self.assertEqual(decision.reason, "active")

    def test_reconcile_repairs_drift_when_a_webhook_was_missed(self):
        sub = self.setup_subscription()
        sub["status"] = "canceled"                      # Stripe changed it; our copy never heard
        self.assertTrue(self.service.access("user-1").paid)
        self.assertFalse(self.service.reconcile(USER).paid)

    def test_the_success_page_reads_the_session_from_stripe(self):
        self.gateway.sessions["cs_test_9"] = dict(checkout_session_obj(id="cs_test_9"), subscription=subscription_obj(status="trialing", trial_end=START + 14 * DAY))
        result = self.service.sync_checkout(USER, "cs_test_9")
        self.assertTrue(result["paid"])
        self.assertTrue(self.store.has_used_trial("user-1"))
        self.assertEqual(self.store.customer_id_for("user-1"), "cus_001")

    def test_the_success_page_rejects_someone_elses_session(self):
        self.gateway.sessions["cs_test_9"] = checkout_session_obj(id="cs_test_9", user_id="someone-else")
        with self.assertRaises(ForbiddenSession):
            self.service.sync_checkout(USER, "cs_test_9")
        self.assertIsNone(self.store.subscription_for("user-1"))

    def test_the_success_page_fulfils_a_one_time_purchase_once(self):
        paid = checkout_session_obj(id="cs_test_5", mode="payment", payment_intent="pi_5", plan_key="credits_100")
        self.gateway.sessions["cs_test_5"] = paid
        first = self.service.sync_checkout(USER, "cs_test_5")
        second = self.service.sync_checkout(USER, "cs_test_5")
        self.assertEqual((first["credits"], first["fulfilled_now"]), (100, True))
        self.assertEqual((second["credits"], second["fulfilled_now"]), (100, False))


class WebhookTests(TestCase):
    def setUp(self):
        self.clock, self.config, self.store, self.gateway, self.service, self.processor, self.sent = build_world()
        self.calls = []

    def send(self, event, **kw):
        return deliver(self.processor, self.clock, event, **kw)

    def test_a_good_event_is_processed_and_logged(self):
        event = make_event("checkout.session.completed", checkout_session_obj(), event_id="evt_a")
        result = self.send(event)
        self.assertEqual((result.status, result.outcome), (200, "processed"))
        self.assertEqual(self.store.event("evt_a")["status"], "processed")

    def test_a_bad_signature_gets_400_and_runs_nothing(self):
        event = make_event("checkout.session.completed", checkout_session_obj(), event_id="evt_b")
        result = self.send(event, secret="whsec_wrong")
        self.assertEqual((result.status, result.outcome), (400, "bad_signature"))
        self.assertIsNone(self.store.event("evt_b"))
        self.assertIsNone(self.store.customer_id_for("user-1"))

    def test_a_tampered_payload_gets_400(self):
        event = make_event("customer.subscription.updated", subscription_obj(status="active"), event_id="evt_t")
        self.assertEqual(self.send(event, tamper=True).status, 400)

    def test_the_same_event_twice_runs_the_handler_once(self):
        runs = []
        processor = WebhookProcessor(ManualVerifier(SECRET, clock=self.clock), self.store,
                                     {"invoice.paid": lambda e: runs.append(e["id"])}, livemode=False, clock=self.clock)
        event = make_event("invoice.paid", {}, event_id="evt_dup")
        first = deliver(processor, self.clock, event)
        second = deliver(processor, self.clock, event)
        self.assertEqual((first.outcome, second.outcome, second.status), ("processed", "duplicate", 200))
        self.assertEqual(runs, ["evt_dup"])

    def test_a_failing_handler_gets_500_and_can_succeed_on_retry(self):
        attempts = []

        def flaky(event):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("database down")
        processor = WebhookProcessor(ManualVerifier(SECRET, clock=self.clock), self.store, {"invoice.paid": flaky},
                                     livemode=False, clock=self.clock)
        event = make_event("invoice.paid", {}, event_id="evt_flaky")
        first = deliver(processor, self.clock, event)
        self.assertEqual((first.status, first.outcome), (500, "handler_failed"))
        self.assertEqual(self.store.event("evt_flaky")["status"], "failed")
        self.assertIn("database down", self.store.event("evt_flaky")["error"])
        second = deliver(processor, self.clock, event)
        self.assertEqual((second.status, second.outcome), (200, "processed"))
        self.assertEqual(self.store.event("evt_flaky")["attempts"], 2)

    def test_an_event_being_processed_right_now_gets_409_until_its_lease_runs_out(self):
        self.store.begin_event("evt_busy", "invoice.paid", self.clock(), 300)       # another worker holds it
        event = make_event("invoice.paid", invoice_obj(), event_id="evt_busy")
        self.assertEqual(self.send(event).status, 409)
        self.clock.t += 301                                                         # the worker must have died
        self.store.link_customer("user-1", "cus_001")
        self.assertEqual(self.send(event).status, 200)

    def test_unknown_event_types_are_acknowledged_and_ignored(self):
        result = self.send(make_event("payout.paid", {}, event_id="evt_p"))
        self.assertEqual((result.status, result.outcome), (200, "ignored"))
        self.assertEqual(self.store.event("evt_p")["status"], "ignored")

    def test_events_from_the_other_mode_are_ignored(self):
        result = self.send(make_event("checkout.session.completed", checkout_session_obj(), livemode=True))
        self.assertEqual((result.status, result.outcome), (200, "ignored_wrong_mode"))
        self.assertIsNone(self.store.customer_id_for("user-1"))

    def test_an_unexpected_api_version_is_reported_but_processed(self):
        result = self.send(make_event("payout.paid", {}, api_version="2025-03-31.basil"))
        self.assertEqual(result.status, 200)
        self.assertTrue(result.warnings)

    def test_a_subscription_event_before_checkout_completed_finds_the_user_by_metadata(self):
        self.send(make_event("customer.subscription.created", subscription_obj(status="active", user_id="user-1")))
        self.assertTrue(self.service.access("user-1").paid)
        self.assertEqual(self.store.customer_id_for("user-1"), "cus_001")

    def test_an_event_for_an_unknown_customer_is_retried(self):
        result = self.send(make_event("invoice.paid", invoice_obj(customer="cus_stranger")))
        self.assertEqual((result.status, result.outcome), (500, "retry_unresolved_customer"))

    def test_an_old_event_arriving_late_does_not_overwrite_newer_state(self):
        self.send(make_event("customer.subscription.updated", subscription_obj(status="active"), created=START + 50))
        self.send(make_event("customer.subscription.updated", subscription_obj(status="past_due"), created=START + 10))
        self.assertEqual(self.store.subscription_for("user-1").status, "active")

    def test_cancelling_and_ending_notify_the_user_once(self):
        user_sub = lambda **k: subscription_obj(**k)
        self.send(make_event("customer.subscription.updated", user_sub(cancel_at_period_end=True), created=START + 1))
        self.send(make_event("customer.subscription.updated", user_sub(cancel_at_period_end=True), created=START + 2))
        self.send(make_event("customer.subscription.deleted", user_sub(status="canceled"), created=START + 3))
        self.assertEqual([k for k, _ in self.sent], ["cancellation_scheduled", "subscription_ended"])

    def test_a_failed_payment_notifies_and_a_paid_invoice_is_recorded(self):
        self.store.link_customer("user-1", "cus_001")
        self.send(make_event("invoice.payment_failed", invoice_obj(attempt_count=2)))
        self.send(make_event("invoice.paid", invoice_obj(id="in_77", amount_paid=4000)))
        self.assertEqual(self.sent, [("payment_failed", "user-1")])
        payment = self.store.payment("in_77")
        self.assertEqual((payment.amount, payment.status, payment.kind), (4000, "paid", "subscription_invoice"))
        self.assertTrue(payment.receipt_url.startswith("https://invoice.stripe.com/"))

    def test_the_trial_ending_reminder_is_sent(self):
        self.send(make_event("customer.subscription.trial_will_end", subscription_obj(status="trialing", trial_end=START + 3 * DAY)))
        self.assertEqual(self.sent, [("trial_ending", "user-1")])

    def test_a_paid_one_time_checkout_grants_credits_once_even_across_different_events(self):
        session = checkout_session_obj(id="cs_pay", mode="payment", payment_intent="pi_9", plan_key="credits_100")
        self.send(make_event("checkout.session.completed", session))
        self.send(make_event("checkout.session.async_payment_succeeded", session))      # a different event, same purchase
        self.assertEqual(self.store.credit_balance("user-1"), 100)

    def test_a_delayed_payment_grants_credits_only_when_it_succeeds(self):
        pending = checkout_session_obj(id="cs_slow", mode="payment", payment_status="unpaid", payment_intent="pi_8", plan_key="credits_100")
        self.send(make_event("checkout.session.completed", pending))
        self.assertEqual(self.store.credit_balance("user-1"), 0)
        self.send(make_event("checkout.session.async_payment_succeeded", dict(pending, payment_status="paid")))
        self.assertEqual(self.store.credit_balance("user-1"), 100)

    def test_a_failed_delayed_payment_notifies(self):
        self.send(make_event("checkout.session.async_payment_failed", checkout_session_obj(mode="payment")))
        self.assertEqual(self.sent[0][0], "payment_failed")

    def test_a_refund_reverses_the_credits_once(self):
        session = checkout_session_obj(id="cs_ref", mode="payment", payment_intent="pi_ref", plan_key="credits_100")
        self.send(make_event("checkout.session.completed", session))
        self.send(make_event("charge.refunded", charge_obj(payment_intent="pi_ref")))
        self.send(make_event("charge.refunded", charge_obj(payment_intent="pi_ref"), event_id="evt_again"))
        self.assertEqual(self.store.credit_balance("user-1"), 0)
        self.assertEqual(self.store.payment("pi_ref").status, "refunded")

    def test_a_partial_refund_keeps_the_credits(self):
        session = checkout_session_obj(id="cs_part", mode="payment", payment_intent="pi_part", plan_key="credits_100")
        self.send(make_event("checkout.session.completed", session))
        self.send(make_event("charge.refunded", charge_obj(payment_intent="pi_part", amount_refunded=500)))
        self.assertEqual(self.store.credit_balance("user-1"), 100)

    def test_a_mobile_payment_is_recorded_once_and_checkout_payments_are_skipped(self):
        intent = {"id": "pi_mobile", "amount_received": 15000, "currency": "usd", "metadata": {"user_id": "user-1"}}
        self.send(make_event("payment_intent.succeeded", intent))
        self.send(make_event("payment_intent.succeeded", intent))
        self.assertEqual(self.store.payment("pi_mobile").amount, 15000)
        self.send(make_event("payment_intent.succeeded", {"id": "pi_checkout", "amount_received": 2000, "metadata": {}}))
        self.assertIsNone(self.store.payment("pi_checkout"))

    def test_a_dispute_alerts_the_team(self):
        self.send(make_event("charge.dispute.created", {"id": "dp_1", "charge": "ch_1", "reason": "fraudulent"}))
        self.assertEqual(self.sent, [("dispute_opened", None)])

    def test_a_user_cannot_be_linked_to_two_customers(self):
        self.store.link_customer("user-1", "cus_first")
        result = self.send(make_event("checkout.session.completed", checkout_session_obj(customer="cus_second")))
        self.assertEqual(result.status, 500)
        self.assertEqual(self.store.customer_id_for("user-1"), "cus_first")

    def test_fulfilment_ignores_unpaid_and_subscription_sessions(self):
        self.assertFalse(fulfil_payment_session(self.store, self.config, checkout_session_obj(mode="subscription")))
        self.assertFalse(fulfil_payment_session(self.store, self.config, checkout_session_obj(mode="payment", payment_status="unpaid")))

    def test_every_handled_event_type_has_a_handler(self):
        table = StripeHandlers(self.store, self.config).table()
        for name in ["checkout.session.completed", "customer.subscription.updated", "customer.subscription.deleted",
                     "invoice.paid", "invoice.payment_failed", "customer.subscription.trial_will_end"]:
            self.assertIn(name, table)


class StoreTests(TestCase):
    def test_the_first_customer_link_wins(self):
        store = InMemoryBillingStore()
        self.assertEqual(store.link_customer("u", "cus_1"), "cus_1")
        self.assertEqual(store.link_customer("u", "cus_2"), "cus_1")
        self.assertEqual(store.user_id_for_customer("cus_2"), None)

    def test_records_are_copies(self):
        store = InMemoryBillingStore()
        store.save_subscription(record())
        copy = store.subscription_for("user-1")
        copy.status = "canceled"
        self.assertEqual(store.subscription_for("user-1").status, "active")

    def test_credits_are_granted_once_per_reference_and_reversed_once(self):
        store = InMemoryBillingStore()
        self.assertTrue(store.grant_credits("u", 50, "ref"))
        self.assertFalse(store.grant_credits("u", 50, "ref"))
        self.assertTrue(store.reverse_credits("ref"))
        self.assertFalse(store.reverse_credits("ref"))
        self.assertFalse(store.reverse_credits("missing"))
        self.assertEqual(store.credit_balance("u"), 0)

    def test_the_past_due_start_time_is_kept_across_repeated_events(self):
        store = InMemoryBillingStore()
        snap = subscription_snapshot(subscription_obj(status="past_due"), CONFIG)
        apply_snapshot(store, snap, "user-1", START + 10)
        apply_snapshot(store, snap, "user-1", START + 99)
        self.assertEqual(store.subscription_for("user-1").past_due_since, START + 10)
        healthy = subscription_snapshot(subscription_obj(status="active"), CONFIG)
        apply_snapshot(store, healthy, "user-1", START + 120)
        self.assertIsNone(store.subscription_for("user-1").past_due_since)


class GatewayTests(TestCase):
    def test_only_server_side_keys_are_accepted(self):
        for key in ["pk_test_123", "whsec_123", "", "sk"]:
            with self.assertRaises(ValueError):
                StripeGateway(key)


class SimulationTests(TestCase):
    def test_the_lifecycle_walks_through_every_state(self):
        rows, sent = run_simulation()
        access = [row[3] for row in rows]
        self.assertEqual(access, ["free", "free", "PAID", "PAID", "PAID", "PAID", "free", "PAID", "PAID", "free"])
        self.assertTrue(all(row[1] == 200 for row in rows))
        self.assertEqual([kind for kind, _ in sent],
                         ["payment_failed", "payment_failed", "cancellation_scheduled", "subscription_ended"])


class CliTests(TestCase):
    def test_commands_run(self):
        import contextlib
        import io
        for command, expected in [("simulate", "grace period"), ("attacks", "duplicate"), ("plans", "pro_monthly")]:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main([command]), 0)
            self.assertIn(expected, out.getvalue())
