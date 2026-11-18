"""A scripted subscription lifecycle sent through the real webhook processor with signed payloads."""
from .config import BillingConfig, Plan
from .entitlements import DAY
from .fakes import FakeGateway
from .fixtures import (START, charge_obj, checkout_session_obj, invoice_obj, make_event, payload_of,
                       subscription_obj)
from .handlers import StripeHandlers
from .service import BillingService, User
from .store import InMemoryBillingStore
from .webhooks import ManualVerifier, WebhookProcessor, sign_payload

SECRET = "whsec_test_secret_for_the_simulator"


def demo_config() -> BillingConfig:
    plans = {
        "pro_monthly": Plan("pro_monthly", "pro", "month", "price_pro_month"),
        "pro_yearly": Plan("pro_yearly", "pro", "year", "price_pro_year"),
        "team_monthly": Plan("team_monthly", "team", "month", "price_team_month"),
        "credits_100": Plan("credits_100", "pro", "once", "price_credits_100", credits=100, trial=False),
    }
    return BillingConfig(plans=plans)


class Clock:
    def __init__(self, t=START):
        self.t = t

    def __call__(self):
        return self.t


def build_world():
    """Everything wired together with fakes: config, store, gateway, service, processor and a clock."""
    clock, config, store, gateway = Clock(), demo_config(), InMemoryBillingStore(), FakeGateway()
    sent = []
    handlers = StripeHandlers(store, config, notify=lambda kind, user, **d: sent.append((kind, user)))
    processor = WebhookProcessor(ManualVerifier(SECRET, clock=clock), store, handlers.table(), livemode=False,
                                 expected_api_version=config.expected_api_version, clock=clock)
    service = BillingService(gateway, store, config, clock=clock)
    return clock, config, store, gateway, service, processor, sent


def deliver(processor, clock, event: dict, *, secret: str = SECRET, tamper: bool = False):
    payload = payload_of(event)
    header = sign_payload(payload, secret, int(clock()))
    if tamper:
        payload = payload.replace(b'"status":"active"', b'"status":"canceled"')
    return processor.handle(payload, header)


def run_simulation() -> list:
    clock, config, store, gateway, service, processor, sent = build_world()
    user = User("user-1", "ada@example.com", "Ada")
    rows = []

    def step(label, event, **kw):
        result = deliver(processor, clock, event, **kw)
        decision = service.access(user.id)
        rows.append((label, result.status, result.outcome, "PAID" if decision.paid else "free", decision.reason))
        return result

    start = service.start_checkout(user, "pro_monthly")
    rows.append(("start checkout", 200, "session " + start.session_id, "free", "no subscription"))
    sub = lambda **k: subscription_obj(user_id="user-1", **k)
    t = START
    step("checkout completed", make_event("checkout.session.completed", checkout_session_obj(), created=t))
    step("subscription created (trial)", make_event("customer.subscription.created",
         sub(status="trialing", trial_end=t + 14 * DAY, period_end=t + 14 * DAY), created=t + 1))
    clock.t = t + 14 * DAY
    step("trial ends, first payment", make_event("customer.subscription.updated",
         sub(status="active", period_end=t + 44 * DAY, trial_end=t + 14 * DAY), created=t + 14 * DAY))
    clock.t = t + 44 * DAY
    step("renewal payment fails", make_event("customer.subscription.updated",
         sub(status="past_due", period_end=t + 44 * DAY), created=t + 44 * DAY))
    clock.t = t + 46 * DAY
    step("two days later (grace period)", make_event("invoice.payment_failed", invoice_obj(attempt_count=2),
         created=t + 46 * DAY))
    clock.t = t + 48 * DAY
    step("four days later", make_event("invoice.payment_failed", invoice_obj(attempt_count=3), created=t + 48 * DAY))
    step("customer pays", make_event("customer.subscription.updated",
         sub(status="active", period_end=t + 74 * DAY), created=t + 48 * DAY + 60))
    step("customer cancels", make_event("customer.subscription.updated",
         sub(status="active", period_end=t + 74 * DAY, cancel_at_period_end=True), created=t + 49 * DAY))
    clock.t = t + 75 * DAY
    step("period ends", make_event("customer.subscription.deleted",
         sub(status="canceled", period_end=t + 74 * DAY, canceled_at=t + 74 * DAY), created=t + 74 * DAY))
    return rows, sent


def format_rows(rows: list) -> str:
    lines = [f"{'step':<32} {'HTTP':>4}  {'outcome':<26} {'access':<6} reason", "-" * 100]
    for label, status, outcome, access, reason in rows:
        lines.append(f"{label:<32} {status:>4}  {outcome:<26} {access:<6} {reason}")
    return "\n".join(lines)
