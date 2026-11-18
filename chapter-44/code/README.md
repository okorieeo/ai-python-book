# Chapter 44 code: Prompt Engineering for Building Software with Claude Code

    CLAUDE.md                        a short example for the AI Chat monorepo
    Makefile                         `make check`: the one command that says "healthy" (tests + config validation + prompt checks)
    docs/api-conventions.md          a small doc the prompts refer to with @docs/api-conventions.md
    .claude/settings.json            permissions + hook registration
    .claude/hooks/                   guard_bash, protect_files, small_commit_guard, post_edit_check, prompt_gate, stop_gate
    .claude/skills/                  feature-plan, step, endpoint-tests, self-review, commit-step   (slash commands)
    .claude/agents/                  code-reviewer, test-writer, security-auditor, migration-checker  (subagents)
    .mcp.json                        example MCP servers (stdio and http, secrets by ${VAR})
    prompts/weak_vs_strong/          nine weak/strong prompt pairs (backend, web, mobile)
    prompts/templates/               feature, bugfix, refactor prompt templates + PLAN.template.md
    tools/promptlint.py              checklist for the four parts of a coding prompt
    tools/planlint.py                checks a PLAN.md (sections, step count, files really exist)
    tools/validate_claude_config.py  validates settings, skills, agents and .mcp.json (needs PyYAML)
    tests/                           177 tests (unittest). Hooks are run as subprocesses, exactly as Claude Code runs them

Run everything (Python 3.10+, `pip install pyyaml`):

    make check

NOT run while writing the chapter: Claude Code itself was not available, so no skill, subagent, plan-mode session or MCP
connection was exercised, and the prompts were not run on a model. The hooks, the checkers and the validator are tested;
the skill and agent prompts and the MCP servers are validated for structure only.

Copy `.claude/` into your own project and adapt: the paths in CLAUDE.md and the prompts are for the AI Chat example, and
`make check` must be changed to run YOUR tests. Review `.claude/` changes like CI configuration: hooks are code that runs on
every contributor's machine.
