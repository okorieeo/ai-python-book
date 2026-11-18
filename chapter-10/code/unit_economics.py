"""A small pricing model: what does one subscriber cost, and what is left over?

ALL NUMBERS ARE ILLUSTRATIVE ASSUMPTIONS. Replace them with current provider prices and your own data.
"""

ASSUMPTIONS = {
    "ai_cost_per_million_input_tokens": 3.00,    # USD, example only
    "ai_cost_per_million_output_tokens": 15.00,  # USD, example only
    "payment_fee_percent": 3.0,                  # percent of each payment, example only
    "payment_fee_fixed": 0.30,                   # USD per payment, example only
    "infrastructure_per_month": 60.00,           # VPS, backups, email, monitoring, domain
    "subscribers": 200,                          # paying users used to share fixed costs
}

PLANS = {
    #          price/month  input tokens used  output tokens used  (per subscriber per month)
    "Basic": {"price": 9.00,  "input_tokens": 300_000,   "output_tokens": 80_000},
    "Pro":   {"price": 19.00, "input_tokens": 1_000_000, "output_tokens": 300_000},
}

def plan_report(name, plan, a):
    ai_cost = (plan["input_tokens"] / 1e6) * a["ai_cost_per_million_input_tokens"] \
            + (plan["output_tokens"] / 1e6) * a["ai_cost_per_million_output_tokens"]
    fee = plan["price"] * a["payment_fee_percent"] / 100 + a["payment_fee_fixed"]
    infra = a["infrastructure_per_month"] / a["subscribers"]
    profit = plan["price"] - ai_cost - fee - infra
    return {"name": name, "price": plan["price"], "ai": ai_cost, "fee": fee, "infra": infra,
            "profit": profit, "margin": profit / plan["price"] * 100}

def show(a):
    print(f"{'Plan':<6}{'Price':>8}{'AI cost':>9}{'Pay fee':>9}{'Infra':>8}{'Profit':>9}{'Margin':>9}")
    for name, plan in PLANS.items():
        r = plan_report(name, plan, a)
        print(f"{r['name']:<6}{r['price']:>8.2f}{r['ai']:>9.2f}{r['fee']:>9.2f}{r['infra']:>8.2f}{r['profit']:>9.2f}{r['margin']:>8.0f}%")

print("Base case (per subscriber per month, USD):")
show(ASSUMPTIONS)

print("\nWhat if every subscriber uses THREE times as many tokens?")
heavy = {k: {**v, "input_tokens": v["input_tokens"] * 3, "output_tokens": v["output_tokens"] * 3} for k, v in PLANS.items()}
original = dict(PLANS)
PLANS.update(heavy)
show(ASSUMPTIONS)
PLANS.update(original)

print("\nMonthly profit of the whole business as the number of Pro subscribers grows:")
for subscribers in (10, 30, 100, 300):
    a = {**ASSUMPTIONS, "subscribers": subscribers}
    pro = plan_report("Pro", PLANS["Pro"], a)
    total_profit = pro["profit"] * subscribers
    print(f"  {subscribers:>3} Pro subscribers -> monthly profit {total_profit:>8.2f} USD")

a = ASSUMPTIONS
pro = PLANS["Pro"]
pro_ai = (pro["input_tokens"] / 1e6) * a["ai_cost_per_million_input_tokens"] + (pro["output_tokens"] / 1e6) * a["ai_cost_per_million_output_tokens"]
contribution = pro["price"] - pro_ai - (pro["price"] * a["payment_fee_percent"] / 100 + a["payment_fee_fixed"])
print(f"\nEach Pro subscriber contributes {contribution:.2f} USD toward the {a['infrastructure_per_month']:.0f} USD fixed costs, "
      f"so break-even is at {-(-a['infrastructure_per_month'] // contribution):.0f} subscribers.")
tokens_per_dollar = 1e6 / (a["ai_cost_per_million_input_tokens"] * 0.77 + a["ai_cost_per_million_output_tokens"] * 0.23)
print(f"\nRough token budget: at a 70% margin target, a ${pro['price']:.0f} plan can afford about "
      f"{pro['price'] * 0.3 * tokens_per_dollar / 1e6:.1f}M tokens per month (assuming a 77/23 input/output split).")
