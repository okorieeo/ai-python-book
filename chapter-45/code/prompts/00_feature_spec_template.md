# Feature spec: <name>

## Goal (one sentence a customer would understand)
<e.g. A signed-in user can send a message in one of their conversations and receive the AI's reply.>

## Users and roles
<who may do this; which roles from core/rbac.py; who must NOT be able to>

## API contract
- Method and path: `POST /api/v1/conversations/<public_id>/send/`
- Headers: `Authorization: Bearer ...`, `Idempotency-Key: <8-80 chars>`
- Request body: `{"content": "string, 1-8000 characters"}`
- Success: `201 {"public_id", "role", "content", "status", "ai_generated", "created_at"}`; `200` with the same body for a repeated key
- Errors: 400 validation, 401 not signed in, 403 role not allowed, 404 not found OR not yours, 429 throttled, 503 provider timeout (retry with the same key)

## Data (link to docs/erd.txt; list only changes)
<new models or fields, constraints, indexes, retention rule, whether personal data>

## Rules and edge cases
- <ownership, idempotency, limits, ordering, what happens on provider failure>

## Non-goals (what NOT to build now)
- <streaming, attachments, anything tempting but out of scope>

## Security and privacy
- <owner scoping, PII sent to the provider goes through core/responsible/pii.py, nothing sensitive in logs>

## Acceptance criteria (each one becomes a test)
1. Unauthenticated request returns 401.
2. Another user's conversation returns 404 and nothing is saved.
3. Empty or oversize content returns 400 and the provider is not called.
4. Same Idempotency-Key twice creates one user message and one reply.
5. A provider timeout returns 503; retrying with the same key succeeds without a second user message.
6. The list endpoint uses a constant number of queries.
