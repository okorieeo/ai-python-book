---
name: endpoint-tests
description: Write the standard test suite for a Django REST endpoint (authentication, ownership, validation boundaries, throttling and query count).
argument-hint: "<METHOD /api/v1/path/>"
---
Write tests for this endpoint: $ARGUMENTS

Read the view and serializer, and copy the house style from @backend/tests_django/test_authorization.py and @backend/tests_django/test_query_count.py.

Cover, one test each unless noted:
- an anonymous request gets 401;
- the owner succeeds (assert the response body AND the change in the database);
- another user gets the SAME 404 as a missing object, never 403;
- every validation rule at its boundary (use parametrize);
- a throttled request gets 429, if a throttle is configured;
- a list endpoint stays within a fixed query budget.

Rules: do not edit the view to make a test pass. If a test reveals a bug, stop and report it. Watch each new test fail once (temporarily break the behaviour) before you trust it.
Run `pytest` on the new file and show me the output.
