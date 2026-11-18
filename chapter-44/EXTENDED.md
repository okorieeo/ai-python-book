# Chapter 44 — Prompt Engineering for Building Software with Claude Code: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Prompting an Agent Is Not Chatting › The tools, from lightest to heaviest

Claude Code gives you several ways to shape its behaviour, and the most common mistake is reaching for a heavy one when a prompt would do, or relying on a light one for something that must always happen. This chapter ends with all of them; here is the map.

*(figure: see the printed book)*

*Figure 44.1: Advice, playbooks, specialists, rules and reach. The right tool depends on whether it must always happen, how often you repeat it, and whether it needs a clean head.*

> **Two kinds of “hook”, two chapters**
>
> Chapter 42 covered **Git pre-commit hooks**: scripts Git runs before a commit, which any tool and any person triggers. **Claude Code hooks**, covered in 44.10, are different: scripts Claude Code runs at points in *its own* work, such as before it runs a shell command or edits a file. They complement each other. A Claude Code hook can stop a bad action before it happens; a Git hook is the last line of defence for anything that gets as far as a commit. This chapter’s `small_commit_guard` even refuses to let Claude bypass the Git hooks with `--no-verify`.


## The Anatomy of a Coding Prompt › A checklist you can run

The bundle’s `promptlint.py` turns the four parts into an automatic checklist. It looks for an action-led opening, a path or URL, constraint language, and acceptance cues, and warns about vague words and about prompts that ask for too much at once. Here it is on the first weak prompt and its strong counterpart:

**python tools/promptlint.py prompts/weak_vs_strong/backend-01-weak.md prompts/weak_vs_strong/backend-01-strong.md**

```python
FAIL  1/4  goal:yes context:NO  constraints:NO  acceptance:NO   backend-01-weak.md
      error too-short: 6 words is too little to act on without guessing.
      error no-context: Point at the files, the existing pattern to copy, or the doc to read.
      error no-constraints: Say what must not change, what to reuse, and what is out of scope.
      error no-acceptance: Say how success is checked: a test to write or run, a command that must pass.
PASS  4/4  goal:yes context:yes constraints:yes acceptance:yes  backend-01-strong.md
```

**tools/promptlint.py (the checks)**

```
ACTION_WORDS = ("add|build|create|fix|implement|refactor|replace|remove|migrate|write|update|extend|rename|split|move|convert|reduce|"
                "investigate|make|show|wire|port|delete|introduce|support|handle|display|connect")
ACTION = re.compile(rf"^(?:{ACTION_WORDS})\b", re.IGNORECASE)
PATH = re.compile(r"(?:@?[\w.\-]+/)+[\w.\-]+|\b[\w\-]+\.(?:py|ts|tsx|js|jsx|mjs|json|md|ya?ml|toml|sql|html|css|kt|swift|sh|ini|cfg)\b|https?://\S+")
CONSTRAINT = re.compile(r"\b(?:do not|don't|dont|must not|must|never|only|without|avoid|keep|follow|reuse|use the existing|no new|"
                        r"out of scope|not touch|leave\b.*\balone|stay within|same as|match the)\b", re.IGNORECASE)
ACCEPT_LABEL = re.compile(r"^\s*(?:done when|acceptance|verify|verification|definition of done|success)\b", re.IGNORECASE | re.MULTILINE)
ACCEPT_CUES = [re.compile(p, re.IGNORECASE) for p in (
    r"\btests?\b", r"\bpytest\b", r"\bjest\b", r"\bplaywright\b", r"\bmaestro\b", r"\bmake check\b", r"\bnpm (?:run )?\w+", r"\bnpx \w+",
    r"\blint\b", r"\btsc\b", r"\btypecheck\b", r"\b[1-5]\d{2}\b(?! ?(?:ms|px|words|chars|characters|lines))", r"\bexpected\b", r"\bpasses|passing\b",
    r"\bassert", r"\bscreenshot\b", r"\bshould (?:return|show|display|fail|pass|be)\b", r"\bresponds? with\b", r"\breturns?\b")]
VAGUE = re.compile(r"\b(?:better|nicer|cleaner|improve[ds]?|properly|good|nice|modern|robust|best practices?|optimi[sz]e[ds]?|faster|"
                   r"clean(?:ed)? up|make it work|polish|production[- ]ready|scalable|elegant|simple)\b", re.IGNORECASE)
# A list item counts as a TASK only if it starts with an action verb. Bullets that state constraints or checks
# ("Do not change the model", "Only the owner may rename") are not tasks, however many there are.
TASK_ITEM = re.compile(rf"^\s*(?:\d+[.)]|[-*])\s+(?:{ACTION_WORDS})\b", re.MULTILINE | re.IGNORECASE)
```

> **What this checker is, and is not**
>
> It is keyword matching. It cannot understand your prompt. A prompt can pass and still be poor (all four parts present, all four wrong), and a good prompt phrased unusually can fail. It exists to make a checklist something you do not have to remember, like a spell-checker: useful, and no substitute for reading. Its first draft also taught a lesson: it counted ordinary constraint bullets (“Do not change module 3”) as separate tasks and warned that the prompt was too big. The fix was to count only list items that begin with an action verb, and a test now pins that behaviour. Heuristics need tests, too.


## Plan First, Then Build › Reviewing a plan: six questions

1. **Is every file real?** A plan that lists a file that does not exist was built on a guess. This is mechanical, so check it mechanically (below).
2. **Is each step small enough to commit by itself?** If one step is “implement the feature”, it is not a step.
3. **Does each step say how we will know it is done?** A step with no check cannot be verified.
4. **Is anything in the plan that you did not ask for?** Scope creep is cheapest to remove at this stage.
5. **What does it say about failure?** Plans describe the happy path unless you ask about the unhappy ones: invalid input, another user’s data, the provider being down.
6. **What is out of scope?** If that section is empty, nobody has decided where this ends.
**tools/planlint.py (the checks)**

```
def lint_plan(text: str, repo_root: str | Path | None = None) -> PlanResult:
    sections = split_sections(text)
    result = PlanResult(sections)
    add = lambda i, sev, msg: result.findings.append(Finding(i, sev, msg))
    for key in SECTIONS:
        if key not in sections or not sections[key].strip():
            add(f"missing-{key}", "error", f"The plan has no '{key.replace('_', ' ')}' section (or it is empty).")

    steps = [s for s in re.findall(r"^\s*\d+[.)]\s+(.+)$", sections.get("steps", ""), re.MULTILINE)]
    if "steps" in sections:
        if len(steps) < 2:
            add("not-a-plan", "error", "Fewer than two numbered steps: this is a single action, not a plan.")
        if len(steps) > MAX_STEPS:
            add("too-many-steps", "error", f"{len(steps)} steps is too big to review. Split the work into separate plans.")
        for n, step in enumerate(steps, start=1):
            if not re.search(r"done when|verify|verified by|check:|test", step, re.IGNORECASE):
                add("step-unverifiable", "warn", f"Step {n} has no way to tell it is finished: {step[:60]!r}")

    files_body = sections.get("files", "")
    paths = []
    for line in files_body.splitlines():
        for m in re.finditer(r"`([^`\s]+\.[A-Za-z0-9]+|[^`\s]+/[^`\s]*)`", line):
            paths.append((m.group(1), bool(re.search(r"\((?:new|create|will be created)\)|\bnew file\b", line, re.IGNORECASE))))
    if "files" in sections and not paths:
        add("files-unlisted", "error", "The files section names no files in backticks, so there is nothing to check or review.")
    if repo_root is not None:
        root = Path(repo_root)
        for path, is_new in paths:
            if not is_new and not (root / path).exists():
                add("missing-file", "error", f"`{path}` does not exist and is not marked (new): the plan may be built on a guess.")

    open_questions = [l for l in sections.get("risks", "").splitlines() if l.strip().endswith("?")]
    if open_questions:
        add("open-questions", "warn", f"{len(open_questions)} open question(s): answer them before building.")
    return result
```

`planlint.py` runs the mechanical parts of that review: it looks for the six sections, counts the steps (fewer than two is not a plan, more than twelve is too big to review), warns about steps with no way to tell they are finished, and **checks that every file named in the plan exists in your repository unless the plan marks it** `(new)`. The skill tells Claude to run it on its own plan and fix every error before showing you, so you review a plan that has already passed the mechanical checks and can spend your attention on the judgement.

> **Two bugs the plan checker had, both found by testing it on its own template**
>
> The heading pattern for the “risks” section did not match **“Risks and open questions”**, the exact heading in the template shipped beside it, so every plan written from the template was reported as missing a section. The fix and a regression test cover five heading variants. The second: the command-line check defaults to the current folder, so a correct plan was reported as referring to missing files when run from the wrong place. That was the checker being right and my test being wrong, which is a useful reminder that a failing check is a question, not always a verdict.


## Small Steps: One Feature, One Prompt, One Commit › Making small commits the default: a hook

Telling Claude “keep commits small” in `CLAUDE.md` is advice. Advice drifts. A hook is a rule. `small_commit_guard.py` runs before every Bash command, ignores everything except `git commit`, and refuses commits that break the house rules: a conventional message, no `--no-verify`, and a bounded diff.

**.claude/hooks/small_commit_guard.py (the rules)**

```
def evaluate(command: str, cwd: str, run_git=None, max_files: int = 15, max_lines: int = 600) -> tuple[str | None, str]:
    args = git_commit_args(command)
    if args is None:
        return None, ""
    info = parse_commit(args)
    if info["no_verify"]:
        return "deny", "do not bypass hooks with --no-verify; fix what the hooks reported"
    if not info["messages"] and not info["other_message"] and not info["amend"]:
        return "deny", 'write the message with -m "type(scope): summary" so it can be checked; an editor cannot open here'
    if info["messages"]:
        subject = info["messages"][0].strip().splitlines()[0] if info["messages"][0].strip() else ""
        if not SUBJECT.match(subject):
            return "deny", f'message must look like "feat(chat): rename a conversation" (type, optional scope, colon, summary); got {subject!r}'
        if len(subject) > 72 or subject.endswith("."):
            return "deny", "keep the subject to 72 characters, without a trailing full stop"
    if run_git is None:
        def run_git(argv):
            try:
                r = subprocess.run(["git", *argv], cwd=cwd, capture_output=True, text=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                return None
            return r.stdout if r.returncode == 0 else None
    files, lines = numstat(run_git, info["all"])
    if files > max_files or lines > max_lines:
        return "deny", (f"this commit changes {files} files and {lines} lines (limits: {max_files} files, {max_lines} lines). "
                        "Split it into smaller commits, one step each, and commit the first now.")
    if info["amend"]:
        return "ask", "amending rewrites the previous commit; confirm it has not been pushed"
    return None, ""
```

When Claude tries to commit twenty files at once, this is exactly what it is shown, and it can act on it:

**What Claude sees when the hook denies a commit of 20 files (real output)**

```
this commit changes 21 files and 21 lines (limits: 15 files, 600 lines). Split it into smaller commits, one step each, and commit the first now.
```

**What Claude sees for a message that is not conventional (real output)**

```
message must look like "feat(chat): rename a conversation" (type, optional scope, colon, summary); got 'wip'
```

Notice that the reason is written to be **acted on**: it states the limits, says what is wrong, and tells Claude the next move (split it, commit the first part now). A hook that says only “blocked” produces a confused agent; a hook that explains produces a corrected one. The limits (15 files, 600 lines) are this bundle’s choice, adjustable with environment variables; pick numbers that match the size of change your team can really review.

The guard was tested against real Git repositories, not only against fake diff data: a small staged change passes, twenty staged files are denied, unstaged files do not count, and `git commit -am` is measured against the whole working tree rather than just the index. That last case is easy to miss: with `-a`, the staged set at hook time is not what Git will commit.


## Weak Prompts and Strong Prompts › Mobile

**prompts/weak_vs_strong/mobile-01-strong.md**

```
Add Settings > Account > Delete account to the Expo app. The App Store requires deletion to be possible inside the app.

Context: the Settings screen is @mobile/app/(tabs)/settings.tsx. The endpoint DELETE /api/v1/account/ already exists. Look at how @mobile/src/privacy/AiConsentGate.tsx handles SecureStore.

Constraints:
- Two-step confirmation: the person must type DELETE before the button is enabled.
- Do not clear anything locally until the server confirms the deletion. On success clear SecureStore and go to /welcome; on failure show a retry message.
- JavaScript only, no new native modules, so this can ship as an over-the-air update.
- Do not touch the version gate or the consent gate.

Done when:
- jest-expo tests cover the confirmation flow, success, and failure.
- A Maestro flow in .maestro/delete-account.yaml covers the happy path.
- `npm test` and `npx expo-doctor` pass.
```

This one carries a constraint specific to phones: *JavaScript only, no new native modules, so this can ship as an over-the-air update*. Chapter 26 explained that a native change needs a new store build and review while a JavaScript change can ship in minutes; stating which you want changes what Claude is allowed to do. The last pair of the nine shows the other side of that rule:

**prompts/weak_vs_strong/mobile-03-strong.md**

```
Add step 1 of 3 of push notifications: ask for permission and register the device token. Sending notifications comes in a later step, so do not build it.

Context: read https://docs.expo.dev/versions/latest/sdk/notifications/ and @mobile/app.config.ts. The token is registered with POST /api/v1/devices/ (see @backend/devices/views.py).

Constraints:
- Ask for permission only after the person's first successful reply, never at launch.
- If permission is denied, remember that in SecureStore and never ask again.
- expo-notifications is a native change: do not run eas build, and do not bump the version yourself. List exactly what will need a new store build.
- Do not touch the version gate or the consent gate.

Done when jest tests with the module mocked cover granted, denied, and already-asked, and `npm test` passes. End your reply with the list of changes that require a new build.
```

“Add push notifications” is not one task, it is at least three. The strong version says **step 1 of 3** and explicitly defers the rest. And because `expo-notifications` is a native change, it tells Claude not to run a build or bump a version, and to end with the list of what will need a new build. That list is the thing you most need and the thing an unprompted agent will not volunteer.

> **A caution about this comparison**
>
> I have not run these eighteen prompts through a model for this chapter, so I cannot show you the difference in output. What the bundle verifies is the *structure*: the checker reports exactly which parts each weak prompt lacks, and the tests assert that all nine weak prompts fail and all nine strong ones pass. That the strong ones produce better results is Anthropic’s published advice and common experience, and it is the first thing worth testing yourself: run both versions of one pair on your own project and compare the diffs.


## Reusable Prompts: Skills and Slash Commands › The step skill and the commit skill

**.claude/skills/step/SKILL.md**

```
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
```

**.claude/skills/commit-step/SKILL.md**

```
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
```

`/step 2` is the whole prompt for a step, because everything else lives in the plan and in `CLAUDE.md`. Its rules encode the habits from this chapter: test first, run `make check`, **stop and report** instead of drifting on, and propose a commit message instead of committing. `/commit-step` is the separate, manual-only action that does the committing, with `allowed-tools` limited to the four Git commands it needs and an instruction never to run `git add -A`.


## Reusable Prompts: Skills and Slash Commands › A skill for a recurring chore: endpoint tests

**.claude/skills/endpoint-tests/SKILL.md**

```
---
name: endpoint-tests
description: Write the standard test suite for a Django REST endpoint (authentication, ownership, validation boundaries, throttling and query count).
argument-hint: "<METHOD /api/v1/path/>"
---
Write tests for this endpoint: $ARGUMENTS

Read the view and serializer, and copy the house style from @backend/tests_django/test_authorization.py and @backend/tests_django/test_query_count.py.

Cover, one test each unless noted:
- an anonymous request gets 401;
- the owner succeeds (assert the response body AND the change in the database);
- another user gets the SAME 404 as a missing object, never 403;
- every validation rule at its boundary (use parametrize);
- a throttled request gets 429, if a throttle is configured;
- a list endpoint stays within a fixed query budget.

Rules: do not edit the view to make a test pass. If a test reveals a bug, stop and report it. Watch each new test fail once (temporarily break the behaviour) before you trust it.
Run `pytest` on the new file and show me the output.
```

This is the Chapter 39 test checklist turned into one command: `/endpoint-tests PATCH /api/v1/conversations/{id}/`. It names the files to copy the house style from, lists the cases, and carries the two rules that make generated tests trustworthy: *do not edit the view to make a test pass* and *watch each test fail once*.

**.claude/skills/self-review/SKILL.md**

```
---
name: self-review
description: Review the current uncommitted changes for bugs, missing tests, security problems and scope creep before I commit.
allowed-tools: Bash(git diff *), Bash(git status)
---
Review my current changes for correctness, security and scope.

Changed files: !`git diff --stat`

Use the code-reviewer subagent on the full diff so the review happens in a fresh context, not in the one that wrote the code. Report only: bugs, missing tests, security problems (authorization, secrets, injection, unsafe parsing), and anything outside the stated scope. Rank them by severity. Do not edit any file. If you find nothing, list what you checked.
```

`/self-review` is the reviewer from 44.9 made one keystroke away. Its `allowed-tools` lets it run only `git diff` and `git status`; it begins with the real list of changed files; and it tells Claude to hand the diff to the `code-reviewer` subagent so that the review happens in a fresh context. Note the final instructions: report only what matters, rank it, **do not edit**, and say what was checked if nothing was found.


## Reusable Prompts: Skills and Slash Commands › Rules for good skills

- **Write the description as a trigger.** It is what Claude matches your request against. “Helps with tests” will fire constantly and unhelpfully; “Write the standard test suite for a Django REST endpoint” fires when it should.
- **Anything with a side effect is manual-only.** Committing, deploying, migrating, deleting. A skill that can commit and can also be triggered automatically is a skill that will commit at a time you did not choose. The validator enforces this: it reads each skill’s body for such actions and errors if `disable-model-invocation` is not `true`.
- **Keep the body short and procedural.** A skill is loaded when used, so it costs context only then, but a long, vague one still dilutes the instruction.
- **Put a stop condition in.** “Then STOP and report” is what separates a step from a runaway.
- **Commit them.**  `.claude/skills/` in the repository means everyone on the team gets the same playbooks, and they are reviewed like code.
> **The bug the validator found in my own skill**
>
> While writing this chapter I wrote the `endpoint-tests` skill with a description containing a colon: “Write the standard test suite for a Django REST endpoint: authentication, ownership...”. In YAML, an unquoted colon inside a value is a syntax error, so the frontmatter did not parse. **Nothing would have told me.** The skill would simply never have loaded, and I would have wondered why `/endpoint-tests` did not appear. The validator in the repository reported it at once:

**python tools/validate_claude_config.py (before the fix)**

```python
ERROR .claude/skills/endpoint-tests/SKILL.md: frontmatter is not valid YAML: mapping values are not allowed here
1 error(s), 0 warning(s)
```

The fix was to reword the description without the colon (quoting it would also work). The lesson is general: **configuration that fails silently needs a checker**, and every kind of file in this section, skills, subagents, hooks and MCP servers, has at least one way to be wrong that produces no error message at all. 44.11 collects them.


## Subagents: Specialists With Clean Heads › When a subagent is the right tool

| **Use a subagent for...** | **Because...** |
|---|---|
| Reviewing your own diff | A fresh context has none of the author’s assumptions (the writer/reviewer pattern of 44.7) |
| Investigating: “where is X handled, and how?” | Reading twenty files stays out of your main context; you get the answer, not the journey |
| A read-only audit (security, migrations) | It can be given **no tools that change anything**, so it cannot make things worse |
| A repetitive specialist job (writing tests in the house style) | A focused prompt, defined once, used every time |
| Cheap, quick checks | It can run on a smaller, cheaper model (`model: haiku`) |

Do not use one for small tasks: starting a subagent has overhead, and for a one-line change it is slower than just asking.


## Subagents: Specialists With Clean Heads › Choosing tools and models

| **Agent** | **tools** | **model** | **Why** |
|---|---|---|---|
| `code-reviewer` | Read, Grep, Glob, Bash | inherit | Needs `git diff`; told in its prompt to read only |
| `security-auditor` | Read, Grep, Glob | inherit | Pure reading; nothing that can change anything |
| `test-writer` | Read, Grep, Glob, Edit, Write, Bash | sonnet | Must write files and run tests |
| `migration-checker` | Read, Grep, Glob, Bash | haiku | A short, mechanical comparison; a cheap model is enough |

Two cautions. **An omitted** `tools` **line means the subagent inherits every tool**, including ones you may not want it to have; the validator warns about it. And **a reviewer must not be able to edit**: the validator errors if an agent whose name contains *review*, *audit* or *check* lists `Edit`, `Write`, `MultiEdit` or `NotebookEdit`. A reviewer that can “just fix it” stops being a reviewer.

> **Do not assume your hooks cover every subagent call**
>
> Whether a subagent’s tool calls pass through your PreToolUse hooks in every circumstance is something to confirm in the documentation for the version you run. The dependable control is the one that does not depend on it: give each subagent the **narrowest** `tools` **list** that lets it do its job, and treat that list as the real permission.


## Hooks: Rules That Cannot Be Talked Out Of › The six hooks

| **Hook** | **Event / matcher** | **What it does** | **Decision** |
|---|---|---|---|
| `prompt_gate` | UserPromptSubmit | Stops a prompt containing what looks like a live secret | exit 2 (shown to you) |
| `guard_bash` | PreToolUse / Bash | Denies destructive commands; asks about release and push-to-main | deny / ask |
| `small_commit_guard` | PreToolUse / Bash | Conventional message, bounded size, no `--no-verify` | deny / ask |
| `protect_files` | PreToolUse / Edit\|Write\|MultiEdit | Protects secrets, keys, lockfiles, applied migrations, `.git`, and the guardrails themselves | deny / ask |
| `post_edit_check` | PostToolUse / Edit\|Write\|MultiEdit | Formats and lints the edited file; reminds about migrations after `models.py` | block with the lint output |
| `stop_gate` | Stop | Claude cannot finish until `make check` passes (with a ceiling) | block with the output |

**.claude/settings.json (the hooks section)**

```
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/guard_bash.py\"", "timeout": 10 },
          { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/small_commit_guard.py\"", "timeout": 30 }
        ]
      },
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/protect_files.py\"", "timeout": 10 }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/post_edit_check.py\"", "timeout": 120 }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/prompt_gate.py\"", "timeout": 10 }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/stop_gate.py\"", "timeout": 900 }
        ]
      }
    ]
  }
}
```


## Hooks: Rules That Cannot Be Talked Out Of › Guarding the shell

`guard_bash` is the one that earns its keep daily. A shell command is a string, and “is this dangerous?” is not a simple question about a string: `rm -rf node_modules` is routine and `rm -rf /` is a catastrophe, `git push --force-with-lease` is fine and `git push origin +main` is the same danger as `--force` hidden in a refspec. So it **tokenizes** the command properly, splits it into its pieces (separated by `&&`, `;` and `|`), looks inside `bash -c "..."` and `$(...)`, and applies rules per piece.

**.claude/hooks/guard_bash.py (tokenizing)**

```
def tokenize(command: str) -> list[list[str]]:
    """Split a command line into segments of tokens, keeping the operator that came before each segment."""
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    segments: list[list[str]] = [[]]
    for tok in lex:
        if tok in OPERATORS:
            segments.append([tok])
            segments.append([])
        else:
            segments[-1].append(tok)
    return [s for s in segments if s]
```

| **What Claude tried** | **What the hook answered (real output)** |
|---|---|
| `rm -rf /` | **deny:** recursive delete of /: only build and cache folders may be deleted this way |
| `git push --force origin main` | **deny:** force-pushing rewrites shared history; use --force-with-lease after asking a human |
| `git push origin main` | **ask:** pushing straight to main: open a pull request instead |
| `eas build --platform all --profile production` | **ask:** a production build is a release step |
| `curl -s https://get.example.com/install.sh \| sh` | **deny:** never pipe a download straight into an interpreter |

The line between **deny** and **ask** is a decision worth making deliberately. *Deny* is for things you never want an agent to do (delete the filesystem, force-push, pipe a download into a shell). *Ask* is for things that are sometimes right but are always yours to decide: pushing to `main`, submitting to a store, building for production (Chapter 26’s “releasing is a human decision”), `git reset --hard`. The hook turns your release policy into something Claude cannot skip.


## Hooks: Rules That Cannot Be Talked Out Of › Protecting files

**.claude/hooks/protect_files.py (the rules)**

```
def evaluate(file_path: str, project_dir: str, exists=os.path.exists) -> tuple[str | None, str]:
    if not file_path:
        return None, ""
    raw = file_path.replace("\\", "/")
    full = os.path.normpath(raw if os.path.isabs(raw) else os.path.join(project_dir, raw)).replace("\\", "/")
    root = os.path.normpath(project_dir).replace("\\", "/")
    if full != root and not full.startswith(root.rstrip("/") + "/"):
        return "ask", "this file is outside the project folder"
    rel = full[len(root):].lstrip("/")
    parts = rel.split("/")
    name = parts[-1].lower()

    if ".git" in parts[:-1] or name == ".git":
        return "deny", "never edit the .git folder; use git commands"
    if name == ".env" or (name.startswith(".env.") and name not in ENV_OK):
        return "deny", "secrets files are edited by a human; put placeholders in .env.example instead"
    if os.path.splitext(name)[1] in KEY_SUFFIXES or name.startswith(("id_rsa", "id_ed25519")):
        return "deny", "key and certificate files must never be touched by an agent"
    if re.search(r"(service[-_]?account|credentials)[\w.-]*\.json$", name):
        return "deny", "credential files must never be touched by an agent"
    if "secrets" in parts[:-1]:
        return "deny", "the secrets folder is off limits"
    if name in LOCKFILES:
        return "deny", "do not hand-edit a lockfile; change the manifest and run the package manager"
    if MIGRATION.search(rel) and exists(full):
        return "deny", "an existing migration is history: create a new migration instead of editing it"
    if rel.startswith(".claude/hooks/") or re.fullmatch(r"\.claude/settings(\.local)?\.json", rel):
        return "ask", "this changes the guardrails themselves"
    return None, ""
```

| **What Claude tried** | **What the hook answered (real output)** |
|---|---|
| Edit `.env` | **deny:** secrets files are edited by a human; put placeholders in .env.example instead |
| Edit an existing migration | **deny:** an existing migration is history: create a new migration instead of editing it |
| Write `web/package-lock.json` | **deny:** do not hand-edit a lockfile; change the manifest and run the package manager |

Two details come from the tests. **Path tricks do not work:**  `backend/../.env`, a Windows-style `backend\.env` and an upper-case `.ENV` are all treated as `.env`, and a *sibling* folder whose name merely starts with the project’s name counts as outside the project. And **a new migration is welcome while an existing one is history**: the hook checks whether the file already exists, so Claude can create `0002_add_title.py` but not edit `0001_initial.py`. The hook also protects itself: edits to `.claude/hooks/` and `settings.json` ask for a human, because changing the guardrails is a decision.


## Hooks: Rules That Cannot Be Talked Out Of › Testing a hook the way it is used

A hook is only useful if it works when Claude Code runs it, and that is a different thing from its logic being right. So the tests run each script as a **subprocess with JSON on standard input**, exactly as Claude Code does, and read the exit code and output back. One more test goes a step further and reads `settings.json` itself, picks the hooks whose matcher matches the tool, and runs the real command strings through a shell, with the project path in `CLAUDE_PROJECT_DIR`:

**tests/test_settings_wiring.py (excerpt)**

```
def hooks_for(event, tool_name=None):
    commands = []
    for entry in SETTINGS["hooks"].get(event, []):
        matcher = entry.get("matcher")
        if matcher is None or tool_name is None or re.fullmatch(matcher, tool_name):
            commands += [h["command"] for h in entry["hooks"]]
    return commands

def run(command, payload, **env):
    full = {**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT), **env}
    p = subprocess.run(command, shell=True, input=json.dumps(payload), capture_output=True, text=True, cwd=ROOT, env=full, timeout=60)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None), p.stderr
```

That test exists because the failure mode it guards is invisible: a quoting mistake in the command string, a wrong script path, or a matcher that does not match (`Edit | Write` with spaces) produces a hook that **never runs and says nothing**. One test runs everything with a project path containing a space, which breaks naive unquoted commands.

> **Hooks are code that runs on your machine, and on your teammates’**
>
> A hook in a committed `.claude/settings.json` executes automatically for everyone who opens the project. That is the point, and it is also a security surface: **a pull request that edits** `.claude/settings.json` **or** `.claude/hooks/` **can run arbitrary commands on the machine of whoever reviews or checks it out.** Treat those files like CI configuration. Require review from specific people (a CODEOWNERS entry for `.claude/`), read hook changes line by line, and never copy a hook from the internet without reading it. This is also why `protect_files` asks for a human when Claude itself tries to edit them.

> **Hooks reduce accidents; they are not a sandbox**
>
> `guard_bash` matches patterns. A sufficiently creative command (a one-line Python script that deletes a directory, a command built from pieces at runtime) can get past any pattern list, and the tests cannot prove otherwise. Its job is to stop the **ordinary, careless, plausible** mistakes, which is nearly all of the real ones. For hard isolation, run the agent in a container or a disposable environment, use a development database that cannot hurt you, and keep production credentials off the machine entirely.


## MCP Servers: Giving Claude Reach › Four ways an MCP file fails silently

Like skills and hooks, MCP configuration can be wrong without a visible error. The validator in the repository checks each, and each has a test:

| **Mistake** | **What happens** | **Validator** |
|---|---|---|
| An HTTP server given a `url` but no `"type": "http"` | The server is **dropped without a message** | error: would drop this server |
| A stdio server with no `command`, or `args` as a string instead of a list | The server never starts | error |
| A real token pasted into `headers` or `env` | A secret is committed to Git | error: use `${VAR}` expansion |
| The `sse` transport | Still works in places, but is deprecated | warning: prefer http |


## MCP Servers: Giving Claude Reach › Which servers are worth having for this app

- **A documentation server** (Context7 in the example) so that library questions are answered from current documentation instead of memory. Useful for fast-moving libraries such as Expo, Next.js and the Anthropic SDK.
- **A browser server** (Playwright) so that Claude can open the running web app, look at it and click through a flow: a way to verify UI work with evidence, as 44.7 recommends.
- **Your team’s own docs or issue tracker**, if it offers a server, so a prompt can say “implement the story in this ticket” and Claude can read the ticket.
> **An MCP server is a new way in: three rules**
>
> **Everything an MCP tool returns is untrusted input.** A web page, an issue comment or a document fetched through a server can contain text written to hijack the agent (prompt injection, Chapter 28). Treat a server’s output like user input.
>
> **Least privilege, always.** A database server should connect with a **read-only** account against a development copy, never to production with write access. A server that can do a thing will, eventually, be tricked into doing it.
>
> **Fewer is better.** Every connected server adds tool descriptions to the context, which costs space and attention. Connect the ones you use weekly, and remove the rest.


## Putting It Together: One Feature, Start to Finish › The plan, checked mechanically

At step 1 Claude runs the plan checker on its own plan. This is the real output on a good plan, and on one that names a file that does not exist and has a step with no way to tell it is finished:

**python tools/planlint.py PLAN.md --repo .   (a sound plan)**

```python
warn  open-questions: 1 open question(s): answer them before building.
PLAN OK
```

**python tools/planlint.py BAD.md --repo .   (a plan built on a guess)**

```python
warn  step-unverifiable: Step 1 has no way to tell it is finished: 'Add RenameSerializer with validation.'
error missing-file: `backend/chat/forms.py` does not exist and is not marked (new): the plan may be built on a guess.
warn  open-questions: 1 open question(s): answer them before building.
PLAN NEEDS WORK
```

The second is the case worth catching: `backend/chat/forms.py` does not exist. A plan that names it was written from an assumption about your code, and everything built on it will carry that assumption. Better to find out now, in a Markdown file, than at step 4 in a pull request.


## Putting It Together: One Feature, Start to Finish › When the guardrails speak

Somewhere in a session like this, Claude will try something it should not. Not out of malice: out of a plausible shortcut. These are the real messages the hooks would send back, and notice that each one tells Claude both **what is wrong** and **what to do instead**:

| **Claude tried...** | **The hook** | **What Claude is told** |
|---|---|---|
| `git add -A && git commit -m "wip"` | `small_commit_guard` | message must look like “feat(chat): rename a conversation” (type, optional scope, colon, summary); got ‘wip’ |
| `git commit --no-verify -m "x"` | `guard_bash` | do not bypass pre-commit hooks with --no-verify |
| `echo 'STRIPE_SECRET=abc' >> .env` | `guard_bash` | do not write secrets files from the shell |
| An edit to the first migration | `protect_files` | an existing migration is history: create a new migration instead of editing it |
| “Done!” while `make check` is failing | `stop_gate` | `make check` failed (attempt 1 of 3). Fix the cause, not the check, then finish. (plus the output) |

None of these needed you to be watching. That is the quiet benefit of the whole chapter: **the work is structured so that the common failures are caught by something other than your attention**, which leaves your attention for the part that is genuinely yours: whether this is the right feature, designed the right way.
