# AI Chat SaaS

Monorepo: `backend/` (Django 5 + DRF + Channels + Celery), `web/` (Next.js, App Router, TypeScript),
`mobile/` (Expo, React Native, TypeScript), `contracts/` (OpenAPI), `docs/specs/` (feature specs),
`tools/` (small Python checks, standard library only).

## How we build features (read this first)
1. A feature starts as a spec in `docs/specs/<name>.md` with numbered acceptance criteria (AC-1, AC-2, ...).
2. The spec becomes a task list in `docs/specs/<name>-tasks.md`. One task = one prompt = one commit.
3. **Contract first.** `contracts/openapi.json` is the single source of truth for the API. Change the contract,
   then the backend, then regenerate types (`npm run api:types` in `web/` and `mobile/`), then the UIs.
4. Every acceptance criterion needs a test whose name or comment contains its id, for example `AC-4`.
5. Never edit files under `*/generated/`. Regenerate them.

## Commands
- Contract: `python -m tools.contract_lint contracts/openapi.json`
- Breaking changes: `python -m tools.contract_diff <old.json> <new.json>`
- Traceability: `python -m tools.trace_check docs/specs/<name>.md backend web mobile`
- Backend: `cd backend && python manage.py test` and `ruff check . && ruff format .`
- Web: `cd web && npm run lint && npm run typecheck && npm test`
- Mobile: `cd mobile && npm run typecheck && npm test`
- Whole stack: `docker compose up --build`

## Conventions
- API: `/api/v1/...`, every query scoped to `request.user`, other people's objects answer 404, errors are `{code, message}`.
- Web: server components by default, `"use client"` only where needed, API calls only through `src/lib/api/`.
- Mobile: tokens only in expo-secure-store; API calls only through `src/lib/`.
- Secrets: never read, print or commit `.env`. Use `.env.example` for names only.

## Boundaries
- Do not touch `backend/` while working in a `web/` or `mobile/` task, and the other way round.
- Ask before adding a dependency. Say what it is for and what you checked about it.
