# Chapter 48 — Building a Full-Stack Application End to End with Claude Code: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## The Shape of a Full-Stack Build with Claude Code › What each stage produces

| **Stage** | **File it produces** | **Who approves** | **Automatic check** |
|---|---|---|---|
| **Spec** | docs/specs/<feature>.md | You | spec_lint: sections present, criteria numbered, no TBD |
| **Plan** | docs/specs/<feature>-tasks.md | You | Every criterion appears in some task |
| **Contract** | contracts/openapi.json | You | contract_lint, contract_diff against main |
| **Backend** | backend/<app>/ and its tests | You, security-reviewer subagent | Django tests, generated schema equals contract |
| **Web** | web/src/ and its tests | You | tsc, lint, component tests, generated types up to date |
| **Mobile** | mobile/src/ and its tests | You | tsc, jest, generated types up to date |
| **Whole** | Dockerfiles, Compose, CI | You | trace_check, sync_check, docker build, CI green |


## The Shape of a Full-Stack Build with Claude Code › The project layout

Everything in this chapter assumes one repository (a **monorepo**) with the three applications side by side. A monorepo makes parallel work and cross-layer checks easy, because one clone, one branch and one pull request can contain a feature end to end. If your earlier chapters used separate repositories, the ideas still apply, but the contract folder and the checks then need a home that all three repositories can read.

**text  project layout**

```text
ai-chat-app/
  CLAUDE.md                     # how we build features (read first, every session)
  .claude/
    settings.json               # permissions the whole team shares
    agents/                     # subagents (reviewers, test runner)
    skills/                     # slash commands: /spec-to-plan, /sync-check
  contracts/openapi.json        # THE API contract (single source of truth)
  docs/specs/                   # one spec and one task list per feature
  tools/                        # small checks, Python standard library only
  backend/                      # Django, DRF, Channels, Celery
  web/                          # Next.js (App Router, TypeScript)
  mobile/                       # Expo, React Native, TypeScript
  docker-compose.yml  .env.example  .github/workflows/ci.yml
```

Chapter 43 introduced CLAUDE.md, and Chapter 44 covered subagents, skills and hooks. Here we put them to work. The most important part of this chapter’s CLAUDE.md is the short section that tells every session how features are built:

**markdown  CLAUDE.md (excerpt)**

```markdown
## How we build features (read this first)
1. A feature starts as a spec in `docs/specs/<name>.md` with numbered acceptance criteria (AC-1, AC-2, ...).
2. The spec becomes a task list in `docs/specs/<name>-tasks.md`. One task = one prompt = one commit.
3. **Contract first.** `contracts/openapi.json` is the single source of truth for the API. Change the contract,
   then the backend, then regenerate types (`npm run api:types` in `web/` and `mobile/`), then the UIs.
4. Every acceptance criterion needs a test whose name or comment contains its id, for example `AC-4`.
```

Notice what is in it: **process**, not just facts. Because CLAUDE.md is loaded at the start of every session, including each parallel session in section 48.5, every Claude Code instance you run follows the same rules without you repeating them.


## From Idea to Product Spec › Let Claude interview you

The weakest way to get a spec is "write me a spec for sharing conversations". Claude Code will happily write one, filled with plausible guesses that you will skim and approve. The better way is to turn the tables: ask Claude Code to **interview you** until the ambiguities are gone, then write the spec from your answers. Start in plan mode (Chapter 43) so it cannot edit anything while it asks questions.

**prompt to Claude Code (plan mode)**

```text
I want to add a feature to the AI Chat SaaS: the owner of a conversation can share
  it
with a link that anyone can open to read it. Read CLAUDE.md and look at how the chat
  app
models conversations and messages (backend/chat/), then interview me about the
  feature.

Rules for the interview:
- Ask at most four questions at a time, each with your recommended answer and why.
- Cover: who can see what, what happens over time (new messages, deletion, expiry),
  what can go wrong or be abused, what we are NOT building, and what each platform
    needs.
- Do not write any code and do not write the spec yet.
- When you have no important questions left, say so, and wait.
```

Claude Code will ask things you had not thought about, and offering a recommended answer makes it quick to respond. In our case the questions that mattered were: "When the owner keeps chatting after sharing, should the viewer see the new messages?" (we decided no, a snapshot: it is safer and simpler); "Should the link reveal who shared it?" (no); "Can the link be switched off?" (yes, immediately); "What happens when someone guesses links?" (long random tokens, rate limits, and one identical error for every failure). Those four decisions shaped the data model, the security design and half the tests.

When the interview ends, ask for the spec in the format your project uses:

**prompt to Claude Code**

```text
Now write docs/specs/share-conversation.md from our interview. Use exactly these
  sections:
Problem, Users and stories, Acceptance criteria, Non-goals, Data, API, Security and
  privacy,
Open questions, Change log. Number the acceptance criteria AC-1, AC-2, ... one
  behaviour
each, written so a test can check it. Include the failure cases and the security
  rules as
criteria, not just the happy path. Mark every open question [resolved] with the
  decision.
Then run: python -m tools.spec_lint docs/specs/share-conversation.md
```


## From Idea to Product Spec › A tiny spec linter

A checklist you must remember is a checklist you will skip, so we make the machine check the mechanical part. `tools/spec_lint.py` (standard library only, about 70 lines) checks that the required sections exist and are not empty, that criteria are numbered consecutively without duplicates, that no open question is unresolved and that nobody left a TBD behind. It cannot tell whether your criteria are good. It can tell you that the spec is not finished.

**python  tools/spec_lint.py (the core)**

```python
REQUIRED_SECTIONS = [
    "Problem",
    "Users and stories",
    "Acceptance criteria",
    "Non-goals",
    "Data",
    "API",
    "Security and privacy",
    "Open questions",
]
AC_LINE = re.compile(r"^\s*[-*]\s*\*{0,2}(AC-(\d+))\*{0,2}\s*[:.]", re.MULTILINE)
PLACEHOLDER = re.compile(r"\b(TBD|TODO|FIXME)\b")

def headings(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^#{1,3}\s+(.+?)\s*$", text, re.MULTILINE)]

def section_body(text: str, name: str) -> str:
    pattern = re.compile(rf"^#{{1,3}}\s+{re.escape(name)}\s*$(.*?)(?=^#{{1,3}}\s|\Z)", re.MULTILINE | re.DOTALL)
    m = pattern.search(text)
    return m.group(1) if m else ""

def lint(text: str) -> list[str]:
    problems: list[str] = []
    found = {h.lower() for h in headings(text)}
    for name in REQUIRED_SECTIONS:
        if name.lower() not in found:
            problems.append(f"missing section: {name}")
        elif not section_body(text, name).strip():
            problems.append(f"empty section: {name}")

    ids = [int(m.group(2)) for m in AC_LINE.finditer(text)]
    if not ids:
        problems.append("no acceptance criteria found (write them as '- AC-1: ...')")
    if len(ids) != len(set(ids)):
        problems.append("duplicate acceptance criterion ids")
    if ids and sorted(set(ids)) != list(range(1, max(ids) + 1)):
        problems.append("acceptance criterion ids are not consecutive from AC-1")

    open_q = section_body(text, "Open questions")
    unresolved = [l for l in open_q.splitlines() if l.strip().startswith(("-", "*")) and "[resolved]" not in l.lower()
                  and "none" not in l.lower()]
    if unresolved:
        problems.append(f"{len(unresolved)} open question(s) not marked [resolved]")

    for n, line in enumerate(text.splitlines(), start=1):
        if PLACEHOLDER.search(line):
            problems.append(f"line {n}: placeholder left in spec: {line.strip()[:60]}")
    return problems
```

Run it on the real spec, and on a copy where criterion AC-5 was renamed AC-15:

**terminal output (real)**

```bash
$ python -m tools.spec_lint docs/specs/share-conversation.md
docs/specs/share-conversation.md: ready to build

$ python -m tools.spec_lint /tmp/spec_bad.md
/tmp/spec_bad.md: NOT READY
  - acceptance criterion ids are not consecutive from AC-1
```


## From Spec to a Task-by-Task Build Plan › Plan first, in plan mode

You already know from Chapter 44 to ask for a plan before code. Here we give that habit a repeatable form: a **skill** (a reusable slash command stored in your repository) that turns any approved spec into a task table. Because the file lives in `.claude/skills/`, the whole team and every parallel session gets the same planner.

**markdown  .claude/skills/spec-to-plan/SKILL.md**

```markdown
---
name: spec-to-plan
description: Turn an approved feature spec into a task-by-task build plan with lanes, dependencies and acceptance criteria per task.
argument-hint: <path to spec>
disable-model-invocation: true
---
Read the spec at $ARGUMENTS and `CLAUDE.md`.

1. Run `python -m tools.spec_lint $ARGUMENTS`. If it reports problems, stop and list them.
2. Write `<spec name>-tasks.md` next to the spec, as a table with columns: ID, Lane (contract, backend, web, mobile, infra, all), Task, Depends on, Covers (AC ids), Done when.
3. Task 1 is always the OpenAPI contract. Backend, web and mobile tasks depend on it, never on each other.
4. Every acceptance criterion must appear in the Covers column of at least one task.
5. Each task must be small enough for one prompt and one commit. If it is not, split it.
6. After the table, write one line saying which tasks can run in parallel.
Do not write any application code. Show me the plan and wait.
```

> **Skills and commands**
>
> In current versions of Claude Code, custom slash commands and skills are the same mechanism. A folder `.claude/skills/<name>/SKILL.md` creates `/name`, and older single-file commands in `.claude/commands/<name>.md` still work. The frontmatter fields shown here (`description`, `argument-hint`, `disable-model-invocation`) were checked against the documentation in November 2026; if your version differs, the documentation is the authority. `disable-model-invocation: true` means Claude will only run it when you type the command, not on its own.

Run it, read the plan, and push back. The plan is the cheapest place in the project to change your mind:

**Claude Code session**

```
> /spec-to-plan docs/specs/share-conversation.md

Spec lint: ready to build. Writing docs/specs/share-conversation-tasks.md.

> The mobile task depends on T1 only, right? It should not wait for the web dialog.

Correct: T8 depends only on the contract (T1). I had written "T6" by mistake. Fixed.
```


## From Spec to a Task-by-Task Build Plan › Traceability: every criterion has a test

The plan promises that each criterion is covered. A second tiny script checks that the **tests** keep the promise. The convention is simple: a test mentions the criterion it protects in its name, a comment or its title (`test_ac4_later_messages_are_not_visible`, `it("AC-11: ...")`). `tools/trace_check.py` reads the criteria from the spec, scans the test files in all three applications, and reports any criterion that no test mentions.

**python  tools/trace_check.py (the core)**

```python
AC_DEF = re.compile(r"^\s*[-*]\s*\*{0,2}AC-(\d+)\*{0,2}\s*[:.]\s*(.*)$", re.MULTILINE)
AC_REF = re.compile(r"(?<![A-Za-z0-9])AC[-_ ]?(\d+)(?!\d)", re.IGNORECASE)  # matches AC-3, AC3 and test_ac3_x

def acceptance_criteria(spec_text: str) -> dict[int, str]:
    return {int(m.group(1)): m.group(2).strip() for m in AC_DEF.finditer(spec_text)}

def is_test_file(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.startswith("test_")
        or name.endswith(("_test.py", "_tests.py"))
        or name == "tests.py"
        or ".test." in name
        or ".spec." in name
        or "__tests__" in path.parts
        or "tests" in path.parts
    )

def iter_test_files(roots: list[Path]):
    for root in roots:
        if root.is_file():
            if is_test_file(root):
                yield root
            continue
        for path in root.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.is_file() and path.suffix in TEXT_SUFFIXES and is_test_file(path):
                yield path

def coverage(spec_text: str, roots: list[Path]) -> tuple[dict[int, str], dict[int, set[str]]]:
    criteria = acceptance_criteria(spec_text)
    covered: dict[int, set[str]] = {n: set() for n in criteria}
    for path in iter_test_files(roots):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in AC_REF.finditer(text):
            n = int(m.group(1))
            if n in covered:
                covered[n].add(str(path))
    return criteria, covered
```

A small detail worth learning from: the pattern for finding references first used `\b` (word boundary), which silently missed names such as `test_ac3_x` because an underscore counts as a word character. The tool’s tests caught it, and the pattern now says "not preceded by a letter or digit" instead. Referee scripts need tests too. Here is the check on the finished project, and on a copy of it where the AC-12 test was deleted:

**terminal output (real)**

```bash
$ python -m tools.trace_check docs/specs/share-conversation.md backend web mobile
AC-1  ok      A signed-in owner can create a share link for one of their own convers
AC-2  ok      The full link is returned only once, when it is created. Afterwards th
  ...
AC-13 ok      The owner sees how many times each link was opened. (Added by change r

13 of 13 criteria have a test

$ python -m tools.trace_check docs/specs/share-conversation.md <copy without the AC-12 test>
AC-11 ok      The web app has a Share dialog with a copy button. The mobile app open
AC-12 MISSING Deleting a conversation deletes its links.
AC-13 ok      The owner sees how many times each link was opened. (Added by change r

12 of 13 criteria have a test        (exit code 1: CI fails)
```

This script proves that a test **mentions** the criterion, not that the test is any good. That is still worth a great deal: the most common failure with AI-written code is not a bad test but a missing one, and a missing test is invisible until something breaks.


## Contract-First Development › Linting the contract

House rules that nobody checks are suggestions. `tools/contract_lint.py` checks seven of them on every pull request:

| **Rule** | **What it checks** | **Why it matters** |
|---|---|---|
| **C1** | Every operation has an operationId | Generated clients use it as the function name |
| **C2** | operationIds are unique and camelCase | Duplicates overwrite each other in generated code |
| **C3** | Every operation has tags and a summary | Docs and client grouping stay readable |
| **C4** | Security is declared, or the endpoint is explicitly public (security: []) | A forgotten permission becomes a visible gap, not a silent default |
| **C5** | At least one 4xx or default response is documented | Clients must know errors exist |
| **C6** | Every {path parameter} is declared | Otherwise the generated types are wrong |
| **C7** | No success response is an untyped object | It would become any in TypeScript and turn the type checker off |

**python  tools/contract_lint.py (the core)**

```python
def lint(doc: dict) -> list[str]:
    problems: list[str] = []
    seen_ids: dict[str, str] = {}
    default_security = doc.get("security")
    for path, method, op in operations(doc):
        where = f"{method.upper()} {path}"
        op_id = op.get("operationId")
        if not op_id:
            problems.append(f"C1 {where}: missing operationId")
        else:
            if not CAMEL.match(op_id):
                problems.append(f"C2 {where}: operationId '{op_id}' is not camelCase")
            if op_id in seen_ids:
                problems.append(f"C2 {where}: operationId '{op_id}' also used by {seen_ids[op_id]}")
            seen_ids[op_id] = where
        if not op.get("tags") or not op.get("summary"):
            problems.append(f"C3 {where}: needs tags and a summary")
        if "security" not in op and not default_security:
            problems.append(f"C4 {where}: no security declared (use security: [] for a public endpoint)")
        responses = op.get("responses", {})
        if not any(code.startswith("4") or code == "default" for code in responses):
            problems.append(f"C5 {where}: no error response documented")
        declared = {resolve(doc, p).get("name") for p in op.get("parameters", [])}
        declared |= {resolve(doc, p).get("name") for p in doc["paths"][path].get("parameters", [])}
        for name in PATH_PARAM.findall(path):
            if name not in declared:
                problems.append(f"C6 {where}: path parameter '{name}' is not declared")
        for code, response in responses.items():
            if not code.startswith("2"):
                continue
            schema = json_schema_of(doc, response)
            if schema and schema.get("type") == "object" and not schema.get("properties") \
                    and "allOf" not in schema and "oneOf" not in schema:
                problems.append(f"C7 {where}: {code} response is an untyped object")
    return problems
```

**terminal output (real)**

```bash
$ python -m tools.contract_lint contracts/openapi.json
contracts/openapi.json: contract looks good
```

The tests for the linter deliberately break the real contract in seven ways (remove an operationId, duplicate one, drop the security default, delete an error response, remove a path parameter declaration, make a response untyped) and check that each break is reported. Break your own rules on purpose to make sure the referee notices.


## Contract-First Development › Code-first or contract-first? An honest comparison

Chapter 12 used **drf-spectacular**, which generates an OpenAPI file **from your Django code**. That is code-first, and it is a good way to work alone. Contract-first reverses the arrow: the file is written first and the code must match. For one developer and one client, code-first is less work. For three clients built in parallel, contract-first wins, because the interface exists before the implementation and can be reviewed on its own. You can have both: write the contract first, then let CI generate the schema from the finished backend and fail if the two differ (section 48.7).


## Contract-First Development › Generating typed clients

Once the contract is merged, the web and mobile lanes each generate their types from it. We use two small libraries: **openapi-typescript** turns the contract into TypeScript types, and **openapi-fetch** is a tiny `fetch` wrapper whose functions are typed by those types.

**bash terminal  (in web/ and again in mobile/)**

```bash
npm install openapi-fetch
npm install -D openapi-typescript typescript

# package.json  "scripts": { "api:types": "openapi-typescript ../contracts/openapi.json -o src/lib/api/generated/schema.d.ts" }
# (in mobile/ the output path is src/lib/generated/schema.d.ts)
npm run api:types
```

The generated file is committed to git but **never edited by hand**: CLAUDE.md says so, and CI regenerates it and fails if the committed copy differs (section 48.7). After this step a wrong URL, a misspelled field or a missing parameter is a compile error:

**typescript  web/src/lib/api/sharing.ts (excerpt)**

```typescript
import { api, ApiError, unwrap } from "./client";
import type { components } from "./generated/schema";

export type ShareLink = components["schemas"]["ShareLink"];
export type ShareLinkCreated = components["schemas"]["ShareLinkCreated"];
export type ExpiresIn = NonNullable<components["schemas"]["ShareLinkCreate"]["expires_in"]>;

export async function createShareLink(conversationId: string, expiresIn: ExpiresIn): Promise<ShareLinkCreated> {
  return unwrap(
    await api.POST("/api/v1/conversations/{conversation_id}/share/", {
      params: { path: { conversation_id: conversationId } },
      body: { expires_in: expiresIn },
    }),
  );
}

export async function listShareLinks(conversationId: string): Promise<ShareLink[]> {
  return unwrap(
    await api.GET("/api/v1/conversations/{conversation_id}/share/", {
      params: { path: { conversation_id: conversationId } },
    }),
```

If someone writes `"/api/v1/conversations/{conversation_id}/shares/"` (note the extra s), the TypeScript compiler reports that the argument is not assignable to the known paths, because `paths` was generated from the contract. The same happens if `body` contains `expiresIn` instead of `expires_in`. These mistakes are exactly the ones an AI assistant makes when it "remembers" an API that does not exist.

> **Do not let Claude Code edit generated files**
>
> If Claude Code "fixes" a type error by editing `schema.d.ts`, it has hidden a real disagreement between the code and the contract. Put the rule in CLAUDE.md, deny edits to generated folders in `.claude/settings.json` if you like, and in CI regenerate and compare. The right fix for a type error is either in the code that uses the type or, if the contract is wrong, in the contract (and then you regenerate).


## Feature Branches, Parallel Sessions and Subagents › Git worktrees: one folder per session

Normally one repository folder holds one checked-out branch. If two Claude Code sessions work in the same folder, they edit the same files and overwrite each other. A **git worktree** is a second folder with its own branch that shares the same history and remote. Each parallel session gets its own worktree, so their changes cannot collide until you merge.

**bash terminal  (plain git: works everywhere)**

```bash
cd ~/projects/ai-chat-app && git checkout main && git pull
git worktree add ../ai-chat-backend -b feature/share-backend
git worktree add ../ai-chat-web     -b feature/share-web
git worktree add ../ai-chat-mobile  -b feature/share-mobile
git worktree list

# one terminal per lane
cd ../ai-chat-backend && claude
cd ../ai-chat-web     && claude
cd ../ai-chat-mobile  && claude
```

Claude Code can also create the worktree for you. The `--worktree` flag (short form `-w`) creates a folder under `.claude/worktrees/<name>/` on a new branch and starts the session inside it, and the desktop app creates a worktree for each new session automatically:

**bash terminal  (Claude Code's built-in worktrees)**

```bash
claude --worktree backend-share
claude --worktree web-share
claude --worktree mobile-share
```

Two practical points. **A new worktree is a fresh checkout**: it has none of your untracked files, so it has no `.venv`, no `node_modules` and no `.env`. Create the virtual environment and run `npm ci` inside each one, and check the worktrees documentation for how to bring a local `.env` along. Never solve the missing-`.env` problem by letting an agent read your real secrets file; our `settings.json` denies that on purpose. Second, `.claude/worktrees` belongs in `.gitignore` and `.dockerignore`.

*(figure: see the printed book)*


## Feature Branches, Parallel Sessions and Subagents › Rules that make parallel work safe

| **Rule** | **Why** |
|---|---|
| **Each lane edits only its own directory** | Two lanes never touch the same file, so merges are boring. CLAUDE.md says so and the starter prompt repeats it. |
| **Shared files change in exactly one lane** | Lockfiles, the contract and generated types are the usual conflict sources. The contract changes only in the contract branch. |
| **Start every lane from the merged contract** | A lane started earlier builds against a contract that may change under it. |
| **Merge order does not matter, review order does** | Review the backend first: it is where mistakes cost most. Web and mobile then confirm the contract is usable. |
| **Rebase or merge main into a lane before its pull request** | So the lane is tested against the others that already landed. |

> **When not to run in parallel**
>
> **You are the bottleneck.** Three lanes mean three streams of diffs to read. If you cannot review as fast as Claude Code writes, parallel work just builds a queue of unreviewed code. Two lanes are often plenty.
>
> **The contract is not stable.** If you are still arguing about field names, finish that argument first. Three sessions will each guess differently.
>
> **The feature is small.** Sharing a conversation takes a few hours sequentially. Parallel setup costs real time (worktrees, environments, three terminals); it pays off for bigger features.


## Feature Branches, Parallel Sessions and Subagents › Which tool for which job?

| **You want to...** | **Use** | **Because** |
|---|---|---|
| **Run two independent pieces of work at the same time** | Separate worktree sessions | Separate files, separate context, no collisions |
| **Review or search without filling your context** | A read-only subagent | Own context window; only the summary comes back |
| **Repeat a prompt the team uses often** | A skill (slash command) | One word instead of a paragraph, versioned in git |
| **Force something to happen every time (format, block a file)** | A hook or a permission rule | Hooks are deterministic; prompts are suggestions |
| **Give Claude facts about your project** | CLAUDE.md | Loaded in every session, including parallel ones |

Finally, the permissions the whole team shares. They live in `.claude/settings.json`, which is committed to git. We allow the referee commands and read-only git, and we deny reading secret files, pushing and recursive deletes:

**json  .claude/settings.json**

```json
{
  "permissions": {
    "allow": [
      "Bash(python -m tools.*)",
      "Bash(python manage.py test*)",
      "Bash(ruff *)",
      "Bash(npm run lint)",
      "Bash(npm run typecheck)",
      "Bash(npm test*)",
      "Bash(git status)",
      "Bash(git diff*)",
      "Bash(git log*)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./.env.local)",
      "Read(./.env.production)",
      "Bash(git push*)",
      "Bash(rm -rf*)"
    ]
  }
}
```

> **Permission rule syntax changes**
>
> The exact pattern syntax for permission rules (the `Bash(...)` strings) has evolved between versions. Treat these as a starting point, open `/permissions` in Claude Code to see how your version reads them, and test that a denied command really is denied before you trust a rule.


## Keeping Backend, Web and Mobile in Sync › Telling very old apps to update

Sometimes you cannot avoid a break. Mobile apps can send their version in an `X-App-Version` header, and the server can answer "too old" with HTTP status 426 (Upgrade Required) so the app shows an update screen instead of failing strangely. The comparison belongs in a small pure function, because comparing versions as text is a classic bug (the text "1.9.0" sorts after "1.10.0"):

**python  backend/core/app_version.py**

```python
_VERSION = re.compile(r"^(\d{1,4})\.(\d{1,4})(?:\.(\d{1,4}))?(?:[-+].*)?$")

class BadVersion(ValueError):
    pass

def parse_version(text: str) -> tuple[int, int, int]:
    """'1.4' -> (1, 4, 0); '2.0.1-beta.3' -> (2, 0, 1). Anything else raises BadVersion."""
    m = _VERSION.match((text or "").strip())
    if not m:
        raise BadVersion(f"not a version: {text!r}")
    major, minor, patch = m.groups()
    return int(major), int(minor), int(patch or 0)

def needs_update(header_value: str | None, minimum: str) -> bool:
    """True only when the client SAID it is older than the minimum.

    A missing or unreadable header returns False: browsers and old builds that never sent
    the header must keep working. (Fail open is right here; this is a courtesy, not security.)
    """
    if not header_value:
        return False
    try:
        return parse_version(header_value) < parse_version(minimum)
    except BadVersion:
        return False
```

Its six tests pass, including the 1.9 versus 1.10 case. Notice the design choice: a missing or unreadable header means **do not block**. This gate is a courtesy to old apps, not a security control, so it fails open. A DRF permission or middleware that calls `needs_update(request.headers.get("X-App-Version"), settings.MIN_APP_VERSION)` and returns 426 is three lines; the mobile app handles 426 once, in its API client, by showing "Please update the app".


## Keeping Backend, Web and Mobile in Sync › Catching hand-written calls: sync_check

Generated clients protect you only when people use them. A hurried `fetch("/api/v1/...")` typed into a component bypasses all the types. `tools/sync_check.py` scans web and mobile source for strings that start with `/api/` and checks that each one matches a path in the contract (a `{id}` in the contract matches a `${id}` in a template string). It is deliberately simple; it cannot prove a call is right, only that the route exists.

**python  tools/sync_check.py (the matching)**

```python
def contract_patterns(doc: dict) -> list[re.Pattern]:
    patterns = []
    for path in doc.get("paths", {}):
        regex = re.escape(path)
        regex = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", regex)
        patterns.append(re.compile(rf"^{regex}$"))
    return patterns

def normalise(url: str) -> str:
    """'/api/v1/x/${id}/share/' -> '/api/v1/x/PARAM/share/'; also add a trailing slash."""
    url = re.sub(r"\$\{[^}]*\}", "PARAM", url)
    return url if url.endswith("/") else url + "/"

def find_calls(root: Path):
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts) or path.suffix not in SOURCE_SUFFIXES:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            for m in LITERAL.finditer(line):
                yield path, n, m.group(1)

def check(doc: dict, roots: list[Path]) -> list[str]:
    patterns = contract_patterns(doc)
    problems = []
    for root in roots:
        for path, n, url in find_calls(root):
            if not any(p.match(normalise(url)) for p in patterns):
                problems.append(f"{path}:{n}: {url} is not in the contract")
    return problems
```

**terminal output (real)**

```bash
$ python -m tools.sync_check contracts/openapi.json web/src mobile/src
every API call in the code is described by the contract

$ python -m tools.sync_check contracts/openapi.json <folder where ...share/ became ...shares/>
1 call(s) the contract does not describe:
  - /tmp/t3/sharing.ts:18: /api/v1/conversations/{conversation_id}/shares/ is not in the contract
```

Its limits are worth knowing. It misses URLs built from a variable that already contains the prefix (the server-side page in section 48.10 builds its URL that way), and it says nothing about the shape of the data. That is why it is one referee among several, not the whole defence.


## Keeping Backend, Web and Mobile in Sync › A daily habit: /sync-check

Put the whole list in a skill so you can run it after any change, and so can every parallel session:

**markdown  .claude/skills/sync-check/SKILL.md**

```markdown
---
name: sync-check
description: Check that contract, backend, web and mobile still agree after a change.
disable-model-invocation: true
---
Run these in order and summarise the results in a short table (check, result, one-line note):

1. `python -m tools.contract_lint contracts/openapi.json`
2. `git show main:contracts/openapi.json > /tmp/old.json && python -m tools.contract_diff /tmp/old.json contracts/openapi.json`
3. `python -m tools.sync_check contracts/openapi.json web/src mobile/src`
4. `(cd web && npm run api:types && npm run typecheck)` and `(cd mobile && npm run api:types && npm run typecheck)`
5. `python -m tools.trace_check docs/specs/$ARGUMENTS.md backend web mobile` (if a spec name was given)

If a TypeScript error appears after regenerating types, list each error as a place that must change.
Do not fix anything unless I ask.
```

Notice the last instruction in that skill: **do not fix anything unless asked**. A checking command that also edits files is a command whose output you can no longer trust.

> **How compile errors become your to-do list**
>
> When you regenerate types after a **breaking** contract change, TypeScript reports every line in web and mobile that used the old shape. That list is exactly the set of places to change, found for free and complete. Ask Claude Code to work through the errors one file at a time, and run the type checker again until it is silent. This is one of the biggest reasons to prefer a typed client to hand-written `fetch` calls.


## Docker, Compose and CI with Claude Code › The files, with the review points

**dockerfile  backend/Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS deps
COPY requirements.lock.txt .
RUN pip install --prefix=/install -r requirements.lock.txt

FROM base AS runtime
RUN useradd --create-home --uid 10001 app
COPY --from=deps /install /usr/local
COPY --chown=app:app . .
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
# daphne serves HTTP and WebSockets (Channels) from one process
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
```

Review it with the checklist below, not by skimming. In this file: the base image has a tag (not `latest`); dependencies are installed in a separate stage from the lockfile so a code change does not reinstall everything; the runtime stage creates a user with `useradd` and switches to it; there is a health check; and `daphne` serves both HTTP and WebSockets because Channels needs an ASGI server (Chapter 14).

**dockerfile  web/Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* values are baked into the browser bundle at build time: they are public by design
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S app && adduser -S app -G app
# requires `output: "standalone"` in next.config.ts
COPY --from=build --chown=app:app /app/.next/standalone ./
COPY --from=build --chown=app:app /app/.next/static ./.next/static
COPY --from=build --chown=app:app /app/public ./public
USER app
EXPOSE 3000
CMD ["node", "server.js"]
```

The web image is built in three stages (install, build, run). One detail trips almost everyone: `NEXT_PUBLIC_` **variables are baked into the browser bundle at build time**, so `NEXT_PUBLIC_API_URL` is a build argument, not a runtime setting, and it must never hold a secret. Server-side code, on the other hand, reads `API_INTERNAL_URL` at runtime, which in Compose is the service name `backend`. The line `output: "standalone"` in `next.config.ts` is required for the small runtime image.

**yaml  docker-compose.yml**

```yaml
# Local development stack: docker compose up --build
name: ai-chat

services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: aichat
      POSTGRES_USER: aichat
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aichat -d aichat"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  backend:
    build: ./backend
    env_file: .env
    environment:
      DATABASE_URL: postgres://aichat:${POSTGRES_PASSWORD}@db:5432/aichat
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }
    ports: ["8000:8000"]
    command: sh -c "python manage.py migrate --noinput && daphne -b 0.0.0.0 -p 8000 config.asgi:application"

  celery:
    build: ./backend
    env_file: .env
    environment:
      DATABASE_URL: postgres://aichat:${POSTGRES_PASSWORD}@db:5432/aichat
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }
    command: celery -A config worker --loglevel=info

  web:
    build:
      context: ./web
      args:
        NEXT_PUBLIC_API_URL: http://localhost:8000
    environment:
      API_INTERNAL_URL: http://backend:8000   # server-side calls use the Docker network name
    depends_on: [backend]
    ports: ["3000:3000"]

volumes:
  pgdata:
```

| **Checklist item** | **Look for** | **Typical AI mistake** |
|---|---|---|
| **Image tags** | A specific version such as postgres:17, python:3.12-slim | `latest`, or a version that is end of life |
| **User** | A non-root USER near the end | Everything runs as root |
| **Secrets** | Read from .env at run time; .env in .dockerignore and .gitignore | A password written inline, or `COPY . .` that copies .env into the image |
| **Startup order** | depends_on with `condition: service_healthy` and real healthchecks | Plain `depends_on`, so the app starts before the database accepts connections |
| **Ports** | Only web and backend published to the host | Postgres and Redis exposed on 5432 and 6379 |
| **Caching** | Dependency files copied and installed before the source | Source copied first, so every edit reinstalls everything |
| **Environment split** | Build-time public values separate from run-time secrets | A secret passed as a build ARG (it stays in image history) |
| **Versions** | Language, database and action versions still supported | Old versions copied from training data |

> **Versions in this chapter will age**
>
> The image tags (Python 3.12, Node 22, Postgres 17, Redis 7) and the action versions (`actions/checkout@v4` and friends) were reasonable when this chapter was written. Before you copy them, check what is currently supported (each project’s release page, or endoflife.date) and update. This is exactly the kind of fact an AI assistant gets wrong from memory, so verify it instead of trusting it.
