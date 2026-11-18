---
name: sync-check
description: Check that contract, backend, web and mobile still agree after a change.
disable-model-invocation: true
---
Run these in order and summarise the results in a short table (check, result, one-line note):

1. `python -m tools.contract_lint contracts/openapi.json`
2. `git show main:contracts/openapi.json > /tmp/old.json && python -m tools.contract_diff /tmp/old.json contracts/openapi.json`
3. `python -m tools.sync_check contracts/openapi.json web/src mobile/src`
4. `(cd web && npm run api:types && npm run typecheck)` and `(cd mobile && npm run api:types && npm run typecheck)`
5. `python -m tools.trace_check docs/specs/$ARGUMENTS.md backend web mobile` (if a spec name was given)

If a TypeScript error appears after regenerating types, list each error as a place that must change.
Do not fix anything unless I ask.
