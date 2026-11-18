INSTALLED_APPS += ["payments"]

# ---------------------------------------------------------------- payments (Chapter 38)
PAYMENT_GATEWAYS = {"stripe": env.bool("ENABLE_STRIPE", default=False), "paystack": env.bool("ENABLE_PAYSTACK", default=True)}
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")            # sk_test_... in development
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")    # whsec_..., from the CLI or the dashboard
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", default="")        # sk_test_... in development
PAYSTACK_CHECK_WEBHOOK_IP = env.bool("PAYSTACK_CHECK_WEBHOOK_IP", default=False)   # True behind a trusted proxy in production
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")

INVOICE_PREFIX = "INV"
TAX_RATE_BP = 750                      # 7.5%: confirm your own rate with an accountant
PRICES_INCLUDE_TAX = False
SELLER_DETAILS = {"name": "Your Company Ltd", "address": "...", "tax_id": "..."}

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update({"checkout": "10/hour"})

CELERY_BEAT_SCHEDULE.update({
    "sweep-missed-webhooks": {"task": "payments.tasks.sweep_missed_webhooks", "schedule": 300},
    "reconcile-paystack": {"task": "payments.tasks.reconcile_gateway", "schedule": crontab(hour=2, minute=10), "args": ("paystack",)},
    "reconcile-stripe": {"task": "payments.tasks.reconcile_gateway", "schedule": crontab(hour=2, minute=20), "args": ("stripe",)},
})
