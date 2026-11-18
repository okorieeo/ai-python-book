# Chapter 43 code: Getting Started with Claude and Claude Code

    claude_starter/CLAUDE.md                 project memory for the AI Chat SaaS (edit commands to match yours)
    claude_starter/.claude/settings.json     narrow allow rules, deny rules for secrets, push and destructive commands
    claude_starter/.claude/rules/*.md        path-scoped rules (payments, frontend)
    claude_starter/gitignore.snippet         lines to append to .gitignore
    tools/lint_claude_config.py              checks CLAUDE.md, settings and .gitignore for common mistakes
    tools/test_lint_claude_config.py         33 tests:  python -m unittest tools.test_lint_claude_config -v

Run the checker:  python tools/lint_claude_config.py <project_dir>      (exit status 1 on errors)

Nothing here was run against a live Claude Code session; see the verification note in the chapter.
