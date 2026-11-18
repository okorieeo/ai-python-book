"""The sample events people send by hand must keep working, or the hands-on instructions rot."""
import json
from pathlib import Path

from billing.handlers import Order

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_the_stripe_sample_event_is_processed_and_credits_the_user(deliver, state):
    assert deliver("stripe", load("checkout_completed.json")) == (200, {"status": "processed"})
    assert state.credits == {7: 100}


def test_the_paystack_sample_event_matches_an_order_and_credits_once(deliver, state):
    state.orders["ref-fixture-1"] = Order("ref-fixture-1", user_id=7, amount_minor=500_000, currency="NGN", credits=300)
    event = load("charge_success.json")
    assert deliver("paystack", event)[1] == {"status": "processed"}
    assert deliver("paystack", event)[1] == {"status": "duplicate"}
    assert state.credits == {7: 300}
