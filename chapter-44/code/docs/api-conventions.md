# API conventions

- Base path `/api/v1/`. JSON in, JSON out.
- Success: the resource, or `{"results": [...], "next": "..."}` for lists.
- Errors: `{"code": "machine_readable", "detail": "Human sentence."}` with the right status.
- An object that exists but belongs to someone else returns **404**, identical to a missing object.
- Money fields are integers in the smallest currency unit, with a separate `currency` field.
- Rate-limited responses carry `Retry-After`.
