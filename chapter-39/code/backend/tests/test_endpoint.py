import json

import pytest

from billing.endpoint import WebhookConfig
from testsupport.signing import paystack_event, paystack_headers, stripe_event, stripe_headers, to_bytes
from billing.handlers import Order

CHECKOUT = stripe_event("evt_100", "checkout.session.completed",
                        {"client_reference_id": "7", "metadata": {"credits": "100"}})


class TestStripeEndpoint:
    def test_a_valid_event_is_processed_then_acknowledged_as_a_duplicate(self, deliver, state):
        assert deliver("stripe", CHECKOUT) == (200, {"status": "processed"})
        assert deliver("stripe", CHECKOUT) == (200, {"status": "duplicate"})
        assert state.credits == {7: 100}

    def test_a_bad_signature_is_a_400_and_does_nothing_and_says_nothing(self, deliver, state):
        status, body = deliver("stripe", CHECKOUT, secret="whsec_attacker")
        assert status == 400
        assert body == {"error": "invalid signature"}                # no hint WHY it failed
        assert state.credits == {}

    def test_a_missing_signature_header_is_a_400(self, deliver, state):
        assert deliver("stripe", CHECKOUT, headers={})[0] == 400
        assert state.credits == {}

    def test_a_replayed_old_delivery_is_rejected_by_the_timestamp(self, deliver, state):
        assert deliver("stripe", CHECKOUT, age=3600)[0] == 400
        assert state.credits == {}

    def test_a_body_altered_after_signing_is_rejected(self, deliver, state, clock):
        good = to_bytes(CHECKOUT)
        headers = stripe_headers(good, "whsec_test_secret_for_unit_tests", int(clock()))
        evil = good.replace(b'"credits":"100"', b'"credits":"99999"')
        assert deliver("stripe", CHECKOUT, body=evil, headers=headers)[0] == 400
        assert state.credits == {}

    def test_header_names_are_case_insensitive(self, deliver, clock):
        body = to_bytes(CHECKOUT)
        h = {k.upper(): v for k, v in stripe_headers(body, "whsec_test_secret_for_unit_tests", int(clock())).items()}
        assert deliver("stripe", CHECKOUT, body=body, headers=h)[0] == 200

    def test_an_event_type_we_do_not_handle_is_acknowledged_so_the_provider_stops_retrying(self, deliver):
        assert deliver("stripe", stripe_event("evt_5", "radar.early_fraud_warning.created", {})) == (200, {"status": "ignored"})

    def test_signed_garbage_and_signed_non_objects_are_400(self, deliver):
        for raw in (b"not json at all", b"[1, 2, 3]", b'"just a string"'):
            from testsupport.signing import stripe_headers as sh
            headers = sh(raw, "whsec_test_secret_for_unit_tests", 1_700_000_000)
            assert deliver("stripe", {}, body=raw, headers=headers)[0] == 400

    def test_a_signed_event_with_no_type_or_id_is_a_400(self, deliver):
        assert deliver("stripe", {"id": "evt_1"})[0] == 400
        assert deliver("stripe", {"type": "invoice.paid"})[0] == 400

    def test_a_handler_failure_is_a_500_and_the_redelivery_succeeds_exactly_once(self, deliver, state, handlers, config, store, clock):
        real = handlers["checkout.session.completed"]
        failures = [True]

        def flaky(event):
            if failures:
                failures.pop()
                raise RuntimeError("db unavailable")
            real(event)

        handlers["checkout.session.completed"] = flaky
        assert deliver("stripe", CHECKOUT)[0] == 500
        assert state.credits == {}
        assert deliver("stripe", CHECKOUT) == (200, {"status": "processed"})   # the provider's retry
        assert deliver("stripe", CHECKOUT) == (200, {"status": "duplicate"})
        assert state.credits == {7: 100}

    def test_the_wrong_provider_and_an_oversized_body(self, deliver, config):
        assert deliver("paypal", CHECKOUT)[0] == 404
        small = WebhookConfig(stripe_secrets=config.stripe_secrets, max_body_bytes=50)
        assert deliver("stripe", CHECKOUT, cfg=small)[0] == 413


class TestPaystackEndpoint:
    @pytest.fixture(autouse=True)
    def order(self, state):
        state.orders["ref-1"] = Order("ref-1", 7, 500_000, "NGN", credits=300)

    EVENT = paystack_event("charge.success", {"id": 11, "reference": "ref-1", "amount": 500_000, "currency": "NGN"})

    def test_valid_then_replayed(self, deliver, state):
        assert deliver("paystack", self.EVENT) == (200, {"status": "processed"})
        assert deliver("paystack", self.EVENT) == (200, {"status": "duplicate"})     # no timestamp: idempotency is the defence
        assert state.credits == {7: 300}

    def test_wrong_key_and_missing_header(self, deliver, state):
        assert deliver("paystack", self.EVENT, secret="sk_test_someone_else")[0] == 400
        assert deliver("paystack", self.EVENT, headers={})[0] == 400
        assert state.credits == {}

    def test_a_forged_amount_inside_a_correctly_signed_body_still_cannot_underpay(self, deliver, state):
        underpaid = paystack_event("charge.success", {"id": 12, "reference": "ref-1", "amount": 100, "currency": "NGN"})
        assert deliver("paystack", underpaid)[0] == 200              # acknowledged, so Paystack stops retrying
        assert state.credits == {}                                   # but nothing was credited
        assert state.flagged

    def test_an_unconfigured_provider_is_a_server_error_not_an_open_door(self, deliver, config):
        cfg = WebhookConfig(stripe_secrets=config.stripe_secrets, paystack_secret=None)
        assert deliver("paystack", self.EVENT, cfg=cfg)[0] == 500
