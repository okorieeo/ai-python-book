# AI Chat: Django API, Next.js web app, Expo mobile app

## How to verify your work
- Run `make check` before you say anything is done. It must pass. Show me the output.
- Backend tests: `pytest backend -q`. Web: `npm test` and `npx tsc --noEmit` in web/. Mobile: `npm test` in mobile/.

## Conventions
- API errors use the shape in @docs/api-conventions.md. Another user's object returns the SAME 404 as a missing one, never 403.
- Money is an integer in the smallest unit (kobo, cents). Never use floats for money.
- The AI provider SDK is imported only in backend/ai/anthropic_client.py.
- New behaviour comes with a test that you have watched fail first.
- Commits are small and conventional: `type(scope): summary`, one step per commit.

## Never
- Never edit .env files, lockfiles, or a migration that already exists. Create a new migration.
- Never run eas submit, a production build, or a production migration. Those are my decisions.
- Never change a test to make it pass. If a test is wrong, tell me and explain why.

## Workflow
- For anything bigger than one small diff: explore, write PLAN.md (use /feature-plan), wait for my review, then /step N.
- Use the code-reviewer subagent on your own diff before you finish.
