"""The database version of stripebilling.store.InMemoryBillingStore: the same methods."""
from dataclasses import fields
from typing import Optional

from django.db import transaction
from django.db.models import Sum

from stripebilling.store import PaymentRecord, SubscriptionRecord

from .models import CreditGrant, StripeCustomer, StripePayment, StripeSubscription, WebhookEvent

_SUB_FIELDS = [f.name for f in fields(SubscriptionRecord) if f.name != "user_id"]


class DjangoBillingStore:
    # ---- customers --------------------------------------------------------------------------
    def customer_id_for(self, user_id) -> Optional[str]:
        return StripeCustomer.objects.filter(user_id=user_id).values_list("customer_id", flat=True).first()

    def user_id_for_customer(self, customer_id: str) -> Optional[str]:
        found = StripeCustomer.objects.filter(customer_id=customer_id).values_list("user_id", flat=True).first()
        return str(found) if found is not None else None

    def link_customer(self, user_id, customer_id: str) -> str:
        obj, _ = StripeCustomer.objects.get_or_create(user_id=user_id, defaults={"customer_id": customer_id})
        return obj.customer_id                                   # the first link wins

    # ---- subscriptions ----------------------------------------------------------------------
    def subscription_for(self, user_id) -> Optional[SubscriptionRecord]:
        row = StripeSubscription.objects.filter(user_id=user_id).first()
        if row is None:
            return None
        return SubscriptionRecord(user_id=str(row.user_id), **{name: getattr(row, name) for name in _SUB_FIELDS})

    def save_subscription(self, record: SubscriptionRecord) -> None:
        values = {name: getattr(record, name) for name in _SUB_FIELDS}
        StripeSubscription.objects.update_or_create(user_id=record.user_id, defaults=values)

    def has_used_trial(self, user_id) -> bool:
        return StripeCustomer.objects.filter(user_id=user_id, trial_used=True).exists()

    def mark_trial_used(self, user_id) -> None:
        StripeCustomer.objects.filter(user_id=user_id).update(trial_used=True)

    # ---- payments and credits -----------------------------------------------------------------
    def payment(self, ref: str) -> Optional[PaymentRecord]:
        row = StripePayment.objects.filter(ref=ref).first()
        return PaymentRecord(row.ref, str(row.user_id), row.kind, row.amount, row.currency, row.status,
                             row.fulfil_ref, row.receipt_url) if row else None

    def save_payment(self, record: PaymentRecord) -> None:
        StripePayment.objects.update_or_create(ref=record.ref, defaults={
            "user_id": record.user_id, "kind": record.kind, "amount": record.amount, "currency": record.currency,
            "status": record.status, "fulfil_ref": record.fulfil_ref, "receipt_url": record.receipt_url})

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

    def event(self, event_id: str) -> Optional[dict]:
        row = WebhookEvent.objects.filter(event_id=event_id).values("status", "attempts", "error").first()
        return row
