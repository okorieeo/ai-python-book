STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")                 # sk_test_... or rk_test_...
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY")       # pk_test_...
STRIPE_WEBHOOK_SECRETS = env.list("STRIPE_WEBHOOK_SECRETS")  # whsec_...; two values while rotating

BILLING_PLANS = {                                            # our key -> Stripe price. The browser sends only the key.
    "pro_monthly":  {"tier": "pro",  "interval": "month", "price_id": env("STRIPE_PRICE_PRO_MONTHLY")},
    "pro_yearly":   {"tier": "pro",  "interval": "year",  "price_id": env("STRIPE_PRICE_PRO_YEARLY")},
    "team_monthly": {"tier": "team", "interval": "month", "price_id": env("STRIPE_PRICE_TEAM_MONTHLY")},
    "credits_100":  {"tier": "pro",  "interval": "once",  "price_id": env("STRIPE_PRICE_CREDITS_100"),
                     "credits": 100, "trial": False},
}
BILLING_SUCCESS_URL = "https://app.example.com/billing/success?session_id={CHECKOUT_SESSION_ID}"
BILLING_CANCEL_URL = "https://app.example.com/billing"
BILLING_RETURN_URL = "https://app.example.com/billing"
BILLING_ALLOWED_HOSTS = ["app.example.com"]
BILLING_TRIAL_DAYS = 14
BILLING_GRACE_DAYS = 3
