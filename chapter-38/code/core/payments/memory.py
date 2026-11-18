"""An in-memory repository for tests and exercises. Production uses the Django models."""
from __future__ import annotations

from .checkout import PaymentRecord


class MemoryRepo:
    def __init__(self):
        self.by_ref: dict[str, PaymentRecord] = {}

    def find_by_key(self, user_id: str, key: str) -> PaymentRecord | None:
        return next((p for p in self.by_ref.values() if p.user_id == user_id and p.idempotency_key == key), None)

    def create(self, record: PaymentRecord) -> PaymentRecord:
        self.by_ref[record.reference] = record
        return record

    def save(self, record: PaymentRecord) -> None:
        self.by_ref[record.reference] = record

    def get(self, reference: str) -> PaymentRecord | None:
        return self.by_ref.get(reference)
