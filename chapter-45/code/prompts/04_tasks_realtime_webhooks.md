Add a Celery task and a Channels consumer for the conversations app, following @CLAUDE.md and @docs/chapters-notes.md.

Celery task: idempotent (safe to run twice), arguments are ids and strings only, queued with transaction.on_commit,
autoretry with backoff for network errors only, logs the task id and conversation public id, never message text.
Channels consumer: authenticate in connect(), check ownership, close with 4401 (not signed in) or 4404 (missing or not yours),
group name from the public id, handler names match the event types, no other user's data ever sent.
Payment webhooks: do NOT write a new handler. Reuse payments/webhooks from Chapter 38 and only add the call to activate_for_payment.
Write tests first. Show me the plan before any edit.
