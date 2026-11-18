# Chapter 35 — Designing a Pricing and Billing System: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Choosing a Pricing Model › Credits and top-ups

**Prepaid credits** let a customer buy a pack and spend it. They suit occasional users and markets where card subscriptions are less common, but they bring obligations: unused credits may need an expiry date, refunds need rules, and a balance can count as money you owe. Ask an accountant before you sell credits. In this chapter's data model, a limited-time bonus can be given with an `EntitlementOverride` (section 35.3). A true wallet with balances and expiry needs its own ledger, which Exercise 3 asks you to design.

> **Pricing in naira and in dollars**
>
> If you sell in both currencies, give each plan **one** `Price` **row per currency** and set each price deliberately, instead of converting a dollar price at today's exchange rate. A plan priced at "about $5" that drifts to a different naira amount every week confuses customers, breaks provider plans that expect a fixed amount, and makes your revenue harder to predict. Review local prices on a schedule (for example quarterly) and add a new `Price` row when you change one. Chapters 36 and 37 cover which currencies each provider supports and how each handles them; check each provider's current documentation before you commit to a currency.


## Choosing a Pricing Model › Where to start

| **If your product is...** | **Start with...** |
|---|---|
| A tool people use a little every day, with predictable AI use | Subscription with a message allowance; the plan sets the model |
| Heavy, uneven use (some customers use 100 times more than others) | Hybrid: allowance plus overage, with a weight on expensive requests |
| Bought occasionally for one job (a report, a document) | Prepaid credits or a one-time purchase per job |
| Used by teams, with a few admins and many members | Per-seat subscription, with the AI allowance per seat or per team (Exercise 1) |
| Very new, with no idea yet how customers will use it | A small free tier and one paid plan with a generous cap. Measure first (section 35.9), then refine. |


## The Billing Data Model in Django › Records that describe what happened

A usage event is a fact: this user did this thing at this time at this cost. Facts are not edited. The model refuses to be saved twice or deleted, which makes the ledger trustworthy when a customer disputes a bill:

**billing/models.py (UsageEvent)**

```
class UsageEvent(models.Model):
    """One thing a user did that we may limit or bill. Written once, never changed."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="usage_events"
    )
    key = models.CharField(max_length=60)  # e.g. "ai.message"
    quantity = models.PositiveBigIntegerField(default=1)
    occurred_at = models.DateTimeField()
    # The caller makes this up from something stable (a request id). Same key = same event.
    idempotency_key = models.CharField(max_length=120, unique=True)
    cost_micro_usd = models.PositiveBigIntegerField(
        default=0, help_text="Our cost, in millionths of a dollar."
    )
    meta = models.JSONField(
        default=dict, blank=True
    )  # ids and model names, never message text

    class Meta:
        indexes = [models.Index(fields=["user", "key", "occurred_at"])]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise AppendOnlyError(
                "Usage events are never changed. Add a correcting event instead."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Usage events are never deleted.")
```

Three details matter. The `idempotency_key` is unique, which is how retries are made harmless (section 35.7). `cost_micro_usd` holds what the event cost **you**, in millionths of a dollar, which is what makes the profitability analysis in section 35.9 possible. And `meta` holds ids and model names, never message text: a billing table is a bad place to copy private conversations (Chapters 17 and 34).

> **Do not cascade-delete financial records**
>
> Notice that `Invoice.user` and `Payment.invoice` use `PROTECT`, not `CASCADE`. Deleting a user must not silently delete the invoices that prove what they paid; tax authorities and your accountant may need them. When a user asks you to delete their account (Chapter 34), anonymize the personal fields and keep the financial records, and take advice on how long to keep them.

Finally, the admin. Records that describe what happened (usage, invoices, payments, webhook events) are registered **read-only**, so nobody can change history by accident. Subscription status is read-only too: it changes through the service functions in section 35.6, which enforce the state machine, and not by editing a dropdown.


## Money Rules: Whole Numbers, Currencies, Proration and Tax › Showing money, and adding months

`format_money` turns a whole number into text for a screen or an email, using a table of how many decimal places each currency has. Both of ours have two, but some currencies have none, so never write "divide by 100" anywhere in your code. Chapter 36 shows how Stripe treats such currencies. Never parse the formatted text back into a number: format at the edge, and keep integers inside.

Adding a month sounds trivial until you try it: what is one month after 31 January? `add_months` clamps to the last day of the target month. And, importantly, renewals are always counted **from the original billing date**, not from the previous renewal, so a customer who subscribed on 31 January is billed on the last day of every month, instead of drifting to the 28th forever. A test runs five renewals starting on 31 January and checks that the end dates are 28 February, 31 March, 30 April, 31 May and 30 June.

**billing/pricing.py (add_months)**

```
def add_months(moment: datetime, months: int) -> datetime:
    """Add calendar months, keeping the day where possible (31 January + 1 month = 28 February)."""
    index = moment.month - 1 + months
    year, month = moment.year + index // 12, index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)
```


## Money Rules: Whole Numbers, Currencies, Proration and Tax › Proration: paying for the time that is left

A customer on Starter ($5) upgrades to Pro ($29) halfway through the month. They have already paid for Starter, so they should get credit for the unused half, and pay for the remaining half of Pro. **Proration** does that arithmetic by the share of the period that is left, to the second:

**billing/pricing.py (prorate)**

```
def prorate(
    old_amount_minor: int,
    new_amount_minor: int,
    period_start: datetime,
    period_end: datetime,
    change_at: datetime,
) -> Proration:
    """Price a mid-period plan change by the share of the period still left (to the second)."""
    total = int((period_end - period_start).total_seconds())
    if total <= 0:
        raise ValueError("The period must have a positive length.")
    left = int((period_end - change_at).total_seconds())
    left = max(0, min(left, total))
    credit = _ratio_round(old_amount_minor, left, total)
    charge = _ratio_round(new_amount_minor, left, total)
    return Proration(credit, charge, charge - credit)
```

All the arithmetic is in integers, with rounding half up, so the answer is identical on every machine. The rounding function multiplies first and divides last, which avoids the errors that come from dividing early. Here is the real output from the demo command for an upgrade on 15 February, exactly half of a 28-day period:

**output (billing_demo, section 3)**

```text
3. Ada subscribes to Starter on 1 Feb, then upgrades to Pro halfway through
   period: 01 Feb to 01 Mar, status active
   upgrade now: credit $2.50 for unused Starter, charge $14.50 for the rest on Pro, net $12.00
     Invoice INV-2026-000001
       Unused time on Starter  x1  -$2.50
       Remaining time on Pro  x1  $14.50
       Tax: $0.00
       Total: $12.00
```

The credit is $2.50 (half of $5.00), the charge is $14.50 (half of $29.00), and the customer owes the difference of $12.00 now. If your payment provider does the proration itself (Chapter 36 shows Stripe doing it), you still want this function, to show the customer a preview before they confirm and to check that the provider's figure matches yours.


## The Life of a Subscription › Failed payments and grace periods

Cards fail for ordinary reasons: an expired card, a bank decline, insufficient funds on payday eve. Most failures are fixed within days, so locking a paying customer out on the first failure costs you good customers. Two settings control the tolerance, and both are a business decision, not a technical one:

| **Setting** | **Default** | **What it protects** |
|---|---|---|
| `BILLING_RENEWAL_GRACE_DAYS` | 3 | A paid customer is not locked out because the provider's "payment succeeded" message arrived late. |
| `BILLING_PAST_DUE_GRACE_DAYS` | 7 | A customer whose renewal failed keeps access while the provider retries the card and your reminders go out. |

After the grace window, `effective_plan` returns the Free plan. Nothing is deleted: the customer's data is still there, they just cannot use paid features until they pay. Chapters 36 and 37 describe how each provider retries failed payments; match your grace days to their schedule.


## Feature Gating and Usage Metering › Plugging it into the AI layer

`billing/ai.py` is the small seam between billing and the AI code from Chapters 27 to 30. The plan decides the model, the check runs before the call, and the record runs after it, using the token counts and cost your Chapter 27 code already computes:

**billing/ai.py (excerpt)**

```
def pick_model(user) -> str:
    """The plan decides which model a user gets. Model ids come from settings (Chapter 27)."""
    if has_feature(user, "ai.premium_models"):
        return settings.BILLING_MODEL_PREMIUM
    return settings.BILLING_MODEL_STANDARD

def check_before_model_call(user) -> None:
    """Call this BEFORE paying for a model call. Raises FeatureNotInPlan or LimitExceeded."""
    if not has_feature(user, "ai.chat"):
        raise FeatureNotInPlan(code="feature_not_in_plan")
    check_can_use(user, "ai.message", 1)

def record_ai_message(
    user,
    *,
    request_id: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    conversation_id: Optional[int] = None,
    weight: int = 1,
):
    """Call this AFTER the model answered, with the numbers from Chapter 27's TokenUsage and cost_usd.

    It never refuses: the money is already spent. Ids and counts only, never message text.
    `weight` lets a heavier request count as more than one message: an agent run that made six
    model calls (Chapter 30) can pass weight=6 so the plan limit follows real cost.
    """
    return record_usage(
        user,
        "ai.message",
        weight,
        f"ai-message:{request_id}",
        cost_micro_usd=round(cost_usd * MICRO),
        meta={
            "model": model_id,
            "in": input_tokens,
            "out": output_tokens,
            "conversation": conversation_id,
        },
    )
```

Note `weight`. An assistant run from Chapter 30 can make several model calls for one user request, so it can record `weight=6` and use up six messages of allowance, which keeps the limit honest about cost. And here is how it sits in a chat service (a **pattern**: adapt the names to your Chapter 29 code, which is not shown here):

**chat/services.py (pattern: adapt, not run against your project)**

```
def answer_message(user, conversation, text, request_id):
    check_before_model_call(user)                       # 1. CHECK (refuses early, costs nothing)
    model_id = pick_model(user)                         # the plan decides the model
    reply = call_model(model_id, conversation, text)    # 2. the model call (Chapter 29)
    record_ai_message(                                  # 3. RECORD what happened
        user, request_id=request_id, model_id=model_id,
        input_tokens=reply.usage.prompt_tokens, output_tokens=reply.usage.output_tokens,
        cost_usd=reply.cost_usd, conversation_id=conversation.id,
    )
    return reply
```

> **Make the request id stable across retries**
>
> The idempotency key must come from the **request**, not be generated fresh each time the code runs. If a Celery task retries (Chapter 15) and creates a new random id on every attempt, the same message is counted two or three times. Create the id when the user's request arrives and pass it down.


## Feature Gating and Usage Metering › Gating in the API

Two helpers turn failures into clear API answers. A permission class refuses a request when the plan lacks the feature, with a machine-readable code. An exception handler turns "limit reached" into a clear 403 that carries the numbers a frontend needs to show an upgrade prompt:

**billing/permissions.py**

```
def entitlement_required(key: str):
    """A DRF permission class: `permission_classes = [IsAuthenticated, entitlement_required("ai.agent_tools")]`."""

    class RequiresEntitlement(BasePermission):
        def has_permission(self, request, view) -> bool:
            if not (request.user and request.user.is_authenticated):
                return False
            if not has_feature(request.user, key):
                raise FeatureNotInPlan(code="feature_not_in_plan")
            return True

    RequiresEntitlement.__name__ = f"Requires_{key.replace('.', '_')}"
    return RequiresEntitlement

def billing_exception_handler(exc, context):
    """Turns LimitExceeded into a clear 403 with real numbers.

    Do not put numbers inside an APIException's detail: DRF converts every value in it to text,
    and your frontend would receive "30" instead of 30. Plug this into your Chapter 8 handler by
    calling it first:  response = billing_exception_handler(exc, context)  and returning it if not None.
    """
    from rest_framework.response import Response
    from rest_framework.views import exception_handler

    if isinstance(exc, LimitExceeded):
        # 403 keeps proxies and clients simple. Some APIs use 402 here; pick one and stay consistent.
        return Response(
            {
                "detail": "You have reached your plan's limit.",
                "code": "limit_reached",
                "key": exc.key,
                "limit": exc.limit,
                "used": exc.used,
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return exception_handler(exc, context)
```

**a limit error as the API returns it (shape)**

```
HTTP 403
{
  "detail": "You have reached your plan's limit.",
  "code": "limit_reached",
  "key": "ai.messages_per_month",
  "limit": 30,
  "used": 30
}
```

The handler exists because of a trap this chapter's own tests caught. If you put numbers inside a Django REST Framework exception's `detail`, DRF converts every value to text, and your frontend would receive `"limit": "30"` instead of `30`. A test checks that the response contains a real number. To use the handler with your Chapter 8 error format, call `billing_exception_handler` first inside your own handler and return its response when it is not `None`.

> **The UI hides, the API enforces**
>
> Hide or disable a button the user's plan does not include, so nobody is confused. But the **API must refuse the request** regardless. Anything done in the browser or the mobile app can be bypassed by anyone who can send an HTTP request. A frontend check is courtesy; a backend check is security.

HTTP 403 is used for both "not in your plan" and "limit reached", with a different `code` for each. Some APIs use 402 (Payment Required) for the second. Either is defensible: choose one and use it consistently, because your frontend (Chapters 21 and 25) will branch on it.


## Invoices, Payments and Webhook Events › Recording payments safely

**billing/invoices.py (record_payment)**

```
def record_payment(
    invoice: Invoice,
    *,
    provider: str,
    provider_payment_id: str,
    amount_minor: int,
    currency: str,
    status: str = Payment.Status.SUCCEEDED,
    now: Optional[datetime] = None,
) -> tuple[Payment, bool]:
    """Store a payment once, however many times the provider tells us about it."""
    if currency != invoice.currency:
        raise ValidationError(
            f"Payment is in {currency} but the invoice is in {invoice.currency}."
        )
    now = now or timezone.now()
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        payment, created = Payment.objects.get_or_create(
            provider=provider,
            provider_payment_id=provider_payment_id,
            defaults={
                "invoice": invoice,
                "amount_minor": amount_minor,
                "currency": currency,
                "status": status,
            },
        )
        if (
            created
            and status == Payment.Status.SUCCEEDED
            and invoice.status == Invoice.Status.OPEN
        ):
            paid = sum(
                p.amount_minor
                for p in invoice.payments.filter(status=Payment.Status.SUCCEEDED)
            )
            if paid >= invoice.total_minor:
                invoice.status = Invoice.Status.PAID
                invoice.paid_at = now
                invoice.save(update_fields=["status", "paid_at"])
    return payment, created
```

- **The payment is stored once** however many times the provider reports it, because the provider's payment id is unique. The return value says whether this call created it.
- **The currency must match the invoice**, or the function refuses. A naira payment is never silently counted against a dollar invoice.
- **An invoice is marked paid only when successful payments cover the total.** A partial payment leaves it open, and a failed one never counts. A test breaks this rule on purpose to prove it is checked.
- **The invoice row is locked** while this happens, so two payment messages processed at the same moment cannot both decide they are the last one.
Invoice numbers like `INV-2026-000002` are made when an invoice is issued. In some countries invoice numbers must be consecutive with no gaps, which a database id cannot guarantee (a rolled-back transaction leaves a gap). If that applies to you, a counter table with a row lock does it (Exercise 5). Ask your accountant.


## Invoices, Payments and Webhook Events › Webhook events: store first, act second

A **webhook** is a message a payment provider sends to your server: "this payment succeeded", "this subscription was cancelled". Chapter 36 covers verifying that a message really came from the provider. The data model for handling them safely is the same for every provider, and it is built here. Every message is stored in `WebhookEvent`  **before** anything else happens, with a unique constraint on the provider and the event id. Then a handler runs at most once successfully:

**billing/webhooks.py (process_once)**

```
def process_once(event: WebhookEvent, handler: Callable[[WebhookEvent], None]) -> bool:
    """Run `handler` for this event at most once successfully. Returns True if it ran now.

    The handler and the status change commit together: if the handler raises, nothing it did
    is kept, the event is marked failed, and a later retry may try again.
    """
    with transaction.atomic():
        locked = WebhookEvent.objects.select_for_update().get(pk=event.pk)
        if locked.status == WebhookEvent.Status.PROCESSED:
            return False
        try:
            with transaction.atomic():
                handler(locked)
        except Exception as exc:
            locked.status = WebhookEvent.Status.FAILED
            locked.error = f"{type(exc).__name__}: {exc}"[:300]
            locked.save(update_fields=["status", "error"])
            return False
        locked.status = WebhookEvent.Status.PROCESSED
        locked.processed_at = timezone.now()
        locked.error = ""
        locked.save(update_fields=["status", "processed_at", "error"])
        return True
```

The handler and the status change commit together. If the handler raises, **everything it did is rolled back**, the event is marked `failed` with a short error, and a later retry may try again. A test proves it: a handler that records usage and then crashes leaves no usage behind, and a retry afterwards succeeds. Receiving the same event twice, which providers do by design, runs the handler once.


## Does the Plan Make Money? Unit Economics for AI › Levers when a plan does not make money

| **Lever** | **How it works in this system** |
|---|---|
| **Lower the allowance** | Change the `limit` on the plan's entitlement. No code change. |
| **Use a cheaper model on that plan** | `BILLING_MODEL_STANDARD` and `BILLING_MODEL_PREMIUM` come from settings, and `ai.premium_models` decides who gets which. |
| **Raise the price** | Add a new `Price` row and retire the old one (grandfathering, section 35.3). |
| **Charge for overage** | Fill in `overage_unit_size` and `overage_unit_price_minor` on the price. |
| **Weigh expensive requests** | Record a `weight` greater than 1 for agent runs and long documents. |
| **Cut the cost itself** | Prompt caching and shorter context (Chapter 27), and routing to cheaper models (Chapters 27 and 33). |
| **Offer annual plans** | A yearly `Price` with a discount brings cash in sooner. Model the cost across all twelve months, because heavy months still cost you. |
