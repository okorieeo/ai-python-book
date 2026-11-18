"""Adapter between the pure checkout code and the Django Payment model."""
from core.payments.checkout import PaymentRecord
from core.payments.money import Money
from core.payments.states import PaymentStatus

from .models import Payment


def to_record(p: Payment) -> PaymentRecord:
    return PaymentRecord(reference=p.reference, idempotency_key=p.idempotency_key, user_id=str(p.user_id),
                         amount=Money(p.amount_minor, p.currency), status=PaymentStatus(p.status), provider=p.provider,
                         provider_ref=p.provider_ref, redirect_url=p.redirect_url, attempts=tuple(p.attempts),
                         refunded_minor=p.refunded_minor, paid_at=p.paid_at)


class DjangoPaymentRepo:
    def __init__(self, *, plan_code: str = "", kind: str = "plan", billing_email: str = ""):
        self.plan_code, self.kind, self.billing_email = plan_code, kind, billing_email

    def find_by_key(self, user_id, key):
        p = Payment.objects.filter(user_id=user_id, idempotency_key=key).first()
        return to_record(p) if p else None

    def create(self, record: PaymentRecord) -> PaymentRecord:
        Payment.objects.create(reference=record.reference, user_id=record.user_id, idempotency_key=record.idempotency_key,
                               amount_minor=record.amount.amount_minor, currency=record.amount.currency,
                               plan_code=self.plan_code, kind=self.kind, billing_email=self.billing_email)
        return record

    def get(self, reference):
        p = Payment.objects.filter(reference=reference).first()
        return to_record(p) if p else None

    def save(self, record: PaymentRecord) -> None:
        Payment.objects.filter(reference=record.reference).update(
            status=record.status.value, provider=record.provider, provider_ref=record.provider_ref,
            redirect_url=record.redirect_url, attempts=list(record.attempts), refunded_minor=record.refunded_minor,
            paid_at=record.paid_at)
