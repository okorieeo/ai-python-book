import pytest

from billing.webhooks import MalformedEvent, event_key, event_type, process_event


def stripe(eid="evt_1", type_="invoice.paid"):
    return {"id": eid, "type": type_, "data": {"object": {}}}


def paystack(event="charge.success", **data):
    return {"event": event, "data": data}


class TestEventKey:
    def test_stripe_uses_the_event_id(self):
        assert event_key("stripe", stripe("evt_9")) == "stripe:evt_9"

    def test_paystack_prefers_the_transaction_id_then_the_reference(self):
        assert event_key("paystack", paystack(id=302961, reference="r1")) == "paystack:charge.success:302961"
        assert event_key("paystack", paystack(reference="r1")) == "paystack:charge.success:r1"

    def test_the_same_transaction_under_two_event_names_is_two_different_events(self):
        assert event_key("paystack", paystack("charge.success", id=1)) != event_key("paystack", paystack("refund.processed", id=1))

    @pytest.mark.parametrize("provider,event", [
        ("stripe", {}), ("stripe", {"id": ""}), ("stripe", {"id": 5}),
        ("paystack", {"event": "charge.success"}), ("paystack", {"event": "charge.success", "data": "x"}),
        ("paystack", {"event": "charge.success", "data": {}}), ("paystack", {"data": {"id": 1}}),
    ])
    def test_unusable_events_are_malformed(self, provider, event):
        with pytest.raises(MalformedEvent):
            event_key(provider, event)

    def test_event_type_per_provider(self):
        assert event_type("stripe", stripe(type_="x.y")) == "x.y"
        assert event_type("paystack", paystack("a.b")) == "a.b"
        with pytest.raises(MalformedEvent):
            event_type("stripe", {"id": "e"})


class TestProcessEvent:
    def test_first_delivery_is_processed_and_a_redelivery_is_a_duplicate(self, store):
        seen = []
        handlers = {"invoice.paid": seen.append}
        assert process_event("stripe", stripe(), store, handlers) == "processed"
        assert process_event("stripe", stripe(), store, handlers) == "duplicate"
        assert len(seen) == 1

    def test_unknown_event_types_are_ignored_and_never_claimed(self, store):
        assert process_event("stripe", stripe(type_="radar.something"), store, {"invoice.paid": lambda e: None}) == "ignored"
        assert store.claim("stripe:evt_1") is True            # nothing was claimed, so this is still the first time

    def test_a_failing_handler_releases_the_claim_so_the_retry_runs_again(self, store):
        attempts = []

        def flaky(event):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("database was down")

        handlers = {"invoice.paid": flaky}
        with pytest.raises(RuntimeError):
            process_event("stripe", stripe(), store, handlers)
        assert process_event("stripe", stripe(), store, handlers) == "processed"
        assert len(attempts) == 2

    def test_different_events_do_not_block_each_other(self, store):
        seen = []
        handlers = {"invoice.paid": lambda e: seen.append(e["id"])}
        for eid in ("evt_1", "evt_2", "evt_3"):
            assert process_event("stripe", stripe(eid), store, handlers) == "processed"
        assert seen == ["evt_1", "evt_2", "evt_3"]

    def test_paystack_redelivery_of_the_same_charge_is_a_duplicate(self, store):
        seen = []
        handlers = {"charge.success": seen.append}
        ev = paystack(id=77, reference="ref-77")
        assert process_event("paystack", ev, store, handlers) == "processed"
        assert process_event("paystack", dict(ev), store, handlers) == "duplicate"
        assert len(seen) == 1

    def test_a_malformed_event_is_reported_not_swallowed(self, store):
        with pytest.raises(MalformedEvent):
            process_event("stripe", {"type": "invoice.paid"}, store, {"invoice.paid": lambda e: None})
