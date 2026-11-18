# Chapter 36 code: Stripe Integration

    python -m unittest stripebilling.test_stripebilling   # 93 tests: no network, no Stripe account, no Django
    python -m stripebilling.cli simulate                  # a whole subscription life through the real processor
    python -m stripebilling.cli attacks                   # bad, repeated, stale and out-of-order webhooks
    python -m stripebilling.cli plans
    python -m stripebilling.tour                          # request parameters, signatures, access decisions

    pip install "stripe>=16,<17"                          # pin it: the SDK major fixes the Stripe API version
    # then see section 36.12 (test mode, the Stripe CLI, the Django app)

Layout
- `stripebilling/`  plain Python: plan table, request builders, access decision, webhook verifier and
  processor, handlers, billing service, fixtures and a fake Stripe. Fully tested.
  `gateway.py` (the only file that calls Stripe) and `OfficialVerifier` were NOT executed (no network, no keys).
- `billing_stripe/` Django app: models, database store, views, URLs, admin, Celery task and two
  management commands (`stripe_reconcile`, `stripe_replay`). NOT executed (no Django, Postgres or Stripe).
- `frontend/` Next.js pages and components. NOT executed.
- `mobile/` React Native screen and helpers. NOT executed. Read section 36.9 (app store rules) first.

Keys belong in environment variables, never in Git. Use test-mode keys (`sk_test_...`) everywhere except production.
