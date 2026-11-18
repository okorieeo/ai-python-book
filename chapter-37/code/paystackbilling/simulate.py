"""A scripted subscription lifecycle sent through the real webhook processor with signed payloads."""
from .config import PaystackConfig, Plan
from .entitlements import DAY
from .fakes import FakeGateway
from .fixtures import (START, body_of, charge_data, event, invoice_data, iso, subscription_obj)
from .handlers import PaystackHandlers
from .service import PaystackBillingService, User
from .store import InMemoryBillingStore
from .webhooks import PaystackVerifier, WebhookProcessor, sign_body

SECRET = "sk_test_simulator_secret_key"


def demo_config() -> PaystackConfig:
    plans = {
        "pro_monthly_ngn": Plan("pro_monthly_ngn", "pro", "monthly", 500000, "NGN", "PLN_pro_m", trial_days=14),
        "pro_yearly_ngn": Plan("pro_yearly_ngn", "pro", "annually", 5000000, "NGN", "PLN_pro_y"),
        "team_monthly_ngn": Plan("team_monthly_ngn", "team", "monthly", 1500000, "NGN", "PLN_team_m"),
        "pro_monthly_usd": Plan("pro_monthly_usd", "pro", "monthly", 1000, "USD", "PLN_pro_m_usd"),
        "credits_100": Plan("credits_100", "pro", "once", 200000, "NGN", credits=100),
    }
    return PaystackConfig(plans=plans)


class Clock:
    def __init__(self, t=START):
        self.t = t

    def __call__(self):
        return self.t


def build_world():
    clock, config, store = Clock(), demo_config(), InMemoryBillingStore()
    gateway = FakeGateway(config, now=START)
    sent = []
    notify = lambda kind, user, **d: sent.append((kind, user))
    handlers = PaystackHandlers(store, config, gateway, notify, clock)
    processor = WebhookProcessor(PaystackVerifier(SECRET), store, handlers.table(), livemode=False, clock=clock)
    service = PaystackBillingService(gateway, store, config, clock, notify)
    return clock, config, store, gateway, service, processor, sent


def deliver(processor, evt: dict, *, key: str = SECRET, algorithm_body=None, tamper: bool = False):
    body = body_of(evt)
    signature = sign_body(body, key)
    if tamper:
        body = body.replace(b'"paid":true', b'"paid":false')
    return processor.handle(body, signature)


def run_simulation():
    clock, config, store, gateway, service, processor, sent = build_world()
    user = User("user-1", "ada@example.com", "Ada")
    rows = []

    def step(label, evt=None):
        result = deliver(processor, evt) if evt else None
        decision = service.access(user.id)
        rows.append((label, result.status if result else 200, result.outcome if result else "-",
                     "PAID" if decision.paid else "free", decision.reason))

    start = service.start_subscription(user, "pro_monthly_ngn")
    pay = gateway.pay(start.reference)                               # the customer pays the N50 card check
    rows.append(("trial: pays the card check", 200, "reference " + start.reference[:11] + "...", "free", "no subscription"))
    step("charge.success (card saved)", event("charge.success", pay))
    code = store.subscription_for(user.id).subscription_code
    sub = gateway.subscriptions[code]
    t_trial_end = store.subscription_for(user.id).trial_end

    clock.t = t_trial_end + 3600
    sub["next_payment_date"] = iso(t_trial_end + 30 * DAY)           # Paystack charged and moved the date
    step("trial ends, first payment", event("invoice.update", invoice_data(sub, paid=True, reference="ref_first")))

    due = t_trial_end + 30 * DAY
    clock.t = due + 3600
    sub["status"] = "attention"
    step("renewal fails", event("invoice.payment_failed", invoice_data(sub, paid=False, reference="ref_fail")))
    clock.t = due + 2 * DAY
    step("two days later (grace period)")
    clock.t = due + 4 * DAY
    step("four days later")
    sub["status"], sub["next_payment_date"] = "active", iso(due + 4 * DAY + 30 * DAY)
    step("customer updates card, pays", event("invoice.update", invoice_data(sub, paid=True, reference="ref_paid2")))

    service.cancel(user)
    step("customer cancels", event("subscription.not_renew", {"domain": "test", "subscription_code": code,
                                                                "customer": sub["customer"]}))
    clock.t = due + 4 * DAY + 31 * DAY
    sub["status"] = "cancelled"
    step("period ends", event("subscription.disable", {"domain": "test", "subscription_code": code,
                                                         "status": "cancelled", "customer": sub["customer"]}))
    return rows, sent


def format_rows(rows) -> str:
    lines = [f"{'step':<32} {'HTTP':>4}  {'outcome':<24} {'access':<6} reason", "-" * 104]
    for label, status, outcome, access, reason in rows:
        lines.append(f"{label:<32} {status:>4}  {outcome:<24} {access:<6} {reason}")
    return "\n".join(lines)
