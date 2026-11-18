---
paths:
  - "backend/payments/**/*.py"
  - "backend/core/payments/**/*.py"
---

# Payments rules (loaded only when working on payment code)

- Amounts are `Money` (integer minor units). Compare amount and currency before granting anything.
- Webhook handlers verify the signature on the raw body, deduplicate by (provider, event id) and never log the body.
- A success is never undone by a later failure event; use the state machine in `core/payments/states.py`.
- Invoices are immutable: correct them with a credit note.
- Fail over to another gateway only after a definite rejection, never after a timeout.
