# Chapter 37 — Paystack Integration: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## What Paystack Does, and How It Differs from Stripe › The objects

| **Object** | **What it is** | **Who creates it** |
|---|---|---|
| **Transaction** | One payment attempt, identified by a **reference**. Its status ends as success, failed or abandoned | Your server starts it (initialize). The customer completes it on Paystack's page |
| **Customer** | A person who pays you, identified by email, with a customer code (`CUS_...`) | Paystack creates it on the first payment |
| **Plan** | A recurring price: an amount, an interval (monthly, annually and others) and a currency, with a code (`PLN_...`) | You, in the Dashboard or by API |
| **Authorization** | A saved card (or other reusable payment method) with an authorization code (`AUTH_...`). It lets you charge the customer later | Paystack, after a successful card payment, if the card is reusable |
| **Subscription** | A customer on a plan, charged on a schedule using the saved authorization, with a code (`SUB_...`) and an **email token** needed to cancel or resume it | Paystack, after the first payment on a plan, or by your API call |
| **Event** | A webhook message such as `charge.success` or `invoice.payment_failed` | Paystack |


## Account, Keys, Test Mode and Going Live › The webhook URL and testing on your laptop

You give Paystack one **webhook URL** for test mode and one for live mode, in the Dashboard's API settings. Paystack must be able to reach it, so on your laptop you need a tunnel (a tool such as ngrok or cloudflared that gives your local server a public HTTPS address), and you paste that address into the test webhook URL. The Dashboard shows the events it sent, the answers it got and lets you inspect the payloads, and it is the first place to look when something does not arrive.


## Account, Keys, Test Mode and Going Live › Test cards

In test mode Paystack gives you test cards. The one to remember is `4084 0840 8408 4081` with any future expiry date and the CVV `408`, which pays successfully. Paystack's documentation lists more cards and test flows for declines, PINs and one-time passwords, bank transfers and USSD, and you should use them to see how each branch of your code behaves, because the flows differ (an OTP step, a pending bank transfer).


## One-Time Payments: Initialize, Callback, Verify › Your own reference is your idempotency key

Stripe lets you attach an `Idempotency-Key` to a request. Paystack does not, and its protection is the **reference**: a transaction reference must be unique, and Paystack refuses a duplicate. So the service makes a fresh random reference for every payment, **saves the expectation first**, then calls initialize:

**python the order matters**

```python
reference = new_reference()                           # "ps_" + 24 random hex characters
self.store.save_pending(PendingTransaction(reference, user.id, plan.key, kind, amount, plan.currency))
data = self.gateway.initialize_transaction(params)    # only now does the customer get a way to pay
```

If the call to Paystack fails, the saved row is harmless: nobody can pay a reference that was never initialized, and the nightly check gives up on it after 72 hours. If the order were reversed, a fast customer and a slow database could make a payment arrive for a reference you had not recorded yet.


## Subscriptions with Plans and Authorization Codes › Changing plans

Paystack has **no in-place plan change and no proration**. There are two honest options. The simple one, which this chapter builds, is to **switch at the next payment date**: create a new subscription for the new plan with `start_date` equal to the old subscription's next payment date, then disable the old one so it becomes `non-renewing`. The customer keeps the plan they paid for until that date, the interface says "switching to Team on 12 December", and on that date the old subscription ends and the new one is charged. The record keeps the pending plan and the pending subscription code, and a small function decides when the new subscription takes over:

**paystackbilling/service.py (change_plan)**

```
    def change_plan(self, user: User, new_plan_key: str) -> AccessDecision:
        """Switch plans at the next payment date. Paystack has no proration and no in-place plan change,
        so we create the new subscription to start when the old one ends, and stop the old one renewing."""
        record = self._record(user)
        new_plan = self.config.plan(new_plan_key)
        old_plan = self.config.plan(record.plan_key) if record.plan_key else None
        if new_plan.interval == "once":
            raise UnknownPlan("A one-time purchase is not a subscription plan.")
        if old_plan and new_plan.currency != old_plan.currency:
            raise UnknownPlan("A subscription cannot switch currency. Cancel it and start a new one.")
        if new_plan.plan_code == (old_plan.plan_code if old_plan else None):
            return self.access(user.id)
        now = self.clock()
        start = record.next_payment_date if record.next_payment_date and record.next_payment_date > now else int(now) + DAY
        created = self.gateway.create_subscription(subscription_params(
            customer_code=record.customer_code, plan_code=new_plan.plan_code,
            authorization_code=record.authorization_code, start_date=iso_time(start)))
        self.gateway.disable_subscription(record.subscription_code, record.email_token)
        sync_subscription(self.store, self.config, self.gateway, record.subscription_code, now, user.id)
        current = self.store.subscription_for(user.id)
        current.pending_plan_key = new_plan_key
        current.pending_subscription_code = created["subscription_code"]
        self.store.save_subscription(current)
        return self.access(user.id)
```

**paystackbilling/handlers.py**

```
def place_snapshot(store, snap: SubscriptionSnapshot, user_id: str, now: float, trial_end: Optional[int] = None) -> str:
    """Save what Paystack says about a subscription as the user's record.

    A user normally has one subscription. During a scheduled plan switch there are two: the old one (now
    non-renewing) and the new one (waiting for its start date). The new one replaces the old only when the
    old one has ended, so a customer never loses the plan they already paid for. Returns what happened.
    """
    current = store.subscription_for(user_id)
    record = SubscriptionRecord(
        user_id=str(user_id), customer_code=snap.customer_code, subscription_code=snap.subscription_code,
        email_token=snap.email_token, status=snap.status, plan_key=snap.plan_key, tier=snap.tier,
        next_payment_date=snap.next_payment_date, authorization_code=snap.authorization_code,
        card_last4=snap.card_last4, trial_end=trial_end)
    if current is None or current.subscription_code == snap.subscription_code:
        if current is not None:
            record = replace(record, trial_end=trial_end if trial_end is not None else current.trial_end,
                             pending_plan_key=current.pending_plan_key,
                             pending_subscription_code=current.pending_subscription_code)
        store.save_subscription(record)
        return "updated" if current else "created"
    old_ended = (current.status in {"cancelled", "completed"} or
                 (current.next_payment_date is not None and now >= current.next_payment_date))
    if snap.subscription_code == current.pending_subscription_code and old_ended:
        store.save_subscription(record)                      # the scheduled switch has arrived
        return "switched"
    if current.status in {"cancelled", "completed"} and snap.status in {"active", "attention"}:
        store.save_subscription(record)                      # a fresh subscription after an old one ended
        return "replaced"
    return "ignored"
```

The other option is an **immediate upgrade**: charge the difference for the rest of the period yourself (using the saved authorization), then switch. It needs a proration formula, a charge that can fail and a rollback story, so build it only if a real customer need justifies the work (Exercise 8 walks through the design). A subscription also **cannot switch currency**, because a plan has one, so the service refuses it.

Here is the whole life of one subscription at once. The simulator sends a scripted lifecycle through the real webhook processor with signed payloads and a clock it can move forward, and you can run it yourself with `python -m paystackbilling.cli simulate`. This is real output. The customer pays the card check and starts a trial, the trial ends and the first payment succeeds, a renewal fails and the grace period starts, the grace period runs out, the customer updates the card and pays, then cancels, and finally the period ends:

**text verified output**

```text
step                             HTTP  outcome                  access reason
--------------------------------------------------------------------------------------------------------
trial: pays the card check        200  reference ps_9a382909... free   no subscription
charge.success (card saved)       200  processed                PAID   free trial
trial ends, first payment         200  processed                PAID   active
renewal fails                     200  processed                PAID   renewal payment pending, in the grace period
two days later (grace period)     200  -                        PAID   renewal payment pending, in the grace period
four days later                   200  -                        free   the renewal payment was not received
customer updates card, pays       200  processed                PAID   active
customer cancels                  200  processed                PAID   cancelled, active until the end of the period
period ends                       200  processed                free   the subscription was cancelled

messages sent to the user: payment_failed, cancellation_scheduled, subscription_ended
```

The grace period is visible on the fourth and fifth rows: the renewal failed, the customer still has access two days later, and loses it at day four. The three messages at the bottom are what the `notify` hook was asked to send.


## Webhooks and Signature Verification › The processor: claim, run, record, answer

The order of the checks matters, as in Chapter 36. **Verify first.** Then check the **mode**: Paystack puts a `domain` of `test` or `live` in the data, and an event from the other mode is acknowledged and ignored. Then **claim the event by its body hash** in the database: a unique row per hash makes a duplicate or a replay harmless, and a short lease stops two workers from running the same event at once while still letting a retry through if the first worker died. Then run the handler and record the result:

**paystackbilling/webhooks.py**

```
class WebhookResult:
    status: int
    outcome: str
    event_type: Optional[str] = None
    warnings: list = field(default_factory=list)

class WebhookProcessor:
    """Runs each distinct event at most once and tells Paystack whether to retry.

    HTTP answers: 200 means done, do not resend. Anything else makes Paystack retry (live mode: every
    3 minutes for four tries, then hourly for up to 72 hours). So: 400 bad signature, 409 busy, 500 failed,
    and 200 for processed, duplicate, ignored and wrong-mode events.
    """

    def __init__(self, verifier, store, handlers: dict, *, livemode: bool, clock: Callable = time.time,
                 lease_seconds: int = 300, log: Callable = lambda *a: None):
        self.verifier, self.store, self.handlers = verifier, store, handlers
        self.livemode, self.clock, self.lease_seconds, self.log = livemode, clock, lease_seconds, log

    def handle(self, body: bytes, signature: str) -> WebhookResult:
        try:
            event = self.verifier.verify(body, signature)
        except SignatureError as error:
            self.log("webhook_rejected", str(error))
            return WebhookResult(400, "bad_signature")
        return self.process_verified(event, event_key(body))

    def process_verified(self, event: dict, key: str) -> WebhookResult:
        name = event["event"]
        data = event.get("data")
        domain = data.get("domain") if isinstance(data, dict) else None
        if domain and (domain == "live") != self.livemode:
            self.log("webhook_wrong_mode", name)
            return WebhookResult(200, "ignored_wrong_mode", name)
        claim = self.store.begin_event(key, name, self.clock(), self.lease_seconds)
        if claim == "duplicate":
            return WebhookResult(200, "duplicate", name)
        if claim == "busy":
            return WebhookResult(409, "busy", name)
        handler = self.handlers.get(name)
        if handler is None:
            self.store.finish_event(key, "ignored")
            return WebhookResult(200, "ignored", name)
        try:
            handler(event)
        except UnresolvedCustomer as error:
            self.store.finish_event(key, "failed", str(error))
            return WebhookResult(500, "retry_unresolved_customer", name)
        except Exception as error:
            self.store.finish_event(key, "failed", f"{type(error).__name__}: {error}")
            self.log("webhook_handler_failed", name, type(error).__name__)
            return WebhookResult(500, "handler_failed", name)
        self.store.finish_event(key, "processed")
        return WebhookResult(200, "processed", name)
```

The HTTP answer is part of the design. Paystack treats a `200` as "received" and anything else as a failure to retry. In live mode it retries every three minutes for the first four attempts and then hourly, for up to 72 hours (in test mode the retries are less frequent and stop sooner), so check the current schedule. The processor answers `400` for a bad signature, `409` for an event another worker holds, `500` when a handler fails (so Paystack tries again) and `200` for everything that is done or should not be retried: processed events, duplicates, events of types we do not handle and events from the wrong mode. Answer quickly, because Paystack gives up on a slow response, and do slow work in a Celery task.


## Webhooks and Signature Verification › Recovery

When a handler failed because of a bug, fix the bug and let Paystack's retry run it, or ask the Dashboard to resend the event if it has stopped retrying. The event table keeps the error text of every failed attempt. Two scheduled jobs make the design robust: `reconcile_pending_payments` (every few minutes) finds payments whose callback and webhook were both lost, and `paystack_reconcile` (nightly) re-reads every unfinished subscription from Paystack and repairs your copy.

> **Keep slow work out of the request**
>
> **Answer within a second or two.** Claim the event, do the fast database writes, queue anything slow (emails, other API calls) in a Celery task, mark the event processed and return `200`. The `notify` hook in this chapter is where that task is started.


## The Django API › The store

The database store has the same methods as the in-memory one used by the tests. Two of them hold the guarantees. `grant_credits` relies on a **unique reference** so a second grant is impossible, and `begin_event` takes a row lock and uses the unique body hash so two workers receiving the same event cannot both run it:

**billing_paystack/store.py**

```
    def grant_credits(self, user_id, amount: int, ref: str) -> bool:
        _, created = CreditGrant.objects.get_or_create(ref=ref, defaults={"user_id": user_id, "amount": amount})
        return created

    def reverse_credits(self, ref: str) -> bool:
        return CreditGrant.objects.filter(ref=ref, reversed=False).update(reversed=True) == 1

    def credit_balance(self, user_id) -> int:
        return CreditGrant.objects.filter(user_id=user_id, reversed=False).aggregate(t=Sum("amount"))["t"] or 0

    @transaction.atomic
    def begin_event(self, event_key: str, event_type: str, now: float, lease_seconds: int = 300) -> str:
        event, created = WebhookEvent.objects.select_for_update().get_or_create(
            event_key=event_key, defaults={"event_type": event_type, "status": "processing", "started_at": now})
        if created:
            return "run"
        if event.status in {"processed", "ignored"}:
            return "duplicate"
        if event.status == "processing" and now - event.started_at < lease_seconds:
            return "busy"
        event.status, event.started_at, event.attempts = "processing", now, event.attempts + 1
        event.save(update_fields=["status", "started_at", "attempts"])
        return "run"

    def finish_event(self, event_key: str, status: str, error: str = "") -> None:
        WebhookEvent.objects.filter(event_key=event_key).update(status=status, error=error[:300])
```

> **The webhook route and your infrastructure**
>
> **The raw body must reach Django unchanged.** A proxy that rewrites or recompresses the body, a middleware that re-encodes it, or a framework layer that parses the JSON first will make every genuine signature fail. If every delivery answers `400` in production while it worked on your laptop, look at what sits between Paystack and Django, and check that production uses the **live** secret key while the Dashboard's live webhook URL points at it.


## The Web Frontend (Next.js) › The pieces

- **A typed API module** (`lib/paystack.ts`): `getStatus`, `pay`, `verify`, `cancelSubscription`, `resumeSubscription`, `changePlan`, `updateCard`, and a `formatMoney` that is for display only.
- **The billing page**: shows the plan and the reason, the price list for the customer's currency (one list per currency, with no conversion), a warning with an "Update card" button when the last renewal failed, a note when a plan switch is scheduled, and the right buttons for the state (subscribe, cancel, resume).
- **The callback page**: Paystack returns the customer to `/billing/callback?reference=...&trxref=...`. The page calls `verify` with the reference, so **your server** asks Paystack, and shows one of six messages. For a payment that is still pending (a bank transfer, for example) it asks again a few times and then says it is still being confirmed. It never decides from the URL alone.
**frontend/paystack.ts (not executed here)**

```
// lib/paystack.ts: typed calls to the Django billing API. apiFetch is the authenticated fetch wrapper from
// the earlier frontend chapters. Not executed here.
import { apiFetch } from "@/lib/api";

export type PlanKey = "pro_monthly_ngn" | "pro_yearly_ngn" | "team_monthly_ngn" | "pro_monthly_usd" | "credits_100";

export interface BillingStatus {
  paid: boolean;
  tier: "free" | "pro" | "team";
  reason: string;
  until: number | null;         // unix seconds
  status: string | null;
  card_last4: string;
  switching_to: PlanKey | null;
  credits: number;
}

interface Started { reference: string; authorization_url: string; access_code: string }

export const getStatus = () => apiFetch<BillingStatus>("/api/billing/paystack/status/");

/** Sends the browser to Paystack's checkout page. The server decides the amount from the plan key. */
export async function pay(plan: PlanKey, kind: "subscribe" | "pay"): Promise<void> {
  const res = await apiFetch<Started>(`/api/billing/paystack/${kind}/`, { method: "POST", body: { plan } });
  window.location.assign(res.authorization_url);
}

/** Called by the callback page. Never trusts the URL: the server asks Paystack and compares the amount. */
export const verify = (reference: string) =>
  apiFetch<{ status: string; paid: boolean; tier: string; credits: number }>("/api/billing/paystack/verify/", {
    method: "POST",
    body: { reference },
  });

export const cancelSubscription = () => apiFetch("/api/billing/paystack/cancel/", { method: "POST", body: {} });
export const resumeSubscription = () => apiFetch("/api/billing/paystack/resume/", { method: "POST", body: {} });
export const changePlan = (plan: PlanKey) => apiFetch("/api/billing/paystack/change-plan/", { method: "POST", body: { plan } });

export async function updateCard(): Promise<void> {
  const { url } = await apiFetch<{ url: string }>("/api/billing/paystack/card-link/", { method: "POST", body: {} });
  window.location.assign(url);   // a Paystack-hosted page where the customer replaces the card
}

export const formatMoney = (kobo: number, currency: string) =>
  new Intl.NumberFormat("en-NG", { style: "currency", currency }).format(kobo / 100);   // display only, never to compute
```

**frontend/BillingPage.tsx (not executed here)**

```
// app/billing/page.tsx: shows the plan, the price list for the customer's currency, and the controls. Not executed here.
"use client";

import { useEffect, useState } from "react";
import {
  BillingStatus, PlanKey, cancelSubscription, formatMoney, getStatus, pay, resumeSubscription, updateCard,
} from "@/lib/paystack";

// One price list per currency: a Paystack plan has a single currency, so we never convert on the fly.
const PRICE_LISTS: Record<"NGN" | "USD", { key: PlanKey; name: string; kobo: number }[]> = {
  NGN: [
    { key: "pro_monthly_ngn", name: "Pro, monthly", kobo: 500000 },
    { key: "pro_yearly_ngn", name: "Pro, yearly", kobo: 5000000 },
    { key: "team_monthly_ngn", name: "Team, monthly", kobo: 1500000 },
  ],
  USD: [{ key: "pro_monthly_usd", name: "Pro, monthly", kobo: 1000 }],
};

export default function BillingPage({ currency = "NGN" }: { currency?: "NGN" | "USD" }) {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { getStatus().then(setStatus).catch(() => setError("Could not load your plan.")); }, []);

  async function run(label: string, action: () => Promise<unknown>, refresh = false) {
    setBusy(label); setError(null);
    try { await action(); if (refresh) setStatus(await getStatus()); }
    catch (e) { setError(e instanceof Error ? e.message : "Something went wrong."); }
    finally { setBusy(null); }
  }

  if (!status) return <p>{error ?? "Loading…"}</p>;
  const until = status.until ? new Date(status.until * 1000).toLocaleDateString() : null;

  return (
    <main>
      <h1>Billing</h1>
      <p>Your plan: <strong>{status.tier}</strong> ({status.reason}{until ? `, until ${until}` : ""})</p>
      {status.reason.startsWith("last renewal failed") && (
        <p role="alert">Your last payment failed. <button onClick={() => run("card", updateCard)}>Update your card</button></p>
      )}
      {status.switching_to && <p>Your plan will change to {status.switching_to} at your next payment date.</p>}

      {!status.paid ? (
        PRICE_LISTS[currency].map((p) => (
          <button key={p.key} disabled={busy !== null} onClick={() => run(p.key, () => pay(p.key, "subscribe"))}>
            {busy === p.key ? "Redirecting…" : `${p.name}: ${formatMoney(p.kobo, currency)}`}
          </button>
        ))
      ) : status.reason.startsWith("cancelled") ? (
        <button disabled={busy !== null} onClick={() => run("resume", resumeSubscription, true)}>Resume subscription</button>
      ) : (
        <>
          <button disabled={busy !== null} onClick={() => run("cancel", cancelSubscription, true)}>Cancel at the end of the period</button>
          <button disabled={busy !== null} onClick={() => run("card", updateCard)}>Update card</button>
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
```

**frontend/CallbackPage.tsx (not executed here)**

```
// app/billing/callback/page.tsx: where Paystack sends the customer after paying.
// The URL carries ?reference=...&trxref=...; the page asks OUR server, which asks Paystack. Not executed here.
"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getStatus, verify } from "@/lib/paystack";

type State = "checking" | "paid" | "pending" | "failed" | "mismatch" | "error";

export default function CallbackPage() {
  const params = useSearchParams();
  const reference = params.get("reference") ?? params.get("trxref");
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    if (!reference) { setState("error"); return; }
    let cancelled = false;
    (async () => {
      try {
        for (let attempt = 0; attempt < 6 && !cancelled; attempt++) {
          const result = await verify(reference);              // the server asks Paystack
          if (result.status === "paid") { setState("paid"); return; }
          if (result.status === "mismatch") { setState("mismatch"); return; }
          if (result.status === "failed") { setState("failed"); return; }
          await new Promise((r) => setTimeout(r, 2000));       // still pending (a bank transfer, for example)
        }
        if (!cancelled) setState((await getStatus()).paid ? "paid" : "pending");
      } catch { if (!cancelled) setState("error"); }
    })();
    return () => { cancelled = true; };
  }, [reference]);

  const messages: Record<State, string> = {
    checking: "Confirming your payment…",
    paid: "Thank you! Your payment was received.",
    pending: "Your payment is still being confirmed. We will email you when it is done.",
    failed: "The payment did not go through. You have not been charged. You can try again.",
    mismatch: "The amount paid did not match the price, so nothing was activated. Please contact support.",
    error: "We could not confirm your payment. If you were charged, contact support with your reference.",
  };
  return <p role={state === "paid" || state === "checking" ? "status" : "alert"}>{messages[state]}</p>;
}
```

**frontend/InlinePopup.tsx (not executed here)**

```
// components/PayInPopup.tsx: Paystack's popup, resumed from an access_code made by OUR server, so the amount
// cannot be changed in the browser. npm install @paystack/inline-js (check its README for the current API). Not executed here.
"use client";

import PaystackPop from "@paystack/inline-js";
import { apiFetch } from "@/lib/api";
import type { PlanKey } from "@/lib/paystack";

export default function PayInPopup({ plan, kind }: { plan: PlanKey; kind: "subscribe" | "pay" }) {
  async function start() {
    const { access_code, reference } = await apiFetch<{ access_code: string; reference: string }>(
      `/api/billing/paystack/${kind}/`, { method: "POST", body: { plan } });
    const popup = new PaystackPop();
    popup.resumeTransaction(access_code, {
      // The popup closing is not proof of payment. Always finish by asking the server (the callback page does).
      onSuccess: () => window.location.assign(`/billing/callback?reference=${encodeURIComponent(reference)}`),
      onCancel: () => { /* the customer closed the popup: nothing to do, the pending payment simply expires */ },
    });
  }
  return <button onClick={start}>Pay with Paystack</button>;
}
```

Two things to keep in mind. The public key (`NEXT_PUBLIC_...`) is the only Paystack key the frontend ever holds, and only the popup needs it. And the `PRICE_LISTS` in the page are labels for display: the amount that is charged always comes from your server's plan table, so changing a number in the browser changes nothing but the text.


## The Mobile App (React Native)

Mobile apps have a second set of rules that come from Apple and Google, and they apply to Paystack exactly as they do to Stripe.

> **The store rules decide what you may sell inside an app**
>
> **Both app stores require their own in-app purchase systems for digital goods and features used inside the app**, such as a subscription to an AI assistant, extra messages or credits, or a premium tier. Paystack's checkout, whether in a WebView or a native SDK, is allowed for **real-world goods and services** consumed outside the app, not for digital features. The rules have been changing since 2025 (the US storefronts now allow links to external purchase pages under conditions, the European Union has its own regime, and other countries differ), so **read section 36.9 and check the current App Store Review Guidelines and Google Play payments policy for every country you launch in, before you design the purchase screen.** The same three approaches apply: web-first billing (the app reads the plan from your server and sells nothing), a link out to your web checkout where the rules allow, or the stores' own in-app purchase, with your server recording the result in the same subscription table.

Whichever you choose, **the app asks your server what the user may do** (`GET /api/billing/paystack/status/`) and nothing else about money. That keeps one source of truth across web, iOS and Android.


### Paystack checkout in an app

For what the rules allow, the simplest dependable way is to open Paystack's hosted checkout in a **WebView** and stop when it redirects to your callback URL. The component below does that: it loads the `authorization_url`, intercepts the navigation to the callback address (so the callback page never loads inside the app), reads the reference from it and **asks your server** to verify. It guards against the redirect firing twice. Paystack also publishes native mobile SDKs, and community packages exist for React Native. Check their maintenance and license before depending on one. The WebView approach has no dependency beyond `react-native-webview`, and it works the same on both platforms:

**mobile/PaystackCheckout.tsx (not executed here)**

```
// mobile/PaystackCheckout.tsx: opens Paystack's hosted checkout in a WebView and catches the callback URL.
// npm install react-native-webview. Not executed here. Read section 37.10 (app store rules) before using it.
import { useRef } from "react";
import { ActivityIndicator, Modal, SafeAreaView } from "react-native";
import { WebView } from "react-native-webview";
import { apiFetch } from "./api";

const CALLBACK_PREFIX = "https://app.example.com/billing/callback";   // must match PAYSTACK_CALLBACK_URL on the server

type Props = { authorizationUrl: string; visible: boolean; onDone: (paid: boolean) => void };

export default function PaystackCheckout({ authorizationUrl, visible, onDone }: Props) {
  const handled = useRef(false);

  async function finish(url: string) {
    if (handled.current) return;                 // the redirect can fire more than once
    handled.current = true;
    const reference = new URL(url).searchParams.get("reference");
    if (!reference) return onDone(false);
    try {
      // The app never decides. The server asks Paystack and compares the amount.
      const result = await apiFetch<{ status: string }>("/api/billing/paystack/verify/", { method: "POST", body: { reference } });
      onDone(result.status === "paid");
    } catch { onDone(false); }
  }

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={() => onDone(false)}>
      <SafeAreaView style={{ flex: 1 }}>
        <WebView
          source={{ uri: authorizationUrl }}
          startInLoadingState
          renderLoading={() => <ActivityIndicator style={{ flex: 1 }} />}
          // Stop at our callback URL instead of loading it inside the app.
          onShouldStartLoadWithRequest={(request) => {
            if (request.url.startsWith(CALLBACK_PREFIX)) { void finish(request.url); return false; }
            return true;
          }}
        />
      </SafeAreaView>
    </Modal>
  );
}
```

**mobile/billing.ts (not executed here)**

```
// mobile/billing.ts: the app reads the plan from YOUR server and starts payments there. Not executed here.
import { apiFetch } from "./api";

export type Status = { paid: boolean; tier: string; reason: string; until: number | null; card_last4: string };
export const getStatus = () => apiFetch<Status>("/api/billing/paystack/status/");

// Returns the Paystack checkout URL for PaystackCheckout. Use it only for what the store rules allow (37.10).
export async function startPayment(plan: string, kind: "pay" | "subscribe"): Promise<string> {
  const { authorization_url } = await apiFetch<{ authorization_url: string }>(
    `/api/billing/paystack/${kind}/`, { method: "POST", body: { plan } });
  return authorization_url;
}
```

The callback URL in the component must be a URL **you** control and the same one your server passes to Paystack (`PAYSTACK_CALLBACK_URL`), which the server also checks against its allowed hosts. A payment that completes while the app is in the background is still recorded by the webhook, so when the app opens again it simply asks the status endpoint.


## Security, Testing and Going Live › What can go wrong

| **Threat** | **How it happens** | **Defence in this chapter** |
|---|---|---|
| **Price tampering** | The browser sends a different amount or plan | The browser sends a plan key. The amount and plan code come from the server's table |
| **Forged webhook** | A stranger POSTs `charge.success` | HMAC-SHA512 over the raw body with the secret key, compared in constant time |
| **Underpaid forged payment** | A real signature is not required: someone pays ₦50 for a ₦2,000 pack, or a webhook claims it | The amount and currency are compared with the pending record. A mismatch grants nothing and alerts the team |
| **Replay** | A captured, valid, signed request is sent again | The event log by body hash. The signature itself has no expiry |
| **Callback tampering** | A user opens the callback URL with someone else's reference | The reference must belong to the logged-in user, and the server asks Paystack |
| **Double grant** | Callback, webhook and the nightly check all see the same payment | One function, a `paid` flag on the pending record and a unique reference on every credit grant |
| **Secret key leak** | The key in Git, a log or an app bundle | Environment variable, server only. Remember it also signs webhooks, so a leak is both an API and a webhook compromise |
| **Stored card misuse** | The authorization code or email token leaks | Never log or return them, hide them in the admin, never send them to the browser |
| **Wrong mode** | A test event reaches the live server | The `domain` check, and the mode derived from the key |
| **Free access by accident** | A status the code did not expect | Unknown statuses give no access |


## Security, Testing and Going Live › Testing

| **Layer** | **What it covers** | **How** |
|---|---|---|
| **Unit tests** | Money, plan table, request builders, access decision, signatures, processor, handlers, service | `python -m unittest paystackbilling.test_paystackbilling` |
| **The simulator** | A whole lifecycle with a trial, and hostile deliveries | `python -m paystackbilling.cli simulate` and `attacks` |
| **Test mode with a tunnel** | Real Paystack objects and real signed events on your laptop | The test cards, your tunnel URL as the test webhook, the Dashboard's webhook log |
| **Real time** | Renewals and the failed-renewal path | Create a test plan with a short interval (Paystack supports hourly and daily intervals) and watch real renewals |

The scenarios worth walking through by hand in test mode, each ending with a look at the subscription row and the event table:

- Pay for the credit pack with the test card, then reload the callback page five times: the balance must stay at 100.
- Start a trial subscription and check the subscription's start date.
- Start a subscription without a trial and watch `subscription.create` and `invoice.update` arrive.
- Use a test card that declines, and an abandoned checkout, and check that nothing is granted.
- Close the tab right after paying, and check that the webhook alone grants the credits.
- Stop your server during a payment, start it again, and watch Paystack's retry.
- Cancel and resume a subscription, and update the card through the hosted link.
- Schedule a plan switch and read both subscriptions at Paystack.
- Send the same webhook body twice (copy it from the Dashboard log) and a body with a changed amount.

## Security, Testing and Going Live › Going live

Going live is a checklist. The mode follows the key, so a live environment has live keys, live plan codes and a live webhook URL, and nothing from test mode:

- **Finish business verification** and add the settlement bank account, so that live keys are issued.
- **Enable the currencies** you sell in, and check the amounts of the live plans against your settings.
- **Recreate the plans in live mode** and put the new plan codes in the live environment.
- **Set the live webhook URL** in the Dashboard, pointing at the production endpoint, and confirm that the production server uses the live secret key.
- **Put the live secret key in your secrets manager**, not in a file in the repository (Chapter 40).
- **Make one small real payment and refund it**, as the final test of the whole chain.
- **Monitor**: events in the `failed` state, events stuck in `processing`, a rise in `400` answers (a wrong key), pending payments that stay pending, subscriptions in `attention`, and any `amount_mismatch` alert, which is always worth reading.
- **Keep a switch.** A feature flag that hides the pay buttons lets you stop new payments in a minute, without touching existing subscribers.