# Chapter 35 code: the billing app

A Django app for plans, prices, entitlements, subscriptions, usage metering, invoices,
payments and webhook events. Provider-independent: Chapters 36 and 37 plug Stripe and
Paystack into it.

`billing_project/` is a tiny project that exists only so the app can run and be tested on its
own. In your real backend, copy the `billing/` folder next to `manage.py`, add `"billing"` to
`INSTALLED_APPS`, copy the `BILLING_*` settings from `billing_project/settings.py`, and include
`billing.urls` (see section 35.10).

    pip install -r requirements.txt
    python manage.py check
    python manage.py migrate
    python manage.py seed_billing        # the example plans (prices are examples, not advice)
    python manage.py test billing        # 92 tests; run them on PostgreSQL too
    python manage.py billing_demo        # a worked example; rolled back, leaves no data

Files in `billing/`: `models.py` (the data model), `registry.py` (the list of entitlements),
`pricing.py` (money, proration, overage, unit economics), `entitlements.py` (what a user may do now),
`usage.py` (limits and metering), `subscriptions.py` (the lifecycle), `invoices.py` (invoices and
payments), `webhooks.py` (store first, process once), `ai.py` (the seam to the AI layer),
`permissions.py` and `api.py` (the API), `reports.py`, `seed.py`, `admin.py`.
