---
paths:
  - "web/**/*.{ts,tsx}"
  - "mobile/**/*.{ts,tsx}"
---

# Frontend rules

- Server state with TanStack Query; local UI state with `useState`; no global store for server data.
- Never read a secret from `process.env` in client code; only `NEXT_PUBLIC_` and `EXPO_PUBLIC_` values are public.
- Every API call sends the Authorization header from the shared client in `lib/api.ts`; do not call `fetch` directly.
- Label AI output from the `ai_generated` field of the API response, not from screen-specific code.
