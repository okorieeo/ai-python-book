# Chapter 49 — Debugging and Fixing Errors Directly with Claude Code: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## The Debugging Loop › A reproduction is also a test in disguise

The smallest reproduction is often already a test. Here is the first museum bug, the one we use to feel the loop. It is a function that decides whether a share link has expired. The very first symptom is a crash:

**python  museum/bug1_timezone/buggy.py**

```python
"""Bug 1: a share link's expiry check. Crashes with a TypeError as soon as it meets a real database value."""
from datetime import datetime

def is_expired(expires_at, now=None):
    now = now or datetime.now()          # naive local time
    return expires_at <= now             # expires_at comes from the database, timezone-aware
```

**terminal output (real)**

```bash
$ IMPL=buggy python -m unittest museum.bug1_timezone.test_bug1
ERROR: test_future_link_is_active_on_a_laptop_in_tokyo ...
TypeError: can't compare offset-naive and offset-aware datetimes
ERROR: test_future_link_is_active_on_a_utc_server ...
TypeError: can't compare offset-naive and offset-aware datetimes
ERROR: test_past_link_is_expired_in_new_york ...
TypeError: can't compare offset-naive and offset-aware datetimes
Ran 4 tests in 0.001s
FAILED (errors=3)
```

That is a reproduction: one command, three failures, the same error each time. We will fix it properly in section 49.5 and compare it with the quick patch that makes the crash disappear.


## Giving Claude Code the Evidence › Protect secrets before you paste

Logs contain things that must not leave your machine: bearer tokens, passwords in connection strings, email addresses, customer data. Claude Code reads files you point it at, and anything you paste becomes part of the conversation. Make redaction a habit, and make it automatic where you can. `tools/triage.py` does both jobs: it removes common secret shapes, finds the exception, keeps your own code frames and drops library frames, trims a long log to its tail, and writes the five-part report.

**python  tools/triage.py (redaction rules)**

```python
REDACTIONS = [
    (re.compile(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"), "Bearer [REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[REDACTED_JWT]"),
    (re.compile(r"\b(sk|pk|rk)[-_](live|test|ant)?[-_]?[A-Za-z0-9]{16,}"), "[REDACTED_KEY]"),
    (re.compile(r"(?i)\b([A-Za-z0-9_]*(?:password|passwd|secret|api[_-]?key|token|access[_-]?key)[A-Za-z0-9_]*)(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&]+)"),
     r"\1\2[REDACTED]"),
    (re.compile(r"(://[^/\s:@]+:)[^@\s/]+@"), r"\1[REDACTED]@"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[REDACTED_EMAIL]"),
]
LIBRARY_MARKERS = ("site-packages", "dist-packages", "/lib/python", "node_modules", "node:", "<frozen")
PY_EXC = re.compile(r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|DoesNotExist|Invalid)\w*)(?::\s?(?P<msg>.*))?$")
PY_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>.+)$')
JS_ERR = re.compile(r"^(?P<type>(?:[A-Z]\w*)?(?:Error|Exception))(?::\s?(?P<msg>.*))?$")
JS_FRAME = re.compile(r"^\s*at (?P<head>.*?):(?P<line>\d+):(?P<col>\d+)\)?\s*$")
```

Run it on a log with a traceback in it. The input was a real log from the museum bug, with a token and an email address added to prove the point:

**terminal output (real, lightly shortened)**

```bash
$ python -m tools.triage --symptom "Public share page shows an error for a valid link" \
    --expected "The shared conversation is shown" \
    --repro "Create a link in the web app; Open it in a private window" \
    --log backend.log --tried "restarted the containers; created a new link"

# Bug report
## Symptom
Public share page shows an error for a valid link
## Expected
The shared conversation is shown
## Steps to reproduce
1. Create a link in the web app
2. Open it in a private window
## Environment
- python: 3.12.3
- os: Linux-6.8-x86_64
## Evidence
**TypeError**: can't compare offset-naive and offset-aware datetimes
Your code, innermost last:
- `/app/sharing/views.py:41` in `get`: `if is_expired(link.expires_at):`
- `/app/museum/bug1_timezone/buggy.py:7` in `is_expired`: `return expires_at <= now ...`
Log tail (secrets removed):
2026-11-09 09:44:35,123 INFO Authorization: Bearer [REDACTED] user=[REDACTED_EMAIL]
  ...
## Already tried
- restarted the containers
- created a new link
```

Two warnings. First, **redaction is a safety net, not a guarantee**: read the report before you share it, because a secret in an unusual shape will slip through. Second, the scripts shown here only read the files you give them; they never contact anything. The safest evidence is evidence that never contained a secret: do not log request bodies, tokens or full URLs with tokens in them in the first place (Chapter 17).


## Fixing Real Errors › Django and DRF, bug 2: the slow list (the N+1 query)

Symptom: the conversation list is fast with 5 chats and takes seconds with 500. Nothing crashes, nothing logs an error; the only evidence is time. The first move is to **count queries**, not to guess. In Django use `django-debug-toolbar` in development or `assertNumQueries` in a test. In our museum version the test counts SQL statements with the database’s trace hook:

**python  museum/bug2_n_plus_one/buggy.py**

```python
"""Bug 2: the conversation list is slow. One query for the list, then one more per row (N+1)."""

def conversation_summaries(conn):
    rows = conn.execute("SELECT id, title FROM conversation ORDER BY id").fetchall()
    out = []
    for conv_id, title in rows:
        (count,) = conn.execute("SELECT COUNT(*) FROM message WHERE conversation_id = ?", (conv_id,)).fetchone()
        out.append({"id": conv_id, "title": title, "message_count": count})
    return out
```

**terminal output (real)**

```bash
$ IMPL=buggy python -m unittest museum.bug2_n_plus_one.test_bug2
FAIL: test_query_count_does_not_grow_with_the_number_of_conversations
AssertionError: 51 not less than or equal to 2 : 51 queries for 50 conversations
FAILED (failures=1)
```

One query fetches the list; then the loop asks the database for each conversation’s message count separately: 1 + N queries. In Django this is the classic `for c in Conversation.objects.all(): c.messages.count()`. The fix asks the database to do the counting once. In Django that is `annotate(message_count=Count("messages"))` (and `select_related` or `prefetch_related` when you need related objects); in the museum it is a join with a group:

**python  museum/bug2_n_plus_one/fixed.py**

```python
"""One query with a LEFT JOIN and GROUP BY. In Django this is annotate(Count('messages'))."""

def conversation_summaries(conn):
    rows = conn.execute(
        """
        SELECT c.id, c.title, COUNT(m.id)
        FROM conversation c LEFT JOIN message m ON m.conversation_id = c.id
        GROUP BY c.id, c.title ORDER BY c.id
        """
    ).fetchall()
    return [{"id": i, "title": t, "message_count": n} for i, t, n in rows]
```

Look at the first test too: it checks that a conversation with **no** messages still appears with a count of zero. A natural but wrong "fix" uses an inner join, which silently drops empty conversations, so the page is faster and **wrong**. Whenever you optimise, keep a test for correctness next to the test for speed.


## Fixing Real Errors › Celery and Channels, bug 3: the task that runs twice

Symptom: some customers receive the receipt email twice. Nothing is broken in the sense of an error, and yet something is badly wrong. Celery (and any queue) gives you **at-least-once** delivery: if a task fails or the worker dies after doing its work but before reporting success, the task will run again. Our task sends an email, then records that it sent it. If recording fails, the whole task is retried, and the email goes out again:

**python  museum/bug3_retry/buggy.py**

```python
"""Bug 3: customers get the receipt email twice. The task is retried after it already sent."""

def send_receipt(order_id, mailer, store):
    mailer.send(order_id)            # side effect happens first
    store.mark_sent(order_id)        # ...then this fails, and the whole task runs again
```

**terminal output (real)**

```bash
$ IMPL=buggy python -m unittest museum.bug3_retry.test_bug3
FAIL: test_a_retried_task_sends_exactly_one_email
AssertionError: Lists differ: [1001, 1001] != [1001]
FAIL: test_running_the_task_again_later_sends_nothing_more
AssertionError: Lists differ: [1001, 1001, 1001] != [1001]
FAILED (failures=2)
```

The tempting patch is to remove the retry, which then loses emails when the failure was a genuine hiccup. The root-cause fix is to make the task **idempotent**: running it twice has the same effect as running it once. Check before acting, and give the outside service a stable key so that it ignores a repeat:

**python  museum/bug3_retry/fixed.py**

```python
"""Make the task safe to run twice (idempotent): check first, and give the provider a stable key."""

def send_receipt(order_id, mailer, store):
    if store.is_sent(order_id):
        return "already sent"
    mailer.send(order_id, idempotency_key=f"receipt-{order_id}")
    store.mark_sent(order_id)
    return "sent"
```

Idempotency is the most important idea for background work. Ask of every task: "if this ran twice, what would happen?" For sending money, sending messages and creating records the answer must be "the same as once" (Chapters 36 and 37 apply the same idea to payment webhooks).


## Fixing Real Errors › Next.js: build errors, hydration errors and server errors

Next.js failures come in three places, and mixing them up wastes the most time: the **build** (`next build`, a compile or type error), the **server** (an exception while rendering on the server) and the **browser** (an error after the page loaded). Always ask: which of the three is this?

| **You see (typical wording)** | **Usual cause** | **Fix at the root** |
|---|---|---|
| **"Application error: a server-side exception has occurred (see the server logs for more information). Digest: 1234567890"** | An exception in a server component or route. The page never says what; the **server log** does, keyed by the digest | Read `docker compose logs web` for that digest. In production, never show the details to users |
| **"You’re importing a component that needs** `useState`**. This React Hook only works in a Client Component."** | A component with state or events is used without `"use client"` | Add `"use client"` to the smallest component that needs it, not to the whole page |
| **"Hydration failed because the server rendered HTML didn’t match the client"** | Something differs between server and browser render: `new Date()`, `Math.random()`, `window` or `localStorage` read during render, invalid HTML nesting (a `<div>` inside a `<p>`) | Render the same thing on both sides, and move browser-only values into `useEffect` |
| **"ReferenceError: window is not defined"** | Browser-only code ran on the server | Move it into `useEffect` or a client component, or check `typeof window` |
| **"Type error: Property ’x’ does not exist on type ..." during build** | The code and the generated API types disagree (Chapter 48) | Do **not** edit the generated file or cast to `any`. Find which side is right: the code, or the contract |
| `fetch failed` **/** `ECONNREFUSED 127.0.0.1:8000` **in the server log** | Server code calls the API at `localhost`. Inside a container that is the container itself | Use the service name (`http://backend:8000`). The root cause in section 49.8 |

A hydration error is a good example of a bug where Claude Code’s speed helps. Ask it: "List every place in this component tree that reads the date, a random number, `window` or `localStorage` during render." That is a mechanical search it does well. Deciding what the page should show on the server and what on the client is your decision.


## Fixing Real Errors › React Native and Metro

Mobile errors have an extra complication: the code runs on a phone or emulator, the bundler (**Metro**) runs on your computer, and a **native** part (compiled code) may be older than your JavaScript. Always say which device, which OS version and whether you use Expo Go or a development build.

| **You see (typical wording)** | **Usual cause** | **Fix at the root** |
|---|---|---|
| **"Unable to resolve module X from Y"** | A missing package, a wrong import path (case matters on some systems), or a stale Metro cache | `npm install`, correct the path, then restart with a cleared cache (`npx expo start -c`). If it persists, the dependency is genuinely missing |
| **A red screen with a JavaScript error and a component stack** | A runtime error in your code, like `undefined is not an object` | Read the **first** frame in your own files; Claude can follow the props back from there |
| **"Invalid hook call" or two copies of React** | Two versions of React in the dependency tree | `npm ls react`; align versions with the Expo SDK’s expected ones |
| **A native module is "not found" or a feature does nothing** | The module needs native code that Expo Go does not include, or the dev build is older than your dependencies | Make a new development build after adding native dependencies; do not just reinstall JavaScript packages |
| **The API works in the browser but not on the phone** | The phone cannot reach `localhost` (that is the phone), or plain HTTP is blocked on the device | Use your computer’s LAN address or a tunnel; check cleartext rules for development |

For mobile, give Claude **both** the Metro terminal output and a screenshot of the device. The two often tell different halves of the story: Metro shows build and bundling errors, the device shows runtime errors.


## Fixing Real Errors › Docker and Docker Compose

| **You see (typical wording)** | **Usual cause** | **Fix at the root** |
|---|---|---|
| **"Bind for 0.0.0.0:8000 failed: port is already allocated"** | Another process or an old container already uses the port | `docker compose ps` and your system’s port listing to find it; stop **that**, do not change the port blindly |
| **A service restarts again and again (**`Restarting`**)** | The process exits at start: bad setting, failed migration, missing file | `docker compose logs --tail 50 <service>`: read the **first** error, not the last |
| **Backend starts before the database is ready and fails** | `depends_on` without a healthcheck condition | Add a healthcheck and `condition: service_healthy` (Chapter 48) |
| **"no such file or directory" for a file that exists on your laptop** | The file was not copied into the image (`.dockerignore`, wrong build context) or lives in a volume that hides it | Check `COPY` lines, `.dockerignore`, the build context and any volume mounted over the folder |
| `exec format error` | The image was built for a different CPU architecture (for example built on an Apple-silicon Mac, run on an x86 server) | Build for the target platform (`--platform`) and check the base image supports it |
| **Changed an environment variable and nothing changed** | Not recreated, or the value is baked in at build time (`NEXT_PUBLIC_*`) | `docker compose up -d --force-recreate <service>`, or rebuild for build-time values |
| **"no space left on device"** | Old images, build cache and volumes filled the disk | `docker system df`, then prune **deliberately**. Never `down -v` on a database you care about |

> **A pattern behind every family above**
>
> In each case the fastest route was the same: **read the first error, find your own code or configuration on the path, and form one hypothesis that an experiment can kill**. The frameworks differ; the loop does not.


## Root Cause or Quick Patch? Avoiding Fix Loops › Smells of a symptom patch

| **In the diff you see** | **What it usually means** | **Ask instead** |
|---|---|---|
| **A new broad** `try/except` **(or** `catch {}`**) around the failing line** | The error is hidden, not fixed. Later failures will be more mysterious | "What exactly raised, and why? Handle only that, or fix why it happens" |
| `time.sleep` **or** `setTimeout` **added** | A race condition is being hidden by delay. It will come back under load | "What is the ordering problem? Wait for the real event, not for time" |
| **A retry loop added around a call** | The call fails for a reason you have not found, or it is not idempotent | "Why does it fail? Is it safe to run twice?" |
| `as any`**,** `// @ts-ignore`**,** `# type: ignore`**,** `# noqa`**,** `eslint-disable` | The checker found a real disagreement and was silenced | "What is the checker telling us? Fix that" |
| **A guard such as** `if x is None: return` | The caller sent something impossible, and the guard hides why | "Why was it None? Should it ever be?" |
| **A test edited, skipped or loosened** | The test was right and the code wrong. Or the test was wrong, which needs a stated reason | "Show me why the old assertion was incorrect" |
| **Changes in many files for one bug** | The fix went looking for places to apply itself | "What is the smallest change that fixes the cause?" |


## Root Cause or Quick Patch? Avoiding Fix Loops › Finding the commit that broke it: git bisect

If something worked last week and fails now, you do not need to understand the code to find the cause. `git bisect` does a binary search through history: you tell it one good commit and one bad one, it checks out the middle, and you tell it good or bad; after a handful of steps it names the first bad commit. With a test that fails on the bug, it can run unattended with `git bisect run`, which is a very good job to hand to Claude Code.

Here is a real run, on a scratch repository with eight commits. A refactor in commit 5 caps coupons at 99 percent, so a 100 percent coupon no longer makes an item free. The test file is the same in every commit:

**terminal output (real)**

```bash
$ git log --oneline
b90c64c chore: comment 8
e7cdbe7 chore: comment 7
13997f8 chore: comment 6
512a781 refactor: round discount and cap coupons
3f2e071 chore: comment 4
776d309 chore: comment 3
de29559 chore: comment 2
cbfa273 feat: price with coupons

$ git bisect start && git bisect bad HEAD && git bisect good cbfa273
$ git bisect run python -m unittest test_price
running 'python3' '-m' 'unittest' 'test_price'
running 'python3' '-m' 'unittest' 'test_price'
running 'python3' '-m' 'unittest' 'test_price'
512a781cb3f01f49e112b7429ee33946e188a632 is the first bad commit
    refactor: round discount and cap coupons
bisect found first bad commit
```

Three test runs found the commit among eight, and the number grows only with the logarithm of the history: a thousand commits take about ten. Ask Claude Code: "Use `git bisect run` with this failing test to find the commit that introduced the bug, then show me that commit’s diff. Do not fix anything yet." Allow `git bisect*` in your permissions, and remember to run `git bisect reset` afterwards (Claude should do it, and you should check `git status`).


## Regression Tests and Reviewing the Diff Before You Commit › What a good regression test looks like

| **Quality** | **Why** | **Example from the museum** |
|---|---|---|
| Reproduces the **cause**, not just the error text | A test for the message breaks on a reworded message and passes on a wrong fix | Bug 1 runs under `TZ=Asia/Tokyo`, the condition that exposed the bug |
| **Small and fast** | Slow tests get skipped | Bug 2 counts queries instead of timing them |
| **Named for the behaviour** | The name is the documentation of the bug | `test_a_retried_task_sends_exactly_one_email` |
| **Fails for the right reason** | A test failing on a typo proves nothing | Read the failure message of the red run |
| **Carries its criterion or bug id** | Traceability (Chapter 48) | `AC-6` in the name, or `docs/debug/<id>.md` in a comment |


## Regression Tests and Reviewing the Diff Before You Commit › Review the diff like a stranger wrote it

Never commit a bug fix you have not read line by line. The diff is where the quick patches, the extra changes and the quietly weakened tests are visible. Look in this order:

1. `git diff --stat`: how many files, how many lines? A one-line bug rarely needs nine files.
2. **Are tests in the diff?** If the source changed and no test did, stop.
3. **Is anything unrelated in it?** Reformatting, renames, "while I was there" cleanups. Split them into a different commit (`git add -p` stages part of a file).
4. **Read each source hunk and ask: root cause or symptom?** Use the smell table in 49.6.
5. **Read each test hunk and ask: was anything removed or loosened?** An assertion that became weaker, a skipped test, a fixture changed to avoid the failure.
6. **Look for new dependencies and configuration**, new logging of data, and anything that touches secrets.

## Regression Tests and Reviewing the Diff Before You Commit › A referee for the diff

Parts of that review are mechanical, so `tools/fix_gate.py` does them. It reads a unified diff and reports: **ERROR** when source changed with no test, a generated file was edited, a check was silenced, a test was disabled or an exception is swallowed; **WARNING** when assertions were removed, a `sleep` or debug print was added, a dependency changed or the diff is over 300 lines. Here it is on a bad patch (a try/catch that swallows the error, a type check silenced, a sleep to hide the timing, and no test) and on a good one:

**python  tools/fix_gate.py (the rules)**

```python
ERROR_PATTERNS = [
    (re.compile(r"@unittest\.skip|pytest\.mark\.skip|\bxit\(|\bxdescribe\(|\b(it|test|describe)\.skip\("), "test disabled"),
    (re.compile(r"eslint-disable|@ts-ignore|@ts-nocheck|# type: ignore|# noqa|# pylint: disable"), "check silenced"),
    (re.compile(r"--no-verify"), "git hook bypassed"),
    (re.compile(r"^\s*except\s*:\s*$|^\s*except\s+(Base)?Exception\s*(as\s+\w+)?\s*:\s*(pass)?\s*$"), "broad except (check what it swallows)"),
    (re.compile(r"catch\s*(\([^)]*\))?\s*\{\s*\}"), "empty catch block"),
]
WARN_PATTERNS = [
    (re.compile(r"\btime\.sleep\(|\bsetTimeout\(|\bawait sleep\("), "sleep or timeout added (hiding a race?)"),
    (re.compile(r"^\s*print\(|console\.log\("), "debug output added"),
]
```

**terminal output (real)**

```bash
$ git diff --cached | python -m tools.fix_gate     # the bad patch
ERROR   web/src/app/s/[token]/page.tsx: source changed but no test file changed: add a regression test
ERROR   web/src/app/s/[token]/page.tsx: empty catch block: } catch (e) {}
ERROR   web/src/app/s/[token]/page.tsx: check silenced: // @ts-ignore
WARNING web/src/app/s/[token]/page.tsx: sleep or timeout added (hiding a race?): await new Promise((r) => setTimeout(r, 500));

3 error(s), 1 warning(s)                            (exit code 1)

$ git diff --cached | python -m tools.fix_gate     # a fix with a regression test
fix gate: no findings                               (exit code 0)
```

> **What the gate cannot do**
>
> It cannot tell whether a fix is **right**, only whether it has the marks of a hasty one. A clean result means "nothing obviously wrong", not "correct". Treat it like a spell checker: it catches a class of mistakes cheaply, and it never replaces reading.


## Regression Tests and Reviewing the Diff Before You Commit › The commit message

Write the commit message as if for the person who will read it during the next outage. State the symptom, the cause and the fix, in that order. Claude Code is good at drafting this once you have verified the facts:

**text  a good bug-fix commit message**

```text
fix(sharing): compare share-link expiry in UTC

Symptom: the public share page raised TypeError (naive vs aware datetime).
Cause: is_expired() used datetime.now() (naive) against a timezone-aware
expires_at from the database.
Fix: use aware UTC, and reject naive input with a ValueError.
Test: test_future_link_is_active_on_a_laptop_in_tokyo (fails without the fix
when TZ is not UTC). Debug log: docs/debug/share-page-error.md
```
