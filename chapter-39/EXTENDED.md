# Chapter 39 — Testing Strategies: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## pytest and Django Tests › Parametrize: one test, many cases

When a rule has many inputs, do not write a loop inside a test, because the first failure hides the rest. `parametrize` makes each case its own test, reported separately, with its own name:

**backend/tests/test_signatures.py (excerpt)**

```
    @pytest.mark.parametrize("age,ok", [(0, True), (299, True), (300, True), (301, False), (-299, True), (-301, False), (86_400, False)],
                             ids=["now", "299s-old", "300s-old", "301s-old", "299s-future", "301s-future", "a-day-old"])
    def test_the_tolerance_window_in_both_directions(self, age, ok):
        h = header(t=NOW - age)
        if ok:
            assert verify_stripe_signature(PAYLOAD, h, [SECRET], now=NOW) == NOW - age
        else:
            with pytest.raises(SignatureError, match="tolerance"):
                verify_stripe_signature(PAYLOAD, h, [SECRET], now=NOW)
```

That one function is seven tests, including both sides of the five-minute boundary: 299 and 300 seconds pass, 301 fails, in the past and in the future. The `ids` give each a readable name in the output (`...[301s-future]`), so a failure tells you which boundary broke.


## pytest and Django Tests › A query budget catches the N+1 problem

**backend/tests_django/test_query_count.py**

```
@pytest.mark.django_db
def test_listing_conversations_does_not_run_a_query_per_row(alice, client_for, django_assert_max_num_queries):
    for _ in range(25):
        c = Conversation.objects.create(user=alice)
        Message.objects.create(conversation=c, role="user", content="hello", status="complete")
    client = client_for(alice)
    with django_assert_max_num_queries(6):          # a fixed budget, however many rows: an N+1 would blow straight through it
        assert client.get("/api/v1/conversations/").status_code == 200
```

Listing 25 conversations with their messages is the classic way to run 26 queries instead of 2. Asserting a **fixed maximum** (`django_assert_max_num_queries`) works however many rows the test creates: an N+1 grows with the rows and blows straight through the budget. `django_assert_num_queries` asserts an exact count, which is stricter and breaks more often.


## pytest and Django Tests › Keeping the suite fast

| **Habit** | **Why it helps** |
|---|---|
| Prefer unit tests that never touch the database | Most of this chapter’s 97 Python tests need no Django at all and run in about 3 seconds in total, including the real HTTP ones |
| `--reuse-db` and `--nomigrations` | Avoids rebuilding the schema on every run (use `--create-db` after a migration change) |
| `pytest -n auto` | Uses every core; requires independent tests |
| A fast password hasher in test settings | Hashing is deliberately slow in production and a major cost in tests that create users |
| Mark slow tests and split them | `pytest -m "not slow"` for the quick local loop, everything in CI |
| Build only the data a test needs | A fixture that creates 1,000 rows for every test is the usual cause of a slow suite |


## Test Doubles, Fake Clocks and a Closed Door to the Internet › The test that cannot call Stripe

Here is a failure that costs real money: a test, written months ago, calls the real payments or AI API, because nobody noticed that a mock was missing. It is slow, it fails when the provider has a bad day, it can create real charges in test mode, and in a CI environment where a live key is present it can spend real money. The defence is not discipline. It is making the mistake impossible: **switch the network off for every test**, and let a test opt in to the one thing it needs.

**backend/testsupport/netblock.py**

```
ALLOWED = {"127.0.0.1", "::1", "localhost"}

class NetworkBlocked(RuntimeError):
    pass

def _host_of(address) -> str:
    return address[0] if isinstance(address, tuple) else str(address)

@contextlib.contextmanager
def block_network(allowed: set[str] | frozenset[str] = frozenset(ALLOWED)):
    real_connect, real_create, real_getaddrinfo = socket.socket.connect, socket.create_connection, socket.getaddrinfo

    def guarded_connect(self, address):
        host = _host_of(address)
        if host not in allowed:
            raise NetworkBlocked(f"test tried to connect to {host}; use a fake instead")
        return real_connect(self, address)

    def guarded_create(address, *a, **k):
        host = _host_of(address)
        if host not in allowed:
            raise NetworkBlocked(f"test tried to connect to {host}; use a fake instead")
        return real_create(address, *a, **k)

    def guarded_getaddrinfo(host, *a, **k):
        if host not in allowed and not str(host).replace(".", "").isdigit():
            raise NetworkBlocked(f"test tried to resolve {host}; use a fake instead")
        return real_getaddrinfo(host, *a, **k)

    socket.socket.connect, socket.create_connection, socket.getaddrinfo = guarded_connect, guarded_create, guarded_getaddrinfo
    try:
        yield
    finally:
        socket.socket.connect, socket.create_connection, socket.getaddrinfo = real_connect, real_create, real_getaddrinfo
```

Anything that tries to connect to a host outside the allow-list raises `NetworkBlocked` with a message naming the host. **Loopback stays open** so a test can start its own server and talk to it, as the real HTTP test in Chapter 39 does. Name resolution is blocked too, so even a lookup of `api.anthropic.com` fails fast. Wiring it in is a three-line `autouse` fixture (shown in 39.4), and then **no test in the project can reach the internet unless it says so out loud.** Its own tests prove all of this, including that the patch is removed afterwards:

**backend/tests/test_netblock.py (excerpt)**

```
def test_the_autouse_fixture_blocks_the_real_internet():
    with pytest.raises(NetworkBlocked, match="api.stripe.com"):
        socket.create_connection(("api.stripe.com", 443), timeout=1)

def test_name_lookups_are_blocked_too():
    with pytest.raises(NetworkBlocked, match="api.anthropic.com"):
        socket.getaddrinfo("api.anthropic.com", 443)
```

> **Contract tests: the one place a live call belongs**
>
> A fake can drift from the real service. Keep a **very small** set of tests marked `@pytest.mark.live` that call the real provider with a throwaway key (Chapter 29’s one-word round trip is the model), excluded from normal runs with `-m "not live"` and executed on a schedule. They catch an SDK upgrade or API change that your fakes would never notice. Everything else stays offline.


## Testing Celery Tasks › Eager mode: useful, and a trap

Setting `CELERY_TASK_ALWAYS_EAGER = True` makes `.delay()` run the task immediately in the calling process, which lets a test call the task and inspect the result. Pair it with `CELERY_TASK_EAGER_PROPAGATES = True`, or an exception inside the task is swallowed into a result object and your test passes while the task is broken.

**backend/tests_django/test_tasks.py**

```
@pytest.fixture(autouse=True)
def eager(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True          # a failing task raises in the test instead of vanishing

@pytest.mark.django_db
def test_refresh_summary_writes_the_summary(alice, monkeypatch):
    from chat.models import Conversation, Message
    conv = Conversation.objects.create(user=alice)
    for i in range(14):
        Message.objects.create(conversation=conv, role="user" if i % 2 == 0 else "assistant", content=f"m{i}", status="complete")

    async def fake_summarize(**kwargs):
        return "They are planning a trip."

    monkeypatch.setattr(ai_tasks, "summarize", fake_summarize)
    monkeypatch.setattr(ai_tasks, "get_client", lambda: object())
    ai_tasks.refresh_summary.apply(args=[conv.pk]).get()
    conv.refresh_from_db()
    assert conv.summary == "They are planning a trip."

@pytest.mark.django_db
def test_a_missing_conversation_raises_instead_of_failing_silently(monkeypatch):
    with pytest.raises(Exception):
        ai_tasks.refresh_summary.apply(args=[999_999]).get()
```

Eager mode is a convenience, **not a faithful simulation.** It does not serialise arguments (so a non-JSON argument that would crash in production works in the test), does not exercise routing or acknowledgements, and does not behave like a real retry with a countdown. Treat it as a way to test the wiring, and keep one slower test, using Celery’s own test worker fixtures, that sends a task through a real broker connection and a real worker in a thread.


## Testing Channels Consumers

A WebSocket consumer is an async class that talks over a long-lived connection. Channels ships a tool for testing one without a browser or a server: the `WebsocketCommunicator`, which connects to your consumer in-process and lets the test send and receive messages.

**backend/tests_django/test_consumers.py**

```
def application():
    return URLRouter([path("ws/chat/<int:conversation_id>/", ChatConsumer.as_asgi())])

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)      # async code runs in another thread: it cannot see an uncommitted test transaction
async def test_an_anonymous_socket_is_refused():
    comm = WebsocketCommunicator(application(), "/ws/chat/1/")
    connected, _ = await comm.connect()
    assert connected is False

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_a_message_gets_streamed_events_back(alice, monkeypatch):
    comm = WebsocketCommunicator(application(), "/ws/chat/1/")
    comm.scope["user"] = alice
    connected, _ = await comm.connect()
    assert connected
    await comm.send_json_to({"text": "hello"})
    first = await comm.receive_json_from(timeout=2)       # always pass a timeout: a hung test is worse than a failed one
    assert first["type"] in {"start", "error"}
    await comm.disconnect()
```

Three details prevent most of the confusion:

- `@pytest.mark.django_db(transaction=True)` is required for async tests that touch the database. The consumer’s database calls run in another thread, which cannot see the uncommitted transaction a normal `django_db` test lives in, so your data would appear to be missing. A transactional test commits for real and is slower, so use it only here.
- **Always pass a** `timeout` to `receive_json_from`. A test that waits forever for a message that never comes hangs your whole pipeline; a test that fails after two seconds tells you what happened.
- **Set** `comm.scope["user"]` before connecting to simulate an authenticated user, and test the anonymous case explicitly: the consumer must refuse an unauthenticated socket (Chapter 17), and nothing else will notice if it does not.
The consumer should stay as thin as the task: it forwards events from the `ChatService`, which is tested without any WebSocket at all (Chapter 29). The communicator tests then only need to prove the connection, authentication and forwarding.

> **Async tests need an async-aware runner**
>
> `pytest-asyncio` provides `@pytest.mark.asyncio`. Without it, pytest collects an `async def` test, never awaits it, and reports a pass with a warning that is easy to miss. If a new async test passes suspiciously on its first run, make it fail on purpose (habit 7 in 39.3) before you believe it.


## Testing Payment Webhooks Locally

A **webhook** is the payment provider calling *your* server to say something happened: a payment succeeded, a subscription was cancelled, a charge was refunded. It is the most important and most dangerous endpoint in the app. It changes what people are entitled to, it is publicly reachable by anyone, and the provider will call it again and again until it gets a success. Nobody can hand you a real customer to test with, so you test it by **being the provider**: building the same signed requests, in the same format, and sending them yourself.

*(figure: see the printed book)*

*Figure 39.3: The five stages of handling a webhook, with the number of tests guarding each. The HTTP status code is the protocol with the provider.*


### What the provider guarantees, and what it does not

| **Property** | **Stripe** | **Paystack** |
|---|---|---|
| How you know it is genuine | `Stripe-Signature` header: `t=<timestamp>,v1=<hex>`; HMAC-SHA256 of `<timestamp>.<raw body>` with your endpoint secret (`whsec_...`) | `x-paystack-signature` header: HMAC-SHA512 of the raw body, keyed with your secret API key |
| Replay protection from the signature | Yes: the timestamp is signed; reject anything outside a tolerance (libraries default to 5 minutes) | **None**: no timestamp is signed, so idempotency is your only defence |
| A unique id per event | Yes: `id`, such as `evt_...` | No top-level id: build one from the event name and `data.id` or `data.reference` |
| Delivery | At least once; retries on a non-2xx response; **order is not guaranteed** | At least once; retries on a non-200 response (test mode retries hourly for a limited period, live mode more often at first); order not guaranteed |
| Several signatures at once | Yes, during secret rotation: more than one `v1` | No |

Read the bottom three rows twice. **At least once** means duplicates are normal, not exceptional. **Order not guaranteed** means a cancellation can arrive before the payment it cancels. Both are properties you must handle, and both are properties no manual click-through test will ever reveal.


### Rule one: verify the exact bytes, before anything else

The signature is computed over the **raw bytes** of the request body. If your framework parses the JSON first and you re-serialise it to check, the spacing, key order or escaping changes, the signature no longer matches, and you spend a day believing the provider is broken. Verify on `request.body` (Django) as received, and only then parse. The same function in the tests signs the **same bytes** it sends:

**backend/testsupport/signing.py**

```
def to_bytes(event: dict) -> bytes:
    """Serialise ONCE and sign THOSE bytes. Re-serialising later would change spacing and break the signature."""
    return json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def stripe_headers(payload: bytes, secret: str, timestamp: int) -> dict[str, str]:
    return {"Content-Type": "application/json",
            "Stripe-Signature": f"t={timestamp},v1={compute_stripe_signature(secret, timestamp, payload)}"}

def paystack_headers(payload: bytes, secret: str) -> dict[str, str]:
    return {"Content-Type": "application/json", "x-paystack-signature": compute_paystack_signature(secret, payload)}

def stripe_event(event_id: str, type_: str, obj: dict) -> dict:
    return {"id": event_id, "object": "event", "type": type_, "data": {"object": obj}}

def paystack_event(event: str, data: dict) -> dict:
    return {"event": event, "data": data}
```


### Verifying Stripe’s signature

**backend/billing/webhooks.py (Stripe)**

```
def verify_stripe_signature(payload: bytes, header: str | None, secrets: Sequence[str], *, now: float,
                            tolerance: int = DEFAULT_TOLERANCE) -> int:
    """
    Header looks like  t=1700000000,v1=<hex>[,v1=<hex>]  . Several v1 values appear while a secret is being
    rotated, so a match against ANY of our secrets is enough. Other schemes (Stripe adds a fake v0 to test
    events) are ignored on purpose: accepting them would let an attacker choose a weaker scheme.
    Returns the signed timestamp.
    """
    if not header:
        raise SignatureError("missing Stripe-Signature header")
    timestamp: int | None = None
    candidates: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                raise SignatureError("timestamp is not a number") from None
        elif key == "v1" and value:
            candidates.append(value)
    if timestamp is None:
        raise SignatureError("no timestamp in header")
    if not candidates:
        raise SignatureError("no v1 signature in header")
    if abs(now - timestamp) > tolerance:                # too old (replay) OR too far in the future (clock trick)
        raise SignatureError("timestamp outside the tolerance window")
    for secret in secrets:
        expected = compute_stripe_signature(secret, timestamp, payload)
        for candidate in candidates:
            if hmac.compare_digest(expected, candidate):   # constant time: no hint about how much matched
                return timestamp
    raise SignatureError("no matching signature")
```

In production you may prefer Stripe’s own library (`stripe.Webhook.construct_event`) for this step. We wrote it by hand here so the tests can sign requests exactly the way Stripe does and prove what happens to each kind of bad one. Whichever you use, know what it does: the code above rejects a missing header, a missing or non-numeric timestamp, a header with no `v1`, a timestamp outside the window **in either direction** (a future timestamp is a trick too), and any signature that does not match any of your secrets. It ignores every scheme except `v1`, because accepting a weaker one would let an attacker pick it. And it compares with `hmac.compare_digest`, which takes the same time however many characters match.


### The tests, and what each one is for

**backend/tests/test_signatures.py (excerpt)**

```
class TestStripe:
    def test_a_correct_signature_is_accepted_and_returns_the_timestamp(self):
        assert verify_stripe_signature(PAYLOAD, header(), [SECRET], now=NOW) == NOW

    @pytest.mark.parametrize("payload", [
        b'{"id":"evt_1","type":"invoice.paid" }',          # one extra space
        b'{"id":"evt_2","type":"invoice.paid"}',           # a different id
        b"",                                               # emptied
    ], ids=["extra-space", "other-id", "empty"])
    def test_any_change_to_the_body_is_rejected(self, payload):
        with pytest.raises(SignatureError, match="no matching signature"):
            verify_stripe_signature(payload, header(), [SECRET], now=NOW)
```

| **Test** | **The attack or accident it stands for** |
|---|---|
| A body changed by one space, a different id, an emptied body | Tampering after signing |
| A changed timestamp in the header | Replaying an old signature with a fresh timestamp |
| 299, 300, 301 seconds, past and future | The boundary of the replay window, both directions |
| `None`, empty, no timestamp, no `v1`, `t=abc` | Malformed or missing headers |
| Two `v1` values; two configured secrets | Secret rotation, which would otherwise cause an outage |
| Only `v0` present | Downgrade to a scheme we do not trust |
| The spy on `compare_digest` | A timing property that cannot be seen from outside (below) |
| The signed string is `timestamp.body` | A refactor quietly changing the scheme |


### Paystack: no timestamp, so idempotency carries the weight

Paystack’s signature is simpler (a SHA-512 HMAC of the body) and, crucially, **contains no timestamp**. A captured, validly signed request is valid forever. You cannot reject it as stale; you can only recognise that you have already processed it. That is what the event key does, and why its tests matter more here than for Stripe:

**backend/billing/webhooks.py (event identity)**

```
def event_key(provider: Provider, event: Mapping) -> str:
    """
    A stable identity for 'this exact event', used to ignore redeliveries.
    Stripe gives every event an id. Paystack events have NO top-level id and its signature carries no timestamp,
    so we build one from the event name plus the transaction's own id (or reference). Idempotency is also
    Paystack's only defence against a replayed delivery.
    """
    if provider == "stripe":
        eid = event.get("id")
        if not isinstance(eid, str) or not eid:
            raise MalformedEvent("stripe event has no id")
        return f"stripe:{eid}"
    data = event.get("data")
    if not isinstance(data, Mapping):
        raise MalformedEvent("paystack event has no data object")
    ident = data.get("id") or data.get("reference")
    if ident in (None, ""):
        raise MalformedEvent("paystack event has neither data.id nor data.reference")
    return f"paystack:{event_type('paystack', event)}:{ident}"
```


### Rule two: process each event once, and never lose one

**backend/billing/webhooks.py (processing)**

```
def process_event(provider: Provider, event: dict, store: IdempotencyStore, handlers: Mapping[str, Handler]) -> Outcome:
    """
    ignored    : an event type we do not handle. Still answered 200, or the provider retries it for days.
    duplicate  : already processed. Answered 200 with no side effects.
    processed  : the handler ran.
    If the handler raises, the claim is released and the error propagates, so the endpoint answers 500, the
    provider redelivers, and the work is attempted again instead of being silently lost.
    """
    handler = handlers.get(event_type(provider, event))
    if handler is None:
        return "ignored"
    key = event_key(provider, event)
    if not store.claim(key):
        return "duplicate"
    try:
        handler(event)
    except Exception:
        store.release(key)
        raise
    return "processed"
```

Read the order of operations, because each line answers a specific failure. An **unknown event type** returns `ignored` without claiming anything: the provider must still get a 200, or it will retry an event we will never handle for days. A **duplicate** is acknowledged and does nothing. A **handler failure releases the claim** and re-raises: the endpoint answers 500, the provider retries, and the work is attempted again instead of being silently lost. Without the `release`, one transient database error would permanently swallow a customer’s payment.

**backend/tests/test_endpoint.py (excerpt)**

```
    def test_a_handler_failure_is_a_500_and_the_redelivery_succeeds_exactly_once(self, deliver, state, handlers, config, store, clock):
        real = handlers["checkout.session.completed"]
        failures = [True]

        def flaky(event):
            if failures:
                failures.pop()
                raise RuntimeError("db unavailable")
            real(event)

        handlers["checkout.session.completed"] = flaky
        assert deliver("stripe", CHECKOUT)[0] == 500
        assert state.credits == {}
        assert deliver("stripe", CHECKOUT) == (200, {"status": "processed"})   # the provider's retry
        assert deliver("stripe", CHECKOUT) == (200, {"status": "duplicate"})
        assert state.credits == {7: 100}
```

> **In production the claim is a database row**
>
> The in-memory store is for tests. In Django, `DbIdempotencyStore` inserts a row into a table with a **UNIQUE constraint** on the event key (it is in the repository, with its model). The database, not Python, decides who was first when two deliveries race on two server processes. Ideally the claim and the handler’s changes commit in **one transaction**, so a crash between them cannot record “processed” without having processed.


### Rule three: never trust what the webhook says was paid

**backend/billing/handlers.py (Paystack)**

```
    def paystack_charge_success(event: dict) -> None:
        data = event["data"]
        order = state.orders.get(data.get("reference", ""))
        if order is None:
            state.flagged.append({"why": "unknown reference", "reference": data.get("reference")})
            return
        if order.status == "paid":                          # belt and braces: idempotent even without the store
            return
        # Never credit what the webhook CLAIMS was paid: compare with what WE asked for.
        if data.get("amount") != order.amount_minor or data.get("currency") != order.currency:
            state.flagged.append({"why": "amount or currency mismatch", "reference": order.reference,
                                  "expected": [order.amount_minor, order.currency],
                                  "got": [data.get("amount"), data.get("currency")]})
            return
        order.status = "paid"
        state.add_credits(order.user_id, order.credits)
```

A correctly signed webhook proves that *Paystack* sent it. It does not prove the amount is the one **you** asked for. The handler therefore compares the amount and currency with the order your server created when the payment was initialised, credits only on an exact match, and flags anything else for a human instead of guessing. It is also safe to run twice for the same order. (Paystack’s own guidance adds a further belt: verify the transaction through its API before fulfilling.) The tests include off-by-one, wrong currency and missing amount, each of which must credit nothing.


### Rule four: do not assume the order

While writing these tests I added a case that failed against my own first draft of the handlers: a cancellation at time 200 arriving *before* a payment event from time 100 would be “corrected” by the late payment, resurrecting a cancelled plan. Providers explicitly do not promise delivery order. The fix is to compare the provider’s own timestamp and never let an older event overwrite a newer decision:

**backend/billing/handlers.py (ordering)**

```
    def set_plan(self, user_id: int, plan: str, created: int) -> bool:
        """Providers do NOT promise delivery order. An older event must never overwrite a newer decision."""
        if created < self.plan_stamp.get(user_id, 0):
            return False
        self.plans[user_id], self.plan_stamp[user_id] = plan, created
        return True
```

**backend/tests/test_handlers.py (excerpt)**

```
    @pytest.mark.parametrize("arrival", ["paid-then-cancelled", "cancelled-then-paid"])
    def test_events_arriving_out_of_order_cannot_resurrect_a_cancelled_plan(self, state, store, handlers, arrival):
        paid = invoice_paid("evt_paid", 7, "pro", created=100)       # happened FIRST, at t=100
        cancelled = sub_deleted("evt_del", 7, created=200)           # happened LAST, at t=200
        in_order = [paid, cancelled] if arrival == "paid-then-cancelled" else [cancelled, paid]   # second: the late 'paid'
        for event in in_order:
            run("stripe", event, store, handlers)
        assert state.plans[7] == "free"                  # the newer decision (cancel, t=200) wins whichever arrived first
```


### The endpoint, as a function you can test without a framework

The decisions (which status to answer, in which order) are a plain function, `handle_webhook_request`, taking bytes and returning a status and a body. The Django view is a handful of lines around it. That is why 15 endpoint tests and a real HTTP test need no Django, and why you can run them in a second:

**backend/billing/endpoint.py**

```
def handle_webhook_request(provider: str, headers: Mapping[str, str], body: bytes, *, config: WebhookConfig,
                           store: IdempotencyStore, handlers: Mapping[str, Handler], now: float) -> tuple[int, dict]:
    if provider not in ("stripe", "paystack"):
        return 404, {"error": "unknown provider"}
    if len(body) > config.max_body_bytes:
        return 413, {"error": "payload too large"}
    h = {k.lower(): v for k, v in headers.items()}       # header names are case-insensitive

    # 1. Authenticate FIRST, on the exact bytes received. Parsing before verifying breaks the signature.
    try:
        if provider == "stripe":
            verify_stripe_signature(body, h.get("stripe-signature"), config.stripe_secrets, now=now, tolerance=config.tolerance)
        else:
            if not config.paystack_secret:
                return 500, {"error": "provider not configured"}
            verify_paystack_signature(body, h.get("x-paystack-signature"), config.paystack_secret)
    except SignatureError as exc:
        logger.warning("webhook rejected", extra={"provider": provider, "reason": str(exc)})   # reason: log it, never return it
        return 400, {"error": "invalid signature"}

    # 2. Only now is the body trusted enough to parse.
    try:
        event = json.loads(body)
        if not isinstance(event, dict):
            raise ValueError("not an object")
    except ValueError:
        return 400, {"error": "malformed payload"}

    # 3. Process once. A failure is a 500 so the provider retries; everything else is a 200.
    try:
        outcome = process_event(provider, event, store, handlers)  # type: ignore[arg-type]
    except MalformedEvent:
        return 400, {"error": "malformed event"}
    except Exception:
        logger.exception("webhook handler failed", extra={"provider": provider})
        return 500, {"error": "handler failed"}
    return 200, {"status": outcome}
```

- **Authenticate first, parse second.** A bad signature is a 400 with the same generic body whatever the reason: the real reason goes to the log, never to the caller, because a precise error is a free oracle for an attacker. A test asserts the body is exactly `{"error": "invalid signature"}`.
- **A handler failure is a 500, on purpose.** That status is how you ask the provider to try again. Returning 200 on failure would lose the event.
- **A body size limit** keeps a hostile, correctly addressed request from making you read a gigabyte.
- `csrf_exempt` **in the Django view is correct here**: the signature is the authentication, and a browser CSRF token cannot apply to a call from a payment provider.

### A real HTTP round trip, with nothing but the standard library

Unit tests prove the logic. One more test layer proves the wiring: a real server on a real socket, receiving a real signed request. The server is a dozen lines of the standard library; the client is the same `send_webhook` script you will use by hand.

**backend/tests/test_http_integration.py (the server)**

```
@pytest.fixture
def server(config, store, handlers):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            provider = self.path.rstrip("/").rsplit("/", 1)[-1]
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))   # the RAW bytes, untouched
            status, payload = handle_webhook_request(provider, dict(self.headers), body, config=config, store=store,
                                                     handlers=handlers, now=time.time())
            out = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args):       # keep test output quiet
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/api/v1/webhooks"
    httpd.shutdown()
    httpd.server_close()
```

**backend/scripts/send_webhook.py (building a request)**

```
def build_request(provider: str, event: dict, secret: str, *, now: float | None = None, age: int = 0,
                  tamper: bool = False) -> tuple[dict[str, str], bytes]:
    body = to_bytes(event)
    if provider == "stripe":
        headers = stripe_headers(body, secret, int((now if now is not None else time.time()) - age))
    elif provider == "paystack":
        headers = paystack_headers(body, secret)
    else:
        raise ValueError("provider must be stripe or paystack")
    if tamper:
        body = body.replace(b"}", b" }", 1)               # one extra space is enough to invalidate a signature
    return headers, body
```

The tests send a signed event and see `processed`, send it again and see `duplicate` (with the credit applied exactly once), tamper with one byte after signing (400), back-date the timestamp an hour (400), sign with the wrong secret (400), and repeat the Paystack delivery. `no_network` is active throughout, and the test still works because loopback is allowed: the suite talks to itself and to nobody else.


### Trying it by hand, locally

Tests prove the code; you also want to see a real provider’s event arrive once. For **Stripe**, the CLI does the hard part:

**Terminal**

```bash
stripe login
stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe/     # prints a whsec_... signing secret for THIS listener
stripe trigger checkout.session.completed                              # in a second terminal: send a sample event
stripe events resend evt_123...                                        # redeliver one: your duplicate test, for real
```

`stripe listen` prints a webhook signing secret that belongs to *that listener*, not to the endpoint you configured in the dashboard. Put it in your local `.env`, and expect a fresh one if you start a new listener. A very common “signature verification failed” is the wrong secret, not a bug.

**Paystack** has no equivalent command-line tool. You have two options. Expose your local server with a tunnel, set that URL as the webhook URL in the dashboard’s test mode, and make a test payment with Paystack’s test cards. Or skip the tunnel and **send the event yourself, correctly signed**, with the script in this bundle, which is also the better way to test the awkward cases:

**Terminal**

```bash
python -m scripts.send_webhook --provider paystack --url http://localhost:8000/api/v1/webhooks/paystack/ \
    --secret sk_test_xxx --event fixtures/charge_success.json --repeat 2      # second delivery must say 'duplicate'
python -m scripts.send_webhook ... --tamper                                 # must be 400
python -m scripts.send_webhook --provider stripe ... --age 3600             # must be 400 (stale)
```

> **Test and live are different worlds**
>
> Stripe’s test and live endpoints have different secrets, and Paystack signs with the secret key of the mode that sent the event. Using a test secret against a live event (or the reverse) fails verification, which is correct behaviour and a frequent surprise on launch day. Keep the two sets of secrets in separate environments, and rehearse the production configuration with a test-mode event before you go live (Chapter 26’s staged rollout applies here too).


### Do your tests actually test anything? Mutation testing

All the tests above pass. That tells you nothing about whether they *would fail* if the code were wrong. The check is blunt and powerful: **break the code on purpose, one small change at a time, and see whether the tests notice.** Each broken copy is a *mutant*. If the suite fails, the mutant is *killed*, which is what you want. If the suite still passes, the mutant *survived*, and you have found a gap.

**backend/tools/mutation_demo.py (the mutants)**

```
MUTANTS = [
    Mutant("M01", "billing/webhooks.py", "abs(now - timestamp) > tolerance", "(now - timestamp) > tolerance", "future timestamps accepted"),
    Mutant("M02", "billing/webhooks.py", "abs(now - timestamp) > tolerance", "abs(now - timestamp) >= tolerance", "off-by-one at the tolerance boundary"),
    Mutant("M03", "billing/webhooks.py", "if abs(now - timestamp) > tolerance:", "if False:", "replay protection removed"),
    Mutant("M04", "billing/webhooks.py", "hmac.compare_digest(expected, candidate)", "expected == candidate", "timing-unsafe comparison (same results!)"),
    Mutant("M05", "billing/webhooks.py", "signed = str(timestamp).encode() + b\".\" + payload", "signed = payload", "timestamp no longer part of what is signed"),
    Mutant("M06", "billing/webhooks.py", 'elif key == "v1" and value:', 'elif key in ("v1", "v0") and value:', "accepts the fake v0 scheme"),
    Mutant("M07", "billing/webhooks.py", "hashlib.sha512", "hashlib.sha256", "Paystack signature downgraded to SHA-256"),
    Mutant("M08", "billing/webhooks.py", "        store.release(key)\n        raise", "        pass\n        raise", "a failed handler keeps its claim, so the retry is skipped"),
    Mutant("M09", "billing/webhooks.py", "if not store.claim(key):\n        return \"duplicate\"", "store.claim(key)", "duplicates are processed again"),
    Mutant("M10", "billing/endpoint.py", 'return 400, {"error": "invalid signature"}', 'return 200, {"error": "invalid signature"}', "bad signatures answered with success"),
    Mutant("M11", "billing/endpoint.py", 'return 400, {"error": "invalid signature"}', 'return 400, {"error": str(exc)}', "the reason for rejection leaks to the caller"),
    Mutant("M12", "billing/endpoint.py", "if len(body) > config.max_body_bytes:", "if False:", "no body size limit"),
    Mutant("M13", "billing/handlers.py", 'data.get("amount") != order.amount_minor or data.get("currency") != order.currency', "False", "amounts and currencies are trusted"),
    Mutant("M14", "billing/handlers.py", "if order.status == \"paid\":", "if False:", "no business-level double-credit guard"),
    Mutant("M15", "billing/handlers.py", "if created < self.plan_stamp.get(user_id, 0):", "if created > self.plan_stamp.get(user_id, 0):", "older events overwrite newer ones"),
    Mutant("M04b", "billing/webhooks.py", "hmac.compare_digest(expected, candidate)", "expected == candidate",
           "same as M04, but with the spy test deleted", drop_tests=["test_the_comparison_is_constant_time"], expect_survive=True),
]
```

`mutation_demo.py` copies the code to a temporary folder, applies each change, and runs the suite against it. This is what it printed when run for this chapter:

**python tools/mutation_demo.py**

```python
id    result    what was broken
M01   killed    future timestamps accepted
M02   killed    off-by-one at the tolerance boundary
M03   killed    replay protection removed
M04   killed    timing-unsafe comparison (same results!)
M05   killed    timestamp no longer part of what is signed
M06   killed    accepts the fake v0 scheme
M07   killed    Paystack signature downgraded to SHA-256
M08   killed    a failed handler keeps its claim, so the retry is skipped
M09   killed    duplicates are processed again
M10   killed    bad signatures answered with success
M11   killed    the reason for rejection leaks to the caller
M12   killed    no body size limit
M13   killed    amounts and currencies are trusted
M14   killed    no business-level double-credit guard
M15   killed    older events overwrite newer ones
M04b  SURVIVED  same as M04, but with the spy test deleted

15 of 16 mutants killed; 1 survived.
```

Look at **M04** and **M04b**. Replacing `hmac.compare_digest` with `==` changes nothing about *what* the function returns; it only makes the comparison leak timing information. No black-box test can tell the difference, so with ordinary tests that mutant **survives**, and M04b proves it by deleting the one test that kills it. That test is the odd one in the signatures file: it replaces `compare_digest` with a spy and asserts the check goes through it. It tests an implementation detail on purpose, because the *property* it guards (constant-time comparison) has no other observable form. The rule: **test behaviour, and pin down by spy only the security properties that have no visible behaviour.**

> **What this does and does not show**
>
> These are sixteen mutants **I chose**, so a clean result proves the suite is sharp against those sixteen changes, not against every possible bug. Real mutation tools (mutmut, cosmic-ray for Python; Stryker for JavaScript) generate thousands automatically and are slow, so teams run them on the code that matters most: here, anything that touches money or authentication. Even sixteen hand-picked mutants are worth running on a payment path before launch.


## Jest and React Testing Library for the Web App › Setup for Next.js

Next.js documents Jest, and Vitest as an alternative, and both work. The recommended Jest route is `next/jest`, which wires up the compiler, CSS and image stubs and `.env` loading for you, so you do not hand-configure a transform:

**Terminal**

```bash
npm install -D jest jest-environment-jsdom @testing-library/react @testing-library/dom \
    @testing-library/jest-dom @testing-library/user-event ts-node @types/jest
```

**web/jest.config.ts**

```
import type { Config } from "jest";
import nextJest from "next/jest.js";

// next/jest wires up the compiler, CSS and image stubs and .env loading for you.
const createJestConfig = nextJest({ dir: "./" });

const config: Config = {
  coverageProvider: "v8",
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  testPathIgnorePatterns: ["<rootDir>/node_modules/", "<rootDir>/e2e/"],    // Playwright specs are NOT Jest tests
};

export default createJestConfig(config);
```

**web/jest.setup.ts**

```
import "@testing-library/jest-dom";
```

Note the line that **excludes** `e2e/`. Playwright specs live in the same repository and look like tests, and Jest will try to run them and fail in confusing ways. Keep the two suites apart on purpose.

> **What Jest cannot test: async Server Components**
>
> The Next.js documentation is explicit that Jest and Vitest do not currently support **async Server Components**. A component that awaits data on the server cannot be unit-tested in jsdom. Test the *logic* it uses as plain functions, and cover the rendered page with a Playwright journey. This is a good reason to keep real logic out of components in the first place.


## Jest and React Testing Library for the Web App › Time and waiting without waiting

After checkout the browser has a problem the server solved elsewhere: the provider tells *your server* the payment succeeded (the webhook), but the app only learns by asking. So the success page polls. Polling code is notorious for slow, flaky tests, because the obvious test waits for real time. The cure is the same as for the signature window: **inject the clock and the sleep.**

**web/lib/checkoutPolling.ts**

```
export async function waitForActivation(fetchStatus: () => Promise<SubscriptionStatus>, opts: PollOptions = {}): Promise<PollResult> {
  const { intervalMs = 1500, timeoutMs = 60_000, maxConsecutiveErrors = 3 } = opts;
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const now = opts.now ?? Date.now;
  const started = now();
  let errors = 0;
  for (;;) {
    try {
      const status = await fetchStatus();
      errors = 0;
      if (status === "active" || status === "failed") return status;
    } catch (err) {
      errors += 1;
      if (errors >= maxConsecutiveErrors) throw err;
    }
    if (now() - started >= timeoutMs) return "timeout";
    await sleep(intervalMs);
  }
}
```

**web/lib/checkoutPolling.test.ts (excerpt)**

```
function fakeTime() {
  let t = 0;
  return { now: () => t, sleep: async (ms: number) => { t += ms; } };
}
const script = (...results: Array<SubscriptionStatus | Error>) => {
  let i = 0;
  return jest.fn(async () => {
    const r = results[Math.min(i++, results.length - 1)];
    if (r instanceof Error) throw r;
    return r;
  });
};

describe("waitForActivation", () => {
  it("returns active as soon as the webhook has landed, without waiting needlessly", async () => {
    const time = fakeTime();
    const fetch = script("pending", "pending", "active");
    expect(await waitForActivation(fetch, { ...time, intervalMs: 1000 })).toBe("active");
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(time.now()).toBe(2000);                       // two sleeps, nothing more
  });
```

`fakeTime` returns a `now` and a `sleep` that simply advance a counter, so a test that “waits” five seconds finishes instantly and **asserts exactly how long it would have waited** (`time.now()` is 2000 after two sleeps). The suite also covers the cases a manual test never hits: a single network blip does not abort polling, three failures in a row do, and a good answer resets the error count.


## Playwright: Real Browser Journeys › Configuration

**web/playwright.config.ts**

```
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,                  // a stray test.only must fail the build, not silently skip the rest
  retries: process.env.CI ? 2 : 0,               // a retry that passes is a FLAKE: it is reported, and it must be fixed
  workers: process.env.CI ? 2 : undefined,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",                     // a full trace of the failing run, without the cost on every run
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-safari", use: { ...devices["iPhone 14"] } },
  ],
  // Start the app for the tests; reuse one you already have running when developing locally.
  webServer: {
    command: process.env.CI ? "npm run build && npm run start" : "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
```

- `webServer` starts your app for the run (`npm run dev` locally, a production build in CI) and reuses one already running when you are developing. `baseURL` then lets tests say `page.goto("/pricing")`.
- `forbidOnly` **in CI** fails the build if someone commits a `test.only`, which would otherwise silently run one test and skip the rest.
- `retries: 2` **in CI is a safety net with a cost.** A test that fails and then passes is reported as *flaky*. Treat that as a bug to fix, not a pass to ignore.
- `trace: "on-first-retry"` records a complete trace (every action, snapshot and network call) only for the run that failed, without slowing every run. Opening it in the trace viewer is the fastest way to understand a CI-only failure.
- **Projects** run the same tests in several browsers and device profiles. Start with Chromium and add the mobile Safari profile when layout matters.

## Playwright: Real Browser Journeys › Rules that keep browser tests trustworthy

1. **Never** `sleep`**.** Wait for a condition: `await expect(...).toHaveText(...)`. A fixed sleep is slow when things are fast and flaky when they are slow.
2. **Reset state before each test** (`beforeEach`), and make each test create what it needs. Tests that depend on each other fail in whatever order the runner picks.
3. **Do not automate someone else’s website.** Stripe’s hosted checkout page and Paystack’s popup are not yours: their markup changes without notice and their anti-fraud systems may block automation. Mock the redirect (as above), or stop the test at the hand-off and cover the return with a delivered webhook.
4. **Log in once, reuse the session.** A setup project signs in through the real form and saves `storageState`; every other test starts already signed in. It makes the suite several times faster and keeps credentials out of each test.
5. **Keep the number small.** Each journey costs seconds and a maintenance burden. Sign-up, first message, purchase, and delete-my-account are the usual four.
6. **Use traces, not screenshots, to debug.**  `npx playwright test --ui` and the trace viewer show the DOM at every step.
**web/e2e/auth.setup.ts**

```
import { expect, test as setup } from "@playwright/test";

// Log in ONCE through the real form, save the browser state, and let every other test start already signed in.
setup("sign in and save the session", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(process.env.E2E_EMAIL!);
  await page.getByLabel("Password").fill(process.env.E2E_PASSWORD!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Your chats" })).toBeVisible();
  await page.context().storageState({ path: "e2e/.auth/user.json" });      // add e2e/.auth to .gitignore
});
```


## Testing the React Native App › Testing a hook: the version gate

Chapter 26’s `useVersionGate` fetches a policy and decides whether the app may run. Its most important property is that it **fails open**: a broken network must not lock people out. That is exactly the kind of rule that is easy to break by accident and invisible until a server outage, so it gets tests:

**mobile/src/release/useVersionGate.test.tsx**

```
import { renderHook, waitFor } from "@testing-library/react-native";

import { useVersionGate } from "./useVersionGate";

jest.mock("expo-application", () => ({ nativeApplicationVersion: "1.2.0" }));
jest.mock("expo-constants", () => ({ __esModule: true, default: { expoConfig: { version: "1.2.0" } } }));

const policy = (over = {}) => ({ min_version: "1.0.0", recommended_version: "1.0.0", store_url: "https://store.example/app", maintenance: false, message: "", ...over });
const respond = (body: unknown, ok = true) => jest.fn().mockResolvedValue({ ok, status: ok ? 200 : 500, json: async () => body });

afterEach(() => { jest.restoreAllMocks(); });

describe("useVersionGate", () => {
  it("blocks an installed version that is below the server's minimum", async () => {
    global.fetch = respond(policy({ min_version: "1.3.0" })) as unknown as typeof fetch;
    const { result } = await renderHook(() => useVersionGate());        // awaiting is harmless where renderHook is synchronous
    await waitFor(() => expect(result.current.checked).toBe(true));
    expect(result.current.state.kind).toBe("blocked");
  });

  it("lets people in when the policy request fails: the gate fails OPEN", async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error("offline")) as unknown as typeof fetch;
    const { result } = await renderHook(() => useVersionGate());
    await waitFor(() => expect(result.current.checked).toBe(true));
    expect(result.current.state.kind).toBe("ok");
  });

  it("lets people in on a server error too", async () => {
    global.fetch = respond({}, false) as unknown as typeof fetch;
    const { result } = await renderHook(() => useVersionGate());
    await waitFor(() => expect(result.current.checked).toBe(true));
    expect(result.current.state.kind).toBe("ok");
  });
});
```

- `jest.mock` **replaces native modules** (`expo-application`, `expo-constants`) with plain objects, so the hook runs in Node with a known installed version.
- `global.fetch` **is replaced** with a stub that resolves, rejects or returns a server error, so every branch of the gate is reachable without a server.
- `await renderHook(...)`**:** recent versions of React Native Testing Library (v14 and later) return a promise from `render` and `renderHook`; awaiting is harmless on versions where they are synchronous, so write it the portable way.
- `waitFor` polls until an asynchronous state change has happened. Never assert immediately after starting an async effect.

## Testing the React Native App › End to end: Maestro

**Maestro** drives the real app on an emulator or simulator from a short YAML flow. It is popular for React Native because a flow reads like the journey it tests and needs no code. Add `testID` props (`chat-input`, `send-button`) to elements that have no unique visible text.

**mobile/.maestro/consent-and-chat.yaml**

```
# One user journey: first launch, accept the AI consent screen, send a message, see a reply.
# Maestro drives the real app on a real emulator or simulator, so keep flows few and about journeys that matter.
appId: com.example.aichat.preview      # use YOUR preview variant's identifier (Chapter 26)
---
- launchApp:
    clearState: true
- assertVisible: "Before you chat"
- tapOn: "I agree"
- assertVisible: "Message"
- tapOn:
    id: "chat-input"
- inputText: "Say hello in five words"
- tapOn:
    id: "send-button"
- assertVisible:
    text: ".+"
    index: 1
    enabled: true
```

Expo’s EAS Workflows can build the app and run Maestro flows on its infrastructure, so an end-to-end check runs on every pull request without anyone owning an emulator farm. The sample workflow in the repository follows Expo’s tutorial, but workflow syntax changes, so **check Expo’s current end-to-end tests tutorial before relying on it**; it is the one file in this chapter that I could only parse, not compare with live documentation.

**mobile/.eas/workflows/e2e-android.yml**

```
# SAMPLE: check Expo's current "end-to-end tests" tutorial for the exact job syntax before relying on this.
name: e2e-android
on:
  pull_request:
    branches: ["main"]
jobs:
  build:
    type: build
    params:
      platform: android
      profile: e2e-test        # add this profile to eas.json: android.buildType "apk", ios.simulator true
  maestro:
    needs: [build]
    type: maestro
    params:
      build_id: ${{ needs.build.outputs.build_id }}
      flow_path: [".maestro/consent-and-chat.yaml", ".maestro/consent-declined.yaml"]
```

> **Devices, simulators and flakiness**
>
> Emulators are slower and flakier than a fast laptop makes them look. Keep flows short (five to ten steps), start each from `clearState: true`, never depend on animation timing, and run the same few flows on a real device before a release. Two or three solid flows beat twenty fragile ones. Chapter 40 covers debugging a crash that only appears on a device.


## Continuous Integration: Running It All › Policies that keep a suite healthy

| **Policy** | **Why** |
|---|---|
| Make the checks **required** before merge | Optional checks are ignored under deadline pressure |
| A failing test is fixed or deleted **within a day** | A permanently red build is a build nobody reads |
| Quarantine a flaky test: move it to a `flaky` group that runs but does not block, with an owner and a date | It keeps the signal clean while you fix it, and the date stops it living there for a year |
| Track the **slowest ten** tests | Suites do not slow down in one step; they slow down a few seconds at a time until nobody runs them locally |
| Run the full suite on `main` after every merge, and the live contract tests nightly | Catches the interactions between two pull requests that each passed alone |
| Treat a retry-then-pass as a **flake report**, not a green tick | Retries hide the very tests you need to fix |
