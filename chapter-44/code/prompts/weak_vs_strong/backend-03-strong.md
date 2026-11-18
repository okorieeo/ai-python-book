Reduce the number of database queries behind GET /api/v1/conversations/.

Context: django-debug-toolbar shows 26 queries for a user with 25 conversations, which looks like an N+1 on the messages. The view is ConversationViewSet.list in @backend/chat/views.py and the serializer is in @backend/chat/serializers.py. A query budget test is the pattern in @backend/tests_django/test_query_count.py.

Constraints:
- The response shape must not change by a single field.
- No caching, and no new indexes or migrations in this step.
- Only touch the queryset and the serializer; leave pagination and permissions alone.

Done when:
- A test creates 25 conversations with messages and asserts the request uses at most 6 queries (django_assert_max_num_queries).
- Existing tests still pass with `pytest backend/chat -q`.
- You report the query count before and after.
