---
name: self-review
description: Review the current uncommitted changes for bugs, missing tests, security problems and scope creep before I commit.
allowed-tools: Bash(git diff *), Bash(git status)
---
Review my current changes for correctness, security and scope.

Changed files: !`git diff --stat`

Use the code-reviewer subagent on the full diff so the review happens in a fresh context, not in the one that wrote the code. Report only: bugs, missing tests, security problems (authorization, secrets, injection, unsafe parsing), and anything outside the stated scope. Rank them by severity. Do not edit any file. If you find nothing, list what you checked.
