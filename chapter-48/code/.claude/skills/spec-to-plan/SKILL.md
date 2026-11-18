---
name: spec-to-plan
description: Turn an approved feature spec into a task-by-task build plan with lanes, dependencies and acceptance criteria per task.
argument-hint: <path to spec>
disable-model-invocation: true
---
Read the spec at $ARGUMENTS and `CLAUDE.md`.

1. Run `python -m tools.spec_lint $ARGUMENTS`. If it reports problems, stop and list them.
2. Write `<spec name>-tasks.md` next to the spec, as a table with columns: ID, Lane (contract, backend, web, mobile, infra, all), Task, Depends on, Covers (AC ids), Done when.
3. Task 1 is always the OpenAPI contract. Backend, web and mobile tasks depend on it, never on each other.
4. Every acceptance criterion must appear in the Covers column of at least one task.
5. Each task must be small enough for one prompt and one commit. If it is not, split it.
6. After the table, write one line saying which tasks can run in parallel.
Do not write any application code. Show me the plan and wait.
