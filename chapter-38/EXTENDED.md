# Chapter 38 — Running Both Gateways Together: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## The Architecture: One Interface, Two Adapters › Assumptions from Chapters 35 to 37

Chapters 35 to 37 were written before this one, so the code below depends on only these few names. If yours differ, change them in one place each:

- `billing.services.price_for(plan_code, currency)` returns the **server-side** price as a `Money`. The client never sends an amount.
- `billing.services.describe_purchase(payment)` returns the text for the invoice line.
- `billing.services.activate_for_payment(payment)` grants the plan or credits. It must be **idempotent** (running it twice for one payment changes nothing).
- The `audit` app from Chapter 17 is present. Add these actions to its `Action` enum: `PAYMENT_SUCCEEDED`, `PAYMENT_REFUND_REQUESTED`, `PAYMENT_DISPUTED`.
- Settings: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `PAYSTACK_SECRET_KEY` (all from the environment, as in Chapter 17), `PAYMENT_GATEWAYS` (which are enabled), `FRONTEND_URL`, `INVOICE_PREFIX`, `SELLER_DETAILS`, `TAX_RATE_BP` and `PRICES_INCLUDE_TAX`.
- Subscriptions (renewals, trials, plan changes) stay in Chapters 36 and 37. This chapter’s layer handles each **charge**, refund and invoice, and normalizes subscription events so your billing code receives one event shape.
The project layout this chapter adds:

**text layout**

```text
core/payments/        plain Python, no Django: money, states, gateway, webhooks, normalize, routing,
                      checkout, events, refunds, invoices, reconciliation, fakes, memory
core/test_payments.py 71 unittest tests
payments/             Django app: models, repo, registry, services, views, tasks, admin, urls, tests
payments/gateways/    stripe_gw.py, paystack_gw.py (the only files that import a provider SDK or API)
```

The rule that keeps the layer clean is simple: **only** `payments/gateways/` **may import** `stripe` **or know a Paystack URL.** A code review can enforce that with one search.


## Money and the Payment Lifecycle › Money is an integer

Payment APIs deal in the smallest currency unit: 5,000 naira is `500000` kobo. The most common billing bug in the world is a float: `0.1 + 0.2` is not `0.3`, and a rounding error of one kobo on every payment becomes a finance team’s nightmare. Our `Money` type stores an integer, refuses floats, and refuses currencies it does not know (a few, such as the yen, have no minor unit at all).

**python core/payments/money.py**

```python
"""Money as integers in the smallest unit. Floats never touch an amount."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Digits after the decimal point. Unknown currencies are refused, not guessed.
EXPONENTS = {
    "NGN": 2, "GHS": 2, "ZAR": 2, "KES": 2, "USD": 2, "EUR": 2, "GBP": 2,
    "JPY": 0, "KRW": 0, "XOF": 0, "XAF": 0, "RWF": 0,
}

class MoneyError(ValueError):
    pass

@dataclass(frozen=True, order=False)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self):
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise MoneyError("amount_minor must be an int (kobo, cents), never a float")
        if self.currency not in EXPONENTS:
            raise MoneyError(f"unsupported currency {self.currency!r}")

    @classmethod
    def from_major(cls, amount: str | int | Decimal, currency: str) -> "Money":
        """Money.from_major("5000.50", "NGN") -> 500050 kobo. Floats are rejected on purpose."""
        if isinstance(amount, float):
            raise MoneyError("pass a string or Decimal, not a float: 0.1 + 0.2 != 0.3")
        if currency not in EXPONENTS:
            raise MoneyError(f"unsupported currency {currency!r}")
        value = Decimal(str(amount)) * (Decimal(10) ** EXPONENTS[currency])
        if value != value.to_integral_value():
            raise MoneyError(f"{amount} has more decimals than {currency} allows")
        return cls(int(value), currency)

    def to_major(self) -> Decimal:
        return Decimal(self.amount_minor) / (Decimal(10) ** EXPONENTS[self.currency])

    def _same(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise MoneyError(f"cannot mix {self.currency} and {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def is_positive(self) -> bool:
        return self.amount_minor > 0

    def basis_points(self, bp: int) -> "Money":
        """bp=750 is 7.5%. Rounds half up, in integer arithmetic."""
        cents = (Decimal(self.amount_minor) * bp / Decimal(10000)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return Money(int(cents), self.currency)

    def __str__(self) -> str:
        places = EXPONENTS[self.currency]
        return f"{self.currency} {self.to_major():,.{places}f}"
```

**python (real output)**

```python
>>> Money.from_major("5000.50", "NGN")
Money(amount_minor=500050, currency='NGN')      # prints as: NGN 5,000.50
>>> Money.from_major(0.1, "NGN")
MoneyError: pass a string or Decimal, not a float: 0.1 + 0.2 != 0.3
```

The three-decimal currencies (such as the Kuwaiti dinar) and a few special cases at each gateway are deliberately not in the table. If you add one, read both gateways’ rules for it first and write a test.


## Choosing a Gateway: Routing › A circuit breaker for a gateway that is failing

If a gateway has an incident, sending every customer to it for ten minutes is a poor plan. `HealthTracker` is a small circuit breaker: after three failures in 60 seconds the gateway is skipped for two minutes, then one trial request is allowed through. If **every** eligible gateway looks unhealthy we still try rather than refuse, because refusing is certain failure.

**python core/payments/routing.py (excerpt)**

```python
@dataclass
class HealthTracker:
    """A small circuit breaker: after `threshold` failures inside `window` seconds, skip the gateway for `cooldown`."""
    clock: Callable[[], float]
    threshold: int = 3
    window: float = 60.0
    cooldown: float = 120.0
    _failures: dict[str, list[float]] = field(default_factory=dict)
    _open_until: dict[str, float] = field(default_factory=dict)

    def record_failure(self, code: str) -> None:
        now = self.clock()
        recent = [t for t in self._failures.get(code, []) if now - t <= self.window] + [now]
        self._failures[code] = recent
        if len(recent) >= self.threshold:
            self._open_until[code] = now + self.cooldown
            self._failures[code] = []

    def record_success(self, code: str) -> None:
        self._failures.pop(code, None)
        self._open_until.pop(code, None)

    def is_open(self, code: str) -> bool:
        until = self._open_until.get(code)
        if until is None:
            return False
        if self.clock() >= until:
            self._open_until.pop(code, None)     # cooldown over: allow a trial request
            return False
        return True
```

The tracker above lives in one process. With several web workers you have several trackers, which is fine for a first version (each learns quickly). If you want one shared view, keep the failure counts in Redis (Chapter 15) behind the same two methods, `record_failure` and `is_open`.

> **Routing is policy, so keep it boring and visible**
>
> Put the rules in one small module with tests, as above, and log which gateway was chosen and why (the attempted gateways are stored on the payment). A hidden rule like "send everyone over 100 dollars to Stripe" becomes a mystery three months later. If you want to experiment (a percentage of traffic to a new gateway), add it as an explicit, logged rule.


## Starting a Checkout Safely › The API view and the client

The view requires the header, validates the body, and takes the price from the server. It never accepts an amount:

**python payments/views.py (excerpt)**

```python
class CheckoutSerializer(serializers.Serializer):
    plan_code = serializers.SlugField(max_length=40)
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    country = serializers.RegexField(r"^[A-Z]{2}$", required=False, allow_null=True)
    preferred = serializers.ChoiceField(choices=["stripe", "paystack"], required=False, allow_null=True)

class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "checkout"

    def post(self, request):
        key = request.headers.get("Idempotency-Key", "")
        if not 8 <= len(key) <= 80:
            return Response({"detail": "Send an Idempotency-Key header (8 to 80 characters)."}, status=400)
        data = CheckoutSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            record = services.begin_checkout(user=request.user, idempotency_key=key, **data.validated_data)
        except CheckoutFailed as exc:
            code = 503 if exc.retry_same_key else 400
            return Response({"detail": str(exc), "retry_with_same_key": exc.retry_same_key}, status=code)
        return Response({"payment_id": record.reference, "provider": record.provider, "redirect_url": record.redirect_url},
                        status=status.HTTP_201_CREATED)
```

On the web, create the key once when the user opens the pay screen, and reuse it for retries of that same purchase. A new purchase gets a new key:

**tsx lib/payments.ts**

```tsx
export function newIdempotencyKey(): string {
  return crypto.randomUUID();           // one per purchase attempt, reused for retries of that attempt
}

export async function startCheckout(planCode: string, currency: string, country: string, key: string) {
  const res = await fetch("/api/v1/payments/checkout/", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": key, Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ plan_code: planCode, currency, country }),
  });
  if (res.status === 503) throw new RetryableError("Payment provider is slow. Please try again.");
  if (!res.ok) throw new Error((await res.json()).detail ?? "Could not start payment");
  const { redirect_url, payment_id } = await res.json();
  window.location.assign(redirect_url);   // hosted checkout: card details never touch our servers (see 38.13)
  return payment_id;
}
```

After the customer returns from the hosted page, the screen **polls**  `GET /api/v1/payments/<reference>/` until the status is `succeeded` or `failed`. It does not treat the redirect as proof of payment: anyone can open the return URL by hand. In React Native (Chapter 24) the same flow opens the redirect URL in an in-app browser and returns to the app through a deep link that triggers the same polling.


## Webhooks From Both Gateways › Step 5: apply, with the state machine and an amount check

This function is the same for both gateways, because it only sees `NormalizedEvent`. It returns a short **outcome code** instead of raising, so the webhook can always answer quickly and the code is easy to test:

**python core/payments/events.py (excerpt)**

```python
def apply_event(event: NormalizedEvent, repo: Repo, *, now: datetime) -> str:
    """Return a short outcome code. Raising is reserved for bugs; business surprises are outcomes."""
    if event.type == EventType.IGNORED:
        return "ignored"
    payment = repo.get(event.reference) if event.reference else None
    if payment is None:
        return "unknown_reference"              # keep the raw event; reconciliation will surface it

    if event.type == EventType.PAYMENT_SUCCEEDED:
        if event.amount_minor != payment.amount.amount_minor or event.currency != payment.amount.currency:
            return "amount_mismatch"            # never grant access for the wrong amount
        if payment.status in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED):
            return "already_applied"
        payment.status, payment.paid_at = transition(payment.status, PaymentStatus.SUCCEEDED), now
        repo.save(payment)
        return "fulfilled"

    if event.type == EventType.PAYMENT_FAILED:
        if payment.status == PaymentStatus.PENDING:
            payment.status = transition(payment.status, PaymentStatus.FAILED)
            repo.save(payment)
            return "failed"
        return "late_failure_ignored"           # a success (or later state) outranks a failure

    if event.type == EventType.REFUND_UPDATED:
        if event.amount_minor is None:
            return "ignored"
        total_refunded = event.amount_minor if event.amount_is_cumulative else payment.refunded_minor + event.amount_minor
        total_refunded = min(total_refunded, payment.amount.amount_minor)
        if total_refunded <= payment.refunded_minor:
            return "already_applied"
        payment.refunded_minor = total_refunded
        new = status_after_refund(payment.amount, Money(total_refunded, payment.amount.currency))
        try:
            payment.status = transition(payment.status, new)
        except InvalidTransition:
            return "refund_on_unpaid_payment"
        repo.save(payment)
        return "refund_recorded"

    if event.type == EventType.DISPUTE_OPENED:
        payment.status = transition(payment.status, PaymentStatus.DISPUTED)
        repo.save(payment)
        return "disputed"

    return "no_action"
```

Three rules in it protect the business:

- **Never fulfil for the wrong amount or currency.** If the event says 100 kobo and the payment row says 500,000, the outcome is `amount_mismatch`, nothing is granted, and an error is logged for a human. This stops a tampered or mismatched payment from unlocking a plan.
- **A late failure is ignored** once the payment has succeeded.
- **Refund events are idempotent** whether they carry a running total (Stripe) or a single amount (Paystack): the code computes the new total, caps it at the payment amount, and does nothing if it has already recorded that much.

## Webhooks From Both Gateways › Step 6: side effects after the commit, then answer

Granting the plan, issuing the invoice and sending the receipt happen in a Celery task queued with `transaction.on_commit`, so they only run if the database change really committed. The task is safe to run twice, because activation is keyed by the payment reference and the invoice task checks whether one exists.

What does the endpoint answer? Use the status code to tell the gateway whether to retry:

| **Situation** | **Response** | **Why** |
|---|---|---|
| **Signature invalid** | 400 | Not from the gateway; retrying will not help |
| **Valid, processed** | 200 | Done |
| **Valid, duplicate** | 200 | Already done; tell the gateway to stop |
| **Valid, unknown reference** | 200 (and keep the stored event) | Retrying cannot fix it; reconciliation will surface it |
| **Our database is down** | 500 | The gateway will retry later (Stripe retries for up to three days; Paystack retries on a schedule) |


## Refunds › Retries without double refunds

The danger is a refund request that times out. Did it go through? If staff click again and we send a second refund, the customer is refunded twice. We prevent it with a **deterministic idempotency key** built from the payment reference, the amount already refunded and the amount requested: the same request in the same state always produces the same key.

**python (real output)**

```python
>>> refund_idempotency_key("pay_1", already_refunded=NGN(0), requested=NGN(10))
'refund:pay_1:0:1000'       # retrying gives the identical key, so a second click cannot refund twice
```

The Django service stores a `Refund` row with that key as a unique value **before** calling the gateway. If the gateway call fails definitely, the row is marked failed. If it is uncertain, the row stays `requested`, a retry finds it, and the gateway (Stripe honours the key itself; for Paystack our unique row is the guard) sees the same request:

**python payments/services.py (excerpt)**

```python
def refund_payment(*, staff_user, payment: Payment, amount: Money, reason: str, override: bool = False) -> Refund:
    """Validate, record the intent, call the gateway, and let the webhook confirm. Safe to retry."""
    with transaction.atomic():
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        total, done = Money(locked.amount_minor, locked.currency), Money(locked.refunded_minor, locked.currency)
        validate_refund(status=PaymentStatus(locked.status), paid_at=locked.paid_at, now=timezone.now(), total=total,
                        already_refunded=done, requested=amount, policy=RefundPolicy(), staff_override=override)
        key = refund_idempotency_key(locked.reference, done, amount)
        refund, created = Refund.objects.get_or_create(
            idempotency_key=key, defaults={"payment": locked, "amount_minor": amount.amount_minor, "reason": reason[:200],
                                           "requested_by": staff_user})
    if not created and refund.status in ("submitted", "succeeded"):
        return refund                                    # a retry of something already sent
    gateway = get_gateways()[locked.provider]
    try:
        result = gateway.refund(reference=locked.reference, provider_ref=locked.provider_ref, amount=amount, idempotency_key=key)
    except GatewayRejected:
        refund.status = "failed"; refund.save(update_fields=["status"])
        raise
    except GatewayUncertain:
        raise                                            # leave it "requested"; reconciliation or a retry settles it
    refund.status, refund.provider_ref = "submitted", result.provider_ref
    refund.save(update_fields=["status", "provider_ref"])
    audit(Action.PAYMENT_REFUND_REQUESTED, actor=staff_user, metadata={"payment": locked.reference, "amount": amount.amount_minor})
    return refund
```

After the call, the refund is `submitted`, not done. The truth arrives in the webhook (`charge.refunded` for Stripe, `refund.processed` for Paystack) and goes through the same `apply_event` as every other event. That one path keeps a payment’s refunded total correct no matter whether the news came from our own call or the gateway’s message.

Some practical points to settle with your finance and legal advisers, because they differ by gateway and country: refunds can take days to reach the customer’s account; gateway processing fees are often **not** returned on refunds; and consumer law in some countries sets minimum refund rights (a cooling-off period for digital subscriptions, for example) that your refund window must respect. Write the policy down, show it on the pricing page, and make the code enforce it.

> **Who can refund?**
>
> Money-moving actions need their own permission (Chapter 17’s role design), an audit event with the reason, and for large amounts a second approver. The service above takes the staff user as an argument for exactly this: nobody refunds "as the system".


## Invoices and Receipts › Tax arithmetic that always adds up

Two common pricing styles exist: prices **exclude** tax (the tax is added on top) and prices **include** tax. The functions below do the arithmetic in integers, round half up **once** on the invoice total, and guarantee that net plus tax equals gross for any amount. A property test runs awkward amounts (1, 7, 99, 12,345 kobo) through both styles to prove it.

**python core/payments/invoices.py (excerpt)**

```python
def totals_for(lines: list[Line], rate_bp: int, *, prices_include_tax: bool) -> Totals:
    """Tax is computed once on the invoice total, not per line, so rounding cannot drift."""
    if not lines:
        raise ValueError("an invoice needs at least one line")
    currency = lines[0].unit_price.currency
    subtotal = Money(0, currency)
    for line in lines:
        subtotal = subtotal + line.total
    if prices_include_tax:
        # tax = gross * rate / (1 + rate)
        tax = Money(round_half_up(subtotal.amount_minor * rate_bp, 10000 + rate_bp), currency)
        return Totals(net=subtotal - tax, tax=tax, gross=subtotal)
    tax = subtotal.basis_points(rate_bp)
    return Totals(net=subtotal, tax=tax, gross=subtotal + tax)

def credit_note_totals(original: Totals, refund_gross: Money) -> Totals:
    """Split a refund into net and tax in the same proportion as the invoice. The parts always add up."""
    if refund_gross.amount_minor > original.gross.amount_minor:
        raise ValueError("a credit note cannot exceed the invoice")
    if original.gross.amount_minor == 0:
        return Totals(refund_gross, Money(0, refund_gross.currency), refund_gross)
    tax = Money(round_half_up(original.tax.amount_minor * refund_gross.amount_minor,
                              original.gross.amount_minor), refund_gross.currency)
    return Totals(net=refund_gross - tax, tax=tax, gross=refund_gross)
```

**python (real output)**

```python
>>> totals = totals_for([Line("Pro plan (monthly)", 1, NGN("10000"))], 750, prices_include_tax=False)
>>> totals.net, totals.tax, totals.gross
(NGN 10,000.00, NGN 750.00, NGN 10,750.00)           # 7.5% VAT = 750 basis points
>>> credit_note_totals(totals, NGN("2500"))             # a credit note for a NGN 2,500 refund
Totals(net=NGN 2,325.58, tax=NGN 174.42, gross=NGN 2,500.00)
>>> invoice_number("INV", 2026, 123)
'INV-2026-000123'
```

Notice the credit note: the refund of a gross amount is split into net and tax **in the same proportion as the original invoice**, and the parts add up exactly (2,325.58 + 174.42 = 2,500.00).

> **Tax is a rate you configure, not a constant you hardcode**
>
> The example uses 7.5%, which was Nigeria’s standard VAT rate in 2026 under the Nigeria Tax Act 2025 (in force from 1 January 2026, with the Nigeria Revenue Service replacing the FIRS as the tax authority). That Act also expects non-resident suppliers of digital services to Nigerian customers to register for and charge VAT, and the revenue service has been rolling out e-invoicing, starting with large taxpayers. Rates, thresholds and rules differ by country and change, and selling to the EU, the UK or US states brings other regimes. The code takes `TAX_RATE_BP` from settings so a rate change is a configuration change. Ask an accountant which taxes apply to you, whether you must register, and what your invoices must show.


## Invoices and Receipts › Privacy and invoices

An invoice contains personal data, but you must keep it for years. Chapter 34 resolved this tension: keep the invoice, remove the person. The invoice stores a **snapshot** of the buyer’s details, and when the person is erased, the eraser from Chapter 34 must clear the snapshot and the payment’s billing fields while leaving the amounts, dates and numbers. Update that eraser now (the queryset `update()` call bypasses the immutability guard on purpose, and is the only place that should):

**python privacy/erasers.py (update from Chapter 34)**

```python
def _anonymize_billing(public_id: str) -> int:
    """Invoices must be kept for tax law, so keep the amounts and drop the person."""
    Payment = apps.get_model("payments", "Payment")
    Invoice = apps.get_model("payments", "Invoice")
    cleared = Payment.objects.filter(user__public_id=public_id).update(
        billing_name="", billing_email="", billing_address="")
    Invoice.objects.filter(payment__user__public_id=public_id).update(buyer_snapshot={})
    return cleared
```

Also add two retention rules to `core/responsible/retention.py` and the data inventory: **webhook payloads** (30 days, because they contain emails; the outcome and ids can stay) and **invoices** (already 7 years, check your country). And when you extend the data export (34.6), map `amount_minor` to the `amount` field the export expects, so a person’s download shows what they paid.


## Disputes and Chargebacks

A **chargeback** happens when a customer asks their bank to reverse a card payment. The gateway tells you by webhook (Stripe sends `charge.dispute.created`), takes the amount from your balance immediately, and gives you a deadline to submit evidence. Our normalized layer reacts to the first part: the payment moves to `DISPUTED`, which blocks refunds (you must not refund a payment that is also being charged back) and notifies staff.

- **Respond inside the deadline.** Evidence usually includes the invoice, proof of access to the service (login and usage logs, which your audit trail from Chapter 17 provides), the terms the customer accepted (Chapter 34’s versioned documents) and your refund policy.
- **Prevent them.** A clear billing descriptor on the card statement, easy cancellation, prompt refunds, and receipts that arrive by email all reduce "I don’t recognise this charge" disputes.
- **Watch the ratio.** Card networks monitor dispute rates, and a high rate can lead to extra fees or a lost account, so track disputes per thousand payments as a metric (Chapter 44).

## Payment Security and Compliance Basics › Protect the keys

| **Practice** | **Why** |
|---|---|
| **Secret keys only on the server, from the environment** | A key in a mobile app or a web bundle is public. Chapter 17 set the rule: secrets never in the repository or the client |
| **Separate test and live keys and webhook secrets** | A test deployment must be unable to touch real money |
| **Use restricted keys where the gateway offers them** | An integration that only creates sessions does not need to refund or read all customers |
| **Rotate on a schedule and on any suspicion** | Both gateways let you roll a key; practise it. If a key leaks, rotate first, investigate second |
| **Alert on live-key use in non-production** | A misconfiguration should be loud |


## Payment Security and Compliance Basics › Tie it to the privacy work

- **Minimize.** Store the gateway’s references, status, amounts and the last four digits. Do not store full card numbers, CVV or raw authorization data. (Chapter 34’s `never_store` list includes financial account numbers.)
- **Retain and erase.** Invoices are kept for the legal period, with the buyer snapshot cleared when the person is erased (38.10). Webhook payloads expire after 30 days.
- **Export.** A person’s data export includes their payments and invoices (amount, currency, status, date).
- **Disclose.** The Privacy Policy names both gateways as recipients of payment data, and says where they process it.
- **Audit.** Record who refunded what, who changed a price, who resolved a discrepancy.