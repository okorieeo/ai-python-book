For the endpoint(s) I just built, write a test class with these cases, one test each, and run it:
1 unauthenticated -> 401   2 another user's object -> 404 and nothing changed   3 wrong role -> 403
4 validation failures -> 400   5 happy path -> exact status and body keys (no internal ids)
6 repeated Idempotency-Key -> one record   7 throttle -> 429   8 constant query count (assertNumQueries)
9 mass assignment: extra fields such as `user` or `public_id` in the body are ignored.

Then act as a security reviewer for ONLY the diff on this branch (git diff main...HEAD). Check: authentication, authorization and ownership,
input validation, injection, secrets, logging of personal data, error messages that leak internals, race conditions, missing timeouts.
Report findings as a table: severity, file:line, what is wrong, a concrete fix. Do not change any code in this step.
