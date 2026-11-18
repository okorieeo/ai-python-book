---
name: commit-step
description: Commit the step just finished with a conventional message, if it is small and has a single purpose.
disable-model-invocation: true
allowed-tools: Bash(git add *), Bash(git commit *), Bash(git diff *), Bash(git status)
---
Commit the work of the step just finished.

1. Run `git status` and `git diff --stat`. If the changes mix concerns (this step plus an unrelated cleanup), commit only the files for this step and tell me about the rest.
2. Stage files by name. Never run `git add -A`.
3. Commit with a conventional message: `type(scope): summary`, at most 72 characters, no full stop. If a body helps, it says why, not what.
4. Never use --no-verify. If a hook blocks the commit, fix the reason and try again.
5. Show `git log -1 --stat`.
