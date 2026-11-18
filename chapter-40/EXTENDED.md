# Chapter 40 — Debugging Like a Professional: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## The Debugging Mindset › The first question for each symptom

| **Symptom** | **First question** | **First tool** |
|---|---|---|
| **A 500 error** | What is the request id, and what does the traceback say on its last line? | Logs by request id (40.4) |
| **Works locally, fails in production** | What is different: environment variables, data, versions, network, time zone, permissions? | Compare configuration, then logs |
| **It is slow** | Which phase is slow: DNS, connect, server wait or download? | `curl -w` timings (40.9) |
| **It works sometimes** | What varies between runs: timing, data, order, concurrency, time of day? | Repeat it 50 times; look for the pattern |
| **Wrong data on screen** | Where is the data first wrong: database, API response or UI state? | Check each layer from the database outward |
| **Nothing happens** | What is the last place that proves it did happen (a log line, a task id, a row)? | Search for the id in each layer in order |
| **The app crashes** | Is it a JavaScript error or a native crash? | RN DevTools or `adb logcat` (40.8) |


## The Debugging Mindset › Habits that save hours

- **Read the whole error message.** Most people read the first few words and skip the rest. The answer is often in the last line.
- **Distrust your assumptions.** "That function is never called with `None`" is an assumption. Verify it with one line of logging or one breakpoint.
- **Work from the evidence outward.** Start at the exact line that failed and walk backwards to where the bad value came from.
- **Change one thing at a time.** And change it back if it did not help.
- **Keep notes.** When you are three hypotheses deep, a few written lines ("tried X, saw Y") stop you repeating yourself.
- **Explain it aloud.** Describing the problem to a colleague, or to a rubber duck, often reveals the gap in your reasoning before you finish the sentence.
- **Know when to ask.** After about 30 minutes without a new hypothesis, write the problem down as a question: what you expected, what happened, what you tried (Chapter 41 shows how to turn that into a good bug report or AI prompt).
> **The rule that keeps debugging fast**
>
> **Never fix what you cannot reproduce, and never call it fixed until the reproduction passes.** A failing test that turns green is the only honest proof.


## Reading Stack Traces › The anatomy of a Python traceback

**text a Python traceback (annotated)**

```text
Traceback (most recent call last):                       <- the oldest call is at the TOP
  File "/app/chat/services.py", line 88, in send_message   <- your code called ...
    reply = provider.complete(turn.messages)
  File "/app/chat/providers.py", line 14, in complete      <- ... which failed HERE (deepest frame)
    return data["choices"][0]["text"]
KeyError: 'choices'                                      <- WHAT happened: read this line first
```

Read it in this order:

1. **The last line:** the exception type and message. This is *what* happened. `KeyError: 'choices'` means a dictionary had no key named `choices`.
2. **The deepest frame of your own code** (just above the last line, skipping library code): this is *where* it happened. Put your first breakpoint there.
3. **The frames above it:** this is *how* you got there, which tells you who passed the bad value.

## Reading Stack Traces › Chained exceptions: the real cause is often the first one

When code catches an exception and raises another, Python prints both. "The above exception was the direct cause of the following exception" means one was raised **from** the other; "During handling of the above exception, another exception occurred" means a second error happened inside an `except` block. In both cases the **first** exception in the chain usually holds the real problem and the last one is just where it surfaced.

**text a chained traceback (shortened)**

```text
urllib3.exceptions.NewConnectionError: Failed to establish a new connection: [Errno 111] Connection refused

The above exception was the direct cause of the following exception:

core.payments.gateway.GatewayUncertain: ConnectionError
```

The last line says "the gateway was uncertain", which tells you nothing. The first says "connection refused": nobody was listening at that address. Is the URL wrong? Is the service down? Is a Docker network name missing? That is a debuggable question.


## Reading Stack Traces › A tool that reads it for you

Our `traceparse` module parses a traceback, marks frames from `site-packages` and the standard library as library code, and prints the three facts you need: what was raised, the deepest frame of **your** code, and where the chain started.

**python core/debugging/traceparse.py (excerpt)**

```python
@dataclass(frozen=True)
class Frame:
    file: str
    line: int
    func: str
    code: str = ""

    @property
    def is_library(self) -> bool:
        return any(marker in self.file for marker in _LIBRARY_MARKERS)

@dataclass
class ParsedException:
    frames: list[Frame] = field(default_factory=list)
    exc_type: str = ""
    message: str = ""
    link_to_next: str = ""          # "cause" | "context" | "" (this is the final exception)

@dataclass
class Traceback:
    chain: list[ParsedException]    # oldest first; the LAST one is what was finally raised

    @property
    def final(self) -> ParsedException:
        return self.chain[-1]

    @property
    def root(self) -> ParsedException:
        """The first exception in the chain is usually where the real problem started."""
        return self.chain[0]

    def last_app_frame(self, exc: ParsedException | None = None) -> Frame | None:
        """The deepest frame that is YOUR code. This is where to put the first breakpoint."""
        exc = exc or self.final
        return next((f for f in reversed(exc.frames) if not f.is_library), None)

    def summary(self) -> str:
        lines = [f"raised:   {self.final.exc_type}: {self.final.message}"]
        app = self.last_app_frame()
        if app:
            lines.append(f"your code: {app.file}:{app.line} in {app.func}")
            if app.code:
                lines.append(f"           {app.code}")
        if len(self.chain) > 1:
            root_app = self.last_app_frame(self.root)
            lines.append(f"started as: {self.root.exc_type}: {self.root.message}")
            if root_app:
                lines.append(f"            at {root_app.file}:{root_app.line} in {root_app.func}")
        return "\n".join(lines)
```

Here is its output on the chained traceback from Chapter 38’s payment adapter (real output):

**python (real output)**

```python
>>> print(parse_traceback(CHAINED).summary())
raised:   core.payments.gateway.GatewayUncertain: ConnectionError
your code: /app/payments/services.py:22 in begin_checkout
           return start_checkout(repo=repo, router=get_router(), gateways=get_gateways())
started as: urllib3.exceptions.NewConnectionError: Failed to establish a new connection: [Errno 111] Connection refused
            at /app/payments/gateways/paystack_gw.py:31 in _call
```

You do not need this tool to read a traceback. You need it to see **why** the reading order works, and it is a handy script to paste into a log-processing job.


## Reading Stack Traces › JavaScript, React and Next.js errors

| **Error** | **What it usually means** | **First check** |
|---|---|---|
| `Cannot read properties of undefined (reading 'x')` | You used a value before it existed (data not loaded yet, or a wrong path) | Log the parent object; guard with optional chaining; render a loading state |
| `Hydration failed because the server HTML did not match` | Server and browser rendered different output (dates, random values, `window` checks) | Move browser-only values into `useEffect` |
| `Invalid hook call` | Hooks called conditionally, outside a component, or two copies of React | Check hook order; `npm ls react` |
| `Unhandled Promise Rejection` | An `async` call failed and nothing caught it | `try/catch` or `.catch`; check missing `await` |
| `Network request failed` **(React Native)** | The device cannot reach that address | `localhost` means the phone itself (40.9) |
| `Maximum update depth exceeded` | A state update inside an effect that re-triggers itself | Look at the effect’s dependency list |

In the browser, the red error overlay and the **Console** tab show the error and the component stack. In Next.js, remember there are two places to look: **server errors** appear in the terminal that runs `next dev`, **client errors** appear in the browser console. A page that "does nothing" has usually thrown an error in the other place than the one you are looking at.

> **Production traces look different**
>
> In production `DEBUG = False`, so users see a generic 500 page and the traceback exists only in your logs and error tracker. In minified JavaScript the trace shows `index.js:1:48213` instead of your file and line; section 40.8 shows how to turn it back. Never turn `DEBUG` on in production to "see the error": it exposes settings, paths and secrets (Chapter 17).


## Using a Debugger › Debugging inside Docker

A debugger prompt needs a terminal. A container started in the background has none, so `breakpoint()` seems to hang. Two fixes:

- Run the service in the foreground with ports published: `docker compose run --service-ports web`. The prompt appears in your terminal.
- Or attach a real IDE debugger. In VS Code, install `debugpy` in the development image and start the server through it, then use an "Attach" launch configuration with **path mappings** from your repository folder to `/app`:
**python manage.py (development only)**

```python
# at the top of manage.py, only when DEBUGPY is set in your .env.dev
import os
if os.environ.get("DEBUGPY") == "1":
    import debugpy
    debugpy.listen(("0.0.0.0", 5678))      # publish 5678 in docker-compose.dev.yml
    print("Waiting for the debugger to attach...")
    debugpy.wait_for_client()
```

**json .vscode/launch.json**

```json
{
  "version": "0.2.0",
  "configurations": [{
    "name": "Attach to Django in Docker",
    "type": "debugpy", "request": "attach",
    "connect": { "host": "localhost", "port": 5678 },
    "pathMappings": [{ "localRoot": "${workspaceFolder}/backend", "remoteRoot": "/app" }]
  }]
}
```

> **A debug port is a remote-control port**
>
> `debugpy.listen` lets anyone who can reach port 5678 run code inside your container. Use it only in the development compose file, never publish it on a server, and never leave `breakpoint()` or `debugpy` in code that ships (Chapter 17 and Chapter 54).


## Logs: The Evidence That Survives › Where to find logs

| **Where the code runs** | **How to read its logs** |
|---|---|
| **Local** `runserver` | The terminal itself |
| **Docker Compose** | `docker compose logs -f --tail=200 web` (add `worker`, `beat`, `db`) |
| **Dokploy (Chapter 54)** | The application’s **Logs** tab, or `docker service logs` on the server |
| **Celery worker** | `celery -A config worker -l INFO`; the worker’s container logs |
| **Browser** | The Console tab |
| **React Native** | The DevTools Console (`j`); on Android `adb logcat`; on iOS the Xcode console or `log stream` (40.8) |

If the logs are empty when they should not be, check three things first: Python’s output **buffering** (set `PYTHONUNBUFFERED=1` in the container), the **log level** (the logger or handler may be set above INFO) and that the code writes to a logger that **propagates** to your configured handler.


## Logs: The Evidence That Survives › A triage tool

When there are thousands of lines, you want the answer to three questions: which requests failed, which were slow, and what happened **in order** inside the failing one. `logtriage` parses JSON lines (and counts, rather than silently drops, the lines that were not JSON), groups them by request id, and finds the first error.

**python core/debugging/logtriage.py (excerpt)**

```python
@dataclass
class Entry:
    time: str
    level: str
    event: str
    request_id: str
    fields: dict
    message: str = ""

@dataclass
class Timeline:
    request_id: str
    entries: list[Entry] = field(default_factory=list)

    @property
    def first_error(self) -> Entry | None:
        return next((e for e in self.entries if LEVELS.get(e.level, 0) >= 40), None)

    @property
    def duration_ms(self) -> float | None:
        values = [e.fields.get("duration_ms") for e in self.entries if "duration_ms" in e.fields]
        return max(values) if values else None

def parse_lines(lines) -> tuple[list[Entry], int]:
    """Returns entries and the number of lines that were not JSON (kept honest, never silently dropped)."""
    entries, skipped = [], 0
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            skipped += 1
            continue
        entries.append(Entry(str(data.get("time", "")), str(data.get("level", "INFO")).upper(), str(data.get("event", "")),
                             str(data.get("request_id", "-")), data.get("fields") or {}, str(data.get("message", ""))))
    return entries, skipped

def timelines(entries: list[Entry]) -> dict[str, Timeline]:
    grouped: dict[str, Timeline] = defaultdict(lambda: Timeline(""))
    for e in sorted(entries, key=lambda e: e.time):
        t = grouped[e.request_id]
        t.request_id = e.request_id
        t.entries.append(e)
    return dict(grouped)

def triage(lines, *, slow_ms: float = 1000.0) -> dict:
    entries, skipped = parse_lines(lines)
    tl = timelines(entries)
    failing = {rid: t for rid, t in tl.items() if t.first_error}
    slow = {rid: t for rid, t in tl.items() if (t.duration_ms or 0) >= slow_ms}
    return {
        "requests": len(tl), "skipped_non_json": skipped,
        "failing": sorted(failing), "slow": sorted(slow, key=lambda r: -(slow[r].duration_ms or 0)),
        "timelines": tl,
    }

def render(timeline: Timeline) -> str:
    rows = [f"request {timeline.request_id}"]
    for e in timeline.entries:
        extra = " ".join(f"{k}={v}" for k, v in e.fields.items())
        rows.append(f"  {e.time}  {e.level:<7} {e.event:<22} {extra}")
    return "\n".join(rows)
```

On a sample of three requests and one stray traceback line (real output):

**python (real output)**

```python
>>> result = triage(lines)
>>> {k: v for k, v in result.items() if k != "timelines"}
{'requests': 3, 'skipped_non_json': 1, 'failing': ['r1'], 'slow': ['r1', 'r3']}
>>> print(render(result["timelines"]["r1"]))
request r1
  2026-11-06T10:00:00.100Z  INFO    request_started        path=/api/v1/chat/
  2026-11-06T10:00:00.300Z  INFO    turn_prepared          redactions=2
  2026-11-06T10:00:02.900Z  ERROR   provider_timeout       provider=x
  2026-11-06T10:00:03.000Z  INFO    request_finished       status=503 duration_ms=2900
```

From the terminal, the same tool runs on a log file or a pipe, and exits non-zero when it finds a failing request, so you can also use it in a script (real output):

**bash terminal**

```bash
python -m core.debugging.logtriage < web.log
3 requests, 1 failing, 2 slow, 1 non-JSON lines skipped

request r1
  2026-11-06T10:00:00.100Z  INFO    request_started        path=/api/v1/chat/
  ...
```

The timeline tells the story in four lines: the request arrived, the message was prepared, the model provider took 2.6 seconds and timed out, and the user got a 503. No guessing, no reproduction needed.


## Debugging Async Code › More async traps

| **Trap** | **Symptom** | **Fix** |
|---|---|---|
| **A task created and not kept** (`asyncio.create_task(f())` with no reference) | The task may be garbage-collected mid-run; its exception disappears (`Task exception was never retrieved`) | Keep a reference; add a done-callback that logs exceptions |
| **Django ORM in async code** | `SynchronousOnlyOperation` | Use `database_sync_to_async` (Channels) or the async ORM methods (`await Model.objects.aget(...)`) |
| **Shared state across** `await` **points** | Two requests interleave and corrupt a value | Treat every `await` as "anything can happen now"; use locks or per-request state |
| **No timeout on an awaited call** | One slow provider freezes a request forever | `asyncio.timeout(10)` (Python 3.11+) or the client’s own timeout |
| **Cancelled tasks swallowed** | The app will not shut down cleanly | Never catch `CancelledError` without re-raising it |

When an async program seems stuck, ask "what is every task waiting on?" The helper `describe_tasks()` lists them; call it from a debug endpoint (admin only) or a signal handler:

**python core/debugging/asyncdebug.py (excerpt)**

```python
def describe_tasks(limit: int = 20) -> list[str]:
    """What is every task doing right now? Call this from a debug endpoint or a signal handler."""
    rows = []
    for task in list(asyncio.all_tasks())[:limit]:
        stack = task.get_stack(limit=1)
        where = f"{stack[0].f_code.co_filename.rsplit('/', 1)[-1]}:{stack[0].f_lineno}" if stack else "?"
        state = "done" if task.done() else "pending"
        rows.append(f"{task.get_name():<14} {state:<8} {task.get_coro().__qualname__:<24} at {where}")
    return rows
```


## Debugging Async Code › The same two bugs in JavaScript

- **A missing** `await` gives you a pending `Promise` where you expected a value (`[object Promise]` on screen, or `undefined` properties).
- **Out-of-order responses.** A user types fast, requests 1 and 2 are sent, response 2 arrives first, then response 1 overwrites it with stale data. Cancel the old request with `AbortController` (or use TanStack Query, which handles it).
- **React Strict Mode runs effects twice in development**, on purpose, to reveal effects that are not safe to repeat. If a request fires twice locally, check that production does not, then make the effect idempotent or cancel it in the cleanup function.
- **Stale closures**: a callback captured an old state value. Use the functional form `setX(prev => ...)` or add the value to the dependency list.

## Debugging WebSockets and Django Channels › Close codes tell you who gave up and why

| **Code** | **Meaning** | **Where to look** |
|---|---|---|
| **1000** | Normal closure | Nothing to fix |
| **1001** | Going away (tab closed, server restarting) | A deploy restarted the server; clients should reconnect |
| **1006** | Abnormal closure: no close frame was received | The connection dropped: proxy timeout, network change, server crash, or the app was suspended |
| **1008** | Policy violation | Your own check rejected it (origin, auth) |
| **1011** | Server error | An exception in the consumer; read the server log |
| **4000 to 4999** | Application-defined | Whatever your consumer sends, for example 4401 for "not authenticated" |


## Debugging Mobile Crashes › Release builds: minified stack traces

In a release build, JavaScript is bundled and minified, so a crash report reads `at a (index.android.bundle:1:48213)`. A **source map**, generated during the build, maps that position back to your original file, line and column. The decoder below is a complete, small implementation of source map version 3 (the format Metro and every bundler use). Its tests build a map with their own encoder and prove the round trip.

**python core/debugging/sourcemap.py (excerpt)**

```python
def decode_vlq(segment: str) -> list[int]:
    values, shift, value = [], 0, 0
    for char in segment:
        digit = _B64_INDEX[char]
        value += (digit & 31) << shift
        if digit & 32:                      # continuation bit
            shift += 5
        else:
            values.append(-(value >> 1) if value & 1 else value >> 1)
            shift = value = 0
    return values

    def lookup(self, line: int, column: int) -> Position | None:
        """line is 1-based, column 0-based, as in a minified stack trace."""
        if not 1 <= line <= len(self._lines):
            return None
        segments = self._lines[line - 1]
        if not segments:
            return None
        idx = bisect.bisect_right([s[0] for s in segments], column) - 1
        if idx < 0:
            return None
        _, src, orig_line, orig_col, name = segments[idx]
        return Position(self.sources[src], orig_line + 1, orig_col, self.names[name] if name is not None else None)

def symbolicate(stack: str, maps: dict[str, SourceMap]) -> list[str]:
    """Rewrite each 'at fn (bundle.js:1:2345)' line using the map for that bundle. Unknown frames are kept."""
    out = []
    for raw in stack.splitlines():
        loc = _JS_LOC.search(raw)
        if not loc:
            out.append(raw)
            continue
        bundle = loc["file"].rsplit("/", 1)[-1].split("?")[0]
        smap = maps.get(bundle)
        pos = smap.lookup(int(loc["line"]), int(loc["col"])) if smap else None
        if pos is None:
            out.append(raw)
            continue
        func_match = _JS_FUNC.match(raw)
        func = pos.name or (func_match.group(1) if func_match else "") or "<anonymous>"
        out.append(f"at {func} ({pos.source}:{pos.line}:{pos.column})")
    return out
```

Real output, symbolicating two Hermes-style frames against a test map:

**python (real output)**

```python
>>> stack = """    at a (address at index.android.bundle:1:130)
...     at b (http://10.0.2.2:8081/index.android.bundle?platform=android:1:305)"""
>>> symbolicate(stack, maps)
['at sendMessage (src/chat.ts:42:4)', 'at b (src/api.ts:10:2)']
```

In practice you do not run this by hand: you upload the source maps for each release to your crash-reporting service (Sentry and similar tools do this for React Native and Expo) and it symbolicates every report for you. The rule that matters: **the source map must be the one generated by the same build as the bundle that crashed**. A map from yesterday’s build points at the wrong lines.


## Debugging the Network › `curl -v` and `curl -w`

**bash terminal**

```bash
# the full conversation: DNS, TCP, TLS, request headers, response headers
curl -v https://api.example.com/api/v1/health/

# timings for each phase of one request
curl -s -o /dev/null -w "dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} ttfb=%{time_starttransfer} total=%{time_total} code=%{http_code} size=%{size_download}\n" https://api.example.com/api/v1/health/
```

`curl` reports **cumulative** times (each number includes the ones before it), which is easy to misread. The `nettiming` module subtracts them to get the time spent **in** each phase and says which one to blame. This is real output for a request whose server took two seconds to answer:

**python core/debugging/nettiming.py (excerpt)**

```python
@dataclass(frozen=True)
class Timing:
    dns: float
    connect: float       # cumulative, as curl reports it
    tls: float
    ttfb: float
    total: float
    code: int
    size: int

    @classmethod
    def parse(cls, line: str) -> "Timing":
        kv = dict(part.split("=", 1) for part in line.split())
        return cls(float(kv["dns"]), float(kv["connect"]), float(kv["tls"]), float(kv["ttfb"]),
                   float(kv["total"]), int(kv["code"]), int(float(kv["size"])))

    def phases(self) -> dict[str, float]:
        """curl reports cumulative times; subtract to get the time spent IN each phase (seconds)."""
        tls_start = max(self.connect, 0.0)
        return {
            "dns": self.dns,
            "tcp_connect": max(self.connect - self.dns, 0.0),
            "tls_handshake": max(self.tls - self.connect, 0.0) if self.tls else 0.0,
            "server_wait": max(self.ttfb - (self.tls or tls_start), 0.0),
            "download": max(self.total - self.ttfb, 0.0),
        }

def diagnose(t: Timing, *, slow: float = 1.0) -> list[str]:
    p = t.phases()
    notes = []
    if t.code == 0:
        notes.append("no HTTP response: DNS, connection or TLS failed before the server answered")
    if p["dns"] > 0.2:
        notes.append(f"DNS took {p['dns']:.2f}s: resolver or record problem")
    if p["tcp_connect"] > 0.5:
        notes.append(f"TCP connect took {p['tcp_connect']:.2f}s: firewall, wrong region or overloaded host")
    if p["tls_handshake"] > 0.5:
        notes.append(f"TLS handshake took {p['tls_handshake']:.2f}s: certificate chain or CPU-starved proxy")
    if p["server_wait"] > slow:
        notes.append(f"server_wait {p['server_wait']:.2f}s: the app or database is slow, not the network (look at logs and queries)")
    if p["download"] > slow and t.size > 0:
        notes.append(f"download took {p['download']:.2f}s for {t.size:,} bytes: payload too large or slow link; try compression or pagination")
    if t.code >= 500:
        notes.append(f"HTTP {t.code}: a server error; find the request id in the logs")
    elif t.code in (401, 403):
        notes.append(f"HTTP {t.code}: authentication or permission, not a network problem")
    return notes or ["no obvious problem in the timings"]
```

**python (real output)**

```python
>>> t = Timing.parse("dns=0.020 connect=0.080 tls=0.200 ttfb=2.300 total=2.400 code=200 size=1500")
>>> {k: round(v, 2) for k, v in t.phases().items()}
{'dns': 0.02, 'tcp_connect': 0.06, 'tls_handshake': 0.12, 'server_wait': 2.1, 'download': 0.1}
>>> diagnose(t)
['server_wait 2.10s: the app or database is slow, not the network (look at logs and queries)']
```

Two seconds of "server wait" with fast DNS, connect and TLS means the **network is fine** and the time went inside your application: go to the logs (40.4) and the queries (40.10). Without this step teams spend days blaming the network, the CDN or the cloud provider.


## Debugging the Network › Other network tools

| **Question** | **Tool** |
|---|---|
| **Does the name resolve, and to what?** | `dig api.example.com` or `nslookup`; a stale DNS record after a server move is common |
| **Is the certificate valid and complete?** | `openssl s_client -connect api.example.com:443 -servername api.example.com` (check the chain and expiry) |
| **Is the port open?** | `nc -vz host 5432`, from the machine that needs to connect (often a different network from yours) |
| **What did the browser really send?** | DevTools Network, **Copy as cURL**; a HAR export to share with a teammate (remove tokens first) |
| **What is the phone sending?** | A debugging proxy such as mitmproxy or Charles with the phone’s proxy setting (for development builds only) |
| **Inside Docker: why can the web container not reach** `db`**?** | `docker compose exec web sh`, then `getent hosts db` and `nc -vz db 5432`; use service names, not `localhost` |


## Debugging the Network › HTTP status codes: where to look first

| **Status** | **First suspect** |
|---|---|
| **400** | The request body or query is malformed: compare with the serializer and its error message |
| **401 / 403** | Missing or expired token, or a permission rule; not a network problem |
| **404** | Wrong URL or version prefix, a trailing slash, or the object belongs to another user (Chapter 17 hides it as 404) |
| **405** | Right URL, wrong method |
| **413** | Request larger than the proxy or app limit (file uploads) |
| **429** | A rate limit worked: check which throttle scope |
| **500** | An unhandled exception: request id, then traceback |
| **502 / 504** | The proxy could not reach the app, or the app was too slow: is the container up, does the health check pass, is the proxy timeout shorter than the slowest request? |


## Debugging the Database › See the queries

In development, Django can print every query. Add this logger to your development settings (it only logs while `DEBUG = True`):

**python config/settings_dev.py (syntax-checked only)**

```python
LOGGING["loggers"]["django.db.backends"] = {"handlers": ["console"], "level": "DEBUG"}
```

In a test or a shell, capture the queries of one operation:

**python terminal: python manage.py shell (expected shape, not captured)**

```python
from django.db import connection
from django.test.utils import CaptureQueriesContext

with CaptureQueriesContext(connection) as ctx:
    list_conversations(user)             # the code under suspicion
print(len(ctx), "queries")
for q in ctx.captured_queries[:5]:
    print(q["time"], q["sql"][:100])
```


## Debugging the Database › Too many queries: the N+1 problem

The classic bug: one query loads 50 conversations, then the code touches `conversation.messages` for each, running 50 more queries. A page that should take 2 queries takes 51. It is invisible with 3 rows of test data and ruinous with 3,000 rows in production. This is lab bug 4.

The detector below turns a list of SQL strings into a fingerprint (numbers and strings replaced by `#`) and counts repeats:

**python core/debugging/sqlcheck.py (excerpt)**

```python
def fingerprint(sql: str) -> str:
    """Same query shape, different values, gives the same fingerprint."""
    s = _STRING.sub("#", sql)
    s = _NUMBER.sub("#", s)
    s = _PARAM.sub("#", s)
    s = re.sub(r"\bIN\s*\((?:\s*#\s*,?)+\)", "IN (#)", s, flags=re.I)
    return _SPACE.sub(" ", s).strip().lower()

def find_repeats(queries: list[str], *, threshold: int = 5) -> list[Repeat]:
    counts = Counter(fingerprint(q) for q in queries)
    return [Repeat(fp, n) for fp, n in counts.most_common() if n >= threshold]

def verdict(queries: list[str], *, budget: int, threshold: int = 5) -> str:
    repeats = find_repeats(queries, threshold=threshold)
    if repeats:
        top = repeats[0]
        return f"N+1 suspected: {top.count} x  {top.fingerprint[:90]}"
    if len(queries) > budget:
        return f"over budget: {len(queries)} queries, expected at most {budget}"
    return "ok"
```

**python (real output)**

```python
>>> queries = ["SELECT * FROM conversation"] + [f"SELECT * FROM message WHERE conversation_id = {i}" for i in range(30)]
>>> verdict(queries, budget=5)
'N+1 suspected: 30 x  select * from message where conversation_id = #'
```

**Fix it with the ORM:**  `select_related("user")` follows a foreign key in the same query (a SQL JOIN); `prefetch_related("messages")` runs one extra query for all the related rows and joins them in Python.

**python chat/selectors.py (the fix, syntax-checked only)**

```python
def conversations_for_list(user):
    return (Conversation.objects.filter(user=user)
            .select_related("user")
            .prefetch_related(Prefetch("messages", queryset=Message.objects.order_by("-created_at")[:1]))
            .order_by("-updated_at")[:50])
```

**Then lock it in with a test** so nobody reintroduces it. Django’s `assertNumQueries` fails the test when the count changes:

**python chat/tests/test_queries.py (syntax-checked only)**

```python
def test_conversation_list_uses_a_constant_number_of_queries(self):
    for i in range(30):
        make_conversation_with_messages(self.user, n=3)
    with self.assertNumQueries(3):                       # count, user, prefetch: the same for 3 rows or 3,000
        list(conversations_for_list(self.user))
```


## Debugging the Database › One slow query: read the plan

Ask PostgreSQL how it ran the query: prefix it with `EXPLAIN (ANALYZE, BUFFERS)` and read the result **from the innermost, most indented node outwards**. The numbers to compare are `rows=` (the planner’s estimate) and `actual ... rows=` (reality), the node type (`Seq Scan` reads the whole table; `Index Scan` uses an index), `loops=` and the execution time. `plancheck` flags the usual suspects. Here is a sample plan written in PostgreSQL’s real format for a query that fetches one conversation’s messages from a table with a million rows and no index on `conversation_id`:

**text sample EXPLAIN ANALYZE output**

```text
Seq Scan on chat_message  (cost=0.00..18334.00 rows=1 width=120) (actual time=0.012..95.331 rows=40000 loops=1)
  Filter: (conversation_id = 42)
  Rows Removed by Filter: 960000
Planning Time: 0.110 ms
Execution Time: 1234.500 ms
```

**python core/debugging/plancheck.py (excerpt)**

```python
@dataclass(frozen=True)
class Finding:
    severity: str      # "high" | "medium" | "info"
    node: str
    message: str

def analyze(plan: str, *, seq_scan_rows: int = 10_000, misestimate_factor: float = 10.0) -> list[Finding]:
    findings: list[Finding] = []
    for line in plan.splitlines():
        m = _NODE.match(line)
        if m and m["act"] is not None:
            node, table = m["node"].strip(), m["table"] or ""
            est, act, loops = int(m["est"]), int(m["act"]), int(m["loops"])
            total_rows = act * loops
            if node == "Seq Scan" and total_rows >= seq_scan_rows:
                findings.append(Finding("high", f"Seq Scan on {table}",
                                        f"read {total_rows:,} rows with no index; check the WHERE columns and add an index"))
            if node == "Seq Scan" and "Rows Removed by Filter" in plan and total_rows < 100:
                findings.append(Finding("high", f"Seq Scan on {table}", "scans the table to return a few rows: a missing index"))
            if max(est, 1) / max(act, 1) >= misestimate_factor or max(act, 1) / max(est, 1) >= misestimate_factor:
                findings.append(Finding("medium", f"{node} {table}".strip(),
                                        f"planner expected {est:,} rows but got {act:,}: run ANALYZE, check statistics"))
            if node == "Nested Loop" and loops == 1 and act >= 100_000:
                findings.append(Finding("medium", "Nested Loop", f"produced {act:,} rows; a hash or merge join may suit better"))
            if loops >= 1000:
                findings.append(Finding("high", f"{node} {table}".strip(), f"executed {loops:,} times: an N+1 inside the database"))
        if "Sort Method: external" in line:
            findings.append(Finding("medium", "Sort", "spilled to disk: raise work_mem for this query or add an index that gives the order"))
        if re.search(r"Rows Removed by Filter: (\d+)", line):
            removed = int(re.search(r"Rows Removed by Filter: (\d+)", line).group(1))
            if removed >= 100_000:
                findings.append(Finding("medium", "Filter", f"threw away {removed:,} rows after reading them: an index on the filter column would avoid that"))
    t = re.search(r"Execution Time: ([\d.]+) ms", plan)
    if t and float(t.group(1)) >= 1000:
        findings.append(Finding("info", "Total", f"execution took {float(t.group(1)):,.0f} ms"))
    return findings
```

**python (real output)**

```python
>>> for f in analyze(SEQ):
...     print(f.severity, "|", f.node, "|", f.message)
high | Seq Scan on chat_message | read 40,000 rows with no index; check the WHERE columns and add an index
medium | Seq Scan chat_message | planner expected 1 rows but got 40,000: run ANALYZE, check statistics
medium | Filter | threw away 960,000 rows after reading them: an index on the filter column would avoid that
info | Total | execution took 1,234 ms
```

The fix is an index on the filtered column. On a live table, create it without blocking writes, in a migration that Django marks as non-atomic:

**python chat/migrations/0012_message_conversation_idx.py (syntax-checked only)**

```python
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models

class Migration(migrations.Migration):
    atomic = False                                    # CONCURRENTLY cannot run inside a transaction
    dependencies = [("chat", "0011_previous")]
    operations = [AddIndexConcurrently(
        "message", models.Index(fields=["conversation", "-created_at"], name="msg_conv_created_idx"))]
```

The order of columns in a composite index matters: it serves queries that filter on the **leading** column(s). Re-run `EXPLAIN` after adding it: `Index Scan using msg_conv_created_idx` and an execution time near a millisecond is your proof.

> **Never debug by running writes on the production database**
>
> Investigate with `SELECT`. If you must change data, first run the `SELECT` that shows exactly which rows will change, then use `BEGIN; UPDATE ...; SELECT ...;` and only `COMMIT` when the result is right (`ROLLBACK` otherwise). Better still: reproduce on a restored backup or a sanitized copy (Chapter 34).


## Debugging the Database › Waiting: locks, long transactions and connections

If queries are fast in isolation but requests hang, something is **waiting**. These PostgreSQL queries show who is doing what and who is blocked by whom (run them as a read-only administrative user):

**sql psql**

```sql
-- what is running, how long, and what is it waiting for?
SELECT pid, state, wait_event_type, wait_event, now() - query_start AS running_for, left(query, 80) AS query
FROM pg_stat_activity
WHERE datname = current_database() AND state <> 'idle'
ORDER BY query_start;

-- who is blocked, and by which process?
SELECT pid, pg_blocking_pids(pid) AS blocked_by, left(query, 80) AS query
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
```

| **Symptom** | **Likely cause** | **Fix** |
|---|---|---|
| **Requests hang,** `pg_blocking_pids` **shows a blocker** | A long transaction holds a row lock (a `select_for_update` that is never released, a task that opened a transaction and waits on an HTTP call) | Keep transactions short; never make a network call inside `transaction.atomic()` |
| `idle in transaction` **sessions pile up** | Code started a transaction and never finished (an exception path, a forgotten commit) | Fix the code path; set `idle_in_transaction_session_timeout` as a safety net |
| `FATAL: sorry, too many clients already` | More connections than `max_connections`: many workers, each holding connections | Use a connection pooler (PgBouncer) or fewer workers; set `CONN_MAX_AGE` deliberately |
| **Deadlock detected** | Two transactions lock the same rows in opposite orders | Always lock in a consistent order; retry the transaction |
| `makemigrations` **or** `migrate` **conflicts** | Two branches created migration `0011` | `python manage.py makemigrations --merge`; look at `showmigrations` and `sqlmigrate app 0012` |
| **A migration runs for hours and blocks writes** | `ALTER TABLE` with a table rewrite or lock on a large table | Add nullable columns first, backfill in batches, create indexes concurrently |


## The Hard Ones: Intermittent Bugs and Regressions › `git bisect`: the bug that used to work

If something worked last week and is broken now, the cause is one of the commits in between, and Git can find it by binary search: 100 commits take about 7 steps. You give it a known-good commit, a known-bad commit and a command that exits 0 for good and non-zero for bad (a test is perfect). Here is a real session in a throwaway repository, where a "refactor" quietly changed 7.5% tax to 7%:

**bash terminal**

```bash
git bisect start HEAD <first-good-commit>
git bisect run python3 check.py
```

**output git bisect run (real output)**

```text
[12a2840ac88da39c3246e56e9db923ce54b3312d] change 7: refactor tax constant
[ee2bfab2e3ff9a7a35218811533ed186e7dad504] change 6
12a2840ac88da39c3246e56e9db923ce54b3312d is the first bad commit
commit 12a2840ac88da39c3246e56e9db923ce54b3312d
Author: t <a@b.c>
Date:   Fri Nov 6 19:24:49 2026 +0000

    change 7: refactor tax constant
```

**app.py | 2 +-**

```
 1 file changed, 1 insertion(+), 1 deletion(-)
bisect found first bad commit
```

Out of 10 commits, `git bisect` pointed at "change 7: refactor tax constant" without anyone reading the other nine. Finish with `git bisect reset` to return to your branch. The technique only works if each commit builds and the test is reliable, which is another argument for small commits and a test that runs fast.


## Debugging in Production

Debugging production is different because **you cannot stop it, you must not break it, and you often cannot reproduce it.** The rules:

- **Observe before you touch.** Logs, metrics, traces and the error tracker first. Read-only database access second. Changes last.
- **Use an error tracker** (such as Sentry) for backend, web and mobile. Each error arrives with a stack trace, the release it came from, the user’s public id and breadcrumbs, grouped so 5,000 occurrences are one issue. **Scrub personal data before it leaves** (Chapter 34): turn off default request-body capture and configure the redaction rules.
- **Tag releases.** Every deploy gets a version; every error report carries it. "It started in release 1.8.3" is half a diagnosis, and it tells `git bisect` where to begin.
- **Never attach a debugger to a live web worker.** A paused worker serves nobody. Reproduce locally with the same version, the same configuration and a sanitized copy of the data.
- **Roll back first, investigate second.** If a release is clearly broken, restore service (Chapter 54), then debug in peace.
- **Use feature flags** to switch off the new behaviour without a deploy, and **kill switches** for risky integrations (the gateway circuit breaker of Chapter 38 is one).
- **Write it down** while it is fresh. A short, blameless post-mortem: what happened, the timeline, the root cause, why it was not caught, and what changes (a test, an alert, a runbook). The goal is that this class of bug cannot return silently.
| **Post-mortem section** | **Question it answers** |
|---|---|
| **Summary and impact** | What broke, for whom, for how long? |
| **Timeline** | When was it introduced, detected, mitigated, resolved? (Use request ids and release tags.) |
| **Root cause** | Why did it happen, in one paragraph with no names? |
| **Detection** | Who noticed, and how? Could an alert have caught it sooner? |
| **Fix and prevention** | The code change, the new test, the new alert |
| **What went well, what did not** | Honest lessons for the team |
