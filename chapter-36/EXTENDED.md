# Chapter 36 — Stripe Integration: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Account, Keys and Test Mode › The Stripe CLI and test cards

The **Stripe CLI** logs in to your account, forwards real webhook events to your laptop and can trigger test events. You will use it in the hands-on:

**bash terminal**

```bash
stripe login
stripe listen --forward-to localhost:8000/api/billing/stripe/webhook/
# it prints your signing secret for this session: whsec_...
stripe trigger checkout.session.completed
```

In test mode you pay with test cards. These are the ones worth memorising:

| **Card number** | **What it does** |
|---|---|
| `4242 4242 4242 4242` | Succeeds. Use any future expiry date, any three-digit CVC and any postal code |
| `4000 0000 0000 0002` | Declined |
| `4000 0000 0000 9995` | Declined for insufficient funds |
| `4000 0025 0000 3155` | Needs 3-D Secure authentication, which a test page lets you complete or fail |
| `4000 0000 0000 0341` | Attaches to a customer but fails when you try to charge it later: the way to test a renewal that fails |

Stripe's documentation lists many more, including cards for disputes and for specific countries. To test subscriptions across time without waiting a month, use **test clocks**: a test customer attached to a clock that you can move forward by a month in one click, to watch the renewal, the failed payment and the cancellation happen.


## One-Time Payments › Building the request

The most important rule is already in the first line: **the request is built by a function that takes a plan key, never a price, an amount or a currency from the browser.** The function also refuses redirect URLs outside your own hosts (an open redirect after payment is a phishing gift), sets `client_reference_id` to your user id so the event can find the user, copies the user id and plan into `metadata`, and never sends `payment_method_types`:

**stripebilling/params.py**

```
"""Building the parameters for Stripe calls as plain dictionaries, so tests can check every one.

Rules that these builders enforce:
  * The price always comes from OUR plan table, never from the browser.
  * Redirect URLs must point at hosts we allow.
  * We never send payment_method_types: current API versions removed it from Checkout, and payment
    methods are managed in the Dashboard.
"""
import hashlib
from typing import Optional
from urllib.parse import urlparse

from .errors import BadRedirectUrl

CHECKOUT_ID_PLACEHOLDER = "{CHECKOUT_SESSION_ID}"

def idempotency_key(*parts) -> str:
    """A key that is the same for the same request and different for a different one.

    Stripe remembers a key for 24 hours. Sending the same key with the same parameters returns the
    original result instead of doing the work twice, and sending it with different parameters is an
    error, so put everything that changes the request into the key.
    """
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return digest[:40]

def check_redirect_url(url: str, allowed_hosts) -> str:
    parsed = urlparse(url.replace(CHECKOUT_ID_PLACEHOLDER, "x"))
    if parsed.scheme not in {"https", "http"} or parsed.hostname not in allowed_hosts:
        raise BadRedirectUrl(f"URL not allowed: {url}")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise BadRedirectUrl("Use https for redirect URLs.")
    return url

def checkout_params(*, plan, user_id: str, customer_id: Optional[str], email: str, success_url: str,
                    cancel_url: str, allowed_hosts, trial_days: Optional[int] = None,
                    embedded: bool = False, allow_promotion_codes: bool = True) -> dict:
    """Parameters for creating a Checkout Session for one plan."""
    check_redirect_url(success_url, allowed_hosts)
    check_redirect_url(cancel_url, allowed_hosts)
    subscribing = plan.interval != "once"
    params = {
        "mode": "subscription" if subscribing else "payment",
        "line_items": [{"price": plan.price_id, "quantity": 1}],
        "client_reference_id": str(user_id),
        "metadata": {"user_id": str(user_id), "plan_key": plan.key},
        "allow_promotion_codes": allow_promotion_codes,
    }
    if embedded:
        params["ui_mode"] = "embedded_page"
        params["return_url"] = success_url          # cancel_url is not allowed with embedded checkout
    else:
        params["success_url"] = success_url          # the default ui_mode is "hosted_page"
        params["cancel_url"] = cancel_url
    if customer_id:
        params["customer"] = customer_id
    elif not subscribing:
        params["customer_email"] = email
    if subscribing:
        # Copy the user id onto the subscription itself, so subscription events can find the user.
        params["subscription_data"] = {"metadata": {"user_id": str(user_id), "plan_key": plan.key}}
        if trial_days:
            params["subscription_data"]["trial_period_days"] = int(trial_days)
            params["payment_method_collection"] = "always"      # collect a card at the start of the trial
    return params

def portal_params(customer_id: str, return_url: str, allowed_hosts) -> dict:
    check_redirect_url(return_url, allowed_hosts)
    return {"customer": customer_id, "return_url": return_url}

def plan_change_params(*, item_id: str, new_price_id: str, direction: str) -> dict:
    """Parameters for switching a subscription to another price.

    direction "up": invoice the prorated difference right away, so the upgrade is paid for now.
    direction "down" or "same": add a credit or charge to the next invoice.
    error_if_incomplete: if the payment for the change fails, the change does not happen.
    """
    proration = "always_invoice" if direction == "up" else "create_prorations"
    return {
        "items": [{"id": item_id, "price": new_price_id}],
        "proration_behavior": proration,
        "payment_behavior": "error_if_incomplete",
    }

def cancel_params(at_period_end: bool = True) -> dict:
    return {"cancel_at_period_end": bool(at_period_end)}

def payment_intent_params(*, amount: int, currency: str, customer_id: str, user_id: str, description: str,
                          max_amount: int = 100_000) -> dict:
    """Parameters for a PaymentIntent that a mobile Payment Sheet will confirm.

    The amount is decided by the server (from your own catalog), never by the app. It is in the smallest
    currency unit: cents for USD, kobo for NGN.
    """
    if not isinstance(amount, int) or isinstance(amount, bool) or not 0 < amount <= max_amount:
        raise ValueError(f"amount must be a whole number between 1 and {max_amount}")
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must be a three-letter code such as 'usd'")
    return {
        "amount": amount,
        "currency": currency.lower(),
        "customer": customer_id,
        "description": description[:200],
        "automatic_payment_methods": {"enabled": True},
        "metadata": {"user_id": str(user_id)},
    }
```

Real output for a subscription with a trial, then for a one-time purchase and for embedded checkout. Look at what the embedded version does differently: it uses `return_url` and has no `cancel_url`, because embedded checkout does not allow one:

**text verified output**

```text
== 1. Parameters for a subscription checkout with a free trial
{
  "mode": "subscription",
  "line_items": [
    {
      "price": "price_pro_month",
      "quantity": 1
    }
  ],
  "client_reference_id": "user-1",
  "metadata": {
    "user_id": "user-1",
    "plan_key": "pro_monthly"
  },
  "allow_promotion_codes": true,
  "success_url": "https://app.example.com/billing/success?session_id={CHECKOUT_SESSION_ID}",
  "cancel_url": "https://app.example.com/billing",
  "customer": "cus_001",
  "subscription_data": {
    "metadata": {
      "user_id": "user-1",
      "plan_key": "pro_monthly"
    },
    "trial_period_days": 14
  },
  "payment_method_collection": "always"
}

== 2. Parameters for a one-time purchase, and for embedded checkout
one-time : {'mode': 'payment', 'client_reference_id': 'user-1', 'metadata': {'user_id': 'user-1', 'plan_key': 'credits_100'}}
embedded : {'ui_mode': 'embedded_page', 'return_url': 'https://app.example.com/billing/success?session_id={CHECKOUT_SESSION_ID}'} | has cancel_url: False
payment_method_types sent: False
```


## Subscriptions › The customer portal

The **customer portal** is a page that Stripe hosts where customers update their card, see and download invoices, switch plans and cancel. It saves you from building all of that and from answering the emails that go with it. You turn it on and decide in the Dashboard which actions it allows (cancelling, switching plans, which prices, whether cancelling asks for a reason). In code it is a single call that returns a one-time URL:

**stripebilling/service.py**

```
    def open_portal(self, user: User) -> str:
        customer = self.store.customer_id_for(user.id)
        if not customer:
            raise NoCustomer("Start a checkout first.")
        return self.gateway.create_portal_session(
            portal_params(customer, self.config.return_url, self.config.allowed_hosts))["url"]

    # ---- changing and cancelling -----------------------------------------------------------------
```

Whatever the customer does in the portal arrives as ordinary events (`customer.subscription.updated`, `customer.subscription.deleted`), so your handlers do not care whether a change came from your page, the portal or the Dashboard. That is the benefit of building on events.


## Webhooks: The Part You Cannot Skip › Processing: claim, run, record, answer

The processor turns every delivery into one of a few outcomes and an HTTP status. The order of its checks matters. **Verify first**, and say nothing else to a request that fails. **Check the mode**: a live-mode event must never reach a test-mode server and the other way round (the livemode of the endpoint comes from the key, so they cannot disagree). **Claim the event id** in the database: a unique row per event id is what makes duplicates harmless, and a short **lease** stops two workers from running the same event at once while still letting a retry through if the first worker died. **Run the handler**, and record the result.

**stripebilling/webhooks.py**

```
class WebhookResult:
    status: int                       # the HTTP status to answer with
    outcome: str                      # a short word for logs: processed, duplicate, ignored, ...
    event_id: Optional[str] = None
    warnings: list = field(default_factory=list)

class WebhookProcessor:
    """Runs one event at most once and tells Stripe whether to retry.

    HTTP answers: 2xx means "got it, do not send again". Anything else makes Stripe retry later, with
    growing delays, for days. So we answer:
      400  the signature is bad (do not retry; someone is guessing, or the secret is wrong)
      409  another worker is processing this event right now (retry later)
      500  our handler failed (retry later)
      200  processed, a duplicate, an unknown event type, or an event from the wrong mode
    """

    def __init__(self, verifier, store, handlers: dict, *, livemode: bool, expected_api_version: str = "",
                 clock: Callable = time.time, lease_seconds: int = 300, log: Callable = lambda *a: None):
        self.verifier, self.store, self.handlers = verifier, store, handlers
        self.livemode, self.expected_api_version = livemode, expected_api_version
        self.clock, self.lease_seconds, self.log = clock, lease_seconds, log

    def handle(self, payload: bytes, header: str) -> WebhookResult:
        try:
            event = self.verifier.verify(payload, header)
        except SignatureError as error:
            self.log("webhook_rejected", str(error))
            return WebhookResult(400, "bad_signature")
        return self.process_verified(event)

    def process_verified(self, event: dict) -> WebhookResult:
        """Run an event whose authenticity is already established: a verified delivery, or a replay
        of an event fetched from Stripe's API with our own secret key."""
        event_id, event_type = event["id"], event["type"]
        warnings = []
        if self.expected_api_version and event.get("api_version") != self.expected_api_version:
            warnings.append(f"event api_version {event.get('api_version')} differs from {self.expected_api_version}")
        if bool(event.get("livemode")) != self.livemode:
            self.log("webhook_wrong_mode", event_id)
            return WebhookResult(200, "ignored_wrong_mode", event_id, warnings)

        claim = self.store.begin_event(event_id, event_type, self.clock(), self.lease_seconds)
        if claim == "duplicate":
            return WebhookResult(200, "duplicate", event_id, warnings)
        if claim == "busy":
            return WebhookResult(409, "busy", event_id, warnings)

        handler = self.handlers.get(event_type)
        if handler is None:
            self.store.finish_event(event_id, "ignored")
            return WebhookResult(200, "ignored", event_id, warnings)
        try:
            handler(event)
        except UnresolvedCustomer as error:          # a normal ordering problem: try again later
            self.store.finish_event(event_id, "failed", str(error))
            return WebhookResult(500, "retry_unresolved_customer", event_id, warnings)
        except Exception as error:                   # a bug or an outage: record it and let Stripe retry
            self.store.finish_event(event_id, "failed", f"{type(error).__name__}: {error}")
            self.log("webhook_handler_failed", event_id, type(error).__name__)
            return WebhookResult(500, "handler_failed", event_id, warnings)
        self.store.finish_event(event_id, "processed")
        return WebhookResult(200, "processed", event_id, warnings)
```

The HTTP answer is part of the design. A `2xx` tells Stripe "done, do not send it again", and any other status makes it retry. So a bad signature gets `400` (retrying would not help), a busy event gets `409` and a failing handler gets `500` (retry later). A duplicate, an unknown event type and a wrong-mode event all get `200`, because there is nothing to retry. Unknown event types are acknowledged and ignored, so that turning on new event types in the Dashboard cannot make your endpoint fail.

Here is what the processor does with eight kinds of delivery, from the Stripe-shaped test events in the repository:

**text verified output**

```text
correct signature                            -> HTTP 200 processed
same event delivered again                   -> HTTP 200 duplicate
wrong signing secret                         -> HTTP 400 bad_signature
payload changed after signing                -> HTTP 400 bad_signature
signature older than five minutes            -> HTTP 400 bad_signature
event from live mode in test mode            -> HTTP 200 ignored_wrong_mode
event type we do not handle                  -> HTTP 200 ignored
newer subscription event                     -> HTTP 200 processed
older event arriving late                    -> HTTP 200 processed
status kept after the late event             -> active
```


## Webhooks: The Part You Cannot Skip › Which events we handle, and why

| **Event** | **What the handler does** |
|---|---|
| `checkout.session.completed` | Link the Stripe customer to our user. For a one-time purchase that is paid, grant the credits |
| `checkout.session.async_payment_succeeded` / `_failed` | Grant the credits when a delayed payment lands, or tell the user it failed |
| `customer.subscription.created`, `.updated`, `.deleted`, `.paused`, `.resumed` | Copy the full subscription state. Notify when a cancellation is scheduled or the subscription ends |
| `customer.subscription.trial_will_end` | Send the "your trial ends in three days" reminder |
| `invoice.paid` | Record the payment and its receipt link |
| `invoice.payment_failed` | Tell the customer to update their card, with the portal link |
| `payment_intent.succeeded` | Record a payment made with the mobile Payment Sheet (it carries our user id in its metadata). Checkout payments are recorded from the checkout event instead |
| `charge.refunded` | Mark the payment refunded and reverse the credits of a fully refunded purchase |
| `charge.dispute.created` | Alert the team: there are days to answer |

In the Dashboard, subscribe the endpoint to **exactly these events** and no others. Every event type you do not handle is traffic and noise.

**stripebilling/handlers.py**

```
class StripeHandlers:
    """Connects event types to methods. notify(kind, user_id, **details) sends emails or push messages."""

    def __init__(self, store, config, notify: Callable = lambda *a, **k: None):
        self.store, self.config, self.notify = store, config, notify

    def table(self) -> dict:
        sub = self.on_subscription
        return {
            "checkout.session.completed": self.on_checkout_completed,
            "checkout.session.async_payment_succeeded": self.on_checkout_completed,
            "checkout.session.async_payment_failed": self.on_async_payment_failed,
            "customer.subscription.created": sub,
            "customer.subscription.updated": sub,
            "customer.subscription.deleted": sub,
            "customer.subscription.paused": sub,
            "customer.subscription.resumed": sub,
            "customer.subscription.trial_will_end": self.on_trial_will_end,
            "invoice.paid": self.on_invoice_paid,
            "invoice.payment_failed": self.on_invoice_payment_failed,
            "payment_intent.succeeded": self.on_payment_intent_succeeded,
            "charge.refunded": self.on_charge_refunded,
            "charge.dispute.created": self.on_dispute,
        }
```


## Webhooks: The Part You Cannot Skip › When something is wrong: replay and reconcile

Two tools make recovery routine instead of frightening:

- **Replay.** When a handler failed because of a bug, fix the bug and run the failed events again. Failed events stay in the event table with their error text. The management command `stripe_replay evt_...` fetches one event from Stripe with your secret key (so it is authentic without a signature) and runs it through the same processor, which still ignores it if it was already processed. From the CLI you can also use `stripe events resend`.
- **Reconcile.** A nightly job (`stripe_reconcile`) reads every live subscription from Stripe and overwrites your copy. It repairs anything a missed or failed event left behind. It is the safety net under the whole design, and the reason a lost webhook costs a night and not a customer.
> **Keep slow work out of the request**
>
> **Return the answer in a second or two.** If a handler sends email, calls another service or does anything slow, enqueue a Celery task (Chapter 15) from the handler and let the task do it. The pattern is: claim the event, do the fast database write, queue the slow part, mark the event processed, answer `200`. The `notify` hook in this chapter is where that task is started.


## The Django API › Building the objects once

`services.py` builds the configuration, the gateway, the store and the processor from settings, once per process. It also derives `livemode` from the **key prefix**, so the key and the mode can never disagree:

**billing_stripe/services.py (Django, not executed here)**

```
"""Builds the billing objects once, from Django settings."""
import logging
from functools import lru_cache

from django.conf import settings

from stripebilling.config import BillingConfig, Plan
from stripebilling.gateway import StripeGateway
from stripebilling.handlers import StripeHandlers
from stripebilling.service import BillingService
from stripebilling.webhooks import ManualVerifier, WebhookProcessor

from .store import DjangoBillingStore

log = logging.getLogger("billing")

def livemode() -> bool:
    """Derived from the secret key, so the key and the mode can never disagree."""
    return settings.STRIPE_SECRET_KEY.startswith(("sk_live_", "rk_live_"))

@lru_cache(maxsize=1)
def get_config() -> BillingConfig:
    plans = {key: Plan(key, **values) for key, values in settings.BILLING_PLANS.items()}
    return BillingConfig(
        plans=plans, livemode=livemode(), success_url=settings.BILLING_SUCCESS_URL,
        cancel_url=settings.BILLING_CANCEL_URL, return_url=settings.BILLING_RETURN_URL,
        allowed_hosts=frozenset(settings.BILLING_ALLOWED_HOSTS), trial_days=settings.BILLING_TRIAL_DAYS,
        grace_days=settings.BILLING_GRACE_DAYS)

def notify(kind: str, user_id, **details) -> None:
    """Tell the user (an email task from Chapter 15) or the team. Details never include card data."""
    log.info("billing_notice kind=%s user=%s", kind, user_id)
    # send_billing_email.delay(kind, user_id, details)   <- your Celery task

@lru_cache(maxsize=1)
def get_service() -> BillingService:
    return BillingService(StripeGateway(settings.STRIPE_SECRET_KEY), DjangoBillingStore(), get_config())

@lru_cache(maxsize=1)
def get_processor() -> WebhookProcessor:
    store, config = DjangoBillingStore(), get_config()
    return WebhookProcessor(
        ManualVerifier(settings.STRIPE_WEBHOOK_SECRETS), store, StripeHandlers(store, config, notify).table(),
        livemode=livemode(), expected_api_version=config.expected_api_version, log=log.warning)
```

Add the app and the throttle rate to your settings, and include the URLs:

**python config/settings.py and config/urls.py (additions, not executed here)**

```python
INSTALLED_APPS += ["billing_stripe"]
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["billing"] = "30/hour"
CELERY_BEAT_SCHEDULE["stripe-reconcile"] = {
    "task": "billing_stripe.tasks.reconcile_all", "schedule": crontab(hour=3, minute=15)}   # a small task that runs the command

# config/urls.py
path("api/billing/", include("billing_stripe.urls")),
```


## The Django API › The store

The database store has the same methods as the in-memory one the tests use. Two of them deserve a look because they are where correctness lives. `grant_credits` relies on the **unique reference** to make a second grant impossible. `begin_event` takes a row lock and uses the unique event id, so two workers that receive the same event at the same moment cannot both run it:

**billing_stripe/store.py**

```
    def grant_credits(self, user_id, amount: int, ref: str) -> bool:
        _, created = CreditGrant.objects.get_or_create(ref=ref, defaults={"user_id": user_id, "amount": amount})
        return created                                           # the unique ref makes this safe to repeat

    def reverse_credits(self, ref: str) -> bool:
        return CreditGrant.objects.filter(ref=ref, reversed=False).update(reversed=True) == 1

    def credit_balance(self, user_id) -> int:
        total = CreditGrant.objects.filter(user_id=user_id, reversed=False).aggregate(t=Sum("amount"))["t"]
        return total or 0

    # ---- the webhook event log ----------------------------------------------------------------
    @transaction.atomic
    def begin_event(self, event_id: str, event_type: str, now: float, lease_seconds: int = 300) -> str:
        event, created = WebhookEvent.objects.select_for_update().get_or_create(
            event_id=event_id, defaults={"event_type": event_type, "status": "processing", "started_at": now})
        if created:
            return "run"
        if event.status in {"processed", "ignored"}:
            return "duplicate"
        if event.status == "processing" and now - event.started_at < lease_seconds:
            return "busy"
        event.status, event.started_at, event.attempts = "processing", now, event.attempts + 1
        event.save(update_fields=["status", "started_at", "attempts"])
        return "run"

    def finish_event(self, event_id: str, status: str, error: str = "") -> None:
        WebhookEvent.objects.filter(event_id=event_id).update(status=status, error=error[:300])
```

> **The webhook route and your infrastructure**
>
> **The raw body must reach Django unchanged.** A reverse proxy that rewrites or recompresses the body, a middleware that reads and re-encodes it, or a framework layer that parses JSON first will all make valid signatures fail. If every delivery returns `400` in production and the Stripe CLI worked locally, look at what sits between Stripe and Django before you look at the secret. Also keep the webhook URL out of rate limits that would block Stripe's servers, and make sure the signing secret in production is the one for **that** endpoint.


## The Web Frontend (Next.js) › Three small pieces

- **A typed API module** (`lib/billing.ts`): `getStatus`, `startCheckout`, `openPortal`, `syncCheckout`, `cancelSubscription`. `startCheckout` asks your server for a Checkout Session and sends the browser to its URL. Stripe.js is not even required for the hosted page.
- **The billing page**: shows the plan and the reason, a warning when the status is `past_due`, plan buttons for free users and a "Manage subscription" button for paying ones. Buttons are disabled while a request is running, so a double click cannot start two checkouts (the server's idempotency key is the second line of defence).
- **The success page**: Stripe redirects here with `?session_id=...`. The page calls `syncCheckout`, which makes your **server** read the session from Stripe, and shows "Thank you" only when the answer says so. For a delayed payment method it polls the status for a few seconds and then says the payment is still being confirmed. It never decides anything from the URL itself.
**frontend/billing.ts (not executed here)**

```
// lib/billing.ts: typed calls to the Django billing API. apiFetch is the authenticated fetch
// wrapper from the earlier frontend chapters (it adds the token and handles 401). Not executed here.
import { apiFetch } from "@/lib/api";

export type PlanKey = "pro_monthly" | "pro_yearly" | "team_monthly" | "credits_100";

export interface BillingStatus {
  paid: boolean;
  tier: "free" | "pro" | "team";
  reason: string;
  until: number | null;     // unix seconds
  status: string | null;
  credits: number;
}

export const getStatus = () => apiFetch<BillingStatus>("/api/billing/status/");

export async function startCheckout(plan: PlanKey): Promise<void> {
  const { url } = await apiFetch<{ url: string }>("/api/billing/checkout/", { method: "POST", body: { plan } });
  window.location.assign(url);          // the hosted Checkout page: Stripe.js is not even needed
}

export async function openPortal(): Promise<void> {
  const { url } = await apiFetch<{ url: string }>("/api/billing/portal/", { method: "POST" });
  window.location.assign(url);
}

export const syncCheckout = (sessionId: string) =>
  apiFetch<{ paid: boolean; tier: string; credits: number }>("/api/billing/sync/", {
    method: "POST",
    body: { session_id: sessionId },
  });

export const cancelSubscription = () => apiFetch("/api/billing/cancel/", { method: "POST", body: {} });
export const resumeSubscription = () => apiFetch("/api/billing/resume/", { method: "POST", body: {} });
```

**frontend/BillingPage.tsx (not executed here)**

```
// app/billing/page.tsx: shows the plan, offers upgrades and opens the customer portal. Not executed here.
"use client";

import { useEffect, useState } from "react";
import { BillingStatus, PlanKey, getStatus, openPortal, startCheckout } from "@/lib/billing";

const PLANS: { key: PlanKey; name: string; note: string }[] = [
  { key: "pro_monthly", name: "Pro, monthly", note: "14-day free trial" },
  { key: "pro_yearly", name: "Pro, yearly", note: "two months free" },
  { key: "team_monthly", name: "Team", note: "shared workspace and SSO" },
];

export default function BillingPage() {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { getStatus().then(setStatus).catch(() => setError("Could not load your plan.")); }, []);

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label); setError(null);
    try { await action(); }                       // on success the browser leaves for Stripe
    catch (e) { setError(e instanceof Error ? e.message : "Something went wrong."); setBusy(null); }
  }

  if (!status) return <p>{error ?? "Loading…"}</p>;
  const until = status.until ? new Date(status.until * 1000).toLocaleDateString() : null;

  return (
    <main>
      <h1>Billing</h1>
      <p>
        Your plan: <strong>{status.tier}</strong> ({status.reason}{until ? `, until ${until}` : ""})
      </p>
      {status.status === "past_due" && <p role="alert">Your last payment failed. Update your card in the portal.</p>}

      {status.paid ? (
        <button disabled={busy !== null} onClick={() => run("portal", openPortal)}>
          {busy === "portal" ? "Opening…" : "Manage subscription"}
        </button>
      ) : (
        PLANS.map((p) => (
          <button key={p.key} disabled={busy !== null} onClick={() => run(p.key, () => startCheckout(p.key))}>
            {busy === p.key ? "Redirecting…" : `${p.name}: ${p.note}`}
          </button>
        ))
      )}
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
```

**frontend/SuccessPage.tsx (not executed here)**

```
// app/billing/success/page.tsx: where Stripe sends the customer after paying.
// The page never trusts the URL: it asks OUR server, which asks Stripe. Not executed here.
"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getStatus, syncCheckout } from "@/lib/billing";

export default function SuccessPage() {
  const sessionId = useSearchParams().get("session_id");
  const [state, setState] = useState<"checking" | "ready" | "pending" | "error">("checking");

  useEffect(() => {
    if (!sessionId) { setState("error"); return; }
    let cancelled = false;
    (async () => {
      try {
        const first = await syncCheckout(sessionId);            // reads the session from Stripe, server side
        if (first.paid || first.credits > 0) { if (!cancelled) setState("ready"); return; }
        for (let i = 0; i < 8 && !cancelled; i++) {             // a delayed payment method: poll the status
          await new Promise((r) => setTimeout(r, 2000));
          if ((await getStatus()).paid) { setState("ready"); return; }
        }
        if (!cancelled) setState("pending");
      } catch { if (!cancelled) setState("error"); }
    })();
    return () => { cancelled = true; };
  }, [sessionId]);

  if (state === "ready") return <p>Thank you! Your plan is active.</p>;
  if (state === "pending") return <p>Your payment is still being confirmed. We will email you when it is done.</p>;
  if (state === "error") return <p role="alert">We could not confirm your payment. If you were charged, contact support.</p>;
  return <p>Confirming your payment…</p>;
}
```


## The Mobile App (React Native) › What the app does in this chapter

The app reads the plan from your server (`mobile/billing.ts`). Where link-outs are allowed, it can open the customer portal in the system browser to manage an existing subscription. And for real-world purchases it can use Stripe's native **Payment Sheet**. The sheet needs three things from your server, created by one endpoint: a PaymentIntent (with the amount decided on the server, from a catalog that holds only real-world items), an **ephemeral key** that lets the sheet read and save the customer's cards, and the customer id. The key must be created with the API version that the mobile SDK uses, so keep that version in a setting and check the SDK's documentation when you upgrade it:

**billing_stripe/views.py (the Payment Sheet endpoint)**

```
# What the mobile app may buy with the Payment Sheet. The amounts live HERE, on the server.
# Only real-world goods and services belong in this table (see the store-rules box in section 36.9).
MOBILE_CATALOG = {"consulting_hour": {"amount": 15000, "currency": "usd", "description": "One hour of consulting"}}

class PaymentSheetView(BillingView):
    """Creates what the mobile Payment Sheet needs: a PaymentIntent, an ephemeral key and the customer id."""

    def post(self, request):
        item = MOBILE_CATALOG.get(request.data.get("item", ""))
        if item is None:
            return Response({"detail": "Unknown item."}, status=400)
        service, user = get_service(), billing_user(request)
        customer = service.customer_id(user)
        intent = service.gateway.create_payment_intent(
            payment_intent_params(customer_id=customer, user_id=user.id, **item),
            idempotency_key("pi", user.id, request.data["item"], int(time.time() // 300)))
        key = service.gateway.create_ephemeral_key(customer, settings.STRIPE_MOBILE_API_VERSION)
        return Response({"paymentIntent": intent["client_secret"], "ephemeralKey": key["secret"],
                         "customer": customer, "publishableKey": settings.STRIPE_PUBLISHABLE_KEY},
                        status=status.HTTP_201_CREATED)
```

**mobile/PayWithPaymentSheet.tsx (not executed here)**

```
// mobile/PayWithPaymentSheet.tsx: Stripe's native Payment Sheet for REAL-WORLD goods and services only.
// Digital features and subscriptions inside the app are governed by the store rules (section 36.9).
// npm install @stripe/stripe-react-native. Not executed here.
import { StripeProvider, useStripe } from "@stripe/stripe-react-native";
import { useState } from "react";
import { Alert, Button } from "react-native";
import { apiFetch } from "./api";

function BuyButton({ item }: { item: string }) {
  const { initPaymentSheet, presentPaymentSheet } = useStripe();
  const [busy, setBusy] = useState(false);

  async function pay() {
    setBusy(true);
    try {
      // 1. Our server decides the amount and creates the PaymentIntent, the customer key and the customer.
      const s = await apiFetch<{ paymentIntent: string; ephemeralKey: string; customer: string }>(
        "/api/billing/payment-sheet/", { method: "POST", body: { item } });
      // 2. Prepare the sheet.
      const init = await initPaymentSheet({
        merchantDisplayName: "AI Chat",
        customerId: s.customer,
        customerEphemeralKeySecret: s.ephemeralKey,
        paymentIntentClientSecret: s.paymentIntent,
        allowsDelayedPaymentMethods: false,
        returnURL: "aichat://stripe-redirect",      // for payment methods that leave the app and come back
      });
      if (init.error) throw new Error(init.error.message);
      // 3. Show it. The card details go from the sheet straight to Stripe, never through our app code.
      const result = await presentPaymentSheet();
      if (result.error) {
        if (result.error.code !== "Canceled") Alert.alert("Payment failed", result.error.message);
        return;
      }
      Alert.alert("Thank you!", "Your payment was received."); // the webhook, not this line, records it
    } catch (e) {
      Alert.alert("Something went wrong", e instanceof Error ? e.message : "Try again.");
    } finally {
      setBusy(false);
    }
  }
  return <Button title={busy ? "Please wait…" : "Pay"} disabled={busy} onPress={pay} />;
}

export default function Screen({ publishableKey }: { publishableKey: string }) {
  return (
    <StripeProvider publishableKey={publishableKey} urlScheme="aichat">
      <BuyButton item="consulting_hour" />
    </StripeProvider>
  );
}
```

**mobile/billing.ts (not executed here)**

```
// mobile/billing.ts: the mobile app reads the plan from YOUR server. Not executed here.
import * as Linking from "expo-linking";
import { apiFetch } from "./api";

export type Status = { paid: boolean; tier: string; reason: string; until: number | null };
export const getStatus = () => apiFetch<Status>("/api/billing/status/");

// Opens the customer portal in the system browser (change card, see invoices, cancel).
// Managing an existing subscription is fine on both stores.
export async function manageSubscription() {
  const { url } = await apiFetch<{ url: string }>("/api/billing/portal/", { method: "POST" });
  await Linking.openURL(url);
}
```

Note the last comment in the sheet code: "the webhook, not this line, records it". The sheet reports success to the app, but your server learns about the payment from the signed event, exactly as on the web. The PaymentIntent's metadata carries the user id, and the `payment_intent.succeeded` handler records the purchase (once, and only for intents that carry our user id). The apps also need their platform setup: the URL scheme for payment methods that leave the app and return, Apple Pay's merchant id and the Google Pay settings, all of which are in Stripe's mobile documentation and need real devices to test.


## Testing and Going Live › Four layers of testing

| **Layer** | **What it covers** | **How** |
|---|---|---|
| **Unit tests** | The plan table, request builders, access decision, signature check, processor and handlers | `python -m unittest stripebilling.test_stripebilling`: instant, free, on every push |
| **The simulator** | A whole lifecycle and hostile deliveries through the real processor | `python -m stripebilling.cli simulate` and `attacks` |
| **Test mode with the Stripe CLI** | Real Stripe objects, real signatures, your real endpoint on your laptop | `stripe listen`, test cards, the portal |
| **Test clocks** | Time: trial end, renewal, failed renewal, cancellation | Create a customer on a test clock in the Dashboard and move the clock forward |

The scenarios worth walking through by hand in test mode, each ending with a look at the subscription row and the event table:

- Subscribe with `4242 4242 4242 4242`, with and without a trial.
- Subscribe with a card that needs 3-D Secure, and fail the authentication.
- Let a renewal fail (the card that attaches but then declines), watch the status go `past_due`, then pay and watch it recover.
- Cancel at the period end in the portal, then resume, then cancel again and move a test clock past the end.
- Upgrade and downgrade, and read the proration lines on the invoice.
- Buy a credit pack, refund it in the Dashboard, and check that the credits are reversed.
- Stop your server during a payment, start it again and use `stripe_replay` or `stripe events resend` to recover.
- Pay on the success page URL with a session id from another user (it must be refused).

## Testing and Going Live › Going live

Going live is a checklist, not a code change. The mode is chosen by the keys, so a live environment has live keys, live price ids and a live webhook secret, and nothing from test mode:

- **Activate the account** (business details, bank account, identity checks). Until it is active you cannot take live payments.
- **Recreate the products and prices in live mode**, and put the new price ids in the live environment's variables.
- **Create the live webhook endpoint** in the Dashboard with the **same API version as your SDK** and exactly the events from 36.6, then store its new `whsec_` secret.
- **Configure the live customer portal**, the receipt and invoice emails, the retry settings and your branding and support details.
- **Put the live keys in your secrets manager**, not in a file in the repository (Chapter 40).
- **Make one small real payment and refund it**, as the final test of the whole chain.
- **Add monitoring**: alert on webhook events in the `failed` state, on events stuck in `processing`, on a rise in `400` answers from the endpoint (a wrong secret) and on a rise in `past_due` subscriptions. The Dashboard's webhook page shows every delivery and its answer, and it is the first place to look.
- **Keep a switch.** A feature flag that hides the buy buttons lets you stop new purchases in a minute if something is wrong, without touching existing subscribers.