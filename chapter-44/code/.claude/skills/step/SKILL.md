---
name: step
description: Implement exactly one step of PLAN.md, verify it, and stop.
argument-hint: "<step number>"
disable-model-invocation: true
---
Implement step $ARGUMENTS of @PLAN.md and nothing else.

- First re-read that step's "Done when" and the rules in CLAUDE.md.
- Follow the pattern of the nearest similar code. Add no dependencies.
- If the step changes behaviour, write the test first and show me it failing.
- When finished, run `make check` and show the output. If it fails, fix the cause, never the check.
- Then STOP. Report: the files you changed, the evidence that "Done when" is met, anything you noticed but did not change, and a one-line conventional commit message. Do not commit.
