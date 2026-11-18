# How we work with Claude Code (team agreement)

1. **You own what you commit.** Whoever opens the pull request is responsible for every line, whether a person or Claude wrote it.
2. **Secrets stay out.** No real secrets in the repo, in prompts, in pasted logs or in screenshots. `.env*` is off limits to the agent.
3. **Production is human-only.** No production credentials or data in an agent session. Paste redacted output instead.
4. **Small steps.** One task, one prompt, one commit. Read the diff before every commit.
5. **Verify, then trust.** Run it. New dependencies are checked in the registry. Docs and API names are confirmed against the real documentation.
6. **Tests come with changes.** Bug fixes carry a regression test that failed first. Features carry tests named for their acceptance criteria.
7. **Higher risk, more eyes.** Authentication, payments, permissions, migrations, deletes and anything public-facing need a second human reviewer.
8. **Shared settings are code.** `.claude/settings.json`, hooks, agents, skills and CLAUDE.md change through pull requests. Personal tweaks go in `.claude/settings.local.json` (not committed).
9. **Disclose in the PR.** Say whether Claude wrote most of it. It is information for the reviewer, not a confession.
10. **Code by hand when it is wiser.** See the list in the chapter: security-critical code, things you cannot verify, tiny edits, and learning.
