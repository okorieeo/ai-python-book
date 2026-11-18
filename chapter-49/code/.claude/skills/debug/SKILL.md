---
name: debug
description: Start a disciplined debugging session for a bug report or failing command.
argument-hint: <bug id or short description>
disable-model-invocation: true
---
We are debugging: $ARGUMENTS

Follow the loop. Do not skip a step and do not change code until step 3.

1. REPRODUCE. Find or write the smallest command that shows the failure. Run it and show me the output.
   If a bug report exists in docs/debug/, read it first. If you cannot reproduce, stop and tell me what you need.
2. DIAGNOSE. Use the bug-investigator subagent. Give me at most three ranked hypotheses and the experiment
   that separates them. Run the cheapest experiment. Update docs/debug/<id>.md with what you ruled in or out.
3. FIX. Make the smallest change that removes the ROOT cause. Say in one sentence why it is the root cause
   and not a symptom. Do not add broad try/except, sleeps, retries or silenced lint or type errors.
4. VERIFY. Run the reproduction again and show me it passes. Then run the test suite for the area.
5. PREVENT. Add a regression test that FAILS on the old code and passes on the new. Show me both runs
   (use git stash on the fix, or IMPL=buggy in the museum). Then run: git diff | python -m tools.fix_gate

Stop after step 2 and wait for my approval of the hypothesis. Stop again before committing.
If three attempts fail, STOP: write what was ruled out in docs/debug/<id>.md and tell me to start a fresh session.
