Fix a bug where one Stripe event credits a user twice.

Symptom: support reports two customers each received double credits for a single purchase. Both show the same event id in the Stripe dashboard, delivered twice about 40 seconds apart.
Context: the handling lives in @backend/billing/webhooks.py (process_event) and @backend/billing/handlers.py. Read both and the existing tests in @backend/tests/test_events.py before changing anything.

Work in this order:
1. Write a failing test in backend/tests/test_handlers.py that delivers the same checkout.session.completed event twice and expects credits to be added once. Run it and show me that it fails.
2. Find the cause and fix it with the smallest change that makes the test pass.

Constraints:
- Do not change the signature verification and do not edit any existing test.
- No schema changes in this step; if you believe one is needed, stop and tell me why.
- Do not "fix" it by swallowing exceptions.

Done when: the new test failed before the fix and passes after (show both runs), and `pytest backend/tests -q` passes.
