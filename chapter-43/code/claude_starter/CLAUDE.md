# AI Chat SaaS

A chat product with an AI assistant. Django REST API + Celery + Channels (backend/), Next.js web app (web/),
Expo React Native app (mobile/). Payments through Stripe and Paystack. Read docs/architecture.md for the big picture.

## Commands (run from the repository root)
- Start everything for development: `docker compose -f docker-compose.dev.yml up -d`
- Backend tests: `cd backend && python -m pytest -q`
- Backend lint and format: `cd backend && ruff check . && ruff format --check .`
- Framework-free unit tests (fast, no database): `cd backend && python -m unittest discover -s core -p "test_*.py"`
- Web tests and type check: `cd web && npm run test && npm run typecheck`
- Mobile type check: `cd mobile && npx tsc --noEmit`
- Make migrations (never edit applied migrations): `cd backend && python manage.py makemigrations`

## Architecture rules
- Views stay thin. Business logic lives in `services.py` and read queries in `selectors.py` of each app.
- Every queryset that returns user data is scoped to the signed-in user (`filter(user=request.user)`); another user's object returns 404, not 403.
- IDs in URLs and API responses are `public_id` UUIDs, never database integer ids.
- Money is an integer in the smallest unit (kobo, cents) in the `Money` type from `core/payments/money.py`. Never use floats for money.
- Calls to model providers and payment gateways go through the service layer with timeouts; never call a provider SDK from a view.
- Only `backend/payments/gateways/` may import `stripe` or know a Paystack URL.

## Security and privacy (non-negotiable)
- Never log prompts, message text, emails, tokens or card data. Log ids, categories and counts (see `core/security/redaction.py`).
- Never put secrets in code, tests or docs. Read them from environment variables; `.env` files are never committed.
- Personal data sent to the AI provider goes through `core/responsible/pii.py` first.
- Every new model with personal data is added to `core/responsible/data_inventory.py` with a retention rule and an eraser.

## Conventions
- Python 3.12, type hints on new code, 4-space indentation, line length 100.
- TypeScript strict mode; React components are function components with hooks; no `any` without a comment.
- API routes are versioned under `/api/v1/`; add a serializer test for every new endpoint.
- Tests: one failing test first for a bug fix; keep tests deterministic (no real network, fake the clock).

## Git
- One feature or fix per branch named `feature/<short-name>` or `fix/<short-name>`; one logical change per commit.
- Commit messages: imperative mood, under 72 characters, say why when it is not obvious.
- Do not push, force-push or merge: a human does that after reviewing the diff.

## How to work here
- For anything touching more than two files, propose a plan first and wait for approval.
- Run the relevant tests after every change and show the result before saying a task is done.
- If a rule above conflicts with the request, say so instead of guessing.
