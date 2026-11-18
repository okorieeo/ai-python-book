INSTALLED_APPS += ["billing_paystack"]
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["billing"] = "30/hour"
CELERY_BEAT_SCHEDULE["paystack-pending"] = {
    "task": "billing_paystack.tasks.reconcile_pending_payments", "schedule": 300}                # every five minutes
CELERY_BEAT_SCHEDULE["paystack-reconcile"] = {
    "task": "billing_paystack.tasks.reconcile_subscriptions", "schedule": crontab(hour=3, minute=20)}

# config/urls.py
path("api/billing/paystack/", include("billing_paystack.urls")),
