"""Walk through the billing system end to end. Everything is rolled back, so nothing is left behind.

    python manage.py migrate
    python manage.py billing_demo
"""
from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from rest_framework.test import APIClient

from billing.ai import pick_model
from billing.entitlements import get_entitlements
from billing.invoices import build_proration_invoice, build_renewal_invoice, describe, finalize, record_payment
from billing.models import Plan, Price
from billing.pricing import format_money, unit_economics
from billing.seed import seed_default_plans
from billing.subscriptions import apply_plan_change, start_subscription
from billing.usage import LimitExceeded, check_can_use, record_usage, usage_summary

UTC = timezone.utc
# Our cost per answered message in micro-dollars, from Chapter 27's worked example
# (a ten-turn chat: $0.0054 on Haiku 5.5 and $0.1085 on Sonnet 5.5, so a tenth of that per turn).
COST_PER_MESSAGE_MICRO = {"claude-haiku-5-5": 540, "claude-sonnet-5-5": 10_850}


class Rollback(Exception):
    pass


class Command(BaseCommand):
    help = "Print a worked example of plans, limits, upgrades, invoices and unit economics."

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                self.run()
                raise Rollback
        except Rollback:
            self.stdout.write("\n(everything above was rolled back: no data was kept)")

    def say(self, text=""):
        self.stdout.write(text)

    def run(self):
        seed_default_plans()
        User = get_user_model()
        ada = User.objects.create_user("demo-ada")
        ben = User.objects.create_user("demo-ben")

        self.say("1. The pricing table (prices in the smallest unit, shown formatted)")
        for plan in Plan.objects.all():
            usd = Price.objects.filter(plan=plan, currency="USD", is_active=True).first()
            ngn = Price.objects.filter(plan=plan, currency="NGN", is_active=True).first()
            ents = {e.key: e for e in plan.entitlements.all()}
            msgs = ents["ai.messages_per_month"].limit
            self.say(f"   {plan.code:<8} {format_money(usd.amount_minor, 'USD') if usd else '$0.00':>8} "
                     f"{format_money(ngn.amount_minor, 'NGN') if ngn else '₦0.00':>12}  "
                     f"{msgs:>5} messages/month  agent tools: {ents['ai.agent_tools'].enabled}")

        self.say("\n2. Ada on the Free plan runs into her limit")
        jan = datetime(2026, 1, 5, 9, tzinfo=UTC)
        self.say(f"   model for Ada: {pick_model(ada)}")
        for i in range(30):
            record_usage(ada, "ai.message", 1, f"ada-{i}", now=jan)
        try:
            check_can_use(ada, "ai.message", 1, jan)
        except LimitExceeded as exc:
            self.say(f"   31st message refused: limit {exc.limit}, used {exc.used}")

        self.say("\n3. Ada subscribes to Starter on 1 Feb, then upgrades to Pro halfway through")
        feb1 = datetime(2026, 2, 1, 0, tzinfo=UTC)
        sub = start_subscription(ada, Price.objects.get(plan__code="starter", currency="USD", is_active=True), now=feb1)
        self.say(f"   period: {sub.current_period_start:%d %b} to {sub.current_period_end:%d %b}, status {sub.status}")
        change = apply_plan_change(sub, Price.objects.get(plan__code="pro", currency="USD", is_active=True),
                                   now=datetime(2026, 2, 15, 0, tzinfo=UTC))
        p = change.proration
        self.say(f"   upgrade {change.effective}: credit {format_money(p.credit_minor, 'USD')} for unused "
                 f"Starter, charge {format_money(p.charge_minor, 'USD')} for the rest on Pro, "
                 f"net {format_money(p.net_minor, 'USD')}")
        inv = finalize(build_proration_invoice(sub, p, old_name="Starter", new_name="Pro"), now=datetime(2026, 2, 15, tzinfo=UTC))
        for line in describe(inv):
            self.say("     " + line)

        self.say("\n4. A month of heavy use on Pro, then the renewal invoice with 7.5% tax (an example rate)")
        record_usage(ada, "ai.message", 1650, "ada-feb", now=datetime(2026, 2, 20, tzinfo=UTC))
        s = usage_summary(ada, datetime(2026, 2, 20, tzinfo=UTC))["ai.messages_per_month"]
        self.say(f"   usage: {s['used']} of {s['limit']} included")
        inv = finalize(build_renewal_invoice(sub, tax_rate_bps=750), now=datetime(2026, 3, 1, tzinfo=UTC))
        for line in describe(inv):
            self.say("     " + line)
        _, first = record_payment(inv, provider="stripe", provider_payment_id="pi_demo_1",
                                  amount_minor=inv.total_minor, currency="USD", now=datetime(2026, 3, 1, tzinfo=UTC))
        _, again = record_payment(inv, provider="stripe", provider_payment_id="pi_demo_1",
                                  amount_minor=inv.total_minor, currency="USD")
        inv.refresh_from_db()
        self.say(f"   payment recorded: {first}; the same payment message arriving again was recorded: {again}")
        self.say(f"   invoice status: {inv.status}")

        self.say("\n5. What the signed-in user sees at GET /api/v1/billing/me/ (Ben, on Pro since just now)")
        start_subscription(ben, Price.objects.get(plan__code="pro", currency="USD", is_active=True))
        client = APIClient()
        client.force_authenticate(ben)
        data = client.get("/api/v1/billing/me/").json()
        self.say(f"   plan: {data['plan']}")
        self.say(f"   status: {data['subscription']['status']}, cancel at period end: {data['subscription']['cancel_at_period_end']}")
        ents = get_entitlements(ben)
        self.say("   entitlements: " + ", ".join(f"{k}={'unlimited' if e.limit is None and e.kind == 'limit' else (e.limit if e.kind == 'limit' else e.enabled)}"
                                                 for k, e in ents.items()))
        u = data["usage"]["ai.messages_per_month"]
        self.say(f"   usage: {u['used']} used, {u['remaining']} remaining of {u['limit']}")

        self.say("\n6. Unit economics: does each plan make money? (example fee 2.9% + 30 cents; model costs from Chapter 27)")
        self.say(f"   {'plan':<8}{'model':<20}{'price':>8}{'cost @40%':>11}{'margin @40%':>13}{'cost @100%':>12}{'margin @100%':>14}")
        for code, model in (("starter", "claude-haiku-5-5"), ("pro", "claude-sonnet-5-5")):
            price = Price.objects.get(plan__code=code, currency="USD", is_active=True)
            limit = Plan.objects.get(code=code).entitlements.get(key="ai.messages_per_month").limit
            per_msg = COST_PER_MESSAGE_MICRO[model]
            row = []
            for share in (40, 100):
                used = limit * share // 100
                e = unit_economics(price_minor=price.amount_minor, cost_micro_usd=used * per_msg, fee_bps=290, fixed_fee_minor=30)
                row.append((e["ai_cost_micro"] / 1e6, e["margin"] * 100))
            self.say(f"   {code:<8}{model:<20}{format_money(price.amount_minor, 'USD'):>8}"
                     f"{'$%.2f' % row[0][0]:>11}{'%.0f%%' % row[0][1]:>13}{'$%.2f' % row[1][0]:>12}{'%.0f%%' % row[1][1]:>14}")
        free_limit = Plan.objects.get(code="free").entitlements.get(key="ai.messages_per_month").limit
        free_cost = free_limit * COST_PER_MESSAGE_MICRO["claude-haiku-5-5"]
        self.say(f"   free     claude-haiku-5-5   costs ${free_cost / 1e6:.4f} per user per month at full use, "
                 f"so 1,000 such users cost ${1000 * free_cost / 1e6:.2f}")
