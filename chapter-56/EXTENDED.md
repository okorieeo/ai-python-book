# Chapter 56 — Project 1: AI Chat Assistant SaaS: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## What we deliberately leave out

A first version is defined as much by what it skips. These are real features you will want later, and each has a home in the book: password reset and social login (Chapter 13), file attachments (Chapters 16 and 32), tools and agents (Chapter 30), document search (Project 2, Chapter 57), evaluations and cost dashboards (Chapter 33), a Markdown renderer for answers (Chapter 21), and in-app purchases on iOS and Android. On that last point, **read the current App Store and Google Play rules before shipping a paid mobile app**. The rules about selling digital subscriptions differ by country and change often, and they decide whether the Upgrade button on the mobile screen may open a web checkout at all.

> **The rule that keeps capstones finishing**
>
> **Build the thinnest version that works end to end, then thicken it.** A chat that streams a fake model's answer, saves it and counts it is worth more on day one than a perfect memory system with no UI. That is why this chapter builds a `FakeProvider` before it touches the real model: every other part can be built and tested without a key, without network and without spending money.

The architecture is the one from Chapter 6, with each box filled in. Read it left to right: clients talk to Django over HTTPS for ordinary requests and over a WebSocket for chat; Django talks to PostgreSQL, Redis and the model provider; the payment gateways talk back through signed webhooks.

*(figure: see the printed book)*


## The order we build in

Build in dependency order and run the tests after every step. Each step ends with something you can check.

| **Step** | **Build** | **You can check that** |
|---|---|---|
| 1 | Accounts and the WebSocket ticket | You can register, log in and get a ticket |
| 2 | Chat data model and usage ledger | Migrations apply |
| 3 | AI provider layer | A fake and a mocked real provider both stream |
| 4 | Memory builder and summary task | Old messages become a summary |
| 5 | Turn services and quotas | The fourth free message is refused |
| 6 | The Channels consumer | A socket streams a reply and saves it |
| 7 | Plans and entitlements | Pro users get the Pro limit |
| 8 | Gateways and webhooks | A signed event upgrades a user, a replay changes nothing |
| 9 | Web and mobile clients | The UI streams, stops, reconnects and upgrades |

Chapter 13 built authentication in full; this project needs the smallest correct version. Three decisions matter.

**Log in with email, not username.** The custom user sets `USERNAME_FIELD = "email"`, lower-cases the address when it creates the account, and keeps a `public_id` UUID that is the only id ever shown to clients or sent to payment gateways. An internal integer id never leaves the server.

**accounts/models.py**

```
class User(AbstractUser):
    """Email-based login (Chapter 13). `public_id` is the id we show outside the system."""

    username = None
    email = models.EmailField(unique=True)
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []
    objects = UserManager()

    def __str__(self) -> str:
        return self.email
```

**Allow-list the fields.** The registration serializer accepts `email`, `password` and `first_name` and nothing else, so a client that adds `"is_staff": true` is simply ignored (a test proves it). The password goes through Django's validators and is hashed by `create_user`; it is never stored or logged in plain text (section 17.6).

**Register and login are the only public endpoints**, and both are throttled with the `auth` scope. Everything else is covered by the global `IsAuthenticated` default, so a forgotten permission locks an endpoint instead of opening it.


## The billing page

The billing page lists plans from the public endpoint, lets the user pick Stripe or Paystack, and calls `POST /billing/checkout/`. The server returns a hosted checkout URL and the page navigates to it. Two details matter.

**web/BillingPage.tsx**

```
  useEffect(() => {
    void refresh();
    // Coming back from the gateway: the webhook may arrive a few seconds AFTER the redirect, so poll briefly.
    if (new URLSearchParams(window.location.search).get("checkout") !== "success") return;
    setMessage("Confirming your payment…");
    let tries = 0;
    const timer = setInterval(async () => {
      const latest = await refresh();
      if (latest?.plan.code !== "free" || ++tries >= 15) {
        clearInterval(timer);
        setMessage(latest?.plan.code !== "free" ? "You are on Pro. Thank you!" : "Still waiting for the payment confirmation. This can take a minute.");
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [refresh]);
```

After the gateway redirects back with `?checkout=success`, the webhook may still be a few seconds away. The page shows "Confirming your payment…" and polls the subscription endpoint every two seconds for up to 30 seconds. If it still sees Free, it says so honestly instead of pretending, and the `plan.updated` push will fix the screen when the webhook lands. Use the hosted checkout pages (Chapter 36 and 37): your server never sees a card number, which keeps you out of the heaviest tier of payment compliance.

Because the engine is shared, the Expo screen is only a view. `WebSocket` and `fetch` exist in React Native, the id helper avoids `crypto.randomUUID`, which is missing there, and `useChat` is imported from the same folder.

**mobile/ChatScreen.tsx**

```
export default function ChatScreen(props: UseChatOptions & { upgradeUrl: string }) {
  const { state, send, stop } = useChat(props);
  const [draft, setDraft] = useState("");
  const list = useRef<FlatList>(null);
  const canSend = state.connection === "open" && !state.busy && !state.limitReached && draft.trim().length > 0;

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={styles.header}>
        <Text>{state.plan?.name ?? "…"}</Text>
        <Text>{state.usage ? `${state.usage.used}/${state.usage.limit} today` : ""}</Text>
        {state.connection !== "open" && <ActivityIndicator />}
      </View>

      <FlatList ref={list} data={state.messages} keyExtractor={(m) => m.key} contentContainerStyle={{ padding: 12 }}
        onContentSizeChange={() => list.current?.scrollToEnd({ animated: true })}
        renderItem={({ item }) => (
          <View style={[styles.bubble, item.role === "user" ? styles.mine : styles.theirs]}>
            <Text style={item.role === "user" ? styles.mineText : undefined}>{item.content || (item.status === "streaming" ? "…" : "")}</Text>
            {item.status === "stopped" && <Text style={styles.note}>Stopped</Text>}
            {item.status === "error" && <Text style={[styles.note, { color: "#b91c1c" }]}>This answer did not finish.</Text>}
          </View>
        )} />

      {state.error && (
        <View style={styles.error}>
          <Text>{state.error.message}</Text>
          {state.limitReached && <Pressable onPress={() => Linking.openURL(props.upgradeUrl)}><Text style={styles.link}>Upgrade</Text></Pressable>}
        </View>
      )}

      <View style={styles.composer}>
        <TextInput style={styles.input} value={draft} onChangeText={setDraft} multiline placeholder="Ask anything…" maxLength={8000} />
        {state.busy
          ? <Pressable style={[styles.button, { backgroundColor: "#1f2937" }]} onPress={stop}><Text style={styles.buttonText}>Stop</Text></Pressable>
          : <Pressable style={[styles.button, !canSend && { opacity: 0.5 }]} disabled={!canSend}
              onPress={() => { if (send(draft)) setDraft(""); }}><Text style={styles.buttonText}>Send</Text></Pressable>}
      </View>
    </KeyboardAvoidingView>
  );
}
```

Mobile adds three concerns the web does not have, all taught in Part V:

- **Backgrounding.** When the app goes to the background the OS may close the socket. The client's reconnect logic handles it, and the reducer turns any half-finished answer into `stopped`. Reopening the conversation loads the saved history from the REST endpoint (`openConversation`).
- **The token.**  `getAccessToken` should read the JWT from secure storage (Chapter 24), never from plain storage.
- **The Upgrade button.** On mobile it opens the web checkout with `Linking.openURL`. As noted in 56.1, **check the current store rules** for selling digital subscriptions before you ship this.
> **The mobile screen was not run**
>
> Unlike the shared logic, which has tests, and the web components, which type-check, this screen was written against the Expo and React Native APIs but was **not compiled or run** while writing this chapter. Treat it as a reviewed draft: build it in your Expo project (Chapter 23), and expect to fix an import or a style prop on the first run.

Chapter 17 gave you a threat model and a checklist. This is that checklist applied to the finished product. For each risk, the table says where it is handled and which test proves it, because "we handle it" without a test is a hope.

| **Risk** | **How this project handles it** | **Proof** |
|---|---|---|
| **Reading another user's chat** (A01) | Every query starts from the owner; other ids return 404 or `not_found` | `test_another_users_conversation_looks_like_it_does_not_exist`, `test_other_users_get_404_for_read_history_and_delete` |
| **Mass assignment** (A01) | Explicit serializer fields; `is_staff` in a request is ignored | `test_client_cannot_make_itself_staff` |
| **Token in a URL** (A02, A07) | Single-use 60-second ticket; 4401 on failure | `test_a_ticket_cannot_be_used_twice`, `test_connection_without_a_valid_ticket_is_closed_with_4401` |
| **Cross-site socket** (A01) | Origin validator on the WebSocket router | Configuration (ASGI) |
| **Fake payment webhook** (A08) | Signature checked on the raw body before anything else | `test_wrong_secret_is_rejected_and_changes_nothing`, `test_tampered_body_is_rejected` |
| **Replayed webhook** (A08) | Stripe timestamp window plus a unique event record | `test_old_timestamps_are_rejected_to_stop_replays`, `test_the_same_event_delivered_twice_is_applied_once` |
| **Underpaying for Pro** (A06) | Expected amount compared; price comes from the server | `test_a_charge_for_the_wrong_amount_does_not_grant_access`, `test_client_cannot_choose_the_price_or_an_unknown_plan` |
| **Denial of wallet** (A06) | Daily limit by plan, atomic counter, size cap per message, one answer at a time, output token cap | `test_limit_is_enforced_exactly`, `test_only_one_answer_at_a_time`, `test_empty_and_too_long_messages_are_rejected` |
| **Brute-forcing login** (A07) | `auth` throttle scope on register, login and refresh | Configuration (the test settings raise the rate, so lower it to see it) |
| **Leaking internals** (A10) | Gateway and provider errors become fixed messages | `test_gateway_failure_becomes_a_clean_502` |
| **Secrets in the browser** | Only the public id and plan code travel; keys live in the server environment | Code review: search the `clients/` folder for `sk_` |
| **Prompt injection through memory** | Summary treated as data, labelled in the prompt | Prompt design (Chapter 28); no automated test can fully prove it |


## How to test an async WebSocket

Consumer tests use `TransactionTestCase` (not `TestCase`) because the consumer's database work runs in other threads, and a `WebsocketCommunicator`, which speaks to the consumer exactly as a server would. The pattern is small enough to memorise:

**python chat/tests/test_consumer.py (pattern)**

```python
comm = WebsocketCommunicator(APP, f"/ws/chat/?ticket={ticket}")
connected, _ = await comm.connect()
await comm.receive_json_from()                        # the "ready" frame
await comm.send_json_to({"type": "chat.send", "content": "Hi"})
frames = await self.collect_until(comm, "chat.done")  # read frames until the one we want
```

Patch `get_provider` to return a `FakeProvider` you control, set its `delay` to make Stop testable, and read `provider.calls` to see exactly what context the model received.


## Testing the tests: a mutation check

Passing tests prove little unless they can fail. After the suite passed, the following breakages were made **one at a time**, the suite was run, and the original code was restored. A test must fail for every one:

| **Deliberate breakage** | **First failing test** |
|---|---|
| Owner filter removed from `start_turn` | `test_another_users_conversation_looks_like_it_does_not_exist` |
| Stripe signature check skipped | `test_missing_signature_header_is_rejected` |
| Paystack signature always accepted | `test_signature_uses_sha512_of_the_raw_body` |
| Idempotency record never conflicts | `test_delivering_the_same_charge_twice_extends_the_period_only_once` |
| Amount check removed | `test_a_charge_for_the_wrong_amount_does_not_grant_access` |
| Stale-event guard removed | `test_an_older_event_arriving_late_cannot_undo_a_newer_one` |
| Stop frame ignored | `test_stop_keeps_the_partial_answer` |
| Ticket not burned on use | `test_ticket_is_single_use` |
| Limit check loosened | `test_limit_is_enforced_exactly` |
| Refund removed after provider failure | `test_provider_failure_before_any_text_refunds_the_message` |
| Grace period ignored | `test_failed_payment_keeps_access_during_the_grace_period_then_ends_it` |
| Webhook answers 200 after a crash | `test_a_crash_while_applying_returns_500_and_leaves_no_seen_marker_so_the_retry_works` |
| Message history leaks across users | `test_other_users_get_404_for_read_history_and_delete` |

All 13 were caught (the table shows the first test to fail in each run; others may fail too). Exercise 1 asks you to repeat this on your own copy. It is the fastest way to find out whether a green test suite deserves your trust, but it only shows that these 13 mistakes would not slip through; it does not replace thinking.


## What the tests cannot tell you

They ran on SQLite, an in-memory channel layer and eager Celery. Three things only show up on the real stack: PostgreSQL's row locking (SQLite ignores `select_for_update`), Redis behaviour under several workers, and a proxy that closes idle WebSockets. Section 56.9 ends with a check of each, and Chapter 55 covers monitoring them.

Follow these steps in order. Total time: about two hours, plus another hour if you create real Stripe and Paystack test accounts. Every step ends with a **check**.
