Read @docs/erd.txt and @CLAUDE.md. In plan mode, propose Django models for the `conversations` app that match the ERD exactly.

Constraints:
- `public_id` UUID on every model that appears in a URL; integer ids never leave the server.
- Explicit `on_delete`, `related_name`, `max_length`; indexes and unique constraints exactly as listed.
- Money, if any, as integer minor units. Timestamps are timezone-aware.
- Do not create serializers, views or tests yet. Do not run `migrate`.

Show me: the plan, then the models, then the output of `python manage.py makemigrations --dry-run -v 3`.
After I approve: run `python -m core.review.erd_check docs/erd.txt backend/conversations/models.py` and fix every error it reports.
