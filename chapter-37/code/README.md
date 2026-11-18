# Chapter 37 code: Paystack Integration

    python -m unittest paystackbilling.test_paystackbilling   # 100 tests: no network, no Paystack account, no Django
    python -m paystackbilling.cli simulate                    # a subscription life, with a trial, through the real processor
    python -m paystackbilling.cli attacks                     # bad, repeated, forged and wrong-mode webhooks
    python -m paystackbilling.cli plans
    python -m paystackbilling.tour                            # money, request parameters, signatures, access decisions

    pip install requests                                      # the only dependency of the gateway
    # then see section 37.12 (test mode, ngrok or the Paystack test webhook URL, the Django app)

Layout
- `paystackbilling/` plain Python: money, plan table, request builders, access decision, webhook verifier and
  processor, handlers, billing service, fixtures and a fake Paystack. Fully tested.
  `gateway.py` is tested against a stand-in HTTP session only: it was NOT run against the real Paystack API.
- `billing_paystack/` Django app: models, database store, views, URLs, admin, Celery task and management
  commands (`paystack_setup_plans`, `paystack_reconcile`). NOT executed (no Django, Postgres or Paystack).
- `frontend/` Next.js pages and components. NOT executed.
- `mobile/` React Native checkout WebView. NOT executed. Read section 37.10 (app store rules) first.

Secret keys (sk_test_..., sk_live_...) belong in environment variables, never in Git, never in a frontend or app bundle.
