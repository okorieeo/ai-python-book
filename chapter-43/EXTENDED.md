# Chapter 43 — Getting Started with Claude and Claude Code: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Installing and Signing In › The recommended install (the native installer)

Run the command for your system. The native installer needs no Node.js and **updates itself in the background**:

**bash macOS, Linux, WSL**

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

**powershell Windows PowerShell**

```
irm https://claude.ai/install.ps1 | iex
```

**text Windows CMD (not PowerShell)**

```text
curl -fsSL https://claude.ai/install.cmd -o install.cmd && install.cmd && del install.cmd
```

Package managers work too, but they do **not** auto-update, so you upgrade them yourself:

**bash terminal**

```bash
brew install --cask claude-code            # macOS, Homebrew (use claude-code@latest for the faster channel)
winget install Anthropic.ClaudeCode        # Windows
```

An npm install (`npm install -g @anthropic-ai/claude-code`) is also supported and needs a recent Node.js (see the setup page for the minimum). Never use `sudo` with it; if you get permission errors, fix your npm prefix instead.

> **Read a script before you pipe it into your shell**
>
> `curl ... | bash` runs whatever the URL returns with your permissions. That is the vendor’s documented method, and the habit is worth examining anyway: download the script first (`curl -fsSL https://claude.ai/install.sh -o install.sh`), read it, then run it. In the same spirit, copy install commands only from the official documentation, never from a forum post or a search ad.


## Installing and Signing In › Verify, then sign in

**bash terminal**

```bash
claude --version          # prints the installed version
claude doctor             # checks the installation and configuration and reports problems
cd ~/projects/ai-chat-app
claude                    # starts a session; the first run opens a browser to sign in
```

The first launch asks you to log in with your Claude account (or Console account). The credentials are stored and reused, and `/login` switches accounts later. Two traps for people who also develop against the API:

> **If you have ANTHROPIC_API_KEY set, read the prompt carefully**
>
> Chapter 29 told you to keep your product’s API key in an environment variable. If that variable is set in the shell where you start `claude`, Claude Code may offer to use it, and **then your coding sessions are billed as API usage on that key**, not on your subscription. Choose deliberately, and prefer a **separate key** (or no key in that shell) so your product’s costs and your development costs stay apart. Never paste a key into a prompt.


## Installing and Signing In › Install problems

| **Symptom** | **Likely cause** | **Fix** |
|---|---|---|
| `claude: command not found` | The install folder is not on your `PATH` (or the terminal was open before the install) | Open a **new** terminal; follow the PATH instruction the installer printed; run `claude doctor` |
| **A** `<` **or "syntax error" when installing** | The install URL returned a web page instead of a script (a network, proxy or region block) | Check access to the URL in a browser; use another install method |
| **PowerShell command fails in CMD (or the reverse)** | The two shells use different install commands | Use `irm ... \| iex` only in PowerShell, `curl ... install.cmd` only in CMD |
| **Login page never completes** | Browser blocked the callback, or a VPN or proxy interferes | Copy the URL into the browser by hand; try without the VPN; run `/login` again |
| **"No active subscription" or a plan error** | The account is on the free plan | Use an account with a paid plan or Console credits (43.1) |
| **Works in one terminal, not in VS Code’s terminal** | Different `PATH` or shell | Start VS Code from a terminal, or set the shell integration |
| **Antivirus or a corporate policy blocks it** | Managed device policy | Ask your IT administrator; Claude Code can be deployed with managed settings |


## The Four Places You Will Use It

All of them run the same engine and share your settings and `CLAUDE.md`. They differ in comfort.

| **Surface** | **How to start** | **Strengths** | **Good for** |
|---|---|---|---|
| **Terminal (CLI)** | `claude` inside your project folder | Everything is available; fastest to learn the concepts; scripting with `claude -p "..."`; works over SSH | The default in this book. Use it side by side with your editor |
| **VS Code extension** | Install the Claude Code extension, then click the spark icon or open the Claude Code panel | Inline diffs you accept or reject, `@` mentions of files and selected lines, plan review in an editor tab, conversation history | People who live in VS Code. It also uses your project’s `CLAUDE.md` and settings |
| **JetBrains plugin** | Install the plugin for IntelliJ, PyCharm, WebStorm and others | Runs Claude Code in the IDE with diff viewing | Python or Java teams on JetBrains |
| **Desktop app** | Open Claude Code in the Claude desktop app | A graphical home for sessions, side-by-side work on several tasks, easy review | Those who prefer not to use a terminal; it needs a paid plan |
| **Web and mobile** | claude.ai/code, or the Claude mobile app | Start or check on work from anywhere, tasks run in a cloud environment | Long tasks you want to hand off |

A few differences are worth knowing. Some conveniences exist only in the terminal (the `!` prefix to run a shell command directly, tab completion), and some only in the IDE (a visual diff, selection context). You can use the **terminal and VS Code together** on the same project: start `claude` in the integrated terminal and the editor connects to it. For this book’s exercises, **use the terminal first**: the commands are explicit and you will see what is happening. Add VS Code when the concepts are familiar.

**bash terminal**

```bash
# open the project in VS Code and start Claude Code in its integrated terminal
cd ~/projects/ai-chat-app && code .
# then, in the integrated terminal:
claude
```


## Your First Session: Explore Before You Change › Everyday controls

| **To do this** | **Press or type** |
|---|---|
| **Interrupt Claude while it works** | **Esc** |
| **Send a multi-line message** | End a line with `\` then Enter, or use the multi-line shortcut shown by `/help` |
| **Start fresh for a new task** | `/clear` |
| **Continue the last conversation** | `claude -c` (or `/resume` inside Claude Code to pick one) |
| **Run a one-off question and exit (scripts)** | `claude -p "summarise the changes in the last 3 commits"` |
| **Start with a task already typed** | `claude "explain the folder structure"` |
| **See all commands** | `/help` |
| **Quit** | `/exit` or Ctrl+D |

> **A habit that pays for itself**
>
> End your exploration session by asking: "Write what you learned about this project’s structure and commands as a short summary I can review." You will use that summary in the next section to start a `CLAUDE.md`.


## Project Memory: CLAUDE.md › Where memory files live

| **Scope** | **Location** | **Shared with** | **Use it for** |
|---|---|---|---|
| **Project** | `./CLAUDE.md` or `./.claude/CLAUDE.md` | The team, through Git | Stack, commands, architecture, conventions |
| **Rules by topic** | `./.claude/rules/*.md` | The team | Instructions for one area; with a `paths:` list they load **only when Claude works on matching files** |
| **Personal, all projects** | `~/.claude/CLAUDE.md` | Only you | Your own preferences (editor habits, how you like explanations) |
| **Personal, this project** | `./CLAUDE.local.md` (add it to `.gitignore`) | Only you | Your local URLs, test accounts without secrets, sandbox notes |
| **Organization policy** | A managed file set by IT | Everyone in the company | Company-wide rules |

More specific, closer-to-the-code files are read in addition to the general ones, and a `CLAUDE.md` in a subfolder (for example `backend/CLAUDE.md`) is picked up when Claude works in that folder. Files can **import** others with `@path/to/file` (for example `@docs/git-workflow.md`), so you can keep one source of truth.

Claude Code can also keep its own **auto memory**: short notes it writes for itself about what it learned in your project (build quirks, your preferences). It is separate from the files above and you can read and edit it with `/memory`. Treat it as a convenience; the facts that matter belong in `CLAUDE.md`, where the team can review them.


## Project Memory: CLAUDE.md › Lint it

A bad `CLAUDE.md` fails silently. The checker in the book’s GitHub repository catches the common mistakes: an empty or oversized file, vague instructions, secrets, paths from one person’s machine, no test command, duplicate lines, and imports that point at files that do not exist. It also checks `.claude/settings.json` (43.4) and that your personal files are in `.gitignore`. Here is a deliberately bad project, checked (real output):

**bash terminal**

```bash
python tools/lint_claude_config.py /tmp/bad
CLAUDE.md                          WARN  vague                  'write clean code' is not checkable; say the exact command or rule instead
CLAUDE.md                          WARN  vague                  'follow best practices' is not checkable; say the exact command or rule instead
CLAUDE.md                          ERROR secret                 looks like a Stripe or Paystack style secret key: never put secrets in CLAUDE.md (it is committed)
CLAUDE.md                          WARN  personal-path          contains a path from one person's machine; use repository-relative paths
CLAUDE.md                          WARN  no-commands            no build, test or run commands in backticks: Claude cannot verify its own work
.claude/settings.json              ERROR allow-all-shell        'Bash(*)' lets Claude run any command without asking
.claude/settings.json              WARN  allow-interpreter      'Bash(python *)' approves arbitrary code through an interpreter
.claude/settings.json              WARN  never-matches          'Write(docs/**)' never matches: use Edit(path) or Read(path)
.claude/settings.json              WARN  wildcard-before-subcommand 'Bash(git * main)' has * before the rest of the command; put it after the subcommand
.claude/settings.json              WARN  env-not-denied         no Read deny rule for .env files: add "Read(./.env)" and "Read(./.env.*)"
.claude/settings.json              INFO  push-not-gated         git push is not in deny or ask: you may want a human to push
.claude/settings.json              ERROR bypass-in-project      bypassPermissions in a project file is ignored by Claude Code and unsafe to ask for
.gitignore                         ERROR personal-file-tracked  CLAUDE.local.md exists but is not in .gitignore

4 error(s), 8 warning(s), 1 note(s)
```

And the starter kit from this chapter comes out clean (the checker also runs as a test, so a later edit that breaks the kit fails the build). Add it to CI (Chapter 42) so every pull request that touches `CLAUDE.md` or `.claude/` is checked:

**python tools/lint_claude_config.py (excerpt)**

```python
def lint_claude_md(text: str, *, base_dir: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.splitlines()
    if not text.strip():
        return [Finding("error", "empty", "CLAUDE.md is empty: run /init or write the build, test and run commands")]
    if len(lines) > HARD_LIMIT_LINES:
        findings.append(Finding("error", "too-long", f"{len(lines)} lines; move topic rules into .claude/rules/ or skills"))
    elif len(lines) > MAX_RECOMMENDED_LINES:
        findings.append(Finding("warn", "long", f"{len(lines)} lines; the guidance is under {MAX_RECOMMENDED_LINES}"))

    prose = _strip_code_and_comments(text)
    lowered = prose.lower()
    for phrase in VAGUE:
        if phrase in lowered:
            findings.append(Finding("warn", "vague", f"'{phrase}' is not checkable; say the exact command or rule instead"))

    for pattern, what in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(Finding("error", "secret", f"looks like {what}: never put secrets in CLAUDE.md (it is committed)"))

    if PERSONAL_PATH.search(text):
        findings.append(Finding("warn", "personal-path", "contains a path from one person's machine; use repository-relative paths"))

    commands = re.findall(r"`([^`\n]+)`", text)
    tool = r"(python|python3|pip|npm|pnpm|yarn|npx|docker|make|pytest|ruff|git|celery|uv|poetry|node|expo|eas|tsc)"
    runnable = [c for c in commands if re.search(r"(^|&&\s*|;\s*|\|\|\s*)(cd\s+\S+\s*&&\s*)?" + tool + r"\b", c)]
    if not runnable:
        findings.append(Finding("warn", "no-commands", "no build, test or run commands in backticks: Claude cannot verify its own work"))
    elif not any(re.search(r"\b(test|pytest|check|lint)\b", c) for c in runnable):
        findings.append(Finding("warn", "no-test-command", "no test or lint command found: add how to run the tests"))

    seen: dict[str, int] = {}
    for n, line in enumerate(lines, 1):
        key = line.strip().lower()
        if len(key) > 25 and key.startswith(("-", "*")):
            if key in seen:
                findings.append(Finding("warn", "duplicate", f"line {n} repeats line {seen[key]}"))
            seen.setdefault(key, n)

    if base_dir is not None:
        for m in IMPORT.finditer(prose):
            target = m.group(1)
            if target.startswith(("~", "/")):
                continue
            if not (base_dir / target).exists():
                findings.append(Finding("error", "missing-import", f"@{target} does not exist relative to CLAUDE.md"))
    return findings
```


## Permissions: Deciding What Claude May Do › Permission modes

*(figure: see the printed book)*

| **Mode** | **What it does** | **When to use it** |
|---|---|---|
| **Manual (the** `default` **mode)** | Asks before edits and before most commands | Your **first weeks**, and anything sensitive. You see everything |
| `acceptEdits` | Edits and simple file operations in your project run without asking; other commands still ask | When you are reviewing diffs anyway and the prompts have become noise |
| `plan` | Claude may read and explore, and writes a **plan**; it does not edit until you approve | Any change that touches more than a couple of files (43.5) |
| `auto` | A separate safety check reviews each action and blocks ones that look risky, so most routine work proceeds without prompts | Long, well-understood tasks, once you trust the setup; it **reduces** risk and does not remove it, and it needs a plan and settings that support it |
| `dontAsk` | Anything not already allowed by a rule is denied; nothing is prompted | Locked-down automation and CI |
| `bypassPermissions` | No prompts and almost no checks | **Only inside a container or VM you can throw away**, never on your normal machine, never as root |

**Switching:** press **Shift+Tab** to cycle through the main modes during a session (the current mode is shown at the bottom of the screen); start in a mode with `claude --permission-mode plan`; set a default in settings. Newer versions may start in `auto` when it is available to you, so **look at the mode indicator before you give a big task**. A few protected locations (your `.git` folder, your Claude configuration) still ask in most modes.

> **Treat "fewer prompts" as a trade, not a feature**
>
> Every prompt you skip is a moment you are not looking. Use broader modes only after you have (1) a clean Git branch, (2) a test command Claude can run, (3) deny rules protecting secrets, and (4) the habit of reading the diff. Chapter 50 builds on this with sandboxes and hooks.


## Permissions: Deciding What Claude May Do › Permission rules in .claude/settings.json

Rules live in settings files. **Deny rules always win, then ask rules, then allow rules**, no matter which file they come from. The syntax is `Tool` or `Tool(pattern)`:

| **Rule** | **Meaning** |
|---|---|
| `Bash(npm run test *)` | Allow (or deny) shell commands that start with `npm run test `, the `*` matches the rest |
| `Bash(git status)` | Only that exact command |
| `Read(./.env)` | The file `.env` in the project; `Read(./.env.*)` covers `.env.local` and the rest |
| `Edit(docs/**)` | Edits to files under `docs` (`Edit` covers file-editing tools; there is no `Write(...)` rule) |
| `Read(//Users/amina/secrets/**)` | An **absolute** path needs `//` at the start; a single `/` means "relative to the settings file’s project" |

Scope decides who is affected, and the more specific, more local file wins when settings disagree:

| **File** | **Scope** | **Committed?** |
|---|---|---|
| `~/.claude/settings.json` | All your projects | No |
| `.claude/settings.json` | This project, for the team | **Yes** |
| `.claude/settings.local.json` | This project, only you (where "always allow" clicks are saved) | **No: add to** `.gitignore` |
| Managed settings | An organization | Set by IT |

Here is the project settings file from the starter kit. It pre-approves the read-only and test commands you run constantly, and **denies** the things that should always need a human or should never happen:

**json claude_starter/.claude/settings.json**

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": [
      "Bash(git status)",
      "Bash(git diff *)",
      "Bash(git log *)",
      "Bash(python -m pytest *)",
      "Bash(python -m unittest *)",
      "Bash(ruff check *)",
      "Bash(npm run test *)",
      "Bash(npm run typecheck)",
      "Bash(npx tsc --noEmit)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./secrets/**)",
      "Bash(git push *)",
      "Bash(git reset --hard *)",
      "Bash(rm -rf *)"
    ]
  }
}
```

Read each line as a decision. The `allow` entries are safe because they are narrow (`python -m pytest *`, not `python *`: an interpreter wildcard would approve arbitrary code). The `deny` entries protect secrets (`.env` files, a `secrets/` folder) and block `git push` (a human pushes after reviewing), a hard reset and a recursive delete.

> **Rules are guardrails, not a security boundary**
>
> A `Bash` rule matches the command text. Clever or accidental variations (a different flag order, a command run through `bash -c`, a script that runs other things) can behave differently from what you intended, and Claude Code warns about this in its own documentation. For real isolation use a **sandbox** or run in a container (Chapter 50). Also remember that a project’s allow rules take effect only after you **trust** the folder, which is why you should not trust folders you have not read.

You can manage rules interactively with `/permissions`, and the checker from Chapter 43 catches the dangerous patterns before you commit them: `Bash(*)`, interpreter wildcards, `rm` or `sudo` in `allow`, `Write(...)` rules that never match, single-slash absolute paths, missing `.env` protection and a `bypassPermissions` default in a shared file.


## Plan Mode: Think Before You Edit › What to look for in a plan

A plan is worth reading critically, like a pull request description:

- **Does it touch only what the task needs?** A plan to "add a health endpoint" that edits the payment code is wrong.
- **Does it follow your rules?** Services for logic, owner-scoped queries, `public_id` in URLs, tests included.
- **Does it say how it will verify?** Look for the test commands it will run.
- **Are there steps you do not understand?** Ask. Learning is the point of this book.
- **Is it too big?** Ask for the first step only.
**text a good plan-mode exchange (prompts for you to type)**

```text
/plan add a GET /api/v1/health/ endpoint that returns {"status": "ok"} with no authentication,
      plus a test. Follow the conventions in CLAUDE.md.

(read the plan)
the plan adds a view to config/urls.py; please put it in a new `health` app and keep it out of the
auth middleware. show the test first.

(approve, then review the diff and run the tests yourself)
```

Plan first for anything that edits more than a couple of files, changes a data model or migration, touches security, payments or privacy, or that you do not fully understand. Skip it for a one-line change you could do faster by hand. Chapter 44 turns this into a prompting method.


## Keeping Sessions Fast and Cheap: Context

Everything in the conversation (your messages, the files read, command output, Claude’s replies) takes up the **context window**. When it fills, Claude Code compacts it, detail is lost, and quality and speed drop. Your plan’s usage also depends on how much context is processed. You control this with a few habits:

- **One task per session.** Finish, commit, then `/clear`. Do not carry a payment-code conversation into a CSS fix.
- **Point, do not dump.**  `@backend/payments/services.py` beats pasting the file, and "look at the failing test" beats pasting 500 lines of log. When you must show output, show the **relevant** part.
- **Ask for narrow reads.** "Search for where `Payment.status` is set" instead of "read the payments app".
- **Check with** `/context` when a session gets sluggish; compact or clear.
- **Put stable facts in** `CLAUDE.md`**,** not in your first message every day.
- **Use the right model and effort** for the job; do not spend your most capable model on renaming a variable.
- **Keep commands quiet.** A test run that prints 10,000 lines floods the context; use `-q` and show failures only (the starter `CLAUDE.md` does this).

## Git Checkpoints: Your Undo Button › Safety net 1: Claude Code’s checkpoints and /rewind

Claude Code automatically records a checkpoint before each of your prompts and tracks the **file edits it makes with its own editing tools**. Press **Esc twice** (or type `/rewind`) to open a menu: you can restore the **code**, the **conversation**, or both, to an earlier point. Checkpoints persist across sessions, so you can rewind after resuming.

They have limits you must remember:

- **Shell commands are not tracked.** If Claude runs `rm`, `mv`, `cp`, a migration, or a script that rewrites files, `/rewind` does not undo it.
- **Edits you made yourself, or other programs made, are not tracked** (outside the current session they may not be captured).
- **They are not version control.** They are a local session aid, not a history you share or recover from a deleted folder.