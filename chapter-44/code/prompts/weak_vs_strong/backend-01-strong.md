Add an endpoint that lets a user rename one of their own conversations: PATCH /api/v1/conversations/{id}/ with {"title": "..."}.

Context: follow the pattern of the existing `archive` action in @backend/chat/views.py and its serializer in @backend/chat/serializers.py. Ownership is already enforced by OwnedQuerysetMixin (Chapter 17); reuse it rather than writing a new check.

Constraints:
- Only the owner may rename. Someone else's conversation must return the same 404 as a missing one.
- The title is 1 to 80 characters after trimming whitespace; an empty or longer title is a 400.
- Do not change the Conversation model and do not add a migration.
- No new dependencies. Do not touch the streaming code in backend/ai/.

Done when:
- New tests in backend/chat/tests/test_rename.py cover: owner gets 200, another user gets a 404 identical to a missing id, an empty title gets 400, an 81-character title gets 400.
- `pytest backend/chat -q` and `make check` both pass. Show me the output.
