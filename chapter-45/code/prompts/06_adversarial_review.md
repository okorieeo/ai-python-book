Start a NEW session (or use a reviewer subagent) so the reviewer has not seen the author's reasoning.

You are reviewing a pull request written by someone else. You did not write it. Assume it contains at least three bugs.
Read `git diff main...HEAD`, @CLAUDE.md and @docs/features/send-message.md. For each acceptance criterion, find the test that proves it
and say whether the test would fail if the code were wrong (mutation thinking). Then list: security issues, concurrency issues,
places where the code does more than the spec asked, and anything you cannot verify. Do not fix anything; report.
