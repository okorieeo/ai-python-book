PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY")             # sk_test_... or sk_live_...; also signs the webhooks
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY")             # pk_test_..., only if you use the popup

PAYSTACK_PLANS = {                                           # our key -> a Paystack plan. The browser sends only the key.
    "pro_monthly_ngn":  {"tier": "pro",  "interval": "monthly",   "currency": "NGN", "amount": "5000",
                         "plan_code": env("PAYSTACK_PLAN_PRO_MONTHLY_NGN"), "trial_days": 14},
    "pro_yearly_ngn":   {"tier": "pro",  "interval": "annually",  "currency": "NGN", "amount": "50000",
                         "plan_code": env("PAYSTACK_PLAN_PRO_YEARLY_NGN")},
    "team_monthly_ngn": {"tier": "team", "interval": "monthly",   "currency": "NGN", "amount": "15000",
                         "plan_code": env("PAYSTACK_PLAN_TEAM_MONTHLY_NGN")},
    "pro_monthly_usd":  {"tier": "pro",  "interval": "monthly",   "currency": "USD", "amount": "10",
                         "plan_code": env("PAYSTACK_PLAN_PRO_MONTHLY_USD")},
    "credits_100":      {"tier": "pro",  "interval": "once",      "currency": "NGN", "amount": "2000", "credits": 100},
}
PAYSTACK_CALLBACK_URL = "https://app.example.com/billing/callback"
PAYSTACK_ALLOWED_HOSTS = ["app.example.com"]
BILLING_GRACE_DAYS = 3
