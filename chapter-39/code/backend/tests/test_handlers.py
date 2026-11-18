import pytest

from billing.handlers import Order
from billing.webhooks import process_event
from testsupport.signing import paystack_event, stripe_event


def checkout(eid, user=1, credits=100):
    return stripe_event(eid, "checkout.session.completed", {"client_reference_id": str(user), "metadata": {"credits": str(credits)}})


def invoice_paid(eid, user, plan, created):
    ev = stripe_event(eid, "invoice.paid", {"metadata": {"user_id": str(user), "plan": plan}})
    ev["created"] = created
    return ev


def sub_deleted(eid, user, created):
    ev = stripe_event(eid, "customer.subscription.deleted", {"metadata": {"user_id": str(user)}})
    ev["created"] = created
    return ev


def charge(ref="ref-1", amount=500_000, currency="NGN", id_=11):
    return paystack_event("charge.success", {"id": id_, "reference": ref, "amount": amount, "currency": currency})


def run(provider, ev, store, handlers):
    return process_event(provider, ev, store, handlers)


class TestStripeHandlers:
    def test_a_credit_purchase_adds_credits(self, state, store, handlers):
        run("stripe", checkout("evt_1", user=7, credits=250), store, handlers)
        assert state.credits == {7: 250}

    def test_a_redelivered_purchase_does_not_pay_out_twice(self, state, store, handlers):
        for _ in range(3):
            run("stripe", checkout("evt_1", user=7, credits=250), store, handlers)
        assert state.credits == {7: 250}

    def test_two_real_purchases_add_up(self, state, store, handlers):
        run("stripe", checkout("evt_1", user=7, credits=100), store, handlers)
        run("stripe", checkout("evt_2", user=7, credits=50), store, handlers)
        assert state.credits[7] == 150

    def test_invoice_paid_activates_the_plan(self, state, store, handlers):
        run("stripe", invoice_paid("evt_1", 7, "pro", 100), store, handlers)
        assert state.plans == {7: "pro"}

    def test_invoice_without_our_metadata_is_ignored_not_an_error(self, state, store, handlers):
        run("stripe", stripe_event("evt_1", "invoice.paid", {}), store, handlers)
        assert state.plans == {}

    def test_cancelling_an_unknown_customer_is_ignored(self, state, store, handlers):
        run("stripe", stripe_event("evt_1", "customer.subscription.deleted", {}), store, handlers)
        assert state.plans == {}

    @pytest.mark.parametrize("arrival", ["paid-then-cancelled", "cancelled-then-paid"])
    def test_events_arriving_out_of_order_cannot_resurrect_a_cancelled_plan(self, state, store, handlers, arrival):
        paid = invoice_paid("evt_paid", 7, "pro", created=100)       # happened FIRST, at t=100
        cancelled = sub_deleted("evt_del", 7, created=200)           # happened LAST, at t=200
        in_order = [paid, cancelled] if arrival == "paid-then-cancelled" else [cancelled, paid]   # second: the late 'paid'
        for event in in_order:
            run("stripe", event, store, handlers)
        assert state.plans[7] == "free"                  # the newer decision (cancel, t=200) wins whichever arrived first

    def test_a_newer_paid_event_does_reactivate_after_an_older_cancel(self, state, store, handlers):
        run("stripe", sub_deleted("evt_del", 7, created=100), store, handlers)
        run("stripe", invoice_paid("evt_paid", 7, "pro", created=200), store, handlers)
        assert state.plans[7] == "pro"


class TestPaystackHandler:
    @pytest.fixture(autouse=True)
    def order(self, state):
        state.orders["ref-1"] = Order("ref-1", user_id=7, amount_minor=500_000, currency="NGN", credits=300)

    def test_a_matching_payment_credits_the_user_once(self, state, store, handlers):
        run("paystack", charge(), store, handlers)
        assert state.credits == {7: 300}
        assert state.orders["ref-1"].status == "paid"

    def test_a_replayed_delivery_does_not_credit_twice(self, state, store, handlers):
        run("paystack", charge(), store, handlers)
        run("paystack", charge(), store, handlers)
        assert state.credits == {7: 300}

    def test_even_a_new_event_id_for_a_paid_order_does_not_credit_twice(self, state, store, handlers):
        run("paystack", charge(id_=11), store, handlers)
        run("paystack", charge(id_=12), store, handlers)            # same reference, different transaction id
        assert state.credits == {7: 300}

    @pytest.mark.parametrize("amount,currency", [(100, "NGN"), (500_001, "NGN"), (500_000, "USD"), (None, "NGN")],
                             ids=["underpaid", "off-by-one", "wrong-currency", "no-amount"])
    def test_a_payment_that_does_not_match_our_order_is_flagged_and_not_credited(self, state, store, handlers, amount, currency):
        run("paystack", charge(amount=amount, currency=currency), store, handlers)
        assert state.credits == {}
        assert state.orders["ref-1"].status == "pending"
        assert state.flagged[0]["why"] == "amount or currency mismatch"

    def test_an_unknown_reference_is_flagged_for_a_human(self, state, store, handlers):
        run("paystack", charge(ref="ref-nobody"), store, handlers)
        assert state.credits == {}
        assert state.flagged == [{"why": "unknown reference", "reference": "ref-nobody"}]
