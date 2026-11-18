"""The database version of paystackbilling.store.InMemoryBillingStore: the same methods."""
from dataclasses import fields
from typing import Optional

from django.db import transaction
from django.db.models import Sum

from paystackbilling.store import PaymentRecord, PendingTransaction, SubscriptionRecord

from .models import (CreditGrant, PaystackCustomer, PaystackPayment, PaystackSubscription,
                     PendingTransaction as PendingRow, WebhookEvent)

_SUB_FIELDS = [f.name for f in fields(SubscriptionRecord) if f.name != "user_id"]
_PENDING_FIELDS = [f.name for f in fields(PendingTransaction) if f.name != "reference"]


class DjangoBillingStore:
    def customer_code_for(self, user_id) -> Optional[str]:
        return PaystackCustomer.objects.filter(user_id=user_id).values_list("customer_code", flat=True).first()

    def user_id_for_customer(self, customer_code: str) -> Optional[str]:
        found = PaystackCustomer.objects.filter(customer_code=customer_code).values_list("user_id", flat=True).first()
        return str(found) if found is not None else None

    def link_customer(self, user_id, customer_code: str) -> str:
        obj, _ = PaystackCustomer.objects.get_or_create(user_id=user_id, defaults={"customer_code": customer_code})
        return obj.customer_code

    def save_pending(self, pending: PendingTransaction) -> None:
        PendingRow.objects.create(reference=pending.reference, **{f: getattr(pending, f) for f in _PENDING_FIELDS})

    def pending(self, reference: str) -> Optional[PendingTransaction]:
        row = PendingRow.objects.filter(reference=reference).first()
        if row is None:
            return None
        values = {f: getattr(row, f) for f in _PENDING_FIELDS}
        values["user_id"] = str(row.user_id)
        return PendingTransaction(reference=row.reference, **values)

    def set_pending_status(self, reference: str, status: str) -> None:
        PendingRow.objects.filter(reference=reference).update(status=status)

    def list_pending(self, *, created_before: float, created_after: float) -> list:
        rows = PendingRow.objects.filter(status="pending", created_at__lte=created_before, created_at__gte=created_after)
        return [self.pending(r.reference) for r in rows]

    def subscription_for(self, user_id) -> Optional[SubscriptionRecord]:
        row = PaystackSubscription.objects.filter(user_id=user_id).first()
        if row is None:
            return None
        return SubscriptionRecord(user_id=str(row.user_id), **{f: getattr(row, f) for f in _SUB_FIELDS})

    def save_subscription(self, record: SubscriptionRecord) -> None:
        PaystackSubscription.objects.update_or_create(
            user_id=record.user_id, defaults={f: getattr(record, f) for f in _SUB_FIELDS})

    def has_used_trial(self, user_id) -> bool:
        return PaystackCustomer.objects.filter(user_id=user_id, trial_used=True).exists()

    def mark_trial_used(self, user_id) -> None:
        PaystackCustomer.objects.filter(user_id=user_id).update(trial_used=True)

    def payment(self, ref: str) -> Optional[PaymentRecord]:
        row = PaystackPayment.objects.filter(ref=ref).first()
        return PaymentRecord(row.ref, str(row.user_id), row.kind, row.amount, row.currency, row.status) if row else None

    def save_payment(self, record: PaymentRecord) -> None:
        PaystackPayment.objects.update_or_create(ref=record.ref, defaults={
            "user_id": record.user_id, "kind": record.kind, "amount": record.amount,
            "currency": record.currency, "status": record.status})

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

    def event(self, event_key: str) -> Optional[dict]:
        return WebhookEvent.objects.filter(event_key=event_key).values("status", "attempts", "error").first()
