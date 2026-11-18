---
description: Plan and build a new screen that follows this app's rules
argument-hint: <screen name and what it should do>
---
Add a new screen: $ARGUMENTS

Work in this order, and stop after step 1 so I can approve the plan:
1. Read CLAUDE.md, then look at one existing screen under `app/` and `lib/api.ts`. Write a short plan: the route file, the data it needs (which API endpoint), the states (loading, empty, error, offline), and the tests you will add. Do not write code yet.
2. After I approve: build it with the smallest change. Use `ApiClient` for reads and the offline queue for writes.
3. Run `npx tsc --noEmit` and `npm test` and show me the results.
4. List every file you changed and anything you could not check.
