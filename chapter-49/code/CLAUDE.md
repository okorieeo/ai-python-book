# Debugging rules (add to the CLAUDE.md from Chapter 48)

- Never change code before you can reproduce the failure, or have said clearly that you cannot.
- Diagnose first (use the bug-investigator subagent), fix second. Keep a log in docs/debug/<id>.md.
- A fix is the smallest change that removes the ROOT cause. No broad try/except, no sleeps, no retries,
  no silenced lint or type errors, no edited generated files, no weakened tests.
- Every bug fix ships with a regression test that fails on the old code and passes on the new.
- Before any commit run: `git diff --cached | python -m tools.fix_gate`.
- Three failed attempts: stop, write down what was ruled out, and ask for a fresh session.
- Never read or print .env or production data. Ask me to run production commands myself and paste redacted output.
- To read container logs: `docker compose logs --since 10m <service> > /tmp/<service>.log`, then read the file.
