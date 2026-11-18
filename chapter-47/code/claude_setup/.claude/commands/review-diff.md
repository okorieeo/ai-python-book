---
description: Review the current uncommitted changes against this app's rules
---
Review `git diff` in a fresh pass. Check, in this order, and give each concern a file and line:
1. Secrets or tokens in code, logs or `EXPO_PUBLIC_` variables.
2. Network calls that bypass `lib/api.ts`, or token storage outside SecureStore.
3. Writes that would be lost offline, or retried without an idempotency key.
4. Navigation built from untrusted data (notification payloads, deep links).
5. New dependencies, or changes to `app.config.ts` or `eas.json` that were not asked for.
6. Missing states (loading, empty, error, offline) and missing tests.
For each concern say what would show you are wrong. End with what you did NOT check.
