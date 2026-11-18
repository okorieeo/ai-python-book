# Chapter 38 code: Running Both Gateways Together

Extends the Chapter 17 project (audit app, throttles, redaction) and the Chapter 34 privacy app.

    core/payments/        plain Python, no Django: money, states, gateway, webhooks, normalize, routing,
                          checkout, events, refunds, invoices, reconciliation, fakes, memory
    core/test_payments.py 71 unittest tests:  python -m unittest core.test_payments -v
    payments/             Django app: models, repo, registry, services, views, tasks, admin, urls, tests
    payments/gateways/    stripe_gw.py, paystack_gw.py  (the only files that talk to a provider)

NOT executed while writing the book (no Django, Stripe SDK, network): payments/ and its tests. Run them in
your project in test mode first. Chapters 35 to 37 were not available: see section 38.2 for the names this
code assumes (billing.services.price_for, describe_purchase, activate_for_payment).

Settings: see section 38.14. Add PAYMENT_CREATED/SUCCEEDED/REFUND audit actions as listed in section 38.2.
